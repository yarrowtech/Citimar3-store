"""One fit/predict interface (BaseForecastModel) over every candidate model
family, looked up by name via MODEL_REGISTRY so backtesting.py/orchestrator.py
never hardcode a specific class. ARIMA/SARIMA/SARIMAX/Prophet natively support
multi-step forecasting + their own prediction intervals; the three sklearn/
xgboost regressors need the recursive strategy (_SklearnRecursiveModel) plus
bootstrap intervals (see intervals.py) -- neither has a built-in notion of
"the next timestep".
"""
from __future__ import annotations

import itertools
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from typing import Callable

import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tsa.statespace.sarimax import SARIMAX
from xgboost import XGBRegressor

from config.forecast_settings import (
    ARIMA_ORDER_GRID,
    CONFIDENCE_LEVEL,
    HGB_MAX_ITER,
    MAX_GRID_SEARCH_COMBINATIONS,
    RANDOM_SEED,
    RF_MAX_DEPTH,
    RF_N_ESTIMATORS,
    SARIMA_SEASONAL_ORDER_GRID,
    XGB_LEARNING_RATE,
    XGB_MAX_DEPTH,
    XGB_N_ESTIMATORS,
)
from src.forecasting.feature_engineering import (
    FeatureConfig,
    add_calendar_features,
    add_cyclical_encodings,
    build_feature_matrix,
    build_feature_row,
    future_calendar_frame,
)
from src.forecasting.intervals import bootstrap_prediction_intervals

logger = logging.getLogger(__name__)


@dataclass
class ForecastResult:
    dates: list[pd.Timestamp]
    point: list[float]
    lower: list[float]
    upper: list[float]
    model_name: str
    used_native_intervals: bool  # True: statsmodels/Prophet. False: bootstrap.


class BaseForecastModel(ABC):
    name: str = "base"

    @abstractmethod
    def fit(
        self,
        series_df: pd.DataFrame,
        config: FeatureConfig,
        raw_regressors: pd.DataFrame | None = None,
        target_series: pd.Series | None = None,
    ) -> None: ...

    @abstractmethod
    def predict(self, horizon: int, alpha: float = 1 - CONFIDENCE_LEVEL) -> ForecastResult: ...


# --- Naive seasonal baseline -------------------------------------------------


class NaiveSeasonalModel(BaseForecastModel):
    """Predicts day t as the value SEASONAL_PERIOD days earlier, cycling the
    same weekly pattern forward once real history runs out. The sanity floor:
    any model scoring worse than this on the leaderboard is flagged in the UI,
    not silently trusted."""

    name = "naive_seasonal"

    def fit(self, series_df, config, raw_regressors=None, target_series=None) -> None:
        df = series_df.sort_values("date")
        self._y = df["y"].to_numpy(dtype="float64")
        self._last_date = df["date"].max() if not df.empty else None
        self._period = min(config.seasonal_period, len(self._y)) if len(self._y) else 1
        self._residuals = self._in_sample_residuals()

    def _in_sample_residuals(self) -> list[float]:
        n, m = len(self._y), self._period
        if n <= m:
            return []
        return (self._y[m:] - self._y[:-m]).tolist()

    def predict(self, horizon: int, alpha: float = 1 - CONFIDENCE_LEVEL) -> ForecastResult:
        n, m = len(self._y), self._period
        point = [float(self._y[n - m + ((h - 1) % m)]) if n else 0.0 for h in range(1, horizon + 1)]
        dates = [self._last_date + pd.Timedelta(days=h) for h in range(1, horizon + 1)] if self._last_date is not None else []
        residual_pool = {1: self._residuals} if self._residuals else {}
        if residual_pool:
            lower, upper = bootstrap_prediction_intervals(point, residual_pool)
        else:
            lower, upper = list(point), list(point)
        return ForecastResult(dates=dates, point=point, lower=lower, upper=upper, model_name=self.name, used_native_intervals=False)


# --- ARIMA / SARIMA / SARIMAX order selection (run ONCE per series, not per fold) ---


