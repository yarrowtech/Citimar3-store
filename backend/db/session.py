"""MongoDB database handles.

get_db() is the FastAPI Depends() entry point (`db: Database = Depends(get_db)`),
mirroring api/deps.py's existing get_dataset(request) dependency pattern.
session_scope() is the equivalent for code with no per-request lifecycle --
src/daily_midnight_job.py's background asyncio task, one-off scripts under
scripts/.

Unlike the Postgres/SQLAlchemy version this replaced, MongoDB writes commit
per-document immediately -- there's no unit-of-work to commit or roll back,
so both functions below are just thin wrappers around db/engine.py's
get_database() that make sure indexes exist (ensure_indexes() is idempotent,
so calling it on every handout is cheap and always safe -- it replaces what
`alembic upgrade head` used to provision).

TEMPORARY: if MONGODB_URI isn't set at all, _get_ready_database() falls back
to db/xlsx_fallback.py's XlsxDatabase (reads/writes TEST_DAILY_DASHBOARD.xlsx
directly) instead of get_database() raising -- lets Daily Operations be
tested locally without a MongoDB account. See xlsx_fallback.py's module
docstring for exactly what it does and doesn't support. The moment a real
MONGODB_URI is configured, get_database() stops raising and this fallback
stops triggering automatically -- no code change needed anywhere to switch
back. The fallback only engages when its workbook actually exists on disk;
with neither MONGODB_URI nor the workbook (a real deployment that forgot to
set MONGODB_URI), _get_ready_database() raises a clear RuntimeError rather
than letting openpyxl throw a cryptic FileNotFoundError on the first login.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from pymongo.database import Database

from config.settings import DAILY_DASHBOARD_XLSX_PATH
from db.engine import get_database
from db.models import ensure_indexes
from db.xlsx_fallback import XlsxDatabase

_indexes_ready = False


def _get_ready_database() -> "Database | XlsxDatabase":
    global _indexes_ready
    try:
        db = get_database()
    except RuntimeError:
        # MONGODB_URI isn't set. The xlsx fallback is local-dev scaffolding and
        # only works if its workbook already exists on disk -- on a real
        # deployment it doesn't, and letting the fallback engage
        # there just turns a config mistake into a confusing FileNotFoundError
        # deep inside openpyxl on the first login. Fail loudly and clearly
        # instead: the fix is to set MONGODB_URI (see .env.example).
        if not DAILY_DASHBOARD_XLSX_PATH.exists():
            raise RuntimeError(
                "MONGODB_URI is not configured. Login and Daily Operations both "
                "require MongoDB -- set MONGODB_URI in the environment (local: "
                "a .env file; hosted: the platform's environment settings). See "
                ".env.example. (The local TEST_DAILY_DASHBOARD.xlsx fallback is "
                "not present, so there is nothing to fall back to.)"
            ) from None
        db = XlsxDatabase()
    if not _indexes_ready:
        ensure_indexes(db)
        _indexes_ready = True
    return db


def get_db() -> "Iterator[Database | XlsxDatabase]":
    yield _get_ready_database()


@contextmanager
def session_scope() -> "Iterator[Database | XlsxDatabase]":
    yield _get_ready_database()


def reset_session_factory_for_tests() -> None:
    """Test-only: pairs with db.engine.reset_engine_for_tests() -- this
    module also caches whether ensure_indexes() has already run, so a test
    that points get_client() at a different MongoDB (e.g. a fresh mongomock
    instance) must reset this flag too, or the new instance would never get
    its indexes created."""
    global _indexes_ready
    _indexes_ready = False
