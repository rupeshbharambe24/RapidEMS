"""Auth endpoints: /login, /register, /me. Async."""
import pyotp
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..core.ratelimit import limiter
from ..core.security import create_access_token
from ..database import get_db
from ..models.user import User
from ..schemas.user import LoginRequest, TokenOut, UserCreate, UserOut
from ..services import auth_service
from .deps import require_user

router = APIRouter(prefix="/auth", tags=["auth"])


class TotpSetupOut(BaseModel):
    secret: str
    provisioning_uri: str = Field(...,
        description="otpauth:// URI — render as QR for any TOTP app.")


class TotpVerifyIn(BaseModel):
    code: str = Field(..., pattern="^[0-9]{6}$")


@router.post("/login", response_model=TokenOut)
@limiter.limit("10/minute")    # bruteforce guard
async def login(request: Request, payload: LoginRequest,
                db: AsyncSession = Depends(get_db)):
    user = await auth_service.authenticate(db, payload.username, payload.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid username or password.")
    # 2FA gate — once a user enables TOTP, login requires the 6-digit code.
    if user.totp_enabled:
        if not payload.totp_code:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="TOTP code required.")
        totp = pyotp.TOTP(user.totp_secret or "")
        if not totp.verify(payload.totp_code, valid_window=1):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid TOTP code.")
    token = create_access_token(subject=user.username, role=user.role)
    return TokenOut(
        access_token=token,
        expires_in=settings.access_token_expire_minutes * 60,
        user=UserOut.model_validate(user),
    )


@router.post("/2fa/setup", response_model=TotpSetupOut)
async def totp_setup(
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Generates a fresh secret + provisioning URI. The secret persists
    immediately so a refresh doesn't lose it, but ``totp_enabled`` stays
    false until /2fa/verify confirms the user actually scanned the QR
    and produced a valid code. Re-running this rotates the secret."""
    secret = pyotp.random_base32()
    user.totp_secret = secret
    user.totp_enabled = False
    await db.commit()
    uri = pyotp.TOTP(secret).provisioning_uri(
        name=user.username, issuer_name="RapidEMS")
    return TotpSetupOut(secret=secret, provisioning_uri=uri)


@router.post("/2fa/verify", status_code=204)
async def totp_verify(
    payload: TotpVerifyIn,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Enables TOTP for the user once a fresh code matches the stored
    secret. valid_window=1 forgives a 30s clock skew either side."""
    if not user.totp_secret:
        raise HTTPException(409, detail="No TOTP secret — call /auth/2fa/setup first.")
    totp = pyotp.TOTP(user.totp_secret)
    if not totp.verify(payload.code, valid_window=1):
        raise HTTPException(401, detail="Code did not match.")
    user.totp_enabled = True
    await db.commit()


@router.post("/2fa/disable", status_code=204)
async def totp_disable(
    payload: TotpVerifyIn,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Disables TOTP. Same fresh-code requirement so a stolen session
    token alone can't switch it off."""
    if not user.totp_enabled or not user.totp_secret:
        raise HTTPException(409, detail="TOTP is not enabled.")
    totp = pyotp.TOTP(user.totp_secret)
    if not totp.verify(payload.code, valid_window=1):
        raise HTTPException(401, detail="Code did not match.")
    user.totp_enabled = False
    user.totp_secret = None
    await db.commit()


@router.post("/register", response_model=UserOut, status_code=201)
@limiter.limit("5/minute")    # per-IP cap so the open registration surface
                              # can't be carpet-bombed
async def register(request: Request, payload: UserCreate,
                   db: AsyncSession = Depends(get_db)):
    if await auth_service.get_user_by_username(db, payload.username):
        raise HTTPException(status_code=400, detail="Username already exists.")
    user = await auth_service.create_user(db, **payload.model_dump())
    return UserOut.model_validate(user)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(require_user)):
    return UserOut.model_validate(user)