def select_arima_order(y: pd.Series) -> tuple[int, int, int]:
    """AIC grid search over ARIMA_ORDER_GRID, capped at
    MAX_GRID_SEARCH_COMBINATIONS. Callers (backtesting.backtest_model) run
    this once per series and reuse the result across every backtest fold and
    the final full-history refit -- re-searching per fold would be both slow
    and make folds harder to compare on equal footing."""
    grid = list(itertools.product(ARIMA_ORDER_GRID["p"], ARIMA_ORDER_GRID["d"], ARIMA_ORDER_GRID["q"]))
    grid = grid[:MAX_GRID_SEARCH_COMBINATIONS]
    best_order, best_aic = None, float("inf")
    for order in grid:
        try:
            fitted = ARIMA(y, order=order).fit()
            if fitted.aic < best_aic:
                best_aic, best_order = fitted.aic, order
        except Exception:  # noqa: BLE001 -- a non-converging candidate is skipped, not fatal
            continue
    if best_order is None:
        logger.warning("select_arima_order: every grid candidate failed to converge, falling back to (1,1,1)")
        return (1, 1, 1)
    return best_order


def select_sarima_seasonal_order(y: pd.Series, order: tuple[int, int, int], seasonal_period: int) -> tuple[int, int, int, int]:
    """AIC grid search over SARIMA_SEASONAL_ORDER_GRID with `order` held
    fixed (chosen separately by select_arima_order) -- keeps total fits
    bounded (8 candidates) instead of a full order x seasonal_order cross
    product. Selected once per series, same reuse contract as select_arima_order."""
    grid = list(itertools.product(SARIMA_SEASONAL_ORDER_GRID["P"], SARIMA_SEASONAL_ORDER_GRID["D"], SARIMA_SEASONAL_ORDER_GRID["Q"]))
    best_seasonal, best_aic = None, float("inf")
    for p, d, q in grid:
        seasonal_order = (p, d, q, seasonal_period)
        try:
            fitted = SARIMAX(y, order=order, seasonal_order=seasonal_order, enforce_stationarity=False, enforce_invertibility=False).fit(disp=False)
            if fitted.aic < best_aic:
                best_aic, best_seasonal = fitted.aic, seasonal_order
        except Exception:  # noqa: BLE001
            continue
    if best_seasonal is None:
        logger.warning("select_sarima_seasonal_order: every candidate failed, falling back to no seasonal component")
        return (0, 0, 0, seasonal_period)
    return best_seasonal


def _fit_arima_safe(y: pd.Series, order: tuple[int, int, int]):
    try:
        return ARIMA(y, order=order).fit()
    except Exception:  # noqa: BLE001
        logger.warning("ArimaModel: order %s failed to converge, falling back to (1,1,1)", order)
        return ARIMA(y, order=(1, 1, 1)).fit()


def _fit_sarimax_safe(y: pd.Series, order, seasonal_order, exog=None):
    try:
        return SARIMAX(y, order=order, seasonal_order=seasonal_order, exog=exog, enforce_stationarity=False, enforce_invertibility=False).fit(disp=False)
    except Exception:  # noqa: BLE001
        logger.warning("SarimaModel/SarimaxModel: order %s/%s failed, falling back to (1,1,1)/no seasonal", order, seasonal_order)
        return SARIMAX(y, order=(1, 1, 1), seasonal_order=(0, 0, 0, seasonal_order[3]), exog=exog, enforce_stationarity=False, enforce_invertibility=False).fit(disp=False)


class ArimaModel(BaseForecastModel):
    """statsmodels ARIMA on y alone (no seasonal term, no exog). `order` can
    be supplied by the caller (e.g. backtesting.py reusing a once-selected
    order across folds) -- if None, select_arima_order() runs at fit() time."""

    name = "arima"

    def __init__(self, order: tuple[int, int, int] | None = None):
        self.order = order
        self._fitted = None
        self._last_date: pd.Timestamp | None = None

    def fit(self, series_df, config, raw_regressors=None, target_series=None) -> None:
        df = series_df.sort_values("date").reset_index(drop=True)
        y = df["y"].astype("float64")
        self._last_date = df["date"].max()
        self.order = self.order or select_arima_order(y)
        self._fitted = _fit_arima_safe(y, self.order)

    def predict(self, horizon: int, alpha: float = 1 - CONFIDENCE_LEVEL) -> ForecastResult:
        forecast_res = self._fitted.get_forecast(steps=horizon)
        point = forecast_res.predicted_mean.tolist()
        ci = forecast_res.conf_int(alpha=alpha)
        lower, upper = ci.iloc[:, 0].tolist(), ci.iloc[:, 1].tolist()
        dates = [self._last_date + pd.Timedelta(days=h) for h in range(1, horizon + 1)]
        return ForecastResult(dates=dates, point=point, lower=lower, upper=upper, model_name=self.name, used_native_intervals=True)


