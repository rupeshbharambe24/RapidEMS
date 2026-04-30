"""Drone reconnaissance — pre-arrival scene preview.

A small fleet of recon drones launches ahead of the ambulance on
serious calls (SEV-1, MCI, structure fire, multi-vehicle RTA), arrives
in 60-90 s, and streams a stub "scene preview" to the dispatcher
dashboard before the first ground unit gets there. The ALS crew
en-route sees what they're rolling into.

Why in-memory and not a DB-backed Drone model?

- The fleet is fixed (3 demo birds) and roster state — busy/free,
  current ETA, sensor payload — is fully ephemeral. Persisting it
  would only complicate Alembic for no operational gain; restarting
  the backend cancels in-flight dispatches anyway.
- This keeps Phase 3.6 a service-only addition: no migration, no
  schema churn, the dispatcher just gets a new live channel.

What lives here:

- ``DRONES`` — module-level roster, seeded at import time from
  ``settings.seed_city_lat/lng``.
- ``dispatch_drone(emergency)`` — picks the nearest free drone, fires
  a background coroutine that emits position frames at 1 Hz and a
  final scene preview after the synthetic ETA, then frees the drone.
- ``should_auto_dispatch(emergency)`` — the heuristic the emergency
  router calls so SEV-1 / MCI / fire calls trigger drones without
  the dispatcher asking.

Channels:
- ``drone:position``        live position updates while flying
- ``drone:scene_preview``   the observation payload on arrival
- ``drone:status``          launch / on_scene / returning / available
"""
from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..config import settings
from ..core.logging import log
from .geo_service import haversine_km


# ── Roster ────────────────────────────────────────────────────────────────
DRONE_SPEED_KMH = 80.0           # cruise speed; matches a Skydio-class quad
DRONE_SETUP_S = 8.0              # spool-up + clearance
DRONE_OBSERVATION_S = 4.0        # circle the scene before sending preview
POSITION_UPDATE_HZ = 1.0


@dataclass
class Drone:
    id: int
    registration: str
    base_lat: float
    base_lng: float
    sensor_payload: List[str]
    status: str = "available"   # available | en_route | on_scene | returning
    current_lat: Optional[float] = None
    current_lng: Optional[float] = None
    target_lat: Optional[float] = None
    target_lng: Optional[float] = None
    current_emergency_id: Optional[int] = None
    eta_arrival_at: Optional[float] = None
    last_preview: Optional[dict] = None


def _seed_drones() -> Dict[int, Drone]:
    base_lat = settings.seed_city_lat
    base_lng = settings.seed_city_lng
    layout = [
        # (registration, lat-offset, lng-offset, sensor payload)
        ("DRONE-201", 0.020, -0.015, ["thermal", "rgb", "spotlight"]),
        ("DRONE-202", -0.018, 0.022, ["thermal", "rgb", "loudspeaker"]),
        ("DRONE-203", 0.000, 0.000, ["thermal", "rgb", "lidar"]),
    ]
    out: Dict[int, Drone] = {}
    for i, (reg, dlat, dlng, payload) in enumerate(layout, start=1):
        d = Drone(
            id=i, registration=reg,
            base_lat=base_lat + dlat, base_lng=base_lng + dlng,
            sensor_payload=payload,
            current_lat=base_lat + dlat, current_lng=base_lng + dlng,
        )
        out[i] = d
    return out


DRONES: Dict[int, Drone] = _seed_drones()


# ── Auto-dispatch heuristic ───────────────────────────────────────────────
_FIRE_KEYWORDS = ("fire", "smoke", "explosion", "burning", "structural")
_RTA_KEYWORDS = ("rollover", "multi-vehicle", "highway pileup",
                 "bus crash", "train")


def should_auto_dispatch(*, severity: Optional[int],
                         is_multi_casualty: bool,
                         chief_complaint: Optional[str]) -> bool:
    if severity == 1:
        return True
    if is_multi_casualty:
        return True
    cc = (chief_complaint or "").lower()
    if any(k in cc for k in _FIRE_KEYWORDS) or any(k in cc for k in _RTA_KEYWORDS):
        return True
    return False


