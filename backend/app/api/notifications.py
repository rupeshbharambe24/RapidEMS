"""Notification subscription management.

Lets a logged-in user list / add / remove / test their delivery channels.
The patient flow is: open dashboard → click "Link Telegram" → it deep-links
to https://t.me/<bot>?start= → user hits Start → grabs their chat_id from
@userinfobot (linked in the help text) → pastes back. From then on every
patient-facing notification reaches them instantly.
"""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..models.notification_subscription import (NotificationChannel,
                                                NotificationSubscription)
from ..models.user import User
from ..services.notifications import (deliver, email_enabled,
                                      telegram_enabled, twilio_enabled)
from .deps import require_user

router = APIRouter(prefix="/notifications", tags=["notifications"])


_VALID_CHANNELS = {c.value for c in NotificationChannel}


class SubscriptionIn(BaseModel):
    channel: str = Field(..., description="telegram | email | sms | web_push")
    target: str = Field(..., min_length=1, max_length=2000)
    label: Optional[str] = Field(default=None, max_length=80)


class SubscriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    channel: str
    target: str
    label: Optional[str] = None
    is_active: bool
    last_used_at: Optional[datetime] = None
    last_error: Optional[str] = None
    created_at: datetime


class CapabilitiesOut(BaseModel):
    telegram: bool
    email: bool
    sms_twilio: bool
    telegram_bot_username: Optional[str] = None


@router.get("/capabilities", response_model=CapabilitiesOut)
def capabilities():
    """What's configured server-side. Frontend uses this to decide which
    Add-Channel buttons to show."""
    return CapabilitiesOut(
        telegram=telegram_enabled(),
        email=email_enabled(),
        sms_twilio=twilio_enabled(),
        telegram_bot_username=settings.telegram_bot_username or None,
    )


@router.get("", response_model=List[SubscriptionOut])
async def list_mine(
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.scalars(
        select(NotificationSubscription)
        .where(NotificationSubscription.user_id == user.id)
        .order_by(NotificationSubscription.created_at.desc())
    )).all()
    return [SubscriptionOut.model_validate(r) for r in rows]


@router.post("", response_model=SubscriptionOut, status_code=201)
async def add(
    payload: SubscriptionIn,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    if payload.channel not in _VALID_CHANNELS:
        raise HTTPException(400,
            detail=f"channel must be one of {sorted(_VALID_CHANNELS)}")
    # Reject duplicates so the list stays sane.
    existing = await db.scalar(
        select(NotificationSubscription).where(
            NotificationSubscription.user_id == user.id,
            NotificationSubscription.channel == payload.channel,
            NotificationSubscription.target == payload.target,
        )
    )
    if existing:
        return SubscriptionOut.model_validate(existing)

    sub = NotificationSubscription(
        user_id=user.id,
        channel=payload.channel,
        target=payload.target.strip(),
        label=payload.label,
    )
    db.add(sub)
    await db.commit()
    await db.refresh(sub)
    return SubscriptionOut.model_validate(sub)


@router.post("/{sub_id}/test", response_model=SubscriptionOut)
async def test(
    sub_id: int,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    sub = await db.scalar(
        select(NotificationSubscription).where(
            NotificationSubscription.id == sub_id,
            NotificationSubscription.user_id == user.id,
        )
    )
    if not sub:
        raise HTTPException(404, detail="Subscription not found.")
    err = await deliver(sub, text=(
        "✅ RapidEMS notification test.\n\n"
        "If you received this, this channel is wired up and you'll get "
        "live updates here when an emergency is dispatched."
    ), subject="RapidEMS notification test")
    await db.commit()
    if err:
        raise HTTPException(502, detail=err)
    await db.refresh(sub)
    return SubscriptionOut.model_validate(sub)


@router.patch("/{sub_id}", response_model=SubscriptionOut)
async def patch_sub(
    sub_id: int,
    payload: SubscriptionIn,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    sub = await db.scalar(
        select(NotificationSubscription).where(
            NotificationSubscription.id == sub_id,
            NotificationSubscription.user_id == user.id,
        )
    )
    if not sub:
        raise HTTPException(404, detail="Subscription not found.")
    sub.channel = payload.channel
    sub.target = payload.target.strip()
    sub.label = payload.label
    await db.commit()
    await db.refresh(sub)
    return SubscriptionOut.model_validate(sub)


@router.delete("/{sub_id}", status_code=204)
async def delete_sub(
    sub_id: int,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    sub = await db.scalar(
        select(NotificationSubscription).where(
            NotificationSubscription.id == sub_id,
            NotificationSubscription.user_id == user.id,
        )
    )
    if not sub:
        raise HTTPException(404, detail="Subscription not found.")
    await db.delete(sub)
    await db.commit()
