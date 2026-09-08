import math

import numpy as np
import pandas as pd
import pytest

from src.forecasting import backtesting
from src.forecasting import model_registry
from src.forecasting.backtesting import (
    Fold,
    backtest_model,
    build_leaderboard,
    generate_walk_forward_folds,
    mae,
    mape,
    rmse,
    select_best_model,
    wape,
)
from src.forecasting.feature_engineering import FeatureConfig
from src.forecasting.model_registry import ForecastResult


def _linear_series_df(n=40, start="2026-01-01") -> pd.DataFrame:
    dates = pd.date_range(start, periods=n, freq="D")
    return pd.DataFrame({"date": dates, "y": [float(i) for i in range(n)]})


def _sine_trend_series(n=80, start="2026-01-01") -> pd.DataFrame:
    dates = pd.date_range(start, periods=n, freq="D")
    t = np.arange(n)
    y = 100 + 0.5 * t + 20 * np.sin(2 * np.pi * t / 7)
    return pd.DataFrame({"date": dates, "y": y})


# --- generate_walk_forward_folds ---


def test_generate_walk_forward_folds_boundaries():
    min_date = pd.Timestamp("2026-01-01")
    max_date = min_date + pd.Timedelta(days=119)  # 120-day range
    folds = generate_walk_forward_folds(min_date, max_date, fold_size_days=7, n_folds=4, min_train_days=60)

    assert len(folds) == 4
    assert folds[0].fold_index == 0  # oldest-first
    assert folds[-1].test_end == max_date
    for i in range(len(folds) - 1):
        assert folds[i].test_end < folds[i + 1].test_start
    for f in folds:
        assert (f.test_end - f.test_start).days == 6
        assert f.train_end == f.test_start - pd.Timedelta(days=1)


def test_generate_walk_forward_folds_early_stop_when_train_too_short():
    min_date = pd.Timestamp("2026-01-01")
    max_date = min_date + pd.Timedelta(days=30)  # only 31 days total
    folds = generate_walk_forward_folds(min_date, max_date, fold_size_days=7, n_folds=4, min_train_days=60)
    assert folds == []  # can never reach 60 train days from only 31 days of data


# --- metrics ---


def test_mape_hand_computed():
    value = mape([100.0, 200.0], [110.0, 180.0])
    expected = ((10 / 100) + (20 / 200)) / 2 * 100
    assert value == pytest.approx(expected, rel=1e-4)


def test_mape_epsilon_guards_zero_actual():
    value = mape([0.0, 10.0], [1.0, 10.0])
    assert value is not None and math.isfinite(value)


def test_rmse_mae_hand_computed():
    actual, predicted = [10.0, 20.0, 30.0], [12.0, 18.0, 33.0]
    assert mae(actual, predicted) == pytest.approx((2 + 2 + 3) / 3)
    assert rmse(actual, predicted) == pytest.approx(math.sqrt((4 + 4 + 9) / 3))


def test_wape_hand_computed():
    actual, predicted = [10.0, 20.0, 30.0], [12.0, 18.0, 33.0]
    expected = (2 + 2 + 3) / (10 + 20 + 30) * 100
    assert wape(actual, predicted) == pytest.approx(expected)


def test_wape_none_when_actual_sums_to_zero():
    assert wape([0.0, 0.0], [1.0, 2.0]) is None


def test_metrics_none_on_mismatched_or_empty_input():
    assert mape([], []) is None
    assert rmse([1.0], [1.0, 2.0]) is None
    assert mae([], []) is None
    assert wape([], []) is None


# --- backtest_model with controllable dummy models ---


class _DeterministicOffsetModel:
    """Predicts last-train-value + 1, constant across the whole horizon --
    deterministic and hand-computable, with no lookahead into test actuals."""

    name = "dummy_offset"

    def fit(self, series_df, config, raw_regressors=None, target_series=None):
        self._value = float(series_df.sort_values("date")["y"].iloc[-1]) + 1.0
        self._last_date = series_df["date"].max()

    def predict(self, horizon, alpha=0.1):
        dates = [self._last_date + pd.Timedelta(days=h) for h in range(1, horizon + 1)]
        point = [self._value] * horizon
        return ForecastResult(dates=dates, point=point, lower=point, upper=point, model_name=self.name, used_native_intervals=True)


class _AlwaysRaisesModel:
    name = "dummy_raises"

    def fit(self, series_df, config, raw_regressors=None, target_series=None):
        raise RuntimeError("synthetic failure for backtest error-handling test")

    def predict(self, horizon, alpha=0.1):
        raise RuntimeError("should not be reached")


