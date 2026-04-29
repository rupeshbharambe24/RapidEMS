"""Pydantic schemas for the Dispatch resource."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class DispatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    emergency_id: int
    ambulance_id: int
    hospital_id: int
    dispatched_at: datetime
    arrived_on_scene_at: Optional[datetime] = None
    departed_scene_at: Optional[datetime] = None
    arrived_hospital_at: Optional[datetime] = None
    predicted_eta_seconds: int
    distance_meters: float
    hospital_recommendation_score: float
    status: str


class DispatchPlan(BaseModel):
    """Returned when the dispatch engine assigns a unit + hospital."""
    dispatch_id: int
    emergency_id: int
    ambulance_id: int
    ambulance_registration: str
    hospital_id: int
    hospital_name: str
    predicted_eta_seconds: int
    predicted_eta_minutes: float
    distance_km: float
    road_distance_km: Optional[float] = None
    hospital_score: float
    severity_level: int
    severity_label: str
    severity_confidence: float
    inferred_patient_type: str
    routing_provider: Optional[str] = None
    congestion: Optional[float] = None
    polyline: Optional[list[list[float]]] = None
    used_fallback: bool = False
    notes: Optional[str] = None


class RoutePreview(BaseModel):
    """Response for the GET /routing/preview endpoint."""
    seconds: float
    minutes: float
    meters: float
    kilometers: float
    polyline: list[list[float]]
    congestion: float
    provider: str
    used_fallback: bool


# ── Multi-emergency optimisation (Phase 1.2) ──────────────────────────────
class OptimizeProposal(BaseModel):
    emergency_id: int
    ambulance_id: int
    ambulance_registration: str
    predicted_eta_seconds: int
    predicted_eta_minutes: float
    severity_level: int
    cost: float
    road_provider: str


class OptimizeResponse(BaseModel):
    preview: bool
    proposals: list[OptimizeProposal]
    unassigned_emergency_ids: list[int]
    dispatched_plans: list[DispatchPlan] = []     # only populated when preview=False