class SarimaModel(ArimaModel):
    """Adds seasonal_order=(P,D,Q,seasonal_period) on top of ArimaModel's
    order -- period 7 (weekly) is the only seasonal cycle a single year of
    daily data can support. predict() is inherited unchanged: both ARIMA and
    SARIMAX fitted results expose the same get_forecast()/conf_int() interface."""

    name = "sarima"

    def __init__(self, order: tuple[int, int, int] | None = None, seasonal_order: tuple[int, int, int, int] | None = None):
        super().__init__(order=order)
        self.seasonal_order = seasonal_order

    def fit(self, series_df, config, raw_regressors=None, target_series=None) -> None:
        df = series_df.sort_values("date").reset_index(drop=True)
        y = df["y"].astype("float64")
        self._last_date = df["date"].max()
        self.order = self.order or select_arima_order(y)
        self.seasonal_order = self.seasonal_order or select_sarima_seasonal_order(y, self.order, config.seasonal_period)
        self._fitted = _fit_sarimax_safe(y, self.order, self.seasonal_order)


class SarimaxModel(SarimaModel):
    """Same order/seasonal_order machinery as SarimaModel, plus exog =
    calendar/cyclical columns ONLY (is_weekend, dow_sin/cos, month_sin/cos,
    day_of_month). Deliberately excludes promo/target features: SARIMAX needs
    real future exog values, and neither has one (no forward promo calendar;
    target only has a flat trailing-average guess beyond the workbook's last
    known row)."""

    name = "sarimax"
    _EXOG_COLUMNS = ["is_weekend", "dow_sin", "dow_cos", "month_sin", "month_cos", "day_of_month"]

    def fit(self, series_df, config, raw_regressors=None, target_series=None) -> None:
        df = series_df.sort_values("date").reset_index(drop=True)
        y = df["y"].astype("float64")
        self._last_date = df["date"].max()
        exog_df = add_cyclical_encodings(add_calendar_features(df[["date"]]))
        exog = exog_df[self._EXOG_COLUMNS]
        self.order = self.order or select_arima_order(y)
        self.seasonal_order = self.seasonal_order or select_sarima_seasonal_order(y, self.order, config.seasonal_period)
        self._fitted = _fit_sarimax_safe(y, self.order, self.seasonal_order, exog=exog)

    def predict(self, horizon: int, alpha: float = 1 - CONFIDENCE_LEVEL) -> ForecastResult:
        future_df = future_calendar_frame(self._last_date, horizon)
        future_exog = future_df[self._EXOG_COLUMNS]
        forecast_res = self._fitted.get_forecast(steps=horizon, exog=future_exog)
        point = forecast_res.predicted_mean.tolist()
        ci = forecast_res.conf_int(alpha=alpha)
        lower, upper = ci.iloc[:, 0].tolist(), ci.iloc[:, 1].tolist()
        return ForecastResult(dates=future_df["date"].tolist(), point=point, lower=lower, upper=upper, model_name=self.name, used_native_intervals=True)


# --- Prophet ------------------------------------------------------------


class ProphetModel(BaseForecastModel):
    """yearly_seasonality is explicitly disabled -- DATASET.xlsx covers a
    single calendar year, so Prophet would otherwise fit a nonsensical yearly
    curve off one partial cycle. Weekly seasonality stays on (the one real
    seasonal signal this data supports). Natively multi-step with native
    intervals, no recursion needed."""

    name = "prophet"

    def fit(self, series_df, config, raw_regressors=None, target_series=None) -> None:
        from prophet import Prophet

        df = series_df.sort_values("date").rename(columns={"date": "ds"})[["ds", "y"]]
        self._model = Prophet(
            yearly_seasonality=False,
            weekly_seasonality=True,
            daily_seasonality=False,
            interval_width=CONFIDENCE_LEVEL,
        )
        self._model.fit(df)

    def predict(self, horizon: int, alpha: float = 1 - CONFIDENCE_LEVEL) -> ForecastResult:
        future = self._model.make_future_dataframe(periods=horizon, freq="D")
        forecast = self._model.predict(future).tail(horizon)
        return ForecastResult(
            dates=forecast["ds"].tolist(),
            point=forecast["yhat"].tolist(),
            lower=forecast["yhat_lower"].tolist(),
            upper=forecast["yhat_upper"].tolist(),
            model_name=self.name,
            used_native_intervals=True,
        )


# --- Recursive sklearn/xgboost regressors --------------------------------


