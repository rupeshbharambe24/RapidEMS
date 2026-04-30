"""Dispatcher copilot endpoint."""
from typing import Any, Dict, List, Optional

from fastapi import (APIRouter, Depends, File, Form, HTTPException, Request,
                     UploadFile)
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..core.ratelimit import limiter
from ..database import get_db
from ..models.user import User
from ..services.copilot import ask
from ..services.voice_transcribe import transcribe
from .deps import require_role

router = APIRouter(prefix="/copilot", tags=["copilot"])


class CopilotAsk(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    context: Optional[Dict[str, Any]] = None


class CopilotToolTrace(BaseModel):
    name: str
    arguments: Dict[str, Any]
    result_preview: str


class CopilotAnswer(BaseModel):
    answer: str
    tool_calls: List[CopilotToolTrace] = []
    provider: str
    latency_ms: int
    error: Optional[str] = None


@router.post("/ask", response_model=CopilotAnswer)
@limiter.limit("20/minute")    # Groq free tier is 30 RPM; leaves headroom
async def copilot_ask(
    request: Request,
    payload: CopilotAsk,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("dispatcher", "admin")),
):
    # Inject server-side defaults the model can rely on.
    ctx = dict(payload.context or {})
    ctx.setdefault("city_lat", settings.seed_city_lat)
    ctx.setdefault("city_lng", settings.seed_city_lng)
    ctx.setdefault("dispatcher", user.username)
    return await ask(db, payload.query, context=ctx)


# ── Voice-first dispatcher (Phase 3.4) ────────────────────────────────────
class VoiceAnswer(CopilotAnswer):
    """``CopilotAnswer`` plus the transcript Whisper produced — the
    frontend renders both so the dispatcher can confirm the question
    was heard correctly before acting on the answer."""
    transcript: str = ""
    transcript_provider: str = ""
    transcribe_ms: int = 0


@router.post("/voice", response_model=VoiceAnswer)
@limiter.limit("12/minute")    # Whisper is more expensive than chat; tighter cap.
async def copilot_voice(
    request: Request,
    audio: Optional[UploadFile] = File(default=None,
        description="Recorded clip (webm/ogg/wav/m4a). Skip if sending transcript."),
    transcript: Optional[str] = Form(default=None,
        description="Text path — used directly if no audio supplied."),
    language: Optional[str] = Form(default=None,
        description="ISO-639-1 hint for Whisper (en, hi, mr, ta, bn)."),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("dispatcher", "admin")),
):
    """Voice → transcript → copilot answer in one round-trip.

    Two paths:
    * ``audio`` upload → Groq Whisper transcribes → reuse copilot ask.
    * ``transcript`` text → skip transcription, useful when the browser
      already ran on-device speech recognition or for offline demos.
    """
    text = (transcript or "").strip()
    transcript_provider = "client" if text else ""
    transcribe_ms = 0

    if audio is not None and audio.filename:
        blob = await audio.read()
        if not blob:
            raise HTTPException(400, detail="Audio upload was empty.")
        if len(blob) > 25 * 1024 * 1024:
            raise HTTPException(413, detail="Audio clip exceeds 25 MB limit.")
        result = await transcribe(
            blob, filename=audio.filename,
            content_type=audio.content_type or "audio/webm",
            language=language,
        )
        text = (result.get("text") or "").strip()
        transcript_provider = str(result.get("provider") or "groq")
        transcribe_ms = int(result.get("latency_ms") or 0)
        if not text:
            err = result.get("error") or "no_speech_detected"
            return VoiceAnswer(
                answer="I couldn't hear anything in that clip. Try again or type the question.",
                tool_calls=[], provider=transcript_provider,
                latency_ms=transcribe_ms, error=str(err),
                transcript="", transcript_provider=transcript_provider,
                transcribe_ms=transcribe_ms,
            )
    elif not text:
        raise HTTPException(400,
            detail="Provide either an audio upload or a transcript text field.")

    ctx: Dict[str, Any] = {
        "city_lat": settings.seed_city_lat,
        "city_lng": settings.seed_city_lng,
        "dispatcher": user.username,
        "modality": "voice",
    }
    answer = await ask(db, text, context=ctx)
    return VoiceAnswer(
        **answer,
        transcript=text,
        transcript_provider=transcript_provider,
        transcribe_ms=transcribe_ms,
    )
