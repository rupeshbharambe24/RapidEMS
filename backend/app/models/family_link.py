"""Time-limited tracking links shared with next-of-kin.

The NoK receives a signed token (Phase 0.10); they hit /track/{token} and see
read-only ambulance position + ETA without needing an account.
"""
from datetime import datetime

from sqlalchemy import (Column, DateTime, ForeignKey, Integer, String, Text)

from ..database import Base


class FamilyLink(Base):
    __tablename__ = "family_links"

    id = Column(Integer, primary_key=True, index=True)
    emergency_id = Column(Integer, ForeignKey("emergencies.id"),
                          nullable=False, index=True)
    dispatch_id = Column(Integer, ForeignKey("dispatches.id"), nullable=True)

    nok_name = Column(String(120))
    nok_phone = Column(String(20))
    nok_relation = Column(String(40))

    # Opaque signed token (itsdangerous). Stored hashed for revocation.
    token_hash = Column(String(128), nullable=False, unique=True, index=True)

    expires_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime, nullable=True)
    last_seen_at = Column(DateTime, nullable=True)
    view_count = Column(Integer, default=0)
    notes = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow)
