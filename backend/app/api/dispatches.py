"""Dispatch listing endpoints."""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.dispatch import Dispatch
from ..schemas.dispatch import DispatchOut

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
