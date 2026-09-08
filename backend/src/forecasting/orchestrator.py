"""Top-level forecasting entrypoints the Streamlit app calls directly: build
series -> build walk-forward folds -> leaderboard -> pick best model -> refit
on full history -> forecast horizon -> attach honest (backtest-derived)
prediction intervals. Also owns growth_trajectory_needed, the pure-arithmetic
"up-scaling goal" calculator that has no model dependency at all, so it's
never blocked by a model/data failure.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from config.forecast_settings import (
    MIN_HISTORY_DAYS_FOR_FORECAST,
    PRIMARY_MODEL_ROSTER,
    PRODUCT_VENDOR_MODEL_ROSTER,
    TOP_N_PRODUCTS,
    TOP_N_VENDORS,
)
from src.forecasting.backtesting import BacktestResult, build_leaderboard, generate_walk_forward_folds, select_best_model
from src.forecasting.feature_engineering import FeatureConfig
from src.forecasting.intervals import bootstrap_prediction_intervals
from src.forecasting.model_registry import MODEL_REGISTRY
from src.forecasting.series_prep import (
    SeriesFrame,
    build_daily_sales_series,
    build_footfall_nob_series,
    build_target_aligned_series,
    top_n_entity_series,
)


@dataclass
class ForecastBundle:
    series_id: str
    label: str
    horizon: int
    history: pd.DataFrame  # date, y
    leaderboard: pd.DataFrame
    backtest_results: dict[str, BacktestResult]  # model_name -> result, reused by the Actual-vs-Estimate tab
    best_model: str | None
    forecast: pd.DataFrame  # date, point, lower, upper
    insufficient_history: bool  # True => forecast/leaderboard empty, UI shows a specific message instead of an error


def _insufficient_history_bundle(series_frame: SeriesFrame, horizon: int) -> ForecastBundle:
    return ForecastBundle(
        series_id=series_frame.series_id,
        label=series_frame.label,
        horizon=horizon,
        history=series_frame.df,
        leaderboard=pd.DataFrame(),
        backtest_results={},
        best_model=None,
        forecast=pd.DataFrame(columns=["date", "point", "lower", "upper"]),
        insufficient_history=True,
    )


def _run_forecast_for_series(
    series_frame: SeriesFrame,
    horizon: int,
    model_set: list[str] | None,
    primary_metric: str,
    target_series: pd.Series | None = None,
) -> ForecastBundle:
    history = series_frame.df
    if history.empty or len(history) < MIN_HISTORY_DAYS_FOR_FORECAST:
        return _insufficient_history_bundle(series_frame, horizon)

    resolved_model_set = model_set or (PRIMARY_MODEL_ROSTER if primary_metric == "mape" else PRODUCT_VENDOR_MODEL_ROSTER)
    config = FeatureConfig()

    folds = generate_walk_forward_folds(history["date"].min(), history["date"].max())
    leaderboard, backtest_results = build_leaderboard(
        history,
        resolved_model_set,
        folds,
        config,
        raw_regressors=series_frame.raw_regressors,
        target_series=target_series,
        primary_metric=primary_metric,
    )
    best_model = select_best_model(leaderboard, primary_metric) or "naive_seasonal"
    if best_model not in MODEL_REGISTRY:
        best_model = "naive_seasonal"

    fixed_kwargs = {}
    backtest_result_for_best = backtest_results.get(best_model)
    if backtest_result_for_best is not None and backtest_result_for_best.selected_order is not None:
        if best_model == "arima":
            fixed_kwargs = {"order": backtest_result_for_best.selected_order}
        elif best_model in ("sarima", "sarimax"):
            order, seasonal_order = backtest_result_for_best.selected_order
            fixed_kwargs = {"order": order, "seasonal_order": seasonal_order}

    final_model = MODEL_REGISTRY[best_model](**fixed_kwargs)
    final_model.fit(history, config, raw_regressors=series_frame.raw_regressors, target_series=target_series)
    result = final_model.predict(horizon)

    # Prefer genuinely out-of-sample backtest residuals over whatever
    # in-sample-residual interval the model computed internally -- tree-model
    # in-sample residuals are optimistic by construction (see intervals.py).
    if not result.used_native_intervals and backtest_result_for_best is not None and backtest_result_for_best.residuals_by_horizon_step:
        result.lower, result.upper = bootstrap_prediction_intervals(result.point, backtest_result_for_best.residuals_by_horizon_step)

    forecast_df = pd.DataFrame({"date": result.dates, "point": result.point, "lower": result.lower, "upper": result.upper})

    return ForecastBundle(
        series_id=series_frame.series_id,
        label=series_frame.label,
        horizon=horizon,
        history=history,
        leaderboard=leaderboard,
        backtest_results=backtest_results,
        best_model=best_model,
        forecast=forecast_df,
        insufficient_history=False,
    )


def forecast_daily_sales(
    fact: pd.DataFrame,
    target: pd.DataFrame,
    store_code: str | None,
    horizon: int,
    model_set: list[str] | None = None,
) -> ForecastBundle:
    series_frame = build_daily_sales_series(fact, store_code=store_code)
    target_series = build_target_aligned_series(target, store_code=store_code)
    return _run_forecast_for_series(series_frame, horizon, model_set, primary_metric="mape", target_series=target_series)


def growth_trajectory_needed(recent_avg_daily: float, target_total: float, days_remaining: int) -> dict:
    """Pure arithmetic, no model dependency -- the 'up-scaling goal' analysis
    is never blocked by a model/data failure."""
    required_avg_daily = max(target_total, 0) / max(days_remaining, 1)
    uplift_pct = ((required_avg_daily - recent_avg_daily) / recent_avg_daily * 100) if recent_avg_daily else None
    return {
        "current_avg_daily": recent_avg_daily,
        "required_avg_daily": required_avg_daily,
        "uplift_pct": uplift_pct,
        "achievable_at_current_pace": bool(recent_avg_daily is not None and recent_avg_daily >= required_avg_daily),
    }


def forecast_footfall_nob(
    footfall: pd.DataFrame,
    store_code: str,
    time_slot: str | None,
    value_col: str,
    horizon: int,
    model_set: list[str] | None = None,
) -> ForecastBundle:
    series_frame = build_footfall_nob_series(footfall, store_code, time_slot, value_col=value_col)
    return _run_forecast_for_series(series_frame, horizon, model_set, primary_metric="mape")


def forecast_products(
    fact: pd.DataFrame,
    level: str,
    horizon: int,
    top_n: int = TOP_N_PRODUCTS,
    model_set: list[str] | None = None,
) -> dict[str, ForecastBundle]:
    bundles = top_n_entity_series(fact, level, top_n)
    return {
        name: _run_forecast_for_series(series_frame, horizon, model_set, primary_metric="wape")
        for name, series_frame in bundles.items()
    }


def forecast_vendors(
    fact: pd.DataFrame,
    horizon: int,
    top_n: int = TOP_N_VENDORS,
    model_set: list[str] | None = None,
) -> dict[str, ForecastBundle]:
    bundles = top_n_entity_series(fact, "vendors", top_n)
    return {
        name: _run_forecast_for_series(series_frame, horizon, model_set, primary_metric="wape")
        for name, series_frame in bundles.items()
    }
