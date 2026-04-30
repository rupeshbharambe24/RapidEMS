# RapidEMS — Rapid Emergency Management System

End-to-end emergency-response platform: triages incoming calls, dispatches the
nearest capable ambulance, and routes the patient to the best-fit hospital.
Backed by five locally trained ML models, an optional LLM intake layer for
free-text caller transcripts, and a live mission-control dashboard.

---

## 1. What it does

```
caller transcript ─►  POST /ai/extract           (LLM, optional)
                          │
                          ▼
                    auto-filled intake form
                          │
                          ▼
                    POST /emergencies            ─►  Severity classifier
                                                       │
                                                       ▼
                    POST /emergencies/{id}/dispatch    Ambulance type filter
                                                       │
                                                       ▼
                                                     Traffic predictor + ETA
                                                       │
                                                       ▼
                                                     Hospital recommender
                                                       │
                                                       ▼
                                            Dispatch record + Socket.IO event
```

End-to-end decision time is sub-second once intake is filled. The intake LLM
adds ~700 ms (Groq) or ~3.6 s (Gemini) but is optional and only runs when the
dispatcher chooses to parse a transcript.

---

## 2. Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│  Frontend  (Vite + React 18 + Tailwind 3 + Leaflet + Socket.IO)      │
│  http://localhost:5173                                               │
│  Pages: Login · Dashboard · Intake · Fleet · Facilities · Analytics  │
│  Stores: Zustand per resource (auth, ambulances, emergencies, …)     │
└────────────────────┬─────────────────────────────────────────────────┘
                     │  REST + Socket.IO (Vite proxy → :8000)
                     ▼
┌──────────────────────────────────────────────────────────────────────┐
│  Backend  (FastAPI 0.115 + SQLAlchemy 2 + python-socketio)           │
│  http://localhost:8000   /docs for OpenAPI explorer                  │
│                                                                      │
│  api/        auth, emergencies, ambulances, hospitals, dispatches,   │
│              ai, analytics, routing, patient, driver, hospital,      │
│              admin, notifications, tracking, copilot, public,        │
│              telemetry, mci, drones, insurance, ar                   │
│  services/   ai_service        – 5 ML models + heuristic fallbacks   │
│              llm_extractor     – Groq → Gemini → heuristic skim      │
│              dispatch_engine   – orchestrator (severity/ETA/hosp)    │
│              multi_dispatch    – Hungarian over PENDING × AVAILABLE  │
│              staging           – LSTM-driven pre-positioning         │
│              copilot           – Groq tool-calling dispatcher copilot│
│              voice_transcribe  – Groq Whisper for /copilot/voice     │
│              drone_recon       – pre-arrival aerial scene preview    │
│              demo_runner       – cinematic scenarios + replay        │
│              chaos             – fault-injection lab                 │
│              insurance         – EDI-271 eligibility (stub registry) │
│              ar_navigation     – polyline → AR waypoints             │
│              mci, ml_extras, severity_explainer, er_briefing,        │
│              tracking_link, notifications, audit_chain, policy,      │
│              data_retention, tenant, auth_service, geo_service       │
│  sockets/    sio.py            – live channels (15+)                 │
│  models/     16 SQLAlchemy ORM tables                                │
│  schemas/    Pydantic v2 request/response                            │
└────┬─────────────────┬────────────────────────────────┬──────────────┘
     │                 │                                │
     ▼                 ▼                                ▼
