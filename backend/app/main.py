"""FastAPI application entry point.

Run with:
    uvicorn backend.app.main:asgi --host 0.0.0.0 --port 8000 --reload
or via the project root:
    python run.py
"""
from contextlib import asynccontextmanager

import socketio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api import (ai as ai_routes, ambulances, analytics, auth, dispatches,
                  emergencies, hospitals, patient, routing)
from .config import settings
from .core.logging import log
from .core.startup_check import run_startup_checks
from .database import AsyncSessionLocal, create_all_tables
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
