"""Pre-arrival hospital alerts.

Created at dispatch time and pushed to the destination hospital so the ER
can prepare. Carries the LLM-generated medical briefing (Phase 0.9).
"""
import enum
from datetime import datetime

from sqlalchemy import (Column, DateTime, ForeignKey, Integer, String, Text)

from ..database import Base


class AlertStatus(str, enum.Enum):
    PENDING = "pending"           # just sent, hospital hasn't seen yet
    ACKNOWLEDGED = "acknowledged"  # hospital staff opened it
    ACCEPTED = "accepted"         # hospital confirms readiness
    DIVERTED = "diverted"         # hospital is on diversion / can't take it


class HospitalAlert(Base):
    __tablename__ = "hospital_alerts"

    id = Column(Integer, primary_key=True, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"),
                         nullable=False, index=True)
    dispatch_id = Column(Integer, ForeignKey("dispatches.id"),
                         nullable=False, index=True)
    emergency_id = Column(Integer, ForeignKey("emergencies.id"),
                          nullable=False, index=True)

    severity_level = Column(Integer)
    eta_seconds = Column(Integer)
    patient_type = Column(String(40))

    # LLM-generated ER-ready summary (Phase 0.9 fills this in)
    briefing = Column(Text)

    status = Column(String(20), default=AlertStatus.PENDING.value, index=True)
    acknowledged_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    acknowledged_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
