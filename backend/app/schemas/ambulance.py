"""Pydantic schemas for the Ambulance resource."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class AmbulanceBase(BaseModel):
    registration_number: str
    ambulance_type: str = "bls"
    home_station_lat: float
    home_station_lng: float
    home_station_name: Optional[str] = None
    paramedic_name: Optional[str] = None
    paramedic_phone: Optional[str] = None
    paramedic_certification: Optional[str] = None
    equipment: List[str] = Field(default_factory=list)


class AmbulanceCreate(AmbulanceBase):
    pass


class AmbulanceLocationUpdate(BaseModel):
    current_lat: float
    current_lng: float


class AmbulanceStatusUpdate(BaseModel):
    status: str


class AmbulanceOut(AmbulanceBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    status: str
    current_lat: Optional[float] = None
    current_lng: Optional[float] = None
    last_gps_update: Optional[datetime] = None
    is_active: bool
    assigned_user_id: Optional[int] = None
