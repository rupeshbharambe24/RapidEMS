"""Time-limited signed family-tracking URLs.

The plaintext token is HMAC-signed with ``settings.secret_key`` via
``itsdangerous`` and embeds the FamilyLink row id. Storage is hash-only —
a DB read can't recover working tokens, only invalidate them.

Token lifecycle
---------------
    create_link  → returns (row, token);  token is shown to the issuer
                                         exactly once.
    verify_token → resolves token → row,  rejecting expired, revoked,
                                          mismatched, or unknown links.
    revoke       → sets revoked_at on the row; subsequent verifies fail.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from typing import Optional, Tuple

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models.family_link import FamilyLink


_SALT = "rapidems.family_tracking.v1"
DEFAULT_TTL_HOURS = 4


def _serializer() -> URLSafeTimedSerializer:
    # Built per-call so tests / config swaps pick up SECRET_KEY changes.
    return URLSafeTimedSerializer(settings.secret_key, salt=_SALT)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def create_link(
    db: AsyncSession,
    emergency_id: int,
    *,
    dispatch_id: Optional[int] = None,
    nok_name: Optional[str] = None,
    nok_phone: Optional[str] = None,
    nok_relation: Optional[str] = None,
    notes: Optional[str] = None,
    ttl_hours: int = DEFAULT_TTL_HOURS,
) -> Tuple[FamilyLink, str]:
    """Persist a new FamilyLink row and return it together with the only
    plaintext copy of the signed token."""
    expires_at = datetime.utcnow() + timedelta(hours=ttl_hours)
    row = FamilyLink(
        emergency_id=emergency_id,
        dispatch_id=dispatch_id,
        nok_name=nok_name,
        nok_phone=nok_phone,
        nok_relation=nok_relation,
        notes=notes,
        expires_at=expires_at,
        # token_hash filled in below once we know the row id.
        token_hash=hashlib.sha256(b"placeholder").hexdigest(),
    )
    db.add(row)
    await db.flush()                          # gets row.id without commit
    token = _serializer().dumps({"link_id": row.id})
    row.token_hash = _hash_token(token)
    await db.commit()
    await db.refresh(row)
    return row, token


async def verify_token(
    db: AsyncSession, token: str, *,
    max_age_seconds: int = DEFAULT_TTL_HOURS * 3600,
) -> FamilyLink:
    """Returns the matching FamilyLink. Raises ``ValueError`` with a
    user-safe reason on any failure."""
    if not token:
        raise ValueError("missing token")
    try:
        payload = _serializer().loads(token, max_age=max_age_seconds)
    except SignatureExpired:
        raise ValueError("link has expired")
    except BadSignature:
        raise ValueError("invalid link")
    if not isinstance(payload, dict):
        raise ValueError("invalid link payload")
    link_id = payload.get("link_id")
    if not isinstance(link_id, int):
        raise ValueError("invalid link payload")

    row = await db.scalar(select(FamilyLink).where(FamilyLink.id == link_id))
    if not row:
        raise ValueError("link not found")
    if row.token_hash != _hash_token(token):
        raise ValueError("link mismatch")
    if row.revoked_at:
        raise ValueError("link revoked")
    if row.expires_at and row.expires_at < datetime.utcnow():
        raise ValueError("link has expired")
    return row
