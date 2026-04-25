"""Ambulance endpoints: list, get, update location, update status."""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.ambulance import Ambulance, AmbulanceStatus
from ..schemas.ambulance import (AmbulanceCreate, AmbulanceLocationUpdate,
                                 AmbulanceOut, AmbulanceStatusUpdate)
from ..sockets.sio import emit_ambulance_position, emit_ambulance_status

router = APIRouter(prefix="/ambulances", tags=["ambulances"])


@router.post("", response_model=AmbulanceOut, status_code=201)
def create_ambulance(payload: AmbulanceCreate, db: Session = Depends(get_db)):
    if db.query(Ambulance).filter(
        Ambulance.registration_number == payload.registration_number
    ).first():
        raise HTTPException(400, detail="Registration number already exists.")
    a = Ambulance(**payload.model_dump(),
                  current_lat=payload.home_station_lat,
                  current_lng=payload.home_station_lng)
    db.add(a)
    db.commit()
    db.refresh(a)
    return AmbulanceOut.model_validate(a)


@router.get("", response_model=List[AmbulanceOut])
def list_ambulances(
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(Ambulance).filter(Ambulance.is_active == True)
    if status:
        q = q.filter(Ambulance.status == status)
    return [AmbulanceOut.model_validate(a) for a in q.all()]


@router.get("/{amb_id}", response_model=AmbulanceOut)
def get_ambulance(amb_id: int, db: Session = Depends(get_db)):
    a = db.query(Ambulance).filter(Ambulance.id == amb_id).first()
    if not a:
        raise HTTPException(404, detail="Ambulance not found.")
    return AmbulanceOut.model_validate(a)


@router.patch("/{amb_id}/location", response_model=AmbulanceOut)
async def update_location(
    amb_id: int, payload: AmbulanceLocationUpdate,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    a = db.query(Ambulance).filter(Ambulance.id == amb_id).first()
    if not a:
        raise HTTPException(404, detail="Ambulance not found.")
    a.current_lat = payload.current_lat
    a.current_lng = payload.current_lng
    a.last_gps_update = datetime.utcnow()
    db.commit()
    db.refresh(a)
    background.add_task(emit_ambulance_position,
                        a.id, a.current_lat, a.current_lng, a.status)
    return AmbulanceOut.model_validate(a)


@router.patch("/{amb_id}/status", response_model=AmbulanceOut)
async def update_status(
    amb_id: int, payload: AmbulanceStatusUpdate,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    a = db.query(Ambulance).filter(Ambulance.id == amb_id).first()
    if not a:
        raise HTTPException(404, detail="Ambulance not found.")
    valid = [s.value for s in AmbulanceStatus]
    if payload.status not in valid:
        raise HTTPException(400, detail=f"Invalid status. Must be one of {valid}.")
    a.status = payload.status
    db.commit()
    db.refresh(a)
    background.add_task(emit_ambulance_status, a.id, a.status)
    return AmbulanceOut.model_validate(a)
