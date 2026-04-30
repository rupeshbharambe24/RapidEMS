"""Prometheus metrics surface.

A single registry, named ``rapidems``, with five families of metrics:

  HTTP            request counts + latency histogram per (method, route, status)
  Dispatch       latency histogram + per-severity / per-outcome counters
  LLM             per-provider call counts + latency histogram
  Routing         per-provider call counts + latency histogram
  System gauges   currently-active dispatches, pending emergencies,
                  available ambulances, hospitals on diversion (refreshed
                  on every /metrics scrape so Prom always sees fresh state).

Emit through the helpers exposed at the bottom of this module so the call
sites stay clean and the metric definitions live in one place.
"""
from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Optional

from prometheus_client import (CONTENT_TYPE_LATEST, CollectorRegistry, Counter,
                               Gauge, Histogram, generate_latest)

# Single registry so /metrics doesn't expose Python's default process metrics
# (we'll re-add them explicitly below to keep it tight).
REGISTRY = CollectorRegistry(auto_describe=True)

# Default Python process metrics — useful for free-tier sanity (mem, fds).
from prometheus_client import (PROCESS_COLLECTOR, PLATFORM_COLLECTOR,
                                GC_COLLECTOR)
REGISTRY.register(PROCESS_COLLECTOR)
REGISTRY.register(PLATFORM_COLLECTOR)
REGISTRY.register(GC_COLLECTOR)


# ── HTTP ──────────────────────────────────────────────────────────────────
http_requests = Counter(
    "rapidems_http_requests_total",
    "HTTP requests by method, route, and status class",
    ["method", "route", "status"],
    registry=REGISTRY,
)
http_latency = Histogram(
    "rapidems_http_request_duration_seconds",
    "HTTP request handler latency in seconds",
    ["method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    registry=REGISTRY,
)


# ── Dispatch pipeline ─────────────────────────────────────────────────────
dispatch_latency = Histogram(
    "rapidems_dispatch_seconds",
    "End-to-end dispatch_emergency() wall time",
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0),
    registry=REGISTRY,
)
dispatch_total = Counter(
    "rapidems_dispatch_total",
    "Dispatches by severity and outcome",
    ["severity", "outcome"],
    registry=REGISTRY,
)


# ── LLM ──────────────────────────────────────────────────────────────────
llm_calls = Counter(
    "rapidems_llm_calls_total",
    "LLM calls by provider, surface, and outcome",
    ["provider", "surface", "outcome"],
    registry=REGISTRY,
)
llm_latency = Histogram(
    "rapidems_llm_latency_seconds",
    "LLM round-trip latency",
    ["provider", "surface"],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0),
    registry=REGISTRY,
)


# ── Routing ──────────────────────────────────────────────────────────────
routing_calls = Counter(
    "rapidems_routing_calls_total",
    "Road-routing provider calls by outcome",
    ["provider", "outcome"],
    registry=REGISTRY,
)
routing_latency = Histogram(
    "rapidems_routing_latency_seconds",
    "Road-routing provider round-trip latency",
    ["provider"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0),
    registry=REGISTRY,
)
routing_fallback_total = Counter(
    "rapidems_routing_fallback_total",
    "How often the chain fell through to the haversine fallback",
    registry=REGISTRY,
)


# ── System gauges (refreshed on /metrics scrape) ──────────────────────────
active_dispatches_g = Gauge(
    "rapidems_active_dispatches",
    "Dispatches in {dispatched,en_route,on_scene,transporting} states",
    registry=REGISTRY,
)
pending_emergencies_g = Gauge(
    "rapidems_pending_emergencies",
    "Emergencies still in PENDING state",
    registry=REGISTRY,
)
available_ambulances_g = Gauge(
    "rapidems_available_ambulances",
    "Active ambulances currently flagged AVAILABLE",
    registry=REGISTRY,
)
hospitals_on_diversion_g = Gauge(
    "rapidems_hospitals_on_diversion",
    "Active hospitals currently on diversion",
    registry=REGISTRY,
)


# ── Helpers ──────────────────────────────────────────────────────────────
@contextmanager
def time_dispatch():
    """Times the dispatch path. Use as ``with time_dispatch():``."""
    t0 = time.perf_counter()
    try:
        yield
    finally:
        dispatch_latency.observe(time.perf_counter() - t0)


def record_dispatch_outcome(severity: int, ok: bool) -> None:
    dispatch_total.labels(severity=str(severity),
                          outcome="ok" if ok else "fail").inc()


def record_llm(provider: str, surface: str, ok: bool,
               latency_ms: Optional[int] = None) -> None:
    llm_calls.labels(provider=provider, surface=surface,
                     outcome="ok" if ok else "fail").inc()
    if latency_ms is not None:
        llm_latency.labels(provider=provider, surface=surface).observe(
            latency_ms / 1000.0)


def record_routing(provider: str, ok: bool,
                   latency_seconds: Optional[float] = None) -> None:
    routing_calls.labels(provider=provider,
                         outcome="ok" if ok else "fail").inc()
    if latency_seconds is not None:
        routing_latency.labels(provider=provider).observe(latency_seconds)


def record_routing_fallback() -> None:
    routing_fallback_total.inc()


# ── Snapshot for /metrics ────────────────────────────────────────────────
async def refresh_gauges_from_db() -> None:
    """Pull the four system gauges from the DB. Cheap aggregate queries —
    runs on every /metrics scrape (Prom default 15s)."""
    from sqlalchemy import func, select

    from ..database import AsyncSessionLocal
    from ..models.ambulance import Ambulance, AmbulanceStatus
    from ..models.dispatch import Dispatch
    from ..models.emergency import Emergency
    from ..models.hospital import Hospital

    async with AsyncSessionLocal() as db:
        active = await db.scalar(
            select(func.count(Dispatch.id))
            .where(Dispatch.status.in_(
                ["dispatched", "en_route", "on_scene", "transporting"]))
        ) or 0
        pending = await db.scalar(
            select(func.count(Emergency.id))
            .where(Emergency.status == "pending")
        ) or 0
        avail = await db.scalar(
            select(func.count(Ambulance.id))
            .where(Ambulance.status == AmbulanceStatus.AVAILABLE.value,
                   Ambulance.is_active == True)
        ) or 0
        diversion = await db.scalar(
            select(func.count(Hospital.id))
            .where(Hospital.is_diversion == True, Hospital.is_active == True)
        ) or 0

    active_dispatches_g.set(int(active))
    pending_emergencies_g.set(int(pending))
    available_ambulances_g.set(int(avail))
    hospitals_on_diversion_g.set(int(diversion))


def render_metrics() -> tuple[bytes, str]:
    """Return (body, content_type) for the /metrics route."""
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST
