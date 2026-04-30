"""Pydantic schemas for the Patient layer."""
from datetime import date, datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class PatientProfileBase(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=120)
    date_of_birth: Optional[date] = None
    gender: Optional[Literal["male", "female", "other"]] = None
    blood_group: Optional[str] = Field(default=None, max_length=5)
    phone: Optional[str] = Field(default=None, max_length=20)
    address: Optional[str] = Field(default=None, max_length=255)
    home_lat: Optional[float] = None
    home_lng: Optional[float] = None
    allergies: Optional[str] = None
    chronic_conditions: Optional[str] = None
    current_medications: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    emergency_contact_relation: Optional[str] = None


class PatientProfileCreate(PatientProfileBase):
    pass


class PatientProfileUpdate(BaseModel):
    """All fields optional; partial updates."""
    full_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    gender: Optional[Literal["male", "female", "other"]] = None
    blood_group: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    home_lat: Optional[float] = None
    home_lng: Optional[float] = None
    allergies: Optional[str] = None
    chronic_conditions: Optional[str] = None
    current_medications: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    emergency_contact_relation: Optional[str] = None


class PatientProfileOut(PatientProfileBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime


class MedicalRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    patient_id: int
    record_type: str
    file_name: str
    file_size: Optional[int] = None
    mime_type: Optional[str] = None
    description: Optional[str] = None
    auto_summary: Optional[str] = None
    uploaded_at: datetime


class RaiseEmergencyRequest(BaseModel):
    """Patient-initiated SOS payload."""
    location_lat: float
    location_lng: float
    location_address: Optional[str] = None
    chief_complaint: Optional[str] = None
    symptoms: List[str] = Field(default_factory=list)
    raw_transcript: Optional[str] = Field(
        default=None,
        description="Optional free-text the patient typed; will be parsed by /ai/extract upstream.",
    )


class RaiseEmergencyResponse(BaseModel):
    emergency_id: int
    severity_level: Optional[int] = None
    severity_label: Optional[str] = None
    dispatch_id: Optional[int] = None
    ambulance_registration: Optional[str] = None
    hospital_name: Optional[str] = None
    eta_minutes: Optional[float] = None
    tracking_token: Optional[str] = None
    message: str
