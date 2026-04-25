"""Raw AI inference endpoints — exposed for the frontend's real-time triage hint."""
from fastapi import APIRouter, Depends

from ..schemas.ai import (ETARequest, ETAResponse, HotspotForecast,
                          TrafficRequest, TrafficResponse,
                          TriageRequest, TriageResponse)
from ..schemas.llm import ExtractionResult, TranscriptIn
from ..services.ai_service import get_ai_service
from ..services.llm_extractor import get_llm_extractor

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
