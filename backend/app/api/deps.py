"""Shared FastAPI dependencies — DB session, current user, role guards. Async."""
from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.security import decode_token
from ..database import get_db
from ..models.user import User


async def get_current_user(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """Decode JWT from `Authorization: Bearer <token>` header.

    Returns None if no header is provided — endpoints decide whether to
    require a user.
    """
    if not authorization:
        return None
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    payload = decode_token(parts[1])
    if not payload:
        return None
    return await db.scalar(select(User).where(User.username == payload.get("sub")))


def require_user(user: Optional[User] = Depends(get_current_user)) -> User:
    """Use as a dependency on endpoints that *must* have a logged-in user."""
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Authentication required.")
    return user


def require_role(*roles: str):
    """Factory for role-based guards: `Depends(require_role('admin'))`."""
    def checker(user: User = Depends(require_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail=f"Requires role: {','.join(roles)}")
        return user
    return checker
