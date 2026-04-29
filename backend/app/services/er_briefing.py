"""Pre-arrival ER briefing generator.

Composes the patient profile + medical-record snapshot + LLM-extracted
emergency context into a single ER-ready brief that lands in
``hospital_alerts.briefing``. Uses Gemini 2.5 Flash for refinement +
prep-recommendations; falls back to a fully-populated structured template
when Gemini is unavailable.

The briefing runs in the background after a dispatch is created — the
hospital portal renders ``briefing`` as soon as it appears, surfaced via
the existing ``hospital:alert_status`` socket channel.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..core.logging import log
from ..models.ambulance import Ambulance
from ..models.dispatch import Dispatch
from ..models.emergency import Emergency
from ..models.hospital import Hospital
from ..models.medical_record import MedicalRecord
from ..models.patient_profile import PatientProfile


GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)


SYSTEM_PROMPT = """You are an emergency medicine triage assistant generating a
concise pre-arrival briefing for a receiving ER team.

You will be handed a STRUCTURED snapshot of a patient and incident. Your job is
to (1) preserve every fact, (2) tighten the prose, and (3) add a short
PREP RECOMMENDATIONS block at the end with at most 3 bullets stating what the
ER should ready before the ambulance arrives (e.g. "stat 12-lead ECG bay",
"call cardiology for STEMI line", "trauma bay, X-ray ready"). Use only the
information provided — never invent vitals, medications, or history.

Output rules
============
- Plain text, no markdown headers other than the exact section labels below.
- Keep total length under 280 words.
- Use the EXACT section order:
    PATIENT
    INCIDENT
    VITALS
    TRANSPORT
    PRIOR RECORDS
    PREP RECOMMENDATIONS
- Mark unknowns as "unknown" rather than guessing.
- No emoji. No commentary about your own behaviour. Just the briefing.
"""


# ── Public entry point ────────────────────────────────────────────────────
async def generate_briefing(
    db: AsyncSession, dispatch: Dispatch, *, use_llm: bool = True,
) -> str:
    emergency, hospital, ambulance, profile, records = await _load_context(db, dispatch)
    template = _render_template(emergency, profile, records, hospital,
                                ambulance, dispatch)

    if not use_llm or not settings.gemini_api_key:
        return template

    try:
        return await _gemini_refine(template)
    except Exception as exc:  # noqa: BLE001
        log.warning(f"er_briefing — Gemini failed, falling back to template: {exc}")
        return template


# ── Context load ──────────────────────────────────────────────────────────
async def _load_context(
    db: AsyncSession, dispatch: Dispatch,
) -> Tuple[
    Optional[Emergency], Optional[Hospital], Optional[Ambulance],
    Optional[PatientProfile], List[MedicalRecord],
]:
    emergency = await db.scalar(
        select(Emergency).where(Emergency.id == dispatch.emergency_id))
    hospital = await db.scalar(
        select(Hospital).where(Hospital.id == dispatch.hospital_id))
    ambulance = await db.scalar(
        select(Ambulance).where(Ambulance.id == dispatch.ambulance_id))

    profile: Optional[PatientProfile] = None
    records: List[MedicalRecord] = []
    if emergency and emergency.phone:
        profile = await db.scalar(
            select(PatientProfile).where(PatientProfile.phone == emergency.phone))
        if profile:
            records = list((await db.scalars(
                select(MedicalRecord)
                .where(MedicalRecord.patient_id == profile.id)
                .order_by(MedicalRecord.uploaded_at.desc())
                .limit(10)
            )).all())
    return emergency, hospital, ambulance, profile, records


# ── Template (also the LLM input) ─────────────────────────────────────────
def _render_template(
    emergency: Optional[Emergency],
    profile: Optional[PatientProfile],
    records: List[MedicalRecord],
    hospital: Optional[Hospital],
    ambulance: Optional[Ambulance],
    dispatch: Dispatch,
) -> str:
    e = emergency
    p = profile
    eta_m = round((dispatch.predicted_eta_seconds or 0) / 60.0, 1)

    name = ((p.full_name if p else None)
            or (e.patient_name if e else None)
            or "Unknown")
    age = (e.patient_age if e else None) or "unknown"
    gender = (e.patient_gender if e else None) or "unknown"
    blood = (p.blood_group if p else None) or "unknown"
    allergies = (p.allergies if p else None) or "unknown"
    chronic = (p.chronic_conditions if p else None) or "unknown"
    meds = (p.current_medications if p else None) or "unknown"
    nok = ((p.emergency_contact_name if p else None) or "unknown")
    nok_ph = (p.emergency_contact_phone if p else None) or ""

    sev = (e.predicted_severity if e else None) or "?"
    pt_type = (e.inferred_patient_type if e else None) or "general"
    chief = (e.chief_complaint if e else None) or "unknown"
    symptoms = ", ".join((e.symptoms or [])) if e else "none recorded"
    if not symptoms:
        symptoms = "none recorded"
    notes = (e.notes if e else None)

    pulse = _fmt(e.pulse_rate if e else None, "bpm")
    spo2 = _fmt(e.spo2 if e else None, "%")
    bp = (f"{e.blood_pressure_systolic}/{e.blood_pressure_diastolic} mmHg"
          if e and e.blood_pressure_systolic and e.blood_pressure_diastolic
          else "unknown")
    rr = _fmt(e.respiratory_rate if e else None, "/min")
    gcs = _fmt(e.gcs_score if e else None, "")

    if records:
        rec_lines = []
        for r in records:
            line = f"  - {r.record_type.upper()}: {r.file_name}"
            if r.description:
                line += f" — {r.description}"
            rec_lines.append(line)
        records_text = "\n".join(rec_lines)
    else:
        records_text = "  none on file"

    amb_line = (f"{ambulance.registration_number} "
                f"({ambulance.ambulance_type.upper()})"
                if ambulance else "unknown")

    return f"""PATIENT
  {name}, age {age}, {gender}
  Blood group: {blood}
  Allergies: {allergies}
  Chronic conditions: {chronic}
  Current medications: {meds}
  Next of kin: {nok}{f' ({nok_ph})' if nok_ph else ''}

INCIDENT
  SEV-{sev} · {pt_type.upper()}
  Chief complaint: {chief}
  Symptoms: {symptoms}
{f'  Caller transcript: {notes}' if notes else ''}

VITALS
  Pulse: {pulse}
  BP: {bp}
  SpO2: {spo2}
  RR: {rr}
  GCS: {gcs}

TRANSPORT
  {amb_line}
  ETA {eta_m} min to {hospital.name if hospital else 'unknown'}

PRIOR RECORDS
{records_text}

PREP RECOMMENDATIONS
  (none — template fallback)
"""


def _fmt(v, suffix: str) -> str:
    if v is None or v == "":
        return "unknown"
    return f"{v}{(' ' + suffix) if suffix else ''}".strip()


# ── Gemini refinement ─────────────────────────────────────────────────────
async def _gemini_refine(template: str) -> str:
    url = GEMINI_URL.format(model=settings.gemini_model or "gemini-2.5-flash")
    body = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user",
                      "parts": [{"text": "STRUCTURED SNAPSHOT:\n\n" + template}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 1500,
        },
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.post(url, params={"key": settings.gemini_api_key}, json=body)
        r.raise_for_status()
        data = r.json()
    parts = data["candidates"][0].get("content", {}).get("parts", []) or []
    text = "".join(p.get("text", "") for p in parts).strip()
    if not text:
        raise ValueError(
            f"empty Gemini response (finishReason="
            f"{data['candidates'][0].get('finishReason')!r})"
        )
    return text
