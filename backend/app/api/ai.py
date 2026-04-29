"""Raw AI inference endpoints — exposed for the frontend's real-time triage hint."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.emergency import Emergency
from ..schemas.ai import (ETARequest, ETAResponse, ExplainRequest,
                          ExplainResponse, HotspotForecast,
                          TrafficRequest, TrafficResponse,
                          TriageRequest, TriageResponse)
from ..schemas.llm import ExtractionResult, TranscriptIn
from ..services.ai_service import get_ai_service
from ..services.llm_extractor import get_llm_extractor
from ..services.severity_explainer import explain as explain_severity

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/triage", response_model=TriageResponse)
def triage(payload: TriageRequest, ai=Depends(get_ai_service)):
    out = ai.predict_severity(
        age=payload.age,
        gender=payload.gender,
        gcs=payload.gcs_score,
        spo2=payload.spo2,
        pulse=payload.pulse_rate,
        resp_rate=payload.respiratory_rate,
        bp_systolic=payload.blood_pressure_systolic,
        bp_diastolic=payload.blood_pressure_diastolic,
        symptoms=payload.symptoms,
    )
    return TriageResponse(**out)


@router.post("/eta", response_model=ETAResponse)
def predict_eta(payload: ETARequest, ai=Depends(get_ai_service)):
    out = ai.predict_eta(**payload.model_dump())
    return ETAResponse(eta_seconds=out["eta_seconds"],
                       eta_minutes=out["eta_minutes"],
                       used_fallback=out["used_fallback"])


@router.post("/traffic", response_model=TrafficResponse)
def predict_traffic(payload: TrafficRequest, ai=Depends(get_ai_service)):
    out = ai.predict_congestion(**payload.model_dump())
    return TrafficResponse(congestion=out["congestion"],
                           used_fallback=out["used_fallback"])


@router.post("/explain", response_model=ExplainResponse)
async def explain_triage(
    payload: ExplainRequest,
    db: AsyncSession = Depends(get_db),
    ai=Depends(get_ai_service),
):
    """Why was this call triaged at SEV-X? Returns top contributing factors
    plus a short Groq-narrated paragraph for the dispatcher tooltip."""
    if (payload.emergency_id is None) == (payload.inline is None):
        raise HTTPException(400, detail="Provide exactly one of emergency_id or inline.")

    if payload.emergency_id is not None:
        e = await db.scalar(
            select(Emergency).where(Emergency.id == payload.emergency_id))
        if not e:
            raise HTTPException(404, detail="Emergency not found.")
        # Re-run severity in case it wasn't computed yet (e.g. PENDING).
        triage = ai.predict_severity(
            age=e.patient_age or 40,
            gender=e.patient_gender or "other",
            gcs=e.gcs_score, spo2=e.spo2,
            pulse=e.pulse_rate, resp_rate=e.respiratory_rate,
            bp_systolic=e.blood_pressure_systolic,
            bp_diastolic=e.blood_pressure_diastolic,
            symptoms=e.symptoms or [],
        )
        return await explain_severity(
            severity_level=int(e.predicted_severity or triage["severity_level"]),
            confidence=float(e.severity_confidence or triage["confidence"]),
            used_fallback=triage["used_fallback"],
            age=e.patient_age, gender=e.patient_gender,
            pulse_rate=e.pulse_rate, spo2=e.spo2,
            blood_pressure_systolic=e.blood_pressure_systolic,
            blood_pressure_diastolic=e.blood_pressure_diastolic,
            respiratory_rate=e.respiratory_rate, gcs_score=e.gcs_score,
            symptoms=e.symptoms or [],
        )

    # Inline path — recompute severity from the supplied features.
    inl = payload.inline
    triage = ai.predict_severity(
        age=inl.age, gender=inl.gender,
        gcs=inl.gcs_score, spo2=inl.spo2,
        pulse=inl.pulse_rate, resp_rate=inl.respiratory_rate,
        bp_systolic=inl.blood_pressure_systolic,
        bp_diastolic=inl.blood_pressure_diastolic,
        symptoms=inl.symptoms,
    )
    return await explain_severity(
        severity_level=triage["severity_level"],
        confidence=triage["confidence"],
        used_fallback=triage["used_fallback"],
        age=inl.age, gender=inl.gender,
        pulse_rate=inl.pulse_rate, spo2=inl.spo2,
        blood_pressure_systolic=inl.blood_pressure_systolic,
        blood_pressure_diastolic=inl.blood_pressure_diastolic,
        respiratory_rate=inl.respiratory_rate, gcs_score=inl.gcs_score,
        symptoms=inl.symptoms,
    )


@router.post("/extract", response_model=ExtractionResult)
async def extract_transcript(payload: TranscriptIn):
    """Parse a free-text caller transcript into structured intake fields.

    Returns the parsed payload plus metadata about which provider answered and
    whether a fallback was used. The dispatcher UI uses this to pre-fill the
    intake form; nothing is persisted here.
    """
    extractor = get_llm_extractor()
    parsed, meta = await extractor.extract(payload.transcript,
                                           language_hint=payload.language_hint)
    return ExtractionResult(extracted=parsed, **meta)


@router.get("/hotspots", response_model=HotspotForecast)
def get_hotspots(zone_id: int = 0, ai=Depends(get_ai_service)):
    """Return the next 24-hour forecast for a zone.

    For the demo we generate a synthetic recent-counts window.
    A production system would fetch the last 48 h from `traffic_snapshots`.
    """
    import numpy as np
    rng = np.random.default_rng(zone_id)
    fake_recent = (rng.poisson(2.0, 48)).tolist()
    out = ai.forecast_hotspots(recent_counts=fake_recent, zone_id=zone_id)
    return HotspotForecast(**out)
