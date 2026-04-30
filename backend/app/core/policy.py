"""Centralised RBAC + ABAC policy via casbin.

Two surfaces:

  enforce(role, obj, act)   pure-Python check; returns bool. Cheap to call
                            from anywhere (audit checks, copilot tool gating,
                            etc.). Public role used for unauthenticated
                            visitors so the same matcher can express public
                            read access alongside role-scoped writes.

  require_policy(obj, act)  FastAPI dependency factory; injects the current
                            user (or 'public' role for unauthenticated
                            requests), runs the enforcer, raises 403 on
                            denial. Use alongside or instead of the
                            existing require_role helpers.

The policy lives in core/policy.csv; reload at runtime via
``reload_policy()`` (admin endpoint).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import casbin
from fastapi import Depends, HTTPException, status

from ..models.user import User
from ..api.deps import get_current_user


_BASE = Path(__file__).resolve().parent
_MODEL = str(_BASE / "policy_model.conf")
_POLICY = str(_BASE / "policy.csv")

_enforcer: Optional[casbin.Enforcer] = None


def get_enforcer() -> casbin.Enforcer:
    global _enforcer
    if _enforcer is None:
        _enforcer = casbin.Enforcer(_MODEL, _POLICY)
    return _enforcer


def reload_policy() -> None:
    """Re-read the CSV from disk so admin edits take effect without a
    backend restart."""
    get_enforcer().load_policy()


def enforce(role: str, obj: str, act: str) -> bool:
    return bool(get_enforcer().enforce(role or "public", obj, act))


def require_policy(obj: str, act: str):
    """Dependency factory.

    Use as ``user: User = Depends(require_policy('emergency', 'write'))``
    on routes you want gated by the central rule set. Anonymous callers
    are checked against the 'public' role.
    """
    async def _check(user: Optional[User] = Depends(get_current_user)) -> Optional[User]:
        role = user.role if user else "public"
        if not enforce(role, obj, act):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{role}' is not allowed to '{act}' on '{obj}'.",
            )
        return user
    return _check


def list_policy() -> list[list[str]]:
    """All persistent policy lines, primarily for admin UIs."""
    return get_enforcer().get_policy()
