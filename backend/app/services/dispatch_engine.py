"""Dispatch engine — the orchestrator.

Given an Emergency, this:
  1. Triages severity from vitals + symptoms
  2. Filters ambulances by required type (Critical → ALS/ICU only)
  3. Estimates ETA for each candidate ambulance using current traffic
  4. Picks the lowest-ETA ambulance
  5. Scores every capable hospital, picks the best
  6. Creates a Dispatch record
  7. Marks the chosen ambulance EN_ROUTE
  8. Returns a complete plan

This is the only place where the 5 ML models meaningfully come together.
"""
import asyncio
import json
from datetime import datetime
from typing import Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..core.logging import log
from ..models.ambulance import Ambulance, AmbulanceStatus, AmbulanceType
from ..models.audit_log import AuditLog
from ..models.dispatch import Dispatch, DispatchStatus
from ..models.emergency import Emergency, EmergencyStatus
from ..models.hospital import Hospital
from ..models.hospital_alert import AlertStatus, HospitalAlert
from ..schemas.dispatch import DispatchPlan
from ..sockets.sio import emit_hospital_alert, emit_hospital_alert_status
from .ai_service import get_ai_service
from ..observability.metrics import (record_dispatch_outcome,
                                     time_dispatch)
from .audit_chain import append as audit_append
from .er_briefing import generate_briefing
from .geo_service import estimate_zone_id, haversine_km
from .ml_extras import (dispatch_match_multiplier, hospital_wait_estimate,
                        outcome_probability)
from .notifications import notify_dispatch_created
from .routing_service import RouteResult, route as road_route


class DispatchError(Exception):
    """Raised when dispatch is impossible (no ambulances, no hospitals)."""


async def _briefing_background(dispatch_id: int, alert_id: int,
                               hospital_id: int) -> None:
    """Generate the ER briefing in its own session after dispatch returns."""
    from ..database import AsyncSessionLocal
    from sqlalchemy import select as _select
    try:
        async with AsyncSessionLocal() as db:
            d = await db.scalar(_select(Dispatch).where(Dispatch.id == dispatch_id))
            if not d:
                return
            text = await generate_briefing(db, d)
            alert = await db.scalar(
                _select(HospitalAlert).where(HospitalAlert.id == alert_id))
            if not alert:
                return
            alert.briefing = text
            await db.commit()
        await emit_hospital_alert_status({
            "alert_id": alert_id, "hospital_id": hospital_id,
            "briefing_ready": True,
        })
    except Exception as exc:  # noqa: BLE001
        log.warning(f"briefing background task failed: {exc}")


async def dispatch_emergency(
    db: AsyncSession, emergency: Emergency,
    user_id: Optional[int] = None,
    *,
    forced_ambulance: Optional[Ambulance] = None,
) -> DispatchPlan:
    """Run the full dispatch pipeline for an emergency.

    ``forced_ambulance`` is supplied by the multi-emergency optimizer
    (Phase 1.2) so the Hungarian assignment is honoured even when a different
    ambulance would have been the greedy local pick.
    """
    with time_dispatch():
        try:
            return await _dispatch_emergency_inner(
                db, emergency, user_id, forced_ambulance=forced_ambulance)
        except DispatchError:
            # Severity may already be persisted on the emergency row even
            # when the candidate filter / hospital scoring fails.
            sev = int(emergency.predicted_severity or 0)
            record_dispatch_outcome(sev, ok=False)
            raise


