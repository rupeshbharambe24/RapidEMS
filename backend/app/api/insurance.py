"""Insurance verification — payer + network lookup at pickup time."""
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.user import User
from ..services.insurance import list_payers, verify
from .deps import require_role


router = APIRouter(prefix="/insurance", tags=["insurance"])


class VerifyIn(BaseModel):
    card_number: str = Field(..., min_length=1, max_length=64,
        description="Insurance card / policy ID. "
                    "Cards prefixed DENY- return uncovered (demo aid).")
    patient_name: Optional[str] = Field(default=None, max_length=120)
    patient_dob: Optional[str] = Field(default=None, max_length=20,
        description="ISO-8601 date or free text — passed through.")


class VerifyOut(BaseModel):
    covered: bool
    card_number: str
    patient_name: Optional[str] = None
    patient_dob: Optional[str] = None
    payer_code: Optional[str] = None
    payer_name: Optional[str] = None
    plan_tier: Optional[str] = None
    copay_inr: Optional[int] = None
    accepts_specialties: List[str] = []
    in_network_hospital_ids: List[int] = []
    effective_through: Optional[str] = None
    reason: str


class PayerOut(BaseModel):
    code: str
    name: str
    plan_tier: str
    copay_inr: int
    accepts_specialties: List[str]


@router.get("/payers", response_model=List[PayerOut])
async def payers(_: User = Depends(require_role("dispatcher", "paramedic",
                                                "hospital_staff", "admin"))):
    return [PayerOut(**p) for p in list_payers()]


@router.post("/verify", response_model=VerifyOut)
async def verify_eligibility(
    payload: VerifyIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role("dispatcher", "paramedic",
                                   "hospital_staff", "admin")),
):
    """EDI-270/271-shaped eligibility check. Returns the payer, plan
    tier, in-network hospital IDs, and effective-through date so the
    dispatcher dashboard can flag in-network options before the bay is
    committed."""
    result = await verify(
        db, card_number=payload.card_number,
        patient_name=payload.patient_name,
        patient_dob=payload.patient_dob,
    )
    return VerifyOut(**result)
