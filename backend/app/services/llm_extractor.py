"""LLM-backed transcript → structured intake parser.

Provider chain: Groq (primary, fast) → Gemini (fallback, multimodal-capable) →
heuristic regex skim. Local ML ensemble still owns the actual triage decision —
this module only converts unstructured caller text into the dispatcher's form
fields.
"""
from __future__ import annotations

import json
import re
import time
from typing import Optional, Tuple

import httpx
from pydantic import ValidationError

from ..config import settings
from ..core.logging import log
from ..schemas.llm import ExtractedEmergency


SYMPTOM_VOCAB = [
    "cardiac_arrest", "unconscious", "severe_burns", "spinal_injury",
    "anaphylaxis", "major_bleeding",
    "stroke_symptoms", "chest_pain", "shortness_of_breath", "seizure",
    "head_trauma", "diabetic_emergency",
    "fracture", "moderate_bleeding", "abdominal_pain", "high_fever",
    "vomiting", "dizziness", "minor_cut", "sprain", "headache",
]


SYSTEM_PROMPT = f"""You are an emergency-dispatch intake assistant.

The user will paste a 911-style caller transcript that may be in English, Hindi,
Marathi, or any mix. Convert it into a single JSON object the dispatch system
can use directly.

Output rules
============
- Output ONLY valid JSON. No prose, no markdown fences.
- Translate any non-English content into English values.
- Do NOT invent vitals. If a number isn't in the transcript, use null.
- Symptoms MUST be drawn from this exact whitelist (use multiple if applicable):
  {", ".join(SYMPTOM_VOCAB)}
- patient_type MUST be one of: cardiac, trauma, stroke, pediatric, burns, general.
- patient_gender MUST be one of: male, female, other (or null).
- severity_hint is your subjective triage on a 1-5 scale (1=Critical, 5=Non-emergency).
  The local ML model still owns the final decision; this is just a hint.
- chief_complaint: one short clinical phrase summarising the call ("65M chest pain 20min").
- location_hint: any free-text place description in the transcript (no coordinates).
- language_detected: best guess at the dominant language ("en", "hi", "mr", "mixed").

JSON schema
===========
{{
  "patient_age": int|null,
  "patient_gender": "male"|"female"|"other"|null,
  "pulse_rate": int|null,
  "blood_pressure_systolic": int|null,
  "blood_pressure_diastolic": int|null,
  "respiratory_rate": int|null,
  "spo2": number|null,
  "gcs_score": int|null,
  "symptoms": [string],
  "chief_complaint": string|null,
  "notes": string|null,
  "location_hint": string|null,
  "patient_type": "cardiac"|"trauma"|"stroke"|"pediatric"|"burns"|"general",
  "severity_hint": int|null,
  "language_detected": string|null
}}
"""


GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)


