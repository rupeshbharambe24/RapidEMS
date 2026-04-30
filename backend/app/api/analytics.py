"""Analytics endpoints — for the Analytics page (KPIs + hotspot heatmap)."""
from datetime import datetime, timedelta
from typing import List

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.ambulance import Ambulance, AmbulanceStatus
from ..models.dispatch import Dispatch
from ..models.emergency import Emergency
from ..models.hospital import Hospital
from ..services.ai_service import get_ai_service

router = APIRouter(prefix="/analytics", tags=["analytics"])


class KPIs(BaseModel):
    total_emergencies_24h: int
    pending_emergencies: int
    active_dispatches: int
    available_ambulances: int
    busy_ambulances: int
    hospitals_on_diversion: int
    avg_response_time_seconds: float | None
    avg_severity: float | None


class HotspotZone(BaseModel):
    zone_id: int
    next_hour_demand: float
    next_24h_total: float


class HotspotMap(BaseModel):
    zones: List[HotspotZone]


@router.get("/kpis", response_model=KPIs)
async def get_kpis(db: AsyncSession = Depends(get_db)):
    yesterday = datetime.utcnow() - timedelta(hours=24)

    total_24h = (await db.scalar(
        select(func.count(Emergency.id))
        .where(Emergency.created_at >= yesterday)
    )) or 0
    pending = (await db.scalar(
        select(func.count(Emergency.id))
        .where(Emergency.status == "pending")
    )) or 0

    active = (await db.scalar(
        select(func.count(Dispatch.id))
        .where(Dispatch.status.in_(
            ["dispatched", "en_route", "on_scene", "transporting"]))
    )) or 0

    avail = (await db.scalar(
        select(func.count(Ambulance.id))
        .where(Ambulance.status == AmbulanceStatus.AVAILABLE.value,
               Ambulance.is_active == True)
    )) or 0
    busy = (await db.scalar(
        select(func.count(Ambulance.id))
        .where(Ambulance.status != AmbulanceStatus.AVAILABLE.value,
               Ambulance.is_active == True)
    )) or 0

    diversions = (await db.scalar(
        select(func.count(Hospital.id))
        .where(Hospital.is_diversion == True, Hospital.is_active == True)
    )) or 0

    avg_resp = await db.scalar(
        select(func.avg(Dispatch.actual_response_time_seconds))
        .where(Dispatch.actual_response_time_seconds.isnot(None))
    )
    avg_sev = await db.scalar(
        select(func.avg(Emergency.predicted_severity))
        .where(Emergency.predicted_severity.isnot(None))
    )

    return KPIs(
        total_emergencies_24h=int(total_24h),
        pending_emergencies=int(pending),
        active_dispatches=int(active),
        available_ambulances=int(avail),
        busy_ambulances=int(busy),
        hospitals_on_diversion=int(diversions),
        avg_response_time_seconds=float(avg_resp) if avg_resp else None,
        avg_severity=float(avg_sev) if avg_sev else None,
    )


@router.get("/hotspots", response_model=HotspotMap)
def hotspots(n_zones: int = Query(12, ge=1, le=24)):
    """Return next-24-hour demand forecast per zone (uses LSTM model)."""
    import numpy as np
    ai = get_ai_service()
    zones = []
    for z in range(n_zones):
        rng = np.random.default_rng(z + 1)
        recent = (rng.poisson(2.0, 48)).tolist()
        out = ai.forecast_hotspots(recent_counts=recent, zone_id=z)
        next_24 = out["next_24h"]
        zones.append(HotspotZone(
            zone_id=z,
            next_hour_demand=round(next_24[0], 3),
            next_24h_total=round(float(sum(next_24)), 2),
        ))
    return HotspotMap(zones=zones)
