"""AR turn-by-turn overlay generator.

Converts a route polyline into a stream of waypoints suitable for an
AR client (web WebXR, ARKit, ARCore) to anchor as floating markers
above the road. The dispatch engine already produces a polyline via
the routing chain; this module just decorates each segment with the
metadata an AR overlay needs:

  * absolute lat/lng so the client can place the marker geographically
  * forward bearing (deg from North, compass) so the marker can rotate
    to face the next leg
  * distance to next waypoint in metres for the on-screen label
  * a coarse turn cue (left / right / straight / arrive) so the icon
    swaps to an arrow

How the polyline is condensed:

The raw road-routing polylines we get back have far more vertices than
an AR overlay needs — every gentle curve produces a point, but the
driver only cares about turns and long straights. Heuristic in
``simplify``:

* Always keep the first and last vertex (start and destination anchor).
* Keep any vertex where the heading change vs the previous segment
  exceeds ``min_turn_deg`` (default 25°) — that's a junction.
* Otherwise, only keep vertices that are at least ``min_segment_m``
  apart (default 120 m) — collapses gentle curves into one straight.

The result is typically 5-15 waypoints for a 5 km city run, which is
the right density for a head-up overlay without flicker.
"""
from __future__ import annotations

import json
import math
from typing import List, Optional, Sequence, Tuple

from .geo_service import haversine_km


EARTH_M = 6371_000.0


def _bearing_deg(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Forward bearing from point 1 to point 2 in degrees from true north."""
    rl1 = math.radians(lat1)
    rl2 = math.radians(lat2)
    dlng = math.radians(lng2 - lng1)
    x = math.sin(dlng) * math.cos(rl2)
    y = (math.cos(rl1) * math.sin(rl2)
         - math.sin(rl1) * math.cos(rl2) * math.cos(dlng))
    return (math.degrees(math.atan2(x, y)) + 360.0) % 360.0


def _heading_diff(b1: float, b2: float) -> float:
    """Smallest signed difference b2 - b1 wrapped to (-180, 180]."""
    d = (b2 - b1 + 540.0) % 360.0 - 180.0
    return d


def _turn_cue(heading_change_deg: float) -> str:
    """Cue based on signed heading change at the waypoint."""
    if heading_change_deg <= -45.0:
        return "sharp_left"
    if heading_change_deg <= -20.0:
        return "left"
    if heading_change_deg >= 45.0:
        return "sharp_right"
    if heading_change_deg >= 20.0:
        return "right"
    return "straight"


def _coerce_polyline(raw: object) -> List[Tuple[float, float]]:
    """Accepts either a list[[lng,lat],...] or a JSON-encoded string of
    the same. Returns a list of (lat, lng) — note the swap, internal
    APIs prefer lat-first so consumers can splat into haversine."""
    if raw is None:
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return []
    if not isinstance(raw, list):
        return []
    out: List[Tuple[float, float]] = []
    for p in raw:
        if isinstance(p, (list, tuple)) and len(p) >= 2:
            try:
                lng = float(p[0])
                lat = float(p[1])
            except (TypeError, ValueError):
                continue
            out.append((lat, lng))
    return out


def simplify(polyline_lat_lng: Sequence[Tuple[float, float]], *,
             min_turn_deg: float = 25.0,
             min_segment_m: float = 120.0) -> List[Tuple[float, float]]:
    if len(polyline_lat_lng) <= 2:
        return list(polyline_lat_lng)
    pts = list(polyline_lat_lng)
    kept = [pts[0]]
    last_kept_idx = 0
    last_bearing: Optional[float] = None
    for i in range(1, len(pts) - 1):
        prev = pts[i - 1]
        cur = pts[i]
        nxt = pts[i + 1]
        b_in = _bearing_deg(prev[0], prev[1], cur[0], cur[1])
        b_out = _bearing_deg(cur[0], cur[1], nxt[0], nxt[1])
        change = abs(_heading_diff(b_in, b_out))
        last = kept[-1]
        seg_m = haversine_km(last[0], last[1], cur[0], cur[1]) * 1000.0
        if change >= min_turn_deg and seg_m >= 25.0:
            kept.append(cur)
            last_kept_idx = i
            last_bearing = b_out
            continue
        # No turn — only keep if the straight is getting too long.
        if seg_m >= min_segment_m:
            kept.append(cur)
            last_kept_idx = i
            last_bearing = b_out
    kept.append(pts[-1])
    return kept


def waypoints_for(polyline: object, *,
                  destination_label: Optional[str] = None
                  ) -> List[dict]:
    """Public entry — turn a stored polyline into AR waypoints."""
    coords = _coerce_polyline(polyline)
    if len(coords) < 2:
        return []
    simp = simplify(coords)
    out: List[dict] = []
    total_m = 0.0
    for i, (lat, lng) in enumerate(simp):
        if i == len(simp) - 1:
            # Destination anchor.
            prev_lat, prev_lng = simp[i - 1]
            bearing = _bearing_deg(prev_lat, prev_lng, lat, lng)
            out.append({
                "index": i, "lat": lat, "lng": lng,
                "distance_to_next_m": 0,
                "cumulative_distance_m": round(total_m),
                "bearing_deg": round(bearing, 1),
                "turn_cue": "arrive",
                "anchor": "destination",
                "label": destination_label or "Destination",
            })
            continue
        nxt_lat, nxt_lng = simp[i + 1]
        seg_m = haversine_km(lat, lng, nxt_lat, nxt_lng) * 1000.0
        bearing_out = _bearing_deg(lat, lng, nxt_lat, nxt_lng)

        if i == 0:
            cue = "depart"
            anchor = "origin"
            label: Optional[str] = "Start"
        else:
            prev_lat, prev_lng = simp[i - 1]
            bearing_in = _bearing_deg(prev_lat, prev_lng, lat, lng)
            change = _heading_diff(bearing_in, bearing_out)
            cue = _turn_cue(change)
            anchor = "intersection" if cue != "straight" else "waypoint"
            label = None
        out.append({
            "index": i, "lat": lat, "lng": lng,
            "distance_to_next_m": round(seg_m),
            "cumulative_distance_m": round(total_m),
            "bearing_deg": round(bearing_out, 1),
            "turn_cue": cue,
            "anchor": anchor,
            "label": label,
        })
        total_m += seg_m
    return out
