"""Hospital-staff portal — pre-arrival alert feed, accept/divert, bed editor.

Hospital staff users belong to one hospital (``users.assigned_hospital_id``).
The portal is scoped to that hospital — every endpoint here only operates on
the staff member's own facility.
"""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.dispatch import Dispatch
from ..models.emergency import Emergency
from ..models.hospital import Hospital
from ..models.hospital_alert import AlertStatus, HospitalAlert
from ..models.user import User
from ..schemas.emergency import EmergencyOut
from ..schemas.hospital import HospitalBedsUpdate, HospitalOut
from ..sockets.sio import (emit_hospital_alert_status,
                           emit_hospital_beds_updated)
from .deps import require_role

router = APIRouter(prefix="/hospital", tags=["hospital_portal"])


# ── Schemas ────────────────────────────────────────────────────────────────
class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    hospital_id: int
    dispatch_id: int
    emergency_id: int
    severity_level: Optional[int] = None
    eta_seconds: Optional[int] = None
    patient_type: Optional[str] = None
    briefing: Optional[str] = None
    status: str
    acknowledged_by: Optional[int] = None
    acknowledged_at: Optional[datetime] = None
    created_at: datetime


class AlertWithContext(AlertOut):
    """An alert plus its emergency snapshot — what the portal renders."""
    emergency: Optional[EmergencyOut] = None
    ambulance_registration: Optional[str] = None
    eta_minutes: Optional[float] = None


class HospitalPortalSnapshot(BaseModel):
    hospital: HospitalOut
    alerts: List[AlertWithContext]
    open_alerts: int
    on_diversion: bool


# ── Helpers ────────────────────────────────────────────────────────────────
async def _my_hospital(db: AsyncSession, user: User) -> Hospital:
    if user.role == "admin":
        # Admin can pass through but needs an assigned_hospital_id to use
        # /hospital/me-style endpoints. Hospital staff need it always.
        if not user.assigned_hospital_id:
            raise HTTPException(409, detail="Admin must claim a hospital first.")
    if not user.assigned_hospital_id:
        raise HTTPException(409,
            detail="No hospital claimed yet — POST /hospital/claim/{hospital_id}.")
    h = await db.scalar(
        select(Hospital).where(Hospital.id == user.assigned_hospital_id))
    if not h:
        raise HTTPException(410, detail="Assigned hospital missing — re-claim.")
    return h


async def _decorate(db: AsyncSession,
                    alert: HospitalAlert) -> AlertWithContext:
    e = await db.scalar(
        select(Emergency).where(Emergency.id == alert.emergency_id))
    d = await db.scalar(
        select(Dispatch).where(Dispatch.id == alert.dispatch_id))
    amb_reg = None
    if d:
        from ..models.ambulance import Ambulance  # local to avoid circular
        a = await db.scalar(select(Ambulance).where(Ambulance.id == d.ambulance_id))
        if a:
            amb_reg = a.registration_number
    return AlertWithContext(
        **AlertOut.model_validate(alert).model_dump(),
        emergency=EmergencyOut.model_validate(e) if e else None,
        ambulance_registration=amb_reg,
        eta_minutes=round(alert.eta_seconds / 60.0, 1) if alert.eta_seconds else None,
    )


# ── Claim / release hospital ──────────────────────────────────────────────
@router.post("/claim/{hospital_id}", response_model=HospitalOut)
async def claim(
    hospital_id: int,
    user: User = Depends(require_role("hospital_staff", "admin")),
    db: AsyncSession = Depends(get_db),
):
    h = await db.scalar(select(Hospital).where(Hospital.id == hospital_id))
    if not h:
        raise HTTPException(404, detail="Hospital not found.")
    user.assigned_hospital_id = h.id
    await db.commit()
    return HospitalOut.model_validate(h)


@router.post("/release", status_code=204)
async def release(
    user: User = Depends(require_role("hospital_staff", "admin")),
    db: AsyncSession = Depends(get_db),
):
    user.assigned_hospital_id = None
    await db.commit()


# ── Snapshot + alert feed ──────────────────────────────────────────────────
@router.get("/me", response_model=HospitalPortalSnapshot)
async def my_snapshot(
    user: User = Depends(require_role("hospital_staff", "admin")),
    db: AsyncSession = Depends(get_db),
):
    h = await _my_hospital(db, user)
    rows = (await db.scalars(
        select(HospitalAlert)
        .where(HospitalAlert.hospital_id == h.id)
        .order_by(HospitalAlert.created_at.desc())
        .limit(50)
    )).all()
    decorated = [await _decorate(db, a) for a in rows]
    open_count = sum(1 for a in decorated if a.status in
                     (AlertStatus.PENDING.value, AlertStatus.ACKNOWLEDGED.value))
    return HospitalPortalSnapshot(
        hospital=HospitalOut.model_validate(h),
        alerts=decorated,
        open_alerts=open_count,
        on_diversion=h.is_diversion,
    )


@router.get("/alerts", response_model=List[AlertWithContext])
async def list_alerts(
    only_open: bool = Query(True),
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(require_role("hospital_staff", "admin")),
    db: AsyncSession = Depends(get_db),
):
    h = await _my_hospital(db, user)
    stmt = (select(HospitalAlert)
            .where(HospitalAlert.hospital_id == h.id)
            .order_by(HospitalAlert.created_at.desc())
            .limit(limit))
    if only_open:
        stmt = stmt.where(HospitalAlert.status.in_(
            [AlertStatus.PENDING.value, AlertStatus.ACKNOWLEDGED.value]))
    rows = (await db.scalars(stmt)).all()
    return [await _decorate(db, a) for a in rows]


# ── Alert state transitions ────────────────────────────────────────────────
class AlertActionResponse(AlertWithContext):
    pass


async def _transition(db: AsyncSession, alert_id: int, hospital: Hospital,
                      user: User, target: str) -> HospitalAlert:
    alert = await db.scalar(
        select(HospitalAlert).where(HospitalAlert.id == alert_id))
    if not alert or alert.hospital_id != hospital.id:
        raise HTTPException(404, detail="Alert not found at your hospital.")
    alert.status = target
    if target in (AlertStatus.ACKNOWLEDGED.value, AlertStatus.ACCEPTED.value,
                  AlertStatus.DIVERTED.value) and not alert.acknowledged_at:
        alert.acknowledged_by = user.id
        alert.acknowledged_at = datetime.utcnow()
    return alert


@router.post("/alerts/{alert_id}/acknowledge", response_model=AlertActionResponse)
async def acknowledge(
    alert_id: int,
    background: BackgroundTasks,
    user: User = Depends(require_role("hospital_staff", "admin")),
    db: AsyncSession = Depends(get_db),
):
    h = await _my_hospital(db, user)
    alert = await _transition(db, alert_id, h, user,
                              AlertStatus.ACKNOWLEDGED.value)
    await db.commit(); await db.refresh(alert)
    background.add_task(emit_hospital_alert_status,
                        {"alert_id": alert.id, "status": alert.status,
                         "hospital_id": h.id})
    return await _decorate(db, alert)


@router.post("/alerts/{alert_id}/accept", response_model=AlertActionResponse)
async def accept(
    alert_id: int,
    background: BackgroundTasks,
    user: User = Depends(require_role("hospital_staff", "admin")),
    db: AsyncSession = Depends(get_db),
):
    h = await _my_hospital(db, user)
    alert = await _transition(db, alert_id, h, user, AlertStatus.ACCEPTED.value)
    await db.commit(); await db.refresh(alert)
    background.add_task(emit_hospital_alert_status,
                        {"alert_id": alert.id, "status": alert.status,
                         "hospital_id": h.id})
    return await _decorate(db, alert)


class DivertIn(BaseModel):
    set_hospital_diversion: bool = Field(default=True,
        description="Also flip the hospital itself to is_diversion=True.")


@router.post("/alerts/{alert_id}/divert", response_model=AlertActionResponse)
async def divert(
    alert_id: int,
    payload: DivertIn,
    background: BackgroundTasks,
    user: User = Depends(require_role("hospital_staff", "admin")),
    db: AsyncSession = Depends(get_db),
):
    h = await _my_hospital(db, user)
    alert = await _transition(db, alert_id, h, user, AlertStatus.DIVERTED.value)
    if payload.set_hospital_diversion:
        h.is_diversion = True
        h.last_updated = datetime.utcnow()
    await db.commit(); await db.refresh(alert)
    background.add_task(emit_hospital_alert_status,
                        {"alert_id": alert.id, "status": alert.status,
                         "hospital_id": h.id, "now_on_diversion": h.is_diversion})
    return await _decorate(db, alert)


# ── Bed editor (scoped to my hospital) ─────────────────────────────────────
@router.patch("/me/beds", response_model=HospitalOut)
async def update_my_beds(
    payload: HospitalBedsUpdate,
    background: BackgroundTasks,
    user: User = Depends(require_role("hospital_staff", "admin")),
    db: AsyncSession = Depends(get_db),
):
    h = await _my_hospital(db, user)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(h, k, v)
    h.last_updated = datetime.utcnow()
    await db.commit(); await db.refresh(h)
    background.add_task(emit_hospital_beds_updated, {
        "hospital_id": h.id, "name": h.name,
        "available_beds_general": h.available_beds_general,
        "available_beds_icu": h.available_beds_icu,
        "available_beds_trauma": h.available_beds_trauma,
        "is_diversion": h.is_diversion,
        "er_wait_minutes": h.er_wait_minutes,
    })
    return HospitalOut.model_validate(h)
