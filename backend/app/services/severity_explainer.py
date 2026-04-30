"""Triage explanation — turns the severity model's prediction into a
short human-readable narrative the dispatcher can hover to read.

Approach
--------
1. Score each input feature against clinical normality bands. This gives a
   list of FeatureFactor structs (name, value, impact, note) that already
   stands on its own — no LLM required.
2. Hand the structured factors plus the model's severity + confidence to
   Groq Llama 3.3 (sub-second). Groq writes a 1-2 sentence dispatcher
   narrative. If Groq is unavailable or unconfigured, fall through to a
   deterministic template assembled from the same factors.

Never raises; always returns a populated ExplainResponse.
"""
from __future__ import annotations

import json
from typing import List, Optional

import httpx

from ..config import settings
from ..core.logging import log
from ..schemas.ai import ExplainResponse, FeatureFactor


_SEVERITY_LABEL = {
    1: "Critical", 2: "Serious", 3: "Moderate", 4: "Minor", 5: "Non-Emergency",
}


# Tiers used to bucket each abnormal vital. Ordered most → least severe.
_VITAL_RULES = {
    "spo2": [
        ("critical", lambda v: v < 88,  "severe hypoxemia"),
        ("serious",  lambda v: v < 92,  "low oxygen saturation"),
        ("moderate", lambda v: v < 95,  "borderline-low oxygen saturation"),
    ],
    "pulse_rate": [
        ("critical", lambda v: v < 40 or v > 160, "extreme tachy/bradycardia"),
        ("serious",  lambda v: v < 50 or v > 130, "marked rate abnormality"),
        ("moderate", lambda v: v < 60 or v > 110, "rate outside normal band"),
    ],
    "respiratory_rate": [
        ("critical", lambda v: v < 8 or v > 30,  "severe respiratory compromise"),
        ("serious",  lambda v: v < 10 or v > 24, "abnormal respiratory rate"),
    ],
    "gcs_score": [
        ("critical", lambda v: v <= 8,           "severely depressed consciousness (GCS ≤ 8)"),
        ("serious",  lambda v: v <= 12,          "moderately depressed consciousness"),
        ("moderate", lambda v: v <= 14,          "mildly altered consciousness"),
    ],
    "blood_pressure_systolic": [
        ("critical", lambda v: v < 80 or v > 200, "extreme blood pressure"),
        ("serious",  lambda v: v < 90 or v > 180, "concerning blood pressure"),
        ("moderate", lambda v: v < 100 or v > 160, "abnormal blood pressure"),
    ],
}

# Symptom impact mapping — highest tier wins.
_SYMPTOM_TIER = {
    # Critical
    "cardiac_arrest": "critical", "unconscious": "critical",
    "severe_burns": "critical", "spinal_injury": "critical",
    "anaphylaxis": "critical", "major_bleeding": "critical",
    # Serious
    "stroke_symptoms": "serious", "chest_pain": "serious",
    "shortness_of_breath": "serious", "seizure": "serious",
    "head_trauma": "serious", "diabetic_emergency": "serious",
    # Moderate
    "fracture": "moderate", "moderate_bleeding": "moderate",
    "abdominal_pain": "moderate", "high_fever": "moderate",
    # Minor
    "vomiting": "normal", "dizziness": "normal", "minor_cut": "normal",
    "sprain": "normal", "headache": "normal",
}

_IMPACT_WEIGHT = {"critical": 4, "serious": 3, "moderate": 2,
                  "normal": 0, "protective": -1}


def derive_factors(
    *, age: Optional[int] = None, gender: Optional[str] = None,
    pulse_rate: Optional[int] = None,
    blood_pressure_systolic: Optional[int] = None,
    blood_pressure_diastolic: Optional[int] = None,
    respiratory_rate: Optional[int] = None,
    spo2: Optional[float] = None,
    gcs_score: Optional[int] = None,
    symptoms: Optional[List[str]] = None,
) -> List[FeatureFactor]:
    """Score every supplied input against clinical bands. Returns the
    ranked-most-severe-first list."""
    factors: List[FeatureFactor] = []

    # Vitals
    vitals = {
        "spo2": spo2,
        "pulse_rate": pulse_rate,
        "respiratory_rate": respiratory_rate,
        "gcs_score": gcs_score,
        "blood_pressure_systolic": blood_pressure_systolic,
    }
    for name, val in vitals.items():
        if val is None:
            continue
        impact = "normal"
        note = "within normal range"
        for tier, predicate, label in _VITAL_RULES.get(name, []):
            try:
                if predicate(val):
                    impact, note = tier, label
                    break
            except TypeError:
                continue
        factors.append(FeatureFactor(
            name=name, value=str(val), impact=impact, note=note,
        ))

    # Symptoms — collapse to the highest tier present
    if symptoms:
        for s in symptoms:
            tier = _SYMPTOM_TIER.get(s, "moderate")
            factors.append(FeatureFactor(
                name=f"symptom:{s}", value=s.replace('_', ' '),
                impact=tier, note=f"{tier}-tier symptom",
            ))

    # Age extremes — pediatric or elderly bumps risk
    if age is not None:
        if age < 5:
            factors.append(FeatureFactor(
                name="age", value=str(age), impact="serious",
                note="pediatric — age-elevated risk",
            ))
        elif age >= 75:
            factors.append(FeatureFactor(
                name="age", value=str(age), impact="moderate",
                note="elderly — age-elevated risk",
            ))

    # Sort: highest impact first.
    factors.sort(key=lambda f: -_IMPACT_WEIGHT.get(f.impact, 0))
    return factors


