"""Authentication service — login, user lookup. Async."""
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.security import hash_password, verify_and_maybe_rehash
from ..models.user import User, UserRole


async def get_user_by_username(db: AsyncSession, username: str) -> Optional[User]:
    return await db.scalar(select(User).where(User.username == username))


async def authenticate(db: AsyncSession, username: str,
                       password: str) -> Optional[User]:
    user = await get_user_by_username(db, username)
    if not user or not user.is_active:
        return None
    ok, new_hash = verify_and_maybe_rehash(password, user.hashed_password)
    if not ok:
        return None
    if new_hash:
        # Silent rehash from bcrypt → Argon2id on the next successful login.
        user.hashed_password = new_hash
        await db.commit()
    return user


async def create_user(
    db: AsyncSession,
    *,
    username: str,
    email: str,
    password: str,
    full_name: Optional[str] = None,
    role: str = UserRole.DISPATCHER.value,
) -> User:
    user = User(
        username=username,
        email=email,
        full_name=full_name,
        hashed_password=hash_password(password),
        role=role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user
