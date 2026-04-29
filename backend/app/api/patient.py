"""Patient-facing endpoints: profile, medical records, raise SOS.

The patient is a User with role=patient. Each user has at most one
PatientProfile (1:1) which carries everything else.
"""
from datetime import datetime
from pathlib import Path
from typing import List

from fastapi import (APIRouter, BackgroundTasks, Depends, File, Form,
                     HTTPException, UploadFile, status)
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.emergency import Emergency
from ..models.medical_record import MedicalRecord, RecordType
from ..models.patient_profile import PatientProfile
from ..models.user import User
from ..schemas.emergency import EmergencyOut
from ..schemas.patient import (MedicalRecordOut, PatientProfileCreate,
                               PatientProfileOut, PatientProfileUpdate,
                               RaiseEmergencyRequest, RaiseEmergencyResponse)
from ..services.dispatch_engine import DispatchError, dispatch_emergency
from ..services.tracking_link import create_link as create_tracking_link
from ..sockets.sio import emit_emergency_created, emit_emergency_dispatched
from .deps import require_role, require_user

router = APIRouter(prefix="/patient", tags=["patient"])


# Uploads land here; created lazily on first upload. Kept out of the
# repo/db so files survive a DB reset and stay user-controlled.
UPLOADS_DIR = Path(__file__).resolve().parent.parent.parent / "uploads"
ALLOWED_RECORD_TYPES = {t.value for t in RecordType}
MAX_UPLOAD_BYTES = 15 * 1024 * 1024   # 15 MB per file


# ── Profile ────────────────────────────────────────────────────────────────
@router.get("/me", response_model=PatientProfileOut)
async def my_profile(
    user: User = Depends(require_role("patient")),
    db: AsyncSession = Depends(get_db),
):
    profile = await db.scalar(
        select(PatientProfile).where(PatientProfile.user_id == user.id)
    )
    if not profile:
        raise HTTPException(404, detail="No profile yet — POST /patient/me to create.")
    return PatientProfileOut.model_validate(profile)


