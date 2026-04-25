"""Audit log table — every meaningful action gets a row here."""
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, JSON, String

from ..database import Base


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    user_id = Column(Integer, nullable=True, index=True)
    action = Column(String(100), index=True)
    entity_type = Column(String(50), index=True)
    entity_id = Column(Integer, nullable=True)
    details = Column(JSON, nullable=True)
