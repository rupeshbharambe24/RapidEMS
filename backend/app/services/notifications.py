"""User-facing notifications across multiple channels.

Channels (all optional, all free tier):
  - Telegram (primary): instant, free, no rate limit. Recipients /start the
    bot once and we keep their chat_id in notification_subscriptions.
  - Email (SMTP): Gmail App Password or SendGrid free tier.
  - SMS (Twilio): paid; only enabled when all three Twilio env vars set.
  - Console: dev fallback so the surface still works with no creds.

Public surface:
    await notify_user(db, user_id, text, *, subject=None, kind='info')
        Fan out to every active subscription on that user across enabled
        channels. Failures are logged on the subscription row but don't
        bubble — one bad target shouldn't drop the rest of the broadcast.

    await notify_dispatch_created(db, dispatch, plan)
    await notify_dispatch_status(db, dispatch, new_status, hospital, ambulance)
        Higher-level helpers used by dispatch_engine and driver routes.
"""
from __future__ import annotations

import asyncio
import smtplib
import ssl
from datetime import datetime
from email.message import EmailMessage
from typing import Iterable, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..core.logging import log
from ..models.ambulance import Ambulance
from ..models.dispatch import Dispatch
from ..models.emergency import Emergency
from ..models.hospital import Hospital
from ..models.notification_subscription import (NotificationChannel,
                                                NotificationSubscription)
from ..models.patient_profile import PatientProfile
from ..models.user import User


# ── Channel availability ───────────────────────────────────────────────────
def telegram_enabled() -> bool:
    return bool(settings.telegram_bot_token)


def email_enabled() -> bool:
    return bool(settings.smtp_host and settings.smtp_username
                and settings.smtp_from)


def twilio_enabled() -> bool:
    return bool(settings.twilio_account_sid and settings.twilio_auth_token
                and settings.twilio_from_number)


# ── Channel implementations ────────────────────────────────────────────────
async def _send_telegram(chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    body = {"chat_id": chat_id, "text": text, "parse_mode": "HTML",
            "disable_web_page_preview": True}
    async with httpx.AsyncClient(timeout=8.0) as client:
        r = await client.post(url, json=body)
        r.raise_for_status()


def _send_email_blocking(to: str, subject: str, text: str) -> None:
    msg = EmailMessage()
    from_addr = (f'"{settings.smtp_from_name}" <{settings.smtp_from}>'
                 if settings.smtp_from_name else settings.smtp_from)
    msg["From"] = from_addr
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)
    if settings.smtp_use_tls:
        ctx = ssl.create_default_context()
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as s:
            s.starttls(context=ctx)
            if settings.smtp_username:
                s.login(settings.smtp_username, settings.smtp_password)
            s.send_message(msg)
    else:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as s:
            if settings.smtp_username:
                s.login(settings.smtp_username, settings.smtp_password)
            s.send_message(msg)


async def _send_email(to: str, subject: str, text: str) -> None:
    # Run blocking smtplib in a worker thread so the event loop stays free.
    await asyncio.to_thread(_send_email_blocking, to, subject, text)


async def _send_twilio_sms(to: str, text: str) -> None:
    url = (f"https://api.twilio.com/2010-04-01/Accounts/"
           f"{settings.twilio_account_sid}/Messages.json")
    auth = (settings.twilio_account_sid, settings.twilio_auth_token)
    data = {"From": settings.twilio_from_number, "To": to, "Body": text}
    async with httpx.AsyncClient(timeout=10.0, auth=auth) as client:
        r = await client.post(url, data=data)
        r.raise_for_status()


# ── Public dispatcher ──────────────────────────────────────────────────────
async def deliver(sub: NotificationSubscription, *,
                  text: str, subject: Optional[str] = None) -> Optional[str]:
    """Send `text` over the channel `sub` describes. Returns an error
    message on failure or None on success. Mutates the subscription row
    (last_used_at / last_error)."""
    try:
        if sub.channel == NotificationChannel.TELEGRAM.value:
            if not telegram_enabled():
                raise RuntimeError("telegram bot token not configured")
            await _send_telegram(sub.target, text)
        elif sub.channel == NotificationChannel.EMAIL.value:
            if not email_enabled():
                raise RuntimeError("smtp not configured")
            await _send_email(sub.target, subject or "RapidEMS notification", text)
        elif sub.channel == NotificationChannel.SMS.value:
            if not twilio_enabled():
                raise RuntimeError("twilio not configured")
            await _send_twilio_sms(sub.target, text)
        else:
            raise RuntimeError(f"unsupported channel: {sub.channel}")
        sub.last_used_at = datetime.utcnow()
        sub.last_error = None
        return None
    except Exception as exc:  # noqa: BLE001
        sub.last_error = f"{type(exc).__name__}: {exc}"[:500]
        log.warning(f"notify {sub.channel}/{sub.id}: {sub.last_error}")
        return sub.last_error


