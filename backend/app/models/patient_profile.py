"""Patient profile — owned by a User with role=patient."""
from datetime import datetime

from sqlalchemy import (Column, Date, DateTime, ForeignKey, Integer, String,
                        Text)
from sqlalchemy.orm import relationship

from ..database import Base


class PatientProfile(Base):
    __tablename__ = "patient_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"),
                     unique=True, nullable=False, index=True)

    full_name = Column(String(120), nullable=False)
    date_of_birth = Column(Date)
    gender = Column(String(10))         # male | female | other
    blood_group = Column(String(5))     # O+, A-, AB+, ...
    phone = Column(String(20))

    # Address
    address = Column(String(255))
    home_lat = Column(String(20))
    home_lng = Column(String(20))

    # Clinical history (free text, LLM-summarisable)
    allergies = Column(Text)
    chronic_conditions = Column(Text)
    current_medications = Column(Text)

    emergency_contact_name = Column(String(120))
    emergency_contact_phone = Column(String(20))
    emergency_contact_relation = Column(String(40))

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow,
                        onupdate=datetime.utcnow)

    medical_records = relationship(
        "MedicalRecord", cascade="all, delete-orphan", back_populates="patient",
    )
