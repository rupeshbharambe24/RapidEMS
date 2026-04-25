"""Authentication service — login, user lookup."""
from typing import Optional

from sqlalchemy.orm import Session

from ..core.security import hash_password, verify_password
from ..models.user import User, UserRole


def get_user_by_username(db: Session, username: str) -> Optional[User]:
    return db.query(User).filter(User.username == username).first()


def authenticate(db: Session, username: str, password: str) -> Optional[User]:
    user = get_user_by_username(db, username)
    if not user or not user.is_active:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


def create_user(
    db: Session,
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
    db.commit()
    db.refresh(user)
    return user
