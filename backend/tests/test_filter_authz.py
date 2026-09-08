"""parse_filter_state / parse_forecast_state clamp `stores` to the caller's
allowed set. Managers are also blocked from the admin-only charts... except the
shared `charts` router, where the clamp is the guard."""
from __future__ import annotations


def test_admin_charts_daily_gauge_allowed(client, admin_headers):
    r = client.get(
        "/api/charts/daily_achievement_gauge",
        params={"stores": "NM", "start": "2026-08-20", "end": "2026-08-20"},
        headers=admin_headers,
    )
    assert r.status_code == 200


def test_manager_daily_gauge_own_store_allowed(client, nw_headers):
    r = client.get(
        "/api/charts/daily_achievement_gauge",
        params={"stores": "NM", "start": "2026-08-20", "end": "2026-08-20"},
        headers=nw_headers,
    )
    assert r.status_code == 200


def test_admin_daily_gauge_overall_all_stores(client, admin_headers):
    # The "Overall Stores Summary" page passes every store -> blended gauge.
    r = client.get(
        "/api/charts/daily_achievement_gauge",
        params={"stores": "NM,HB,CHW", "start": "2026-08-20", "end": "2026-08-20"},
        headers=admin_headers,
    )
    assert r.status_code == 200


def test_manager_daily_gauge_other_store_forbidden(client, nw_headers):
    r = client.get(
        "/api/charts/daily_achievement_gauge",
        params={"stores": "HB", "start": "2026-08-20", "end": "2026-08-20"},
        headers=nw_headers,
    )
    assert r.status_code == 403


def test_manager_kpis_scoped_selection_forbidden(client, nw_headers):
    # kpis router is admin-only anyway, but assert the 403
    assert client.get("/api/kpis", params={"stores": "HB"}, headers=nw_headers).status_code == 403


def test_admin_kpis_multi_store_ok(client, admin_headers):
    assert client.get("/api/kpis", params={"stores": "NM,HB"}, headers=admin_headers).status_code == 200


def test_charts_require_auth(client):
    assert client.get("/api/charts/monthly_sales").status_code == 401
