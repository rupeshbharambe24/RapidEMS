"""Drone reconnaissance endpoints.

Roster + manual dispatch. Auto-dispatch fires from the emergencies
router for SEV-1 / MCI / fire / multi-vehicle calls (see
``services.drone_recon.should_auto_dispatch``).
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.emergency import Emergency
from ..models.user import User
from ..services.drone_recon import (DRONES, dispatch_drone, list_active,
                                    list_drones)
from .deps import require_role


router = APIRouter(prefix="/drones", tags=["drones"])


class DroneOut(BaseModel):
    id: int
    registration: str
    status: str
    sensor_payload: List[str]
    current_lat: Optional[float] = None
    current_lng: Optional[float] = None
    base_lat: float
    base_lng: float
    current_emergency_id: Optional[int] = None
    eta_arrival_at: Optional[float] = None


class DroneDispatchIn(BaseModel):
    emergency_id: int = Field(..., gt=0,
        description="Existing Emergency to launch a drone toward.")


class DroneDispatchOut(BaseModel):
    drone_id: int
    drone_registration: str
    sensor_payload: List[str]
    eta_seconds: float
    eta_arrival_at: float
    emergency_id: int


@router.get("", response_model=List[DroneOut])
async def list_all(
    _: User = Depends(require_role("dispatcher", "admin")),
):
    return [DroneOut(**d) for d in list_drones()]


@router.get("/active", response_model=List[DroneOut])
async def list_in_flight(
    _: User = Depends(require_role("dispatcher", "admin")),
):
    """Drones currently en-route, on-scene, or returning."""
    return [DroneOut(**d) for d in list_active()]


@router.post("/dispatch", response_model=DroneDispatchOut, status_code=201)
async def manual_dispatch(
    payload: DroneDispatchIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("dispatcher", "admin")),
):
    """Launch a drone toward an existing emergency. Picks the nearest
    free drone; refuses with 503 if the whole fleet is busy."""
    e = await db.scalar(select(Emergency).where(Emergency.id == payload.emergency_id))
    if not e:
        raise HTTPException(404, detail="Emergency not found.")
    result = await dispatch_drone(
        emergency_id=e.id,
        target_lat=e.location_lat, target_lng=e.location_lng,
        chief_complaint=e.chief_complaint,
    )
    if result is None:
        raise HTTPException(503,
            detail="No drone available — the entire fleet is in flight.")
    return DroneDispatchOut(**result)
