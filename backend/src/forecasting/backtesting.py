"""Walk-forward rolling-origin backtesting: the single place MAPE/RMSE/MAE/WAPE
are computed, so the leaderboard, the "best model" selection, and the Actual
vs Estimation tab all read identical numbers. Folds are deliberately small
(default 7-day blocks) because DATASET.xlsx only spans ~181 days -- the usual
multi-month holdout isn't available.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from config.forecast_settings import (
    BACKTEST_FOLD_SIZE_DAYS,
    BACKTEST_MIN_TRAIN_DAYS,
    BACKTEST_N_FOLDS,
    MAPE_EPSILON,
)
from src.forecasting.feature_engineering import FeatureConfig
from src.forecasting.model_registry import MODEL_REGISTRY, select_arima_order, select_sarima_seasonal_order


@dataclass
class Fold:
    fold_index: int
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp


@dataclass
class FoldScore:
    fold_index: int
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    mape: float | None
    rmse: float | None
    mae: float | None
    wape: float | None
    actual: list[float] = field(default_factory=list)
    predicted: list[float] = field(default_factory=list)
    error: str | None = None


@dataclass
class BacktestResult:
    model_name: str
    fold_scores: list[FoldScore]
    mean_mape: float | None
    mean_rmse: float | None
    mean_mae: float | None
    mean_wape: float | None
    residuals_by_horizon_step: dict[int, list[float]]
    selected_order: tuple | None = None  # ARIMA (p,d,q) or SARIMA/SARIMAX ((p,d,q), (P,D,Q,m)) chosen once, for reuse


def generate_walk_forward_folds(
    min_date,
    max_date,
    fold_size_days: int = BACKTEST_FOLD_SIZE_DAYS,
    n_folds: int = BACKTEST_N_FOLDS,
    min_train_days: int = BACKTEST_MIN_TRAIN_DAYS,
) -> list[Fold]:
    """Counts backward from max_date in fold_size_days blocks. Stops early
    (returns fewer than n_folds, possibly zero) once a fold's train window
    would fall below min_train_days -- 181 days of history can't support the
    usual multi-month holdout. Returned oldest-first."""
    min_date, max_date = pd.Timestamp(min_date), pd.Timestamp(max_date)
    folds: list[Fold] = []
    test_end = max_date
    for i in range(n_folds):
        test_start = test_end - pd.Timedelta(days=fold_size_days - 1)
        train_end = test_start - pd.Timedelta(days=1)
        train_days = (train_end - min_date).days + 1
        if train_days < min_train_days:
            break
        folds.append(Fold(fold_index=i, train_end=train_end, test_start=test_start, test_end=test_end))
        test_end = train_end
    folds.reverse()
    for new_index, fold in enumerate(folds):
        fold.fold_index = new_index
    return folds


def _to_metric_arrays(actual, predicted) -> tuple[np.ndarray, np.ndarray] | None:
    if not actual or not predicted or len(actual) != len(predicted):
        return None
    return np.asarray(actual, dtype="float64"), np.asarray(predicted, dtype="float64")


def mape(actual: list[float], predicted: list[float], epsilon: float = MAPE_EPSILON) -> float | None:
    arrays = _to_metric_arrays(actual, predicted)
    if arrays is None:
        return None
    a, p = arrays
    return float(np.mean(np.abs(a - p) / (np.abs(a) + epsilon)) * 100)


def rmse(actual: list[float], predicted: list[float]) -> float | None:
    arrays = _to_metric_arrays(actual, predicted)
    if arrays is None:
        return None
    a, p = arrays
    return float(np.sqrt(np.mean((a - p) ** 2)))


def mae(actual: list[float], predicted: list[float]) -> float | None:
    arrays = _to_metric_arrays(actual, predicted)
    if arrays is None:
        return None
    a, p = arrays
    return float(np.mean(np.abs(a - p)))


def wape(actual: list[float], predicted: list[float]) -> float | None:
    """sum(|actual-predicted|) / sum(|actual|) * 100 -- the zero-inflation-
    robust metric. Daily total sales/footfall are large and rarely zero, so
    MAPE behaves fine there, but per-product/per-vendor series have many
    zero-sales days after gap-filling, where MAPE explodes even with an
    epsilon guard. WAPE degrades gracefully instead."""
    arrays = _to_metric_arrays(actual, predicted)
    if arrays is None:
        return None
    a, p = arrays
    denom = np.sum(np.abs(a))
    if denom == 0:
        return None
    return float(np.sum(np.abs(a - p)) / denom * 100)


def _select_order_once(model_name: str, series_df: pd.DataFrame, config: FeatureConfig):
    """Refinement: order is chosen ONCE per series via AIC grid search against
    the full history, then reused (only coefficients refit) across every
    backtest fold and the final full-history refit -- re-searching an 18+8
    combo grid on every fold would be slow and makes folds harder to compare
    on equal footing."""
    if model_name not in ("arima", "sarima", "sarimax"):
        return {}, None
    y = series_df.sort_values("date")["y"].astype("float64").reset_index(drop=True)
    order = select_arima_order(y)
    if model_name == "arima":
        return {"order": order}, order
    seasonal_order = select_sarima_seasonal_order(y, order, config.seasonal_period)
    return {"order": order, "seasonal_order": seasonal_order}, (order, seasonal_order)


def backtest_model(
    model_name: str,
    series_df: pd.DataFrame,
    folds: list[Fold],
    config: FeatureConfig,
    raw_regressors: pd.DataFrame | None = None,
    target_series: pd.Series | None = None,
) -> BacktestResult:
    fixed_kwargs, selected_order = _select_order_once(model_name, series_df, config)

    fold_scores: list[FoldScore] = []
    residuals_by_horizon_step: dict[int, list[float]] = {}

    for fold in folds:
        train_df = series_df.loc[series_df["date"] <= fold.train_end]
        test_df = series_df.loc[(series_df["date"] >= fold.test_start) & (series_df["date"] <= fold.test_end)].sort_values("date")

        if train_df.empty or test_df.empty:
            fold_scores.append(
                FoldScore(fold.fold_index, fold.test_start, fold.test_end, None, None, None, None, error="empty train/test window")
            )
            continue

        try:
            model = MODEL_REGISTRY[model_name](**fixed_kwargs)
            fold_raw_regressors = raw_regressors.loc[raw_regressors["date"] <= fold.train_end] if raw_regressors is not None else None
            fold_target_series = target_series.loc[target_series.index <= fold.train_end] if target_series is not None and not target_series.empty else None
            model.fit(train_df, config, raw_regressors=fold_raw_regressors, target_series=fold_target_series)

            result = model.predict(len(test_df))
            actual = test_df["y"].tolist()
            predicted = list(result.point)[: len(actual)]

            fold_scores.append(
                FoldScore(
                    fold_index=fold.fold_index,
                    test_start=fold.test_start,
                    test_end=fold.test_end,
                    mape=mape(actual, predicted),
                    rmse=rmse(actual, predicted),
                    mae=mae(actual, predicted),
                    wape=wape(actual, predicted),
                    actual=actual,
                    predicted=predicted,
                )
            )
            for step, (a, p) in enumerate(zip(actual, predicted), start=1):
                residuals_by_horizon_step.setdefault(step, []).append(a - p)
        except Exception as exc:  # noqa: BLE001 -- one fold's failure (e.g. non-convergence) must not abort the whole backtest
            fold_scores.append(
                FoldScore(fold.fold_index, fold.test_start, fold.test_end, None, None, None, None, error=str(exc))
            )

    def _mean_of(attr: str) -> float | None:
        values = [getattr(fs, attr) for fs in fold_scores if fs.error is None and getattr(fs, attr) is not None]
        return float(np.mean(values)) if values else None

    return BacktestResult(
        model_name=model_name,
        fold_scores=fold_scores,
        mean_mape=_mean_of("mape"),
        mean_rmse=_mean_of("rmse"),
        mean_mae=_mean_of("mae"),
        mean_wape=_mean_of("wape"),
        residuals_by_horizon_step=residuals_by_horizon_step,
        selected_order=selected_order,
    )


def build_leaderboard(
    series_df: pd.DataFrame,
    model_set: list[str],
    folds: list[Fold],
    config: FeatureConfig,
    raw_regressors: pd.DataFrame | None = None,
    target_series: pd.Series | None = None,
    primary_metric: str = "mape",
) -> tuple[pd.DataFrame, dict[str, BacktestResult]]:
    """Runs backtest_model for every model_set entry. Returns
    (leaderboard_df, results_by_model) -- the full BacktestResult per model is
    returned alongside the summary table (not just the table) so callers
    (orchestrator.py) can reuse backtest residuals for prediction intervals
    and the Actual-vs-Estimate tab can render fold-level actual-vs-predicted
    without re-running the backtest. A model failing every fold still appears
    with all-null scores -- failure is visible, not hidden."""
    rows = []
    results_by_model: dict[str, BacktestResult] = {}
    for model_name in model_set:
        result = backtest_model(model_name, series_df, folds, config, raw_regressors, target_series)
        results_by_model[model_name] = result
        rows.append(
            {
                "model": model_name,
                "mean_mape": result.mean_mape,
                "mean_rmse": result.mean_rmse,
                "mean_mae": result.mean_mae,
                "mean_wape": result.mean_wape,
                "folds_evaluated": sum(1 for fs in result.fold_scores if fs.error is None),
                "folds_failed": sum(1 for fs in result.fold_scores if fs.error is not None),
            }
        )
    leaderboard = pd.DataFrame(rows)
    sort_col = f"mean_{primary_metric}"
    leaderboard = leaderboard.sort_values(sort_col, na_position="last").reset_index(drop=True)
    return leaderboard, results_by_model


def select_best_model(leaderboard: pd.DataFrame, primary_metric: str = "mape") -> str | None:
    sort_col = f"mean_{primary_metric}"
    if leaderboard.empty or sort_col not in leaderboard.columns:
        return None
    valid = leaderboard.loc[leaderboard[sort_col].notna()]
    if valid.empty:
        return None
    return str(valid.sort_values(sort_col).iloc[0]["model"])
