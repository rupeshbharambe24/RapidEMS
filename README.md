# 🚑 AI-Enabled Smart Emergency Response & Ambulance Coordination System

A production-grade hackathon system that triages emergencies, dispatches the nearest capable ambulance, and routes to the best hospital — all powered by **5 trained ML models** working in concert. Now with a complete **mission-control React frontend** (Vite + Leaflet + Socket.IO).

> **Status:** Phase 1 (backend + simulator) ✅, Phase 2 (frontend) ✅ — full stack ready to demo.

---

## ⚡ Quick start

```bash
# One command — sets up everything
python run.py
```

That's it. The script will:
1. Verify Python ≥ 3.10
2. Create a virtual environment (`.venv/`)
3. Install all backend dependencies (~60s on first run)
4. Initialize the SQLite database and seed it with 8 hospitals + 20 ambulances + 1 admin user
5. Detect ML models — offer to **quick-train them in 90s** if missing
6. Detect Node.js + run `npm install` for the frontend (~60s on first run)
7. Start three subprocesses: backend (FastAPI + Socket.IO on `:8000`), GPS simulator, and Vite dev server (`:5173`)

When done you'll have:
- **Frontend (start here):** http://localhost:5173 — login `admin` / `admin123`
- **API docs:** http://localhost:8000/docs
- **Health check:** http://localhost:8000/health

Press **Ctrl-C** to stop everything cleanly.

---

## 🧠 The 5 ML models

| # | Model | What it does | Notebook |
|---|-------|--------------|----------|
| 1 | **Severity Classifier** | Triages each call into Critical / Serious / Moderate / Minor / Non-Emergency | `notebooks/01_severity_classifier.ipynb` |
| 2 | **ETA Predictor** | Predicts arrival time given distance, traffic, weather, time-of-day | `notebooks/02_eta_predictor.ipynb` |
| 3 | **Hospital Recommender** | Scores each hospital for a given patient (specialty, beds, distance, ER wait) | `notebooks/03_hospital_recommender.ipynb` |
| 4 | **Traffic Predictor** | Forecasts congestion per zone given hour/day/weather | `notebooks/04_traffic_predictor.ipynb` |
| 5 | **LSTM Hotspot Forecaster** | Forecasts next-24-hour incident counts per zone | `notebooks/05_hotspot_forecaster_lstm.ipynb` |

The dispatch engine in `backend/app/services/dispatch_engine.py` is the only place where all 5 models meaningfully come together.

### Two ways to get trained models

**Option A — Full quality (>95% accuracy):** Open the 5 notebooks and run all cells. Each notebook saves its artifacts directly to `backend/ai_models/`. Total: ~30 minutes.

**Option B — Quick-train fallback (~90s, ~85-92% accuracy):**
```bash
cd backend
python -m app.ai.quick_train
```
This trains lightweight `RandomForest` + tiny `LSTM` versions of all 5 models. Good for first-run / demo purposes. `run.py` will offer to do this automatically if it detects missing model files.

**Heuristic fallbacks** are built into every prediction method, so the system stays functional even if you skip training entirely. Predictions just use rule-based logic instead of ML.

---

## 🗂️ Project structure

```
emergency-response-system/
├── run.py                          ← single entry point
├── .env.example                    ← copy → .env (defaults work as-is)
├── README.md                       ← this file
│
├── backend/
│   ├── requirements.txt
│   ├── ai_models/                  ← .pkl / .keras drop in here
│   │
│   └── app/
│       ├── main.py                 ← FastAPI app + Socket.IO mount
│       ├── config.py               ← Pydantic settings
│       ├── database.py             ← SQLAlchemy session, auto-create tables
│       ├── seed.py                 ← demo hospitals + ambulances + admin
│       │
│       ├── models/                 ← 7 SQLAlchemy ORM tables
│       ├── schemas/                ← Pydantic request/response shapes
│       │
│       ├── api/                    ← REST endpoints (8 routers)
│       │   ├── auth.py             POST /auth/login, /auth/register
│       │   ├── emergencies.py      CRUD + POST /emergencies/{id}/dispatch
│       │   ├── ambulances.py       CRUD + PATCH /location, /status
│       │   ├── hospitals.py        CRUD + PATCH /beds
│       │   ├── dispatches.py       GET /dispatches/active
│       │   ├── ai.py               raw inference: /ai/triage, /ai/eta, etc.
│       │   └── analytics.py        /analytics/kpis, /analytics/hotspots
│       │
│       ├── services/
│       │   ├── ai_service.py       ← singleton: loads all 5 models + heuristic fallbacks
│       │   ├── dispatch_engine.py  ← THE orchestrator
│       │   ├── auth_service.py
│       │   └── geo_service.py      ← haversine, zone mapping
│       │
│       ├── sockets/sio.py          ← Socket.IO real-time channel
│       ├── core/
│       │   ├── security.py         ← JWT + bcrypt
│       │   ├── logging.py          ← loguru config
│       │   └── startup_check.py    ← model file detection
│       └── ai/
│           └── quick_train.py      ← 90-second fallback training
│
├── simulator/
│   └── gps_simulator.py            ← drives the ambulance fleet
│
├── notebooks/                      ← your 5 model-training notebooks
│
└── frontend/                       ← Vite + React + Tailwind + Leaflet
    ├── package.json
    ├── vite.config.js              ← proxies /auth, /emergencies, /socket.io to :8000
    ├── tailwind.config.js          ← mission-control palette + animations
    └── src/
        ├── main.jsx, App.jsx, index.css
        ├── api/                    ← axios client + Socket.IO wiring
        ├── store/                  ← Zustand stores (auth, ambulances, hospitals, …)
        ├── components/             ← Layout, Sidebar, Topbar, MapView, KPICard, …
        ├── pages/                  ← Login, Dashboard, EmergencyForm, AmbulanceTracking,
        │                              HospitalAvailability, Analytics
        └── utils/                  ← format helpers + custom Leaflet divIcons
```

