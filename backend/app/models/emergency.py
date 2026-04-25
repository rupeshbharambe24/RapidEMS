"""Emergency call records."""
import enum
from datetime import datetime
from sqlalchemy import (Boolean, Column, DateTime, Float, Integer, JSON,
                        String, Text)
from sqlalchemy.orm import relationship

from ..database import Base


class SeverityLevel(enum.IntEnum):
    CRITICAL = 1
    SERIOUS = 2
    MODERATE = 3
    MINOR = 4
    NON_EMERGENCY = 5


class EmergencyStatus(str, enum.Enum):
    PENDING = "pending"
    DISPATCHED = "dispatched"
    ON_SCENE = "on_scene"
    TRANSPORTING = "transporting"
    ARRIVED = "arrived"
    RESOLVED = "resolved"
    CANCELLED = "cancelled"


class Emergency(Base):
    __tablename__ = "emergencies"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    # Patient identity
    patient_name = Column(String(100))
    patient_age = Column(Integer)
    patient_gender = Column(String(10))         # "male" / "female" / "other"
    phone = Column(String(20))
    next_of_kin_phone = Column(String(20), nullable=True)

    # Location
    location_lat = Column(Float, nullable=False, index=True)
    location_lng = Column(Float, nullable=False, index=True)
    location_address = Column(String(300), nullable=True)

    # Clinical
    symptoms = Column(JSON, default=list)        # list[str]
    chief_complaint = Column(Text, nullable=True)
    pulse_rate = Column(Integer, nullable=True)
    blood_pressure_systolic = Column(Integer, nullable=True)
    blood_pressure_diastolic = Column(Integer, nullable=True)
    respiratory_rate = Column(Integer, nullable=True)
    spo2 = Column(Float, nullable=True)
    gcs_score = Column(Integer, nullable=True)

    # AI output
    predicted_severity = Column(Integer, nullable=True)     # 1-5
    severity_confidence = Column(Float, nullable=True)      # 0.0 - 1.0
    inferred_patient_type = Column(String(30), nullable=True)  # cardiac/trauma/...

    # Operational
    is_multi_casualty = Column(Boolean, default=False)
    casualty_count = Column(Integer, default=1)
    status = Column(String(30), default=EmergencyStatus.PENDING.value, index=True)
    resolved_at = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)

    dispatches = relationship("Dispatch", back_populates="emergency")
