"""Patient-uploaded medical records (MRI, CT, X-ray, ECG, blood tests, ...)."""
import enum
from datetime import datetime

from sqlalchemy import (Column, DateTime, ForeignKey, Integer, String, Text)
from sqlalchemy.orm import relationship

from ..database import Base


class RecordType(str, enum.Enum):
    MRI = "mri"
    CT_SCAN = "ct_scan"
    XRAY = "xray"
    ECG = "ecg"
    BLOOD_TEST = "blood_test"
    PRESCRIPTION = "prescription"
    DISCHARGE_SUMMARY = "discharge_summary"
    OTHER = "other"


class MedicalRecord(Base):
    __tablename__ = "medical_records"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer,
                        ForeignKey("patient_profiles.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    record_type = Column(String(40), default=RecordType.OTHER.value)

    file_name = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)   # relative to UPLOADS_DIR
    file_size = Column(Integer)                       # bytes
    mime_type = Column(String(80))

    description = Column(Text)
    # LLM-generated short summary on upload — saves time at intake.
    auto_summary = Column(Text)

    uploaded_at = Column(DateTime, default=datetime.utcnow)

    patient = relationship("PatientProfile", back_populates="medical_records")
