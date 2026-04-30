"""LLM dispatcher copilot — natural-language queries against the live system.

Uses Groq's OpenAI-compatible function-calling so the model can invoke
read-only tools against the same data the dashboards see, then narrates
the result.

Design constraints
------------------
* All tools are read-only. Anything that would mutate state (create, dispatch,
  divert) requires the dispatcher to act on the existing UIs.
* Tools accept geographic filters in lat/lng + km — the model is told the
  city centre so 'within 5km of the city centre' resolves naturally; for
  named places the dispatcher should paste coordinates or use the map.
* Hard-cap of 4 tool-call iterations per query to prevent runaway loops.
* Falls through with a clean error message when Groq is unavailable.
"""
from __future__ import annotations

import json
import math
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..core.logging import log
from ..models.ambulance import Ambulance, AmbulanceStatus
from ..models.dispatch import Dispatch
from ..models.emergency import Emergency
from ..models.hospital import Hospital


GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MAX_TOOL_LOOPS = 4
TOOL_RESULT_TRUNCATE = 6000   # chars; keep model-context lean


# ── Tool catalogue (OpenAI-compatible JSON Schema) ────────────────────────
TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list_ambulances",
            "description": "List active ambulances. Optionally filter by "
                           "status, type, geographic radius (km), or "
                           "equipment string match. Returns up to 30 rows.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {"type": "string",
                               "enum": ["available", "en_route", "on_scene",
                                        "transporting", "returning",
                                        "out_of_service"]},
                    "type": {"type": "string", "enum": ["bls", "als", "icu"]},
                    "near_lat": {"type": "number"},
                    "near_lng": {"type": "number"},
                    "radius_km": {"type": "number",
                                  "description": "Required if near_lat/near_lng given."},
                    "has_equipment": {"type": "string",
                                      "description": "Substring match against "
                                                     "the equipment list, e.g. "
                                                     "'AED', 'ventilator'."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_hospitals",
            "description": "List active hospitals. Filter by specialty, "
                           "geographic radius, ICU bed availability, or "
                           "diversion status.",
            "parameters": {
                "type": "object",
                "properties": {
                    "specialty": {"type": "string",
                                  "description": "Match against the "
                                                 "specialties array, e.g. "
                                                 "'cardiac', 'trauma'."},
                    "near_lat": {"type": "number"},
                    "near_lng": {"type": "number"},
                    "radius_km": {"type": "number"},
                    "min_icu_beds": {"type": "integer"},
                    "exclude_on_diversion": {"type": "boolean"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_emergencies",
            "description": "List emergencies in the system. Filter by status, "
                           "severity range, or how recently the call came in.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {"type": "string",
                               "enum": ["pending", "dispatched", "resolved",
                                        "cancelled"]},
                    "severity_min": {"type": "integer", "minimum": 1, "maximum": 5},
                    "severity_max": {"type": "integer", "minimum": 1, "maximum": 5},
                    "last_minutes": {"type": "integer",
                                     "description": "Only show calls created "
                                                    "within this many minutes."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_kpis",
            "description": "Return the system-wide KPIs the dispatcher dashboard "
                           "shows: pending count, active dispatches, "
                           "available units, average severity, etc.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


# ── Tool implementations ──────────────────────────────────────────────────
def _hav_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371.0
    dl = math.radians(lat2 - lat1)
    dn = math.radians(lng2 - lng1)
    a = (math.sin(dl / 2) ** 2 + math.cos(math.radians(lat1))
         * math.cos(math.radians(lat2)) * math.sin(dn / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


async def _tool_list_ambulances(db: AsyncSession, args: Dict[str, Any]) -> str:
    stmt = select(Ambulance).where(Ambulance.is_active == True)
    if args.get("status"):
        stmt = stmt.where(Ambulance.status == args["status"])
    if args.get("type"):
        stmt = stmt.where(Ambulance.ambulance_type == args["type"])
    rows = (await db.scalars(stmt.limit(60))).all()

    near = args.get("near_lat"), args.get("near_lng")
    radius = args.get("radius_km")
    has_eq = (args.get("has_equipment") or "").lower()

    out: List[Dict[str, Any]] = []
    for a in rows:
        if has_eq:
            eq = " ".join(a.equipment or []).lower()
            if has_eq not in eq:
                continue
        if near[0] is not None and near[1] is not None and radius is not None:
            if a.current_lat is None or a.current_lng is None:
                continue
            d = _hav_km(near[0], near[1], a.current_lat, a.current_lng)
            if d > radius:
                continue
            extra = {"distance_km": round(d, 2)}
        else:
            extra = {}
        out.append({
            "id": a.id, "registration": a.registration_number,
            "type": a.ambulance_type, "status": a.status,
            "equipment": a.equipment or [],
            "lat": a.current_lat, "lng": a.current_lng,
            "paramedic": a.paramedic_name,
            **extra,
        })
    return json.dumps({"count": len(out), "rows": out[:30]})


async def _tool_list_hospitals(db: AsyncSession, args: Dict[str, Any]) -> str:
    stmt = select(Hospital).where(Hospital.is_active == True)
    if args.get("exclude_on_diversion"):
        stmt = stmt.where(Hospital.is_diversion == False)
    rows = (await db.scalars(stmt)).all()

    near = args.get("near_lat"), args.get("near_lng")
    radius = args.get("radius_km")
    spec = (args.get("specialty") or "").lower()
    min_icu = args.get("min_icu_beds")

    out: List[Dict[str, Any]] = []
    for h in rows:
        if spec:
            specs = [s.lower() for s in (h.specialties or [])]
            if not any(spec in s for s in specs):
                continue
        if min_icu is not None and (h.available_beds_icu or 0) < min_icu:
            continue
        if near[0] is not None and near[1] is not None and radius is not None:
            d = _hav_km(near[0], near[1], h.lat, h.lng)
            if d > radius:
                continue
            extra = {"distance_km": round(d, 2)}
        else:
            extra = {}
        out.append({
            "id": h.id, "name": h.name,
            "specialties": h.specialties or [],
            "available_beds_general": h.available_beds_general,
            "available_beds_icu": h.available_beds_icu,
            "available_beds_trauma": h.available_beds_trauma,
            "er_wait_minutes": h.er_wait_minutes,
            "is_diversion": h.is_diversion,
            "lat": h.lat, "lng": h.lng,
            **extra,
        })
    return json.dumps({"count": len(out), "rows": out[:30]})


async def _tool_list_emergencies(db: AsyncSession, args: Dict[str, Any]) -> str:
    stmt = select(Emergency).order_by(Emergency.created_at.desc())
    if args.get("status"):
        stmt = stmt.where(Emergency.status == args["status"])
    if args.get("severity_min") is not None:
        stmt = stmt.where(Emergency.predicted_severity >= args["severity_min"])
    if args.get("severity_max") is not None:
        stmt = stmt.where(Emergency.predicted_severity <= args["severity_max"])
    if args.get("last_minutes") is not None:
        cutoff = datetime.utcnow() - timedelta(minutes=int(args["last_minutes"]))
        stmt = stmt.where(Emergency.created_at >= cutoff)
    rows = (await db.scalars(stmt.limit(40))).all()
    out = [{
        "id": e.id, "status": e.status,
        "severity": e.predicted_severity,
        "patient_name": e.patient_name,
        "patient_age": e.patient_age,
        "patient_type": e.inferred_patient_type,
        "chief_complaint": e.chief_complaint,
        "symptoms": e.symptoms or [],
        "lat": e.location_lat, "lng": e.location_lng,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    } for e in rows]
    return json.dumps({"count": len(out), "rows": out})


async def _tool_get_kpis(db: AsyncSession, args: Dict[str, Any]) -> str:
    yesterday = datetime.utcnow() - timedelta(hours=24)
    pending = await db.scalar(
        select(func.count(Emergency.id)).where(Emergency.status == "pending")) or 0
    dispatched = await db.scalar(
        select(func.count(Dispatch.id)).where(Dispatch.status.in_(
            ["dispatched", "en_route", "on_scene", "transporting"]))) or 0
    avail = await db.scalar(
        select(func.count(Ambulance.id)).where(
            Ambulance.status == AmbulanceStatus.AVAILABLE.value,
            Ambulance.is_active == True)) or 0
    busy = await db.scalar(
        select(func.count(Ambulance.id)).where(
            Ambulance.status != AmbulanceStatus.AVAILABLE.value,
            Ambulance.is_active == True)) or 0
    diversions = await db.scalar(
        select(func.count(Hospital.id)).where(
            Hospital.is_diversion == True, Hospital.is_active == True)) or 0
    calls_24h = await db.scalar(
        select(func.count(Emergency.id)).where(Emergency.created_at >= yesterday)) or 0
    avg_sev = await db.scalar(
        select(func.avg(Emergency.predicted_severity))
        .where(Emergency.predicted_severity.isnot(None)))
    return json.dumps({
        "pending_emergencies": int(pending),
        "active_dispatches": int(dispatched),
        "available_ambulances": int(avail),
        "busy_ambulances": int(busy),
        "hospitals_on_diversion": int(diversions),
        "calls_last_24h": int(calls_24h),
        "avg_severity": round(float(avg_sev), 2) if avg_sev else None,
    })


_DISPATCHERS = {
    "list_ambulances":  _tool_list_ambulances,
    "list_hospitals":   _tool_list_hospitals,
    "list_emergencies": _tool_list_emergencies,
    "get_kpis":         _tool_get_kpis,
}


# ── Conversation loop ──────────────────────────────────────────────────────
def _system_prompt(now: datetime, context: Optional[Dict[str, Any]]) -> str:
    parts = [
        "You are RapidEMS Copilot — a read-only assistant for the dispatcher.",
        "Answer in 1-3 sentences. Be specific (numbers, ambulance regs, hospital "
        "names). Cite tool results — don't make up data.",
        f"Current UTC time: {now.isoformat(timespec='seconds')}.",
    ]
    if context:
        if context.get("city_lat") is not None and context.get("city_lng") is not None:
            parts.append(f"City centre: {context['city_lat']}, {context['city_lng']}. "
                         "Use this when the dispatcher says 'near the city' or "
                         "doesn't pin a place.")
        if context.get("dispatcher"):
            parts.append(f"Dispatcher logged in: {context['dispatcher']}.")
    parts.append("If a question can't be answered with the available tools, say "
                 "so — don't guess.")
    return "\n".join(parts)


async def ask(
    db: AsyncSession, query: str, *,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Returns {answer, tool_calls, provider, latency_ms, error?}."""
    if not settings.groq_api_key:
        return {
            "answer": "Copilot is not configured — set GROQ_API_KEY in .env to enable.",
            "tool_calls": [], "provider": "disabled",
            "latency_ms": 0, "error": "no_groq_key",
        }

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": _system_prompt(datetime.utcnow(), context)},
        {"role": "user",   "content": query},
    ]
    tool_trace: List[Dict[str, Any]] = []

    headers = {"Authorization": f"Bearer {settings.groq_api_key}",
               "Content-Type": "application/json"}
    body_base = {
        "model": settings.groq_model,
        "tools": TOOLS,
        "tool_choice": "auto",
        "temperature": 0.1,
        "max_tokens": 700,
    }

    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            for _ in range(MAX_TOOL_LOOPS):
                r = await client.post(
                    GROQ_URL, headers=headers,
                    json={**body_base, "messages": messages},
                )
                r.raise_for_status()
                msg = r.json()["choices"][0]["message"]
                # Append assistant turn (with tool_calls if any).
                messages.append(msg)
                tool_calls = msg.get("tool_calls") or []
                if not tool_calls:
                    return {
                        "answer": (msg.get("content") or "").strip()
                                  or "(no answer)",
                        "tool_calls": tool_trace,
                        "provider": "groq",
                        "latency_ms": int((time.perf_counter() - t0) * 1000),
                    }
                # Execute every tool call returned in this round.
                for tc in tool_calls:
                    fn_name = tc["function"]["name"]
                    raw_args = tc["function"].get("arguments") or "{}"
                    try:
                        args = json.loads(raw_args) if raw_args else {}
                    except json.JSONDecodeError:
                        args = {}
                    impl = _DISPATCHERS.get(fn_name)
                    if not impl:
                        result = json.dumps({"error": f"unknown tool {fn_name}"})
                    else:
                        try:
                            result = await impl(db, args)
                        except Exception as exc:  # noqa: BLE001
                            result = json.dumps({"error": str(exc)})
                    if len(result) > TOOL_RESULT_TRUNCATE:
                        result = result[:TOOL_RESULT_TRUNCATE] + '..."}]}'
                    tool_trace.append({
                        "name": fn_name, "arguments": args,
                        "result_preview": result[:300],
                    })
                    messages.append({
                        "role": "tool", "tool_call_id": tc["id"],
                        "name": fn_name, "content": result,
                    })
            # Hit the loop cap.
            return {
                "answer": "I made too many tool calls trying to answer that. Please ask more specifically.",
                "tool_calls": tool_trace,
                "provider": "groq",
                "latency_ms": int((time.perf_counter() - t0) * 1000),
                "error": "tool_loop_limit",
            }
    except Exception as exc:  # noqa: BLE001
        log.warning(f"copilot: {exc}")
        return {
            "answer": f"Copilot error: {exc}",
            "tool_calls": tool_trace,
            "provider": "groq",
            "latency_ms": int((time.perf_counter() - t0) * 1000),
            "error": str(exc),
        }
