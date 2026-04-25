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
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from ..core.logging import log
from ..models.ambulance import Ambulance, AmbulanceStatus, AmbulanceType
from ..models.audit_log import AuditLog
from ..models.dispatch import Dispatch, DispatchStatus
from ..models.emergency import Emergency, EmergencyStatus
from ..models.hospital import Hospital
from ..schemas.dispatch import DispatchPlan
from .ai_service import get_ai_service
from .geo_service import estimate_zone_id, haversine_km


class DispatchError(Exception):
    """Raised when dispatch is impossible (no ambulances, no hospitals)."""


def dispatch_emergency(db: Session, emergency: Emergency,
                       user_id: Optional[int] = None) -> DispatchPlan:
    """Run the full dispatch pipeline for an emergency."""
    ai = get_ai_service()
    now = datetime.utcnow()
    used_fallback = False

    # ── 1. Triage ─────────────────────────────────────────
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
    patient_type = ai.infer_patient_type(emergency.symptoms or [],
                                         age=emergency.patient_age)
    emergency.inferred_patient_type = patient_type
    db.commit()

    # ── 2. Filter ambulances by required type ─────────────
    if severity_level <= 2:                    # Critical / Serious
        required = [AmbulanceType.ALS.value, AmbulanceType.ICU_MOBILE.value]
    elif severity_level == 3:                  # Moderate
        required = [AmbulanceType.BLS.value, AmbulanceType.ALS.value,
                    AmbulanceType.ICU_MOBILE.value]
    else:                                      # Minor / Non-emergency
        required = [AmbulanceType.BLS.value]

    candidates = (db.query(Ambulance)
                  .filter(Ambulance.status == AmbulanceStatus.AVAILABLE.value,
                          Ambulance.is_active == True,
                          Ambulance.ambulance_type.in_(required))
                  .all())

    if not candidates:
        # Relax type constraint as a fallback
        candidates = (db.query(Ambulance)
                      .filter(Ambulance.status == AmbulanceStatus.AVAILABLE.value,
                              Ambulance.is_active == True)
                      .all())
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

    type_to_int = {AmbulanceType.BLS.value: 0,
                   AmbulanceType.ALS.value: 1,
                   AmbulanceType.ICU_MOBILE.value: 2}

    for amb in candidates:
        if amb.current_lat is None or amb.current_lng is None:
            # ambulance hasn't reported GPS yet — assume it's at home depot
            cur_lat = amb.home_station_lat
            cur_lng = amb.home_station_lng
        else:
            cur_lat, cur_lng = amb.current_lat, amb.current_lng
        d_km = haversine_km(cur_lat, cur_lng,
                            emergency.location_lat, emergency.location_lng)
        eta = ai.predict_eta(
            distance_km=d_km, congestion=congestion,
            hour=now.hour, day_of_week=now.weekday(),
            weather=0,
            ambulance_type=type_to_int.get(amb.ambulance_type, 0),
            road_type=0,    # urban default
        )
        used_fallback = used_fallback or eta["used_fallback"]
        if eta["eta_seconds"] < best_eta_seconds:
            best_eta_seconds = eta["eta_seconds"]
            best_amb = amb
            best_distance_km = d_km

    # ── 4. Pick the best capable hospital ─────────────────
    candidate_hospitals = (db.query(Hospital)
                           .filter(Hospital.is_active == True)
                           .all())
    if not candidate_hospitals:
        raise DispatchError("No active hospitals in the system.")

    best_hosp = None
    best_score = -1.0
    for h in candidate_hospitals:
        d_h = haversine_km(emergency.location_lat, emergency.location_lng,
                            h.lat, h.lng)
        scored = ai.score_hospital(patient_type=patient_type,
                                   hospital=h, distance_km=d_h)
        used_fallback = used_fallback or scored["used_fallback"]
        if scored["score"] > best_score:
            best_score = scored["score"]
            best_hosp = h

    if best_hosp is None:
        raise DispatchError("Could not score any hospital.")

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
    )
    db.add(dispatch)

    best_amb.status = AmbulanceStatus.EN_ROUTE.value
    emergency.status = EmergencyStatus.DISPATCHED.value

    db.add(AuditLog(
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
    db.commit()
    db.refresh(dispatch)

    log.success(
        f"Dispatch #{dispatch.id} | sev {severity_level} | "
        f"amb {best_amb.registration_number} | {best_hosp.name} | "
        f"ETA {best_eta_seconds:.0f}s"
    )

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
        hospital_score=round(best_score, 4),
        severity_level=severity_level,
        severity_label=triage["severity_label"],
        severity_confidence=round(triage["confidence"], 4),
        inferred_patient_type=patient_type,
        used_fallback=used_fallback,
    )
