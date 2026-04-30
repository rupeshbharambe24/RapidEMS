"""Tenant — top-level isolation boundary.

Each tenant is a city / agency / regional ops centre. All domain rows
(emergencies, ambulances, hospitals, dispatches, users) carry a
``tenant_id`` so a query without a tenant filter is impossible to write
without going through the central helper. Legacy rows from before
Phase 2.8 are unscoped (tenant_id NULL), and we keep them readable
under the conventional 'default' tenant slug.
"""
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String

from ..database import Base


class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String(40), unique=True, nullable=False, index=True)
    name = Column(String(120), nullable=False)
    is_active = Column(Boolean, default=True)
    # Optional vanity overrides for the city centre coordinates the
    # dispatcher copilot uses ('within 5km of the city centre').
    city_lat = Column(String(20), nullable=True)
    city_lng = Column(String(20), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
