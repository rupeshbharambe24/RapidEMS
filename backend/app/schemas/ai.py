"""Pydantic schemas for raw AI inference endpoints."""
from typing import List, Optional

from pydantic import BaseModel, Field


class TriageRequest(BaseModel):
    age: int = Field(ge=0, le=130)
    gender: str = Field(pattern="^(male|female|other)$")
    pulse_rate: Optional[int] = Field(None, ge=20, le=250)
    blood_pressure_systolic: Optional[int] = Field(None, ge=40, le=260)
    blood_pressure_diastolic: Optional[int] = Field(None, ge=20, le=180)
    respiratory_rate: Optional[int] = Field(None, ge=4, le=60)
    spo2: Optional[float] = Field(None, ge=40, le=100)
    gcs_score: Optional[int] = Field(None, ge=3, le=15)
    symptoms: List[str] = Field(default_factory=list)


class TriageResponse(BaseModel):
    severity_level: int
    severity_label: str
    confidence: float
    used_fallback: bool


class ETARequest(BaseModel):
    distance_km: float = Field(ge=0)
    congestion: float = Field(ge=0, le=1)
    hour: int = Field(ge=0, le=23)
    day_of_week: int = Field(ge=0, le=6)
    weather: int = Field(0, ge=0, le=3)
    ambulance_type: int = Field(0, ge=0, le=2)
    road_type: int = Field(0, ge=0, le=2)


class ETAResponse(BaseModel):
    eta_seconds: float
    eta_minutes: float
    used_fallback: bool


class TrafficRequest(BaseModel):
    zone_id: int = Field(ge=0)
    hour: int = Field(ge=0, le=23)
    day_of_week: int = Field(ge=0, le=6)
    month: int = Field(ge=1, le=12)
    weather: int = Field(0, ge=0, le=3)
    is_holiday: int = Field(0, ge=0, le=1)


class TrafficResponse(BaseModel):
    congestion: float
    used_fallback: bool


class HotspotForecast(BaseModel):
    zone_id: int
    next_24h: List[float]
    used_fallback: bool


# ── Triage explanation (Phase 1.5) ────────────────────────────────────────
class ExplainRequest(BaseModel):
    """Either an emergency_id (server loads from DB) or an explicit feature
    snapshot. Exactly one of emergency_id / inline must be supplied."""
    emergency_id: Optional[int] = None
    inline: Optional[TriageRequest] = None


class FeatureFactor(BaseModel):
    name: str
    value: Optional[str] = None
    impact: str       # 'critical' | 'serious' | 'moderate' | 'normal' | 'protective'
    note: str


class ExplainResponse(BaseModel):
    severity_level: int
    severity_label: str
    confidence: float
    factors: List[FeatureFactor]
    narrative: str
    provider: str       # 'groq' | 'gemini' | 'template'
    used_fallback: bool
