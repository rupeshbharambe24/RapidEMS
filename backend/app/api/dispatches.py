"""Dispatch listing + multi-emergency optimisation endpoints."""
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.dispatch import Dispatch
from ..models.user import User
from ..schemas.dispatch import (DispatchOut, OptimizeProposal,
                                OptimizeResponse)
from ..services.multi_dispatch import optimize as multi_optimize
from ..sockets.sio import emit_emergency_dispatched
from .deps import get_current_user

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
