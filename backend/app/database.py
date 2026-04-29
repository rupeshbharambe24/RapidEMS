"""Async SQLAlchemy engine, session factory, and base class.

The dev path uses ``sqlite+aiosqlite``; the prod path uses ``postgresql+asyncpg``.
``settings.database_url`` is auto-translated, so existing ``.env`` files
written against the sync drivers (``sqlite:///`` / ``postgresql+psycopg2://``)
keep working.
"""
import asyncio

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (AsyncSession, async_sessionmaker,
                                    create_async_engine)
from sqlalchemy.orm import DeclarativeBase

from .config import settings


def _to_async_url(url: str) -> str:
    """Map sync DSNs to their async equivalents so .env doesn't have to know."""
    if url.startswith("sqlite:///"):
        return url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
    if url.startswith("postgresql+psycopg2://"):
        return url.replace("postgresql+psycopg2://",
                           "postgresql+asyncpg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


DATABASE_URL = _to_async_url(settings.database_url)
IS_SQLITE = "sqlite" in DATABASE_URL


# Async SQLite (aiosqlite) doesn't take ``pool_size`` / ``max_overflow``;
# its underlying QueuePool is replaced with a single-connection model. The
# WAL pragmas below give us reader/writer concurrency anyway.
connect_args: dict = {"timeout": 30} if IS_SQLITE else {}

engine_kwargs: dict = dict(echo=False, pool_pre_ping=True, pool_recycle=1800)
if not IS_SQLITE:
    engine_kwargs.update(pool_size=20, max_overflow=40)

engine = create_async_engine(DATABASE_URL, connect_args=connect_args,
                             **engine_kwargs)


if IS_SQLITE:
    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _conn_record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=10000")
        cursor.close()


AsyncSessionLocal = async_sessionmaker(
    engine, expire_on_commit=False, class_=AsyncSession,
)


class Base(DeclarativeBase):
    """Common SQLAlchemy declarative base."""
    pass


async def get_db():
    """FastAPI dependency yielding an AsyncSession scoped to one request."""
    async with AsyncSessionLocal() as session:
        yield session


async def create_all_tables():
    """Create every table defined on Base.metadata. Idempotent.

    Will be replaced by ``alembic upgrade head`` in Phase 0.3.
    """
    # Importing the model modules registers them with Base.metadata.
    from .models import (  # noqa: F401
        ambulance, audit_log, dispatch, emergency, family_link, hospital,
        hospital_alert, medical_record, patient_profile, traffic_snapshot,
        user,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def _apply_alembic_upgrade() -> None:
    """Run ``alembic upgrade head`` against the configured DSN.

    Synchronous because Alembic drives its own asyncio loop in env.py; we
    invoke it from a worker thread (via ``asyncio.to_thread``) so the
    launcher's loop isn't reused.
    """
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    backend_dir = Path(__file__).resolve().parent.parent
    cfg = Config(str(backend_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_dir / "migrations"))
    command.upgrade(cfg, "head")


async def init_and_seed() -> None:
    """One-call helper for the launcher: migrate to head, then seed.

    Lives here so ``run.py`` can drive it via a single-line
    ``python -c "import asyncio; from app.database import init_and_seed;
    asyncio.run(init_and_seed())"`` (which avoids ``python -c`` not
    accepting multi-line ``async def`` bodies).
    """
    from .seed import seed_database

    # Alembic env.py runs its own asyncio.run() — keep it off our loop.
    await asyncio.to_thread(_apply_alembic_upgrade)

    async with AsyncSessionLocal() as db:
        await seed_database(db)
