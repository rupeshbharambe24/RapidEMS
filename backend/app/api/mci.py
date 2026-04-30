"""Mass-Casualty Incident command endpoints.

Surfaces:
  POST /mci/declare           Open a new MCI; refuses if one is already
                              active. dispatcher / admin only.
  POST /mci/{id}/close        Close it.
  GET  /mci                   Active incident + roster snapshot.
  POST /mci/victims           Register a victim. Vitals are optional;
                              the START algorithm runs against whatever
                              is supplied and writes the category back.
  POST /mci/optimize          Hungarian preview — proposed assignments.
  POST /mci/execute           Same Hungarian, but run each pair through
                              dispatch_engine for real.
"""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.mci import (MciIncident, MciStatus, MciVictim, MciVictimStatus,
                          StartCategory)
from ..models.user import User
from ..schemas.dispatch import DispatchPlan
from ..services.mci import (execute_mci, get_active_incident, optimize_mci,
                            start_classify)
from .deps import require_role

router = APIRouter(prefix="/mci", tags=["mci"])


# ── Schemas ────────────────────────────────────────────────────────────────
class MciDeclareIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    location_lat: float
    location_lng: float
    location_address: Optional[str] = None
    estimated_victim_count: Optional[int] = Field(default=None, ge=0)
    notes: Optional[str] = None


class MciIncidentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    location_lat: float
    location_lng: float
    location_address: Optional[str] = None
    estimated_victim_count: Optional[int] = None
    notes: Optional[str] = None
    status: str
    declared_by_user_id: Optional[int] = None
    declared_at: datetime
    closed_at: Optional[datetime] = None


class VictimIn(BaseModel):
    label: Optional[str] = Field(default=None, max_length=80)
    age: Optional[int] = Field(default=None, ge=0, le=130)
    gender: Optional[str] = None
    can_walk: Optional[bool] = None
    breathing: Optional[bool] = None
    respiratory_rate: Optional[int] = Field(default=None, ge=0, le=80)
    pulse_rate: Optional[int] = Field(default=None, ge=0, le=300)
    capillary_refill_seconds: Optional[float] = Field(default=None, ge=0, le=20)
    follows_commands: Optional[bool] = None
    notes: Optional[str] = Field(default=None, max_length=500)


class VictimOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    incident_id: int
    label: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    category: str
    status: str
    pulse_rate: Optional[int] = None
    respiratory_rate: Optional[int] = None
    can_walk: Optional[bool] = None
    breathing: Optional[bool] = None
    follows_commands: Optional[bool] = None
    capillary_refill_seconds: Optional[float] = None
    notes: Optional[str] = None
    registered_at: datetime
    assigned_at: Optional[datetime] = None
    dispatched_to_dispatch_id: Optional[int] = None


class CategoryCounts(BaseModel):
    red: int = 0
    yellow: int = 0
    green: int = 0
    black: int = 0
    assigned: int = 0
    transported: int = 0
    delivered: int = 0


class MciSnapshot(BaseModel):
    incident: Optional[MciIncidentOut] = None
    victims: List[VictimOut] = []
    counts: CategoryCounts = CategoryCounts()


class OptimizeProposal(BaseModel):
    victim_id: int
    category: str
    ambulance_id: int
    ambulance_registration: str
    scene_eta_seconds: int
    cost: float


class OptimizeOut(BaseModel):
    proposals: List[OptimizeProposal] = []


class ExecuteOut(BaseModel):
    proposals: List[OptimizeProposal] = []
    dispatched_plans: List[DispatchPlan] = []


# ── Routes ─────────────────────────────────────────────────────────────────
@router.post("/declare", response_model=MciIncidentOut, status_code=201)
async def declare_mci(
    payload: MciDeclareIn,
    user: User = Depends(require_role("dispatcher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    existing = await get_active_incident(db)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An MCI ({existing.id} '{existing.name}') is already active.")
    inc = MciIncident(
        **payload.model_dump(),
        declared_by_user_id=user.id,
        tenant_id=user.tenant_id,
    )
    db.add(inc)
    await db.commit()
    await db.refresh(inc)
    return MciIncidentOut.model_validate(inc)


@router.post("/{incident_id}/close", response_model=MciIncidentOut)
async def close_mci(
    incident_id: int,
    _: User = Depends(require_role("dispatcher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    inc = await db.scalar(select(MciIncident).where(MciIncident.id == incident_id))
    if not inc:
        raise HTTPException(404, detail="Incident not found.")
    inc.status = MciStatus.CLOSED.value
    inc.closed_at = datetime.utcnow()
    await db.commit()
    await db.refresh(inc)
    return MciIncidentOut.model_validate(inc)


@router.get("", response_model=MciSnapshot)
async def get_snapshot(
    _: User = Depends(require_role("dispatcher", "paramedic", "admin")),
    db: AsyncSession = Depends(get_db),
):
    inc = await get_active_incident(db)
    if not inc:
        return MciSnapshot()
    rows = list((await db.scalars(
        select(MciVictim).where(MciVictim.incident_id == inc.id)
        .order_by(MciVictim.registered_at.asc())
    )).all())
    counts = CategoryCounts()
    for v in rows:
        if v.status in (MciVictimStatus.ASSIGNED.value,):
            counts.assigned += 1
        elif v.status == MciVictimStatus.TRANSPORTED.value:
            counts.transported += 1
        elif v.status == MciVictimStatus.DELIVERED.value:
            counts.delivered += 1
        if v.category == StartCategory.RED.value:    counts.red += 1
        elif v.category == StartCategory.YELLOW.value: counts.yellow += 1
        elif v.category == StartCategory.GREEN.value:  counts.green += 1
        elif v.category == StartCategory.BLACK.value:  counts.black += 1
    return MciSnapshot(
        incident=MciIncidentOut.model_validate(inc),
        victims=[VictimOut.model_validate(v) for v in rows],
        counts=counts,
    )


@router.post("/victims", response_model=VictimOut, status_code=201)
async def register_victim(
    payload: VictimIn,
    _: User = Depends(require_role("dispatcher", "paramedic", "admin")),
    db: AsyncSession = Depends(get_db),
):
    inc = await get_active_incident(db)
    if not inc:
        raise HTTPException(409, detail="No active MCI — declare one first.")
    cat = start_classify(
        can_walk=payload.can_walk, breathing=payload.breathing,
        respiratory_rate=payload.respiratory_rate,
        pulse_rate=payload.pulse_rate,
        capillary_refill_seconds=payload.capillary_refill_seconds,
        follows_commands=payload.follows_commands,
    )
    v = MciVictim(
        incident_id=inc.id,
        category=cat,
        **payload.model_dump(),
    )
    db.add(v)
    await db.commit()
    await db.refresh(v)
    return VictimOut.model_validate(v)


@router.post("/optimize", response_model=OptimizeOut)
async def optimize(
    _: User = Depends(require_role("dispatcher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    proposals = await optimize_mci(db)
    return OptimizeOut(proposals=[OptimizeProposal(**p) for p in proposals])


@router.post("/execute", response_model=ExecuteOut)
async def execute(
    user: User = Depends(require_role("dispatcher", "admin")),
    db: AsyncSession = Depends(get_db),
):
    proposals, plans = await execute_mci(db, user_id=user.id)
    return ExecuteOut(
        proposals=[OptimizeProposal(**p) for p in proposals],
        dispatched_plans=plans,
    )
