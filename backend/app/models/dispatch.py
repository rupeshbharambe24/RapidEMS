"""Dispatch records — one per (emergency, ambulance, hospital) assignment."""
import enum
from datetime import datetime
from sqlalchemy import (Column, DateTime, Float, ForeignKey, Integer, String,
                        Text)
from sqlalchemy.orm import relationship

from ..database import Base


class DispatchStatus(str, enum.Enum):
    DISPATCHED = "dispatched"
    EN_ROUTE = "en_route"
    ON_SCENE = "on_scene"
    TRANSPORTING = "transporting"
    ARRIVED_HOSPITAL = "arrived_hospital"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class Dispatch(Base):
    __tablename__ = "dispatches"

    id = Column(Integer, primary_key=True, index=True)
    emergency_id = Column(Integer, ForeignKey("emergencies.id"), index=True)
    ambulance_id = Column(Integer, ForeignKey("ambulances.id"), index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), index=True)

    dispatched_at = Column(DateTime, default=datetime.utcnow, index=True)
    arrived_on_scene_at = Column(DateTime, nullable=True)
    departed_scene_at = Column(DateTime, nullable=True)
    arrived_hospital_at = Column(DateTime, nullable=True)

    predicted_eta_seconds = Column(Integer)
    actual_response_time_seconds = Column(Integer, nullable=True)
    distance_meters = Column(Float)

    route_polyline = Column(Text, nullable=True)
    hospital_recommendation_score = Column(Float)
    status = Column(String(30), default=DispatchStatus.DISPATCHED.value, index=True)

    dispatcher_notes = Column(Text, nullable=True)

    # Phase 2.8 — multi-tenancy.
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True,
                       index=True)

    emergency = relationship("Emergency", back_populates="dispatches")
    ambulance = relationship("Ambulance", back_populates="dispatches")
    hospital = relationship("Hospital", back_populates="dispatches")
