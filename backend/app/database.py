"""SQLAlchemy engine, session factory, and base class."""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings


is_sqlite = settings.database_url.startswith("sqlite")

# SQLite needs `check_same_thread=False` and a longer busy timeout to handle
# concurrent traffic from the simulator (20 ambulances PATCHing) plus the
# frontend's polling.
connect_args = {}
if is_sqlite:
    connect_args = {"check_same_thread": False, "timeout": 30}

# Larger pool for the simulator + frontend + sockets concurrency; the default
# of 5+10 was easy to exhaust during demos.
engine_kwargs = dict(
    echo=False, future=True,
    pool_size=20, max_overflow=40,
    pool_recycle=1800, pool_pre_ping=True,
)

engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    **engine_kwargs,
)


# Enable WAL mode on SQLite so readers don't block writers (and vice versa)
# during the simulator's GPS update storm.
if is_sqlite:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _conn_record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=10000")
        cursor.close()


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