class LLMExtractor:
    """Provider-agnostic caller-transcript parser."""

    def __init__(self) -> None:
        self._timeout = httpx.Timeout(connect=4.0, read=15.0, write=4.0, pool=4.0)

    # ── capability checks ──────────────────────────────────────────────
    @property
    def has_groq(self) -> bool:
        return bool(settings.groq_api_key)

    @property
    def has_gemini(self) -> bool:
        return bool(settings.gemini_api_key)

    @property
    def enabled(self) -> bool:
        return self.has_groq or self.has_gemini

    # ── public API ─────────────────────────────────────────────────────
    async def extract(
        self, transcript: str, language_hint: Optional[str] = None
    ) -> Tuple[ExtractedEmergency, dict]:
        """Returns (parsed, meta). Never raises — always returns *some* result."""
        meta = {"provider_used": None, "used_fallback": False,
                "latency_ms": None, "error": None}
        if not transcript or not transcript.strip():
            return ExtractedEmergency(), {**meta, "used_fallback": True,
                                          "error": "empty transcript"}

        user_msg = transcript.strip()
        if language_hint:
            user_msg = f"[caller language hint: {language_hint}]\n{user_msg}"

        order = [p.strip() for p in (settings.llm_provider_order or "").split(",")
                 if p.strip()]
        if not order:
            order = ["groq", "gemini"]

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            last_err: Optional[str] = None
            for provider in order:
                if provider == "groq" and self.has_groq:
                    try:
                        t0 = time.perf_counter()
                        raw = await self._call_groq(client, user_msg)
                        parsed = self._parse_to_schema(raw)
                        meta.update({"provider_used": "groq",
                                     "latency_ms": int((time.perf_counter() - t0) * 1000)})
                        return parsed, meta
                    except Exception as exc:  # noqa: BLE001
                        last_err = f"groq: {exc}"
                        log.warning(f"LLM extractor — Groq failed: {exc}")
                        continue
                if provider == "gemini" and self.has_gemini:
                    try:
                        t0 = time.perf_counter()
                        raw = await self._call_gemini(client, user_msg)
                        parsed = self._parse_to_schema(raw)
                        meta.update({"provider_used": "gemini",
                                     "latency_ms": int((time.perf_counter() - t0) * 1000)})
                        return parsed, meta
                    except Exception as exc:  # noqa: BLE001
                        last_err = f"gemini: {exc}"
                        log.warning(f"LLM extractor — Gemini failed: {exc}")
                        continue

        # All providers exhausted (or none configured) → heuristic skim.
        parsed = self._heuristic_extract(transcript)
        meta.update({"provider_used": "heuristic", "used_fallback": True,
                     "error": last_err or "no providers configured"})
        return parsed, meta

    # ── provider implementations ───────────────────────────────────────
    async def _call_groq(self, client: httpx.AsyncClient, transcript: str) -> str:
        body = {
            "model": settings.groq_model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": transcript},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
            "max_tokens": 800,
        }
        headers = {"Authorization": f"Bearer {settings.groq_api_key}",
                   "Content-Type": "application/json"}
        r = await client.post(GROQ_URL, headers=headers, json=body)
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"]

    async def _call_gemini(self, client: httpx.AsyncClient, transcript: str) -> str:
        url = GEMINI_URL.format(model=settings.gemini_model)
        body = {
            "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"role": "user", "parts": [{"text": transcript}]}],
            "generationConfig": {
                "response_mime_type": "application/json",
                "temperature": 0.1,
                "maxOutputTokens": 800,
            },
        }
        params = {"key": settings.gemini_api_key}
        r = await client.post(url, params=params, json=body)
        r.raise_for_status()
        data = r.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]

    # ── parsing & sanitisation ─────────────────────────────────────────
    @staticmethod
    def _parse_to_schema(raw: str) -> ExtractedEmergency:
        obj = json.loads(_strip_codefence(raw))
        # Filter symptoms to whitelist; preserves dispatch_engine's expectations.
        if isinstance(obj.get("symptoms"), list):
            obj["symptoms"] = [s for s in obj["symptoms"] if s in SYMPTOM_VOCAB]
        try:
            return ExtractedEmergency.model_validate(obj)
        except ValidationError as ve:
            # Drop the offending fields and try once more — better partial than nothing.
            bad = {".".join(str(p) for p in e["loc"]) for e in ve.errors()}
            cleaned = {k: v for k, v in obj.items() if k not in bad}
            return ExtractedEmergency.model_validate(cleaned)

    @staticmethod
    def _heuristic_extract(transcript: str) -> ExtractedEmergency:
        """Last-ditch regex skim so the form gets *something* even if all LLMs fail."""
        t = transcript.lower()
        out: dict = {"symptoms": []}

        m = re.search(r"\b(\d{1,3})\s*(?:y|yo|yr|year|years|साल|वर्ष)\b", t)
        if m:
            try:
                age = int(m.group(1))
                if 0 <= age <= 130:
                    out["patient_age"] = age
            except ValueError:
                pass

        if re.search(r"\b(male|man|male|पुरुष|आदमी)\b", t):
            out["patient_gender"] = "male"
        elif re.search(r"\b(female|woman|lady|महिला|औरत)\b", t):
            out["patient_gender"] = "female"

        keyword_to_symptom = {
            "chest pain": "chest_pain", "heart attack": "chest_pain",
            "cardiac": "cardiac_arrest", "unconscious": "unconscious",
            "stroke": "stroke_symptoms", "seizure": "seizure",
            "burn": "severe_burns", "bleeding": "major_bleeding",
            "fracture": "fracture", "broken": "fracture",
            "head injury": "head_trauma", "head trauma": "head_trauma",
            "shortness of breath": "shortness_of_breath", "breathless": "shortness_of_breath",
            "vomit": "vomiting", "dizz": "dizziness",
            "fever": "high_fever", "headache": "headache",
        }
        for kw, sym in keyword_to_symptom.items():
            if kw in t and sym not in out["symptoms"]:
                out["symptoms"].append(sym)

        # Coarse patient_type guess
        sym_set = set(out["symptoms"])
        if {"chest_pain", "cardiac_arrest"} & sym_set:
            out["patient_type"] = "cardiac"
        elif {"stroke_symptoms"} & sym_set:
            out["patient_type"] = "stroke"
        elif {"severe_burns"} & sym_set:
            out["patient_type"] = "burns"
        elif {"head_trauma", "spinal_injury", "fracture", "major_bleeding"} & sym_set:
            out["patient_type"] = "trauma"
        elif out.get("patient_age") is not None and out["patient_age"] < 16:
            out["patient_type"] = "pediatric"

        if out["symptoms"]:
            out["chief_complaint"] = transcript.strip()[:140]

        return ExtractedEmergency(**out)


def _strip_codefence(s: str) -> str:
    """Some models wrap JSON in ```json ... ``` despite instructions — strip it."""
    s = s.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    return s


# ── singleton ────────────────────────────────────────────────────────────
_extractor: Optional[LLMExtractor] = None


def get_llm_extractor() -> LLMExtractor:
    global _extractor
    if _extractor is None:
        _extractor = LLMExtractor()
    return _extractor
