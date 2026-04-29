"""Ambulance driver / paramedic endpoints.

Each paramedic User claims one Ambulance (via ``ambulances.assigned_user_id``).
The driver app reads its current dispatch through ``GET /driver/me``, advances
state through ``PATCH /driver/status``, and pushes GPS via
``PATCH /driver/location``.

State machine driven by these endpoints
---------------------------------------
    DISPATCHED ──► EN_ROUTE ──► ON_SCENE ──► TRANSPORTING ──► ARRIVED_HOSPITAL
                                                                   │
                                                                   ▼
                                                                COMPLETED
                                                                (ambulance
                                                                returns to
                                                                AVAILABLE)
"""
from datetime import datetime
from typing import Literal, Optional

from fastapi import (APIRouter, BackgroundTasks, Depends, HTTPException,
                     status as http_status)
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.ambulance import Ambulance, AmbulanceStatus
from ..models.dispatch import Dispatch, DispatchStatus
from ..models.emergency import Emergency, EmergencyStatus
from ..models.hospital import Hospital
from ..models.user import User
from ..schemas.ambulance import AmbulanceOut
from ..schemas.dispatch import DispatchOut
from ..schemas.emergency import EmergencyOut
from ..schemas.hospital import HospitalOut
from ..services.notifications import notify_dispatch_status
from ..services.routing_service import route as road_route
from ..sockets.sio import emit_ambulance_position, emit_ambulance_status
from .deps import require_role

router = APIRouter(prefix="/driver", tags=["driver"])


# Permitted forward transitions for the driver's "next" button. Anything
# else returns 409 — backend is the source of truth, frontend just renders.
_NEXT: dict[str, str] = {
    DispatchStatus.DISPATCHED.value:       DispatchStatus.EN_ROUTE.value,
    DispatchStatus.EN_ROUTE.value:         DispatchStatus.ON_SCENE.value,
    DispatchStatus.ON_SCENE.value:         DispatchStatus.TRANSPORTING.value,
    DispatchStatus.TRANSPORTING.value:     DispatchStatus.ARRIVED_HOSPITAL.value,
    DispatchStatus.ARRIVED_HOSPITAL.value: DispatchStatus.COMPLETED.value,
}

_DISPATCH_TO_AMB: dict[str, str] = {
    DispatchStatus.DISPATCHED.value:       AmbulanceStatus.EN_ROUTE.value,
    DispatchStatus.EN_ROUTE.value:         AmbulanceStatus.EN_ROUTE.value,
    DispatchStatus.ON_SCENE.value:         AmbulanceStatus.ON_SCENE.value,
    DispatchStatus.TRANSPORTING.value:     AmbulanceStatus.TRANSPORTING.value,
    DispatchStatus.ARRIVED_HOSPITAL.value: AmbulanceStatus.RETURNING.value,
    DispatchStatus.COMPLETED.value:        AmbulanceStatus.AVAILABLE.value,
}


# ── Request / response schemas ─────────────────────────────────────────────
class LocationIn(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)


class StatusAdvanceIn(BaseModel):
    """Optional explicit target — if omitted the engine advances by one step."""
    target: Optional[str] = None


class DriverAssignment(BaseModel):
    model_config = ConfigDict(from_attributes=False)
    ambulance: AmbulanceOut
    active_dispatch: Optional[DispatchOut] = None
    emergency: Optional[EmergencyOut] = None
    hospital: Optional[HospitalOut] = None
    leg_to_scene: Optional[dict] = None
    leg_to_hospital: Optional[dict] = None


# ── Helpers ────────────────────────────────────────────────────────────────
async def _my_ambulance(db: AsyncSession, user: User) -> Ambulance:
    amb = await db.scalar(
        select(Ambulance).where(Ambulance.assigned_user_id == user.id)
    )
    if not amb:
        raise HTTPException(http_status.HTTP_409_CONFLICT,
                            detail="No ambulance claimed yet — POST /driver/claim/{amb_id}.")
    return amb


async def _active_dispatch_for(db: AsyncSession, ambulance_id: int) -> Optional[Dispatch]:
    open_states = [
        DispatchStatus.DISPATCHED.value,
        DispatchStatus.EN_ROUTE.value,
        DispatchStatus.ON_SCENE.value,
        DispatchStatus.TRANSPORTING.value,
        DispatchStatus.ARRIVED_HOSPITAL.value,
    ]
    return await db.scalar(
        select(Dispatch)
        .where(Dispatch.ambulance_id == ambulance_id)
        .where(Dispatch.status.in_(open_states))
        .order_by(Dispatch.dispatched_at.desc())
    )


