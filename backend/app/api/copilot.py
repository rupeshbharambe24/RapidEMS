"""Dispatcher copilot endpoint."""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..core.ratelimit import limiter
from ..database import get_db
from ..models.user import User
from ..services.copilot import ask
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
