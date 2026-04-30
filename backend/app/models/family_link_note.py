"""Short bidirectional notes attached to a FamilyLink.

Lets the next-of-kin reply through the public tracking page ("I'm at the
hospital", "stuck in traffic, ETA 10m"). Each note is timestamped, stamped
with the sender role, and length-capped — they're presence updates, not
chat. The patient + dispatcher both see them.
"""
import enum
from datetime import datetime

from sqlalchemy import (Column, DateTime, ForeignKey, Integer, String, Text)

from ..database import Base


class NoteSenderRole(str, enum.Enum):
    NOK = "nok"
    DISPATCHER = "dispatcher"
    PATIENT = "patient"
    SYSTEM = "system"


class FamilyLinkNote(Base):
    __tablename__ = "family_link_notes"

    id = Column(Integer, primary_key=True, index=True)
    family_link_id = Column(Integer,
                            ForeignKey("family_links.id", ondelete="CASCADE"),
                            nullable=False, index=True)
    sender_role = Column(String(20), default=NoteSenderRole.NOK.value)
    sender_name = Column(String(120), nullable=True)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
