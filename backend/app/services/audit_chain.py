"""Tamper-evident audit-log hash chain.

Each AuditLog row stores ``prev_hash`` (the previous row's row_hash) and
``row_hash`` = SHA-256 over (prev_hash + canonical(payload)). Rewriting any
historical row breaks every row that follows; the verifier walks the chain
and reports the first mismatch.

The canonical payload uses sorted-key JSON with ISO timestamps so the hash
is reproducible across machines and Python versions.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.audit_log import AuditLog


GENESIS_HASH = "0" * 64


def _canonical(row: AuditLog) -> str:
    payload = {
        "id": row.id,
        "timestamp": row.timestamp.isoformat() if row.timestamp else None,
        "user_id": row.user_id,
        "action": row.action,
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "details": row.details,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      default=str)


def compute_row_hash(row: AuditLog, prev_hash: str) -> str:
    body = (prev_hash + "|" + _canonical(row)).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


async def append(db: AsyncSession, row: AuditLog) -> AuditLog:
    """Insert ``row`` with prev_hash set from the current chain tip and
    row_hash computed off it. Caller is responsible for the surrounding
    commit. The id is needed for the canonical hash, so we flush() first
    to populate it."""
    if not row.timestamp:
        row.timestamp = datetime.utcnow()
    db.add(row)
    await db.flush()                        # populates row.id

    last = await db.scalar(
        select(AuditLog).where(AuditLog.id < row.id)
        .order_by(AuditLog.id.desc()).limit(1)
    )
    prev = last.row_hash if last and last.row_hash else GENESIS_HASH
    row.prev_hash = prev
    row.row_hash = compute_row_hash(row, prev)
    return row


async def verify_chain(db: AsyncSession, *, limit: Optional[int] = None
                       ) -> Tuple[bool, Optional[int], int]:
    """Walks the chain in id order. Returns
    (ok, first_bad_id_or_None, rows_checked). ``limit`` caps the walk so
    very long histories don't fight the response timeout."""
    stmt = select(AuditLog).order_by(AuditLog.id.asc())
    if limit:
        stmt = stmt.limit(limit)
    rows = list((await db.scalars(stmt)).all())

    expected_prev = GENESIS_HASH
    for r in rows:
        # Legacy rows from before Phase 2.2 have null hashes — accept them
        # but stamp the chain tip to match so newer rows can verify.
        if r.row_hash is None:
            expected_prev = expected_prev
            continue
        if r.prev_hash != expected_prev:
            return False, r.id, len(rows)
        if r.row_hash != compute_row_hash(r, expected_prev):
            return False, r.id, len(rows)
        expected_prev = r.row_hash
    return True, None, len(rows)
