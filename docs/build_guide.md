# 🚑 AI-Enabled Smart Emergency Response & Ambulance Coordination System
## Complete Build Guide — Architecture · Data · AI Training · Backend · Frontend

---

> **Ground Rules Before You Start**
> - No external AI API keys (OpenAI, Claude, Gemini, etc.) — all intelligence is your own trained models
> - Google Maps JavaScript API is allowed for map rendering only
> - All AI logic runs locally via trained `.pkl` / `.h5` model files served through a Python FastAPI backend
> - Stack: **Python (AI/Backend)** + **React (Frontend)** + **Socket.IO (Real-time)** + **PostgreSQL (DB)**

---

## 📐 Table of Contents

1. [System Architecture Overview](#1-system-architecture-overview)
2. [Complete Feature List](#2-complete-feature-list)
3. [Technology Stack](#3-technology-stack)
4. [Database Schema](#4-database-schema)
5. [Synthetic Data Generation](#5-synthetic-data-generation)
6. [AI Model Training Pipeline](#6-ai-model-training-pipeline)
   - 6a. Emergency Severity Classifier
   - 6b. ETA Prediction Model
   - 6c. Hospital Recommendation Engine
   - 6d. Traffic Congestion Predictor
   - 6e. Demand Hotspot Forecaster (LSTM)
7. [Backend API (FastAPI)](#7-backend-api-fastapi)
8. [Real-Time Engine (Socket.IO)](#8-real-time-engine-socketio)
9. [Frontend Dashboard (React)](#9-frontend-dashboard-react)
10. [Ambulance GPS Simulation](#10-ambulance-gps-simulation)
11. [Testing Strategy](#11-testing-strategy)
12. [Folder Structure](#12-folder-structure)
13. [Step-by-Step Build Order](#13-step-by-step-build-order)

---

## 1. System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        FRONTEND (React)                         │
│  Live Map · Dispatch Panel · Hospital Board · Analytics         │
└────────────────────────┬────────────────────────────────────────┘
                         │  REST + WebSocket
┌────────────────────────▼────────────────────────────────────────┐
│                   BACKEND (Python FastAPI)                       │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────┐ │
│  │  Emergency   │  │  Dispatch    │  │  Hospital Coordinator  │ │
│  │  Intake API  │  │  Engine      │  │  API                   │ │
│  └──────┬───────┘  └──────┬───────┘  └───────────┬────────────┘ │
│         │                 │                       │              │
│  ┌──────▼─────────────────▼───────────────────────▼───────────┐ │
│  │                    AI Inference Layer                       │ │
│  │  Severity Model · ETA Model · Hospital Model · Traffic Model│ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  ┌──────────────────────┐  ┌──────────────────────────────────┐ │
│  │  Socket.IO Server    │  │  Background Scheduler            │ │
│  │  (Live GPS updates)  │  │  (Hotspot prediction, reporting) │ │
│  └──────────────────────┘  └──────────────────────────────────┘ │
└────────────────────────────────────┬────────────────────────────┘
                                     │
               ┌─────────────────────▼──────────────────────┐
               │              PostgreSQL Database             │
               │  emergencies · ambulances · hospitals ·      │
               │  routes · predictions · audit_log            │
               └────────────────────────────────────────────-─┘
```

**Data Flow for a Single Emergency:**

```
📞 Emergency Call Comes In
        │
        ▼
[Severity Classifier] → Triage Score (1–5)
        │
        ▼
[Nearest Ambulance Finder] → Top 3 ambulances ranked by distance + availability
        │
        ▼
[ETA Predictor] → Predicted arrival time per ambulance
        │
        ▼
[Hospital Matcher] → Ranked hospitals by: bed availability + specialty + distance
        │
        ▼
[Dispatch Command] → Sent to ambulance driver app via Socket.IO
        │
        ▼
[Route Engine] → Fastest route computed (Google Maps Directions API)
        │
        ▼
[Live Tracking] → Patient, dispatcher, and hospital all see real-time ambulance location
```

---

## 2. Complete Feature List

### 🆘 Emergency Intake
- [ ] Emergency call logging form (patient name, age, location, symptoms, vitals if available)
- [ ] **AI Severity Classifier** — 5-level triage (Critical / Serious / Moderate / Minor / Non-Emergency)
- [ ] Auto-priority queue — Critical cases always dispatched first
- [ ] Multi-casualty incident flag — one emergency can request multiple ambulances
- [ ] Callback number + next-of-kin capture

### 🚑 Ambulance Management
- [ ] Live GPS position of every ambulance on the map (simulated or real)
- [ ] Status tracking: Available / En Route / On Scene / Returning / Out of Service
- [ ] Ambulance type: BLS (Basic Life Support) / ALS (Advanced Life Support) / ICU Mobile
- [ ] Crew details: paramedic name, certification level
- [ ] Equipment manifest (defibrillator, oxygen, medications)
- [ ] **AI dispatch** — system recommends best ambulance match (type + distance + ETA)
- [ ] Manual override — dispatcher can reassign

### 🏥 Hospital Management
- [ ] Hospital registry: name, location, specialties, contact
- [ ] Real-time bed availability dashboard (General / ICU / Trauma / Pediatric / Burns)
- [ ] ER wait time tracking
- [ ] Capability tags: Trauma Center, Cath Lab, Stroke Unit, NICU, Burn Unit, etc.
- [ ] **AI Hospital Recommender** — scores hospitals for each patient type
- [ ] Pre-arrival notification sent to hospital when ambulance is dispatched
- [ ] Hospital acceptance / rejection workflow
- [ ] Diversion alerts (hospital at capacity)

### 🗺️ Routing & Traffic
- [ ] Google Maps JavaScript API for map visualization
- [ ] Google Maps Directions API for route calculation
- [ ] Multiple route options with ETA comparison
- [ ] **AI Traffic Predictor** — augments Google ETA with local congestion pattern model
- [ ] Emergency vehicle signal pre-emption simulation (green corridor display)
- [ ] Dynamic rerouting if traffic changes en route

### 📊 Analytics & Predictions
- [ ] **LSTM Demand Hotspot Forecaster** — predicts high-demand zones by time of day / day of week
- [ ] Response time heatmap over city
- [ ] Average response time by zone and hour
- [ ] Hospital load forecasting
- [ ] Weekly/monthly incident reports (PDF export)
- [ ] KPI dashboard: avg response time, dispatch accuracy, hospital match score

### 🔔 Alerts & Communication
- [ ] SMS simulation panel (shows messages sent to patient, hospital, ambulance)
- [ ] In-app notification for dispatcher when a new emergency arrives
- [ ] Escalation alert if no ambulance responds within 60 seconds
- [ ] Weather overlay on map (affects routing recommendations)

### 🔐 Role-Based Access
- [ ] **Dispatcher** — full control, dispatch decisions
- [ ] **Paramedic** — mobile view, update status, receive route
- [ ] **Hospital Admin** — update bed counts, accept/reject incoming patients
- [ ] **System Admin** — manage all users, ambulances, hospitals
- [ ] **Analyst** — read-only analytics dashboard

---

## 3. Technology Stack

### Backend (Python)
```
fastapi==0.111.0          # REST API framework
uvicorn==0.29.0           # ASGI server
python-socketio==5.11.2   # WebSocket real-time events
sqlalchemy==2.0.29        # ORM for PostgreSQL
asyncpg==0.29.0           # Async PostgreSQL driver
psycopg2-binary==2.9.9    # Sync PostgreSQL driver
alembic==1.13.1           # DB migrations
pydantic==2.7.1           # Request/response validation
python-jose[cryptography]  # JWT authentication
passlib[bcrypt]           # Password hashing
python-multipart          # File uploads
httpx==0.27.0             # Async HTTP client (Google Maps calls)
apscheduler==3.10.4       # Background job scheduler
```

### AI / ML (Python)
```
numpy==1.26.4
pandas==2.2.2
scikit-learn==1.4.2
xgboost==2.0.3
lightgbm==4.3.0
tensorflow==2.16.1        # LSTM hotspot model
keras==3.3.3
imbalanced-learn==0.12.2  # Handle class imbalance in severity data
shap==0.45.0              # Model explainability
joblib==1.4.2             # Model serialization
matplotlib==3.9.0         # Training plots
seaborn==0.13.2
```

### Frontend (React)
```
react + react-dom (18.x)
react-router-dom (6.x)       # Multi-page routing
socket.io-client             # Real-time connection
axios                        # REST API calls
@react-google-maps/api       # Google Maps components
recharts                     # Analytics charts
react-hot-toast              # Notifications
zustand                      # Lightweight state management
date-fns                     # Date formatting
react-table (tanstack)       # Data tables
jspdf + jspdf-autotable      # PDF report export
tailwindcss                  # Styling
```

### Infrastructure
```
PostgreSQL 15               # Primary database
Redis (optional)            # Cache for real-time ambulance positions
Docker + Docker Compose     # Local dev environment
nginx (optional)            # Reverse proxy for production
```

---

## 4. Database Schema

Create these tables in PostgreSQL via SQLAlchemy models:

```python
# models.py — paste this into your backend/models.py file

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, JSON, Enum, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import enum

Base = declarative_base()

class SeverityLevel(enum.Enum):
    CRITICAL = 1      # Immediate life threat (cardiac arrest, major trauma)
    SERIOUS = 2       # Urgent but stable (stroke, severe fracture)
    MODERATE = 3      # Needs attention within 30 min (broken arm, moderate pain)
    MINOR = 4         # Can wait (minor cuts, mild symptoms)
    NON_EMERGENCY = 5 # No ambulance needed (advisory only)

class AmbulanceStatus(enum.Enum):
    AVAILABLE = "available"
    EN_ROUTE = "en_route"
    ON_SCENE = "on_scene"
    TRANSPORTING = "transporting"
    RETURNING = "returning"
    OUT_OF_SERVICE = "out_of_service"

class AmbulanceType(enum.Enum):
    BLS = "bls"           # Basic Life Support
    ALS = "als"           # Advanced Life Support
    ICU_MOBILE = "icu"    # Mobile ICU

class Emergency(Base):
    __tablename__ = "emergencies"
    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    patient_name = Column(String(100))
    patient_age = Column(Integer)
    patient_gender = Column(String(10))
    phone = Column(String(20))
    next_of_kin_phone = Column(String(20))
    location_lat = Column(Float, nullable=False)
    location_lng = Column(Float, nullable=False)
    location_address = Column(String(300))
    symptoms = Column(JSON)                       # List of symptom strings
    chief_complaint = Column(Text)
    pulse_rate = Column(Integer, nullable=True)
    blood_pressure_systolic = Column(Integer, nullable=True)
    blood_pressure_diastolic = Column(Integer, nullable=True)
    respiratory_rate = Column(Integer, nullable=True)
    spo2 = Column(Float, nullable=True)           # Oxygen saturation
    gcs_score = Column(Integer, nullable=True)    # Glasgow Coma Scale (3–15)
    predicted_severity = Column(Integer)          # AI output 1–5
    severity_confidence = Column(Float)           # Model confidence %
    is_multi_casualty = Column(Boolean, default=False)
    casualty_count = Column(Integer, default=1)
    status = Column(String(50), default="pending") # pending/dispatched/arrived/resolved/cancelled
    resolved_at = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)
    dispatches = relationship("Dispatch", back_populates="emergency")

class Ambulance(Base):
    __tablename__ = "ambulances"
    id = Column(Integer, primary_key=True)
    registration_number = Column(String(20), unique=True)
    ambulance_type = Column(Enum(AmbulanceType), default=AmbulanceType.BLS)
    status = Column(Enum(AmbulanceStatus), default=AmbulanceStatus.AVAILABLE)
    current_lat = Column(Float)
    current_lng = Column(Float)
    last_gps_update = Column(DateTime, default=datetime.utcnow)
    home_station_lat = Column(Float)
    home_station_lng = Column(Float)
    home_station_name = Column(String(100))
    paramedic_name = Column(String(100))
    paramedic_phone = Column(String(20))
    paramedic_certification = Column(String(50))  # EMT-Basic / EMT-Paramedic / ACLS
    equipment = Column(JSON)                      # List of equipment aboard
    last_service_date = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    dispatches = relationship("Dispatch", back_populates="ambulance")

class Hospital(Base):
    __tablename__ = "hospitals"
    id = Column(Integer, primary_key=True)
    name = Column(String(200))
    address = Column(String(300))
    lat = Column(Float)
    lng = Column(Float)
    phone = Column(String(20))
    emergency_phone = Column(String(20))
    specialties = Column(JSON)                     # ["trauma", "cardiac", "stroke", "pediatric"]
    total_beds_general = Column(Integer, default=0)
    available_beds_general = Column(Integer, default=0)
    total_beds_icu = Column(Integer, default=0)
    available_beds_icu = Column(Integer, default=0)
    total_beds_trauma = Column(Integer, default=0)
    available_beds_trauma = Column(Integer, default=0)
    total_beds_pediatric = Column(Integer, default=0)
    available_beds_pediatric = Column(Integer, default=0)
    total_beds_burns = Column(Integer, default=0)
    available_beds_burns = Column(Integer, default=0)
    er_wait_minutes = Column(Integer, default=0)
    is_diversion = Column(Boolean, default=False)  # True = at capacity, diverting
    is_active = Column(Boolean, default=True)
    last_updated = Column(DateTime, default=datetime.utcnow)
    dispatches = relationship("Dispatch", back_populates="hospital")

class Dispatch(Base):
    __tablename__ = "dispatches"
    id = Column(Integer, primary_key=True)
    emergency_id = Column(Integer, ForeignKey("emergencies.id"))
    ambulance_id = Column(Integer, ForeignKey("ambulances.id"))
    hospital_id = Column(Integer, ForeignKey("hospitals.id"))
    dispatched_at = Column(DateTime, default=datetime.utcnow)
    arrived_on_scene_at = Column(DateTime, nullable=True)
    departed_scene_at = Column(DateTime, nullable=True)
    arrived_hospital_at = Column(DateTime, nullable=True)
    predicted_eta_seconds = Column(Integer)
    actual_response_time_seconds = Column(Integer, nullable=True)
    route_polyline = Column(Text)              # Encoded Google Maps polyline
    distance_meters = Column(Float)
    hospital_recommendation_score = Column(Float)
    dispatcher_notes = Column(Text, nullable=True)
    emergency = relationship("Emergency", back_populates="dispatches")
    ambulance = relationship("Ambulance", back_populates="dispatches")
    hospital = relationship("Hospital", back_populates="dispatches")

class TrafficSnapshot(Base):
    __tablename__ = "traffic_snapshots"
    id = Column(Integer, primary_key=True)
    recorded_at = Column(DateTime, default=datetime.utcnow)
    zone_id = Column(String(50))
    lat = Column(Float)
    lng = Column(Float)
    congestion_level = Column(Float)    # 0.0 (clear) to 1.0 (standstill)
    avg_speed_kmh = Column(Float)
    incident_count = Column(Integer, default=0)
    day_of_week = Column(Integer)       # 0=Monday … 6=Sunday
    hour_of_day = Column(Integer)

class AuditLog(Base):
    __tablename__ = "audit_log"
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    user_id = Column(Integer, nullable=True)
    action = Column(String(100))
    entity_type = Column(String(50))
    entity_id = Column(Integer, nullable=True)
    details = Column(JSON, nullable=True)
```

---

## 5. Synthetic Data Generation

Create `ai/data_generation/generate_all_data.py` and run it once before training.

```python
"""
generate_all_data.py
Generates realistic synthetic training data for all 5 AI models.
Run: python generate_all_data.py
Outputs: data/severity_data.csv, eta_data.csv, hospital_data.csv,
         traffic_data.csv, hotspot_data.csv
"""

import numpy as np
import pandas as pd
import random
from datetime import datetime, timedelta
import os

os.makedirs("data", exist_ok=True)

np.random.seed(42)
random.seed(42)
N = 50_000   # Total samples (increase for better model accuracy)

# ─────────────────────────────────────────────────────────────
# 5.1  SEVERITY CLASSIFIER DATA
# ─────────────────────────────────────────────────────────────
"""
Target: severity_level (1=Critical, 2=Serious, 3=Moderate, 4=Minor, 5=Non-Emergency)
Features: patient vitals + symptoms + demographics
"""

SYMPTOMS_POOL = [
    "chest_pain", "shortness_of_breath", "unconscious", "seizure",
    "major_bleeding", "stroke_symptoms", "cardiac_arrest", "severe_burns",
    "spinal_injury", "head_trauma", "anaphylaxis", "diabetic_emergency",
    "fracture", "moderate_bleeding", "abdominal_pain", "vomiting",
    "dizziness", "high_fever", "minor_cut", "sprain", "headache",
    "anxiety", "nausea", "cough", "back_pain"
]

# Symptom→ severity weight mapping (higher = more severe)
SYMPTOM_SEVERITY_WEIGHT = {
    "cardiac_arrest": 1.0, "unconscious": 0.95, "major_bleeding": 0.9,
    "anaphylaxis": 0.88, "chest_pain": 0.85, "severe_burns": 0.88,
    "spinal_injury": 0.85, "stroke_symptoms": 0.83, "head_trauma": 0.82,
    "shortness_of_breath": 0.78, "seizure": 0.75, "diabetic_emergency": 0.70,
    "high_fever": 0.55, "fracture": 0.50, "moderate_bleeding": 0.50,
    "abdominal_pain": 0.45, "vomiting": 0.35, "dizziness": 0.30,
    "sprain": 0.20, "back_pain": 0.18, "headache": 0.15,
    "nausea": 0.12, "minor_cut": 0.10, "anxiety": 0.08, "cough": 0.07
}

def generate_severity_data(n):
    rows = []
    for _ in range(n):
        # Demographics
        age = np.random.randint(1, 90)
        gender = random.choice([0, 1])  # 0=Female, 1=Male
        
        # Pick 1–4 symptoms
        num_symptoms = random.choices([1, 2, 3, 4], weights=[0.4, 0.35, 0.2, 0.05])[0]
        selected_symptoms = random.sample(SYMPTOMS_POOL, num_symptoms)
        
        # Compute base severity from worst symptom weight
        max_weight = max(SYMPTOM_SEVERITY_WEIGHT[s] for s in selected_symptoms)
        
        # Vitals (correlated with severity)
        # High-severity → abnormal vitals
        if max_weight > 0.80:
            pulse = np.random.choice([
                np.random.randint(0, 40),       # bradycardia/arrest
                np.random.randint(140, 200)     # tachycardia
            ])
            bp_sys = np.random.choice([
                np.random.randint(60, 80),      # shock
                np.random.randint(180, 230)     # hypertensive crisis
            ])
            spo2 = round(np.random.uniform(60, 92), 1)
            rr = np.random.choice([np.random.randint(4, 8), np.random.randint(28, 45)])
            gcs = np.random.randint(3, 10)
        elif max_weight > 0.55:
            pulse = np.random.randint(50, 140)
            bp_sys = np.random.randint(85, 180)
            spo2 = round(np.random.uniform(88, 96), 1)
            rr = np.random.randint(12, 28)
            gcs = np.random.randint(10, 15)
        else:
            pulse = np.random.randint(60, 110)
            bp_sys = np.random.randint(100, 140)
            spo2 = round(np.random.uniform(95, 100), 1)
            rr = np.random.randint(12, 20)
            gcs = np.random.randint(13, 16)
        
        # Elderly patients slightly more severe for same symptoms
        age_factor = 0.05 if age > 65 else (0.03 if age < 5 else 0.0)
        
        # Convert weight → severity label (1=worst, 5=best)
        adjusted_weight = min(1.0, max_weight + age_factor + np.random.normal(0, 0.05))
        if adjusted_weight > 0.82:
            severity = 1
        elif adjusted_weight > 0.65:
            severity = 2
        elif adjusted_weight > 0.42:
            severity = 3
        elif adjusted_weight > 0.20:
            severity = 4
        else:
            severity = 5
        
        # Binary symptom flags for each symptom in pool
        symptom_flags = {s: int(s in selected_symptoms) for s in SYMPTOMS_POOL}
        
        row = {
            "age": age,
            "gender": gender,
            "pulse_rate": pulse,
            "bp_systolic": bp_sys,
            "spo2": spo2,
            "respiratory_rate": rr,
            "gcs_score": gcs,
            "num_symptoms": num_symptoms,
            "is_elderly": int(age > 65),
            "is_pediatric": int(age < 12),
            **symptom_flags,
            "severity_level": severity
        }
        rows.append(row)
    return pd.DataFrame(rows)

severity_df = generate_severity_data(N)
severity_df.to_csv("data/severity_data.csv", index=False)
print(f"✅ Severity data: {len(severity_df)} rows | Distribution:\n{severity_df['severity_level'].value_counts().sort_index()}")


# ─────────────────────────────────────────────────────────────
# 5.2  ETA PREDICTION DATA
# ─────────────────────────────────────────────────────────────
"""
Target: actual_eta_seconds
Features: distance, time of day, traffic, road type, weather, etc.
"""

def generate_eta_data(n):
    rows = []
    for _ in range(n):
        distance_km = round(np.random.exponential(scale=4.0), 2)  # Most calls are within 8km
        distance_km = max(0.3, min(distance_km, 40.0))
        
        hour = np.random.randint(0, 24)
        day_of_week = np.random.randint(0, 7)
        
        # Rush hour: 8–10am, 5–8pm on weekdays
        is_rush_hour = int((day_of_week < 5) and (8 <= hour <= 10 or 17 <= hour <= 20))
        is_night = int(hour >= 22 or hour <= 5)
        is_weekend = int(day_of_week >= 5)
        
        # Traffic congestion level (0=clear, 1=standstill)
        if is_rush_hour:
            congestion = round(np.random.beta(5, 2), 2)  # skewed toward 0.7–0.9
        elif is_night:
            congestion = round(np.random.beta(1, 6), 2)  # skewed toward 0.1–0.2
        else:
            congestion = round(np.random.beta(2, 4), 2)
        
        road_type = random.choices(
            ["highway", "arterial", "urban", "rural"],
            weights=[0.15, 0.35, 0.40, 0.10]
        )[0]
        road_type_enc = {"highway": 0, "arterial": 1, "urban": 2, "rural": 3}[road_type]
        
        # Base speed by road type (km/h) × congestion reduction
        base_speed = {"highway": 90, "arterial": 60, "urban": 40, "rural": 70}[road_type]
        # Ambulance gets ~30% speed advantage (sirens clear traffic)
        effective_speed = base_speed * (1 - congestion * 0.6) * 1.30
        effective_speed = max(15, effective_speed)  # never below 15 km/h
        
        weather = random.choices(
            ["clear", "rain", "heavy_rain", "fog", "storm"],
            weights=[0.55, 0.25, 0.10, 0.07, 0.03]
        )[0]
        weather_enc = {"clear": 0, "rain": 1, "heavy_rain": 2, "fog": 3, "storm": 4}[weather]
        weather_multiplier = {"clear": 1.0, "rain": 1.15, "heavy_rain": 1.35, "fog": 1.20, "storm": 1.50}[weather]
        
        # Calculate base ETA
        base_eta = (distance_km / effective_speed) * 3600 * weather_multiplier
        
        # Add signal waits + dispatch preparation time
        signal_wait = np.random.exponential(30) if not is_night else np.random.exponential(10)
        prep_time = np.random.uniform(45, 120)  # 45s–2min to gear up and depart
        
        actual_eta = base_eta + signal_wait + prep_time + np.random.normal(0, 30)
        actual_eta = max(60, actual_eta)  # minimum 60 seconds
        
        rows.append({
            "distance_km": distance_km,
            "hour_of_day": hour,
            "day_of_week": day_of_week,
            "is_rush_hour": is_rush_hour,
            "is_night": is_night,
            "is_weekend": is_weekend,
            "congestion_level": congestion,
            "road_type": road_type_enc,
            "weather": weather_enc,
            "ambulance_type": random.randint(0, 2),   # 0=BLS, 1=ALS, 2=ICU
            "severity_level": random.randint(1, 5),   # higher severity → faster dispatch
            "actual_eta_seconds": round(actual_eta)
        })
    return pd.DataFrame(rows)

eta_df = generate_eta_data(N)
eta_df.to_csv("data/eta_data.csv", index=False)
print(f"✅ ETA data: {len(eta_df)} rows | Mean ETA: {eta_df['actual_eta_seconds'].mean():.0f}s")


# ─────────────────────────────────────────────────────────────
# 5.3  HOSPITAL RECOMMENDATION DATA
# ─────────────────────────────────────────────────────────────
"""
Target: match_score (0–100) — how well this hospital fits this patient
Features: bed availability, specialty match, distance, ER load, etc.
"""

SPECIALTIES = ["cardiac", "trauma", "stroke", "pediatric", "burns", "orthopedic", "general"]

def generate_hospital_data(n):
    rows = []
    for _ in range(n):
        severity = np.random.randint(1, 6)
        patient_needs = random.choice(SPECIALTIES)
        
        hospital_specialties_count = random.randint(1, 5)
        has_needed_specialty = random.choices([1, 0], weights=[0.55, 0.45])[0]
        
        distance_km = round(np.random.exponential(8.0), 2)
        distance_km = max(0.5, min(distance_km, 60.0))
        
        beds_icu_available = random.randint(0, 30)
        beds_trauma_available = random.randint(0, 20)
        beds_general_available = random.randint(0, 100)
        
        er_wait_min = random.randint(0, 240)
        is_diversion = int(er_wait_min > 120 and beds_general_available < 5)
        
        total_beds_occupied_pct = round(np.random.uniform(0, 1), 2)
        
        # Score formula (used as training target):
        # Lower distance → higher score
        # Has specialty → big bonus
        # Available beds → higher score
        # Low ER wait → higher score
        # Not diversion → required
        
        distance_score = max(0, 100 - distance_km * 2)
        specialty_score = 40 if has_needed_specialty else 0
        
        bed_need = "icu" if severity <= 2 else ("trauma" if severity == 3 else "general")
        bed_available = {
            "icu": beds_icu_available,
            "trauma": beds_trauma_available,
            "general": beds_general_available
        }[bed_need]
        bed_score = min(30, bed_available * 2)
        
        er_score = max(0, 20 - er_wait_min / 12)
        diversion_penalty = -50 if is_diversion else 0
        
        match_score = round(
            (distance_score * 0.30 + specialty_score * 0.40 + bed_score * 0.20 + er_score * 0.10)
            + diversion_penalty + np.random.normal(0, 3)
        )
        match_score = max(0, min(100, match_score))
        
        rows.append({
            "severity_level": severity,
            "patient_specialty_need": SPECIALTIES.index(patient_needs),
            "has_needed_specialty": has_needed_specialty,
            "hospital_specialties_count": hospital_specialties_count,
            "distance_km": distance_km,
            "beds_icu_available": beds_icu_available,
            "beds_trauma_available": beds_trauma_available,
            "beds_general_available": beds_general_available,
            "er_wait_minutes": er_wait_min,
            "is_diversion": is_diversion,
            "total_occupied_pct": total_beds_occupied_pct,
            "match_score": match_score
        })
    return pd.DataFrame(rows)

hospital_df = generate_hospital_data(N)
hospital_df.to_csv("data/hospital_data.csv", index=False)
print(f"✅ Hospital data: {len(hospital_df)} rows | Mean match score: {hospital_df['match_score'].mean():.1f}")


# ─────────────────────────────────────────────────────────────
# 5.4  TRAFFIC CONGESTION DATA
# ─────────────────────────────────────────────────────────────
"""
Target: congestion_level (0.0–1.0)
Features: time, location, historical patterns
"""

def generate_traffic_data(n):
    rows = []
    zone_centers = [(random.uniform(18.8, 19.2), random.uniform(72.7, 73.1)) for _ in range(20)]
    
    for _ in range(n):
        zone_id = random.randint(0, 19)
        zone_lat, zone_lng = zone_centers[zone_id]
        
        dt = datetime(2023, 1, 1) + timedelta(hours=random.randint(0, 8760))
        hour = dt.hour
        dow = dt.weekday()
        month = dt.month
        
        # Simulate rush hour peaks + night lows
        if dow < 5:  # Weekday
            if 8 <= hour <= 10 or 17 <= hour <= 20:
                base_cong = np.random.beta(5, 2)
            elif 11 <= hour <= 16:
                base_cong = np.random.beta(3, 4)
            elif 22 <= hour or hour <= 5:
                base_cong = np.random.beta(1, 8)
            else:
                base_cong = np.random.beta(2, 4)
        else:  # Weekend
            base_cong = np.random.beta(2, 3) if 10 <= hour <= 20 else np.random.beta(1, 6)
        
        # Zone-specific density modifier
        zone_density = (zone_id % 5 + 1) / 5.0  # 0.2 to 1.0
        congestion = round(min(1.0, base_cong * zone_density + np.random.normal(0, 0.03)), 3)
        congestion = max(0.0, congestion)
        
        avg_speed = round(max(5, 70 * (1 - congestion * 0.8) + np.random.normal(0, 3)), 1)
        
        rows.append({
            "zone_id": zone_id,
            "lat": round(zone_lat + np.random.normal(0, 0.005), 5),
            "lng": round(zone_lng + np.random.normal(0, 0.005), 5),
            "hour_of_day": hour,
            "day_of_week": dow,
            "month": month,
            "is_rush_hour": int(dow < 5 and (8 <= hour <= 10 or 17 <= hour <= 20)),
            "is_weekend": int(dow >= 5),
            "zone_density_level": round(zone_density, 2),
            "congestion_level": congestion,
            "avg_speed_kmh": avg_speed
        })
    return pd.DataFrame(rows)

traffic_df = generate_traffic_data(N)
traffic_df.to_csv("data/traffic_data.csv", index=False)
print(f"✅ Traffic data: {len(traffic_df)} rows")


# ─────────────────────────────────────────────────────────────
# 5.5  HOTSPOT TIME-SERIES DATA (for LSTM)
# ─────────────────────────────────────────────────────────────
"""
48 hourly time steps per row (2 days of history) → predict next hour's incident count
This builds sequences for the LSTM model.
"""

def generate_hotspot_data(n_days=730, n_zones=10):
    """Generate 2 years of hourly incident data per zone"""
    rows = []
    for zone_id in range(n_zones):
        zone_base_rate = np.random.uniform(0.5, 3.0)
        for day in range(n_days):
            for hour in range(24):
                dt = datetime(2022, 1, 1) + timedelta(days=day, hours=hour)
                dow = dt.weekday()
                month = dt.month
                
                rush_mult = 2.0 if (dow < 5 and (8 <= hour <= 10 or 17 <= hour <= 20)) else 1.0
                night_mult = 0.3 if (hour >= 23 or hour <= 5) else 1.0
                weekend_mult = 0.7 if dow >= 5 else 1.0
                season_mult = 1.2 if month in [5, 6, 10, 11] else 1.0  # monsoon/festival peaks
                
                lam = zone_base_rate * rush_mult * night_mult * weekend_mult * season_mult
                incident_count = np.random.poisson(lam)
                
                rows.append({
                    "zone_id": zone_id,
                    "datetime": dt.isoformat(),
                    "hour": hour,
                    "day_of_week": dow,
                    "month": month,
                    "is_rush_hour": int(dow < 5 and (8 <= hour <= 10 or 17 <= hour <= 20)),
                    "incident_count": incident_count
                })
    return pd.DataFrame(rows)

hotspot_df = generate_hotspot_data()
hotspot_df.to_csv("data/hotspot_data.csv", index=False)
print(f"✅ Hotspot data: {len(hotspot_df)} rows | Total incidents: {hotspot_df['incident_count'].sum()}")

print("\n🎯 All datasets generated successfully in data/ folder")
```

---

## 6. AI Model Training Pipeline

Create the file `ai/train_all_models.py`. Run this after data generation.

```python
"""
train_all_models.py
Trains all 5 AI models following ML best practices.
Run: python train_all_models.py
Outputs: models/ folder with all saved model files
"""

import os
import numpy as np
import pandas as pd
import joblib
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns

from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_score
from sklearn.preprocessing import StandardScaler, LabelEncoder, RobustScaler
from sklearn.metrics import (classification_report, confusion_matrix,
                             mean_absolute_error, mean_squared_error, r2_score,
                             accuracy_score, f1_score)
from sklearn.pipeline import Pipeline
from sklearn.ensemble import RandomForestClassifier, GradientBoostingRegressor, VotingClassifier
from sklearn.calibration import CalibratedClassifierCV
from xgboost import XGBClassifier, XGBRegressor
from lightgbm import LGBMClassifier, LGBMRegressor
from imblearn.over_sampling import SMOTE
from imblearn.pipeline import Pipeline as ImbPipeline
import shap
import warnings
warnings.filterwarnings('ignore')

os.makedirs("models", exist_ok=True)
os.makedirs("reports", exist_ok=True)

RANDOM_STATE = 42

def save_training_report(model_name, metrics: dict):
    """Save training metrics to a JSON report file."""
    path = f"reports/{model_name}_report.json"
    with open(path, "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"   📄 Report saved: {path}")

def plot_confusion_matrix(y_true, y_pred, model_name, labels):
    fig, ax = plt.subplots(figsize=(8, 6))
    cm = confusion_matrix(y_true, y_pred)
    sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', ax=ax,
                xticklabels=labels, yticklabels=labels)
    ax.set_title(f'{model_name} — Confusion Matrix')
    ax.set_ylabel('True Label')
    ax.set_xlabel('Predicted Label')
    plt.tight_layout()
    plt.savefig(f"reports/{model_name}_confusion_matrix.png", dpi=150)
    plt.close()

def plot_feature_importance(model, feature_names, model_name, top_n=20):
    try:
        if hasattr(model, 'feature_importances_'):
            importances = model.feature_importances_
        elif hasattr(model, 'named_steps'):
            importances = model.named_steps.get('classifier', model.named_steps.get('regressor')).feature_importances_
        else:
            return
        
        top_idx = np.argsort(importances)[-top_n:]
        fig, ax = plt.subplots(figsize=(10, 7))
        ax.barh(range(len(top_idx)), importances[top_idx], color='steelblue')
        ax.set_yticks(range(len(top_idx)))
        ax.set_yticklabels([feature_names[i] for i in top_idx], fontsize=9)
        ax.set_title(f'{model_name} — Top {top_n} Feature Importances')
        ax.set_xlabel('Importance Score')
        plt.tight_layout()
        plt.savefig(f"reports/{model_name}_feature_importance.png", dpi=150)
        plt.close()
    except Exception as e:
        print(f"   ⚠️  Could not plot feature importance: {e}")


# ═══════════════════════════════════════════════════════════════
# MODEL 1 — EMERGENCY SEVERITY CLASSIFIER
# ═══════════════════════════════════════════════════════════════

print("\n" + "="*60)
print("MODEL 1: EMERGENCY SEVERITY CLASSIFIER")
print("="*60)

df_sev = pd.read_csv("data/severity_data.csv")
print(f"   Dataset: {df_sev.shape} | Class distribution:\n{df_sev['severity_level'].value_counts().sort_index()}")

FEATURE_COLS_SEV = [c for c in df_sev.columns if c != "severity_level"]
X_sev = df_sev[FEATURE_COLS_SEV].values
y_sev = df_sev["severity_level"].values - 1  # 0-indexed for XGBoost

X_train, X_test, y_train, y_test = train_test_split(
    X_sev, y_sev, test_size=0.20, random_state=RANDOM_STATE, stratify=y_sev
)

# Handle class imbalance with SMOTE
smote = SMOTE(random_state=RANDOM_STATE)
X_resampled, y_resampled = smote.fit_resample(X_train, y_train)
print(f"   After SMOTE: {X_resampled.shape[0]} samples")

# ── Ensemble: XGBoost + LightGBM + Random Forest (Soft Voting)
xgb_clf = XGBClassifier(
    n_estimators=300,
    max_depth=7,
    learning_rate=0.08,
    subsample=0.85,
    colsample_bytree=0.85,
    min_child_weight=3,
    reg_alpha=0.1,
    reg_lambda=1.0,
    use_label_encoder=False,
    eval_metric='mlogloss',
    random_state=RANDOM_STATE,
    n_jobs=-1
)

lgbm_clf = LGBMClassifier(
    n_estimators=300,
    max_depth=7,
    learning_rate=0.08,
    subsample=0.85,
    colsample_bytree=0.85,
    min_child_samples=20,
    reg_alpha=0.1,
    reg_lambda=1.0,
    random_state=RANDOM_STATE,
    n_jobs=-1,
    verbose=-1
)

rf_clf = RandomForestClassifier(
    n_estimators=200,
    max_depth=10,
    min_samples_split=10,
    min_samples_leaf=4,
    max_features='sqrt',
    class_weight='balanced',
    random_state=RANDOM_STATE,
    n_jobs=-1
)

voting_clf = VotingClassifier(
    estimators=[('xgb', xgb_clf), ('lgbm', lgbm_clf), ('rf', rf_clf)],
    voting='soft',
    n_jobs=-1
)

# Scaler pipeline
scaler_sev = StandardScaler()
X_resampled_scaled = scaler_sev.fit_transform(X_resampled)
X_test_scaled = scaler_sev.transform(X_test)

# ── 5-fold cross-validation (on resampled training data)
print("   Running 5-fold cross-validation...")
cv_scores = cross_val_score(voting_clf, X_resampled_scaled, y_resampled,
                             cv=StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE),
                             scoring='f1_macro', n_jobs=-1)
print(f"   CV F1-macro: {cv_scores.mean():.4f} ± {cv_scores.std():.4f}")

# ── Final training
voting_clf.fit(X_resampled_scaled, y_resampled)

# ── Calibrate probabilities for reliable confidence scores
calibrated_clf = CalibratedClassifierCV(voting_clf, method='sigmoid', cv='prefit')
calibrated_clf.fit(X_resampled_scaled, y_resampled)

y_pred = calibrated_clf.predict(X_test_scaled)
y_proba = calibrated_clf.predict_proba(X_test_scaled)

acc = accuracy_score(y_test, y_pred)
f1 = f1_score(y_test, y_pred, average='macro')
class_labels = ["Critical", "Serious", "Moderate", "Minor", "Non-Emergency"]

print(f"\n   ✅ Test Accuracy: {acc:.4f}")
print(f"   ✅ Macro F1-Score: {f1:.4f}")
print(f"\n{classification_report(y_test, y_pred, target_names=class_labels)}")

# Save artifacts
joblib.dump(calibrated_clf, "models/severity_classifier.pkl")
joblib.dump(scaler_sev, "models/severity_scaler.pkl")
joblib.dump(FEATURE_COLS_SEV, "models/severity_features.pkl")

plot_confusion_matrix(y_test, y_pred, "severity_classifier", class_labels)

save_training_report("severity_classifier", {
    "model": "VotingClassifier (XGBoost + LightGBM + RandomForest) + Calibration",
    "n_features": len(FEATURE_COLS_SEV),
    "train_samples": len(X_resampled),
    "test_samples": len(X_test),
    "cv_f1_macro_mean": float(cv_scores.mean()),
    "cv_f1_macro_std": float(cv_scores.std()),
    "test_accuracy": float(acc),
    "test_f1_macro": float(f1),
    "smote_applied": True,
    "classes": class_labels
})

print("   💾 Model saved: models/severity_classifier.pkl")


# ═══════════════════════════════════════════════════════════════
# MODEL 2 — ETA PREDICTOR
# ═══════════════════════════════════════════════════════════════

print("\n" + "="*60)
print("MODEL 2: ETA PREDICTOR")
print("="*60)

df_eta = pd.read_csv("data/eta_data.csv")
print(f"   Dataset: {df_eta.shape}")

FEATURE_COLS_ETA = [c for c in df_eta.columns if c != "actual_eta_seconds"]
X_eta = df_eta[FEATURE_COLS_ETA].values
y_eta = df_eta["actual_eta_seconds"].values

X_train, X_test, y_train, y_test = train_test_split(
    X_eta, y_eta, test_size=0.20, random_state=RANDOM_STATE
)

scaler_eta = RobustScaler()  # RobustScaler is better for data with outliers
X_train_scaled = scaler_eta.fit_transform(X_train)
X_test_scaled = scaler_eta.transform(X_test)

# ── Gradient Boosting ensemble for regression
xgb_reg = XGBRegressor(
    n_estimators=400,
    max_depth=6,
    learning_rate=0.05,
    subsample=0.80,
    colsample_bytree=0.80,
    min_child_weight=5,
    reg_alpha=0.05,
    reg_lambda=1.0,
    random_state=RANDOM_STATE,
    n_jobs=-1
)

lgbm_reg = LGBMRegressor(
    n_estimators=400,
    max_depth=6,
    learning_rate=0.05,
    subsample=0.80,
    colsample_bytree=0.80,
    min_child_samples=20,
    reg_alpha=0.05,
    reg_lambda=1.0,
    random_state=RANDOM_STATE,
    n_jobs=-1,
    verbose=-1
)

# CV with negative MAE
from sklearn.model_selection import cross_val_score as cvs
print("   Running 5-fold cross-validation (XGBoost)...")
cv_mae = -cvs(xgb_reg, X_train_scaled, y_train,
              cv=5, scoring='neg_mean_absolute_error', n_jobs=-1)
print(f"   CV MAE: {cv_mae.mean():.1f}s ± {cv_mae.std():.1f}s")

xgb_reg.fit(X_train_scaled, y_train)
lgbm_reg.fit(X_train_scaled, y_train)

# Ensemble predictions (average of both)
y_pred_xgb = xgb_reg.predict(X_test_scaled)
y_pred_lgbm = lgbm_reg.predict(X_test_scaled)
y_pred = (y_pred_xgb + y_pred_lgbm) / 2

mae = mean_absolute_error(y_test, y_pred)
rmse = np.sqrt(mean_squared_error(y_test, y_pred))
r2 = r2_score(y_test, y_pred)

print(f"\n   ✅ Test MAE:  {mae:.1f} seconds ({mae/60:.2f} minutes)")
print(f"   ✅ Test RMSE: {rmse:.1f} seconds")
print(f"   ✅ Test R²:   {r2:.4f}")

# Percentage within ±60 seconds
within_60s = np.mean(np.abs(y_test - y_pred) < 60) * 100
print(f"   ✅ Predictions within ±60s: {within_60s:.1f}%")

# Feature importance plot
plot_feature_importance(xgb_reg, FEATURE_COLS_ETA, "eta_predictor")

# Save
joblib.dump(xgb_reg, "models/eta_model_xgb.pkl")
joblib.dump(lgbm_reg, "models/eta_model_lgbm.pkl")
joblib.dump(scaler_eta, "models/eta_scaler.pkl")
joblib.dump(FEATURE_COLS_ETA, "models/eta_features.pkl")

save_training_report("eta_predictor", {
    "model": "XGBoost + LightGBM ensemble regressor",
    "n_features": len(FEATURE_COLS_ETA),
    "cv_mae_seconds_mean": float(cv_mae.mean()),
    "cv_mae_seconds_std": float(cv_mae.std()),
    "test_mae_seconds": float(mae),
    "test_rmse_seconds": float(rmse),
    "test_r2": float(r2),
    "pct_within_60s": float(within_60s)
})

print("   💾 Model saved: models/eta_model_xgb.pkl + eta_model_lgbm.pkl")


# ═══════════════════════════════════════════════════════════════
# MODEL 3 — HOSPITAL RECOMMENDATION ENGINE
# ═══════════════════════════════════════════════════════════════

print("\n" + "="*60)
print("MODEL 3: HOSPITAL RECOMMENDATION ENGINE")
print("="*60)

df_hosp = pd.read_csv("data/hospital_data.csv")
print(f"   Dataset: {df_hosp.shape}")

FEATURE_COLS_HOSP = [c for c in df_hosp.columns if c != "match_score"]
X_hosp = df_hosp[FEATURE_COLS_HOSP].values
y_hosp = df_hosp["match_score"].values

X_train, X_test, y_train, y_test = train_test_split(
    X_hosp, y_hosp, test_size=0.20, random_state=RANDOM_STATE
)

scaler_hosp = StandardScaler()
X_train_scaled = scaler_hosp.fit_transform(X_train)
X_test_scaled = scaler_hosp.transform(X_test)

hosp_model = XGBRegressor(
    n_estimators=300,
    max_depth=5,
    learning_rate=0.07,
    subsample=0.85,
    colsample_bytree=0.85,
    min_child_weight=4,
    random_state=RANDOM_STATE,
    n_jobs=-1
)

print("   Running 5-fold cross-validation...")
cv_mae_h = -cross_val_score(hosp_model, X_train_scaled, y_train,
                             cv=5, scoring='neg_mean_absolute_error', n_jobs=-1)
print(f"   CV MAE: {cv_mae_h.mean():.2f} ± {cv_mae_h.std():.2f} score points")

hosp_model.fit(X_train_scaled, y_train)
y_pred_h = hosp_model.predict(X_test_scaled)
y_pred_h = np.clip(y_pred_h, 0, 100)

mae_h = mean_absolute_error(y_test, y_pred_h)
r2_h = r2_score(y_test, y_pred_h)

print(f"\n   ✅ Test MAE: {mae_h:.2f} score points")
print(f"   ✅ Test R²:  {r2_h:.4f}")

# Top-3 recommendation accuracy (rank agreement)
# For every group of 5 random hospitals, check if model picks the same top-1 as ground truth
top1_correct = 0
n_groups = 5000
for _ in range(n_groups):
    idxs = np.random.choice(len(y_test), 5, replace=False)
    true_best = idxs[np.argmax(y_test[idxs])]
    pred_best = idxs[np.argmax(y_pred_h[idxs])]
    top1_correct += int(true_best == pred_best)

ranking_acc = top1_correct / n_groups * 100
print(f"   ✅ Top-1 Ranking Accuracy: {ranking_acc:.1f}%")

plot_feature_importance(hosp_model, FEATURE_COLS_HOSP, "hospital_recommender")

joblib.dump(hosp_model, "models/hospital_recommender.pkl")
joblib.dump(scaler_hosp, "models/hospital_scaler.pkl")
joblib.dump(FEATURE_COLS_HOSP, "models/hospital_features.pkl")

save_training_report("hospital_recommender", {
    "model": "XGBoost Regressor",
    "n_features": len(FEATURE_COLS_HOSP),
    "cv_mae_mean": float(cv_mae_h.mean()),
    "test_mae": float(mae_h),
    "test_r2": float(r2_h),
    "top1_ranking_accuracy_pct": float(ranking_acc)
})

print("   💾 Model saved: models/hospital_recommender.pkl")


# ═══════════════════════════════════════════════════════════════
# MODEL 4 — TRAFFIC CONGESTION PREDICTOR
# ═══════════════════════════════════════════════════════════════

print("\n" + "="*60)
print("MODEL 4: TRAFFIC CONGESTION PREDICTOR")
print("="*60)

df_traf = pd.read_csv("data/traffic_data.csv")
print(f"   Dataset: {df_traf.shape}")

FEATURE_COLS_TRAF = [c for c in df_traf.columns
                     if c not in ["congestion_level", "avg_speed_kmh", "lat", "lng"]]
X_traf = df_traf[FEATURE_COLS_TRAF].values
y_traf = df_traf["congestion_level"].values

X_train, X_test, y_train, y_test = train_test_split(
    X_traf, y_traf, test_size=0.20, random_state=RANDOM_STATE
)

scaler_traf = StandardScaler()
X_train_s = scaler_traf.fit_transform(X_train)
X_test_s = scaler_traf.transform(X_test)

traf_model = LGBMRegressor(
    n_estimators=400,
    max_depth=6,
    learning_rate=0.06,
    subsample=0.85,
    colsample_bytree=0.85,
    min_child_samples=20,
    random_state=RANDOM_STATE,
    n_jobs=-1,
    verbose=-1
)

traf_model.fit(X_train_s, y_train)
y_pred_t = np.clip(traf_model.predict(X_test_s), 0, 1)

mae_t = mean_absolute_error(y_test, y_pred_t)
r2_t = r2_score(y_test, y_pred_t)

print(f"   ✅ Test MAE: {mae_t:.4f} congestion units")
print(f"   ✅ Test R²:  {r2_t:.4f}")

joblib.dump(traf_model, "models/traffic_predictor.pkl")
joblib.dump(scaler_traf, "models/traffic_scaler.pkl")
joblib.dump(FEATURE_COLS_TRAF, "models/traffic_features.pkl")

save_training_report("traffic_predictor", {
    "model": "LightGBM Regressor",
    "n_features": len(FEATURE_COLS_TRAF),
    "test_mae": float(mae_t),
    "test_r2": float(r2_t)
})

print("   💾 Model saved: models/traffic_predictor.pkl")


# ═══════════════════════════════════════════════════════════════
# MODEL 5 — DEMAND HOTSPOT FORECASTER (LSTM)
# ═══════════════════════════════════════════════════════════════

print("\n" + "="*60)
print("MODEL 5: DEMAND HOTSPOT FORECASTER (LSTM)")
print("="*60)

import tensorflow as tf
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense, Dropout, BatchNormalization
from tensorflow.keras.callbacks import EarlyStopping, ReduceLROnPlateau, ModelCheckpoint
from tensorflow.keras.optimizers import Adam
from sklearn.preprocessing import MinMaxScaler

tf.random.set_seed(RANDOM_STATE)

df_hot = pd.read_csv("data/hotspot_data.csv")

LOOKBACK = 48       # Use 48 hours of history to predict next hour
FORECAST_STEPS = 1  # Predict next 1 hour

def create_sequences(data, lookback):
    X_seq, y_seq = [], []
    for i in range(lookback, len(data)):
        X_seq.append(data[i - lookback:i])
        y_seq.append(data[i])
    return np.array(X_seq), np.array(y_seq)

all_X, all_y = [], []

for zone_id in df_hot['zone_id'].unique():
    zone_data = df_hot[df_hot['zone_id'] == zone_id].sort_values('datetime')
    
    features = zone_data[['incident_count', 'hour', 'day_of_week', 'month', 'is_rush_hour']].values
    
    scaler_zone = MinMaxScaler()
    features_scaled = scaler_zone.fit_transform(features)
    
    X_z, y_z = create_sequences(features_scaled, LOOKBACK)
    all_X.append(X_z)
    all_y.append(y_z[:, 0])   # Predict incident_count only (first column)

X_lstm = np.vstack(all_X)
y_lstm = np.concatenate(all_y)

# Train/test split (time-series aware: don't shuffle)
split = int(0.80 * len(X_lstm))
X_tr, X_te = X_lstm[:split], X_lstm[split:]
y_tr, y_te = y_lstm[:split], y_lstm[split:]

print(f"   LSTM Input shape: {X_tr.shape} | Output: {y_tr.shape}")

# ── LSTM Architecture
model_lstm = Sequential([
    LSTM(128, return_sequences=True, input_shape=(LOOKBACK, X_lstm.shape[2])),
    BatchNormalization(),
    Dropout(0.25),
    LSTM(64, return_sequences=True),
    BatchNormalization(),
    Dropout(0.20),
    LSTM(32, return_sequences=False),
    Dropout(0.15),
    Dense(32, activation='relu'),
    Dense(16, activation='relu'),
    Dense(1, activation='relu')   # Incident count ≥ 0
], name="hotspot_forecaster")

model_lstm.compile(
    optimizer=Adam(learning_rate=0.001),
    loss='huber',                   # Huber loss robust to outliers
    metrics=['mae']
)

model_lstm.summary()

callbacks = [
    EarlyStopping(monitor='val_loss', patience=10, restore_best_weights=True, verbose=1),
    ReduceLROnPlateau(monitor='val_loss', factor=0.5, patience=5, min_lr=1e-6, verbose=1),
    ModelCheckpoint("models/hotspot_lstm_best.h5", monitor='val_loss', save_best_only=True, verbose=1)
]

history = model_lstm.fit(
    X_tr, y_tr,
    validation_split=0.15,
    epochs=80,
    batch_size=256,
    callbacks=callbacks,
    verbose=1
)

# ── Evaluation
y_pred_lstm = model_lstm.predict(X_te).flatten()
mae_lstm = mean_absolute_error(y_te, y_pred_lstm)
rmse_lstm = np.sqrt(mean_squared_error(y_te, y_pred_lstm))

print(f"\n   ✅ LSTM Test MAE:  {mae_lstm:.4f} incidents/hour")
print(f"   ✅ LSTM Test RMSE: {rmse_lstm:.4f}")

# Plot training history
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
ax1.plot(history.history['loss'], label='Train Loss')
ax1.plot(history.history['val_loss'], label='Val Loss')
ax1.set_title('LSTM Training Loss')
ax1.set_xlabel('Epoch')
ax1.legend()

ax2.plot(history.history['mae'], label='Train MAE')
ax2.plot(history.history['val_mae'], label='Val MAE')
ax2.set_title('LSTM Training MAE')
ax2.set_xlabel('Epoch')
ax2.legend()

plt.tight_layout()
plt.savefig("reports/hotspot_lstm_training.png", dpi=150)
plt.close()

model_lstm.save("models/hotspot_lstm.h5")

save_training_report("hotspot_lstm", {
    "model": "Bidirectional LSTM (128→64→32) + Dense",
    "lookback_hours": LOOKBACK,
    "test_mae": float(mae_lstm),
    "test_rmse": float(rmse_lstm),
    "epochs_trained": len(history.history['loss'])
})

print("   💾 Model saved: models/hotspot_lstm.h5")

print("\n" + "="*60)
print("🎉 ALL 5 MODELS TRAINED SUCCESSFULLY!")
print("="*60)
print("\nModels saved in models/")
print("Training reports saved in reports/")
```

---

## 7. Backend API (FastAPI)

### 7.1 Project Structure
```
backend/
├── main.py              ← App entry point, middleware, routers
├── config.py            ← Environment config
├── database.py          ← DB session setup
├── models.py            ← SQLAlchemy ORM models (from Section 4)
├── schemas.py           ← Pydantic request/response schemas
├── auth.py              ← JWT authentication
├── routers/
│   ├── emergencies.py   ← Emergency CRUD + AI dispatch trigger
│   ├── ambulances.py    ← Ambulance CRUD + GPS update
│   ├── hospitals.py     ← Hospital CRUD + bed management
│   ├── dispatch.py      ← Dispatch orchestration endpoint
│   ├── analytics.py     ← Reports, KPIs, heatmaps
│   └── users.py         ← User management
├── services/
│   ├── ai_inference.py  ← Load models + inference functions
│   ├── dispatch_engine.py ← Core dispatch logic
│   ├── maps_service.py  ← Google Maps API wrapper
│   └── notifications.py ← SMS/push simulation
└── socket_manager.py    ← Socket.IO events
```

### 7.2 main.py
```python
# backend/main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import socketio
from routers import emergencies, ambulances, hospitals, dispatch, analytics, users
from socket_manager import sio
from database import engine, Base

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Smart Emergency Response API",
    description="AI-powered ambulance coordination system",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register REST routers
app.include_router(emergencies.router, prefix="/api/emergencies", tags=["Emergencies"])
app.include_router(ambulances.router, prefix="/api/ambulances", tags=["Ambulances"])
app.include_router(hospitals.router, prefix="/api/hospitals", tags=["Hospitals"])
app.include_router(dispatch.router, prefix="/api/dispatch", tags=["Dispatch"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["Analytics"])
app.include_router(users.router, prefix="/api/users", tags=["Users"])

# Mount Socket.IO on the ASGI app
socket_app = socketio.ASGIApp(sio, other_asgi_app=app)

@app.get("/health")
def health_check():
    return {"status": "ok", "version": "1.0.0"}
```

### 7.3 AI Inference Service
```python
# backend/services/ai_inference.py
"""
Loads all trained model files and exposes inference functions.
Call these from your API routes — never retrain inside a request.
"""

import numpy as np
import joblib
import json
import os
import tensorflow as tf

MODEL_DIR = os.path.join(os.path.dirname(__file__), "../../ai/models")

# ── Load all models once at startup
_sev_clf = joblib.load(f"{MODEL_DIR}/severity_classifier.pkl")
_sev_scaler = joblib.load(f"{MODEL_DIR}/severity_scaler.pkl")
_sev_features = joblib.load(f"{MODEL_DIR}/severity_features.pkl")

_eta_xgb = joblib.load(f"{MODEL_DIR}/eta_model_xgb.pkl")
_eta_lgbm = joblib.load(f"{MODEL_DIR}/eta_model_lgbm.pkl")
_eta_scaler = joblib.load(f"{MODEL_DIR}/eta_scaler.pkl")
_eta_features = joblib.load(f"{MODEL_DIR}/eta_features.pkl")

_hosp_model = joblib.load(f"{MODEL_DIR}/hospital_recommender.pkl")
_hosp_scaler = joblib.load(f"{MODEL_DIR}/hospital_scaler.pkl")
_hosp_features = joblib.load(f"{MODEL_DIR}/hospital_features.pkl")

_traf_model = joblib.load(f"{MODEL_DIR}/traffic_predictor.pkl")
_traf_scaler = joblib.load(f"{MODEL_DIR}/traffic_scaler.pkl")
_traf_features = joblib.load(f"{MODEL_DIR}/traffic_features.pkl")

_lstm_model = tf.keras.models.load_model(f"{MODEL_DIR}/hotspot_lstm.h5")

SEVERITY_LABELS = {1: "Critical", 2: "Serious", 3: "Moderate", 4: "Minor", 5: "Non-Emergency"}
SEVERITY_COLORS = {1: "#FF1744", 2: "#FF6D00", 3: "#FFD600", 4: "#00E676", 5: "#00B0FF"}

ALL_SYMPTOMS = [
    "chest_pain", "shortness_of_breath", "unconscious", "seizure",
    "major_bleeding", "stroke_symptoms", "cardiac_arrest", "severe_burns",
    "spinal_injury", "head_trauma", "anaphylaxis", "diabetic_emergency",
    "fracture", "moderate_bleeding", "abdominal_pain", "vomiting",
    "dizziness", "high_fever", "minor_cut", "sprain", "headache",
    "anxiety", "nausea", "cough", "back_pain"
]

def predict_severity(patient_data: dict) -> dict:
    """
    Input: patient_data dict with keys matching severity features
    Output: {"severity_level": int, "label": str, "confidence": float, "color": str}
    """
    # Build feature vector
    symptom_flags = {s: int(s in patient_data.get("symptoms", [])) for s in ALL_SYMPTOMS}
    
    feature_dict = {
        "age": patient_data.get("age", 30),
        "gender": int(patient_data.get("gender", "male") == "male"),
        "pulse_rate": patient_data.get("pulse_rate", 75),
        "bp_systolic": patient_data.get("blood_pressure_systolic", 120),
        "spo2": patient_data.get("spo2", 98.0),
        "respiratory_rate": patient_data.get("respiratory_rate", 16),
        "gcs_score": patient_data.get("gcs_score", 15),
        "num_symptoms": len(patient_data.get("symptoms", [])),
        "is_elderly": int(patient_data.get("age", 30) > 65),
        "is_pediatric": int(patient_data.get("age", 30) < 12),
        **symptom_flags
    }
    
    X = np.array([[feature_dict[f] for f in _sev_features]])
    X_scaled = _sev_scaler.transform(X)
    
    pred_class = int(_sev_clf.predict(X_scaled)[0])
    proba = _sev_clf.predict_proba(X_scaled)[0]
    
    severity_level = pred_class + 1  # back to 1-indexed
    confidence = float(proba[pred_class])
    
    return {
        "severity_level": severity_level,
        "label": SEVERITY_LABELS[severity_level],
        "confidence": round(confidence, 3),
        "color": SEVERITY_COLORS[severity_level],
        "all_probabilities": {SEVERITY_LABELS[i+1]: round(float(p), 3) for i, p in enumerate(proba)}
    }


def predict_eta(distance_km: float, context: dict) -> dict:
    """
    Returns predicted ETA in seconds + minutes.
    context: hour_of_day, day_of_week, congestion_level, road_type (0–3),
             weather (0–4), ambulance_type (0–2), severity_level (1–5)
    """
    from datetime import datetime
    now = datetime.now()
    hour = context.get("hour_of_day", now.hour)
    dow = context.get("day_of_week", now.weekday())
    
    feature_dict = {
        "distance_km": distance_km,
        "hour_of_day": hour,
        "day_of_week": dow,
        "is_rush_hour": int(dow < 5 and (8 <= hour <= 10 or 17 <= hour <= 20)),
        "is_night": int(hour >= 22 or hour <= 5),
        "is_weekend": int(dow >= 5),
        "congestion_level": context.get("congestion_level", 0.3),
        "road_type": context.get("road_type", 2),
        "weather": context.get("weather", 0),
        "ambulance_type": context.get("ambulance_type", 0),
        "severity_level": context.get("severity_level", 3)
    }
    
    X = np.array([[feature_dict[f] for f in _eta_features]])
    X_scaled = _eta_scaler.transform(X)
    
    pred_xgb = float(_eta_xgb.predict(X_scaled)[0])
    pred_lgbm = float(_eta_lgbm.predict(X_scaled)[0])
    eta_seconds = max(30, (pred_xgb + pred_lgbm) / 2)
    
    return {
        "eta_seconds": round(eta_seconds),
        "eta_minutes": round(eta_seconds / 60, 1)
    }


def score_hospital(patient_info: dict, hospital_info: dict) -> float:
    """
    Returns a match score 0–100 for routing a patient to a hospital.
    """
    SPECIALTIES = ["cardiac", "trauma", "stroke", "pediatric", "burns", "orthopedic", "general"]
    
    patient_need = patient_info.get("specialty_need", "general")
    hosp_specialties = hospital_info.get("specialties", [])
    
    feature_dict = {
        "severity_level": patient_info.get("severity_level", 3),
        "patient_specialty_need": SPECIALTIES.index(patient_need) if patient_need in SPECIALTIES else 6,
        "has_needed_specialty": int(patient_need in hosp_specialties),
        "hospital_specialties_count": len(hosp_specialties),
        "distance_km": hospital_info.get("distance_km", 5.0),
        "beds_icu_available": hospital_info.get("available_beds_icu", 0),
        "beds_trauma_available": hospital_info.get("available_beds_trauma", 0),
        "beds_general_available": hospital_info.get("available_beds_general", 0),
        "er_wait_minutes": hospital_info.get("er_wait_minutes", 30),
        "is_diversion": int(hospital_info.get("is_diversion", False)),
        "total_occupied_pct": hospital_info.get("occupied_pct", 0.5)
    }
    
    X = np.array([[feature_dict[f] for f in _hosp_features]])
    X_scaled = _hosp_scaler.transform(X)
    score = float(_hosp_model.predict(X_scaled)[0])
    return round(max(0, min(100, score)), 2)


def predict_traffic(zone_id: int, hour: int, day_of_week: int, month: int) -> dict:
    """Predict congestion level for a zone at a specific time."""
    feature_dict = {
        "zone_id": zone_id,
        "hour_of_day": hour,
        "day_of_week": day_of_week,
        "month": month,
        "is_rush_hour": int(day_of_week < 5 and (8 <= hour <= 10 or 17 <= hour <= 20)),
        "is_weekend": int(day_of_week >= 5),
        "zone_density_level": 0.5  # default; override with real data in production
    }
    
    X = np.array([[feature_dict[f] for f in _traf_features]])
    X_scaled = _traf_scaler.transform(X)
    congestion = float(np.clip(_traf_model.predict(X_scaled)[0], 0, 1))
    
    speed_kmh = max(10, 70 * (1 - congestion * 0.8))
    level = "Clear" if congestion < 0.3 else ("Moderate" if congestion < 0.6 else ("Heavy" if congestion < 0.85 else "Standstill"))
    
    return {
        "congestion_level": round(congestion, 3),
        "level_label": level,
        "estimated_speed_kmh": round(speed_kmh, 1)
    }
```

### 7.4 Dispatch Engine
```python
# backend/services/dispatch_engine.py
"""
Core orchestration: given an emergency, find the best ambulance + hospital combination.
"""

import math
from services.ai_inference import predict_eta, score_hospital, predict_traffic
from datetime import datetime

def haversine_distance(lat1, lng1, lat2, lng2) -> float:
    """Returns distance in km between two GPS coordinates."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


async def find_best_dispatch(emergency: dict, available_ambulances: list, hospitals: list) -> dict:
    """
    Returns the optimal dispatch recommendation:
    {
        "ambulance": {...},
        "hospital": {...},
        "predicted_eta_seconds": int,
        "hospital_score": float,
        "ranked_ambulances": [...],
        "ranked_hospitals": [...]
    }
    """
    now = datetime.now()
    severity = emergency.get("severity_level", 3)
    
    # ── Step 1: Score + rank ambulances by weighted ETA + type match
    ambulance_scores = []
    for amb in available_ambulances:
        if amb["status"] != "available":
            continue
        
        dist_km = haversine_distance(
            emergency["lat"], emergency["lng"],
            amb["current_lat"], amb["current_lng"]
        )
        
        # Get predicted traffic at ambulance's zone
        traffic_info = predict_traffic(
            zone_id=0,  # In production: resolve zone from lat/lng
            hour=now.hour,
            day_of_week=now.weekday(),
            month=now.month
        )
        
        eta_info = predict_eta(dist_km, {
            "congestion_level": traffic_info["congestion_level"],
            "severity_level": severity,
            "ambulance_type": {"bls": 0, "als": 1, "icu": 2}.get(amb["type"], 0)
        })
        
        # Type matching bonus: Critical cases need ALS or ICU
        type_bonus = 0
        if severity <= 2 and amb["type"] in ["als", "icu"]:
            type_bonus = -30   # Subtract from ETA equivalent (prioritize)
        elif severity <= 2 and amb["type"] == "bls":
            type_bonus = +60   # Penalty for sending wrong type to critical
        
        effective_eta = eta_info["eta_seconds"] + type_bonus
        
        ambulance_scores.append({
            **amb,
            "distance_km": round(dist_km, 2),
            "predicted_eta_seconds": eta_info["eta_seconds"],
            "effective_score_eta": effective_eta,
            "traffic_congestion": traffic_info["congestion_level"]
        })
    
    ranked_ambulances = sorted(ambulance_scores, key=lambda x: x["effective_score_eta"])
    best_ambulance = ranked_ambulances[0] if ranked_ambulances else None
    
    # ── Step 2: Score + rank hospitals
    # Determine specialty need from severity + (in production: symptom analysis)
    specialty_map = {1: "trauma", 2: "cardiac", 3: "general", 4: "general", 5: "general"}
    specialty_need = emergency.get("specialty_need", specialty_map.get(severity, "general"))
    
    hospital_scores = []
    for hosp in hospitals:
        if hosp.get("is_diversion") and severity > 2:
            continue  # Skip diverted hospitals for non-critical
        
        dist_km = haversine_distance(
            emergency["lat"], emergency["lng"],
            hosp["lat"], hosp["lng"]
        )
        
        score = score_hospital(
            patient_info={"severity_level": severity, "specialty_need": specialty_need},
            hospital_info={**hosp, "distance_km": dist_km}
        )
        
        hospital_scores.append({**hosp, "distance_km": round(dist_km, 2), "match_score": score})
    
    ranked_hospitals = sorted(hospital_scores, key=lambda x: -x["match_score"])
    best_hospital = ranked_hospitals[0] if ranked_hospitals else None
    
    return {
        "ambulance": best_ambulance,
        "hospital": best_hospital,
        "predicted_eta_seconds": best_ambulance["predicted_eta_seconds"] if best_ambulance else None,
        "hospital_score": best_hospital["match_score"] if best_hospital else None,
        "ranked_ambulances": ranked_ambulances[:5],
        "ranked_hospitals": ranked_hospitals[:5]
    }
```

---

## 8. Real-Time Engine (Socket.IO)

```python
# backend/socket_manager.py

import socketio
import asyncio
import random
import math
from datetime import datetime

sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins=['http://localhost:3000']
)

# In-memory ambulance GPS positions (production: use Redis)
ambulance_positions = {}

@sio.event
async def connect(sid, environ, auth):
    print(f"🔌 Client connected: {sid}")
    await sio.emit("connection_ack", {"status": "connected", "timestamp": datetime.now().isoformat()}, to=sid)

@sio.event
async def disconnect(sid):
    print(f"❌ Client disconnected: {sid}")

@sio.event
async def join_room(sid, data):
    """Clients join rooms by role: dispatcher, hospital_{id}, ambulance_{id}"""
    room = data.get("room", "dispatcher")
    await sio.enter_room(sid, room)
    await sio.emit("room_joined", {"room": room}, to=sid)

@sio.event
async def ambulance_gps_update(sid, data):
    """
    Ambulance driver app sends GPS updates.
    data: { ambulance_id, lat, lng, status, speed_kmh }
    """
    amb_id = data["ambulance_id"]
    ambulance_positions[amb_id] = {
        **data,
        "timestamp": datetime.now().isoformat()
    }
    # Broadcast to all dispatchers
    await sio.emit("ambulance_moved", data, room="dispatcher")

@sio.event
async def new_emergency_alert(sid, data):
    """Dispatcher broadcasts new emergency to all connected clients."""
    await sio.emit("emergency_incoming", data, room="dispatcher")

async def simulate_ambulance_movement(ambulance_id: int, start_lat: float, start_lng: float,
                                       end_lat: float, end_lng: float, steps: int = 30):
    """
    Simulate an ambulance moving from point A to B over `steps` socket emissions.
    Call this in a background task after dispatch.
    """
    for i in range(steps + 1):
        t = i / steps
        lat = start_lat + (end_lat - start_lat) * t
        lng = start_lng + (end_lng - start_lng) * t
        # Add small random jitter to simulate real GPS noise
        lat += random.uniform(-0.0002, 0.0002)
        lng += random.uniform(-0.0002, 0.0002)
        
        data = {
            "ambulance_id": ambulance_id,
            "lat": round(lat, 6),
            "lng": round(lng, 6),
            "progress_pct": round(t * 100),
            "speed_kmh": round(random.uniform(40, 80), 1),
            "timestamp": datetime.now().isoformat()
        }
        ambulance_positions[ambulance_id] = data
        await sio.emit("ambulance_moved", data, room="dispatcher")
        await asyncio.sleep(2)   # Update every 2 seconds
    
    # On arrival
    await sio.emit("ambulance_arrived", {"ambulance_id": ambulance_id}, room="dispatcher")
```

---

## 9. Frontend Dashboard (React)

### 9.1 App Structure
```
frontend/src/
├── App.jsx                     ← Router + auth guard
├── store/
│   ├── useEmergencyStore.js    ← Zustand: active emergencies
│   ├── useAmbulanceStore.js    ← Zustand: ambulance fleet
│   └── useSocketStore.js       ← WebSocket connection state
├── pages/
│   ├── Login.jsx
│   ├── DispatcherDashboard.jsx ← Main map view + emergency queue
│   ├── HospitalPortal.jsx      ← Bed management, incoming patients
│   ├── Analytics.jsx           ← KPI charts, heatmaps
│   └── AmbulanceTracker.jsx    ← Paramedic mobile view
├── components/
│   ├── EmergencyForm.jsx       ← New emergency intake with AI triage
│   ├── EmergencyCard.jsx       ← Priority-colored emergency in queue
│   ├── AmbulanceMarker.jsx     ← Custom Google Maps marker
│   ├── DispatchModal.jsx       ← Confirm dispatch with AI recommendations
│   ├── HospitalCard.jsx        ← Live bed counts, specialty badges
│   ├── SeverityBadge.jsx       ← Color-coded severity chip
│   ├── ETATimer.jsx            ← Countdown timer with live updates
│   ├── StatsCard.jsx           ← KPI metric card
│   └── Sidebar.jsx             ← Navigation
├── hooks/
│   ├── useSocket.js            ← Socket.IO connection hook
│   ├── useGoogleMaps.js        ← Maps API initialization
│   └── useAI.js                ← API calls to AI endpoints
└── utils/
    ├── distance.js             ← Haversine formula (JS version)
    ├── formatters.js           ← Time, distance, score formatters
    └── colors.js               ← Severity/status color constants
```

### 9.2 Key Pages

#### DispatcherDashboard.jsx (Core Page)
```jsx
// src/pages/DispatcherDashboard.jsx
import { useEffect, useState } from "react";
import { GoogleMap, useLoadScript, Marker, Polyline, InfoWindow } from "@react-google-maps/api";
import { useEmergencyStore } from "../store/useEmergencyStore";
import { useAmbulanceStore } from "../store/useAmbulanceStore";
import { useSocket } from "../hooks/useSocket";
import EmergencyCard from "../components/EmergencyCard";
import DispatchModal from "../components/DispatchModal";
import EmergencyForm from "../components/EmergencyForm";
import ETATimer from "../components/ETATimer";
import axios from "axios";
import toast from "react-hot-toast";

const MAP_CENTER = { lat: 19.0760, lng: 72.8777 }; // Mumbai — change to your city

export default function DispatcherDashboard() {
  const { isLoaded } = useLoadScript({ googleMapsApiKey: process.env.REACT_APP_GOOGLE_MAPS_KEY });
  const { emergencies, setEmergencies } = useEmergencyStore();
  const { ambulances, updateAmbulancePosition } = useAmbulanceStore();
  const { socket } = useSocket();
  
  const [selectedEmergency, setSelectedEmergency] = useState(null);
  const [showDispatchModal, setShowDispatchModal] = useState(false);
  const [dispatchRecommendation, setDispatchRecommendation] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [activeRoutes, setActiveRoutes] = useState([]);

  // Load initial data
  useEffect(() => {
    axios.get("/api/emergencies?status=pending,dispatched").then(r => setEmergencies(r.data));
  }, []);

  // Real-time socket events
  useEffect(() => {
    if (!socket) return;
    socket.emit("join_room", { room: "dispatcher" });
    
    socket.on("ambulance_moved", (data) => {
      updateAmbulancePosition(data.ambulance_id, data.lat, data.lng);
    });
    
    socket.on("emergency_incoming", (data) => {
      setEmergencies(prev => [data, ...prev]);
      toast.error(`🚨 NEW EMERGENCY — ${data.severity_label}`, { duration: 8000 });
    });
    
    return () => { socket.off("ambulance_moved"); socket.off("emergency_incoming"); };
  }, [socket]);

  const handleDispatch = async (emergency) => {
    setSelectedEmergency(emergency);
    const res = await axios.post(`/api/dispatch/recommend`, { emergency_id: emergency.id });
    setDispatchRecommendation(res.data);
    setShowDispatchModal(true);
  };

  const confirmDispatch = async (ambulanceId, hospitalId) => {
    const res = await axios.post("/api/dispatch/confirm", {
      emergency_id: selectedEmergency.id,
      ambulance_id: ambulanceId,
      hospital_id: hospitalId
    });
    setActiveRoutes(prev => [...prev, res.data.route_polyline]);
    toast.success("✅ Ambulance dispatched!");
    setShowDispatchModal(false);
  };

  if (!isLoaded) return <div className="loading">Loading Map...</div>;

  return (
    <div className="dashboard-container">
      {/* LEFT: Emergency Queue */}
      <aside className="emergency-queue">
        <div className="queue-header">
          <h2>Emergency Queue</h2>
          <span className="badge">{emergencies.filter(e => e.status === "pending").length} PENDING</span>
          <button onClick={() => setShowForm(true)} className="btn-new">+ New Emergency</button>
        </div>
        
        <div className="queue-list">
          {emergencies
            .sort((a, b) => a.predicted_severity - b.predicted_severity)  // Critical first
            .map(e => (
              <EmergencyCard
                key={e.id}
                emergency={e}
                onDispatch={() => handleDispatch(e)}
                isSelected={selectedEmergency?.id === e.id}
              />
            ))}
        </div>
      </aside>

      {/* CENTER: Live Map */}
      <main className="map-area">
        <GoogleMap
          mapContainerStyle={{ width: "100%", height: "100%" }}
          center={MAP_CENTER}
          zoom={13}
          options={{
            styles: darkMapStyle,  // Custom dark theme (see below)
            disableDefaultUI: false,
            zoomControl: true,
          }}
        >
          {/* Emergency markers (red pulsing) */}
          {emergencies.map(e => (
            <Marker
              key={`emg-${e.id}`}
              position={{ lat: e.location_lat, lng: e.location_lng }}
              icon={{ url: `/icons/emergency_sev${e.predicted_severity}.png`, scaledSize: new window.google.maps.Size(40, 40) }}
              onClick={() => setSelectedEmergency(e)}
            />
          ))}

          {/* Ambulance markers (moving) */}
          {ambulances.map(a => (
            <Marker
              key={`amb-${a.id}`}
              position={{ lat: a.current_lat, lng: a.current_lng }}
              icon={{ url: `/icons/ambulance_${a.status}.png`, scaledSize: new window.google.maps.Size(36, 36) }}
              title={`${a.registration_number} — ${a.status}`}
            />
          ))}

          {/* Active routes (polylines) */}
          {activeRoutes.map((route, i) => (
            <Polyline
              key={i}
              path={window.google.maps.geometry.encoding.decodePath(route)}
              options={{ strokeColor: "#00E5FF", strokeWeight: 4, strokeOpacity: 0.85 }}
            />
          ))}
        </GoogleMap>

        {/* Map overlay: quick stats bar */}
        <div className="map-stats-bar">
          <StatChip label="Available" value={ambulances.filter(a => a.status === "available").length} color="green" />
          <StatChip label="En Route" value={ambulances.filter(a => a.status === "en_route").length} color="orange" />
          <StatChip label="Hospitals OK" value="7/9" color="blue" />
          <StatChip label="Avg ETA" value="8.2 min" color="purple" />
        </div>
      </main>

      {/* RIGHT: Hospital Status Panel */}
      <aside className="hospital-panel">
        <h2>Hospital Status</h2>
        <HospitalStatusList />
      </aside>

      {/* Modals */}
      {showForm && <EmergencyForm onClose={() => setShowForm(false)} />}
      {showDispatchModal && (
        <DispatchModal
          emergency={selectedEmergency}
          recommendation={dispatchRecommendation}
          onConfirm={confirmDispatch}
          onClose={() => setShowDispatchModal(false)}
        />
      )}
    </div>
  );
}
```

### 9.3 EmergencyForm.jsx (AI Triage Integration)
```jsx
// src/components/EmergencyForm.jsx
import { useState } from "react";
import axios from "axios";
import SeverityBadge from "./SeverityBadge";
import toast from "react-hot-toast";

const SYMPTOMS_LIST = [
  "chest_pain", "shortness_of_breath", "unconscious", "seizure",
  "major_bleeding", "stroke_symptoms", "cardiac_arrest", "severe_burns",
  "spinal_injury", "head_trauma", "anaphylaxis", "diabetic_emergency",
  "fracture", "moderate_bleeding", "abdominal_pain", "vomiting",
  "dizziness", "high_fever", "minor_cut", "sprain", "headache",
  "anxiety", "nausea", "cough", "back_pain"
];

export default function EmergencyForm({ onClose }) {
  const [form, setForm] = useState({
    patient_name: "", patient_age: "", patient_gender: "male",
    phone: "", location_address: "", location_lat: "", location_lng: "",
    symptoms: [], chief_complaint: "",
    pulse_rate: "", bp_systolic: "", spo2: "", respiratory_rate: "", gcs_score: "",
    is_multi_casualty: false, casualty_count: 1
  });
  
  const [aiResult, setAiResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const runAITriage = async () => {
    if (form.symptoms.length === 0) { toast.error("Select at least one symptom"); return; }
    setLoading(true);
    try {
      const res = await axios.post("/api/emergencies/triage", form);
      setAiResult(res.data);
      toast.success("AI triage complete");
    } catch {
      toast.error("Triage failed");
    }
    setLoading(false);
  };

  const handleSubmit = async () => {
    if (!aiResult) { toast.error("Run AI triage first"); return; }
    await axios.post("/api/emergencies", { ...form, predicted_severity: aiResult.severity_level });
    toast.success("Emergency logged!");
    onClose();
  };

  const toggleSymptom = (s) => {
    setForm(prev => ({
      ...prev,
      symptoms: prev.symptoms.includes(s)
        ? prev.symptoms.filter(x => x !== s)
        : [...prev.symptoms, s]
    }));
  };

  return (
    <div className="modal-overlay">
      <div className="emergency-form-modal">
        <h2>🆘 New Emergency Intake</h2>
        
        <section>
          <h3>Patient Details</h3>
          <div className="form-row">
            <input placeholder="Patient Name" value={form.patient_name}
              onChange={e => setForm({...form, patient_name: e.target.value})} />
            <input type="number" placeholder="Age" value={form.patient_age}
              onChange={e => setForm({...form, patient_age: e.target.value})} />
            <select value={form.patient_gender} onChange={e => setForm({...form, patient_gender: e.target.value})}>
              <option value="male">Male</option>
              <option value="female">Female</option>
              <option value="other">Other</option>
            </select>
          </div>
          <input placeholder="Location Address" className="full-width"
            value={form.location_address} onChange={e => setForm({...form, location_address: e.target.value})} />
          <div className="form-row">
            <input placeholder="Latitude" value={form.location_lat}
              onChange={e => setForm({...form, location_lat: e.target.value})} />
            <input placeholder="Longitude" value={form.location_lng}
              onChange={e => setForm({...form, location_lng: e.target.value})} />
          </div>
        </section>

        <section>
          <h3>Vitals (Optional but improves accuracy)</h3>
          <div className="vitals-grid">
            <input type="number" placeholder="Pulse Rate (bpm)" value={form.pulse_rate}
              onChange={e => setForm({...form, pulse_rate: e.target.value})} />
            <input type="number" placeholder="BP Systolic (mmHg)" value={form.bp_systolic}
              onChange={e => setForm({...form, bp_systolic: e.target.value})} />
            <input type="number" placeholder="SpO2 (%)" value={form.spo2}
              onChange={e => setForm({...form, spo2: e.target.value})} />
            <input type="number" placeholder="Resp. Rate (/min)" value={form.respiratory_rate}
              onChange={e => setForm({...form, respiratory_rate: e.target.value})} />
            <input type="number" placeholder="GCS Score (3–15)" value={form.gcs_score}
              onChange={e => setForm({...form, gcs_score: e.target.value})} />
          </div>
        </section>

        <section>
          <h3>Symptoms (select all that apply)</h3>
          <div className="symptoms-grid">
            {SYMPTOMS_LIST.map(s => (
              <button
                key={s}
                className={`symptom-chip ${form.symptoms.includes(s) ? "selected" : ""}`}
                onClick={() => toggleSymptom(s)}
              >
                {s.replace(/_/g, " ")}
              </button>
            ))}
          </div>
        </section>

        <textarea placeholder="Chief complaint (describe in own words)"
          value={form.chief_complaint} onChange={e => setForm({...form, chief_complaint: e.target.value})} />

        {/* AI Triage Result */}
        {aiResult && (
          <div className={`ai-triage-result severity-${aiResult.severity_level}`}>
            <SeverityBadge level={aiResult.severity_level} label={aiResult.label} />
            <span className="confidence">Confidence: {(aiResult.confidence * 100).toFixed(1)}%</span>
            <div className="prob-breakdown">
              {Object.entries(aiResult.all_probabilities).map(([label, prob]) => (
                <div key={label} className="prob-bar">
                  <span>{label}</span>
                  <div className="bar" style={{ width: `${prob * 100}%` }} />
                  <span>{(prob * 100).toFixed(1)}%</span>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="form-actions">
          <button onClick={runAITriage} disabled={loading} className="btn-triage">
            {loading ? "Running AI Triage..." : "🤖 Run AI Triage"}
          </button>
          <button onClick={handleSubmit} disabled={!aiResult} className="btn-submit">
            Log Emergency & Find Ambulance
          </button>
          <button onClick={onClose} className="btn-cancel">Cancel</button>
        </div>
      </div>
    </div>
  );
}
```

---

## 10. Ambulance GPS Simulation

This script simulates ambulances moving around the city. Run it in a separate terminal during demo.

```python
# tools/simulate_gps.py
"""
Simulates live GPS updates from ambulances via Socket.IO.
Run: python simulate_gps.py
"""

import socketio
import asyncio
import random
import math
import json

sio = socketio.AsyncClient()

# Mumbai area bounds — change to your city
LAT_MIN, LAT_MAX = 18.90, 19.25
LNG_MIN, LNG_MAX = 72.75, 73.05

AMBULANCE_COUNT = 12

class SimulatedAmbulance:
    def __init__(self, amb_id):
        self.id = amb_id
        self.lat = random.uniform(LAT_MIN, LAT_MAX)
        self.lng = random.uniform(LNG_MIN, LNG_MAX)
        self.speed_kmh = random.uniform(30, 70)
        self.heading = random.uniform(0, 360)
        self.status = random.choice(["available", "available", "en_route", "returning"])
    
    def move(self):
        # Random walk with heading persistence
        self.heading += random.uniform(-20, 20)
        speed_ms = self.speed_kmh / 3.6
        delta_lat = speed_ms * math.cos(math.radians(self.heading)) / 111_139
        delta_lng = speed_ms * math.sin(math.radians(self.heading)) / (111_139 * math.cos(math.radians(self.lat)))
        
        self.lat = max(LAT_MIN, min(LAT_MAX, self.lat + delta_lat))
        self.lng = max(LNG_MIN, min(LNG_MAX, self.lng + delta_lng))
        
        # Bounce off boundaries
        if self.lat <= LAT_MIN or self.lat >= LAT_MAX:
            self.heading = 180 - self.heading
        if self.lng <= LNG_MIN or self.lng >= LNG_MAX:
            self.heading = 360 - self.heading

ambulances = [SimulatedAmbulance(i+1) for i in range(AMBULANCE_COUNT)]

@sio.event
async def connect():
    print(f"✅ GPS Simulator connected. Simulating {AMBULANCE_COUNT} ambulances...")

async def broadcast_loop():
    while True:
        for amb in ambulances:
            amb.move()
            await sio.emit("ambulance_gps_update", {
                "ambulance_id": amb.id,
                "lat": round(amb.lat, 6),
                "lng": round(amb.lng, 6),
                "speed_kmh": round(amb.speed_kmh, 1),
                "status": amb.status,
                "heading": round(amb.heading % 360, 1)
            })
        await asyncio.sleep(2)   # Update every 2 seconds

async def main():
    await sio.connect("http://localhost:8000")
    await broadcast_loop()

asyncio.run(main())
```

---

## 11. Testing Strategy

### 11.1 AI Model Tests
```python
# tests/test_ai_models.py

import pytest
import numpy as np
import joblib

def test_severity_model_loads():
    clf = joblib.load("ai/models/severity_classifier.pkl")
    assert clf is not None

def test_severity_critical_patient():
    """Cardiac arrest patient must be predicted as Critical (level 1)"""
    from ai.services.ai_inference import predict_severity
    result = predict_severity({
        "age": 65, "gender": "male",
        "symptoms": ["cardiac_arrest", "chest_pain", "unconscious"],
        "pulse_rate": 0, "blood_pressure_systolic": 60,
        "spo2": 70.0, "respiratory_rate": 4, "gcs_score": 3
    })
    assert result["severity_level"] == 1
    assert result["confidence"] > 0.70

def test_severity_non_emergency():
    """Cough + mild headache must NOT be predicted Critical"""
    from ai.services.ai_inference import predict_severity
    result = predict_severity({
        "age": 25, "gender": "female",
        "symptoms": ["cough", "headache"],
        "pulse_rate": 72, "blood_pressure_systolic": 118,
        "spo2": 99.0, "respiratory_rate": 16, "gcs_score": 15
    })
    assert result["severity_level"] >= 4

def test_eta_prediction_range():
    from ai.services.ai_inference import predict_eta
    result = predict_eta(5.0, {"congestion_level": 0.5, "severity_level": 2})
    assert 60 <= result["eta_seconds"] <= 3600

def test_hospital_diversion_penalty():
    from ai.services.ai_inference import score_hospital
    score_normal = score_hospital(
        {"severity_level": 1, "specialty_need": "trauma"},
        {"specialties": ["trauma"], "distance_km": 2, "available_beds_icu": 5,
         "available_beds_trauma": 3, "available_beds_general": 20,
         "er_wait_minutes": 15, "is_diversion": False, "occupied_pct": 0.5}
    )
    score_diverted = score_hospital(
        {"severity_level": 1, "specialty_need": "trauma"},
        {"specialties": ["trauma"], "distance_km": 2, "available_beds_icu": 0,
         "available_beds_trauma": 0, "available_beds_general": 0,
         "er_wait_minutes": 240, "is_diversion": True, "occupied_pct": 0.98}
    )
    assert score_normal > score_diverted + 20, "Diversion hospital should score much lower"
```

### 11.2 API Tests
```python
# tests/test_api.py

from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

def test_health():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"

def test_triage_endpoint():
    payload = {
        "age": 55, "gender": "male",
        "symptoms": ["chest_pain", "shortness_of_breath"],
        "pulse_rate": 110, "blood_pressure_systolic": 180,
        "spo2": 91.0, "respiratory_rate": 24, "gcs_score": 14
    }
    res = client.post("/api/emergencies/triage", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert "severity_level" in data
    assert 1 <= data["severity_level"] <= 5
    assert "confidence" in data

def test_dispatch_recommendation():
    res = client.post("/api/dispatch/recommend", json={"emergency_id": 1})
    assert res.status_code in [200, 404]  # 404 if no test data

def test_hospital_list():
    res = client.get("/api/hospitals")
    assert res.status_code == 200
    assert isinstance(res.json(), list)
```

---

## 12. Folder Structure

```
emergency-response-system/
│
├── ai/
│   ├── data_generation/
│   │   └── generate_all_data.py       ← Run first
│   ├── data/                          ← Generated CSV files
│   ├── train_all_models.py            ← Run second
│   ├── models/                        ← Saved .pkl and .h5 files
│   └── reports/                       ← Training plots and metrics JSON
│
├── backend/
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── models.py
│   ├── schemas.py
│   ├── auth.py
│   ├── socket_manager.py
│   ├── routers/
│   │   ├── emergencies.py
│   │   ├── ambulances.py
│   │   ├── hospitals.py
│   │   ├── dispatch.py
│   │   ├── analytics.py
│   │   └── users.py
│   └── services/
│       ├── ai_inference.py
│       ├── dispatch_engine.py
│       ├── maps_service.py
│       └── notifications.py
│
├── frontend/
│   ├── public/
│   │   └── icons/                     ← Ambulance, emergency, hospital map icons
│   ├── src/
│   │   ├── App.jsx
│   │   ├── store/
│   │   ├── pages/
│   │   ├── components/
│   │   ├── hooks/
│   │   └── utils/
│   ├── .env                           ← REACT_APP_GOOGLE_MAPS_KEY=...
│   └── package.json
│
├── tools/
│   └── simulate_gps.py               ← Run for demo
│
├── tests/
│   ├── test_ai_models.py
│   └── test_api.py
│
├── docker-compose.yml
├── requirements.txt                   ← Python dependencies
└── README.md
```

---

## 13. Step-by-Step Build Order

Follow this order exactly — each step depends on the previous.

```
PHASE 1 — DATA & AI (Days 1–2)
────────────────────────────────
[ ] 1. Set up Python environment:
        python -m venv venv
        source venv/bin/activate      (Windows: venv\Scripts\activate)
        pip install -r requirements.txt

[ ] 2. Run data generation:
        cd ai
        python data_generation/generate_all_data.py
        # Verify: data/ folder has 5 CSV files

[ ] 3. Train all models:
        python train_all_models.py
        # Takes 10–20 mins on a laptop CPU
        # Verify: models/ has 10+ files, reports/ has PNGs and JSONs

[ ] 4. Review training reports:
        cat reports/severity_classifier_report.json
        # Check accuracy > 85%, F1 > 0.80

PHASE 2 — BACKEND (Days 2–3)
────────────────────────────────
[ ] 5. Set up PostgreSQL:
        docker-compose up -d postgres
        # Or install locally and create DB: emergency_db

[ ] 6. Configure backend/.env:
        DATABASE_URL=postgresql://user:pass@localhost:5432/emergency_db
        GOOGLE_MAPS_API_KEY=your_key_here
        SECRET_KEY=your_jwt_secret_here
        AI_MODELS_PATH=../ai/models

[ ] 7. Run DB migrations:
        cd backend
        alembic init alembic
        alembic revision --autogenerate -m "initial"
        alembic upgrade head

[ ] 8. Seed test data:
        python seed_data.py
        # Creates 12 ambulances, 9 hospitals, 3 test users

[ ] 9. Start backend:
        uvicorn main:socket_app --reload --port 8000
        # Test: http://localhost:8000/docs (Swagger UI)

[ ] 10. Test AI endpoint:
         curl -X POST http://localhost:8000/api/emergencies/triage \
           -H "Content-Type: application/json" \
           -d '{"age":65,"gender":"male","symptoms":["cardiac_arrest","chest_pain"],"gcs_score":6}'
         # Expected: {"severity_level": 1, "label": "Critical", ...}

PHASE 3 — FRONTEND (Days 3–4)
────────────────────────────────
[ ] 11. Set up React:
         cd frontend
         npx create-react-app . --template cra-template
         # OR: npm create vite@latest . -- --template react
         npm install socket.io-client axios @react-google-maps/api recharts \
                      react-hot-toast zustand date-fns jspdf

[ ] 12. Add .env:
         REACT_APP_GOOGLE_MAPS_KEY=your_google_maps_api_key
         REACT_APP_API_URL=http://localhost:8000

[ ] 13. Build pages in order:
         Login → DispatcherDashboard → EmergencyForm (with AI triage) →
         DispatchModal → HospitalPortal → Analytics

[ ] 14. Start frontend:
         npm start
         # Opens http://localhost:3000

PHASE 4 — INTEGRATION & DEMO (Day 4–5)
────────────────────────────────────────
[ ] 15. Start GPS simulator (separate terminal):
         python tools/simulate_gps.py
         # Ambulances should start moving on map

[ ] 16. End-to-end test:
         - Log a new emergency with cardiac_arrest symptoms
         - AI triage should return Critical (red)
         - Click "Find Ambulance" — AI recommends nearest ALS ambulance
         - Click "Dispatch" — route appears on map, ETA shown
         - Watch ambulance move toward emergency location
         - Hospital panel shows pre-arrival notification

[ ] 17. Demo polish:
         - Add demo "seed emergencies" button for live presentation
         - Create PDF report download on analytics page
         - Record 2-min screen capture as backup

[ ] 18. Presentation checklist:
         ✅ Explain the 5 AI models and why each was chosen
         ✅ Show training accuracy metrics (from reports/ folder)
         ✅ Demonstrate live dispatch with AI recommendations
         ✅ Show hospital ranking with bed availability
         ✅ Show ETA prediction vs manual estimate
         ✅ Explain SMOTE + calibration (why probabilities are reliable)
         ✅ Show LSTM hotspot map (visual demand prediction)
```

---

## 🎯 AI Model Summary (for Presentation)

| Model | Algorithm | Key Metric | Why Chosen |
|-------|-----------|------------|------------|
| Severity Classifier | XGBoost + LightGBM + RF Ensemble + Calibration | F1-Macro > 0.85 | Ensemble reduces overfitting; calibration gives reliable confidence % |
| ETA Predictor | XGBoost + LightGBM Average | MAE < 45s | Gradient boosting best for tabular regression; ensemble reduces variance |
| Hospital Recommender | XGBoost Regressor | R² > 0.88, Ranking Acc > 80% | Learns non-linear interactions between bed types, distance, specialty |
| Traffic Predictor | LightGBM Regressor | MAE < 0.05 congestion units | Fastest training, handles categorical features natively |
| Hotspot Forecaster | 3-layer LSTM | MAE < 0.4 incidents/hr | Sequential time patterns require recurrent architecture |

**Total valid AI points for judging:**
- ✅ 5 independently trained models
- ✅ Synthetic data generation with realistic domain modeling
- ✅ SMOTE for class imbalance handling
- ✅ Stratified K-fold cross-validation
- ✅ Probability calibration
- ✅ Ensemble methods
- ✅ RobustScaler for outlier-heavy ETA data
- ✅ SHAP for model explainability
- ✅ Early stopping + LR scheduling for LSTM
- ✅ Huber loss for robustness to outlier incident counts

---

*Built for Hackathon — All AI inference is local, no external AI APIs used.*
