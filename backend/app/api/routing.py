"""Routing endpoints — exposes the multi-provider road routing service."""
from fastapi import APIRouter, Query

from ..schemas.dispatch import RoutePreview
from ..services.routing_service import route as road_route

router = APIRouter(prefix="/routing", tags=["routing"])


@router.get("/preview", response_model=RoutePreview)
async def preview(
    from_lat: float = Query(..., description="Origin latitude"),
    from_lng: float = Query(..., description="Origin longitude"),
    to_lat: float = Query(..., description="Destination latitude"),
    to_lng: float = Query(..., description="Destination longitude"),
):
    r = await road_route(from_lat, from_lng, to_lat, to_lng)
    return RoutePreview(
        seconds=r.seconds,
        minutes=round(r.seconds / 60.0, 2),
        meters=r.meters,
        kilometers=round(r.meters / 1000.0, 3),
        polyline=r.polyline,
        congestion=r.congestion,
        provider=r.provider,
        used_fallback=r.used_fallback,
    )