# ── Claim / release ────────────────────────────────────────────────────────
@router.post("/claim/{amb_id}", response_model=AmbulanceOut)
async def claim(
    amb_id: int,
    user: User = Depends(require_role("paramedic", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """Take control of an ambulance. One ambulance per paramedic; if you
    already have one this re-assigns to the new id."""
    target = await db.scalar(select(Ambulance).where(Ambulance.id == amb_id))
    if not target:
        raise HTTPException(404, detail="Ambulance not found.")
    if target.assigned_user_id and target.assigned_user_id != user.id:
        raise HTTPException(409,
            detail="That ambulance is already claimed by another paramedic.")

    # Release any previously claimed unit so the unique constraint holds.
    prev = await db.scalar(
        select(Ambulance).where(Ambulance.assigned_user_id == user.id))
    if prev and prev.id != amb_id:
        prev.assigned_user_id = None

    target.assigned_user_id = user.id
    if not target.paramedic_name:
        target.paramedic_name = user.full_name or user.username
    await db.commit()
    await db.refresh(target)
    return AmbulanceOut.model_validate(target)


@router.post("/release", response_model=AmbulanceOut)
async def release(
    user: User = Depends(require_role("paramedic", "admin")),
    db: AsyncSession = Depends(get_db),
):
    amb = await _my_ambulance(db, user)
    amb.assigned_user_id = None
    await db.commit()
    await db.refresh(amb)
    return AmbulanceOut.model_validate(amb)


# ── Read current assignment ───────────────────────────────────────────────
@router.get("/me", response_model=DriverAssignment)
async def my_assignment(
    user: User = Depends(require_role("paramedic", "admin")),
    db: AsyncSession = Depends(get_db),
):
    amb = await _my_ambulance(db, user)
    dispatch = await _active_dispatch_for(db, amb.id)

    emergency: Optional[Emergency] = None
    hospital: Optional[Hospital] = None
    leg_to_scene = None
    leg_to_hospital = None

    if dispatch:
        emergency = await db.scalar(
            select(Emergency).where(Emergency.id == dispatch.emergency_id))
        hospital = await db.scalar(
            select(Hospital).where(Hospital.id == dispatch.hospital_id))

        # Pre-compute the two legs the driver actually drives.
        if amb.current_lat and amb.current_lng and emergency:
            r = await road_route(amb.current_lat, amb.current_lng,
                                 emergency.location_lat, emergency.location_lng)
            leg_to_scene = {
                "minutes": round(r.seconds / 60.0, 1),
                "km": round(r.meters / 1000.0, 2),
                "polyline": r.polyline,
                "provider": r.provider,
                "used_fallback": r.used_fallback,
            }
        if emergency and hospital:
            r2 = await road_route(emergency.location_lat, emergency.location_lng,
                                  hospital.lat, hospital.lng)
            leg_to_hospital = {
                "minutes": round(r2.seconds / 60.0, 1),
                "km": round(r2.meters / 1000.0, 2),
                "polyline": r2.polyline,
                "provider": r2.provider,
                "used_fallback": r2.used_fallback,
            }

    return DriverAssignment(
        ambulance=AmbulanceOut.model_validate(amb),
        active_dispatch=DispatchOut.model_validate(dispatch) if dispatch else None,
        emergency=EmergencyOut.model_validate(emergency) if emergency else None,
        hospital=HospitalOut.model_validate(hospital) if hospital else None,
        leg_to_scene=leg_to_scene,
        leg_to_hospital=leg_to_hospital,
    )


# ── Status advance ─────────────────────────────────────────────────────────
@router.patch("/status", response_model=DispatchOut)
async def advance_status(
    payload: StatusAdvanceIn,
    background: BackgroundTasks,
    user: User = Depends(require_role("paramedic", "admin")),
    db: AsyncSession = Depends(get_db),
):
    amb = await _my_ambulance(db, user)
    dispatch = await _active_dispatch_for(db, amb.id)
    if not dispatch:
        raise HTTPException(404, detail="No active dispatch on your ambulance.")

    target = payload.target or _NEXT.get(dispatch.status)
    if target is None:
        raise HTTPException(409,
            detail=f"Dispatch is in terminal state ({dispatch.status}).")
    if target not in _DISPATCH_TO_AMB:
        raise HTTPException(400, detail=f"Unknown target status: {target}.")
    expected = _NEXT.get(dispatch.status)
    if payload.target and payload.target != expected:
        raise HTTPException(409,
            detail=f"Cannot jump from {dispatch.status} to {payload.target}; "
                   f"next allowed is {expected}.")

    now = datetime.utcnow()
    dispatch.status = target
    if target == DispatchStatus.ON_SCENE.value:
        dispatch.arrived_on_scene_at = now
        dispatch.actual_response_time_seconds = int(
            (now - dispatch.dispatched_at).total_seconds())
    elif target == DispatchStatus.TRANSPORTING.value:
        dispatch.departed_scene_at = now
    elif target == DispatchStatus.ARRIVED_HOSPITAL.value:
        dispatch.arrived_hospital_at = now
        # Emergency itself becomes RESOLVED at hospital arrival.
        emergency = await db.scalar(
            select(Emergency).where(Emergency.id == dispatch.emergency_id))
        if emergency:
            emergency.status = EmergencyStatus.RESOLVED.value
            emergency.resolved_at = now

    amb.status = _DISPATCH_TO_AMB[target]
    await db.commit()
    await db.refresh(dispatch)

    background.add_task(emit_ambulance_status, amb.id, amb.status)
    # Patient ping (best-effort; never blocks the response).
    try:
        await notify_dispatch_status(db, dispatch, target)
    except Exception:  # noqa: BLE001
        pass
    return DispatchOut.model_validate(dispatch)


# ── GPS push ───────────────────────────────────────────────────────────────
@router.patch("/location", response_model=AmbulanceOut)
async def push_location(
    payload: LocationIn,
    background: BackgroundTasks,
    user: User = Depends(require_role("paramedic", "admin")),
    db: AsyncSession = Depends(get_db),
):
    amb = await _my_ambulance(db, user)
    amb.current_lat = payload.lat
    amb.current_lng = payload.lng
    amb.last_gps_update = datetime.utcnow()
    await db.commit()
    await db.refresh(amb)
    background.add_task(emit_ambulance_position,
                        amb.id, amb.current_lat, amb.current_lng, amb.status)
    return AmbulanceOut.model_validate(amb)
