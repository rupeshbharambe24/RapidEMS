"""Five additional ML signals that ride alongside the original 5 models.

All five ship with heuristic fallbacks so the dispatch engine has something
useful to consume from day one. When the matching ``.pkl`` artifacts appear
in ``ai_models/`` they will be loaded by ``ai_service`` and the heuristics
will step aside (Phase-1.6 follow-up). The functions in this file always
return a populated result with a ``used_fallback`` flag.

Functions
---------
    outcome_probability      30-day survival probability for the patient
                             given severity, age, and vitals.
    equipment_score          how well the ambulance's equipment matches
                             what this patient_type needs (1.0 = perfect).
    paramedic_skill_score    bonus when the on-board paramedic's
                             certification fits the patient_type.
    drug_interaction_warnings  flags risky in-ambulance interventions when
                             the patient's current medications collide
                             with likely on-scene drugs.
    hospital_wait_estimate   refines the static ``er_wait_minutes`` with
                             a time-of-day / day-of-week adjustment.
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, Iterable, List, Optional, Tuple


# ── 1. Outcome predictor ───────────────────────────────────────────────────
# Severity-anchored survival baselines (30-day outcome, well-resourced
# system). These are conservative estimates from published trauma /
# cardiac registry ranges; the heuristic adjusts them by age and the
# worst-vital flag count.
_SEV_OUTCOME_BASELINE = {1: 0.55, 2: 0.85, 3: 0.95, 4: 0.985, 5: 0.999}


def outcome_probability(
    *, severity_level: int,
    age: Optional[int] = None,
    spo2: Optional[float] = None,
    pulse_rate: Optional[int] = None,
    respiratory_rate: Optional[int] = None,
    blood_pressure_systolic: Optional[int] = None,
    gcs_score: Optional[int] = None,
) -> Dict:
    base = _SEV_OUTCOME_BASELINE.get(severity_level, 0.95)
    penalty = 0.0

    # Age tails
    if age is not None:
        if age >= 80:    penalty += 0.10
        elif age >= 65:  penalty += 0.05
        elif age < 1:    penalty += 0.08
        elif age < 5:    penalty += 0.04

    # Vital red flags — each one knocks ~3-7% off the survival baseline.
    if spo2 is not None and spo2 < 88:                   penalty += 0.07
    elif spo2 is not None and spo2 < 92:                 penalty += 0.03
    if pulse_rate is not None and (pulse_rate < 40 or pulse_rate > 160):
        penalty += 0.06
    if respiratory_rate is not None and (respiratory_rate < 8 or respiratory_rate > 30):
        penalty += 0.05
    if blood_pressure_systolic is not None and blood_pressure_systolic < 80:
        penalty += 0.07
    if gcs_score is not None and gcs_score <= 8:         penalty += 0.10
    elif gcs_score is not None and gcs_score <= 12:      penalty += 0.04

    prob = max(0.05, min(0.999, base - penalty))
    return {"survival_prob_30d": round(prob, 3), "used_fallback": True}


# ── 2. Equipment matcher ───────────────────────────────────────────────────
# Per-patient-type equipment needs. Items are matched as case-insensitive
# substrings against ``ambulance.equipment``.
_REQUIRED_EQUIPMENT = {
    "cardiac":   ["AED", "ECG", "IV", "drugs"],
    "stroke":    ["IV", "ECG", "monitor"],
    "trauma":    ["IV", "O2", "drugs"],
    "burns":     ["IV", "O2", "drugs"],
    "pediatric": ["O2", "AED"],
    "general":   ["AED", "O2"],
}


def equipment_score(*, patient_type: str,
                    ambulance_equipment: Optional[Iterable[str]]) -> Dict:
    needed = _REQUIRED_EQUIPMENT.get(patient_type, _REQUIRED_EQUIPMENT["general"])
    have = " ".join((ambulance_equipment or [])).lower()
    missing: List[str] = []
    matched = 0
    for item in needed:
        if item.lower() in have:
            matched += 1
        else:
            missing.append(item)
    score = matched / len(needed) if needed else 1.0
    return {"score": round(score, 3),
            "missing": missing,
            "needed": needed,
            "used_fallback": True}


# ── 3. Paramedic-skill matcher ────────────────────────────────────────────
# Cheap text match: ALS/ICU certifications get a bonus on cardiac, stroke,
# trauma. EMT-Basic stays neutral.
_CERT_BONUSES = {
    "cardiac":  {"acls": 0.20, "emt-paramedic": 0.10, "emt-basic": 0.0},
    "stroke":   {"acls": 0.15, "emt-paramedic": 0.10, "emt-basic": 0.0},
    "trauma":   {"acls": 0.10, "emt-paramedic": 0.10, "emt-basic": 0.0},
    "burns":    {"acls": 0.05, "emt-paramedic": 0.05, "emt-basic": 0.0},
    "pediatric":{"acls": 0.05, "emt-paramedic": 0.10, "emt-basic": 0.0},
    "general":  {"acls": 0.05, "emt-paramedic": 0.05, "emt-basic": 0.0},
}


def paramedic_skill_score(*, patient_type: str,
                          paramedic_certification: Optional[str]) -> Dict:
    cert = (paramedic_certification or "").lower().strip()
    table = _CERT_BONUSES.get(patient_type, _CERT_BONUSES["general"])
    bonus = 0.0
    for keyword, value in table.items():
        if keyword in cert:
            bonus = max(bonus, value)
    return {"bonus": round(bonus, 3), "used_fallback": True}


# ── 4. Drug interactions ──────────────────────────────────────────────────
# Mini interaction table; entries are case-insensitive substring matches
# in either direction. Real systems would lean on RxNorm + DrugBank; the
# heuristic handles the most common pre-hospital traps.
_INTERACTIONS = [
    {
        "pair": ("warfarin",  "aspirin"),
        "tier": "major",
        "note": "Warfarin + aspirin: severe bleeding risk; avoid antiplatelets en route.",
    },
    {
        "pair": ("warfarin",  "ibuprofen"),
        "tier": "major",
        "note": "Warfarin + NSAID: GI bleed risk; use paracetamol if analgesia needed.",
    },
    {
        "pair": ("ssri",      "tramadol"),
        "tier": "major",
        "note": "SSRI + tramadol: serotonin syndrome risk; consider opioid alternative.",
    },
    {
        "pair": ("metformin", "iv contrast"),
        "tier": "moderate",
        "note": "Metformin: hold if IV contrast likely (lactic acidosis risk).",
    },
    {
        "pair": ("beta-blocker", "epinephrine"),
        "tier": "moderate",
        "note": "Beta-blocker on board: epinephrine response may be blunted; "
                "consider higher dose or glucagon.",
    },
    {
        "pair": ("nitrate",   "sildenafil"),
        "tier": "major",
        "note": "Recent sildenafil/tadalafil/vardenafil: nitrates contraindicated "
                "(profound hypotension).",
    },
    {
        "pair": ("maoi",      "morphine"),
        "tier": "major",
        "note": "MAOI + opioid: hypertensive crisis risk; consult medical control.",
    },
    {
        "pair": ("insulin",   "beta-blocker"),
        "tier": "moderate",
        "note": "Beta-blocker may mask hypoglycemia symptoms in a diabetic patient.",
    },
]

# Drugs typically administered en route (covered by every ambulance type).
_LIKELY_INTERVENTIONS = [
    "aspirin", "epinephrine", "morphine", "nitrate",
    "ibuprofen", "iv contrast",
]


def drug_interaction_warnings(
    *, current_medications: Optional[str],
    patient_type: Optional[str] = None,
    extra_planned: Optional[Iterable[str]] = None,
) -> Dict:
    if not current_medications:
        return {"warnings": [], "used_fallback": True}
    cm = current_medications.lower()

    # Build the list of likely en-route interventions for this case.
    planned = set(_LIKELY_INTERVENTIONS)
    if extra_planned:
        planned.update(s.lower() for s in extra_planned)
    if patient_type == "cardiac":
        planned.update({"nitrate", "aspirin", "morphine", "epinephrine", "beta-blocker"})
    elif patient_type == "trauma":
        planned.update({"morphine", "iv contrast"})
    elif patient_type == "stroke":
        planned.update({"aspirin"})

    warnings = []
    for inter in _INTERACTIONS:
        a, b = inter["pair"]
        # The interaction triggers when either side appears in current
        # meds and the other in planned — direction-agnostic.
        cm_has_a = a in cm
        cm_has_b = b in cm
        plan_has_a = any(a in p for p in planned)
        plan_has_b = any(b in p for p in planned)
        if (cm_has_a and plan_has_b) or (cm_has_b and plan_has_a):
            warnings.append({"tier": inter["tier"], "note": inter["note"],
                             "pair": list(inter["pair"])})
    return {"warnings": warnings, "used_fallback": True}


# ── 5. Hospital-wait predictor ────────────────────────────────────────────
# Refines the static er_wait_minutes with a time-of-day / weekday curve
# (peaks late afternoon weekdays; quiet overnight weekends).
def _diurnal_multiplier(hour: int, dow: int) -> float:
    weekend = dow >= 5
    # 0=quiet midnight, 1=peak. Triangular curve peaking ~17:00.
    if 0 <= hour < 6:
        m = 0.55
    elif 6 <= hour < 9:
        m = 0.85
    elif 9 <= hour < 14:
        m = 1.05
    elif 14 <= hour < 19:
        m = 1.30
    elif 19 <= hour < 23:
        m = 1.10
    else:
        m = 0.75
    if weekend:
        m *= 0.85       # ERs typically ~15% lower volume on weekends
    return m


def hospital_wait_estimate(
    *, base_er_wait_minutes: int,
    is_diversion: bool = False,
    when: Optional[datetime] = None,
) -> Dict:
    when = when or datetime.utcnow()
    mult = _diurnal_multiplier(when.hour, when.weekday())
    if is_diversion:
        # Diverting hospitals quote a long wait so the recommender skips them.
        mult *= 2.0
    predicted = max(0, int(round((base_er_wait_minutes or 0) * mult)))
    return {
        "predicted_wait_minutes": predicted,
        "diurnal_multiplier": round(mult, 2),
        "used_fallback": True,
    }


# ── Convenience: combined cost-matrix multiplier ─────────────────────────
def dispatch_match_multiplier(
    *, patient_type: str,
    ambulance_equipment: Optional[Iterable[str]],
    paramedic_certification: Optional[str],
) -> Tuple[float, Dict]:
    """Combine equipment + skill into a single (eta-cost) multiplier.

    Returns (multiplier, detail). Multiplier is in [0.7, 1.5] — lower is
    better since the optimizer minimises cost. A perfectly equipped ALS
    crew on a cardiac call lands near 0.75 (15% bonus from skill + 100%
    equipment match); a missing-equipment match lands above 1.0.
    """
    eq = equipment_score(patient_type=patient_type,
                         ambulance_equipment=ambulance_equipment)
    skill = paramedic_skill_score(patient_type=patient_type,
                                  paramedic_certification=paramedic_certification)
    # Base 1.0; drop by 0.25 × equipment_score and by skill.bonus.
    mult = 1.0 - 0.25 * eq["score"] - skill["bonus"]
    # Penalty if any required item is missing.
    if eq["missing"]:
        mult += 0.10 * len(eq["missing"])
    mult = max(0.7, min(1.5, mult))
    return mult, {
        "equipment_score": eq["score"],
        "missing_equipment": eq["missing"],
        "skill_bonus": skill["bonus"],
    }
