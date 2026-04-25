"""Dispatch listing endpoints."""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.dispatch import Dispatch
from ..schemas.dispatch import DispatchOut

router = APIRouter(prefix="/dispatches", tags=["dispatches"])


@router.get("", response_model=List[DispatchOut])
def list_dispatches(
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    q = db.query(Dispatch).order_by(Dispatch.dispatched_at.desc())
    if status:
        q = q.filter(Dispatch.status == status)
    return [DispatchOut.model_validate(d) for d in q.limit(limit).all()]


@router.get("/active", response_model=List[DispatchOut])
def active_dispatches(db: Session = Depends(get_db)):
    """Dispatches that aren't done yet — what the dispatcher actively manages."""
    open_statuses = ["dispatched", "en_route", "on_scene", "transporting"]
    return [DispatchOut.model_validate(d)
            for d in db.query(Dispatch)
            .filter(Dispatch.status.in_(open_statuses))
            .order_by(Dispatch.dispatched_at.desc()).all()]


@router.get("/{did}", response_model=DispatchOut)
def get_dispatch(did: int, db: Session = Depends(get_db)):
    d = db.query(Dispatch).filter(Dispatch.id == did).first()
    if not d:
        raise HTTPException(404, detail="Dispatch not found.")
    return DispatchOut.model_validate(d)
