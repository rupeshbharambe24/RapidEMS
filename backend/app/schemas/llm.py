"""Schemas for the LLM extraction endpoint."""
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


PatientType = Literal["cardiac", "trauma", "stroke", "pediatric", "burns", "general"]


class TranscriptIn(BaseModel):
    transcript: str = Field(..., min_length=1, max_length=8000)
    language_hint: Optional[str] = Field(
        default=None,
        description="Optional ISO code or name; the model auto-detects when omitted.",
    )


class MultimodalIn(BaseModel):
    """Same intake parser, but with optional image/audio bytes attached.

    At least one of ``transcript``, ``image_base64``, ``audio_base64`` must be
    supplied. Multimodal inputs force the Gemini provider (Groq is text-only)
    and a single round trip parses every modality together — a photo of an
    injury alongside a Hindi voice note alongside the dispatcher's typed
    notes all collapse into one structured ExtractedEmergency.
    """
    transcript: Optional[str] = Field(default=None, max_length=8000)
    language_hint: Optional[str] = None

    image_base64: Optional[str] = Field(default=None,
        description="Standard base64 (no data: prefix). Up to ~4 MB.",
    )
    image_mime: Optional[str] = Field(default="image/jpeg",
        description="image/jpeg | image/png | image/webp | image/heic.")

    audio_base64: Optional[str] = Field(default=None,
        description="Standard base64 (no data: prefix). Up to ~4 MB.",
    )
    audio_mime: Optional[str] = Field(default="audio/mpeg",
        description="audio/mpeg | audio/wav | audio/ogg | audio/aac | "
                    "audio/flac | audio/webm.")


class ExtractedEmergency(BaseModel):
    """LLM-parsed emergency intake. Fields mirror EmergencyCreate where they exist."""

    patient_age: Optional[int] = Field(default=None, ge=0, le=130)
    patient_gender: Optional[Literal["male", "female", "other"]] = None

    pulse_rate: Optional[int] = Field(default=None, ge=20, le=250)
    blood_pressure_systolic: Optional[int] = Field(default=None, ge=40, le=260)
    blood_pressure_diastolic: Optional[int] = Field(default=None, ge=20, le=180)
    respiratory_rate: Optional[int] = Field(default=None, ge=4, le=60)
    spo2: Optional[float] = Field(default=None, ge=40, le=100)
    gcs_score: Optional[int] = Field(default=None, ge=3, le=15)

    symptoms: List[str] = Field(default_factory=list)
    chief_complaint: Optional[str] = None
    notes: Optional[str] = None
    location_hint: Optional[str] = None

    patient_type: PatientType = "general"
    severity_hint: Optional[int] = Field(default=None, ge=1, le=5)
    language_detected: Optional[str] = None


class ExtractionResult(BaseModel):
    """Wrapper returned by POST /ai/extract."""

    extracted: ExtractedEmergency
    provider_used: Optional[str] = None
    used_fallback: bool = False
    latency_ms: Optional[int] = None
    error: Optional[str] = None
