"""Ambulance endpoints: list, get, update location, update status."""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.ambulance import Ambulance, AmbulanceStatus
from ..schemas.ambulance import (AmbulanceCreate, AmbulanceLocationUpdate,
                                 AmbulanceOut, AmbulanceStatusUpdate)
from ..sockets.sio import emit_ambulance_position, emit_ambulance_status

router = APIRouter(prefix="/ambulances", tags=["ambulances"])


@router.post("", response_model=AmbulanceOut, status_code=201)
async def create_ambulance(payload: AmbulanceCreate,
                           db: AsyncSession = Depends(get_db)):
    existing = await db.scalar(select(Ambulance).where(
        Ambulance.registration_number == payload.registration_number))
    if existing:
        raise HTTPException(400, detail="Registration number already exists.")
    a = Ambulance(**payload.model_dump(),
                  current_lat=payload.home_station_lat,
                  current_lng=payload.home_station_lng)
    db.add(a)
    await db.commit()
    await db.refresh(a)
    return AmbulanceOut.model_validate(a)


@router.get("", response_model=List[AmbulanceOut])
async def list_ambulances(
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Ambulance).where(Ambulance.is_active == True)
    if status:
        stmt = stmt.where(Ambulance.status == status)
    rows = (await db.scalars(stmt)).all()
    return [AmbulanceOut.model_validate(a) for a in rows]


@router.get("/{amb_id}", response_model=AmbulanceOut)
async def get_ambulance(amb_id: int, db: AsyncSession = Depends(get_db)):
    a = await db.scalar(select(Ambulance).where(Ambulance.id == amb_id))
    if not a:
        raise HTTPException(404, detail="Ambulance not found.")
    return AmbulanceOut.model_validate(a)


@router.patch("/{amb_id}/location", response_model=AmbulanceOut)
async def update_location(
    amb_id: int, payload: AmbulanceLocationUpdate,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    a = await db.scalar(select(Ambulance).where(Ambulance.id == amb_id))
    if not a:
        raise HTTPException(404, detail="Ambulance not found.")
    a.current_lat = payload.current_lat
    a.current_lng = payload.current_lng
    a.last_gps_update = datetime.utcnow()
    await db.commit()
    await db.refresh(a)
    background.add_task(emit_ambulance_position,
                        a.id, a.current_lat, a.current_lng, a.status)
    return AmbulanceOut.model_validate(a)


@router.patch("/{amb_id}/status", response_model=AmbulanceOut)
async def update_status(
    amb_id: int, payload: AmbulanceStatusUpdate,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    a = await db.scalar(select(Ambulance).where(Ambulance.id == amb_id))
    if not a:
        raise HTTPException(404, detail="Ambulance not found.")
    valid = [s.value for s in AmbulanceStatus]
    if payload.status not in valid:
        raise HTTPException(400, detail=f"Invalid status. Must be one of {valid}.")
    a.status = payload.status
    await db.commit()
    await db.refresh(a)
    background.add_task(emit_ambulance_status, a.id, a.status)
    return AmbulanceOut.model_validate(a)
