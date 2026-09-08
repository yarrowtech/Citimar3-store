"""Prediction-interval math for models with no native notion of forecast
uncertainty. ARIMA/SARIMA/SARIMAX/Prophet all produce their own intervals
(state-space forecast-error variance / Bayesian posterior respectively);
RandomForest/HistGradientBoosting/XGBoost have no such machinery, so their
model_registry adapters borrow this bootstrap-residual approach instead.
"""
from __future__ import annotations

import numpy as np

from config.forecast_settings import BOOTSTRAP_N_SIMS, CONFIDENCE_LEVEL, RANDOM_SEED


def bootstrap_prediction_intervals(
    point_forecast: list[float],
    residuals_by_step: dict[int, list[float]],
    n_sims: int = BOOTSTRAP_N_SIMS,
    alpha: float = 1 - CONFIDENCE_LEVEL,
    seed: int = RANDOM_SEED,
) -> tuple[list[float], list[float]]:
    """residuals_by_step[h] = pooled (actual - predicted) errors observed at
    forecast-step h across walk-forward backtest folds, for the SAME model
    about to produce this live forecast (already computed by
    backtesting.build_leaderboard -- no extra backtest run needed here). For
    h beyond the largest step with residuals (h_max), reuses h_max's residual
    pool scaled by sqrt(h / h_max) so bands keep widening with horizon instead
    of flattening out past the backtest fold size. Deterministic given `seed`.
    Returns (lower, upper), same length as point_forecast."""
    rng = np.random.default_rng(seed)
    steps_with_residuals = sorted(k for k, v in residuals_by_step.items() if v)

    if not steps_with_residuals:
        # No residual history at all (e.g. a lone ad-hoc call with no prior
        # backtest) -- degrade to a zero-width band rather than crash. Callers
        # should prefer in_sample_residuals() as a fallback source instead.
        return list(point_forecast), list(point_forecast)

    h_max = steps_with_residuals[-1]
    lower: list[float] = []
    upper: list[float] = []
    for h, point in enumerate(point_forecast, start=1):
        step_for_pool = h if residuals_by_step.get(h) else h_max
        pool = np.asarray(residuals_by_step[step_for_pool], dtype="float64")
        # De-mean: point_forecast is already this model's best estimate, so
        # the bootstrap should express SPREAD around it, not re-inject the
        # model's own historical bias (e.g. a naive/seasonal method on a
        # trending series has a systematically nonzero-mean residual pool --
        # sampling it raw could push the whole band to one side of the point
        # forecast, breaking lower <= point <= upper).
        pool = pool - pool.mean()
        scale = float(np.sqrt(h / step_for_pool)) if h > step_for_pool else 1.0
        sampled = rng.choice(pool, size=n_sims, replace=True) * scale
        simulated = point + sampled
        lo, hi = np.percentile(simulated, [100 * alpha / 2, 100 * (1 - alpha / 2)])
        lower.append(float(lo))
        upper.append(float(hi))
    return lower, upper


def in_sample_residuals(y_true: list[float], y_pred: list[float]) -> list[float]:
    """Fallback source of residuals for an ad-hoc forecast with no prior
    backtest. Less trustworthy than backtest residuals (tree-model in-sample
    residuals are optimistic by construction, since the model partly
    memorized the data they're computed on) -- callers using this path should
    flag ForecastResult.used_native_intervals=False with an 'approximate
    interval' note in the UI."""
    return [float(a) - float(p) for a, p in zip(y_true, y_pred)]
