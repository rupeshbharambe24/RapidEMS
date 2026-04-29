"""Emergency endpoints: create, list, fetch, trigger dispatch, update status."""
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.emergency import Emergency, EmergencyStatus
from ..schemas.dispatch import DispatchPlan
from ..schemas.emergency import EmergencyCreate, EmergencyOut, EmergencyUpdate
from ..services.dispatch_engine import DispatchError, dispatch_emergency
from ..sockets.sio import emit_emergency_created, emit_emergency_dispatched
from .deps import get_current_user

router = APIRouter(prefix="/emergencies", tags=["emergencies"])


@router.post("", response_model=EmergencyOut, status_code=201)
async def create_emergency(
    payload: EmergencyCreate,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    emergency = Emergency(**payload.model_dump())
    db.add(emergency)
    db.commit()
    db.refresh(emergency)

    # Push real-time event
    background.add_task(emit_emergency_created, {
        "id": emergency.id,
        "lat": emergency.location_lat,
        "lng": emergency.location_lng,
        "status": emergency.status,
        "address": emergency.location_address,
        "chief_complaint": emergency.chief_complaint,
        "symptoms": emergency.symptoms,
    })
    return EmergencyOut.model_validate(emergency)


@router.get("", response_model=List[EmergencyOut])
def list_emergencies(
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    q = db.query(Emergency).order_by(Emergency.created_at.desc())
    if status:
        q = q.filter(Emergency.status == status)
    return [EmergencyOut.model_validate(e) for e in q.limit(limit).all()]


@router.get("/{emergency_id}", response_model=EmergencyOut)
def get_emergency(emergency_id: int, db: Session = Depends(get_db)):
    e = db.query(Emergency).filter(Emergency.id == emergency_id).first()
    if not e:
        raise HTTPException(404, detail="Emergency not found.")
    return EmergencyOut.model_validate(e)


@router.post("/{emergency_id}/dispatch", response_model=DispatchPlan)
async def trigger_dispatch(
    emergency_id: int,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    e = db.query(Emergency).filter(Emergency.id == emergency_id).first()
    if not e:
        raise HTTPException(404, detail="Emergency not found.")
    if e.status != EmergencyStatus.PENDING.value:
        raise HTTPException(409,
                            detail=f"Emergency already {e.status}; cannot dispatch.")
    try:
        plan = await dispatch_emergency(db, e, user_id=user.id if user else None)
    except DispatchError as exc:
        raise HTTPException(409, detail=str(exc))

    background.add_task(emit_emergency_dispatched, plan.model_dump())
    return plan


@router.patch("/{emergency_id}", response_model=EmergencyOut)
def update_emergency(emergency_id: int, payload: EmergencyUpdate,
                     db: Session = Depends(get_db)):
    e = db.query(Emergency).filter(Emergency.id == emergency_id).first()
    if not e:
        raise HTTPException(404, detail="Emergency not found.")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(e, k, v)
    db.commit()
    db.refresh(e)
    return EmergencyOut.model_validate(e)
