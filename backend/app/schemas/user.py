"""Pydantic schemas for users and auth."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserBase(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: EmailStr
    full_name: Optional[str] = None
    role: str = "dispatcher"


class UserCreate(UserBase):
    password: str = Field(min_length=6, max_length=128)


class UserOut(UserBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    is_active: bool
    created_at: datetime


class LoginRequest(BaseModel):
    username: str
    password: str
    totp_code: Optional[str] = Field(default=None, pattern="^[0-9]{6}$",
                                     description="6-digit TOTP code, "
                                                 "required if 2FA is enabled.")


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut
