"""Family-tracking endpoints.

Mounted at /track-api so the SPA's public /track/:token URL never collides
with backend routes. Three surfaces:

  - Authenticated patient/dispatcher/admin creates / lists / revokes links
  - Public, token-only endpoint returns a read-only NoK snapshot
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.ambulance import Ambulance
from ..models.dispatch import Dispatch
from ..models.emergency import Emergency
from ..models.family_link import FamilyLink
from ..models.hospital import Hospital
from ..models.patient_profile import PatientProfile
from ..models.user import User
from ..services.tracking_link import (DEFAULT_TTL_HOURS, create_link,
                                      verify_token)
from .deps import require_user

router = APIRouter(prefix="/track-api", tags=["tracking"])


# ── Schemas ────────────────────────────────────────────────────────────────
class CreateLinkIn(BaseModel):
    emergency_id: int
    nok_name: Optional[str] = None
    nok_phone: Optional[str] = None
    nok_relation: Optional[str] = None
    notes: Optional[str] = None
    ttl_hours: int = Field(default=DEFAULT_TTL_HOURS, ge=1, le=24)


class CreatedLink(BaseModel):
    id: int
    emergency_id: int
    token: str
    relative_path: str = Field(
        ..., description="Front-end SPA path; combine with origin to share.")
    expires_at: datetime


class FamilyLinkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    emergency_id: int
    dispatch_id: Optional[int] = None
    nok_name: Optional[str] = None
    nok_phone: Optional[str] = None
    nok_relation: Optional[str] = None
    expires_at: datetime
    revoked_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None
    view_count: int = 0
    created_at: datetime


class TrackSnapshot(BaseModel):
    """Public NoK view. Strictly read-only and minimal PHI."""
    emergency_id: int
    patient_first_name: Optional[str] = None
    severity_level: Optional[int] = None

    ambulance_registration: Optional[str] = None
    ambulance_lat: Optional[float] = None
    ambulance_lng: Optional[float] = None
    ambulance_status: Optional[str] = None
    last_gps_update: Optional[datetime] = None

    incident_lat: Optional[float] = None
    incident_lng: Optional[float] = None

    hospital_name: Optional[str] = None
    hospital_lat: Optional[float] = None
    hospital_lng: Optional[float] = None

    dispatch_status: Optional[str] = None
    eta_minutes: Optional[float] = None
    expires_at: datetime


# ── Helpers ────────────────────────────────────────────────────────────────
async def _emergency_belongs_to_patient(
    db: AsyncSession, emergency: Emergency, user: User,
) -> bool:
    profile = await db.scalar(
        select(PatientProfile).where(PatientProfile.user_id == user.id))
    return bool(profile and emergency.phone == profile.phone)


# ── Authenticated: create / list / revoke ─────────────────────────────────
@router.post("/links", response_model=CreatedLink, status_code=201)
async def create(
    payload: CreateLinkIn,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    em = await db.scalar(
        select(Emergency).where(Emergency.id == payload.emergency_id))
    if not em:
        raise HTTPException(404, detail="Emergency not found.")
    if user.role == "patient" and not await _emergency_belongs_to_patient(db, em, user):
        raise HTTPException(403, detail="Not your emergency.")

    dispatch = await db.scalar(
        select(Dispatch).where(Dispatch.emergency_id == payload.emergency_id)
        .order_by(Dispatch.dispatched_at.desc())
    )

    row, token = await create_link(
        db, payload.emergency_id,
        dispatch_id=dispatch.id if dispatch else None,
        nok_name=payload.nok_name, nok_phone=payload.nok_phone,
        nok_relation=payload.nok_relation, notes=payload.notes,
        ttl_hours=payload.ttl_hours,
    )
    return CreatedLink(
        id=row.id, emergency_id=row.emergency_id, token=token,
        relative_path=f"/track/{token}", expires_at=row.expires_at,
    )


@router.get("/links", response_model=List[FamilyLinkOut])
async def list_mine(
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    if user.role == "patient":
        profile = await db.scalar(
            select(PatientProfile).where(PatientProfile.user_id == user.id))
        if not profile:
            return []
        ems = list((await db.scalars(
            select(Emergency.id).where(Emergency.phone == profile.phone)
        )).all())
        if not ems:
            return []
        rows = (await db.scalars(
            select(FamilyLink).where(FamilyLink.emergency_id.in_(ems))
            .order_by(FamilyLink.created_at.desc())
        )).all()
    else:
        rows = (await db.scalars(
            select(FamilyLink).order_by(FamilyLink.created_at.desc()).limit(100)
        )).all()
    return [FamilyLinkOut.model_validate(r) for r in rows]


@router.post("/links/{link_id}/revoke", status_code=204)
async def revoke(
    link_id: int,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    row = await db.scalar(select(FamilyLink).where(FamilyLink.id == link_id))
    if not row:
        raise HTTPException(404, detail="Link not found.")
    if user.role == "patient":
        em = await db.scalar(
            select(Emergency).where(Emergency.id == row.emergency_id))
        if not em or not await _emergency_belongs_to_patient(db, em, user):
            raise HTTPException(403, detail="Not your link.")
    if row.revoked_at:
        return
    row.revoked_at = datetime.utcnow()
    await db.commit()


# ── Public: token-only snapshot ───────────────────────────────────────────
@router.get("/{token}", response_model=TrackSnapshot)
async def public_snapshot(token: str, db: AsyncSession = Depends(get_db)):
    try:
        link = await verify_token(db, token)
    except ValueError as exc:
        # 410 Gone fits expired/revoked semantically; 410 also for unknowns
        # so we don't leak which condition tripped.
        raise HTTPException(410, detail=str(exc))

    em = await db.scalar(
        select(Emergency).where(Emergency.id == link.emergency_id))
    dispatch = (await db.scalar(
        select(Dispatch).where(Dispatch.id == link.dispatch_id))
        if link.dispatch_id else None)
    amb = (await db.scalar(
        select(Ambulance).where(Ambulance.id == dispatch.ambulance_id))
        if dispatch else None)
    hosp = (await db.scalar(
        select(Hospital).where(Hospital.id == dispatch.hospital_id))
        if dispatch else None)

    # Track view (best-effort; never block on it).
    link.view_count = (link.view_count or 0) + 1
    link.last_seen_at = datetime.utcnow()
    try:
        await db.commit()
    except Exception:  # noqa: BLE001
        pass

    first_name = None
    if em and em.patient_name:
        first_name = em.patient_name.strip().split()[0]

    eta_minutes = None
    if dispatch and dispatch.predicted_eta_seconds:
        eta_minutes = round(dispatch.predicted_eta_seconds / 60.0, 1)

    return TrackSnapshot(
        emergency_id=link.emergency_id,
        patient_first_name=first_name,
        severity_level=em.predicted_severity if em else None,
        ambulance_registration=amb.registration_number if amb else None,
        ambulance_lat=amb.current_lat if amb else None,
        ambulance_lng=amb.current_lng if amb else None,
        ambulance_status=amb.status if amb else None,
        last_gps_update=amb.last_gps_update if amb else None,
        incident_lat=em.location_lat if em else None,
        incident_lng=em.location_lng if em else None,
        hospital_name=hosp.name if hosp else None,
        hospital_lat=hosp.lat if hosp else None,
        hospital_lng=hosp.lng if hosp else None,
        dispatch_status=dispatch.status if dispatch else None,
        eta_minutes=eta_minutes,
        expires_at=link.expires_at,
    )
