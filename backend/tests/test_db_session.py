"""db/session.py's fallback guard -- the xlsx fallback must not silently
engage on a deployment that simply forgot to set MONGODB_URI."""
from __future__ import annotations

from pathlib import Path

import pytest

import db.engine
import db.session


@pytest.fixture()
def no_mongo(monkeypatch):
    """No MONGODB_URI and no cached client -- get_database() will raise, the
    same state a fresh Render deploy is in before its env vars are filled."""
    monkeypatch.setattr(db.engine, "_client", None)
    monkeypatch.setattr("config.env.env.mongodb_uri", None, raising=False)
    db.session.reset_session_factory_for_tests()
    yield
    db.engine.reset_engine_for_tests()
    db.session.reset_session_factory_for_tests()


def test_missing_mongo_and_missing_workbook_raises_clear_error(no_mongo, monkeypatch, tmp_path):
    monkeypatch.setattr(db.session, "DAILY_DASHBOARD_XLSX_PATH", tmp_path / "nope.xlsx")
    with pytest.raises(RuntimeError, match="MONGODB_URI is not configured"):
        db.session._get_ready_database()


def test_missing_mongo_but_workbook_present_falls_back(no_mongo, monkeypatch, tmp_path):
    present = tmp_path / "TEST_DAILY_DASHBOARD.xlsx"
    present.write_bytes(b"")  # existence is all the guard checks
    monkeypatch.setattr(db.session, "DAILY_DASHBOARD_XLSX_PATH", present)
    monkeypatch.setattr(db.session, "ensure_indexes", lambda _db: None)
    from db.xlsx_fallback import XlsxDatabase

    assert isinstance(db.session._get_ready_database(), XlsxDatabase)