# ── ETA + dispatch ────────────────────────────────────────────────────────
def _eta_seconds(drone: Drone, target_lat: float, target_lng: float) -> float:
    if drone.current_lat is None or drone.current_lng is None:
        return float("inf")
    km = haversine_km(drone.current_lat, drone.current_lng,
                      target_lat, target_lng)
    flight_s = (km / DRONE_SPEED_KMH) * 3600.0
    return DRONE_SETUP_S + flight_s


def pick_nearest_available(target_lat: float,
                           target_lng: float) -> Optional[Tuple[Drone, float]]:
    """Return the closest free drone and its ETA in seconds, or None."""
    best: Optional[Tuple[Drone, float]] = None
    for d in DRONES.values():
        if d.status != "available":
            continue
        eta = _eta_seconds(d, target_lat, target_lng)
        if best is None or eta < best[1]:
            best = (d, eta)
    return best


def list_drones() -> List[dict]:
    out = []
    for d in DRONES.values():
        out.append({
            "id": d.id, "registration": d.registration,
            "status": d.status, "sensor_payload": d.sensor_payload,
            "current_lat": d.current_lat, "current_lng": d.current_lng,
            "base_lat": d.base_lat, "base_lng": d.base_lng,
            "current_emergency_id": d.current_emergency_id,
            "eta_arrival_at": d.eta_arrival_at,
        })
    return out


def list_active() -> List[dict]:
    return [d for d in list_drones() if d["status"] != "available"]


# ── Scene preview generator ───────────────────────────────────────────────
def _stub_scene_preview(drone: Drone, *, emergency_id: int,
                        target_lat: float, target_lng: float,
                        chief_complaint: Optional[str]) -> dict:
    """Synthesises a plausible aerial observation. In production this
    payload would be fed by an on-board CV model; here it's a deterministic
    sketch so the demo stays narratively consistent.

    The sketch is biased by the chief complaint — fire-coded calls report
    smoke / hazards, RTA-coded calls report victims / accessibility — so
    the dispatcher dashboard renders something coherent.
    """
    rng = random.Random(emergency_id * 1009)
    cc = (chief_complaint or "").lower()
    fire = any(k in cc for k in _FIRE_KEYWORDS)
    rta = any(k in cc for k in _RTA_KEYWORDS)

    if fire:
        victim_estimate = rng.randint(1, 6)
        hazards = ["smoke_visible", "active_flames"]
        access_score = 0.4
        notes = "Active fire visible from above; smoke plume north-east."
    elif rta:
        victim_estimate = rng.randint(2, 8)
        hazards = ["fuel_leak_suspected", "debris_field"]
        access_score = 0.6
        notes = "Multi-vehicle scene; lane closure recommended."
    else:
        victim_estimate = rng.randint(1, 3)
        hazards = []
        access_score = 0.85
        notes = "Single-victim scene; access clear."

    return {
        "drone_id": drone.id,
        "drone_registration": drone.registration,
        "emergency_id": emergency_id,
        "scene_lat": target_lat, "scene_lng": target_lng,
        "victim_estimate": victim_estimate,
        "hazards": hazards,
        "access_score": access_score,
        "sensor_payload": drone.sensor_payload,
        "notes": notes,
        "captured_at": time.time(),
    }


