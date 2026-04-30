"""Audit log table — every meaningful action gets a row here.

Phase 2.2 added a tamper-evident hash chain: each row stores
``prev_hash`` (the previous row's ``row_hash``) and its own ``row_hash`` =
SHA-256(prev_hash + canonical(timestamp, action, entity_type, entity_id,
details, user_id)). Any after-the-fact mutation breaks the chain at the
mutated row and every row after it; ``GET /admin/audit-log/verify`` walks
the chain and reports the first mismatch.
"""
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

    # Tamper-evidence chain. Both stored as 64-char hex (sha256). prev_hash
    # for the very first row is "0" * 64 (genesis).
    prev_hash = Column(String(64), nullable=True)
    row_hash = Column(String(64), nullable=True, index=True)
