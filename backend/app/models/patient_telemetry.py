"""Patient wearable / device telemetry.

A time-series row per reading, ingested from Apple HealthKit, Google Fit,
generic BLE health devices (BP cuff, pulse oximeter, glucometer, smart
scale), or manual entry. Vitals captured here flow into the patient's
emergency snapshot when an SOS is raised — the dispatch engine sees the
latest measured values rather than asking the patient to recall them.
"""
import enum
from datetime import datetime

from sqlalchemy import (Column, DateTime, Float, ForeignKey, Integer, JSON,
                        String)

from ..database import Base


class TelemetrySource(str, enum.Enum):
    APPLE_HEALTH = "apple_health"
    GOOGLE_FIT = "google_fit"
    BLE_BP_CUFF = "ble_bp_cuff"
    BLE_PULSE_OX = "ble_pulse_ox"
    BLE_GLUCOMETER = "ble_glucometer"
    SMART_WATCH = "smart_watch"
    MANUAL = "manual"


class PatientTelemetry(Base):
    __tablename__ = "patient_telemetry"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer,
                        ForeignKey("patient_profiles.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    recorded_at = Column(DateTime, nullable=False, default=datetime.utcnow,
                         index=True)
    source = Column(String(40), default=TelemetrySource.MANUAL.value, index=True)

    # Vitals — every column nullable since wearables emit one metric at a
    # time. Bounds are clinical sanity checks, not strict validation.
    heart_rate = Column(Integer, nullable=True)             # bpm, 20-250
    spo2 = Column(Float, nullable=True)                     # %, 40-100
    blood_pressure_systolic = Column(Integer, nullable=True)   # mmHg
    blood_pressure_diastolic = Column(Integer, nullable=True)
    respiratory_rate = Column(Integer, nullable=True)       # /min
    body_temperature_c = Column(Float, nullable=True)       # °C
    glucose_mg_dl = Column(Integer, nullable=True)
    steps_since_midnight = Column(Integer, nullable=True)
    fall_detected = Column(Integer, default=0)              # 0/1, Apple Watch fall sensor

    # Catch-all for source-specific fields the rest of the app doesn't
    # need to know about (HRV, ECG waveforms, sleep stages, etc.).
    raw_payload = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
