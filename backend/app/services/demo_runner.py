"""Cinematic demo + replay.

Runs a scripted scenario as a background task, threading real rows through
the standard pipeline (Emergency rows are created normally, dispatch is
triggered through ``dispatch_engine``, MCI victims are registered through
``services.mci``). The audience sees the same UI a real shift would —
the only difference is that the events are scripted and timed.

Two surfaces:

* **start_scenario / stop_scenario / status**: drive a live demo. The
  runner emits ``demo:narration`` events alongside the normal real-time
  channels so the dashboard can overlay subtitles ("Caller reports
  crushing chest pain → severity 1 predicted → ALS-1009 dispatched").

* **start_replay / replay_status**: re-emit a captured event log at the
  original cadence (or a multiplier). Replays do **not** touch the
  database — they only re-emit the captured Socket.IO frames so the
  dashboard renders an identical sequence. Useful for repeatable demos
  without polluting state.

Capture is automatic: every live demo writes its frames to
``backend/replays/<scenario>-<unix>.jsonl`` so any run can be replayed
later.
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..core.logging import log
from ..database import AsyncSessionLocal
from ..models.emergency import Emergency, EmergencyStatus
from ..models.mci import MciIncident, MciStatus
from ..services.dispatch_engine import DispatchError, dispatch_emergency
from ..services.mci import (execute_mci, get_active_incident, optimize_mci,
                            start_classify)
from ..models.mci import MciVictim
from ..sockets.sio import (emit_emergency_created, emit_emergency_dispatched,
                           sio)


REPLAY_DIR = Path(__file__).resolve().parents[2] / "replays"
REPLAY_DIR.mkdir(parents=True, exist_ok=True)


# ── Narration channel ─────────────────────────────────────────────────────
async def _narrate(session_id: str, text: str, kind: str = "info") -> dict:
    payload = {"session_id": session_id, "text": text, "kind": kind,
               "ts": time.time()}
    await sio.emit("demo:narration", payload)
    return payload


# ── Beat definitions ──────────────────────────────────────────────────────
@dataclass
class Beat:
    """One scripted action with a delay before it fires."""
    delay_s: float
    kind: str
    payload: Dict[str, Any] = field(default_factory=dict)


def _coords(offset_lat: float = 0.0, offset_lng: float = 0.0) -> Dict[str, float]:
    """Lat/lng helper using the model's column names so it can be splatted
    straight into the Emergency / MciIncident constructors."""
    return {
        "location_lat": settings.seed_city_lat + offset_lat,
        "location_lng": settings.seed_city_lng + offset_lng,
    }


# Built-in scenarios. Each is a sequence of beats. Delays are *between*
# beats so a 0.0 delay fires immediately after the previous one.
SCENARIOS: Dict[str, List[Beat]] = {
    # 1) Single 911-style cardiac call → triage → dispatch → arrival.
    "cardiac_chain": [
        Beat(0.0, "narrate", {"text": "Caller reports crushing chest pain, age 58."}),
        Beat(1.0, "emergency", {
            "chief_complaint": "Severe chest pain radiating to left arm",
            "symptoms": ["chest_pain", "shortness_of_breath", "sweating"],
            "patient_age": 58, "patient_gender": "male",
            "pulse_rate": 130, "blood_pressure_systolic": 90,
            "respiratory_rate": 24, "spo2": 89.0,
            "inferred_patient_type": "cardiac",
            **_coords(0.012, -0.008),
            "location_address": "Demo: Bandra West",
        }),
        Beat(1.5, "narrate", {"text": "Severity classifier → 1 (critical). Triggering dispatch."}),
        Beat(0.5, "dispatch_last"),
        Beat(2.0, "narrate", {"text": "Pre-arrival ER briefing pushed to receiving hospital."}),
    ],

    # 2) Three concurrent calls → Hungarian optimiser sorts them.
    "multi_dispatch": [
        Beat(0.0, "narrate", {"text": "Three calls arrive within 90 s. Watch the multi-dispatch optimiser."}),
        Beat(1.0, "emergency", {
            "chief_complaint": "Cardiac arrest",
            "symptoms": ["unresponsive", "no_pulse"],
            "patient_age": 65, "patient_gender": "female",
            "inferred_patient_type": "cardiac",
            **_coords(0.020, 0.010),
            "location_address": "Demo: Andheri",
        }),
        Beat(1.0, "emergency", {
            "chief_complaint": "RTA, suspected pelvic fracture",
            "symptoms": ["trauma", "bleeding", "leg_pain"],
            "patient_age": 32, "patient_gender": "male",
            "inferred_patient_type": "trauma",
            **_coords(-0.015, 0.025),
            "location_address": "Demo: Powai",
        }),
        Beat(1.0, "emergency", {
            "chief_complaint": "Stroke symptoms — right-side weakness",
            "symptoms": ["facial_droop", "slurred_speech"],
            "patient_age": 71, "patient_gender": "female",
            "inferred_patient_type": "stroke",
            **_coords(0.025, -0.020),
            "location_address": "Demo: Worli",
        }),
        Beat(2.0, "narrate", {"text": "All three pending. Running Hungarian optimiser…"}),
        Beat(0.5, "optimize_pending"),
        Beat(1.5, "narrate", {"text": "Global minimum cost assignment applied."}),
    ],

    # 3) MCI declared → 5 victims START-triaged → optimiser dispatches.
    "mci_bus_crash": [
        Beat(0.0, "narrate", {"text": "Bus rollover with multiple casualties. Declaring MCI."}),
        Beat(1.0, "mci_declare", {
            "name": "Demo: Bus rollover, Eastern Expressway",
            **{"location_lat": settings.seed_city_lat + 0.030,
               "location_lng": settings.seed_city_lng + 0.015},
            "estimated_victim_count": 5,
        }),
        Beat(1.5, "mci_victim", {
            "label": "V1", "age": 28, "gender": "male",
            "can_walk": False, "breathing": True, "respiratory_rate": 36,
            "pulse_rate": 130, "follows_commands": False,
        }),
        Beat(1.0, "mci_victim", {
            "label": "V2", "age": 45, "gender": "female",
            "can_walk": True, "breathing": True, "respiratory_rate": 18,
            "pulse_rate": 90, "follows_commands": True,
        }),
        Beat(1.0, "mci_victim", {
            "label": "V3", "age": 9, "gender": "male",
            "can_walk": False, "breathing": False,  # apneic → BLACK
        }),
        Beat(1.0, "mci_victim", {
            "label": "V4", "age": 62, "gender": "female",
            "can_walk": False, "breathing": True, "respiratory_rate": 24,
            "pulse_rate": 110, "follows_commands": True,
        }),
        Beat(1.0, "mci_victim", {
            "label": "V5", "age": 35, "gender": "male",
            "can_walk": False, "breathing": True, "respiratory_rate": 40,
            "pulse_rate": 140, "follows_commands": False,
        }),
        Beat(2.0, "narrate", {"text": "5 victims triaged. Running MCI optimiser…"}),
        Beat(0.5, "mci_optimize"),
        Beat(1.5, "narrate", {"text": "Reds dispatched first by Hungarian cost matrix."}),
    ],
}


# ── Runner state ──────────────────────────────────────────────────────────
@dataclass
class RunnerState:
    session_id: str
    scenario: str
    speed: float
    started_at: float
    total_beats: int
    current_beat: int = 0
    last_narration: str = ""
    last_emergency_id: Optional[int] = None
    finished: bool = False
    error: Optional[str] = None
    capture_path: Optional[str] = None
    events_captured: int = 0


_runner: Optional[RunnerState] = None
_runner_task: Optional[asyncio.Task] = None
_runner_lock = asyncio.Lock()


def _make_session_id(scenario: str) -> str:
    return f"{scenario}-{int(time.time())}"


# ── Beat dispatchers ──────────────────────────────────────────────────────
async def _do_emergency(state: RunnerState, db: AsyncSession,
                        payload: Dict[str, Any], capture: List[dict]) -> None:
    """Create an Emergency row and emit emergency:created.

    Keeps the same shape the REST handler uses so dashboards don't notice
    the difference. We do *not* auto-dispatch here — the dispatch_last
    beat triggers that explicitly so the narration can sit between.
    """
    e = Emergency(**payload)
    db.add(e)
    await db.commit()
    await db.refresh(e)
    state.last_emergency_id = e.id
    frame = {
        "event": "emergency:created",
        "data": {
            "id": e.id, "lat": e.location_lat, "lng": e.location_lng,
            "status": e.status, "address": e.location_address,
            "chief_complaint": e.chief_complaint, "symptoms": e.symptoms,
        },
    }
    await emit_emergency_created(frame["data"])
    capture.append({"t": time.time() - state.started_at, **frame})
    state.events_captured += 1


async def _do_dispatch_last(state: RunnerState, db: AsyncSession,
                            capture: List[dict]) -> None:
    if state.last_emergency_id is None:
        return
    e = await db.scalar(
        select(Emergency).where(Emergency.id == state.last_emergency_id))
    if not e or e.status != EmergencyStatus.PENDING.value:
        return
    try:
        plan = await dispatch_emergency(db, e)
    except DispatchError as exc:
        state.error = f"dispatch failed: {exc}"
        return
    payload = plan.model_dump()
    await emit_emergency_dispatched(payload)
    capture.append({"t": time.time() - state.started_at,
                    "event": "emergency:dispatched", "data": payload})
    state.events_captured += 1


async def _do_optimize_pending(state: RunnerState, db: AsyncSession,
                               capture: List[dict]) -> None:
    """Run the multi-emergency Hungarian optimiser and dispatch the picks."""
    from ..services.multi_dispatch import optimize as multi_optimize
    proposals, _unassigned, plans = await multi_optimize(db, preview=False)
    for plan in plans:
        if plan:
            await emit_emergency_dispatched(plan.model_dump())
            capture.append({"t": time.time() - state.started_at,
                            "event": "emergency:dispatched",
                            "data": plan.model_dump()})
            state.events_captured += 1


async def _do_mci_declare(state: RunnerState, db: AsyncSession,
                          payload: Dict[str, Any], capture: List[dict]) -> None:
    existing = await get_active_incident(db)
    if existing:
        # Re-use it; some scenarios may declare twice across runs.
        return
    inc = MciIncident(**payload)
    db.add(inc)
    await db.commit()
    await db.refresh(inc)
    frame = {"event": "mci:declared",
             "data": {"id": inc.id, "name": inc.name,
                      "lat": inc.location_lat, "lng": inc.location_lng}}
    await sio.emit("mci:declared", frame["data"])
    capture.append({"t": time.time() - state.started_at, **frame})
    state.events_captured += 1


async def _do_mci_victim(state: RunnerState, db: AsyncSession,
                         payload: Dict[str, Any], capture: List[dict]) -> None:
    inc = await get_active_incident(db)
    if not inc:
        return
    cat = start_classify(
        can_walk=payload.get("can_walk"), breathing=payload.get("breathing"),
        respiratory_rate=payload.get("respiratory_rate"),
        pulse_rate=payload.get("pulse_rate"),
        capillary_refill_seconds=payload.get("capillary_refill_seconds"),
        follows_commands=payload.get("follows_commands"),
    )
    v = MciVictim(incident_id=inc.id, category=cat, **payload)
    db.add(v)
    await db.commit()
    await db.refresh(v)
    frame = {"event": "mci:victim_registered",
             "data": {"id": v.id, "label": v.label, "category": cat}}
    await sio.emit("mci:victim_registered", frame["data"])
    capture.append({"t": time.time() - state.started_at, **frame})
    state.events_captured += 1


async def _do_mci_optimize(state: RunnerState, db: AsyncSession,
                           capture: List[dict]) -> None:
    proposals, plans = await execute_mci(db)
    for plan in plans:
        await emit_emergency_dispatched(plan.model_dump())
        capture.append({"t": time.time() - state.started_at,
                        "event": "emergency:dispatched",
                        "data": plan.model_dump()})
        state.events_captured += 1


# ── Main runner ───────────────────────────────────────────────────────────
async def _run_scenario(state: RunnerState, beats: List[Beat]) -> None:
    capture: List[dict] = []
    try:
        async with AsyncSessionLocal() as db:
            for i, beat in enumerate(beats):
                if state.finished:
                    break
                # Speed multiplier compresses or stretches all wait times.
                wait = max(0.0, beat.delay_s) / max(0.1, state.speed)
                if wait:
                    await asyncio.sleep(wait)
                state.current_beat = i + 1
                if beat.kind == "narrate":
                    text = beat.payload.get("text", "")
                    state.last_narration = text
                    payload = await _narrate(state.session_id, text)
                    capture.append({"t": time.time() - state.started_at,
                                    "event": "demo:narration", "data": payload})
                    state.events_captured += 1
                elif beat.kind == "emergency":
                    await _do_emergency(state, db, dict(beat.payload), capture)
                elif beat.kind == "dispatch_last":
                    await _do_dispatch_last(state, db, capture)
                elif beat.kind == "optimize_pending":
                    await _do_optimize_pending(state, db, capture)
                elif beat.kind == "mci_declare":
                    await _do_mci_declare(state, db, dict(beat.payload), capture)
                elif beat.kind == "mci_victim":
                    await _do_mci_victim(state, db, dict(beat.payload), capture)
                elif beat.kind == "mci_optimize":
                    await _do_mci_optimize(state, db, capture)
                else:
                    log.warning(f"demo: unknown beat kind '{beat.kind}'")
    except asyncio.CancelledError:
        log.info(f"demo: scenario '{state.scenario}' cancelled at beat "
                 f"{state.current_beat}/{state.total_beats}")
        raise
    except Exception as exc:  # noqa: BLE001
        log.exception(f"demo: scenario '{state.scenario}' failed: {exc}")
        state.error = str(exc)
    finally:
        state.finished = True
        # Dump capture file unless empty.
        if capture:
            path = REPLAY_DIR / f"{state.session_id}.jsonl"
            with path.open("w", encoding="utf-8") as f:
                for frame in capture:
                    f.write(json.dumps(frame) + "\n")
            state.capture_path = str(path)
            log.info(f"demo: captured {len(capture)} frames → {path.name}")
        await sio.emit("demo:finished",
                       {"session_id": state.session_id,
                        "error": state.error,
                        "events_captured": state.events_captured})


async def start_scenario(scenario: str, speed: float = 1.0) -> RunnerState:
    """Kick off a scenario in the background. Refuses if one is running."""
    global _runner, _runner_task
    if scenario not in SCENARIOS:
        raise ValueError(f"Unknown scenario '{scenario}'. "
                         f"Available: {list(SCENARIOS)}")
    async with _runner_lock:
        if _runner_task and not _runner_task.done():
            raise RuntimeError(
                f"Demo '{_runner.scenario}' already running "
                f"(beat {_runner.current_beat}/{_runner.total_beats}).")
        beats = SCENARIOS[scenario]
        state = RunnerState(
            session_id=_make_session_id(scenario),
            scenario=scenario,
            speed=max(0.1, min(20.0, float(speed))),
            started_at=time.time(),
            total_beats=len(beats),
        )
        _runner = state
        _runner_task = asyncio.create_task(_run_scenario(state, beats))
    return state


async def stop_scenario() -> bool:
    """Cancel a running scenario. Returns True if something was cancelled."""
    global _runner_task
    async with _runner_lock:
        if _runner_task and not _runner_task.done():
            _runner_task.cancel()
            try:
                await _runner_task
            except asyncio.CancelledError:
                pass
            return True
        return False


def runner_status() -> Optional[dict]:
    if not _runner:
        return None
    return {
        "session_id": _runner.session_id,
        "scenario": _runner.scenario,
        "speed": _runner.speed,
        "started_at": _runner.started_at,
        "current_beat": _runner.current_beat,
        "total_beats": _runner.total_beats,
        "last_narration": _runner.last_narration,
        "events_captured": _runner.events_captured,
        "finished": _runner.finished,
        "error": _runner.error,
        "capture_path": _runner.capture_path,
    }


def list_scenarios() -> List[dict]:
    return [{"name": k, "beats": len(v)} for k, v in SCENARIOS.items()]


# ── Replay ────────────────────────────────────────────────────────────────
@dataclass
class ReplayState:
    session_id: str
    file: str
    speed: float
    started_at: float
    frames_total: int
    frames_emitted: int = 0
    finished: bool = False


_replay: Optional[ReplayState] = None
_replay_task: Optional[asyncio.Task] = None


def list_captures() -> List[dict]:
    out = []
    for p in sorted(REPLAY_DIR.glob("*.jsonl"), reverse=True):
        try:
            n = sum(1 for _ in p.open(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            n = 0
        out.append({"session_id": p.stem, "frames": n,
                    "size_bytes": p.stat().st_size})
    return out


async def _run_replay(state: ReplayState, frames: List[dict]) -> None:
    last_t = 0.0
    try:
        for f in frames:
            wait = max(0.0, f["t"] - last_t) / max(0.1, state.speed)
            if wait:
                await asyncio.sleep(wait)
            last_t = f["t"]
            await sio.emit(f["event"], f["data"])
            state.frames_emitted += 1
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001
        log.exception(f"replay: failed: {exc}")
    finally:
        state.finished = True
        await sio.emit("replay:finished",
                       {"session_id": state.session_id,
                        "frames_emitted": state.frames_emitted})


async def start_replay(session_id: str, speed: float = 1.0) -> ReplayState:
    """Re-emit a captured session. Independent of demo runner — replays
    do **not** create rows; they only rebroadcast the captured frames."""
    global _replay, _replay_task
    path = REPLAY_DIR / f"{session_id}.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"No capture for session '{session_id}'.")
    if _replay_task and not _replay_task.done():
        raise RuntimeError("A replay is already running.")
    frames = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            frames.append(json.loads(line))
    state = ReplayState(
        session_id=session_id, file=str(path),
        speed=max(0.1, min(20.0, float(speed))),
        started_at=time.time(), frames_total=len(frames),
    )
    _replay = state
    _replay_task = asyncio.create_task(_run_replay(state, frames))
    return state


def replay_status() -> Optional[dict]:
    if not _replay:
        return None
    return {
        "session_id": _replay.session_id,
        "speed": _replay.speed,
        "started_at": _replay.started_at,
        "frames_total": _replay.frames_total,
        "frames_emitted": _replay.frames_emitted,
        "finished": _replay.finished,
    }
