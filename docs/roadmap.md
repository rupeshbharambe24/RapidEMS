# RapidEMS — Roadmap to Surpass BlitzNova

Audit: where each system leads today, the path to close the gap, and the leap
beyond. Every BlitzNova lead is treated as the **floor** RapidEMS must clear
within Phase 0; Phases 1–3 push past anything BlitzNova has on the board.

Time estimates assume a single full-time engineer. Items inside a phase are
parallelisable unless an explicit dependency arrow is shown.

---

## Snapshot of the gap (today)

| Axis | RapidEMS today | BlitzNova today | Phase to close |
|---|---|---|---|
| Roles / dashboards | 1 (dispatcher) | 5 (patient, driver, hospital, dispatcher, admin) | 0 |
| Road routing | haversine + ML ETA | Google → ORS → haversine, A*-blend | 0 |
| DB | sync SQLAlchemy in async handlers | aiosqlite / asyncpg, Alembic | 0 |
| Notifications | Socket.IO only | SMS / push / hospital alerts (sim) | 0 |
| Pre-arrival ER briefing | none | OpenAI medical summary on dispatch | 0 |
| LLM caller intake | **Groq + Gemini, multilingual** | none | — RapidEMS leads |
| Per-model ML training | **5 notebooks with EDA + SHAP** | one training script | — RapidEMS leads |
| Code organisation | **schemas/ models/ split** | monolithic schemas.py / models.py | — RapidEMS leads |
| Frontend cohesion | **mission-control design system** | 4 dashboards, separate styles | — RapidEMS leads |
| FastAPI / TF / LLM versions | **0.115 / 2.18 / Llama 3.3 / Gemini 2.5** | 0.111 / 2.16 / OpenAI | — RapidEMS leads |

---

## Phase 0 — Floor clearance (match BlitzNova, ~7 days)

Goal: nothing BlitzNova has should be missing from RapidEMS by end of Phase 0.

### 0.1 Real road routing — `services/routing_service.py` (1 day)
- Multi-provider chain with health-checked failover:
  `Google Routes API → OpenRouteService → OSRM (self-hosted Docker) → haversine`
