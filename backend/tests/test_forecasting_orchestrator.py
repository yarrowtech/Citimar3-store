import numpy as np
import pandas as pd
import pytest

from src.forecasting.orchestrator import (
    forecast_daily_sales,
    forecast_footfall_nob,
    forecast_products,
    forecast_vendors,
    growth_trajectory_needed,
)


def _fact(n=90, start="2026-01-01", stores=("NM", "HB")) -> pd.DataFrame:
    dates = pd.date_range(start, periods=n, freq="D")
    rows = []
    styles = ["Style-A", "Style-B", "Style-C"]
    vendors = ["Vendor-1", "Vendor-2", "Vendor-3"]
    for i, d in enumerate(dates):
        for j, store in enumerate(stores):
            rows.append(
                {
                    "date": d,
                    "store_code": store,
                    "net_amount": 100.0 + i * 0.5 + 10 * np.sin(2 * np.pi * i / 7) + j * 20,
                    "product_style": styles[i % len(styles)],
                    "vendors": vendors[i % len(vendors)],
                    "promo_type": "P" if i % 5 == 0 else None,
                    "discount_amount": 5.0 if i % 5 == 0 else 0.0,
                    "gross_amount": 105.0,
                }
            )
    return pd.DataFrame(rows)


def _footfall(n=90, start="2026-01-01", stores=("NM",)) -> pd.DataFrame:
    dates = pd.date_range(start, periods=n, freq="D")
    slots = ["11.00 AM - 01.59 PM", "02.00 PM - 04.59 PM", "05.00 PM - 07.59 PM", "08.00 PM - 11.59 PM"]
    rows = []
    for i, d in enumerate(dates):
        for store in stores:
            for slot in slots:
                rows.append({"date": d, "time_slot": slot, "footfall": 100.0 + i, "nob": 30.0 + i * 0.3, "store_code": store})
    return pd.DataFrame(rows)


def _target(n=90, start="2026-01-01", stores=("NM", "HB")) -> pd.DataFrame:
    dates = pd.date_range(start, periods=n, freq="D")
    rows = [{"date": d, "target": 300.0, "store_code": s} for d in dates for s in stores]
    return pd.DataFrame(rows)


FAST_MODEL_SET = ["naive_seasonal", "arima", "random_forest"]


def test_forecast_daily_sales_end_to_end():
    bundle = forecast_daily_sales(_fact(), _target(), store_code="NM", horizon=7, model_set=FAST_MODEL_SET)

    assert bundle.insufficient_history is False
    assert len(bundle.forecast) == 7
    assert list(bundle.forecast["date"]) == sorted(bundle.forecast["date"])
    assert (bundle.forecast["date"].diff().dropna() == pd.Timedelta(days=1)).all()
    assert not bundle.leaderboard.empty
    assert bundle.best_model in FAST_MODEL_SET
    # lower <= point <= upper for every forecasted day
    assert (bundle.forecast["lower"] <= bundle.forecast["point"] + 1e-6).all()
    assert (bundle.forecast["point"] <= bundle.forecast["upper"] + 1e-6).all()


def test_forecast_daily_sales_insufficient_history():
    tiny_fact = _fact(n=5)
    tiny_target = _target(n=5)
    bundle = forecast_daily_sales(tiny_fact, tiny_target, store_code="NM", horizon=7, model_set=FAST_MODEL_SET)
    assert bundle.insufficient_history is True
    assert bundle.forecast.empty
    assert bundle.leaderboard.empty
    assert bundle.best_model is None


def test_forecast_footfall_nob_timeslot_aware():
    footfall = _footfall()
    bundle = forecast_footfall_nob(footfall, "NM", "11.00 AM - 01.59 PM", "footfall", horizon=7, model_set=FAST_MODEL_SET)
    assert bundle.insufficient_history is False
    assert len(bundle.forecast) == 7


def test_forecast_products_top_n_plus_other():
    bundles = forecast_products(_fact(), "product_style", horizon=7, top_n=2, model_set=FAST_MODEL_SET)
    assert "Other" in bundles  # 3 styles total, top_n=2 -> 1 remaining folds into Other
    assert len(bundles) == 3  # 2 named styles + Other
    for b in bundles.values():
        assert b.insufficient_history is False
        assert len(b.forecast) == 7


def test_forecast_vendors_top_n_plus_other():
    bundles = forecast_vendors(_fact(), horizon=7, top_n=2, model_set=FAST_MODEL_SET)
    assert "Other" in bundles
    assert len(bundles) == 3


def test_growth_trajectory_needed_arithmetic():
    result = growth_trajectory_needed(recent_avg_daily=100.0, target_total=1500.0, days_remaining=10)
    assert result["required_avg_daily"] == pytest.approx(150.0)
    assert result["uplift_pct"] == pytest.approx(50.0)
    assert result["achievable_at_current_pace"] is False


def test_growth_trajectory_needed_already_achievable():
    result = growth_trajectory_needed(recent_avg_daily=200.0, target_total=1000.0, days_remaining=10)
    assert result["required_avg_daily"] == pytest.approx(100.0)
    assert result["achievable_at_current_pace"] is True


def test_growth_trajectory_needed_zero_current_avg_uplift_is_none():
    result = growth_trajectory_needed(recent_avg_daily=0.0, target_total=1000.0, days_remaining=10)
    assert result["uplift_pct"] is None
