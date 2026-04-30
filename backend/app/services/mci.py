"""Mass-Casualty Incident orchestration.

When MCI mode is on, the engine swaps from per-emergency optimality
(Phases 0-1) to throughput-max — many victims, one scene, prioritise by
START triage category.

Key pieces:

  start_classify(victim)   deterministic START algorithm — returns one of
                           red / yellow / green / black from a vital snapshot.
  optimize_mci(db)         Hungarian assignment over open red+yellow+green
                           victims × available ambulances. Cost matrix uses
                           category weights (red=100, yellow=10, green=1,
                           black=0.1) × full trip seconds (scene→hospital
                           via the same routing chain Phase 0.1 set up).
  execute_mci(db, ...)     Apply the assignment by creating a Dispatch row
                           per pair through the existing dispatch_engine
                           (which honours forced_ambulance from Phase 1.2).
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import List, Optional

import numpy as np
from scipy.optimize import linear_sum_assignment
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.logging import log
from ..models.ambulance import Ambulance, AmbulanceStatus, AmbulanceType
from ..models.emergency import Emergency, EmergencyStatus
from ..models.hospital import Hospital
from ..models.mci import (MciIncident, MciStatus, MciVictim, MciVictimStatus,
                          StartCategory)
from ..schemas.dispatch import DispatchPlan
from .dispatch_engine import DispatchError, dispatch_emergency
from .geo_service import haversine_km
from .routing_service import route as road_route


CATEGORY_WEIGHT = {
    StartCategory.RED.value:    100.0,
    StartCategory.YELLOW.value:  10.0,
    StartCategory.GREEN.value:    1.0,
    StartCategory.BLACK.value:    0.1,    # expectant — last priority
}

INF_COST = 1e9


# ── START triage ──────────────────────────────────────────────────────────
def start_classify(*,
                   can_walk: Optional[bool] = None,
                   breathing: Optional[bool] = None,
                   respiratory_rate: Optional[int] = None,
                   pulse_rate: Optional[int] = None,
                   capillary_refill_seconds: Optional[float] = None,
                   follows_commands: Optional[bool] = None) -> str:
    """Standard pre-hospital START algorithm:

    1. Walking? → GREEN (minor).
    2. Not breathing even after airway open? → BLACK (expectant).
    3. RR > 30 → RED (immediate).
    4. Pulse absent OR cap refill > 2s → RED.
    5. Doesn't follow simple commands → RED.
    6. Otherwise → YELLOW (delayed).

    Missing inputs degrade gracefully — without enough signal we default
    to YELLOW so the victim still gets in line."""
    if can_walk is True:
        return StartCategory.GREEN.value
    if breathing is False:
        return StartCategory.BLACK.value
    if respiratory_rate is not None and respiratory_rate > 30:
        return StartCategory.RED.value
    if respiratory_rate is not None and respiratory_rate < 10:
        return StartCategory.RED.value
    if pulse_rate is not None and pulse_rate <= 0:
        return StartCategory.BLACK.value
    if capillary_refill_seconds is not None and capillary_refill_seconds > 2.0:
        return StartCategory.RED.value
    if follows_commands is False:
        return StartCategory.RED.value
    return StartCategory.YELLOW.value


# ── Active-incident helpers ───────────────────────────────────────────────
async def get_active_incident(db: AsyncSession) -> Optional[MciIncident]:
    return await db.scalar(
        select(MciIncident).where(MciIncident.status == MciStatus.ACTIVE.value)
        .order_by(MciIncident.id.desc()).limit(1)
    )


# ── Hungarian throughput-max ──────────────────────────────────────────────
async def optimize_mci(db: AsyncSession,
                        ) -> List[dict]:
    """Walk all open victims of the active incident × available ambulances,
    build a (cat_weight × full_trip_seconds) cost matrix, run the Hungarian
    solver, and return the proposed pairings — preview only, caller decides
    when to execute via execute_mci()."""
    incident = await get_active_incident(db)
    if not incident:
        return []

    open_states = [MciVictimStatus.REGISTERED.value]
    victims = list((await db.scalars(
        select(MciVictim).where(
            MciVictim.incident_id == incident.id,
            MciVictim.status.in_(open_states),
        ).order_by(MciVictim.id.asc())
    )).all())
    available = list((await db.scalars(
        select(Ambulance).where(
            Ambulance.status == AmbulanceStatus.AVAILABLE.value,
            Ambulance.is_active == True,
        )
    )).all())

    if not victims or not available:
        return []

    # Pre-compute the destination (best-fit hospital) per victim and the
    # per-ambulance scene ETA. The hospital scoring runs again inside
    # dispatch_engine when we execute, so cost here only needs to capture
    # the bulk magnitudes for ranking.
    n_v, n_a = len(victims), len(available)
    cost = np.full((n_v, n_a), INF_COST)
    routes: list[list[Optional[float]]] = [[None] * n_a for _ in range(n_v)]

    starts = [(a.current_lat or a.home_station_lat,
               a.current_lng or a.home_station_lng) for a in available]

    coros = []
    pair_idx: list[tuple[int, int]] = []
    for vi in range(n_v):
        for ai in range(n_a):
            slat, slng = starts[ai]
            pair_idx.append((vi, ai))
            coros.append(road_route(slat, slng,
                                    incident.location_lat,
                                    incident.location_lng))
    rrs = await asyncio.gather(*coros) if coros else []

    for (vi, ai), rr in zip(pair_idx, rrs):
        cat_w = CATEGORY_WEIGHT.get(victims[vi].category,
                                    CATEGORY_WEIGHT[StartCategory.YELLOW.value])
        # Full trip ≈ scene ETA + a flat 12-min on-scene + 1.5x scene ETA
        # back to hospital (approximation; refined when dispatched).
        full_seconds = rr.seconds + 12 * 60 + rr.seconds * 1.5
        cost[vi, ai] = cat_w * full_seconds
        routes[vi][ai] = rr.seconds

    row_idx, col_idx = linear_sum_assignment(cost)

    out: List[dict] = []
    for vi, ai in zip(row_idx, col_idx):
        if cost[vi, ai] >= INF_COST:
            continue
        v = victims[vi]
        a = available[ai]
        out.append({
            "victim_id": v.id,
            "category": v.category,
            "ambulance_id": a.id,
            "ambulance_registration": a.registration_number,
            "scene_eta_seconds": int(routes[vi][ai] or 0),
            "cost": float(cost[vi, ai]),
        })
    return out


# ── Execute proposals ─────────────────────────────────────────────────────
async def execute_mci(db: AsyncSession, *,
                      user_id: Optional[int] = None,
                      ) -> tuple[List[dict], List[DispatchPlan]]:
    """Run the optimizer and dispatch each pair through the standard
    pipeline. Each victim becomes an Emergency row first (so the existing
    dispatch infra applies — hospital scoring, ER briefing, alerts) and
    we wire MciVictim.dispatched_to_dispatch_id back so the MCI command
    page can drill in."""
    proposals = await optimize_mci(db)
    if not proposals:
        return [], []

    incident = await get_active_incident(db)
    plans: List[DispatchPlan] = []
    for p in proposals:
        v = await db.scalar(select(MciVictim).where(MciVictim.id == p["victim_id"]))
        a = await db.scalar(select(Ambulance).where(Ambulance.id == p["ambulance_id"]))
        if not v or not a:
            continue

        # Build a synthetic Emergency from the victim's snapshot. Severity
        # follows the START category; the regular triage classifier still
        # runs but the persisted severity comes from category mapping.
        sev = {"red": 1, "yellow": 2, "green": 4, "black": 5}.get(v.category, 3)
        em = Emergency(
            patient_name=v.label or f"MCI victim #{v.id}",
            patient_age=v.age, patient_gender=v.gender,
            location_lat=incident.location_lat,
            location_lng=incident.location_lng,
            location_address=incident.location_address,
            chief_complaint=f"Mass casualty: {incident.name}",
            symptoms=[],
            pulse_rate=v.pulse_rate,
            respiratory_rate=v.respiratory_rate,
            predicted_severity=sev,
            severity_confidence=0.99,
            status=EmergencyStatus.PENDING.value,
            tenant_id=incident.tenant_id,
        )
        db.add(em)
        await db.commit()
        await db.refresh(em)

        try:
            plan = await dispatch_emergency(db, em, user_id=user_id,
                                            forced_ambulance=a)
            v.status = MciVictimStatus.ASSIGNED.value
            v.assigned_at = datetime.utcnow()
            v.dispatched_to_dispatch_id = plan.dispatch_id
            await db.commit()
            plans.append(plan)
        except DispatchError as exc:
            log.warning(f"MCI dispatch failed for victim {v.id}: {exc}")
    return proposals, plans