- Each provider returns `{seconds, meters, polyline, congestion_factor, provider}`.
- 120-second LRU cache keyed on `(from_lat, from_lng, to_lat, to_lng, hour_bucket)`.
- Wire into `dispatch_engine.py`:
  `final_eta = 0.7·road_eta + 0.3·ml_eta` (BlitzNova's blend) **plus**
  `congestion_factor` directly from the provider response, not just the
  Traffic ML model.
- Adds env vars: `GOOGLE_ROUTES_API_KEY`, `ORS_API_KEY`, `OSRM_URL`.
- New endpoint `GET /routing/preview?from=…&to=…` for the frontend's polyline.

### 0.2 Async SQLAlchemy migration (1 day) — depends on nothing
- Engine: `create_async_engine(...)`, sessions: `async_sessionmaker`.
- Replace every `Session = Depends(get_db)` with `AsyncSession`.
- Convert every `db.query(X)…first()` → `await db.scalar(select(X).where(...))`.
- Drivers: `aiosqlite` (dev), `asyncpg` (prod). Drop `psycopg2-binary` in
  favour of `asyncpg`.
- Acceptance: simulator pushes 10 PATCH/s for 30 min with no event-loop block.

### 0.3 Alembic migrations (½ day)
- `alembic init backend/migrations`, autogenerate from current models.
- Drop `Base.metadata.create_all()` from `lifespan`. Run
  `alembic upgrade head` in `run.py` phase 4 instead.

### 0.4 Multi-role auth + Patient dashboard (2 days)
- Roles: `dispatcher`, `paramedic`, `hospital_staff`, `admin`, `patient`.
- New tables: `patient_profiles`, `medical_records`, `hospital_alerts`,
  `family_links`.
- New router `api/patient.py`: profile CRUD, medical-record upload (MRI / CT
  / X-ray / blood-test / ECG / prescription), `POST /patient/sos`.
- New page `frontend/src/pages/PatientDashboard.jsx`: profile, record upload
  with drag-drop, raise-SOS button, live status with ambulance position +
  ETA countdown.

### 0.5 Ambulance driver dashboard (1 day)
- New page `AmbulanceDriver.jsx`: full-screen map, current dispatch card with
  patient summary + LLM-extracted notes, turn-by-turn polyline from 0.1,
  one-tap status updates (ON_SCENE / TRANSPORTING / AT_HOSPITAL / RETURNING).
- PWA manifest so it installs on Android in-vehicle tablets.

### 0.6 Hospital portal (1 day)
- New page `HospitalPortal.jsx`: incoming-pre-alert feed, ER bed-availability
  inline editor, accept / divert flow.
- Subscribes to Socket.IO channel `hospital:alert` (new).

### 0.7 Admin dashboard (½ day)
- New page `Admin.jsx`: user CRUD, role assignment, ambulance + hospital
  fleet management, audit-log viewer.

### 0.8 Notifications service — `services/notifications.py` (½ day)
- Channels: `sms_twilio`, `whatsapp_business`, `web_push_vapid`,
  `socket_room`, `email_smtp`, `console_log` (dev).
- `send(channel, recipient, message)` — pluggable adapters, env-key gated.
- Triggered on `dispatch_created` (patient SMS, hospital alert), on
  `ambulance:status_change` (patient + family), on `bed_threshold_low`
  (admin alert).

### 0.9 Pre-arrival ER briefing — `services/er_briefing.py` (½ day)
- Combine `ExtractedEmergency` from intake + patient profile + medical
  records + vitals into one Groq-generated medical summary.
- Save into `hospital_alerts.briefing` and push via Socket.IO at dispatch
  time.
- Better than BlitzNova's because the input is already structured.

### 0.10 Family tracking link (½ day)
- Time-limited signed URL (`itsdangerous` token, 4-hour TTL) shared via SMS
  to next-of-kin.
- Public `/track/{signed_token}` page: read-only ambulance position + ETA.

**Phase 0 exit criteria.** All 5 dashboards live; real road ETA in dispatch;
async DB; Alembic; SMS + WhatsApp + push working; ER briefing on every
dispatch; family link sharable.

---

## Phase 1 — Surpass on every axis BlitzNova leads (~7 days)

Goal: take each Phase-0 item one step further than BlitzNova ever went.

### 1.1 Routing — beyond BlitzNova's 3-tier
- Add **TomTom Traffic API** for real-time congestion overlays on the
  polyline (BlitzNova relies on a static congestion factor).
- Add **Mapbox Directions** as a 4th provider.
- Add **construction-zone exclusion** via Mumbai municipal open-data API
  (real if available, mocked otherwise).
- **Helicopter dispatch tier**: when SEV-1 + ground ETA > 12 min + a
  helipad-equipped hospital is within 30 km, propose air dispatch.
  `helicopter` becomes a new `AmbulanceType`.

### 1.2 Multi-emergency assignment — Hungarian algorithm
- When ≥ 2 pending emergencies exist, replace per-emergency greedy ambulance
  selection with a global cost-minimising assignment over the
  emergency × ambulance grid (`scipy.optimize.linear_sum_assignment`).
- Cost matrix entry = `severity_weight · final_eta`. Critical emergencies
  always claim the best ambulance even if a moderate one was logged earlier.
- New endpoint `POST /dispatches/optimize` runs the solver across all
  PENDING emergencies in one shot. Surfaces "would-be-better" reassignments
  as suggestions.

### 1.3 LLM intake → multimodal + streaming
- **Streaming live transcription**: WebSocket `/ws/intake/{session_id}`,
  pushes audio frames from the dispatcher's mic to **Gemini Live audio**
  (or Whisper). Form fields auto-fill in real time as the caller talks —
  not at the end of a paste.
- **Real-time translation**: caller speaks Marathi, dispatcher hears
  English on a side channel; transcript persists in both languages.
- **Photo of injury → severity hint**: Gemini multimodal endpoint accepting
  base64 images. Pre-fills `severe_burns` / `major_bleeding` / `head_trauma`
  before vitals are typed.

### 1.4 LLM dispatcher copilot — `POST /ai/copilot`
- Function-calling LLM (Groq tool-use) that sees the dispatcher's natural
  language ("show me ALS units within 5km of MG Road that have an AED")
  and emits API calls against `/ambulances`, `/hospitals`, `/dispatches`.
- Response is the function result + a one-line explanation.
- Wire as a slide-over panel in the dispatcher dashboard with `/` shortcut.

### 1.5 LLM triage explanation — `POST /ai/explain`
- Inputs: emergency_id (or full feature vector). Loads the severity
  classifier, runs SHAP locally, asks Groq to narrate the top contributing
  features in one paragraph: *"SEV-2 because GCS 11, SpO₂ 91, chest pain
  symptom — together drive 78% of the model's confidence."*
- Persisted to `audit_log.details.explanation` and shown as a tooltip on
  the severity pill.

### 1.6 Five extra ML models
- **Outcome predictor** (`outcome_lgbm.pkl`): given dispatch params,
  predicts probability of survival at 30 days. Drives priority in 1.2.
- **Equipment matcher**: matches required equipment (AED, IV pump, neonatal
  incubator) to ambulance inventory before scoring.
- **Paramedic-skill matcher**: when SEV-2 cardiac, prefer ambulances whose
  on-board paramedic has cardiac certification.
- **Drug interaction model**: when patient profile has current medications,
  flags risky in-ambulance interventions for the paramedic UI.
- **Hospital-wait predictor**: forecasts the ER wait at each candidate
  hospital from `traffic_snapshots`-style history. Feeds the recommender.

### 1.7 Wearable telemetry ingestion
- New router `api/telemetry.py` — accepts batches from Apple HealthKit /
  Google Fit / generic BLE BP-cuff JSON.
- Stored in new `patient_telemetry` time-series table; used as additional
  input to the severity classifier when present.

### 1.8 i18n — UI in EN / HI / MR / TA / BN
- `react-i18next`, English source-of-truth, Gemini-assisted bulk translation.
- Locale persisted per user; LLM prompts honour `Accept-Language`.
- Symptom labels also translated server-side from the canonical IDs.

### 1.9 Public transparency dashboard
- Read-only public page `/public/city`: anonymised aggregate response times,
  active emergencies count by zone, average ETA over last hour, hospital
  bed occupancy rolled up.
- Ranked best response zones — gives citizens visibility into system
  performance.

### 1.10 Family / NoK richer flow
- `family_links` table maps NoK phone to a tracking session.
- WhatsApp template message with live position. Works even if NoK has no
  app installed. WhatsApp deep-link for one-tap call to the dispatcher.

**Phase 1 exit criteria.** RapidEMS leads on every BlitzNova axis. Multi-
emergency optimisation, multimodal LLM intake, copilot, triage
explanations, 5 additional ML models, wearable data, multilingual UI.

---

## Phase 2 — Production hardening (~10 days)

These are categories BlitzNova doesn't address at all. Each one alone is a
demo differentiator.

### 2.1 Observability
- **OpenTelemetry** auto-instrumentation across FastAPI, SQLAlchemy, httpx.
- Prometheus metrics: dispatch latency p50/p95, LLM provider failover rate,
  pool checkout time, model inference latency, Socket.IO connection count.
- **Grafana dashboard** preconfigured (committed JSON).
- **Sentry** for unhandled exceptions; PR-blocking error budget.
- `/metrics` endpoint scraped by Prometheus.

### 2.2 Security
- Argon2id replacing bcrypt (passlib). Pepper from KMS.
- mTLS between simulator ↔ backend.
- **Column-level encryption** for PHI fields (patient_name, phone, address)
  with `cryptography.fernet` + keys from env / Vault.
- 2FA for hospital_staff and admin (TOTP via `pyotp`).
- Tamper-evident audit log: each row hashes the previous row's id +
  payload (`prev_hash`) — append-only chain detectable on any rewrite.
- Time-limited signed URLs for tracking, file downloads, family links.
- API rate-limiting with `slowapi`: 60 req/min per IP, 600 per token.

### 2.3 RBAC + ABAC
- `casbin` policy engine with route-level decorators.
- Cross-cutting attributes (e.g. hospital_staff sees only their hospital's
  alerts).

### 2.4 MLflow + model registry
- All 10 models tracked in MLflow with run params, metrics, artefacts.
- `ai_service` loads from MLflow registry rather than `ai_models/` files.
- Promotion gating: model graduates from `Staging` to `Production` only when
  validation accuracy ≥ baseline + drift score < threshold.

### 2.5 Online learning + drift monitoring
- Weekly retraining job (APScheduler) on dispatch outcomes (`actual_response_time_seconds` vs prediction).
- Feature distribution monitoring (Evidently AI). Alerts when KS-statistic
  on any input feature exceeds threshold for 24 h.

### 2.6 Self-hosted OSRM (Docker)
- `docker-compose.yml` adds an OSRM container with India.osm.pbf
  pre-processed.
- Removes external API dependency for dev; unlimited free routing.
- Fallback chain stays for prod (OSRM is the *primary* in dev, *fallback*
  in prod).

### 2.7 TimescaleDB for traffic + telemetry
- New service in compose. Migrate `traffic_snapshots` and the new
  `patient_telemetry` tables to hypertables.
- Continuous aggregates for analytics (`hourly_traffic`, `zone_hourly`).

### 2.8 Multi-tenancy
- `tenants` table; `tenant_id` foreign key on every domain table.
- Schema: tenant per city. Mumbai instance never sees Pune data even if
  someone leaks a token.
- Subdomain routing: `mumbai.rapidems.app`, `pune.rapidems.app`.

### 2.9 Offline-first paramedic PWA
- IndexedDB queue of unsent status updates while offline.
- `Background Sync` API replays the queue when network returns.
- Pre-cached map tiles for the active dispatch route.

### 2.10 Compliance posture (DPDP Act / HIPAA-equivalent)
- Data inventory + retention policies (auto-purge resolved emergencies'
  PII after 90 days).
- Consent receipts on patient registration.
- Subject Access Request endpoint (`POST /patient/dsr`).

**Phase 2 exit criteria.** Production-grade observability, security
hardening, multi-tenant capable, compliant data handling, self-hostable
without paid APIs.

---

## Phase 3 — Pure leapfrog differentiators (~10 days)

Things BlitzNova has zero presence in.

### 3.1 Cinematic demo + replay mode
- Pre-scripted incident playbooks (`demos/cardiac_chain.json`,
  `demos/multi_casualty_bus.json`) — each is an ordered sequence of
  emergency injections with expected dispatch decisions.
- `python -m demo.run cardiac_chain` injects synthetic SOSes at the
  configured cadence; the dashboard plays out as if real.
- **Replay**: every dispatch persisted as an event log; `/replay/{id}`
  page time-warps the map back through that incident's timeline.

### 3.2 Predictive ambulance pre-positioning
- Cron job consumes the LSTM hotspot 24-h forecast; computes the optimal
  set of "park here at 19:00" instructions for currently-idle ambulances
  (linear programming with `pulp`).
- Pushes a non-emergency `staging:position` Socket.IO event to drivers.

### 3.3 Mass casualty incident (MCI) mode
- Dispatcher toggles MCI on; system enters a different mode where the
  dispatch engine maximises throughput instead of per-emergency optimality.
- Triages on-scene patients with a categorical START / SALT model
  (separate notebook), assigns them to ambulances + hospitals via the
  Hungarian solver from 1.2.

### 3.4 Voice-first dispatcher mode
- Wake-word ("RapidEMS, …") → command goes to copilot LLM (1.4).
- Hands-free workflow: "RapidEMS, dispatch the nearest ALS to the new
  call" — system reads back the plan, awaits confirm.

### 3.5 AR navigation for paramedics
- WebXR overlay on the driver's phone-on-windscreen mount: arrows on
  the road, lane callouts, hazard markers from real-time incident reports.

### 3.6 Drone reconnaissance
- For SEV-1 multi-casualty, a drone is pre-dispatched (mock for demo,
  DJI SDK if available). Streams a first-look video to the dispatcher
  before the ambulance arrives.

### 3.7 Federated learning
- Hospitals run a local FL client (`flwr`); models train on aggregated
  gradient updates without ever sharing patient rows.
- Demo path: simulate 3 hospital clients, show convergence vs
  centrally-trained baseline.

### 3.8 Differential-privacy analytics
- All public analytics queries pass through Google's `tmlt-analytics`
  with ε-budget enforcement. Public dashboard shows the privacy budget
  consumed.

### 3.9 Insurance verification at intake
- Mock NHA / private-insurer API integration. At intake, surface the
  patient's network hospitals and copay so the recommender can prefer
  network providers when clinical fit is comparable.

### 3.10 "What-if" simulator (chaos lab)
- A separate UI mode runs synthetic emergencies at 10× real-world rate,
  surfaces system bottlenecks (which models lag, which providers fail
  first, where the pool runs out).
- Output: a one-page "max sustainable load" report.

---

## Cross-cutting work (all phases)

### Testing
- **k6 load tests**: simulate 200 ambulances + 50 concurrent emergencies.
  CI gate on p95 ≤ 800 ms for `POST /emergencies/{id}/dispatch`.
- **Playwright E2E**: dispatcher flow, patient SOS flow, hospital alert
  acceptance — runs on every PR.
- **Chaos**: kill backend mid-dispatch, simulator must reconnect; kill
  Groq, intake must Gemini-fall-through.
- **Model drift**: nightly check of feature distributions against
  training-set baseline.

### CI / CD
- GitHub Actions workflow: lint (ruff + eslint), type-check (mypy + tsc),
  unit tests, integration tests with mocked external APIs, Docker image
  build, k6 smoke.
- Trivy / Bandit security scan on every PR.
- Auto-deploy preview environments per PR (Fly.io / Render).

### Documentation
- `docs/architecture.md` — sequence diagrams of every flow.
- `docs/runbook.md` — on-call playbook for each failure mode.
- `docs/security.md` — threat model + STRIDE table.
- `docs/data-model.md` — ERD generated from SQLAlchemy on every PR.

---

## Sequencing summary

```
Week 1  ─►  Phase 0.1 routing  ║  0.2 async DB  ║  0.3 Alembic
                ▼                       ▼              ▼
            0.4 patient role  ─►  0.5 driver  ─►  0.6 hospital portal
                                                    ▼
            0.8 notifications  ─►  0.9 ER briefing  ─►  0.10 family link
                                                    ▼
            0.7 admin dashboard  (final cleanup)
                                                    ▼
Week 2  ─►  Phase 1.1 routing+  ║  1.2 Hungarian  ║  1.3 streaming LLM
                ▼                       ▼                ▼
            1.4 copilot         1.5 explain       1.6 +5 ML models
                                                    ▼
            1.7 wearables  ─►  1.8 i18n  ─►  1.9 public dash  ─►  1.10 family
                                                    ▼
Week 3-4 ─► Phase 2 hardening (parallelisable)
                                                    ▼
Week 5-6 ─► Phase 3 leapfrog features (each one independent)
```

---

## Decision points the user should decide before Week 2

1. **Hosting target**: Render / Fly.io / AWS? Determines Phase 2.6 / 2.8
   shape.
2. **Real or simulated SMS / WhatsApp at demo time**: Twilio costs ~$0.01
   per SMS. WhatsApp Business is paid + needs approval (1-3 weeks).
3. **Real Google Routes / Mapbox key now, or rely on free OSRM tier**:
   affects Phase 0.1 / 1.1 cost and timing.
4. **Real OpenAI for ER briefing, or stick to Groq**: Groq doesn't currently
   host a strong medical-summary model; Gemini does. Could run ER briefings
   on Gemini and intake on Groq — consistent with the speed-vs-quality
   split we already have.
5. **MCI mode (Phase 3.3): include in scope, or future**: it's the most
   demo-impactful Phase-3 item but also the most complex.

---

## What "ten steps ahead" looks like at the end

| Axis | RapidEMS at end of roadmap | BlitzNova today |
|---|---|---|
| Roles | 5 + family + paramedic mobile + 911 call-taker + ER triage prep | 5 |
| Routing providers | 5 (Google, Mapbox, ORS, OSRM self-hosted, haversine) + TomTom traffic + helicopter tier | 3 |
| Dispatch optimisation | Hungarian global, multi-emergency, severity-weighted | greedy per-emergency |
| LLM intake | streaming, multimodal, multilingual, multi-provider | n/a |
| LLM elsewhere | copilot, explanations, ER briefing, post-incident report | ER summary only |
| ML models | 10 (5 original + outcome, equipment, skill, drug, ER-wait) | 5 |
| Async DB | aiosqlite + asyncpg + Alembic | aiosqlite + asyncpg + Alembic |
| Notifications | SMS + WhatsApp + push + email + SIP fallback | SMS + push (sim) |
| Patient experience | upload + auto-summary + wearable telemetry + family link + tracking | upload + SOS |
| Multi-tenancy | yes | no |
| Observability | OTEL + Prometheus + Grafana + Sentry | none visible |
| Security | Argon2 + mTLS + column encryption + 2FA + audit hash chain + rate limit | JWT + bcrypt |
| MLflow / online learning | yes | no |
| Compliance | DPDP / HIPAA-equivalent posture | no |
| Demo modes | cinematic playbooks + replay + chaos lab + MCI | none |
| Federated learning | yes | no |
| Differential privacy | yes (public analytics) | no |

That's the "ten steps ahead" target. Phase 0 + 1 alone (two weeks) already
puts RapidEMS strictly ahead on every existing axis; Phases 2 and 3 turn
the lead into a moat.
