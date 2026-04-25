"""Hospital endpoints: list, get, update beds."""
from datetime import datetime
from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.hospital import Hospital
from ..schemas.hospital import HospitalBedsUpdate, HospitalCreate, HospitalOut
from ..sockets.sio import emit_hospital_beds_updated

router = APIRouter(prefix="/hospitals", tags=["hospitals"])


@router.post("", response_model=HospitalOut, status_code=201)
def create_hospital(payload: HospitalCreate, db: Session = Depends(get_db)):
    h = Hospital(**payload.model_dump())
    db.add(h)
    db.commit()
    db.refresh(h)
    return HospitalOut.model_validate(h)


@router.get("", response_model=List[HospitalOut])
def list_hospitals(db: Session = Depends(get_db)):
    return [HospitalOut.model_validate(h)
            for h in db.query(Hospital).filter(Hospital.is_active == True).all()]


@router.get("/{hid}", response_model=HospitalOut)
def get_hospital(hid: int, db: Session = Depends(get_db)):
    h = db.query(Hospital).filter(Hospital.id == hid).first()
    if not h:
        raise HTTPException(404, detail="Hospital not found.")
    return HospitalOut.model_validate(h)


@router.patch("/{hid}/beds", response_model=HospitalOut)
async def update_beds(hid: int, payload: HospitalBedsUpdate,
                      background: BackgroundTasks,
                      db: Session = Depends(get_db)):
    h = db.query(Hospital).filter(Hospital.id == hid).first()
    if not h:
        raise HTTPException(404, detail="Hospital not found.")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(h, k, v)
    h.last_updated = datetime.utcnow()
    db.commit()
    db.refresh(h)
    background.add_task(emit_hospital_beds_updated, {
        "hospital_id": h.id, "name": h.name,
        "available_beds_general": h.available_beds_general,
        "available_beds_icu": h.available_beds_icu,
        "available_beds_trauma": h.available_beds_trauma,
        "is_diversion": h.is_diversion,
        "er_wait_minutes": h.er_wait_minutes,
    })
    return HospitalOut.model_validate(h)
