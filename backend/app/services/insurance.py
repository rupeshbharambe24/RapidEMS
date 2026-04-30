"""Insurance verification stub.

Real EMS systems poll a clearinghouse like Availity or PokitDok at
patient-pickup time so the receiving hospital knows whether the
patient is in-network before the bay is committed. Live integrations
sit behind paid APIs and per-state regulatory plumbing — well beyond
what a free-tier demo can wire up — so this module ships a
deterministic stub registry instead.

What's real about it:

* The shape mirrors the standard EDI 270/271 eligibility response —
  ``covered``, ``plan``, ``copay``, ``in_network_hospital_ids``,
  ``effective_through`` — so swapping the stub for a clearinghouse
  later is one function replacement.
* Lookups are deterministic from the input. The same card number
  resolves to the same plan every time, so demos and replays stay
  consistent.
* Stub payers are seeded with realistic in-network hospital lists
  drawn from whatever the seeder put in the DB — see
  ``_resolve_in_network_ids`` — so the dispatcher dashboard can show
  a sensible "prefer this hospital" badge.

What's NOT real:

* No actual eligibility check happens. Card numbers starting with
  ``DENY-`` always come back uncovered; everything else is covered.
* The plan / copay tier is hashed off the card number for variety.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.hospital import Hospital


# ── Stub payer catalogue ──────────────────────────────────────────────────
@dataclass(frozen=True)
class Payer:
    code: str
    name: str
    plan_tier: str
    copay_inr: int
    accepts_specialties: List[str]


# Realistic-looking but fully synthetic payers. Anything matched on
# specialties tells the recommender "this payer's network covers cardiac
# but not paediatric" → in-network filter follows.
PAYERS: List[Payer] = [
    Payer("STAR-HEALTH",  "Star Health Insurance",
          plan_tier="silver",  copay_inr=500,
          accepts_specialties=["cardiac", "general", "trauma"]),
    Payer("HDFC-ERGO",    "HDFC ERGO Optima",
          plan_tier="gold",    copay_inr=300,
          accepts_specialties=["cardiac", "stroke", "trauma", "general"]),
    Payer("APOLLO-MUNICH", "Apollo Munich Easy Health",
          plan_tier="platinum", copay_inr=0,
          accepts_specialties=["cardiac", "stroke", "trauma", "pediatric",
                                "burns", "general"]),
    Payer("AYUSHMAN",     "Ayushman Bharat (PMJAY)",
          plan_tier="state",   copay_inr=0,
          accepts_specialties=["general", "trauma", "stroke",
                                "pediatric", "burns"]),
]


def _payer_for_card(card_number: str) -> Payer:
    """Hash the card number to one of the four payers. Deterministic so
    the same card always resolves to the same insurer."""
    h = int(hashlib.sha256(card_number.encode("utf-8")).hexdigest()[:8], 16)
    return PAYERS[h % len(PAYERS)]


async def _resolve_in_network_ids(db: AsyncSession,
                                  payer: Payer) -> List[int]:
    """Pull the hospitals from the DB whose specialties intersect what
    this payer covers. Real plans have explicit network rosters; this
    keeps the demo coherent without bolting on another table."""
    rows = (await db.scalars(
        select(Hospital).where(Hospital.is_active == True)
    )).all()
    accepted = {s.lower() for s in payer.accepts_specialties}
    out: List[int] = []
    for h in rows:
        specs = {s.lower() for s in (h.specialties or [])}
        if specs & accepted:
            out.append(h.id)
    return out


# ── Public API ────────────────────────────────────────────────────────────
async def verify(db: AsyncSession, *,
                 card_number: str,
                 patient_name: Optional[str] = None,
                 patient_dob: Optional[str] = None) -> dict:
    """EDI-270/271-shaped eligibility result.

    A card number starting with ``DENY-`` (case-insensitive) returns
    uncovered to let the demo exercise the "no insurance on file"
    branch. Everything else resolves to a covered status against one
    of the stubbed payers.
    """
    card = (card_number or "").strip()
    if not card:
        return {
            "covered": False, "card_number": "",
            "patient_name": patient_name, "patient_dob": patient_dob,
            "reason": "missing_card_number",
        }
    if card.upper().startswith("DENY-"):
        return {
            "covered": False, "card_number": card,
            "patient_name": patient_name, "patient_dob": patient_dob,
            "reason": "policy_inactive",
        }

    payer = _payer_for_card(card)
    in_network = await _resolve_in_network_ids(db, payer)
    return {
        "covered": True,
        "card_number": card,
        "patient_name": patient_name,
        "patient_dob": patient_dob,
        "payer_code": payer.code,
        "payer_name": payer.name,
        "plan_tier": payer.plan_tier,
        "copay_inr": payer.copay_inr,
        "accepts_specialties": payer.accepts_specialties,
        "in_network_hospital_ids": in_network,
        # Effective-through is fixed per-card-hash so re-verifying within
        # the same demo session keeps a stable expiry.
        "effective_through": _effective_through(card),
        "reason": "active",
    }


def _effective_through(card: str) -> str:
    """Deterministic synthetic expiry — yyyy-mm-dd a few months out."""
    h = int(hashlib.sha256(card.encode("utf-8")).hexdigest()[8:14], 16)
    months = h % 18 + 3       # 3-21 months in the future
    # Compute a target month/year without pulling in dateutil.
    from datetime import datetime
    now = datetime.utcnow()
    total_months = (now.year * 12 + now.month - 1) + months
    yy, mm = divmod(total_months, 12)
    return f"{yy:04d}-{mm + 1:02d}-15"


def list_payers() -> List[dict]:
    """For dashboards that need to render the payer dropdown."""
    return [{"code": p.code, "name": p.name, "plan_tier": p.plan_tier,
             "copay_inr": p.copay_inr,
             "accepts_specialties": p.accepts_specialties}
            for p in PAYERS]
