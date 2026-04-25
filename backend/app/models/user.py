"""Application users with role-based access."""
import enum
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Integer, String

from ..database import Base


class UserRole(str, enum.Enum):
    DISPATCHER = "dispatcher"
    PARAMEDIC = "paramedic"
    HOSPITAL_STAFF = "hospital_staff"
    ADMIN = "admin"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(120), unique=True, nullable=False)
    full_name = Column(String(120))
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(20), default=UserRole.DISPATCHER.value)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
