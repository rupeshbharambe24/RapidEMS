"""Voice → text transcription for the dispatcher copilot.

Wraps Groq's OpenAI-compatible Whisper endpoint (whisper-large-v3-turbo
on the free tier — ~250x realtime). The output feeds straight into the
existing copilot tool-calling loop, so a dispatcher can run an entire
scene by talking instead of typing.

Why Groq Whisper specifically:
- The same key the copilot already uses, no second provider to manage.
- v3-turbo handles English plus the multilingual triage cases (Hindi /
  Marathi / Tamil / Bengali — same locales we ship i18n strings for).
- Sub-second latency keeps the voice loop conversational.

Falls through with ``provider='disabled'`` when GROQ_API_KEY is unset
so the same endpoint can be used in offline demos with the
``transcript`` text path instead of audio upload.
"""
from __future__ import annotations

import time
from typing import Dict, Optional

import httpx

from ..config import settings
from ..core.logging import log


GROQ_TRANSCRIBE_URL = "https://api.groq.com/openai/v1/audio/transcriptions"


async def transcribe(
    audio_bytes: bytes,
    *,
    filename: str = "clip.webm",
    content_type: str = "audio/webm",
    language: Optional[str] = None,
) -> Dict[str, object]:
    """Returns ``{text, provider, latency_ms, error?}``.

    ``language`` is an optional ISO-639-1 hint (``en``, ``hi``, ``mr`` …)
    that nudges Whisper when the dispatcher is on a non-English call;
    omitting it lets the model auto-detect.
    """
    if not settings.groq_api_key:
        return {"text": "", "provider": "disabled", "latency_ms": 0,
                "error": "no_groq_key"}
    if not audio_bytes:
        return {"text": "", "provider": "groq", "latency_ms": 0,
                "error": "empty_audio"}

    headers = {"Authorization": f"Bearer {settings.groq_api_key}"}
    data: Dict[str, str] = {
        "model": settings.groq_whisper_model,
        "response_format": "json",
        "temperature": "0",
    }
    if language:
        data["language"] = language

    files = {"file": (filename, audio_bytes, content_type)}
    t0 = time.perf_counter()
    try:
        # Whisper requests can be larger than the default 5 s timeout for
        # longer clips; allow up to 30 s for a 60-second recording.
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(GROQ_TRANSCRIBE_URL, headers=headers,
                                  data=data, files=files)
            r.raise_for_status()
            text = (r.json().get("text") or "").strip()
        return {"text": text, "provider": "groq",
                "latency_ms": int((time.perf_counter() - t0) * 1000)}
    except httpx.HTTPStatusError as exc:
        body = ""
        try:
            body = exc.response.text[:300]
        except Exception:  # noqa: BLE001
            pass
        log.warning(f"voice transcribe: HTTP {exc.response.status_code} — {body}")
        return {"text": "", "provider": "groq",
                "latency_ms": int((time.perf_counter() - t0) * 1000),
                "error": f"http_{exc.response.status_code}"}
    except Exception as exc:  # noqa: BLE001
        log.warning(f"voice transcribe: {exc}")
        return {"text": "", "provider": "groq",
                "latency_ms": int((time.perf_counter() - t0) * 1000),
                "error": str(exc)}
