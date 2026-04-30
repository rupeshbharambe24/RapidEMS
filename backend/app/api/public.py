"""Public, no-auth read-only system snapshot.

Mounted at ``/public-api`` so the SPA's ``/city`` route stays free. Exposes
city-level aggregates only — every PHI-bearing field is excluded by design,
including patient names, ages, addresses, phone numbers, vitals, and chief
complaints.

Endpoints
---------
    GET /public-api/city          high-level KPIs
    GET /public-api/zones         per-zone activity rollup
    GET /public-api/hospitals     anonymised facility availability
    GET /public-api/heartbeat     trivial 200 to confirm the surface is up
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.ambulance import Ambulance, AmbulanceStatus
from ..models.dispatch import Dispatch
from ..models.emergency import Emergency
from ..models.hospital import Hospital
from ..services.geo_service import estimate_zone_id

router = APIRouter(prefix="/public-api", tags=["public"])


# ── Schemas ────────────────────────────────────────────────────────────────
class PublicCityKPIs(BaseModel):
    active_emergencies: int
    pending_emergencies: int
    available_ambulances: int
    busy_ambulances: int
    hospitals_total: int
    hospitals_on_diversion: int
    icu_beds_available: int
    general_beds_available: int
    avg_response_time_last_hour_seconds: Optional[float] = None
    calls_last_hour: int
    calls_last_24h: int
    avg_severity_24h: Optional[float] = None
    last_updated: datetime


class PublicZone(BaseModel):
    zone_id: int
    active: int
    last_24h: int
    avg_response_seconds: Optional[float] = None


class PublicHospital(BaseModel):
    """Hospital row with no operational PII (no phone, no address)."""
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    specialties: List[str]
    available_beds_general: int
    total_beds_general: int
    available_beds_icu: int
    total_beds_icu: int
    available_beds_trauma: int
    total_beds_trauma: int
    available_beds_pediatric: int
    total_beds_pediatric: int
    available_beds_burns: int
    total_beds_burns: int
    er_wait_minutes: int
    is_diversion: bool
    quality_rating: Optional[int] = None


# ── Heartbeat ──────────────────────────────────────────────────────────────
@router.get("/heartbeat")
def heartbeat():
    return {"ok": True, "now": datetime.utcnow().isoformat(timespec="seconds")}


# ── City KPIs ──────────────────────────────────────────────────────────────
@router.get("/city", response_model=PublicCityKPIs)
async def city_snapshot(db: AsyncSession = Depends(get_db)):
    now = datetime.utcnow()
    last_hour = now - timedelta(hours=1)
    last_day = now - timedelta(hours=24)

    pending = await db.scalar(
        select(func.count(Emergency.id))
        .where(Emergency.status == "pending")
    ) or 0
    active = await db.scalar(
        select(func.count(Dispatch.id))
        .where(Dispatch.status.in_(
            ["dispatched", "en_route", "on_scene", "transporting"]))
    ) or 0
    avail = await db.scalar(
        select(func.count(Ambulance.id))
        .where(Ambulance.status == AmbulanceStatus.AVAILABLE.value,
               Ambulance.is_active == True)
    ) or 0
    busy = await db.scalar(
        select(func.count(Ambulance.id))
        .where(Ambulance.status != AmbulanceStatus.AVAILABLE.value,
               Ambulance.is_active == True)
    ) or 0

    hosp_total = await db.scalar(
        select(func.count(Hospital.id))
        .where(Hospital.is_active == True)
    ) or 0
    hosp_div = await db.scalar(
        select(func.count(Hospital.id))
        .where(Hospital.is_diversion == True, Hospital.is_active == True)
    ) or 0
    icu_avail = await db.scalar(
        select(func.coalesce(func.sum(Hospital.available_beds_icu), 0))
        .where(Hospital.is_active == True)
    ) or 0
    gen_avail = await db.scalar(
        select(func.coalesce(func.sum(Hospital.available_beds_general), 0))
        .where(Hospital.is_active == True)
    ) or 0

    calls_hour = await db.scalar(
        select(func.count(Emergency.id))
        .where(Emergency.created_at >= last_hour)
    ) or 0
    calls_day = await db.scalar(
        select(func.count(Emergency.id))
        .where(Emergency.created_at >= last_day)
    ) or 0
    avg_sev = await db.scalar(
        select(func.avg(Emergency.predicted_severity))
        .where(Emergency.predicted_severity.isnot(None),
               Emergency.created_at >= last_day)
    )
    avg_resp = await db.scalar(
        select(func.avg(Dispatch.actual_response_time_seconds))
        .where(Dispatch.actual_response_time_seconds.isnot(None),
               Dispatch.dispatched_at >= last_hour)
    )

    return PublicCityKPIs(
        active_emergencies=int(active),
        pending_emergencies=int(pending),
        available_ambulances=int(avail),
        busy_ambulances=int(busy),
        hospitals_total=int(hosp_total),
        hospitals_on_diversion=int(hosp_div),
        icu_beds_available=int(icu_avail),
        general_beds_available=int(gen_avail),
        avg_response_time_last_hour_seconds=(
            float(avg_resp) if avg_resp is not None else None),
        calls_last_hour=int(calls_hour),
        calls_last_24h=int(calls_day),
        avg_severity_24h=float(avg_sev) if avg_sev is not None else None,
        last_updated=now,
    )


# ── Per-zone rollup ───────────────────────────────────────────────────────
@router.get("/zones", response_model=List[PublicZone])
async def zones(
    n_zones: int = Query(12, ge=1, le=24),
    db: AsyncSession = Depends(get_db),
):
    """Aggregates emergencies into spatial zones using the same
    ``estimate_zone_id`` helper the hotspot model uses, so the public
    dashboard's heatmap aligns with the analytics page."""
    last_day = datetime.utcnow() - timedelta(hours=24)
    open_states = ["pending", "dispatched"]

    open_rows = list((await db.scalars(
        select(Emergency).where(Emergency.status.in_(open_states))
    )).all())
    day_rows = list((await db.scalars(
        select(Emergency).where(Emergency.created_at >= last_day)
    )).all())

    # Per-zone average response from dispatches in the same window.
    dispatch_rows = list((await db.scalars(
        select(Dispatch).where(
            Dispatch.actual_response_time_seconds.isnot(None),
            Dispatch.dispatched_at >= last_day,
        )
    )).all())

    active: dict[int, int] = {}
    last24: dict[int, int] = {}
    rt_sum: dict[int, float] = {}
    rt_count: dict[int, int] = {}

    for e in open_rows:
        z = estimate_zone_id(e.location_lat, e.location_lng) % n_zones
        active[z] = active.get(z, 0) + 1
    for e in day_rows:
        z = estimate_zone_id(e.location_lat, e.location_lng) % n_zones
        last24[z] = last24.get(z, 0) + 1
    for d in dispatch_rows:
        em = await db.scalar(
            select(Emergency).where(Emergency.id == d.emergency_id))
        if not em:
            continue
        z = estimate_zone_id(em.location_lat, em.location_lng) % n_zones
        rt_sum[z] = rt_sum.get(z, 0.0) + float(d.actual_response_time_seconds)
        rt_count[z] = rt_count.get(z, 0) + 1

    out = []
    for z in range(n_zones):
        out.append(PublicZone(
            zone_id=z,
            active=active.get(z, 0),
            last_24h=last24.get(z, 0),
            avg_response_seconds=(
                rt_sum[z] / rt_count[z] if rt_count.get(z) else None),
        ))
    return out


# ── Anonymised hospital list ──────────────────────────────────────────────
@router.get("/hospitals", response_model=List[PublicHospital])
async def public_hospitals(db: AsyncSession = Depends(get_db)):
    rows = (await db.scalars(
        select(Hospital).where(Hospital.is_active == True)
        .order_by(Hospital.name.asc())
    )).all()
    return [PublicHospital.model_validate(h) for h in rows]
