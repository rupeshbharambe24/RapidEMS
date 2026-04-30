"""JWT + password hashing utilities."""
from datetime import datetime, timedelta
from typing import Any, Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from ..config import settings


# Argon2id is the new default; bcrypt stays in the schemes list so existing
# users from before Phase 2.2 keep verifying. Passlib's needs_update() will
# tag bcrypt hashes as deprecated, so on the next successful login they're
# auto-rehashed under Argon2id. New users always get Argon2id directly.
pwd_context = CryptContext(
    schemes=["argon2", "bcrypt"],
    deprecated="auto",
    argon2__type="ID",
    argon2__time_cost=3,
    argon2__memory_cost=64 * 1024,    # 64 MB
    argon2__parallelism=2,
)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(plain, hashed)
    except Exception:
        return False


def verify_and_maybe_rehash(plain: str, hashed: str) -> tuple[bool, Optional[str]]:
    """Returns (matched, new_hash_or_None). When ``new_hash`` is non-None
    the caller should persist it — it's an Argon2id rehash of a legacy
    bcrypt password that was just successfully verified."""
    try:
        ok = pwd_context.verify(plain, hashed)
    except Exception:
        return False, None
    if not ok:
        return False, None
    if pwd_context.needs_update(hashed):
        return True, pwd_context.hash(plain)
    return True, None


def create_access_token(subject: str, role: str,
                        expires_minutes: Optional[int] = None) -> str:
    expire_min = expires_minutes or settings.access_token_expire_minutes
    expire = datetime.utcnow() + timedelta(minutes=expire_min)
    payload: dict[str, Any] = {"sub": subject, "role": role, "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError:
        return None