class _SklearnRecursiveModel(BaseForecastModel):
    """Shared base for RandomForest/HistGradientBoosting/XGBoost. None of
    these has a native notion of "the next timestep", so multi-step forecasts
    use the recursive strategy: predict one day, append it to a working copy
    of history, recompute lag/rolling features (which now include the model's
    own prior predictions), predict the next day. See build_feature_row /
    feature_engineering.py for why this can never drift from batch training's
    feature computation.

    Promo/target features are force-disabled here regardless of the caller's
    config: build_feature_row (used at every recursive step) can never
    reproduce them for a future date, so training must not use them either --
    otherwise the estimator would expect columns inference can't supply."""

    def _build_estimator(self):  # pragma: no cover - overridden by subclasses
        raise NotImplementedError

    def fit(self, series_df, config, raw_regressors=None, target_series=None) -> None:
        self._config = replace(config, include_promo_features=False, include_target_features=False)
        df = series_df.sort_values("date").reset_index(drop=True)
        self._history_df = df[["date", "y"]].copy()
        X, y, feature_names = build_feature_matrix(df, self._config)
        self._feature_names = feature_names
        if X.empty:
            self._estimator = None
            self._in_sample_residuals: list[float] = []
            return
        self._estimator = self._build_estimator()
        self._estimator.fit(X[feature_names], y)
        in_sample_pred = self._estimator.predict(X[feature_names])
        self._in_sample_residuals = (y.to_numpy() - in_sample_pred).tolist()

    def _recursive_predict(self, horizon: int) -> list[float]:
        working_history = self._history_df.copy()
        predictions: list[float] = []
        for _ in range(horizon):
            next_date = working_history["date"].max() + pd.Timedelta(days=1)
            x_row = build_feature_row(working_history, next_date, self._config)
            y_hat = float(self._estimator.predict(x_row[self._feature_names])[0])
            predictions.append(y_hat)
            working_history = pd.concat(
                [working_history, pd.DataFrame({"date": [next_date], "y": [y_hat]})],
                ignore_index=True,
            )
        return predictions

    def predict(self, horizon: int, alpha: float = 1 - CONFIDENCE_LEVEL) -> ForecastResult:
        last_date = self._history_df["date"].max() if not self._history_df.empty else None
        if self._estimator is None or last_date is None:
            # Not enough history to have fit anything -- orchestrator's
            # insufficient_history guard should normally prevent reaching
            # this, but degrade to a flat zero forecast rather than raise.
            dates = [last_date + pd.Timedelta(days=h) for h in range(1, horizon + 1)] if last_date is not None else []
            zeros = [0.0] * len(dates)
            return ForecastResult(dates=dates, point=zeros, lower=zeros, upper=zeros, model_name=self.name, used_native_intervals=False)

        point = self._recursive_predict(horizon)
        residual_pool = {1: self._in_sample_residuals} if self._in_sample_residuals else {}
        if residual_pool:
            lower, upper = bootstrap_prediction_intervals(point, residual_pool)
        else:
            lower, upper = list(point), list(point)
        dates = [last_date + pd.Timedelta(days=h) for h in range(1, horizon + 1)]
        return ForecastResult(dates=dates, point=point, lower=lower, upper=upper, model_name=self.name, used_native_intervals=False)


class RandomForestModel(_SklearnRecursiveModel):
    name = "random_forest"

    def _build_estimator(self):
        return RandomForestRegressor(n_estimators=RF_N_ESTIMATORS, max_depth=RF_MAX_DEPTH, random_state=RANDOM_SEED)


class HistGradientBoostingModel(_SklearnRecursiveModel):
    name = "hist_gradient_boosting"

    def _build_estimator(self):
        return HistGradientBoostingRegressor(max_iter=HGB_MAX_ITER, random_state=RANDOM_SEED)


class XGBoostModel(_SklearnRecursiveModel):
    name = "xgboost"

    def _build_estimator(self):
        return XGBRegressor(
            n_estimators=XGB_N_ESTIMATORS,
            max_depth=XGB_MAX_DEPTH,
            learning_rate=XGB_LEARNING_RATE,
            random_state=RANDOM_SEED,
            objective="reg:squarederror",
        )


MODEL_REGISTRY: dict[str, Callable[[], BaseForecastModel]] = {
    "naive_seasonal": NaiveSeasonalModel,
    "arima": ArimaModel,
    "sarima": SarimaModel,
    "sarimax": SarimaxModel,
    "prophet": ProphetModel,
    "random_forest": RandomForestModel,
    "hist_gradient_boosting": HistGradientBoostingModel,
    "xgboost": XGBoostModel,
}