SQLite (WAL mode)  ai_models/*.pkl, *.keras       Groq / Gemini
(8 hospitals,      severity, ETA (xgb+lgbm+cat),  (optional, free tiers)
 20 ambulances,    hospital recommender, traffic,
 1 admin user)     hotspot LSTM
     ▲
     │
┌────┴─────────────────────────────────────────────────────────────────┐
│  Simulator  (Python asyncio)                                         │
│  Drives the 20 seeded ambulances through the dispatch lifecycle:     │
│  AVAILABLE → EN_ROUTE → ON_SCENE → TRANSPORTING → at hospital →      │
│  RETURNING → AVAILABLE. Reports GPS via PATCH /ambulances/{id}/      │
│  location every 2 seconds.                                           │
└──────────────────────────────────────────────────────────────────────┘
```

A single launcher (`run.py`) creates `.venv`, installs Python and Node
dependencies, initialises the database, detects ML model files, and spawns
backend + simulator + Vite as managed subprocesses with a shared Ctrl-C
shutdown.

---

## 3. The 5 ML models

| # | Model | Architecture | Training notebook | Used by |
|---|---|---|---|---|
| 1 | **Severity classifier** | Soft-voting ensemble (XGBoost + LightGBM + CatBoost) with isotonic calibration, SMOTE-balanced | `notebooks/01_severity_classifier.ipynb` | Triage at dispatch |
| 2 | **ETA predictor** | Averaged ensemble of 3 gradient boosters (XGBoost + LightGBM + CatBoost) | `notebooks/02_eta_predictor.ipynb` | Ambulance ranking |
| 3 | **Hospital recommender** | XGBoost regressor with NDCG@3 ranking eval | `notebooks/03_hospital_recommender.ipynb` | Hospital selection |
| 4 | **Traffic predictor** | LightGBM with cyclical hour/day features | `notebooks/04_traffic_predictor.ipynb` | Feeds ETA |
| 5 | **Hotspot forecaster** | Stacked / Bidirectional LSTM (Keras) with dropout + Huber loss | `notebooks/05_hotspot_forecaster_lstm.ipynb` | Analytics, pre-positioning |

All five train on synthetic-but-realistic data generated inside their
notebooks — no external dataset required. Saved artifacts live in
`backend/ai_models/`.

**Two ways to populate `backend/ai_models/`:**

```bash
# Full quality (~25 min total on CPU)
jupyter nbconvert --execute --to notebook --inplace notebooks/*.ipynb

# Or interactively from Jupyter — Run All on each notebook
```

```bash
# Quick fallback (~90 s) — RandomForest + tiny LSTM
cd backend && python -m app.ai.quick_train
```

If the artifacts are missing, every prediction method has a **rule-based
heuristic fallback** built in. API responses include `used_fallback: true` so
the frontend can surface the degraded mode.

---

## 4. LLM intake layer

Optional. Converts free-text caller transcripts (English / Hindi / Marathi or
any mix) into structured intake fields. The local ML ensemble still owns the
actual triage decision — the LLM only parses unstructured input.

```
transcript ─► services/llm_extractor.py
                │
                ├─► Groq    (Llama 3.3 70B, ~700 ms, primary)
                ├─► Gemini  (gemini-2.5-flash, ~3.6 s, fallback)
                └─► heuristic regex skim (last-ditch, never raises)
                │
                ▼
          ExtractedEmergency (Pydantic-validated)
            age, gender, vitals, symptoms (whitelist-filtered),
            chief_complaint, location_hint, patient_type,
            severity_hint, language_detected
```

**Provider selection.** `LLM_PROVIDER_ORDER=groq,gemini` in `.env` (default).
Groq runs first because it's an order of magnitude faster; Gemini is reserved
for fallbacks. Set the order to a single provider to disable the other, or
leave both keys empty to disable LLM extraction entirely (heuristic mode).

**Symptom safety.** LLM output is filtered against the canonical 21-term
symptom whitelist before reaching the severity model — no surprise free-text
strings pollute the feature space.

**Endpoint.**

```
POST /ai/extract
Body:  { "transcript": "...", "language_hint": "en|hi|mr|null" }
Returns: { extracted: ExtractedEmergency, provider_used, used_fallback,
           latency_ms, error }
```

The Intake page wires this to a "Caller transcript" textarea. Click
**Auto-fill from transcript** and the form populates with whatever the LLM
extracted. Existing user input is never overwritten — extracted values only
fill blanks. The `inferred_patient_type` flows through to dispatch so the
ML-driven hospital-scoring uses the LLM hint instead of keyword matching.

---

## 5. Dispatch pipeline

The single place where all five ML models meaningfully come together.
Lives in `backend/app/services/dispatch_engine.py`:

```
POST /emergencies/{id}/dispatch
  │
  1. Triage  ← Severity classifier  (1-5 + confidence)
  │
  2. Filter ambulances by required type
       sev 1-2 → ALS / ICU only
       sev 3   → BLS / ALS / ICU
       sev 4-5 → BLS
  │
  3. Get current zone congestion  ← Traffic predictor
  │
  4. For each candidate ambulance:
       distance = haversine(amb, emergency)
       eta      = ETA predictor(distance, congestion, hour, dow, ...)
     Pick lowest ETA
  │
  5. Use emergency.inferred_patient_type if set (LLM-extracted at intake);
     otherwise infer from symptom keywords
  │
  6. For each hospital:
       score = Hospital recommender(patient_type, h, distance)
     Pick highest score
  │
  7. Persist Dispatch row, mark ambulance EN_ROUTE,
     mark emergency DISPATCHED, audit-log the decision
  │
  8. Emit Socket.IO event: emergency:dispatched
  │
Returns DispatchPlan {severity, ambulance_reg, hospital_name, ETA,
                      distance, fit-score, used_fallback}
```

---

## 6. Data model

| Table | Purpose | Key fields |
|---|---|---|
| `emergencies` | Each call | location, vitals (pulse, BP, SpO₂, GCS, RR), symptoms[], predicted_severity, severity_confidence, inferred_patient_type, status |
| `ambulances` | Fleet | registration, type (BLS / ALS / ICU_MOBILE), status, current_lat/lng, home_station_*, paramedic info, equipment[] |
| `hospitals` | Facilities | name, lat/lng, specialties[], bed counts × 5 categories (general, ICU, trauma, pediatric, burns), ER wait, diversion flag, quality rating |
| `dispatches` | Assignment | emergency_id ↔ ambulance_id ↔ hospital_id, dispatched_at, predicted_eta_seconds, actual_response_time_seconds, hospital_recommendation_score, status |
| `users` | Auth | username, hashed_password (bcrypt), role |
| `audit_log` | Decisions trail | timestamp, user_id, action, entity_type, entity_id, details (JSON) |
| `traffic_snapshots` | Historical congestion | recorded_at, zone_id, congestion_level, avg_speed_kmh, hour_of_day, day_of_week |

Tables auto-create on first run via `Base.metadata.create_all()`. SQLite is
the default; switching to PostgreSQL is a single `DATABASE_URL` change.

**SQLite tuning** (in `database.py`): WAL journal mode, `busy_timeout=10s`,
pool size 20 / overflow 40. The simulator pushes ~10 PATCH/sec across the
fleet — the default 5+10 pool was easy to exhaust under that load.

---

## 7. REST API surface

OpenAPI explorer at `http://localhost:8000/docs`.

**Auth**
- `POST /auth/login` → JWT
- `POST /auth/register`
- `GET  /auth/me`

**Emergencies**
- `GET   /emergencies` (filterable by status)
- `POST  /emergencies`
- `GET   /emergencies/{id}`
- `POST  /emergencies/{id}/dispatch` — runs the full pipeline
- `PATCH /emergencies/{id}` — status update

**Ambulances**
- `GET   /ambulances` (filterable by status)
- `POST  /ambulances`
- `PATCH /ambulances/{id}/location` — used by the simulator
- `PATCH /ambulances/{id}/status`

**Hospitals**
- `GET   /hospitals`, `POST /hospitals`
- `PATCH /hospitals/{id}/beds`

**Dispatches**
- `GET   /dispatches/active`, `GET /dispatches/{id}`

**AI inference**
- `POST  /ai/triage` — severity + confidence + used_fallback
- `POST  /ai/eta`, `POST /ai/traffic`
- `GET   /ai/hotspots`
- `POST  /ai/extract` — caller transcript → structured intake

**Analytics**
- `GET   /analytics/kpis`
- `GET   /analytics/hotspots` — LSTM heatmap data per zone

**Multi-emergency optimisation & predictive staging**
- `POST  /dispatches/optimize?execute=…` — Hungarian assignment over all PENDING calls × AVAILABLE units
- `GET   /dispatches/staging/preview?horizon_hours=…` — LSTM-driven pre-positioning advisories
- `POST  /dispatches/staging/apply` — same plus `staging:position` Socket.IO emit per drone-… ambulance

**MCI command (Mass-Casualty Incidents)**
- `POST  /mci/declare`, `POST /mci/{id}/close`, `GET /mci`
- `POST  /mci/victims` — START algorithm classifies into red / yellow / green / black
- `POST  /mci/optimize` (preview), `POST /mci/execute` (Hungarian over the live victim queue)

**Voice-first dispatcher copilot**
- `POST  /copilot/ask` — Groq tool-calling over read-only fleet/hospital/emergency tools
- `POST  /copilot/voice` — multipart audio (Groq Whisper v3-turbo) **or** transcript path → reuses `/ask`

**Drone reconnaissance**
- `GET   /drones`, `GET /drones/active`
- `POST  /drones/dispatch` — manual; auto-launch fires from `/emergencies` for SEV-1 / MCI / fire / RTA

**Insurance verification (EDI-271 shape)**
- `POST  /insurance/verify` — payer + plan tier + in-network hospital IDs
- `GET   /insurance/payers`

**AR turn-by-turn overlay**
- `GET   /ar/turn-by-turn/{dispatch_id}` — origin / destination / sequenced waypoints with bearings + turn cues

**Cinematic demo + replay (admin)**
- `GET   /admin/demo/scenarios`, `POST /admin/demo/start`, `GET /admin/demo/status`, `POST /admin/demo/stop`
- `GET   /admin/replay`, `POST /admin/replay/start`, `GET /admin/replay/status` — re-emits captured Socket.IO frames at any speed

**Chaos lab (admin)**
- `GET   /admin/chaos`, `POST /admin/chaos/inject`, `POST /admin/chaos/clear?scenario=…`
  Scenarios: `routing_provider_down`, `severity_predictor_slow`, `dispatch_failure_rate`

**Patient / driver / hospital portals**
- `/patient/*` — patient self-service profile + medical record + tracking links
- `/driver/*` — claim/release a unit, push GPS, status transitions
- `/hospital/*` — alert acknowledge / accept / divert from inbound dispatches
- `/track/{token}` — public family-facing tracking link (signed, time-limited)

**Public + telemetry + admin**
- `/public-api/*` — anonymised city dashboard data
- `/telemetry/*` — Patient-monitor vitals stream
- `/admin/*` — users, audit log, retention sweep, export bundle, erasure, ambulance assign
- `/metrics` — Prometheus scrape target

---

## 8. Real-time channels (Socket.IO at `/socket.io`)

| Channel | Payload |
|---|---|
| `ambulance:position` | `{ ambulance_id, lat, lng, status }` — every simulator tick |
| `ambulance:status_change` | `{ ambulance_id, status }` |
| `emergency:created` | full intake payload (location, symptoms, …) |
| `emergency:dispatched` | full DispatchPlan |
| `hospital:beds_updated` | `{ hospital_id, available_beds_*, … }` |
| `hospital:alert` | pre-arrival ER briefing (Gemini text + structured fields) |
| `hospital:alert_status` | acknowledged / accepted / diverted |
| `staging:position` | predictive pre-positioning advisory for an idle unit |
| `mci:declared` / `mci:victim_registered` | MCI command stream |
| `drone:position` / `drone:status` / `drone:scene_preview` | recon overlay |
| `demo:narration` / `demo:finished` | cinematic-demo subtitles + completion |
| `replay:finished` | captured-session re-emit completed |

Handlers in `frontend/src/api/socket.js` mutate the corresponding Zustand
stores directly, so every page reflects changes without prop drilling.

---

## 9. Frontend

Aesthetic: dark mission-control. JetBrains Mono for IDs and numeric data,
Manrope for UI. Severity uses a 5-step palette
(red / orange / amber / cyan / emerald for SEV 1–5).

| Page | URL | What's there |
|---|---|---|
| Login | `/login` | JWT auth; defaults pre-filled in dev |
| Dashboard | `/dashboard` | Live tactical map (Leaflet + dark-filtered OSM tiles), status-coloured ambulance markers, pulsing emergency markers, hospital rings tinted by bed availability, dashed polylines for active dispatches. KPI rail + pending intake queue + active-dispatch rail |
| Intake | `/intake` | **Caller transcript textarea** with one-click LLM auto-fill (provider/latency/language badge), live AI triage chip (350 ms debounced), 4-tier symptom palette, click-anywhere-on-map to set location. Submit as Create or Create + Dispatch |
| Fleet | `/ambulances` | Roster with status filters, click a unit to fly the map and inspect crew, certification, depot, last GPS, and active dispatch |
| Facilities | `/hospitals` | Per-hospital cards with bed bars (general / ICU / trauma / pediatric / burns), ER wait, diversion flag, quality stars. Inline bed-count edit broadcasts via Socket.IO |
| Analytics | `/analytics` | LSTM hotspot heatmap (12-zone grid coloured by next-24-h forecast) + Recharts bar chart + KPI strip |

Custom Leaflet `divIcon` markers (status-coloured ambulance circles with
embedded SVGs, pulsing CSS-keyframe emergency rings, hospital rings tied to
bed counts). OSM tiles get
`hue-rotate(195deg) invert(0.92) saturate(0.6) brightness(0.85)` for a dark
theme without paying for a tile provider.

---

## 10. Project layout

```
RapidEMS/
├── run.py                           single-command launcher (8 phases)
├── README.md                        this file
├── .env.example                     copy → .env (defaults work as-is)
│
├── docs/
│   └── build_guide.md               full architecture spec
│
├── backend/
│   ├── requirements.txt
│   ├── ai_models/                   trained .pkl / .keras drop here
│   ├── tests/test_api.py            pytest end-to-end smoke tests
│   └── app/
│       ├── main.py                  FastAPI + Socket.IO mount
│       ├── config.py                pydantic-settings (incl. LLM keys)
│       ├── database.py              SQLAlchemy engine + WAL pragmas
│       ├── seed.py                  hospitals, ambulances, admin user
│       ├── models/                  7 ORM tables
│       ├── schemas/                 Pydantic request/response
│       │   └── llm.py               TranscriptIn, ExtractedEmergency
│       ├── api/                     8 routers (incl. /ai/extract)
│       ├── services/
│       │   ├── ai_service.py        loads 5 ML models + heuristic fallbacks
│       │   ├── llm_extractor.py     Groq + Gemini transcript parser
│       │   ├── dispatch_engine.py   the orchestrator
│       │   ├── auth_service.py
│       │   └── geo_service.py
│       ├── sockets/sio.py
│       ├── core/                    security, logging, startup_check
│       └── ai/quick_train.py        90 s fallback ML training
│
├── simulator/
│   └── gps_simulator.py             drives the 20 ambulances
│
├── notebooks/                       5 model-training notebooks
│   ├── 01_severity_classifier.ipynb
│   ├── 02_eta_predictor.ipynb
│   ├── 03_hospital_recommender.ipynb
│   ├── 04_traffic_predictor.ipynb
│   ├── 05_hotspot_forecaster_lstm.ipynb
│   └── README.md
│
└── frontend/                        Vite + React + Tailwind + Leaflet
    ├── package.json, vite.config.js, tailwind.config.js
    ├── index.html
    └── src/
        ├── main.jsx, App.jsx, index.css
        ├── api/                     axios client + Socket.IO wiring
        │   └── client.js            includes aiApi.extract()
        ├── store/                   Zustand stores
        ├── components/              Layout, MapView, KPICard, …
        ├── pages/                   Login, Dashboard, EmergencyForm, …
        └── utils/                   format, leaflet icons
```

---

## 11. Setup

### Prerequisites

- Python ≥ 3.10
- Node.js ≥ 18 (only if you want the frontend; backend works without it)
- Optional: a Groq and/or Gemini API key for transcript extraction

### One command

```bash
python run.py
```

The launcher walks 8 phases:

1. Verify Python ≥ 3.10
2. Create or reuse `.venv/`
3. `pip install -r backend/requirements.txt` (cached after first run)
4. Initialise the SQLite database, run schema, seed data
5. Detect ML model artifacts; offer to `quick_train` if any are missing
6. Verify Node + run `npm install` (cached)
7. Spawn backend (uvicorn :8000) + simulator + Vite (:5173) as subprocesses
8. Stream their logs; Ctrl-C cleanly stops all three

When done:

- Frontend: <http://localhost:5173>  (login: `admin` / `admin123`)
- API docs: <http://localhost:8000/docs>
- Health:   <http://localhost:8000/health>

### Useful flags

```bash
python run.py --no-sim         # backend + frontend only
python run.py --no-frontend    # backend + simulator only
python run.py --backend-only
python run.py --setup-only     # set up env / db / models, then exit
python run.py --skip-install   # faster restart, skips pip + npm install
python run.py --reset-db       # delete the SQLite db before starting
```

---

## 12. Configuration

`.env` (copied from `.env.example` on first run). Defaults work without
edits; LLM keys are optional.

```ini
# Database — sqlite by default, switch to postgres with one line
DATABASE_URL=sqlite:///./emergency.db

# Auth
SECRET_KEY=change-me-...
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# App
APP_HOST=0.0.0.0
APP_PORT=8000
DEBUG=true
LOG_LEVEL=INFO

# ML
MODELS_DIR=./ai_models
ALLOW_HEURISTIC_FALLBACK=true

# LLM extraction (optional, free tiers)
# Empty keys = feature disabled, system falls back to heuristic regex skim.
# Groq:   https://console.groq.com/keys
# Gemini: https://aistudio.google.com/apikey
GROQ_API_KEY=
GROQ_MODEL=llama-3.3-70b-versatile
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.5-flash
LLM_PROVIDER_ORDER=groq,gemini

# CORS
CORS_ORIGINS=http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173

# Seed
SEED_ON_STARTUP=true
SEED_CITY_LAT=19.0760
SEED_CITY_LNG=72.8777
SEED_NUM_AMBULANCES=20
SEED_NUM_HOSPITALS=8

# Default admin
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin123
```

---

## 13. Tech stack

**Backend (Python 3.10+)**
- FastAPI 0.115 + Uvicorn (ASGI)
- SQLAlchemy 2 + SQLite (PostgreSQL-ready) with WAL journal mode
- Pydantic v2 + pydantic-settings
- python-socketio 5 (mounted as `socketio.ASGIApp`)
- python-jose (JWT) + passlib[bcrypt]
- numpy, pandas, scikit-learn, xgboost, lightgbm, catboost, joblib
- TensorFlow 2.18 (only for the LSTM; optional)
- httpx 0.27 (LLM provider HTTP — direct REST, no provider SDKs)
- loguru for structured logging

**Frontend (Node 18+)**
- Vite 5 + React 18 + React Router 6
- Tailwind CSS 3.4 with custom mission-control palette
- Zustand 4 (one store per resource)
- React-Leaflet 4.2 + Leaflet 1.9 + OpenStreetMap
- Socket.IO client 4.7
- Recharts 2.13
- Lucide React (icons)
- Axios with JWT interceptor + auto-401-logout

**LLM providers** (no SDK dependency)
- Groq REST (OpenAI-compatible chat completions, JSON mode)
- Google Generative Language v1beta (`generateContent`, `application/json` mime)

**Tooling**
- pytest 8 (`backend/tests/test_api.py`)
- jupyter / nbconvert (training notebooks)

---

## 14. Resilience

Built into every layer:

- **Missing ML models** → heuristic rule-based fallbacks per prediction method.
  API responses report `used_fallback: true` so the UI can surface the
  degraded mode.
- **No LLM keys / Groq down** → Gemini retried; if both fail or are
  unconfigured, a regex skim returns whatever it can. The endpoint never
  raises.
- **Missing TensorFlow** → LSTM hotspot path uses heuristic forecast; the
  rest of the system is unaffected.
- **Socket.IO disconnect** → the topbar indicator turns red and the
  dashboard falls back to 8-second REST polling so it never goes stale.
- **Backend down during simulator startup** → the simulator retries every
  2 s for up to 60 s before giving up.
- **JWT expired / invalid** → axios interceptor auto-logs-out and
  redirects to `/login`.
- **Unhandled exception in any endpoint** → universal 500 handler returns a
  JSON body so the frontend can toast it instead of seeing a raw error.
- **SQLite under load** → WAL mode + `busy_timeout=10s` + pool size 20 /
  overflow 40 lets the simulator push GPS updates while readers query in
  parallel without lock contention.

---

## 15. Tests

```bash
cd backend
pytest tests/ -v
```

End-to-end smoke tests cover login → list hospitals → create emergency →
dispatch. The suite uses an in-memory database so it doesn't touch
`emergency.db`.

---

## 16. Switching to PostgreSQL

```bash
pip install psycopg2-binary
```

Edit `.env`:

```
DATABASE_URL=postgresql+psycopg2://user:password@localhost:5432/rapidems
```

The SQLite-specific WAL pragmas in `database.py` skip themselves when the URL
isn't sqlite. Tables auto-create on first start; seed runs once if the
`users` table is empty.
