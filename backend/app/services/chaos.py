"""Chaos lab — controlled fault injection for resilience testing.

Lets an admin reproduce real failure modes — a routing provider going
down, the severity model lagging, dispatch occasionally failing — so
the team can verify the system degrades gracefully under each.

What's injectable:

* ``routing_provider_down`` — a named provider (osrm / ors / mapbox /
  here) raises immediately when called, forcing the chain to fall
  through. Verifies the haversine fallback is wired correctly and
  metrics record the failure.
* ``severity_predictor_slow`` — adds a synthetic delay (ms) before the
  classifier returns. Demonstrates that callers tolerate slow AI
  without blocking the dispatch path.
* ``dispatch_failure_rate`` — flips a deterministic coin on every
  dispatch attempt and raises ``DispatchError`` for the requested
  fraction. Stresses retry / re-route logic.

State lives module-level so the hooks throughout the codebase can
check it cheaply (one dict lookup, no IO). Nothing here mutates the
database — every effect is reversed by ``clear`` or by restarting the
backend.
"""
from __future__ import annotations

import asyncio
import random
import time
from typing import Dict, List, Optional


# ── Scenario registry ─────────────────────────────────────────────────────
KNOWN_SCENARIOS = {
    "routing_provider_down",
    "severity_predictor_slow",
    "dispatch_failure_rate",
}

# Internal store: scenario name → params dict. We index by scenario
# name (not opaque IDs) so a re-injection updates the existing entry —
# you can't have two simultaneous "routing provider down" with
# conflicting params, which is the right behavior.
_active: Dict[str, Dict[str, object]] = {}
_seed = 0   # bumped on each inject so dispatch_failure_rate gets a
            # deterministic-but-reshuffled coin sequence per session.


def inject(scenario: str, **params: object) -> Dict[str, object]:
    """Register a fault. Returns the active record."""
    global _seed
    if scenario not in KNOWN_SCENARIOS:
        raise ValueError(f"Unknown chaos scenario '{scenario}'. "
                         f"Available: {sorted(KNOWN_SCENARIOS)}")
    _seed += 1
    record = {**params, "scenario": scenario,
              "injected_at": time.time(), "seed": _seed}
    _active[scenario] = record
    return record


def clear(scenario: Optional[str] = None) -> int:
    """Remove one (or all) active faults. Returns count removed."""
    if scenario is None:
        n = len(_active)
        _active.clear()
        return n
    if scenario in _active:
        _active.pop(scenario)
        return 1
    return 0


def status() -> List[Dict[str, object]]:
    return list(_active.values())


def is_active(scenario: str) -> bool:
    return scenario in _active


# ── Hook helpers ──────────────────────────────────────────────────────────
def is_routing_provider_down(provider_name: str) -> bool:
    """Called by ``routing_service.route`` before invoking each provider."""
    rec = _active.get("routing_provider_down")
    if not rec:
        return False
    target = str(rec.get("provider", "")).lower()
    return target in ("*", "all") or target == provider_name.lower()


async def maybe_delay_severity() -> None:
    """Awaited at the top of severity-prediction hot paths."""
    rec = _active.get("severity_predictor_slow")
    if not rec:
        return
    delay_ms = float(rec.get("delay_ms", 0) or 0)
    if delay_ms > 0:
        await asyncio.sleep(delay_ms / 1000.0)


def maybe_fail_dispatch(emergency_id: int) -> Optional[str]:
    """Called by ``dispatch_engine`` before scoring units. Returns a
    reason string when chaos says to fail this attempt, else None.

    Decision is deterministic from emergency_id + the chaos seed so
    the same scenario reproduces consistently across runs."""
    rec = _active.get("dispatch_failure_rate")
    if not rec:
        return None
    rate = float(rec.get("rate", 0.0) or 0.0)
    if rate <= 0.0:
        return None
    seed = int(rec.get("seed", 0))
    rng = random.Random(emergency_id * 9973 + seed)
    if rng.random() < rate:
        return f"chaos: dispatch_failure_rate={rate:.2f}"
    return None
