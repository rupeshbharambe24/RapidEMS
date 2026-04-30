"""Multi-provider road routing.

Provider chain (env-key gated, all free tiers):
  1. OSRM self-hosted    (if OSRM_URL set)             unlimited, no key
  2. OpenRouteService    (if ORS_API_KEY set)          2000 req/day free
  3. Mapbox Directions   (if MAPBOX_API_KEY set)       100K req/month free
  4. HERE Routes v8      (if HERE_API_KEY set)         250K req/month free
  5. Haversine fallback  (always available)

Returns RouteResult with seconds, meters, polyline (GeoJSON [[lng,lat],…]),
congestion estimate, provider name, and used_fallback flag.

The chain is short-circuit: first provider that responds wins. Failures fall
through to the next. Results are cached in-process for 120s on a coarse
geohash key so the same dispatch query doesn't re-hit the upstream API.
"""
from __future__ import annotations

import math
import time
from typing import List, Optional, Tuple

import httpx
from pydantic import BaseModel, Field

from ..config import settings
from ..core.logging import log
from ..observability.metrics import record_routing, record_routing_fallback


# ── Result schema ──────────────────────────────────────────────────────────
class RouteResult(BaseModel):
    seconds: float
    meters: float
    polyline: List[List[float]] = Field(default_factory=list,
                                        description="GeoJSON-style [[lng, lat], …]")
    congestion: float = Field(default=0.5, ge=0.0, le=1.0,
                              description="0 free-flow, 1 gridlock")
    provider: str = "haversine"
    used_fallback: bool = False


# ── Cache ──────────────────────────────────────────────────────────────────
_CACHE_TTL = 120.0
_cache: dict[str, Tuple[RouteResult, float]] = {}


def _cache_key(a: Tuple[float, float], b: Tuple[float, float]) -> str:
    # Round to 4 decimals (~11m) so micro-jitter from GPS doesn't bust the cache.
    return f"{a[0]:.4f},{a[1]:.4f}->{b[0]:.4f},{b[1]:.4f}"


def _cache_get(key: str) -> Optional[RouteResult]:
    hit = _cache.get(key)
    if not hit:
        return None
    result, expires = hit
    if expires < time.time():
        _cache.pop(key, None)
        return None
    return result


def _cache_set(key: str, value: RouteResult) -> None:
    _cache[key] = (value, time.time() + _CACHE_TTL)


