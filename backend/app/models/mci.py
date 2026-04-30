"""Mass-Casualty Incident (MCI) state.

When the dispatcher toggles MCI mode the system swaps its objective from
per-emergency optimality to maximum-throughput triage: many victims, one
incident location, prioritise by START/SALT category.

Two tables:
  mci_incidents  one row per active MCI; only one ``status='active'`` row
                 is allowed at a time. Closing it sets status='closed' so
                 the audit trail stays.
  mci_victims    individual victims registered to an incident. Each carries
                 the full vital snapshot at registration plus the START
                 triage category (red / yellow / green / black).
"""
import enum
from datetime import datetime

from sqlalchemy import (Boolean, Column, DateTime, Float, ForeignKey,
                        Integer, JSON, String)
from sqlalchemy.orm import relationship

from ..database import Base


class MciStatus(str, enum.Enum):
    ACTIVE = "active"
    CLOSED = "closed"


class StartCategory(str, enum.Enum):
    """START triage colours.

    RED       immediate — life-threatening, transport now
    YELLOW    delayed — serious but stable enough to wait
    GREEN     minor — walking wounded
    BLACK     expectant — deceased / non-survivable
    """
    RED = "red"
    YELLOW = "yellow"
    GREEN = "green"
    BLACK = "black"


class MciVictimStatus(str, enum.Enum):
    REGISTERED = "registered"     # logged at the scene
    ASSIGNED = "assigned"         # ambulance dispatched for this victim
    TRANSPORTED = "transported"   # patient en route to hospital
    DELIVERED = "delivered"       # arrived at hospital
    DECEASED = "deceased"


class MciIncident(Base):
    __tablename__ = "mci_incidents"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    location_lat = Column(Float, nullable=False)
    location_lng = Column(Float, nullable=False)
    location_address = Column(String(300), nullable=True)
    notes = Column(String(1000), nullable=True)

    # Estimated headcount at the time the dispatcher declared MCI.
    estimated_victim_count = Column(Integer, nullable=True)

    status = Column(String(20), default=MciStatus.ACTIVE.value, index=True)
    declared_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    declared_at = Column(DateTime, default=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True,
                       index=True)

    victims = relationship(
        "MciVictim", cascade="all, delete-orphan", back_populates="incident",
    )


class MciVictim(Base):
    __tablename__ = "mci_victims"

    id = Column(Integer, primary_key=True, index=True)
    incident_id = Column(Integer,
                         ForeignKey("mci_incidents.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    label = Column(String(80), nullable=True)
    age = Column(Integer, nullable=True)
    gender = Column(String(10), nullable=True)

    # Vitals snapshot at registration (used for START classification).
    can_walk = Column(Boolean, nullable=True)
    breathing = Column(Boolean, nullable=True)
    respiratory_rate = Column(Integer, nullable=True)
    pulse_rate = Column(Integer, nullable=True)
    capillary_refill_seconds = Column(Float, nullable=True)
    follows_commands = Column(Boolean, nullable=True)

    notes = Column(String(500), nullable=True)
    raw_assessment = Column(JSON, nullable=True)

    category = Column(String(10), default=StartCategory.YELLOW.value,
                      index=True)
    status = Column(String(20), default=MciVictimStatus.REGISTERED.value,
                    index=True)

    # Once dispatched these point at the regular dispatch infra so the
    # MCI flow reuses everything (ambulance, hospital, briefing).
    dispatched_to_dispatch_id = Column(Integer, ForeignKey("dispatches.id"),
                                       nullable=True)

    registered_at = Column(DateTime, default=datetime.utcnow)
    assigned_at = Column(DateTime, nullable=True)

    incident = relationship("MciIncident", back_populates="victims")