---

## 🌐 REST API

Visit `http://localhost:8000/docs` for the live OpenAPI explorer. Highlights:

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Liveness + model file status |
| POST | `/auth/login` | Issue JWT |
| GET | `/emergencies` | List recent calls |
| POST | `/emergencies` | Create a new emergency |
| **POST** | **`/emergencies/{id}/dispatch`** | **Run the full AI dispatch pipeline** |
| GET | `/ambulances` | List fleet (with live positions) |
| PATCH | `/ambulances/{id}/location` | Push GPS update |
| PATCH | `/ambulances/{id}/status` | Status transition |
| GET | `/hospitals` | List hospitals (with bed availability) |
| PATCH | `/hospitals/{id}/beds` | Update bed counts |
| GET | `/dispatches/active` | What's currently in progress |
| POST | `/ai/triage` | Raw severity prediction (used by frontend for live triage hints) |
| POST | `/ai/eta` | Raw ETA prediction |
| POST | `/ai/traffic` | Raw congestion prediction |
| GET | `/ai/hotspots` | Forecast for one zone |
| GET | `/analytics/kpis` | Dashboard counters |
| GET | `/analytics/hotspots` | Heatmap data for all zones |

### Example: trigger a full dispatch

```bash
# 1. Create an emergency
curl -X POST http://localhost:8000/emergencies -H "Content-Type: application/json" -d '{
  "patient_age": 55, "patient_gender": "male",
  "location_lat": 19.07, "location_lng": 72.87,
  "symptoms": ["chest_pain", "shortness_of_breath"],
  "pulse_rate": 130, "spo2": 88, "gcs_score": 13
}'
# → {"id": 1, ...}

# 2. Dispatch
curl -X POST http://localhost:8000/emergencies/1/dispatch
# → {
#     "severity_level": 2, "severity_label": "Serious",
#     "inferred_patient_type": "cardiac",
#     "ambulance_registration": "AMB-1019",
#     "hospital_name": "Heritage Cardiac Institute",
#     "predicted_eta_minutes": 4.7, ...
#   }
```

---

## 📡 Real-time Socket.IO channels

Connect to `ws://localhost:8000/socket.io/`:

| Channel | Payload |
|---------|---------|
| `ambulance:position` | `{ ambulance_id, lat, lng, status }` |
| `ambulance:status_change` | `{ ambulance_id, status }` |
| `emergency:created` | `{ id, lat, lng, symptoms, ... }` |
| `emergency:dispatched` | full `DispatchPlan` object |
| `hospital:beds_updated` | `{ hospital_id, available_beds_*, ... }` |

The frontend subscribes to these for live map updates (see the Frontend tour below).

---

## 🚦 GPS Simulator

The simulator drives 20 ambulances around the seeded city:
- **Idle** ambulances wander randomly within ~6 km of their depot.
- When a dispatch is created, the assigned ambulance switches to **EN_ROUTE** and drives toward the emergency.
- On arrival → **ON_SCENE** for ~12s → **TRANSPORTING** to the assigned hospital.
- Hospital handoff (~18s) → **RETURNING** to depot → **AVAILABLE** again.

Run it standalone (e.g., for debugging) with:
```bash
python simulator/gps_simulator.py --backend http://localhost:8000
```

---

## 🛠️ Configuration

Everything is configured via environment variables. Defaults work — you typically don't need a `.env` file at all. To customize, copy `.env.example` to `.env` and edit. Key settings:

| Variable | Default | Notes |
|----------|---------|-------|
| `DATABASE_URL` | `sqlite:///./emergency.db` | Switch to `postgresql+psycopg2://...` for Postgres |
| `SECRET_KEY` | (dev placeholder) | Change in production! |
| `MODELS_DIR` | `./ai_models` | Where `.pkl`/`.keras` files live |
| `ALLOW_HEURISTIC_FALLBACK` | `true` | If `false`, missing models cause 500s |
| `SEED_NUM_AMBULANCES` | `20` | Fleet size |
| `SEED_NUM_HOSPITALS` | `8` | |
| `SEED_CITY_LAT` / `SEED_CITY_LNG` | Mumbai | The point everything's seeded around |
| `CORS_ORIGINS` | `localhost:5173, localhost:3000` | Add your frontend origin if different |

