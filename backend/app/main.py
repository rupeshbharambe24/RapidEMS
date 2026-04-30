"""FastAPI application entry point.

Run with:
    uvicorn backend.app.main:asgi --host 0.0.0.0 --port 8000 --reload
or via the project root:
    python run.py
"""
import time
from contextlib import asynccontextmanager

import socketio
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from .api import (admin, ai as ai_routes, ambulances, analytics, auth,
                  copilot, dispatches, driver, emergencies, hospital_portal,
                  hospitals, notifications, patient, public, routing,
                  telemetry, tracking)
from .config import settings
from .core.logging import log
from .core.startup_check import run_startup_checks
from .database import AsyncSessionLocal, create_all_tables
from .observability.metrics import (http_latency, http_requests,
                                    refresh_gauges_from_db, render_metrics)
from .seed import seed_database
from .services.ai_service import get_ai_service
from .sockets.sio import sio


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("=" * 60)
    log.info(f" 🚑 AI Emergency Response System — backend starting")
    log.info(f"    Database: {settings.database_url}")
    log.info(f"    Models:   {settings.models_dir}")
    log.info("=" * 60)

    # 1. Tables
    await create_all_tables()
    log.success("Database tables ready ✓")

    # 2. Seed
    if settings.seed_on_startup:
        async with AsyncSessionLocal() as db:
            await seed_database(db)

    # 3. Startup health checks (warns about missing model files)
    run_startup_checks()

    # 4. Pre-warm AI service (loads all models into RAM once)
    get_ai_service()

    log.success("Backend ready — visit http://localhost:8000/docs for the API explorer.")
    yield
    log.info("Backend shutting down…")


app = FastAPI(
    title="AI Emergency Response & Ambulance Coordination API",
    version="1.0.0",
    description=(
        "Triage emergencies, dispatch the nearest ambulance, route to the best hospital — "
        "powered by 5 trained ML models."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _metrics_middleware(request: Request, call_next):
    """HTTP request count + latency histogram. Uses the route template
    (``/emergencies/{id}``) rather than the concrete path to keep label
    cardinality bounded."""
    t0 = time.perf_counter()
    response: Response = await call_next(request)
    elapsed = time.perf_counter() - t0

    route = request.url.path
    # FastAPI exposes the matched APIRoute on request.scope["route"] — use
    # its path template if available, fall back to the raw URL otherwise.
    try:
        scope_route = request.scope.get("route")
        if scope_route and getattr(scope_route, "path", None):
            route = scope_route.path
    except Exception:  # noqa: BLE001
        pass

    status_class = f"{response.status_code // 100}xx"
    http_requests.labels(method=request.method, route=route,
                         status=status_class).inc()
    http_latency.labels(method=request.method, route=route).observe(elapsed)
    return response


@app.get("/metrics", tags=["meta"], include_in_schema=False)
async def metrics():
    """Prometheus scrape target. Refreshes the system gauges from the DB
    so each scrape sees fresh state."""
    try:
        await refresh_gauges_from_db()
    except Exception as exc:  # noqa: BLE001
        log.warning(f"metrics: gauge refresh failed: {exc}")
    body, content_type = render_metrics()
    return Response(content=body, media_type=content_type)


@app.exception_handler(Exception)
async def universal_exception_handler(request, exc):
    """Catch-all so the frontend never sees a raw 500 with no body."""
    log.exception(f"Unhandled exception on {request.url.path}: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error.", "error": str(exc)},
    )


# Routers
app.include_router(auth.router)
app.include_router(emergencies.router)
app.include_router(ambulances.router)
app.include_router(hospitals.router)
app.include_router(dispatches.router)
app.include_router(ai_routes.router)
app.include_router(analytics.router)
app.include_router(routing.router)
app.include_router(patient.router)
app.include_router(driver.router)
app.include_router(hospital_portal.router)
app.include_router(admin.router)
app.include_router(notifications.router)
app.include_router(tracking.router)
app.include_router(copilot.router)
app.include_router(public.router)
app.include_router(telemetry.router)


@app.get("/", tags=["meta"])
def root():
    return {
        "service": "AI Emergency Response Backend",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health", tags=["meta"])
def health():
    from .core.startup_check import check_models
    present, missing = check_models()
    return {
        "status": "ok",
        "models_present": len(present),
        "models_missing": len(missing),
        "missing_model_files": missing,
        "fallback_enabled": settings.allow_heuristic_fallback,
    }


# ── Wrap FastAPI with Socket.IO ───────────────────────────────
# `asgi` is the actual ASGI callable that uvicorn should serve.
asgi = socketio.ASGIApp(sio, other_asgi_app=app, socketio_path="/socket.io")
