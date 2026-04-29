"""Hungarian-algorithm multi-emergency assignment.

When two or more PENDING emergencies exist at the same time, the per-emergency
greedy ambulance picker produces locally-optimal but globally-bad results — a
SEV-3 logged five seconds before a SEV-1 will claim the nearest ALS unit.

This module replaces that with a global cost-minimising assignment over the
entire emergency × ambulance grid:

    cost[e][a] = severity_weight(e) * blended_eta(e, a)

where ``blended_eta`` is the same ``ETA_ROAD_WEIGHT * road_eta + (1-w) * ml_eta``
the dispatch engine uses, and forbidden type pairings (e.g. SEV-1 on a BLS
unit) get a sentinel cost of ``+inf``. ``scipy.optimize.linear_sum_assignment``
handles rectangular matrices natively, so cases with more emergencies than
ambulances (or vice versa) work without padding.

Two modes:

* ``preview=True``  — returns the proposed assignments without persisting.
* ``preview=False`` — calls ``dispatch_engine.dispatch_emergency`` once per
  pair with ``forced_ambulance``; that path also handles hospital scoring,
  audit log, hospital-alert + briefing, notifications, and socket events.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import List, Optional, Tuple

import numpy as np
from scipy.optimize import linear_sum_assignment
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..core.logging import log
from ..models.ambulance import Ambulance, AmbulanceStatus, AmbulanceType
from ..models.emergency import Emergency, EmergencyStatus
from ..schemas.dispatch import DispatchPlan
from .ai_service import get_ai_service
from .dispatch_engine import DispatchError, dispatch_emergency
from .geo_service import estimate_zone_id, haversine_km
from .routing_service import RouteResult, route as road_route


# Higher weight = more cost penalty per second of ETA, so the solver
# strongly prefers to give critical calls the fastest unit.
SEVERITY_WEIGHT = {1: 100.0, 2: 25.0, 3: 5.0, 4: 1.0, 5: 0.5}

# Sentinel for forbidden ambulance/severity pairings. Picked large enough to
# dominate any realistic blended ETA × severity_weight product (~10^6).
INF_COST = 1e9


_TYPES_BY_SEVERITY = {
    1: {AmbulanceType.ALS.value, AmbulanceType.ICU_MOBILE.value},
    2: {AmbulanceType.ALS.value, AmbulanceType.ICU_MOBILE.value},
    3: {AmbulanceType.BLS.value, AmbulanceType.ALS.value,
        AmbulanceType.ICU_MOBILE.value},
    4: {AmbulanceType.BLS.value},
    5: {AmbulanceType.BLS.value},
}


# ── Result schemas (returned to the API) ──────────────────────────────────
class Proposal:
    """Plain Python container so API layer can serialise as Pydantic later."""
    __slots__ = ("emergency_id", "ambulance_id", "ambulance_registration",
                 "predicted_eta_seconds", "predicted_eta_minutes",
                 "severity_level", "cost", "road_provider")

    def __init__(self, *, emergency_id, ambulance_id, ambulance_registration,
                 predicted_eta_seconds, severity_level, cost, road_provider):
        self.emergency_id = emergency_id
        self.ambulance_id = ambulance_id
        self.ambulance_registration = ambulance_registration
        self.predicted_eta_seconds = predicted_eta_seconds
        self.predicted_eta_minutes = round(predicted_eta_seconds / 60.0, 1)
        self.severity_level = severity_level
        self.cost = cost
        self.road_provider = road_provider

    def as_dict(self) -> dict:
        return {
            "emergency_id": self.emergency_id,
            "ambulance_id": self.ambulance_id,
            "ambulance_registration": self.ambulance_registration,
            "predicted_eta_seconds": int(self.predicted_eta_seconds),
            "predicted_eta_minutes": self.predicted_eta_minutes,
            "severity_level": self.severity_level,
            "cost": float(self.cost),
            "road_provider": self.road_provider,
        }


# ── Cost matrix construction ──────────────────────────────────────────────
async def _build_cost_matrix(
    db: AsyncSession, emergencies: List[Emergency], ambulances: List[Ambulance],
) -> Tuple[np.ndarray, List[List[Optional[RouteResult]]],
           List[List[Optional[float]]], List[int]]:
    """Returns (cost, routes, etas, severities) where:
       routes[e][a]: RouteResult or None if forbidden/missing
       etas[e][a]:   blended seconds or None
       severities:   severity per emergency (re-uses persisted if present, else
                     re-runs the severity classifier)."""
    ai = get_ai_service()
    n_e, n_a = len(emergencies), len(ambulances)
    cost = np.full((n_e, n_a), INF_COST)
    routes: List[List[Optional[RouteResult]]] = [[None] * n_a for _ in range(n_e)]
    etas: List[List[Optional[float]]] = [[None] * n_a for _ in range(n_e)]
    severities: List[int] = []

    # Resolve severities up front so the cost weight is correct.
    for e in emergencies:
        if e.predicted_severity:
            severities.append(int(e.predicted_severity))
        else:
            triage = ai.predict_severity(
                age=e.patient_age or 40,
                gender=e.patient_gender or "other",
                gcs=e.gcs_score, spo2=e.spo2,
                pulse=e.pulse_rate, resp_rate=e.respiratory_rate,
                bp_systolic=e.blood_pressure_systolic,
                bp_diastolic=e.blood_pressure_diastolic,
                symptoms=e.symptoms or [],
            )
            severities.append(int(triage["severity_level"]))

    # Resolve current GPS for each ambulance once.
    starts = []
    for a in ambulances:
        if a.current_lat is None or a.current_lng is None:
            starts.append((a.home_station_lat, a.home_station_lng))
        else:
            starts.append((a.current_lat, a.current_lng))

    type_to_int = {AmbulanceType.BLS.value: 0,
                   AmbulanceType.ALS.value: 1,
                   AmbulanceType.ICU_MOBILE.value: 2}

    # Fan out road_route calls for every (emergency × candidate ambulance)
    # pair where the type is allowed. Forbidden pairings stay at INF_COST.
    pair_indices: list[tuple[int, int]] = []
    coros = []
    for ei, e in enumerate(emergencies):
        sev = severities[ei]
        allowed = _TYPES_BY_SEVERITY.get(sev, set())
        for ai_idx, a in enumerate(ambulances):
            if a.ambulance_type not in allowed:
                continue
            pair_indices.append((ei, ai_idx))
            (slat, slng) = starts[ai_idx]
            coros.append(road_route(slat, slng, e.location_lat, e.location_lng))

    rrs = await asyncio.gather(*coros) if coros else []

    now = datetime.utcnow()
    for (ei, ai_idx), rr in zip(pair_indices, rrs):
        e = emergencies[ei]
        a = ambulances[ai_idx]
        sev = severities[ei]
        road_km = rr.meters / 1000.0
        # Same blend the engine uses for single-emergency dispatch.
        eta_pred = ai.predict_eta(
            distance_km=road_km, congestion=rr.congestion,
            hour=now.hour, day_of_week=now.weekday(), weather=0,
            ambulance_type=type_to_int.get(a.ambulance_type, 0),
            road_type=0,
        )
        w = settings.eta_road_weight if not rr.used_fallback else 0.0
        blended = w * rr.seconds + (1.0 - w) * eta_pred["eta_seconds"]
        weight = SEVERITY_WEIGHT.get(sev, 1.0)
        cost[ei, ai_idx] = weight * blended
        routes[ei][ai_idx] = rr
        etas[ei][ai_idx] = blended

    return cost, routes, etas, severities


# ── Public entry point ────────────────────────────────────────────────────
async def optimize(
    db: AsyncSession, *, preview: bool = True, user_id: Optional[int] = None,
) -> Tuple[List[Proposal], List[int], List[Optional[DispatchPlan]]]:
    """Return (proposals, unassigned_emergency_ids, dispatch_plans).

    ``dispatch_plans`` is parallel to ``proposals``; entries are ``None`` in
    preview mode.
    """
    # Pull pending emergencies in arrival order so ties break predictably.
    pending = (await db.scalars(
        select(Emergency)
        .where(Emergency.status == EmergencyStatus.PENDING.value)
        .order_by(Emergency.created_at.asc())
    )).all()
    available = (await db.scalars(
        select(Ambulance).where(
            Ambulance.status == AmbulanceStatus.AVAILABLE.value,
            Ambulance.is_active == True,
        )
    )).all()

    if not pending or not available:
        return [], [e.id for e in pending], []

    cost, routes, etas, severities = await _build_cost_matrix(
        db, list(pending), list(available)
    )

    # Hungarian — handles rectangular matrices automatically.
    row_idx, col_idx = linear_sum_assignment(cost)

    proposals: List[Proposal] = []
    chosen_emergencies: set[int] = set()
    for ei, ai_idx in zip(row_idx, col_idx):
        if cost[ei, ai_idx] >= INF_COST:
            continue   # forbidden — skip; emergency stays unassigned
        e = pending[ei]
        a = available[ai_idx]
        proposals.append(Proposal(
            emergency_id=e.id,
            ambulance_id=a.id,
            ambulance_registration=a.registration_number,
            predicted_eta_seconds=etas[ei][ai_idx],
            severity_level=severities[ei],
            cost=cost[ei, ai_idx],
            road_provider=routes[ei][ai_idx].provider if routes[ei][ai_idx] else "haversine",
        ))
        chosen_emergencies.add(e.id)

    unassigned = [e.id for e in pending if e.id not in chosen_emergencies]

    if preview:
        log.info(f"multi_dispatch preview: "
                 f"{len(proposals)} proposed, {len(unassigned)} unassigned")
        return proposals, unassigned, [None] * len(proposals)

    # Execute mode — run dispatch_engine.dispatch_emergency once per proposal
    # with forced_ambulance so each assignment is honoured even if the local
    # greedy choice would have differed.
    plans: List[Optional[DispatchPlan]] = []
    for prop in proposals:
        e = next(em for em in pending if em.id == prop.emergency_id)
        a = next(am for am in available if am.id == prop.ambulance_id)
        try:
            plan = await dispatch_emergency(db, e, user_id=user_id,
                                            forced_ambulance=a)
            plans.append(plan)
        except DispatchError as exc:
            log.warning(f"multi_dispatch execute: emergency {e.id} failed: {exc}")
            plans.append(None)
    return proposals, unassigned, plans
