"""Pydantic schemas for the Emergency resource."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class EmergencyVitalsBase(BaseModel):
    pulse_rate: Optional[int] = Field(None, ge=20, le=250)
    blood_pressure_systolic: Optional[int] = Field(None, ge=40, le=260)
    blood_pressure_diastolic: Optional[int] = Field(None, ge=20, le=180)
    respiratory_rate: Optional[int] = Field(None, ge=4, le=60)
    spo2: Optional[float] = Field(None, ge=40, le=100)
    gcs_score: Optional[int] = Field(None, ge=3, le=15)


class EmergencyCreate(EmergencyVitalsBase):
    patient_name: Optional[str] = None
    patient_age: Optional[int] = Field(None, ge=0, le=130)
    patient_gender: Optional[str] = Field(None, pattern="^(male|female|other)$")
    phone: Optional[str] = None
    next_of_kin_phone: Optional[str] = None

    location_lat: float
    location_lng: float
    location_address: Optional[str] = None

    symptoms: List[str] = Field(default_factory=list)
    chief_complaint: Optional[str] = None

    is_multi_casualty: bool = False
    casualty_count: int = 1
    notes: Optional[str] = None


class EmergencyUpdate(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None
    resolved_at: Optional[datetime] = None


class EmergencyOut(EmergencyCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    predicted_severity: Optional[int] = None
    severity_confidence: Optional[float] = None
    inferred_patient_type: Optional[str] = None
    status: str
    resolved_at: Optional[datetime] = None
