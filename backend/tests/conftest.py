"""Pytest bootstrap shared across every backend test module.

Lives at session scope so the seeded test database is built once per
``pytest`` invocation regardless of which subset of test files is
collected. Lets ``pytest tests/test_phase3.py`` (without test_api) work
the same as a full run.
"""
import asyncio
import os
import sys
from pathlib import Path

# Test env must be set BEFORE app modules are imported, since database.py
# reads DATABASE_URL at import time.
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SEED_ON_STARTUP", "true")

# Ensure the backend package directory (one above tests/) is importable
# even when pytest is invoked from elsewhere.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest


@pytest.fixture(scope="session", autouse=True)
def _bootstrap_test_db():
    """Wipe + recreate + seed the SQLite test DB once per session."""
    test_db = Path("./test.db")
    if test_db.exists():
        test_db.unlink()

    # Imports are deferred to here so the env vars above are honoured.
    from app.database import AsyncSessionLocal, create_all_tables, engine
    from app.seed import seed_database

    async def _setup():
        await create_all_tables()
        async with AsyncSessionLocal() as db:
            await seed_database(db, force=True)

    asyncio.run(_setup())
    yield

    # Dispose of the connection pool before unlinking — on Windows
    # SQLite holds the file lock until the last connection closes.
    async def _teardown():
        await engine.dispose()
    try:
        asyncio.run(_teardown())
    except Exception:
        pass
    # Best-effort delete; tolerate Windows file-lock races (shm/wal stay
    # open inside other test runners) without failing the suite.
    for p in (test_db, Path("./test.db-wal"), Path("./test.db-shm")):
        try:
            if p.exists():
                p.unlink()
        except OSError:
            pass
