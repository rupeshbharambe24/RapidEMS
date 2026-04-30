"""AR turn-by-turn overlay endpoint.

Reads the active dispatch's stored polyline, condenses it into the
~5-15 waypoints an AR client needs, and returns the overlay payload.
The response is a self-contained AR scene description — origin,
destination, sequenced waypoints with bearings + turn cues — so the
client can place markers without making further calls.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.ambulance import Ambulance
from ..models.dispatch import Dispatch
from ..models.hospital import Hospital
from ..models.user import User
from ..services.ar_navigation import waypoints_for
from .deps import require_role


router = APIRouter(prefix="/ar", tags=["ar"])


class ARWaypoint(BaseModel):
    index: int
    lat: float
    lng: float
    distance_to_next_m: int
    cumulative_distance_m: int
    bearing_deg: float
    turn_cue: str
    anchor: str
    label: Optional[str] = None


class ARPosition(BaseModel):
    lat: float
    lng: float
    label: Optional[str] = None


class AROverlay(BaseModel):
    dispatch_id: int
    ambulance_id: int
    ambulance_registration: str
    hospital_id: int
    destination: ARPosition
    current_position: Optional[ARPosition] = None
    waypoints: List[ARWaypoint]
    total_distance_m: int
    predicted_eta_seconds: int
    has_polyline: bool


@router.get("/turn-by-turn/{dispatch_id}", response_model=AROverlay)
async def turn_by_turn(
    dispatch_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("paramedic", "dispatcher", "admin")),
):
    """AR overlay payload for the given dispatch.

    Returns 404 if the dispatch doesn't exist; returns the overlay
    with ``has_polyline=False`` and an empty waypoint list when the
    routing chain fell through to haversine and no polyline was stored
    — clients should render a straight bearing line in that case.
    """
    d = await db.scalar(select(Dispatch).where(Dispatch.id == dispatch_id))
    if not d:
        raise HTTPException(404, detail="Dispatch not found.")

    amb = await db.scalar(select(Ambulance).where(Ambulance.id == d.ambulance_id))
    hosp = await db.scalar(select(Hospital).where(Hospital.id == d.hospital_id))
    if not amb or not hosp:
        raise HTTPException(409,
            detail="Dispatch references an ambulance or hospital that no longer exists.")

    pts = waypoints_for(d.route_polyline, destination_label=hosp.name)
    total_m = pts[-1]["cumulative_distance_m"] if pts else int(d.distance_meters or 0)

    current: Optional[ARPosition] = None
    if amb.current_lat is not None and amb.current_lng is not None:
        current = ARPosition(lat=amb.current_lat, lng=amb.current_lng,
                             label=amb.registration_number)

    return AROverlay(
        dispatch_id=d.id,
        ambulance_id=amb.id,
        ambulance_registration=amb.registration_number,
        hospital_id=hosp.id,
        destination=ARPosition(lat=hosp.lat, lng=hosp.lng, label=hosp.name),
        current_position=current,
        waypoints=[ARWaypoint(**w) for w in pts],
        total_distance_m=total_m,
        predicted_eta_seconds=d.predicted_eta_seconds or 0,
        has_polyline=bool(pts),
    )
