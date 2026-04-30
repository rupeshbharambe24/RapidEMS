"""Data retention + Subject Access Request helpers.

DPDP Act / HIPAA-equivalent posture:
- Default retention windows for the major PHI-bearing tables:
    emergencies (resolved):           90 days  → soft-redact
    medical_records:                  on demand from patient (DSR delete)
    family_links (revoked/expired):   30 days  → hard delete
    family_link_notes (orphaned):     30 days
    patient_telemetry (>180 days):    180 days → hard delete
    audit_log:                        retained indefinitely (regulatory)
- Retention is enforced by ``run_retention_sweep()``. Run it on a cron
  (apscheduler or external) to age out PHI; default is opt-in via env so
  test environments don't lose data.

Subject Access Request:
- ``patient_export_bundle()`` returns a complete dump of one patient's
  data — profile, records (metadata only — file contents are streamed
  separately), telemetry, emergencies, dispatches, family-link history.
- ``patient_erasure()`` redacts PII from past emergencies, deletes the
  profile + records + telemetry, and records an audit-log row capturing
  the erasure event so we keep the chain intact even when the underlying
  PHI is gone.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.logging import log
from ..models.audit_log import AuditLog
from ..models.dispatch import Dispatch
from ..models.emergency import Emergency
from ..models.family_link import FamilyLink
from ..models.family_link_note import FamilyLinkNote
from ..models.medical_record import MedicalRecord
from ..models.patient_profile import PatientProfile
from ..models.patient_telemetry import PatientTelemetry
from .audit_chain import append as audit_append


# Default windows (days). Overridable in run_retention_sweep().
RESOLVED_EMERGENCY_REDACT_DAYS = 90
REVOKED_LINK_DELETE_DAYS = 30
TELEMETRY_DELETE_DAYS = 180


# ── Retention sweep ───────────────────────────────────────────────────────
async def run_retention_sweep(
    db: AsyncSession, *,
    resolved_redact_days: int = RESOLVED_EMERGENCY_REDACT_DAYS,
    revoked_link_delete_days: int = REVOKED_LINK_DELETE_DAYS,
    telemetry_delete_days: int = TELEMETRY_DELETE_DAYS,
) -> Dict[str, int]:
    """Age out PHI per the configured windows.

    Returns counts of rows touched per table.
    """
    now = datetime.utcnow()
    counts = {"emergencies_redacted": 0, "links_deleted": 0,
              "notes_deleted": 0, "telemetry_deleted": 0}

    # 1. Resolved emergencies older than N days — wipe PII columns but
    #    keep the row so the audit chain still references it.
    cutoff_em = now - timedelta(days=resolved_redact_days)
    stale_em = list((await db.scalars(
        select(Emergency)
        .where(Emergency.status == "resolved",
               Emergency.resolved_at.isnot(None),
               Emergency.resolved_at < cutoff_em,
               Emergency.patient_name.isnot(None))
    )).all())
    for e in stale_em:
        e.patient_name = None
        e.phone = None
        e.next_of_kin_phone = None
        e.location_address = None
        e.notes = None
    counts["emergencies_redacted"] = len(stale_em)

    # 2. Family links: revoked OR expired more than N days ago.
    cutoff_link = now - timedelta(days=revoked_link_delete_days)
    stale_links = list((await db.scalars(
        select(FamilyLink).where(
            (FamilyLink.revoked_at.isnot(None)) | (FamilyLink.expires_at < now),
        )
    )).all())
    expired_old = [l for l in stale_links
                   if (l.revoked_at and l.revoked_at < cutoff_link)
                   or (l.expires_at and l.expires_at < cutoff_link)]
    for l in expired_old:
        # cascade-deletes notes via family_link_notes.family_link_id FK ON DELETE
        await db.execute(
            delete(FamilyLinkNote).where(
                FamilyLinkNote.family_link_id == l.id))
        await db.delete(l)
    counts["links_deleted"] = len(expired_old)

    # 3. Patient telemetry rows older than N days.
    cutoff_tel = now - timedelta(days=telemetry_delete_days)
    res = await db.execute(
        delete(PatientTelemetry)
        .where(PatientTelemetry.recorded_at < cutoff_tel)
    )
    counts["telemetry_deleted"] = res.rowcount or 0

    await audit_append(db, AuditLog(
        action="retention_sweep", entity_type="system", entity_id=None,
        details={"counts": counts, "windows_days": {
            "resolved_emergency": resolved_redact_days,
            "revoked_link": revoked_link_delete_days,
            "telemetry": telemetry_delete_days,
        }},
    ))
    await db.commit()
    log.info(f"retention_sweep: {counts}")
    return counts


# ── DSR: export ──────────────────────────────────────────────────────────
async def patient_export_bundle(
    db: AsyncSession, profile_id: int,
) -> Dict[str, Any]:
    """Returns a JSON-serialisable dump of everything we hold on one
    patient. Medical-record file payloads are referenced by id +
    download URL only — the caller streams them through
    /patient/records/{id}/download."""
    profile = await db.scalar(
        select(PatientProfile).where(PatientProfile.id == profile_id))
    if not profile:
        return {"profile": None, "records": [], "telemetry": [],
                "emergencies": [], "family_links": []}

    records = list((await db.scalars(
        select(MedicalRecord).where(MedicalRecord.patient_id == profile_id)
        .order_by(MedicalRecord.uploaded_at.desc())
    )).all())
    telemetry = list((await db.scalars(
        select(PatientTelemetry).where(PatientTelemetry.patient_id == profile_id)
        .order_by(PatientTelemetry.recorded_at.desc())
    )).all())
    # Emergencies tied to this patient via phone (the same heuristic the
    # rest of the app uses).
    em_rows = list((await db.scalars(
        select(Emergency).where(Emergency.phone == profile.phone)
        .order_by(Emergency.created_at.desc())
    )).all())
    em_ids = [e.id for e in em_rows]
    family_links = list((await db.scalars(
        select(FamilyLink).where(FamilyLink.emergency_id.in_(em_ids))
    )).all()) if em_ids else []

    return {
        "profile": _row_to_dict(profile),
        "records": [_row_to_dict(r) for r in records],
        "telemetry": [_row_to_dict(t) for t in telemetry],
        "emergencies": [_row_to_dict(e) for e in em_rows],
        "family_links": [_row_to_dict(l) for l in family_links],
    }


# ── DSR: erasure ─────────────────────────────────────────────────────────
async def patient_erasure(
    db: AsyncSession, profile_id: int, *, requested_by_user_id: Optional[int] = None,
) -> Dict[str, int]:
    """Hard-delete all of a patient's PHI.

    - Profile, medical records (DB rows + uploaded file paths recorded
      but file deletion is the file-store layer's responsibility — we
      log paths so an offline cleaner can wipe them).
    - Telemetry rows.
    - Patient-tied emergencies are *redacted* (PII wiped) rather than
      deleted, because they're referenced by dispatch + audit rows.
    - An audit_log row records what was erased and when.
    """
    counts = {"records": 0, "telemetry": 0, "emergencies_redacted": 0,
              "family_links": 0}
    profile = await db.scalar(
        select(PatientProfile).where(PatientProfile.id == profile_id))
    if not profile:
        return counts

    record_paths = [r.file_path for r in (await db.scalars(
        select(MedicalRecord).where(MedicalRecord.patient_id == profile_id)
    )).all()]
    res = await db.execute(
        delete(MedicalRecord).where(MedicalRecord.patient_id == profile_id))
    counts["records"] = res.rowcount or 0

    res = await db.execute(
        delete(PatientTelemetry).where(PatientTelemetry.patient_id == profile_id))
    counts["telemetry"] = res.rowcount or 0

    em_rows = list((await db.scalars(
        select(Emergency).where(Emergency.phone == profile.phone)
    )).all())
    for e in em_rows:
        e.patient_name = None
        e.phone = None
        e.next_of_kin_phone = None
        e.location_address = None
        e.notes = None
    counts["emergencies_redacted"] = len(em_rows)

    em_ids = [e.id for e in em_rows]
    if em_ids:
        res = await db.execute(
            delete(FamilyLink).where(FamilyLink.emergency_id.in_(em_ids)))
        counts["family_links"] = res.rowcount or 0

    await db.delete(profile)

    await audit_append(db, AuditLog(
        user_id=requested_by_user_id,
        action="patient_erasure", entity_type="patient_profile",
        entity_id=profile_id,
        details={"counts": counts, "file_paths": record_paths},
    ))
    await db.commit()
    return counts


def _row_to_dict(row) -> Dict[str, Any]:
    """Cheap SQLAlchemy → dict conversion for JSON export."""
    out: Dict[str, Any] = {}
    for col in row.__table__.columns:
        val = getattr(row, col.name)
        if isinstance(val, datetime):
            val = val.isoformat()
        out[col.name] = val
    return out