@router.post("/me", response_model=PatientProfileOut, status_code=201)
async def create_profile(
    payload: PatientProfileCreate,
    user: User = Depends(require_role("patient")),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.scalar(
        select(PatientProfile).where(PatientProfile.user_id == user.id)
    )
    if existing:
        raise HTTPException(409, detail="Profile already exists; PATCH it instead.")
    profile = PatientProfile(user_id=user.id, **payload.model_dump())
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return PatientProfileOut.model_validate(profile)


@router.patch("/me", response_model=PatientProfileOut)
async def update_profile(
    payload: PatientProfileUpdate,
    user: User = Depends(require_role("patient")),
    db: AsyncSession = Depends(get_db),
):
    profile = await db.scalar(
        select(PatientProfile).where(PatientProfile.user_id == user.id)
    )
    if not profile:
        raise HTTPException(404, detail="No profile yet — POST /patient/me first.")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(profile, k, v)
    profile.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(profile)
    return PatientProfileOut.model_validate(profile)


# ── Medical records ────────────────────────────────────────────────────────
@router.get("/records", response_model=List[MedicalRecordOut])
async def list_records(
    user: User = Depends(require_role("patient")),
    db: AsyncSession = Depends(get_db),
):
    profile = await _require_profile(db, user)
    rows = (await db.scalars(
        select(MedicalRecord)
        .where(MedicalRecord.patient_id == profile.id)
        .order_by(MedicalRecord.uploaded_at.desc())
    )).all()
    return [MedicalRecordOut.model_validate(r) for r in rows]


@router.post("/records", response_model=MedicalRecordOut, status_code=201)
async def upload_record(
    record_type: str = Form(...),
    description: str = Form(""),
    file: UploadFile = File(...),
    user: User = Depends(require_role("patient")),
    db: AsyncSession = Depends(get_db),
):
    if record_type not in ALLOWED_RECORD_TYPES:
        raise HTTPException(400,
            detail=f"record_type must be one of {sorted(ALLOWED_RECORD_TYPES)}")
    profile = await _require_profile(db, user)

    # Stream to disk with a hard size cap.
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = _sanitise_filename(file.filename or "upload.bin")
    target_dir = UPLOADS_DIR / f"patient_{profile.id}"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{int(datetime.utcnow().timestamp())}_{safe_name}"

    written = 0
    with target.open("wb") as out:
        while chunk := await file.read(64 * 1024):
            written += len(chunk)
            if written > MAX_UPLOAD_BYTES:
                out.close()
                target.unlink(missing_ok=True)
                raise HTTPException(413, detail="File too large (max 15MB).")
            out.write(chunk)

    rec = MedicalRecord(
        patient_id=profile.id,
        record_type=record_type,
        file_name=safe_name,
        file_path=str(target.relative_to(UPLOADS_DIR)),
        file_size=written,
        mime_type=file.content_type,
        description=description or None,
    )
    db.add(rec)
    await db.commit()
    await db.refresh(rec)
    return MedicalRecordOut.model_validate(rec)


@router.get("/records/{rec_id}/download")
async def download_record(
    rec_id: int,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    rec = await db.scalar(select(MedicalRecord).where(MedicalRecord.id == rec_id))
    if not rec:
        raise HTTPException(404, detail="Record not found.")

    # Patients see only their own; clinical staff (paramedic/hospital_staff/
    # admin) see anyone's.
    profile = await db.scalar(
        select(PatientProfile).where(PatientProfile.id == rec.patient_id)
    )
    if user.role == "patient" and profile.user_id != user.id:
        raise HTTPException(403, detail="Not your record.")

    full_path = UPLOADS_DIR / rec.file_path
    if not full_path.exists():
        raise HTTPException(410, detail="File missing on disk.")
    return FileResponse(str(full_path), media_type=rec.mime_type or "application/octet-stream",
                        filename=rec.file_name)


@router.delete("/records/{rec_id}", status_code=204)
async def delete_record(
    rec_id: int,
    user: User = Depends(require_role("patient")),
    db: AsyncSession = Depends(get_db),
):
    rec = await db.scalar(select(MedicalRecord).where(MedicalRecord.id == rec_id))
    if not rec:
        raise HTTPException(404, detail="Record not found.")
    profile = await _require_profile(db, user)
    if rec.patient_id != profile.id:
        raise HTTPException(403, detail="Not your record.")
    full_path = UPLOADS_DIR / rec.file_path
    full_path.unlink(missing_ok=True)
    await db.delete(rec)
    await db.commit()


# ── SOS ────────────────────────────────────────────────────────────────────
@router.post("/sos", response_model=RaiseEmergencyResponse)
async def raise_sos(
    payload: RaiseEmergencyRequest,
    background: BackgroundTasks,
    user: User = Depends(require_role("patient")),
    db: AsyncSession = Depends(get_db),
):
    """Patient-initiated SOS. Creates an Emergency seeded with profile context
    and immediately runs the dispatch pipeline."""
    profile = await db.scalar(
        select(PatientProfile).where(PatientProfile.user_id == user.id)
    )

    age: int | None = None
    if profile and profile.date_of_birth:
        delta = (datetime.utcnow().date() - profile.date_of_birth).days // 365
        if 0 <= delta <= 130:
            age = int(delta)

    emergency = Emergency(
        patient_name=profile.full_name if profile else user.full_name,
        patient_age=age,
        patient_gender=profile.gender if profile else None,
        phone=profile.phone if profile else None,
        next_of_kin_phone=profile.emergency_contact_phone if profile else None,
        location_lat=payload.location_lat,
        location_lng=payload.location_lng,
        location_address=payload.location_address,
        chief_complaint=payload.chief_complaint,
        symptoms=payload.symptoms,
        notes=payload.raw_transcript,
    )
    db.add(emergency)
    await db.commit()
    await db.refresh(emergency)

    background.add_task(emit_emergency_created, {
        "id": emergency.id,
        "lat": emergency.location_lat,
        "lng": emergency.location_lng,
        "status": emergency.status,
        "address": emergency.location_address,
        "chief_complaint": emergency.chief_complaint,
        "symptoms": emergency.symptoms,
        "source": "patient_sos",
    })

    # Auto-dispatch immediately. If nothing's available, return the bare
    # emergency_id so the client can show "we logged your call".
    try:
        plan = await dispatch_emergency(db, emergency, user_id=user.id)
        background.add_task(emit_emergency_dispatched, plan.model_dump())

        # Auto-create a tracking link if the profile has a NoK contact —
        # the patient gets the URL inline so they can forward it.
        tracking_token: Optional[str] = None
        if profile and profile.emergency_contact_phone:
            try:
                _, tracking_token = await create_tracking_link(
                    db, emergency.id,
                    dispatch_id=plan.dispatch_id,
                    nok_name=profile.emergency_contact_name,
                    nok_phone=profile.emergency_contact_phone,
                    nok_relation=profile.emergency_contact_relation,
                )
            except Exception:  # noqa: BLE001
                pass

        return RaiseEmergencyResponse(
            emergency_id=emergency.id,
            severity_level=plan.severity_level,
            severity_label=plan.severity_label,
            dispatch_id=plan.dispatch_id,
            ambulance_registration=plan.ambulance_registration,
            hospital_name=plan.hospital_name,
            eta_minutes=plan.predicted_eta_minutes,
            tracking_token=tracking_token,
            message=f"Help dispatched: {plan.ambulance_registration} → "
                    f"{plan.hospital_name} (ETA {plan.predicted_eta_minutes:.1f}m)",
        )
    except DispatchError as exc:
        return RaiseEmergencyResponse(
            emergency_id=emergency.id,
            message=f"Emergency logged (could not dispatch yet: {exc})",
        )


@router.get("/active-emergency", response_model=EmergencyOut | None)
async def my_active_emergency(
    user: User = Depends(require_role("patient")),
    db: AsyncSession = Depends(get_db),
):
    """The patient's most recent open emergency (for the 'we're on the way'
    banner on their dashboard)."""
    profile = await db.scalar(
        select(PatientProfile).where(PatientProfile.user_id == user.id)
    )
    if not profile:
        return None
    e = await db.scalar(
        select(Emergency)
        .where(Emergency.phone == profile.phone)
        .where(Emergency.status.in_(["pending", "dispatched"]))
        .order_by(Emergency.created_at.desc())
    )
    return EmergencyOut.model_validate(e) if e else None


# ── Helpers ────────────────────────────────────────────────────────────────
async def _require_profile(db: AsyncSession, user: User) -> PatientProfile:
    profile = await db.scalar(
        select(PatientProfile).where(PatientProfile.user_id == user.id)
    )
    if not profile:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            detail="Create your patient profile first (POST /patient/me).")
    return profile


def _sanitise_filename(name: str) -> str:
    # Strip path separators and limit length; the filesystem timestamp prefix
    # at the call site already prevents collisions.
    bad = '/\\:*?"<>|\0\r\n\t'
    cleaned = "".join("_" if c in bad else c for c in name).strip()
    return (cleaned or "upload.bin")[:120]
