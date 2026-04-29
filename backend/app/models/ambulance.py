"""Ambulance fleet records."""
import enum
from datetime import datetime
from sqlalchemy import (Boolean, Column, DateTime, Float, ForeignKey, Integer,
                        JSON, String)
from sqlalchemy.orm import relationship

from ..database import Base


class AmbulanceType(str, enum.Enum):
    BLS = "bls"          # Basic Life Support
    ALS = "als"          # Advanced Life Support
    ICU_MOBILE = "icu"   # Mobile ICU


class AmbulanceStatus(str, enum.Enum):
    AVAILABLE = "available"
    EN_ROUTE = "en_route"
    ON_SCENE = "on_scene"
    TRANSPORTING = "transporting"
    RETURNING = "returning"
    OUT_OF_SERVICE = "out_of_service"


class Ambulance(Base):
    __tablename__ = "ambulances"

    id = Column(Integer, primary_key=True, index=True)
    registration_number = Column(String(20), unique=True, nullable=False, index=True)
    ambulance_type = Column(String(10), default=AmbulanceType.BLS.value)
    status = Column(String(20), default=AmbulanceStatus.AVAILABLE.value, index=True)

    # Live position
    current_lat = Column(Float, index=True)
    current_lng = Column(Float, index=True)
    last_gps_update = Column(DateTime, default=datetime.utcnow)

    # Home depot
    home_station_lat = Column(Float)
    home_station_lng = Column(Float)
    home_station_name = Column(String(100))

    # Crew
    paramedic_name = Column(String(100))
    paramedic_phone = Column(String(20))
    paramedic_certification = Column(String(50))

    # Paramedic user account currently signed in to this unit (1:1).
    # Phase 0.5 — driver dashboard reads its assignment from here.
    assigned_user_id = Column(Integer, ForeignKey("users.id"),
                              nullable=True, unique=True, index=True)

    # Equipment + maintenance
    equipment = Column(JSON, default=list)
    last_service_date = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)

    dispatches = relationship("Dispatch", back_populates="ambulance")
