"""Wearable telemetry ingestion + retrieval.

Endpoints
---------
    POST /telemetry/batch           ingest a batch of readings (patient auth)
    GET  /telemetry/me              recent readings (patient auth)
    GET  /telemetry/me/latest       most recent value of each metric
    GET  /telemetry/patient/{id}    clinical roles only — read another
                                    patient's history (paramedic / admin /
                                    hospital_staff)

The model accepts arrays so source apps (Apple Health export, Google Fit
sync, custom BLE bridge) can post a day's worth of data in one call. Every
metric is independently optional — a glucometer reading lands as one row
with everything but ``glucose_mg_dl`` left null.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.patient_profile import PatientProfile
from ..models.patient_telemetry import PatientTelemetry, TelemetrySource
from ..models.user import User
from .deps import require_role, require_user

router = APIRouter(prefix="/telemetry", tags=["telemetry"])


# ── Schemas ────────────────────────────────────────────────────────────────
_VALID_SOURCES = {s.value for s in TelemetrySource}


class TelemetryReadingIn(BaseModel):
    recorded_at: Optional[datetime] = None
    source: str = Field(default="manual")
    heart_rate: Optional[int] = Field(default=None, ge=20, le=250)
    spo2: Optional[float] = Field(default=None, ge=40, le=100)
    blood_pressure_systolic: Optional[int] = Field(default=None, ge=40, le=260)
    blood_pressure_diastolic: Optional[int] = Field(default=None, ge=20, le=180)
    respiratory_rate: Optional[int] = Field(default=None, ge=4, le=60)
    body_temperature_c: Optional[float] = Field(default=None, ge=25, le=45)
    glucose_mg_dl: Optional[int] = Field(default=None, ge=20, le=900)
    steps_since_midnight: Optional[int] = Field(default=None, ge=0, le=200_000)
    fall_detected: Optional[int] = Field(default=None, ge=0, le=1)
    raw_payload: Optional[Dict] = None


class TelemetryBatchIn(BaseModel):
    readings: List[TelemetryReadingIn] = Field(..., min_length=1, max_length=500)


class TelemetryReadingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    recorded_at: datetime
    source: str
    heart_rate: Optional[int] = None
    spo2: Optional[float] = None
    blood_pressure_systolic: Optional[int] = None
    blood_pressure_diastolic: Optional[int] = None
    respiratory_rate: Optional[int] = None
    body_temperature_c: Optional[float] = None
    glucose_mg_dl: Optional[int] = None
    steps_since_midnight: Optional[int] = None
    fall_detected: Optional[int] = None


class LatestVitals(BaseModel):
    """Most-recent value for each metric, with the timestamp it came from."""
    heart_rate: Optional[int] = None
    heart_rate_at: Optional[datetime] = None
    spo2: Optional[float] = None
    spo2_at: Optional[datetime] = None
    blood_pressure_systolic: Optional[int] = None
    blood_pressure_diastolic: Optional[int] = None
    blood_pressure_at: Optional[datetime] = None
    respiratory_rate: Optional[int] = None
    respiratory_rate_at: Optional[datetime] = None
    body_temperature_c: Optional[float] = None
    body_temperature_at: Optional[datetime] = None
    glucose_mg_dl: Optional[int] = None
    glucose_at: Optional[datetime] = None
    steps_since_midnight: Optional[int] = None
    fall_detected_at: Optional[datetime] = None


# ── Helpers ────────────────────────────────────────────────────────────────
async def _profile_for(db: AsyncSession, user: User) -> PatientProfile:
    profile = await db.scalar(
        select(PatientProfile).where(PatientProfile.user_id == user.id))
    if not profile:
        raise HTTPException(409,
            detail="Create your patient profile first (POST /patient/me).")
    return profile


async def _latest_vitals(db: AsyncSession, patient_id: int) -> LatestVitals:
    """Walk recent rows once, picking the first non-null per metric."""
    rows = list((await db.scalars(
        select(PatientTelemetry)
        .where(PatientTelemetry.patient_id == patient_id)
        .order_by(PatientTelemetry.recorded_at.desc())
        .limit(200)
    )).all())

    out = LatestVitals()
    for r in rows:
        if out.heart_rate is None and r.heart_rate is not None:
            out.heart_rate, out.heart_rate_at = r.heart_rate, r.recorded_at
        if out.spo2 is None and r.spo2 is not None:
            out.spo2, out.spo2_at = r.spo2, r.recorded_at
        if (out.blood_pressure_systolic is None
                and r.blood_pressure_systolic is not None):
            out.blood_pressure_systolic = r.blood_pressure_systolic
            out.blood_pressure_diastolic = r.blood_pressure_diastolic
            out.blood_pressure_at = r.recorded_at
        if out.respiratory_rate is None and r.respiratory_rate is not None:
            out.respiratory_rate, out.respiratory_rate_at = r.respiratory_rate, r.recorded_at
        if out.body_temperature_c is None and r.body_temperature_c is not None:
            out.body_temperature_c, out.body_temperature_at = r.body_temperature_c, r.recorded_at
        if out.glucose_mg_dl is None and r.glucose_mg_dl is not None:
            out.glucose_mg_dl, out.glucose_at = r.glucose_mg_dl, r.recorded_at
        if out.steps_since_midnight is None and r.steps_since_midnight is not None:
            out.steps_since_midnight = r.steps_since_midnight
        if out.fall_detected_at is None and r.fall_detected:
            out.fall_detected_at = r.recorded_at
    return out


# ── Patient routes ────────────────────────────────────────────────────────
@router.post("/batch", response_model=Dict[str, int], status_code=201)
async def ingest_batch(
    payload: TelemetryBatchIn,
    user: User = Depends(require_role("patient")),
    db: AsyncSession = Depends(get_db),
):
    profile = await _profile_for(db, user)
    inserted = 0
    for r in payload.readings:
        if r.source not in _VALID_SOURCES:
            raise HTTPException(400,
                detail=f"source must be one of {sorted(_VALID_SOURCES)}")
        # Skip rows that have no actual measurements — saves clutter.
        any_value = any([
            r.heart_rate, r.spo2, r.blood_pressure_systolic,
            r.blood_pressure_diastolic, r.respiratory_rate,
            r.body_temperature_c, r.glucose_mg_dl,
            r.steps_since_midnight, r.fall_detected,
        ])
        if not any_value:
            continue
        db.add(PatientTelemetry(
            patient_id=profile.id,
            recorded_at=r.recorded_at or datetime.utcnow(),
            source=r.source,
            heart_rate=r.heart_rate,
            spo2=r.spo2,
            blood_pressure_systolic=r.blood_pressure_systolic,
            blood_pressure_diastolic=r.blood_pressure_diastolic,
            respiratory_rate=r.respiratory_rate,
            body_temperature_c=r.body_temperature_c,
            glucose_mg_dl=r.glucose_mg_dl,
            steps_since_midnight=r.steps_since_midnight,
            fall_detected=r.fall_detected or 0,
            raw_payload=r.raw_payload,
        ))
        inserted += 1
    await db.commit()
    return {"inserted": inserted}


@router.get("/me", response_model=List[TelemetryReadingOut])
async def list_mine(
    limit: int = Query(50, ge=1, le=500),
    last_hours: Optional[int] = Query(None, ge=1, le=720),
    user: User = Depends(require_role("patient")),
    db: AsyncSession = Depends(get_db),
):
    profile = await _profile_for(db, user)
    stmt = (select(PatientTelemetry)
            .where(PatientTelemetry.patient_id == profile.id)
            .order_by(PatientTelemetry.recorded_at.desc())
            .limit(limit))
    if last_hours is not None:
        cutoff = datetime.utcnow() - timedelta(hours=last_hours)
        stmt = stmt.where(PatientTelemetry.recorded_at >= cutoff)
    rows = (await db.scalars(stmt)).all()
    return [TelemetryReadingOut.model_validate(r) for r in rows]


@router.get("/me/latest", response_model=LatestVitals)
async def latest_mine(
    user: User = Depends(require_role("patient")),
    db: AsyncSession = Depends(get_db),
):
    profile = await _profile_for(db, user)
    return await _latest_vitals(db, profile.id)


# ── Clinical-role lookup of another patient's telemetry ───────────────────
@router.get("/patient/{patient_id}/latest", response_model=LatestVitals)
async def latest_for(
    patient_id: int,
    user: User = Depends(require_role("paramedic", "hospital_staff", "admin")),
    db: AsyncSession = Depends(get_db),
):
    profile = await db.scalar(
        select(PatientProfile).where(PatientProfile.id == patient_id))
    if not profile:
        raise HTTPException(404, detail="Patient profile not found.")
    return await _latest_vitals(db, profile.id)
