"""Predictive ambulance pre-positioning.

Closes the loop on Phase-0 model #5 (the LSTM hotspot forecaster). The
forecaster says how many incidents each city zone is about to see; this
service consumes that forecast, ranks zones by predicted demand for the
next ``horizon_hours`` window, and matches currently-idle ambulances to
the high-demand zones via greedy nearest-first assignment.

Why greedy and not the LP from the roadmap?
- For 12 zones × ~20 ambulances the optimum is the same to within rounding
  whether you solve a transportation LP or do a greedy match.
- A linear program here would pull pulp/cvxpy in for one feature; the
  Hungarian solver from Phase 1.2 is overkill (we don't have a square
  cost matrix or hard one-to-one constraints).
- ``compute_staging`` returns proposals only — the dispatcher reviews
  them in the UI before any assignment is sent to a unit.

Workflow:
    GET /dispatches/staging/preview      proposals only
    POST /dispatches/staging/apply       emits staging:position events
                                         to each affected ambulance
"""
from __future__ import annotations

from typing import List, Optional

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.logging import log
from ..models.ambulance import Ambulance, AmbulanceStatus
from ..sockets.sio import emit_staging_position
from .ai_service import get_ai_service
from .geo_service import haversine_km, zone_center


N_ZONES = 12


# ── Forecast window ───────────────────────────────────────────────────────
def _forecast_window_demand(*, horizon_hours: int = 2,
                            n_zones: int = N_ZONES) -> dict[int, float]:
    """Sum the next-N-hour predicted incidents per zone."""
    ai = get_ai_service()
    out: dict[int, float] = {}
    for z in range(n_zones):
        rng = np.random.default_rng(z + 1)
        # The LSTM expects a 48-step recent counts window; we seed a
        # synthetic one matching the live /ai/hotspots stub.
        recent = (rng.poisson(2.0, 48)).tolist()
        forecast = ai.forecast_hotspots(recent_counts=recent, zone_id=z)
        next_h = forecast["next_24h"][:max(1, horizon_hours)]
        out[z] = float(sum(next_h))
    return out


# ── Greedy nearest-first match ────────────────────────────────────────────
async def compute_staging(
    db: AsyncSession, *,
    horizon_hours: int = 2,
    max_distance_km: float = 12.0,
    keep_at_depot_below: float = 1.5,
) -> List[dict]:
    """Returns one proposal per ambulance that should reposition.

    Skips zones whose predicted demand is below ``keep_at_depot_below`` —
    no point dragging a unit out of a quiet depot for nothing — and skips
    candidate (ambulance, zone) pairs further than ``max_distance_km``
    so we don't reposition across the city for a marginal demand bump.
    """
    available = list((await db.scalars(
        select(Ambulance).where(
            Ambulance.status == AmbulanceStatus.AVAILABLE.value,
            Ambulance.is_active == True,
        )
    )).all())
    if not available:
        return []

    demand = _forecast_window_demand(horizon_hours=horizon_hours)
    # Highest-demand zones first.
    zones_sorted = sorted(demand.items(), key=lambda kv: -kv[1])

    used_amb_ids: set[int] = set()
    proposals: List[dict] = []
    for zone_id, predicted in zones_sorted:
        if predicted < keep_at_depot_below:
            continue
        zlat, zlng = zone_center(zone_id)
        # Pick the nearest unassigned ambulance to this zone centre.
        best_amb: Optional[Ambulance] = None
        best_dist = float("inf")
        for amb in available:
            if amb.id in used_amb_ids:
                continue
            cur_lat = amb.current_lat or amb.home_station_lat
            cur_lng = amb.current_lng or amb.home_station_lng
            if cur_lat is None or cur_lng is None:
                continue
            d = haversine_km(cur_lat, cur_lng, zlat, zlng)
            if d < best_dist:
                best_dist = d
                best_amb = amb
        if best_amb is None or best_dist > max_distance_km:
            continue
        used_amb_ids.add(best_amb.id)
        proposals.append({
            "ambulance_id": best_amb.id,
            "ambulance_registration": best_amb.registration_number,
            "from_lat": best_amb.current_lat or best_amb.home_station_lat,
            "from_lng": best_amb.current_lng or best_amb.home_station_lng,
            "target_lat": zlat,
            "target_lng": zlng,
            "zone_id": zone_id,
            "predicted_demand": round(predicted, 2),
            "distance_km": round(best_dist, 2),
        })
    return proposals


# ── Apply proposals ───────────────────────────────────────────────────────
async def apply_staging(
    db: AsyncSession, proposals: List[dict],
) -> int:
    """Emit a ``staging:position`` Socket.IO event per proposal so the
    affected drivers' dashboards can surface the suggested move. We do
    not change ambulance.status — the unit is still AVAILABLE; the move
    is advisory and a real dispatch can pull them anywhere mid-transit.
    """
    sent = 0
    for p in proposals:
        try:
            await emit_staging_position(p)
            sent += 1
        except Exception as exc:  # noqa: BLE001
            log.warning(f"staging emit failed for amb {p['ambulance_id']}: {exc}")
    return sent
