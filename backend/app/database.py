"""SQLAlchemy engine, session factory, and base class."""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings


# SQLite needs `check_same_thread=False` to be used across FastAPI threads.
connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    echo=False,
    future=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Common SQLAlchemy declarative base."""
    pass


def get_db():
    """FastAPI dependency that yields a DB session and closes it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_all_tables():
    """Create every table defined on Base.metadata. Idempotent."""
    # Import models here so SQLAlchemy registers them with Base.metadata
    # before we try to create tables.
    from .models import (  # noqa: F401
        ambulance, audit_log, dispatch, emergency, hospital,
        traffic_snapshot, user,
    )
    Base.metadata.create_all(bind=engine)
