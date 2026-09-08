"""Shared pytest fixtures.

db_session provides a pymongo-compatible Database backed by mongomock (an
in-memory fake MongoDB), for tests that exercise src/daily_dashboard_store.py
(db/models.py's BILLS/FOOTFALL/NOB/TARGETS collections). This is the Mongo
equivalent of the project's existing "in-memory, no real DB needed" testing
philosophy -- it covers the module's query/mutation logic correctly, but
mongomock doesn't enforce every real-MongoDB behavior (e.g. some aggregation
edge cases), so it isn't a substitute for testing against a real MongoDB
instance before deploying. Indexes are created directly via
db.models.ensure_indexes(), not through any migration step -- MongoDB is
schemaless, so there's no Alembic-equivalent to run first.

The `client` fixture builds a FastAPI TestClient for the HTTP-level auth/RBAC
tests. It deliberately does NOT enter the app's lifespan (which would read the
real DATASET.xlsx and start the midnight job); instead it sets a tiny synthetic
dataset on app.state and overrides get_db with the mongomock db_session.
"""
from __future__ import annotations

import time as _time
from datetime import datetime
from types import SimpleNamespace

import jwt
import mongomock
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from db.models import ensure_indexes
from src import user_store
from src.user_store import resolved_seed_passwords, seed_users

TEST_JWT_SECRET = "test-secret"

# PBKDF2 at production strength (600k iterations) x four accounts per db_session
# fixture dominates the suite runtime; the hashing behaviour under test is
# iteration-count-independent.
user_store._ITERATIONS = 1000


@pytest.fixture()
def db_session():
    client = mongomock.MongoClient()
    db = client["citimart"]
    ensure_indexes(db)
    # The four fixed accounts, so POST /api/auth/login works against this
    # in-memory DB exactly as it would against a real one.
    seed_users(db, resolved_seed_passwords())
    yield db


def _synthetic_dataset() -> SimpleNamespace:
    """Minimal MasterDataset stand-in: enough columns for parse_filter_state,
    apply_filters, filter_store_level_table and compute_kpis to run."""
    dates = pd.to_datetime(["2026-08-20", "2026-08-21"])
    rows = []
    for store in ("NM", "HB", "CHW"):
        for d in dates:
            rows.append({
                "store_code": store,
                "date": d,
                "bill_no": f"{store}-{d.day}",
                "net_amount": 1000.0,
                "gross_amount": 1200.0,
                "discount_amount": 200.0,
                "bill_quantity": 3.0,
                "cogs_with_gst": 700.0,
            })
    fact = pd.DataFrame(rows)

    footfall = pd.DataFrame([
        {"store_code": s, "date": d, "time_slot": "11.00 AM - 01.59 PM", "footfall": 50.0, "nob": 20.0}
        for s in ("NM", "HB", "CHW") for d in dates
    ])
    target = pd.DataFrame([
        {"store_code": s, "date": d, "target": 5000.0}
        for s in ("NM", "HB", "CHW") for d in dates
    ])
    return SimpleNamespace(
        fact=fact, footfall=footfall, target=target,
        profile=None, schema_maps={}, loaded_sheets=[], skipped_sheets=[],
        source_mtime=0.0, cleaning_stats={},
    )


def make_token(role: str, store_code: str | None, username: str, *, secret: str = TEST_JWT_SECRET, ttl: int = 3600) -> str:
    now = int(_time.time())
    return jwt.encode(
        {
            "sub": f"test-{username}",
            "iat": now,
            "exp": now + ttl,
            "username": username,
            "role": role,
            "store_code": store_code,
        },
        secret,
        algorithm="HS256",
    )


@pytest.fixture()
def client(db_session, monkeypatch):
    monkeypatch.setattr("config.env.env.jwt_secret", TEST_JWT_SECRET, raising=False)

    import app as app_module
    from db.session import get_db

    app_module.app.state.dataset = _synthetic_dataset()
    app_module.app.state.loaded_at = datetime.now()
    app_module.app.dependency_overrides[get_db] = lambda: db_session

    test_client = TestClient(app_module.app)  # no `with` -> lifespan not run
    try:
        yield test_client
    finally:
        app_module.app.dependency_overrides.clear()


@pytest.fixture()
def admin_headers():
    return {"Authorization": f"Bearer {make_token('admin', None, 'ADMINISTRATOR')}"}


@pytest.fixture()
def nw_headers():
    return {"Authorization": f"Bearer {make_token('manager', 'NM', 'CITIMART - NEW MARKET')}"}


@pytest.fixture()
def hb_headers():
    return {"Authorization": f"Bearer {make_token('manager', 'HB', 'CITIMART - HATIBAGAN')}"}
