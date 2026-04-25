"""Traffic congestion snapshots per zone."""
from datetime import datetime
from sqlalchemy import Column, DateTime, Float, Integer, String

from ..database import Base


class TrafficSnapshot(Base):
    __tablename__ = "traffic_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    recorded_at = Column(DateTime, default=datetime.utcnow, index=True)
    zone_id = Column(String(50), index=True)
    lat = Column(Float)
    lng = Column(Float)
    congestion_level = Column(Float)        # 0.0 (clear) to 1.0 (standstill)
    avg_speed_kmh = Column(Float)
    incident_count = Column(Integer, default=0)
    day_of_week = Column(Integer)
    hour_of_day = Column(Integer)
