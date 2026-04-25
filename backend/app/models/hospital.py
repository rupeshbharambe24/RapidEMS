"""Hospital facility records."""
from datetime import datetime
from sqlalchemy import (Boolean, Column, DateTime, Float, Integer, JSON,
                        String)
from sqlalchemy.orm import relationship

from ..database import Base


class Hospital(Base):
    __tablename__ = "hospitals"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    address = Column(String(300))
    lat = Column(Float, index=True)
    lng = Column(Float, index=True)
    phone = Column(String(20))
    emergency_phone = Column(String(20))

    # Capabilities — list of strings, e.g. ["trauma","cardiac","stroke","pediatric"]
    specialties = Column(JSON, default=list)

    # Bed inventory
    total_beds_general = Column(Integer, default=0)
    available_beds_general = Column(Integer, default=0)
    total_beds_icu = Column(Integer, default=0)
    available_beds_icu = Column(Integer, default=0)
    total_beds_trauma = Column(Integer, default=0)
    available_beds_trauma = Column(Integer, default=0)
    total_beds_pediatric = Column(Integer, default=0)
    available_beds_pediatric = Column(Integer, default=0)
    total_beds_burns = Column(Integer, default=0)
    available_beds_burns = Column(Integer, default=0)

    # Operational
    er_wait_minutes = Column(Integer, default=0)
    is_diversion = Column(Boolean, default=False)
    quality_rating = Column(Integer, default=3)  # 1-5
    is_active = Column(Boolean, default=True)
    last_updated = Column(DateTime, default=datetime.utcnow)

    dispatches = relationship("Dispatch", back_populates="hospital")