def test_backtest_model_exact_metrics_with_deterministic_model(monkeypatch):
    monkeypatch.setitem(model_registry.MODEL_REGISTRY, "dummy_offset", _DeterministicOffsetModel)
    series_df = _linear_series_df(40)  # y = 0..39
    fold = Fold(
        fold_index=0,
        train_end=pd.Timestamp("2026-01-01") + pd.Timedelta(days=29),  # y[29] = 29.0
        test_start=pd.Timestamp("2026-01-01") + pd.Timedelta(days=30),
        test_end=pd.Timestamp("2026-01-01") + pd.Timedelta(days=34),
    )
    result = backtest_model("dummy_offset", series_df, [fold], FeatureConfig())

    assert len(result.fold_scores) == 1
    fs = result.fold_scores[0]
    assert fs.error is None
    assert fs.actual == [30.0, 31.0, 32.0, 33.0, 34.0]
    assert fs.predicted == [30.0, 30.0, 30.0, 30.0, 30.0]  # constant: last_train(29)+1
    errors = [0.0, 1.0, 2.0, 3.0, 4.0]
    assert fs.mae == pytest.approx(sum(errors) / 5)
    assert fs.rmse == pytest.approx(math.sqrt(sum(e**2 for e in errors) / 5))
    assert fs.wape == pytest.approx(sum(errors) / sum(fs.actual) * 100)
    assert result.mean_mae == pytest.approx(fs.mae)


def test_backtest_model_fold_failure_does_not_raise(monkeypatch):
    monkeypatch.setitem(model_registry.MODEL_REGISTRY, "dummy_raises", _AlwaysRaisesModel)
    series_df = _linear_series_df(40)
    folds = generate_walk_forward_folds(series_df["date"].min(), series_df["date"].max(), fold_size_days=5, n_folds=2, min_train_days=20)
    assert len(folds) >= 1

    result = backtest_model("dummy_raises", series_df, folds, FeatureConfig())  # must not raise
    assert all(fs.error is not None for fs in result.fold_scores)
    assert all(fs.mape is None for fs in result.fold_scores)
    assert result.mean_mape is None


def test_backtest_model_empty_fold_window_handled():
    series_df = _linear_series_df(10)
    # A fold entirely outside the series' date range -> empty train/test slices.
    fold = Fold(fold_index=0, train_end=pd.Timestamp("2020-01-01"), test_start=pd.Timestamp("2020-01-02"), test_end=pd.Timestamp("2020-01-03"))
    result = backtest_model("naive_seasonal", series_df, [fold], FeatureConfig())
    assert result.fold_scores[0].error is not None
    assert result.mean_mape is None


# --- build_leaderboard / select_best_model ---


def test_build_leaderboard_sorts_ascending_nulls_last(monkeypatch):
    monkeypatch.setitem(model_registry.MODEL_REGISTRY, "dummy_offset", _DeterministicOffsetModel)
    monkeypatch.setitem(model_registry.MODEL_REGISTRY, "dummy_raises", _AlwaysRaisesModel)
    series_df = _linear_series_df(40)
    folds = generate_walk_forward_folds(series_df["date"].min(), series_df["date"].max(), fold_size_days=5, n_folds=2, min_train_days=20)

    leaderboard, results = build_leaderboard(series_df, ["dummy_offset", "dummy_raises", "naive_seasonal"], folds, FeatureConfig(), primary_metric="mae")

    assert set(results.keys()) == {"dummy_offset", "dummy_raises", "naive_seasonal"}
    # dummy_raises' mean_mae is null -> must sort to the very end regardless of primary_metric value
    assert leaderboard.iloc[-1]["model"] == "dummy_raises"
    assert pd.isna(leaderboard.iloc[-1]["mean_mae"])
    # Every non-null row must be ascending by the primary metric.
    non_null = leaderboard.loc[leaderboard["mean_mae"].notna(), "mean_mae"].tolist()
    assert non_null == sorted(non_null)


def test_select_best_model_lowest_metric_and_none_when_all_null(monkeypatch):
    monkeypatch.setitem(model_registry.MODEL_REGISTRY, "dummy_raises", _AlwaysRaisesModel)
    series_df = _linear_series_df(40)
    folds = generate_walk_forward_folds(series_df["date"].min(), series_df["date"].max(), fold_size_days=5, n_folds=2, min_train_days=20)

    leaderboard, _ = build_leaderboard(series_df, ["naive_seasonal", "dummy_raises"], folds, FeatureConfig(), primary_metric="mape")
    assert select_best_model(leaderboard, primary_metric="mape") == "naive_seasonal"

    all_null_leaderboard, _ = build_leaderboard(series_df, ["dummy_raises"], folds, FeatureConfig(), primary_metric="mape")
    assert select_best_model(all_null_leaderboard, primary_metric="mape") is None


# --- order-selected-once (refinement #1) ---


def test_arima_order_selected_once_not_per_fold(monkeypatch):
    call_count = {"n": 0}
    original = model_registry.select_arima_order

    def counting_wrapper(y):
        call_count["n"] += 1
        return original(y)

    monkeypatch.setattr(backtesting, "select_arima_order", counting_wrapper)

    series_df = _sine_trend_series(80)
    folds = generate_walk_forward_folds(series_df["date"].min(), series_df["date"].max(), fold_size_days=7, n_folds=3, min_train_days=30)
    assert len(folds) >= 2  # need multiple folds for this test to be meaningful

    result = backtest_model("arima", series_df, folds, FeatureConfig())
    assert call_count["n"] == 1
    assert result.selected_order is not None