---

## 🧪 Run the tests

```bash
cd backend
pytest tests/ -v
```

Covers: health check, hospital/ambulance listing, emergency creation, full dispatch pipeline, AI inference, login, KPIs.

---

## 🐛 Troubleshooting

| Symptom | Cause / Fix |
|---------|-------------|
| `python run.py` says "Python 3.10+ required" | Install Python 3.10+ from python.org and re-run. |
| Backend logs many "model file missing" warnings | Run `python -m app.ai.quick_train` from `backend/` (~90s) or run notebooks 1-5. |
| `pip install` fails on TensorFlow | TF is optional (used only by hotspot LSTM). The system works without it — you'll just get the heuristic hotspot forecast. To skip: comment out the `tensorflow*` lines in `requirements.txt`. |
| Port 8000 already in use | `python run.py --port 8001` |
| Want to start fresh | `python run.py --reset-db` (deletes `emergency.db` first) |
| Want to test backend in isolation | `python run.py --no-sim --no-frontend` (or `--backend-only`) |
| Backend works but simulator can't reach it | The simulator polls `http://localhost:8000` — adjust with `--backend` if running elsewhere. |
| `email-validator` rejects your custom admin email | Use a real-looking TLD (e.g. `.com`, `.org`) — `.local` is reserved. |
| `bcrypt` warns about `__about__` | Cosmetic issue with newer bcrypt + older passlib — safe to ignore. |
| Frontend can't load — `node` / `npm` not found | Install Node.js 18+ from https://nodejs.org/. The backend + simulator still run without it. |
| Map tiles don't load on the dashboard | Check internet connectivity to OpenStreetMap (`a.tile.openstreetmap.org`). No API key needed. |
| Frontend can't talk to backend | Vite dev server proxies `/auth`, `/emergencies`, `/socket.io`, etc. to `:8000` — confirm backend is up at `localhost:8000/health`. |
| Want a production frontend build | `cd frontend && npm run build` — output goes to `frontend/dist/`. |

---

## 🖥️ Frontend tour

Once `python run.py` is up, visit **http://localhost:5173** and sign in (`admin` / `admin123`). You get a 6-page mission-control console:

| Page | URL | What it does |
|------|-----|--------------|
| **Login** | `/login` | Branded split-panel terminal — no SSO, JWT-based |
| **Console** (Dashboard) | `/dashboard` | Live tactical map + 6 KPI cards + pending intake queue + active dispatches list. Click pending calls to fly the map; press **Dispatch now** to trigger the full AI pipeline. |
| **Intake** | `/intake` | Caller-intake form with **live AI triage chip** that updates as you type vitals/symptoms (debounced 350ms). Click anywhere on the map to set the incident location. **Create + Dispatch** in one shot. |
| **Fleet** | `/ambulances` | Ambulance roster with status filters (Available / En Route / On Scene / Transporting). Click a unit to fly the map and see crew, certification, and the active dispatch's ETA + destination. |
| **Facilities** | `/hospitals` | Per-hospital cards with bed-availability bars (general / ICU / trauma / pediatric / burns), ER wait, diversion flag, quality stars. Inline edit form for hospital staff to update beds & wait times. |
| **Analytics** | `/analytics` | LSTM hotspot heatmap (next-hour demand per zone), 24-hour bar chart, KPI strip. |

### Real-time channels

The frontend subscribes to all five Socket.IO channels — `ambulance:position`, `ambulance:status_change`, `emergency:created`, `emergency:dispatched`, `hospital:beds_updated`. New emergencies pop a **critical** toast; new dispatches pop an info toast; ambulances move on the map as the simulator drives them. The topbar's **LIVE** indicator pulses green while the socket is connected and turns red on disconnect — the dashboard also has an 8-second polling fallback so it never goes stale.

### Aesthetic & tech notes

- **Visual direction:** mission-control / 911 dispatch console — dark slate base (`#0a0e1a`), JetBrains Mono for IDs and data, Manrope for UI. Severity uses a 5-step signal palette (red / orange / amber / cyan / emerald).
- **Map:** React-Leaflet + OpenStreetMap, with a CSS filter (`hue-rotate(195deg) invert(.92) saturate(.6) brightness(.85)`) to give the tiles a dark theme without needing a paid tile provider.
- **Custom markers:** ambulances are status-colored divIcons with embedded SVG; emergencies have a pulsing ring whose intensity tracks predicted severity; hospitals use a ring-color whose hue reflects bed availability.
- **State:** Zustand (one store per entity type) — Socket.IO handlers mutate the stores directly, so the UI stays consistent across pages without prop drilling.
- **Bundling:** `npm run build` produces `dist/` ~250 KB gzipped. Vite dev server boots in ~600ms.

---

## 📜 License

MIT. Built for hackathon use.
