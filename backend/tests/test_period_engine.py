import pandas as pd
import pytest

from src import period_engine as pe


def test_periods_constant():
    assert pe.PERIODS == ("day", "week", "month", "quarter", "year")


def test_period_start_anchors():
    dates = pd.Series(pd.to_datetime(["2026-08-29", "2026-08-31", "2026-02-14"]))  # Sat, Mon, Sat
    assert list(pe.period_start(dates, "day")) == list(pd.to_datetime(["2026-08-29", "2026-08-31", "2026-02-14"]))
    # week -> Monday of that week
    assert list(pe.period_start(dates, "week")) == list(pd.to_datetime(["2026-08-24", "2026-08-31", "2026-02-09"]))
    assert list(pe.period_start(dates, "month")) == list(pd.to_datetime(["2026-08-01", "2026-08-01", "2026-02-01"]))
    assert list(pe.period_start(dates, "quarter")) == list(pd.to_datetime(["2026-07-01", "2026-07-01", "2026-01-01"]))
    assert list(pe.period_start(dates, "year")) == list(pd.to_datetime(["2026-01-01", "2026-01-01", "2026-01-01"]))


def test_period_start_is_nat_safe():
    dates = pd.Series(pd.to_datetime(["2026-08-29", None, "not-a-date"], errors="coerce"))
    for period in pe.PERIODS:
        out = pe.period_start(dates, period)
        assert out.isna().sum() == 2
        assert len(out) == 3


def test_period_label_per_period():
    ts = pd.Timestamp("2026-08-24")
    assert pe.period_label(ts, "day") == "24 Aug 2026"
    assert pe.period_label(ts, "week") == "Wk of 24 Aug 2026"
    assert pe.period_label(ts, "month") == "Aug 2026"
    assert pe.period_label(pd.Timestamp("2026-07-01"), "quarter") == "Q3 2026"
    assert pe.period_label(pd.Timestamp("2026-01-01"), "year") == "2026"
    assert pe.period_label(pd.NaT, "day") == "Unknown"


def test_period_label_vectorised():
    starts = pd.Series(pd.to_datetime(["2026-01-01", "2026-04-01"]))
    assert list(pe.period_label(starts, "quarter")) == ["Q1 2026", "Q2 2026"]


def test_resample_frame_buckets_and_sorts():
    df = pd.DataFrame({
        "date": pd.to_datetime(["2026-08-01", "2026-08-15", "2026-09-02", "2026-08-20"]),
        "net_amount": [100.0, 50.0, 200.0, 25.0],
    })
    out = pe.resample_frame(df, "month", net_sales=("net_amount", "sum"))
    assert list(out.columns) == ["Date", "period_start", "net_sales"]
    assert list(out["Date"]) == ["Aug 2026", "Sep 2026"]
    assert list(out["net_sales"]) == [175.0, 200.0]


def test_resample_frame_drops_nat_bucket():
    df = pd.DataFrame({
        "date": pd.to_datetime(["2026-08-01", None], errors="coerce"),
        "net_amount": [100.0, 999.0],
    })
    out = pe.resample_frame(df, "month", net_sales=("net_amount", "sum"))
    assert len(out) == 1
    assert out.iloc[0]["net_sales"] == 100.0


def test_resample_frame_empty_input_keeps_shape():
    out = pe.resample_frame(pd.DataFrame(), "week", net_sales=("net_amount", "sum"))
    assert out.empty
    assert list(out.columns) == ["Date", "period_start", "net_sales"]


def test_resample_frame_works_on_footfall_style_frame():
    # No derived calendar columns -- only a bare `date`.
    df = pd.DataFrame({
        "date": pd.to_datetime(["2026-08-03", "2026-08-04", "2026-08-11"]),  # wk of 03 Aug x2, wk of 10 Aug
        "footfall": [10.0, 20.0, 5.0],
    })
    out = pe.resample_frame(df, "week", footfall=("footfall", "sum"))
    assert list(out["Date"]) == ["Wk of 03 Aug 2026", "Wk of 10 Aug 2026"]
    assert list(out["footfall"]) == [30.0, 5.0]


def test_seasonal_key_cyclic_buckets():
    dates = pd.Series(pd.to_datetime(["2026-08-31", "2026-09-07", "2026-12-25"]))  # Mon, Mon, Fri
    keys, order = pe.seasonal_key(dates, "day")
    assert list(keys) == ["Mon", "Mon", "Fri"]
    assert order == ["Mon", "Tues", "Weds", "Thurs", "Fri", "Sat", "Sun"]

    keys, order = pe.seasonal_key(dates, "month")
    assert list(keys) == ["August", "September", "December"]
    assert order[0] == "January" and len(order) == 12

    keys, order = pe.seasonal_key(dates, "quarter")
    assert list(keys) == ["Q3", "Q3", "Q4"]
    assert order == ["Q1", "Q2", "Q3", "Q4"]


def test_invalid_period_raises():
    with pytest.raises(ValueError):
        pe.period_start(pd.Series(pd.to_datetime(["2026-08-01"])), "fortnight")