# ── Flight choreography ───────────────────────────────────────────────────
async def _fly_to_scene(drone: Drone, *, emergency_id: int,
                        target_lat: float, target_lng: float,
                        chief_complaint: Optional[str], eta_s: float) -> None:
    """Background coroutine that streams position frames, emits the scene
    preview on arrival, then returns the drone to base."""
    from ..sockets.sio import emit_drone_position, emit_drone_scene_preview, emit_drone_status

    start_lat = drone.current_lat or drone.base_lat
    start_lng = drone.current_lng or drone.base_lng
    drone.target_lat = target_lat
    drone.target_lng = target_lng

    try:
        await emit_drone_status({
            "drone_id": drone.id, "registration": drone.registration,
            "status": "en_route", "emergency_id": emergency_id,
            "eta_seconds": round(eta_s, 1),
        })
        await asyncio.sleep(DRONE_SETUP_S)
        flight_s = max(0.5, eta_s - DRONE_SETUP_S)
        steps = max(1, int(flight_s * POSITION_UPDATE_HZ))
        for i in range(1, steps + 1):
            frac = i / steps
            drone.current_lat = start_lat + (target_lat - start_lat) * frac
            drone.current_lng = start_lng + (target_lng - start_lng) * frac
            await emit_drone_position({
                "drone_id": drone.id, "registration": drone.registration,
                "lat": drone.current_lat, "lng": drone.current_lng,
                "status": drone.status, "emergency_id": emergency_id,
            })
            await asyncio.sleep(1.0 / POSITION_UPDATE_HZ)

        # On scene — circle for a beat, then push the preview.
        drone.status = "on_scene"
        await emit_drone_status({
            "drone_id": drone.id, "registration": drone.registration,
            "status": "on_scene", "emergency_id": emergency_id,
        })
        await asyncio.sleep(DRONE_OBSERVATION_S)
        preview = _stub_scene_preview(
            drone, emergency_id=emergency_id,
            target_lat=target_lat, target_lng=target_lng,
            chief_complaint=chief_complaint,
        )
        drone.last_preview = preview
        await emit_drone_scene_preview(preview)

        # Return to base.
        drone.status = "returning"
        await emit_drone_status({
            "drone_id": drone.id, "registration": drone.registration,
            "status": "returning", "emergency_id": emergency_id,
        })
        return_steps = max(1, int(flight_s * POSITION_UPDATE_HZ / 2))
        for i in range(1, return_steps + 1):
            frac = i / return_steps
            drone.current_lat = target_lat + (drone.base_lat - target_lat) * frac
            drone.current_lng = target_lng + (drone.base_lng - target_lng) * frac
            await emit_drone_position({
                "drone_id": drone.id, "registration": drone.registration,
                "lat": drone.current_lat, "lng": drone.current_lng,
                "status": drone.status, "emergency_id": emergency_id,
            })
            await asyncio.sleep(1.0 / POSITION_UPDATE_HZ)
    except asyncio.CancelledError:
        log.info(f"drone {drone.registration}: flight cancelled")
        raise
    except Exception as exc:  # noqa: BLE001
        log.exception(f"drone {drone.registration}: flight failed: {exc}")
    finally:
        drone.status = "available"
        drone.current_emergency_id = None
        drone.eta_arrival_at = None
        drone.target_lat = None
        drone.target_lng = None
        drone.current_lat = drone.base_lat
        drone.current_lng = drone.base_lng
        try:
            await emit_drone_status({
                "drone_id": drone.id, "registration": drone.registration,
                "status": "available", "emergency_id": None,
            })
        except Exception:  # noqa: BLE001
            pass


_in_flight: Dict[int, asyncio.Task] = {}


async def dispatch_drone(*, emergency_id: int,
                         target_lat: float, target_lng: float,
                         chief_complaint: Optional[str] = None
                         ) -> Optional[dict]:
    """Pick the nearest available drone and launch it. Returns the
    dispatch summary, or None if no drone is free."""
    pick = pick_nearest_available(target_lat, target_lng)
    if pick is None:
        return None
    drone, eta_s = pick
    drone.status = "en_route"
    drone.current_emergency_id = emergency_id
    drone.eta_arrival_at = time.time() + eta_s
    task = asyncio.create_task(_fly_to_scene(
        drone, emergency_id=emergency_id,
        target_lat=target_lat, target_lng=target_lng,
        chief_complaint=chief_complaint, eta_s=eta_s,
    ))
    _in_flight[drone.id] = task

    def _cleanup(_t: asyncio.Task) -> None:
        _in_flight.pop(drone.id, None)
    task.add_done_callback(_cleanup)

    return {
        "drone_id": drone.id,
        "drone_registration": drone.registration,
        "sensor_payload": drone.sensor_payload,
        "eta_seconds": round(eta_s, 1),
        "eta_arrival_at": drone.eta_arrival_at,
        "emergency_id": emergency_id,
    }
