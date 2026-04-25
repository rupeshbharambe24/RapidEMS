"""Pydantic schemas for the Hospital resource."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class HospitalBase(BaseModel):
    name: str
    address: Optional[str] = None
    lat: float
    lng: float
    phone: Optional[str] = None
    emergency_phone: Optional[str] = None

    specialties: List[str] = Field(default_factory=list)

    total_beds_general: int = 0
    available_beds_general: int = 0
    total_beds_icu: int = 0
    available_beds_icu: int = 0
    total_beds_trauma: int = 0
    available_beds_trauma: int = 0
    total_beds_pediatric: int = 0
    available_beds_pediatric: int = 0
    total_beds_burns: int = 0
    available_beds_burns: int = 0

    er_wait_minutes: int = 0
    is_diversion: bool = False
    quality_rating: int = Field(3, ge=1, le=5)


class HospitalCreate(HospitalBase):
    pass


class HospitalBedsUpdate(BaseModel):
    available_beds_general: Optional[int] = None
    available_beds_icu: Optional[int] = None
    available_beds_trauma: Optional[int] = None
    available_beds_pediatric: Optional[int] = None
    available_beds_burns: Optional[int] = None
    er_wait_minutes: Optional[int] = None
    is_diversion: Optional[bool] = None


class HospitalOut(HospitalBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    is_active: bool
    last_updated: datetime