async def _dispatch_emergency_inner(
    db: AsyncSession, emergency: Emergency,
    user_id: Optional[int] = None,
    *,
    forced_ambulance: Optional[Ambulance] = None,
) -> DispatchPlan:
    # Phase 3.10 chaos hook — admin can dial up a synthetic dispatch
    # failure rate to verify retry / re-route logic.
    from .chaos import maybe_delay_severity, maybe_fail_dispatch
    chaos_reason = maybe_fail_dispatch(emergency.id)
    if chaos_reason:
        raise DispatchError(chaos_reason)

    ai = get_ai_service()
    now = datetime.utcnow()
    used_fallback = False

    # ── 1. Triage ─────────────────────────────────────────
    await maybe_delay_severity()

    triage = ai.predict_severity(
        age=emergency.patient_age or 40,
        gender=emergency.patient_gender or "other",
        gcs=emergency.gcs_score,
        spo2=emergency.spo2,
        pulse=emergency.pulse_rate,
        resp_rate=emergency.respiratory_rate,
        bp_systolic=emergency.blood_pressure_systolic,
        bp_diastolic=emergency.blood_pressure_diastolic,
        symptoms=emergency.symptoms or [],
    )
    used_fallback = used_fallback or triage["used_fallback"]
    severity_level = triage["severity_level"]

    # Persist triage results on the emergency
    emergency.predicted_severity = severity_level
    emergency.severity_confidence = triage["confidence"]
    # Honor an LLM-set patient_type from intake; only re-infer if blank.
    if emergency.inferred_patient_type:
        patient_type = emergency.inferred_patient_type
    else:
        patient_type = ai.infer_patient_type(emergency.symptoms or [],
                                             age=emergency.patient_age)
        emergency.inferred_patient_type = patient_type
    await db.commit()

    # ── 2. Filter ambulances by required type ─────────────
    if severity_level <= 2:                    # Critical / Serious
        required = [AmbulanceType.ALS.value, AmbulanceType.ICU_MOBILE.value]
    elif severity_level == 3:                  # Moderate
        required = [AmbulanceType.BLS.value, AmbulanceType.ALS.value,
                    AmbulanceType.ICU_MOBILE.value]
    else:                                      # Minor / Non-emergency
        required = [AmbulanceType.BLS.value]

    if forced_ambulance is not None:
        candidates = [forced_ambulance]
    else:
        candidates = (await db.scalars(
            select(Ambulance).where(
                Ambulance.status == AmbulanceStatus.AVAILABLE.value,
                Ambulance.is_active == True,
                Ambulance.ambulance_type.in_(required),
            )
        )).all()

        if not candidates:
            # Relax type constraint as a fallback.
            candidates = (await db.scalars(
                select(Ambulance).where(
                    Ambulance.status == AmbulanceStatus.AVAILABLE.value,
                    Ambulance.is_active == True,
                )
            )).all()
            if candidates:
                log.warning(f"No ambulances of required type {required} — using any available")

        if not candidates:
            raise DispatchError("No available ambulances right now.")

    # ── 3. ETA per candidate using current traffic ────────
    zone_id = estimate_zone_id(emergency.location_lat, emergency.location_lng)
    traffic = ai.predict_congestion(
        zone_id=zone_id,
        hour=now.hour, day_of_week=now.weekday(), month=now.month,
        weather=0,  # could plug in a real weather API
        is_holiday=0,
        zone_density=0.7,
        lat=emergency.location_lat, lng=emergency.location_lng,
    )
    used_fallback = used_fallback or traffic["used_fallback"]
    congestion = traffic["congestion"]

    best_amb = None
    best_eta_seconds = float("inf")
    best_distance_km = 0.0
    best_road_meters: Optional[float] = None
    best_route: Optional[RouteResult] = None

    type_to_int = {AmbulanceType.BLS.value: 0,
                   AmbulanceType.ALS.value: 1,
                   AmbulanceType.ICU_MOBILE.value: 2}

    # Resolve current GPS for every candidate (depot fallback if unreported).
    starts = []
    for amb in candidates:
        if amb.current_lat is None or amb.current_lng is None:
            starts.append((amb.home_station_lat, amb.home_station_lng))
        else:
            starts.append((amb.current_lat, amb.current_lng))

    # Parallel road-routing for every candidate. Even with 20 candidates this
    # finishes in roughly the slowest provider's response time, not 20× it.
    routes: list[RouteResult] = await asyncio.gather(*[
        road_route(s[0], s[1], emergency.location_lat, emergency.location_lng)
        for s in starts
    ])

    # Score each candidate by blending road ETA with ML ETA per the configured
    # weight. Falls back to ML-only when the routing chain only had haversine.
    # The blended ETA is then nudged by the equipment + paramedic-skill match
    # multiplier — a perfectly-equipped, ALS-certified crew on a cardiac call
    # gets an effective ~25% ETA bonus over a BLS unit even at the same
    # distance, which steers the picker toward the right vehicle.
    best_match_detail: Optional[Dict] = None
    for amb, (cur_lat, cur_lng), rr in zip(candidates, starts, routes):
        road_km = rr.meters / 1000.0
        d_km = haversine_km(cur_lat, cur_lng,
                            emergency.location_lat, emergency.location_lng)
        eta = ai.predict_eta(
            distance_km=road_km, congestion=rr.congestion or congestion,
            hour=now.hour, day_of_week=now.weekday(),
            weather=0,
            ambulance_type=type_to_int.get(amb.ambulance_type, 0),
            road_type=0,
        )
        used_fallback = used_fallback or eta["used_fallback"] or rr.used_fallback
        w = settings.eta_road_weight if not rr.used_fallback else 0.0
        blended = w * rr.seconds + (1.0 - w) * eta["eta_seconds"]

        match_mult, match_detail = dispatch_match_multiplier(
            patient_type=patient_type,
            ambulance_equipment=amb.equipment,
            paramedic_certification=amb.paramedic_certification,
        )
        scored = blended * match_mult

        if scored < best_eta_seconds:
            best_eta_seconds = scored
            best_amb = amb
            best_distance_km = d_km
            best_road_meters = rr.meters
            best_route = rr
            best_match_detail = match_detail

    # ── 4. Pick the best capable hospital ─────────────────
    candidate_hospitals = (await db.scalars(
        select(Hospital).where(Hospital.is_active == True)
    )).all()
    if not candidate_hospitals:
        raise DispatchError("No active hospitals in the system.")

    # Helipad bias: when SEV-1 + ground ETA already long enough that air
    # would help, give helipad-equipped hospitals a recommender boost so
    # the pipeline naturally lands on one when reasonable.
    helipad_bonus_active = (
        severity_level == 1
        and (best_eta_seconds / 60.0) > settings.helicopter_min_savings_minutes * 1.5
    )

    best_hosp = None
    best_score = -1.0
    best_hospital_wait: Optional[int] = None
    for h in candidate_hospitals:
        d_h = haversine_km(emergency.location_lat, emergency.location_lng,
                            h.lat, h.lng)
        scored = ai.score_hospital(patient_type=patient_type,
                                   hospital=h, distance_km=d_h)
        used_fallback = used_fallback or scored["used_fallback"]

        # Refine the static er_wait_minutes with a time-of-day curve so a
        # 5pm weekday call avoids the ER everyone else is also flooding.
        wait = hospital_wait_estimate(
            base_er_wait_minutes=h.er_wait_minutes or 0,
            is_diversion=h.is_diversion, when=now,
        )
        # Penalty: each predicted minute of wait shaves up to 0.005 off the
        # recommender score (so 60-min wait ≈ −0.30 score).
        penalty = min(0.30, wait["predicted_wait_minutes"] * 0.005)
        adj_score = scored["score"] - penalty
        if helipad_bonus_active and h.has_helipad and d_h <= settings.helicopter_max_range_km:
            # Bias scales with ground-ETA — the longer the ground trip, the
            # stronger the pull toward a helipad-equipped facility. 30 min →
            # +0.60 boost; 60 min → +0.80; capped to keep recommender ≤ ~1.5.
            ground_min = best_eta_seconds / 60.0
            adj_score += min(0.80, 0.30 + ground_min * 0.01)

        if adj_score > best_score:
            best_score = adj_score
            best_hosp = h
            best_hospital_wait = wait["predicted_wait_minutes"]

    if best_hosp is None:
        raise DispatchError("Could not score any hospital.")

    # ── Helicopter dispatch eligibility ──────────────────
    # SEV-1 calls where ground transit is far enough that lift+land
    # overhead pays for itself, and a helipad-equipped hospital is
    # within range of both scene and destination.
    air_proposed = False
    air_reason: Optional[str] = None
    air_eta_seconds: Optional[float] = None
    air_distance_km: Optional[float] = None
    if severity_level == 1 and best_amb is not None:
        ground_minutes = best_eta_seconds / 60.0
        scene_to_hosp_km = haversine_km(
            emergency.location_lat, emergency.location_lng,
            best_hosp.lat, best_hosp.lng,
        )
        # Air time scene → hospital + lift/land overhead.
        air_seconds_calc = (
            settings.helicopter_setup_minutes * 60.0
            + (scene_to_hosp_km / settings.helicopter_speed_kmh) * 3600.0
        )
        air_minutes_calc = air_seconds_calc / 60.0
        in_range = scene_to_hosp_km <= settings.helicopter_max_range_km
        helipad_ok = bool(best_hosp.has_helipad)
        savings_ok = (ground_minutes - air_minutes_calc) >= settings.helicopter_min_savings_minutes
        if in_range and helipad_ok and savings_ok:
            air_proposed = True
            air_reason = (f"SEV-1 with ground ETA {ground_minutes:.1f}m vs "
                          f"air {air_minutes_calc:.1f}m — savings "
                          f"{ground_minutes - air_minutes_calc:.1f}m.")
            air_eta_seconds = air_seconds_calc
            air_distance_km = scene_to_hosp_km
        elif severity_level == 1 and not helipad_ok:
            air_reason = "Air dispatch skipped: best-fit hospital lacks a helipad."
        elif severity_level == 1 and not savings_ok:
            air_reason = "Air dispatch skipped: ground ETA already competitive."
        elif severity_level == 1:
            air_reason = "Air dispatch skipped: hospital out of helicopter range."

    # Outcome predictor — surfaces on the dispatch plan + audit log so the
    # dispatcher can see the model's 30-day survival probability for this case.
    outcome = outcome_probability(
        severity_level=severity_level,
        age=emergency.patient_age,
        spo2=emergency.spo2,
        pulse_rate=emergency.pulse_rate,
        respiratory_rate=emergency.respiratory_rate,
        blood_pressure_systolic=emergency.blood_pressure_systolic,
        gcs_score=emergency.gcs_score,
    )

    # ── 5. Persist Dispatch + side effects ────────────────
    dispatch = Dispatch(
        emergency_id=emergency.id,
        ambulance_id=best_amb.id,
        hospital_id=best_hosp.id,
        dispatched_at=now,
        predicted_eta_seconds=int(best_eta_seconds),
        distance_meters=float(best_distance_km * 1000),
        hospital_recommendation_score=float(best_score),
        status=DispatchStatus.EN_ROUTE.value,
        # Persist the route polyline so the AR overlay (Phase 3.5) and
        # post-incident replay can read it back without re-routing.
        route_polyline=(json.dumps(best_route.polyline)
                        if best_route and best_route.polyline else None),
    )
    db.add(dispatch)

    best_amb.status = AmbulanceStatus.EN_ROUTE.value
    emergency.status = EmergencyStatus.DISPATCHED.value

    await audit_append(db, AuditLog(
        user_id=user_id,
        action="dispatch_created",
        entity_type="emergency",
        entity_id=emergency.id,
        details={
            "ambulance_id": best_amb.id,
            "hospital_id": best_hosp.id,
            "severity_level": severity_level,
            "predicted_eta_s": int(best_eta_seconds),
            "used_fallback": used_fallback,
        },
    ))
    await db.commit()
    await db.refresh(dispatch)

    # Hospital pre-arrival alert. The briefing slot is filled by Phase 0.9.
    alert = HospitalAlert(
        hospital_id=best_hosp.id,
        dispatch_id=dispatch.id,
        emergency_id=emergency.id,
        severity_level=severity_level,
        eta_seconds=int(best_eta_seconds),
        patient_type=patient_type,
        status=AlertStatus.PENDING.value,
    )
    db.add(alert)
    await db.commit()
    await db.refresh(alert)
    await emit_hospital_alert({
        "id": alert.id,
        "hospital_id": best_hosp.id,
        "hospital_name": best_hosp.name,
        "dispatch_id": dispatch.id,
        "emergency_id": emergency.id,
        "severity_level": severity_level,
        "eta_seconds": int(best_eta_seconds),
        "eta_minutes": round(best_eta_seconds / 60.0, 1),
        "patient_type": patient_type,
        "ambulance_registration": best_amb.registration_number,
        "status": alert.status,
    })

    log.success(
        f"Dispatch #{dispatch.id} | sev {severity_level} | "
        f"amb {best_amb.registration_number} | {best_hosp.name} | "
        f"ETA {best_eta_seconds:.0f}s"
    )

    # Fire-and-forget user notifications (Telegram / email / SMS).
    # Anything that fails inside notifications is logged on the subscription
    # row, never bubbled — we never want a notification problem to block
    # dispatch persistence.
    try:
        await notify_dispatch_created(db, dispatch, plan=None)
    except Exception as exc:  # noqa: BLE001
        log.warning(f"notify_dispatch_created failed: {exc}")

    # Background ER briefing (Gemini ~3-5s; falls back to template). Runs in
    # its own AsyncSession so the request can return immediately.
    asyncio.create_task(_briefing_background(dispatch.id, alert.id, best_hosp.id))

    record_dispatch_outcome(severity_level, ok=True)

    return DispatchPlan(
        dispatch_id=dispatch.id,
        emergency_id=emergency.id,
        ambulance_id=best_amb.id,
        ambulance_registration=best_amb.registration_number,
        hospital_id=best_hosp.id,
        hospital_name=best_hosp.name,
        predicted_eta_seconds=int(best_eta_seconds),
        predicted_eta_minutes=round(best_eta_seconds / 60.0, 1),
        distance_km=round(best_distance_km, 2),
        road_distance_km=round(best_road_meters / 1000.0, 2) if best_road_meters else None,
        hospital_score=round(best_score, 4),
        severity_level=severity_level,
        severity_label=triage["severity_label"],
        severity_confidence=round(triage["confidence"], 4),
        inferred_patient_type=patient_type,
        routing_provider=best_route.provider if best_route else None,
        congestion=round(best_route.congestion, 3) if best_route else None,
        polyline=best_route.polyline if best_route else None,
        used_fallback=used_fallback,
        survival_prob_30d=outcome["survival_prob_30d"],
        equipment_score=best_match_detail["equipment_score"] if best_match_detail else None,
        missing_equipment=best_match_detail["missing_equipment"] if best_match_detail else None,
        skill_bonus=best_match_detail["skill_bonus"] if best_match_detail else None,
        predicted_er_wait_minutes=best_hospital_wait,
        air_dispatch_proposed=air_proposed,
        air_dispatch_reason=air_reason,
        air_eta_minutes=round(air_eta_seconds / 60.0, 1) if air_eta_seconds else None,
        air_distance_km=round(air_distance_km, 2) if air_distance_km else None,
    )
