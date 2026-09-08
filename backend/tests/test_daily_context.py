from datetime import date

import pandas as pd

from src import daily_context


def test_day_type_buckets_the_week_three_ways():
    assert daily_context.day_type(date(2026, 9, 5)) == "Weekend"   # Saturday
    assert daily_context.day_type(date(2026, 9, 6)) == "Weekend"   # Sunday
    assert daily_context.day_type(date(2026, 9, 2)) == "Mid-Week"  # Wednesday
    assert daily_context.day_type(date(2026, 9, 3)) == "Mid-Week"  # Thursday
    assert daily_context.day_type(date(2026, 9, 1)) == "Regular"   # Tuesday
    assert daily_context.day_type(date(2026, 9, 4)) == "Regular"   # Friday


def test_previous_year_same_day_returns_none_without_prior_year_rows():
    empty = pd.DataFrame(columns=["date", "store_code", "net_amount"])
    assert daily_context.previous_year_same_day(date(2026, 9, 1), {}, empty, empty, empty) is None


def test_previous_year_same_day_builds_matrix_and_variance():
    prev_day = pd.Timestamp("2025-09-01")
    fact = pd.DataFrame([
        {"date": prev_day, "store_code": "NM", "net_amount": 800.0, "bill_quantity": 4.0},
    ])
    footfall = pd.DataFrame([
        {"date": prev_day, "store_code": "NM", "footfall": 40.0, "nob": 10.0},
    ])
    target = pd.DataFrame([{"date": prev_day, "store_code": "NM", "target": 1000.0}])

    result = daily_context.previous_year_same_day(
        date(2026, 9, 1), {"net_sales": 1000.0}, fact, footfall, target
    )
    assert result["date"] == "2025-09-01"
    net_row = next(r for r in result["rows"] if r["kpi"] == "net_sales")
    assert net_row["previous"] == 800.0
    assert net_row["current"] == 1000.0
    assert net_row["variance_pct"] == 25.0  # (1000 - 800) / 800 * 100
    # A KPI absent from current_kpis still reports last year's figure.
    footfall_row = next(r for r in result["rows"] if r["kpi"] == "footfall")
    assert footfall_row["previous"] == 40.0
    assert footfall_row["current"] is None
    assert footfall_row["variance_pct"] is None


def test_get_holiday_name_recognises_west_bengal_holiday():
    # Pohela Boishakh (Bengali New Year) is a West Bengal regional holiday,
    # not a national one -- confirms the subdiv="WB" calendar is active,
    # not just the generic national "IN" calendar.
    assert daily_context.get_holiday_name(date(2026, 4, 15)) == "Pohela Boishakh"


def test_get_holiday_name_returns_none_for_ordinary_day():
    assert daily_context.get_holiday_name(date(2026, 2, 10)) is None


def test_get_election_info_flags_declared_poll_and_counting_days():
    assert "Lok Sabha" in daily_context.get_election_info(date(2024, 5, 13))
    assert "counting" in daily_context.get_election_info(date(2024, 6, 4))
    assert "WB Assembly" in daily_context.get_election_info(date(2021, 3, 27))


def test_get_election_info_returns_none_for_ordinary_day():
    assert daily_context.get_election_info(date(2026, 2, 10)) is None
