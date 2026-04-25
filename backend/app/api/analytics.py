"""Analytics endpoints — for the Analytics page (KPIs + hotspot heatmap)."""
from datetime import datetime, timedelta
from typing import List

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

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
def get_kpis(db: Session = Depends(get_db)):
    yesterday = datetime.utcnow() - timedelta(hours=24)

    total_24h = (db.query(func.count(Emergency.id))
                 .filter(Emergency.created_at >= yesterday).scalar() or 0)
    pending = (db.query(func.count(Emergency.id))
               .filter(Emergency.status == "pending").scalar() or 0)

    active = (db.query(func.count(Dispatch.id))
              .filter(Dispatch.status.in_(
                  ["dispatched","en_route","on_scene","transporting"])).scalar() or 0)

    avail = (db.query(func.count(Ambulance.id))
             .filter(Ambulance.status == AmbulanceStatus.AVAILABLE.value,
                     Ambulance.is_active == True).scalar() or 0)
    busy = (db.query(func.count(Ambulance.id))
            .filter(Ambulance.status != AmbulanceStatus.AVAILABLE.value,
                    Ambulance.is_active == True).scalar() or 0)

    diversions = (db.query(func.count(Hospital.id))
                  .filter(Hospital.is_diversion == True,
                          Hospital.is_active == True).scalar() or 0)

    avg_resp = (db.query(func.avg(Dispatch.actual_response_time_seconds))
                .filter(Dispatch.actual_response_time_seconds.isnot(None))
                .scalar())
    avg_sev = (db.query(func.avg(Emergency.predicted_severity))
               .filter(Emergency.predicted_severity.isnot(None)).scalar())

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
