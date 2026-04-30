"""Dispatch listing + multi-emergency optimisation endpoints."""
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.dispatch import Dispatch
from ..models.user import User
from ..schemas.dispatch import (DispatchOut, OptimizeProposal,
                                OptimizeResponse)
from ..services.multi_dispatch import optimize as multi_optimize
from ..services.staging import apply_staging, compute_staging
from ..sockets.sio import emit_emergency_dispatched
from .deps import get_current_user, require_role

router = APIRouter(prefix="/dispatches", tags=["dispatches"])


@router.get("", response_model=List[DispatchOut])
async def list_dispatches(
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Dispatch).order_by(Dispatch.dispatched_at.desc())
    if status:
        stmt = stmt.where(Dispatch.status == status)
    rows = (await db.scalars(stmt.limit(limit))).all()
    return [DispatchOut.model_validate(d) for d in rows]


@router.get("/active", response_model=List[DispatchOut])
async def active_dispatches(db: AsyncSession = Depends(get_db)):
    """Dispatches that aren't done yet — what the dispatcher actively manages."""
    open_statuses = ["dispatched", "en_route", "on_scene", "transporting"]
    rows = (await db.scalars(
        select(Dispatch)
        .where(Dispatch.status.in_(open_statuses))
        .order_by(Dispatch.dispatched_at.desc())
    )).all()
    return [DispatchOut.model_validate(d) for d in rows]


@router.get("/{did}", response_model=DispatchOut)
async def get_dispatch(did: int, db: AsyncSession = Depends(get_db)):
    d = await db.scalar(select(Dispatch).where(Dispatch.id == did))
    if not d:
        raise HTTPException(404, detail="Dispatch not found.")
    return DispatchOut.model_validate(d)


class StagingProposal(BaseModel):
    ambulance_id: int
    ambulance_registration: str
    from_lat: Optional[float] = None
    from_lng: Optional[float] = None
    target_lat: float
    target_lng: float
    zone_id: int
    predicted_demand: float
    distance_km: float


class StagingResponse(BaseModel):
    horizon_hours: int
    proposals: list[StagingProposal]
    emitted: int = 0


@router.get("/staging/preview", response_model=StagingResponse)
async def staging_preview(
    horizon_hours: int = Query(2, ge=1, le=12),
    max_distance_km: float = Query(12.0, ge=1.0, le=50.0),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("dispatcher", "admin")),
):
    """Predictive pre-positioning preview. Reads the LSTM hotspot
    forecaster's next-N-hour window per zone and matches each
    above-threshold zone to its nearest idle ambulance via greedy
    nearest-first. Caller decides when to actually emit the advisory.
    """
    proposals = await compute_staging(
        db, horizon_hours=horizon_hours, max_distance_km=max_distance_km)
    return StagingResponse(horizon_hours=horizon_hours,
                           proposals=[StagingProposal(**p) for p in proposals])


@router.post("/staging/apply", response_model=StagingResponse)
async def staging_apply(
    horizon_hours: int = Query(2, ge=1, le=12),
    max_distance_km: float = Query(12.0, ge=1.0, le=50.0),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("dispatcher", "admin")),
):
    """Same as /preview, but emits ``staging:position`` Socket.IO events
    so each affected driver dashboard can surface the suggested move."""
    proposals = await compute_staging(
        db, horizon_hours=horizon_hours, max_distance_km=max_distance_km)
    sent = await apply_staging(db, proposals)
    return StagingResponse(
        horizon_hours=horizon_hours,
        proposals=[StagingProposal(**p) for p in proposals],
        emitted=sent,
    )


@router.post("/optimize", response_model=OptimizeResponse)
async def optimize_pending(
    background: BackgroundTasks,
    execute: bool = Query(False, description="Apply the assignment, not just preview."),
    db: AsyncSession = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """Hungarian-algorithm multi-emergency assignment.

    Builds a cost matrix over all PENDING emergencies × AVAILABLE ambulances
    where ``cost = severity_weight * blended_eta`` and forbidden type
    pairings get sentinel costs. ``scipy.optimize.linear_sum_assignment``
    finds the global minimum.

    With ``execute=false`` (default) returns the proposed pairings without
    persisting — the dispatcher dashboard uses this to surface
    'would-be-better' suggestions. With ``execute=true`` runs each
    proposal through the standard dispatch pipeline.
    """
    proposals, unassigned, plans = await multi_optimize(
        db, preview=not execute, user_id=user.id if user else None,
    )
    if execute:
        for p in plans:
            if p:
                background.add_task(emit_emergency_dispatched, p.model_dump())
    return OptimizeResponse(
        preview=not execute,
        proposals=[OptimizeProposal(**p.as_dict()) for p in proposals],
        unassigned_emergency_ids=unassigned,
        dispatched_plans=[p for p in plans if p],
    )