# ── Geometry fallback ──────────────────────────────────────────────────────
def haversine_meters(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6_371_000.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlng / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _haversine_route(a: Tuple[float, float], b: Tuple[float, float]) -> RouteResult:
    """Last-ditch fallback. Assumes 35 km/h average urban speed."""
    meters = haversine_meters(a[0], a[1], b[0], b[1])
    seconds = meters / (35_000.0 / 3600.0)  # 35 km/h
    return RouteResult(
        seconds=seconds, meters=meters,
        polyline=[[a[1], a[0]], [b[1], b[0]]],
        congestion=0.5, provider="haversine", used_fallback=True,
    )


# ── Provider implementations ───────────────────────────────────────────────
async def _osrm(client: httpx.AsyncClient,
                a: Tuple[float, float], b: Tuple[float, float]) -> RouteResult:
    base = settings.osrm_url.rstrip("/")
    url = f"{base}/route/v1/driving/{a[1]},{a[0]};{b[1]},{b[0]}"
    params = {"overview": "false", "alternatives": "false",
              "annotations": "false", "geometries": "geojson"}
    # Ask for geometry too — the cost is small and the frontend wants it.
    params["overview"] = "full"
    r = await client.get(url, params=params)
    r.raise_for_status()
    data = r.json()
    if data.get("code") != "Ok" or not data.get("routes"):
        raise RuntimeError(f"OSRM rejected: {data.get('code')}")
    route = data["routes"][0]
    poly = route.get("geometry", {}).get("coordinates") or []
    return RouteResult(
        seconds=float(route["duration"]),
        meters=float(route["distance"]),
        polyline=poly,
        congestion=_congestion_from_speed(route["distance"], route["duration"]),
        provider="osrm",
    )


async def _ors(client: httpx.AsyncClient,
               a: Tuple[float, float], b: Tuple[float, float]) -> RouteResult:
    url = "https://api.openrouteservice.org/v2/directions/driving-car/geojson"
    headers = {"Authorization": settings.ors_api_key,
               "Content-Type": "application/json"}
    body = {"coordinates": [[a[1], a[0]], [b[1], b[0]]]}
    r = await client.post(url, headers=headers, json=body)
    r.raise_for_status()
    data = r.json()
    feat = data["features"][0]
    summary = feat["properties"]["summary"]
    poly = feat["geometry"]["coordinates"]
    return RouteResult(
        seconds=float(summary["duration"]),
        meters=float(summary["distance"]),
        polyline=poly,
        congestion=_congestion_from_speed(summary["distance"], summary["duration"]),
        provider="openrouteservice",
    )


async def _mapbox(client: httpx.AsyncClient,
                  a: Tuple[float, float], b: Tuple[float, float]) -> RouteResult:
    coords = f"{a[1]},{a[0]};{b[1]},{b[0]}"
    url = f"https://api.mapbox.com/directions/v5/mapbox/driving-traffic/{coords}"
    params = {
        "alternatives": "false",
        "geometries": "geojson",
        "overview": "full",
        "access_token": settings.mapbox_api_key,
    }
    r = await client.get(url, params=params)
    r.raise_for_status()
    data = r.json()
    if data.get("code") != "Ok" or not data.get("routes"):
        raise RuntimeError(f"Mapbox rejected: {data.get('code')}")
    route = data["routes"][0]
    poly = route.get("geometry", {}).get("coordinates") or []
    return RouteResult(
        seconds=float(route["duration"]),
        meters=float(route["distance"]),
        polyline=poly,
        congestion=_congestion_from_speed(route["distance"], route["duration"]),
        provider="mapbox",
    )


async def _here(client: httpx.AsyncClient,
                a: Tuple[float, float], b: Tuple[float, float]) -> RouteResult:
    url = "https://router.hereapi.com/v8/routes"
    params = {
        "transportMode": "car",
        "origin": f"{a[0]},{a[1]}",
        "destination": f"{b[0]},{b[1]}",
        "return": "summary,polyline",
        "apikey": settings.here_api_key,
    }
    r = await client.get(url, params=params)
    r.raise_for_status()
    data = r.json()
    if not data.get("routes"):
        raise RuntimeError("HERE returned no routes")
    section = data["routes"][0]["sections"][0]
    summary = section["summary"]
    # HERE returns flexible-polyline encoded geometry — decode lazily.
    poly = _decode_here_flexpolyline(section.get("polyline", ""))
    return RouteResult(
        seconds=float(summary["duration"]),
        meters=float(summary["length"]),
        polyline=poly,
        congestion=_congestion_from_speed(summary["length"], summary["duration"]),
        provider="here",
    )


# ── Public API ─────────────────────────────────────────────────────────────
async def route(
    from_lat: float, from_lng: float,
    to_lat: float, to_lng: float,
    *, prefer: Optional[str] = None,
) -> RouteResult:
    """Return a road-network route, falling through providers as needed.

    ``prefer`` lets the caller skip earlier providers (e.g. force ORS for an
    A/B test).
    """
    a = (from_lat, from_lng)
    b = (to_lat, to_lng)
    key = _cache_key(a, b)
    cached = _cache_get(key)
    if cached is not None:
        return cached

    chain: list[Tuple[str, callable]] = []
    if settings.osrm_url:
        chain.append(("osrm", _osrm))
    if settings.ors_api_key:
        chain.append(("openrouteservice", _ors))
    if settings.mapbox_api_key:
        chain.append(("mapbox", _mapbox))
    if settings.here_api_key:
        chain.append(("here", _here))

    if prefer is not None:
        chain = [c for c in chain if c[0] == prefer]

    last_err: Optional[str] = None
    if chain:
        async with httpx.AsyncClient(timeout=httpx.Timeout(6.0)) as client:
            for name, fn in chain:
                t0 = time.time()
                try:
                    result = await fn(client, a, b)
                    record_routing(name, ok=True,
                                   latency_seconds=time.time() - t0)
                    _cache_set(key, result)
                    return result
                except Exception as exc:  # noqa: BLE001
                    record_routing(name, ok=False,
                                   latency_seconds=time.time() - t0)
                    last_err = f"{name}: {exc}"
                    log.warning(f"routing — {name} failed: {exc}")

    fallback = _haversine_route(a, b)
    if last_err:
        log.info(f"routing — using haversine fallback ({last_err})")
    record_routing_fallback()
    record_routing("haversine", ok=True, latency_seconds=0.0)
    _cache_set(key, fallback)
    return fallback


# ── Helpers ────────────────────────────────────────────────────────────────
def _congestion_from_speed(meters: float, seconds: float) -> float:
    """Map effective speed to a 0..1 congestion estimate.

    Free-flow ≈ 50 km/h → 0.0; gridlock ≈ 5 km/h → 1.0. Provider-supplied
    real-time figures already encode congestion in the duration, so this is
    a derived estimate, not a separate measurement.
    """
    if seconds <= 0:
        return 0.5
    kph = (meters / 1000.0) / (seconds / 3600.0)
    if kph >= 50:
        return 0.0
    if kph <= 5:
        return 1.0
    return round(1.0 - (kph - 5.0) / 45.0, 3)


def _decode_here_flexpolyline(encoded: str) -> List[List[float]]:
    """HERE Flexible Polyline decoder (returns [[lng, lat], …]).

    Spec: https://github.com/heremaps/flexible-polyline
    Minimal Python port — sufficient for what HERE Routes v8 emits.
    """
    if not encoded:
        return []
    DECODING_TABLE = [
        62, -1, -1, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, -1, -1, -1, -1,
        -1, -1, -1, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16,
        17, 18, 19, 20, 21, 22, 23, 24, 25, -1, -1, -1, -1, 63, -1, 26, 27,
        28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44,
        45, 46, 47, 48, 49, 50, 51,
    ]

    def _decode_unsigned(it):
        result = 0
        shift = 0
        while True:
            ch = next(it)
            v = DECODING_TABLE[ord(ch) - 45] if 45 <= ord(ch) - 45 + 45 < 0x7e else -1
            if v < 0:
                raise ValueError("invalid flex-polyline char")
            result |= (v & 0x1F) << shift
            if v < 0x20:
                return result
            shift += 5

    def _to_signed(v):
        return ~(v >> 1) if v & 1 else (v >> 1)

    it = iter(encoded)
    header_version = _decode_unsigned(it)  # noqa: F841
    meta = _decode_unsigned(it)
    precision = meta & 0x0F
    third_dim = (meta >> 4) & 0x07
    third_dim_precision = (meta >> 7) & 0x0F  # noqa: F841
    factor = 10 ** precision
    coords: List[List[float]] = []
    last_lat = 0
    last_lng = 0
    try:
        while True:
            last_lat += _to_signed(_decode_unsigned(it))
            last_lng += _to_signed(_decode_unsigned(it))
            if third_dim:
                _decode_unsigned(it)  # discard 3rd dim if present
            coords.append([last_lng / factor, last_lat / factor])
    except StopIteration:
        pass
    return coords
