"""Tenant resolution + scoping helpers.

For Phase 2.8 we keep the existing single-tenant data path intact (every
tenant_id stays NULL on legacy rows) but expose the scaffolding so future
deployments can isolate data per agency / city.

Resolution order at request time:
  1. ``X-Tenant`` header — explicit override (admin tooling, CI).
  2. ``user.tenant_id`` — claim attached to the authenticated user.
  3. ``settings.default_tenant_slug`` — server-wide fallback.
  4. None — legacy single-tenant mode.
"""
from __future__ import annotations

from typing import Optional

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.tenant import Tenant
from ..models.user import User
from ..api.deps import get_current_user


async def resolve_tenant(
    x_tenant: Optional[str] = Header(default=None, alias="X-Tenant"),
    user: Optional[User] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Optional[Tenant]:
    """FastAPI dependency. Returns the active Tenant row or None when
    the system is running in legacy single-tenant mode."""
    if x_tenant:
        t = await db.scalar(
            select(Tenant).where(Tenant.slug == x_tenant.lower(),
                                 Tenant.is_active == True))
        if not t:
            raise HTTPException(404, detail=f"Unknown tenant '{x_tenant}'.")
        # Cross-tenant override is admin-only — anyone else gets a 403.
        if user and user.role != "admin" and user.tenant_id and user.tenant_id != t.id:
            raise HTTPException(403,
                detail="X-Tenant override requires admin role.")
        return t
    if user and user.tenant_id:
        return await db.scalar(
            select(Tenant).where(Tenant.id == user.tenant_id))
    return None


def require_same_tenant(row_tenant_id: Optional[int],
                        user_tenant_id: Optional[int]) -> None:
    """Cross-tenant access guard helper for in-place row checks.

    NULL on either side is treated as 'legacy / default' and is allowed —
    that lets pre-Phase-2.8 data and freshly-tenant-aware users coexist
    until the migration backfill happens.
    """
    if row_tenant_id is None or user_tenant_id is None:
        return
    if row_tenant_id != user_tenant_id:
        raise HTTPException(403,
            detail="Resource belongs to a different tenant.")