async def notify_user(
    db: AsyncSession, user_id: int, text: str, *,
    subject: Optional[str] = None, kind: str = "info",
    channels: Optional[Iterable[str]] = None,
) -> int:
    """Fan out to every active subscription for the user. Returns the
    number of successful deliveries."""
    if not user_id:
        return 0
    stmt = select(NotificationSubscription).where(
        NotificationSubscription.user_id == user_id,
        NotificationSubscription.is_active == True,
    )
    if channels:
        stmt = stmt.where(NotificationSubscription.channel.in_(list(channels)))
    subs = (await db.scalars(stmt)).all()
    if not subs:
        # Always log to console so dev sees something even with no subs.
        log.info(f"[notify→user {user_id}] (no subs) {text}")
        return 0
    sent = 0
    for sub in subs:
        err = await deliver(sub, text=text, subject=subject)
        if err is None:
            sent += 1
    await db.commit()
    return sent


# ── High-level templates ───────────────────────────────────────────────────
async def notify_dispatch_created(
    db: AsyncSession, dispatch: Dispatch, plan,
) -> None:
    """Patient + hospital staff get a dispatch-created ping."""
    emergency = await db.scalar(
        select(Emergency).where(Emergency.id == dispatch.emergency_id))
    hospital = await db.scalar(
        select(Hospital).where(Hospital.id == dispatch.hospital_id))
    ambulance = await db.scalar(
        select(Ambulance).where(Ambulance.id == dispatch.ambulance_id))

    eta_m = round((dispatch.predicted_eta_seconds or 0) / 60.0, 1)

    # Patient (if the emergency is tied to a patient profile)
    if emergency and emergency.phone:
        profile = await db.scalar(
            select(PatientProfile).where(PatientProfile.phone == emergency.phone))
        if profile:
            patient_msg = (
                f"🚑 <b>Help is on the way.</b>\n\n"
                f"Ambulance <b>{ambulance.registration_number}</b> "
                f"({ambulance.ambulance_type.upper()}) dispatched.\n"
                f"ETA <b>{eta_m} min</b>.\n"
                f"Receiving facility: <b>{hospital.name}</b>.\n\n"
                f"Stay calm. Stay where you are unless safety requires otherwise."
            )
            await notify_user(db, profile.user_id, patient_msg,
                              subject=f"RapidEMS: ambulance dispatched (ETA {eta_m}m)")

    # Hospital staff for the destination facility
    staff_rows = (await db.scalars(
        select(User).where(User.assigned_hospital_id == hospital.id,
                           User.is_active == True)
    )).all()
    if staff_rows and emergency:
        staff_msg = (
            f"🏥 <b>Inbound at {hospital.name}</b>\n\n"
            f"SEV-{emergency.predicted_severity or '?'} · "
            f"{(emergency.inferred_patient_type or 'general').upper()}\n"
            f"ETA <b>{eta_m} min</b> · {ambulance.registration_number}\n"
            f"{emergency.patient_name or 'Patient'}"
            f"{f', {emergency.patient_age}' if emergency.patient_age else ''}\n"
            f"Symptoms: {', '.join((emergency.symptoms or [])[:5]) or '—'}"
        )
        for staff in staff_rows:
            await notify_user(db, staff.id, staff_msg,
                              subject=f"Inbound SEV-{emergency.predicted_severity}: ETA {eta_m}m")


async def notify_dispatch_status(
    db: AsyncSession, dispatch: Dispatch, new_status: str,
) -> None:
    """Patient gets a status update ('on scene', 'transporting', ...)."""
    emergency = await db.scalar(
        select(Emergency).where(Emergency.id == dispatch.emergency_id))
    if not emergency or not emergency.phone:
        return
    profile = await db.scalar(
        select(PatientProfile).where(PatientProfile.phone == emergency.phone))
    if not profile:
        return

    label = {
        "en_route":          "🚑 Ambulance is en route to you.",
        "on_scene":          "📍 The crew has arrived on scene.",
        "transporting":      "🏥 You're being transported now.",
        "arrived_hospital":  "✅ Arrived at the hospital.",
        "completed":         "🏁 Trip completed. Take care.",
    }.get(new_status)
    if not label:
        return
    await notify_user(db, profile.user_id, label,
                      subject=f"RapidEMS: status — {new_status.replace('_',' ')}")