# ── LLM narration ──────────────────────────────────────────────────────────
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

NARRATIVE_SYSTEM = """You write 1-2 sentence dispatcher-facing explanations
of why an emergency call was triaged at a given severity level.

You receive: severity_level (1=Critical .. 5=Non-Emergency), confidence
(0..1), and a list of feature factors with their clinical impact tags
('critical', 'serious', 'moderate', 'normal', 'protective').

Constraints:
- Plain text, no markdown, no headers, no emoji.
- Lead with the severity ("SEV-2 because ...").
- Cite at most 3 factors; pick the highest-impact ones.
- Don't recommend treatment; this is for triage explanation only.
- Don't invent values that aren't in the factor list.
- Keep total length under 60 words.
"""


async def narrate(
    severity_level: int, confidence: float, factors: List[FeatureFactor],
) -> tuple[str, str]:
    """Returns (narrative, provider). Falls back to a deterministic
    template when Groq is unconfigured or fails."""
    if not settings.groq_api_key:
        return _template_narrative(severity_level, confidence, factors), "template"

    payload = {
        "model": settings.groq_model,
        "messages": [
            {"role": "system", "content": NARRATIVE_SYSTEM},
            {"role": "user", "content": json.dumps({
                "severity_level": severity_level,
                "severity_label": _SEVERITY_LABEL.get(severity_level, "?"),
                "confidence": round(confidence, 3),
                "factors": [f.model_dump() for f in factors[:6]],
            })},
        ],
        "temperature": 0.2,
        "max_tokens": 200,
    }
    headers = {"Authorization": f"Bearer {settings.groq_api_key}",
               "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.post(GROQ_URL, headers=headers, json=payload)
            r.raise_for_status()
            text = r.json()["choices"][0]["message"]["content"].strip()
        return text, "groq"
    except Exception as exc:  # noqa: BLE001
        log.warning(f"severity_explainer Groq failed: {exc}")
        return _template_narrative(severity_level, confidence, factors), "template"


def _template_narrative(severity_level: int, confidence: float,
                        factors: List[FeatureFactor]) -> str:
    """Deterministic fallback: cite the top 3 highest-impact factors."""
    label = _SEVERITY_LABEL.get(severity_level, "?")
    pct = round(confidence * 100)
    top = [f for f in factors if _IMPACT_WEIGHT.get(f.impact, 0) >= 2][:3]
    if not top:
        return (f"SEV-{severity_level} ({label}) at {pct}% confidence — "
                "vitals and symptoms within normal bands.")
    parts = []
    for f in top:
        if f.value and not f.name.startswith("symptom:"):
            parts.append(f"{f.name.replace('_', ' ')} {f.value} ({f.note})")
        else:
            parts.append(f"{f.note}")
    body = "; ".join(parts)
    return (f"SEV-{severity_level} ({label}) at {pct}% confidence because "
            f"{body}.")


# ── Top-level entry point ──────────────────────────────────────────────────
async def explain(
    severity_level: int, confidence: float, used_fallback: bool, *,
    age: Optional[int] = None, gender: Optional[str] = None,
    pulse_rate: Optional[int] = None,
    blood_pressure_systolic: Optional[int] = None,
    blood_pressure_diastolic: Optional[int] = None,
    respiratory_rate: Optional[int] = None,
    spo2: Optional[float] = None,
    gcs_score: Optional[int] = None,
    symptoms: Optional[List[str]] = None,
) -> ExplainResponse:
    factors = derive_factors(
        age=age, gender=gender, pulse_rate=pulse_rate,
        blood_pressure_systolic=blood_pressure_systolic,
        blood_pressure_diastolic=blood_pressure_diastolic,
        respiratory_rate=respiratory_rate, spo2=spo2,
        gcs_score=gcs_score, symptoms=symptoms,
    )
    narrative, provider = await narrate(severity_level, confidence, factors)
    return ExplainResponse(
        severity_level=severity_level,
        severity_label=_SEVERITY_LABEL.get(severity_level, "?"),
        confidence=round(confidence, 4),
        factors=factors,
        narrative=narrative,
        provider=provider,
        used_fallback=used_fallback,
    )
