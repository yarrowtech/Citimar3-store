import numpy as np
import pandas as pd
import pytest

from src.forecasting.feature_engineering import FeatureConfig
from src.forecasting.model_registry import (
    MODEL_REGISTRY,
    ArimaModel,
    NaiveSeasonalModel,
    SarimaModel,
    SarimaxModel,
    _SklearnRecursiveModel,
)


def _synthetic_series_df(n=90, start="2026-01-01") -> pd.DataFrame:
    dates = pd.date_range(start, periods=n, freq="D")
    t = np.arange(n)
    y = 100 + 0.5 * t + 20 * np.sin(2 * np.pi * t / 7)  # trend + weekly seasonality
    return pd.DataFrame({"date": dates, "y": y})


# Fixed orders passed explicitly to skip each model's internal AIC grid
# search (that search is covered separately in test_forecasting_backtesting.py)
# -- keeps this smoke test fast while still exercising fit()/predict() for
# every adapter in MODEL_REGISTRY.
FAST_MODELS = {
    "naive_seasonal": lambda: MODEL_REGISTRY["naive_seasonal"](),
    "arima": lambda: ArimaModel(order=(1, 1, 1)),
    "sarima": lambda: SarimaModel(order=(1, 1, 1), seasonal_order=(1, 0, 0, 7)),
    "sarimax": lambda: SarimaxModel(order=(1, 1, 1), seasonal_order=(1, 0, 0, 7)),
    "prophet": lambda: MODEL_REGISTRY["prophet"](),
    "random_forest": lambda: MODEL_REGISTRY["random_forest"](),
    "hist_gradient_boosting": lambda: MODEL_REGISTRY["hist_gradient_boosting"](),
    "xgboost": lambda: MODEL_REGISTRY["xgboost"](),
}


@pytest.mark.parametrize("model_name", list(FAST_MODELS.keys()))
def test_fit_predict_smoke(model_name):
    series_df = _synthetic_series_df()
    config = FeatureConfig()
    model = FAST_MODELS[model_name]()
    model.fit(series_df, config)
    horizon = 7
    result = model.predict(horizon)

    assert len(result.point) == horizon
    assert len(result.dates) == horizon
    for i in range(1, horizon):
        assert (pd.Timestamp(result.dates[i]) - pd.Timestamp(result.dates[i - 1])) == pd.Timedelta(days=1)
    for lo, p, hi in zip(result.lower, result.point, result.upper):
        assert lo <= p <= hi
    assert result.model_name == model_name


def test_naive_seasonal_exact_seven_day_lag():
    series_df = _synthetic_series_df(n=30)
    model = NaiveSeasonalModel()
    model.fit(series_df, FeatureConfig())
    result = model.predict(7)
    expected = series_df["y"].to_numpy()[-7:]
    assert result.point == pytest.approx(expected.tolist())


def test_recursive_predict_refeeds_prior_predictions():
    """A toy estimator that always predicts lag_1 + 1. If the recursive loop
    correctly re-feeds its own predictions into working history, the forecast
    keeps climbing by 1 each step (40, 41, 42, ...). A buggy loop that
    recomputed lag_1 from the ORIGINAL static series at every step (never
    appending its own predictions) would instead predict the same value
    every time (40, 40, 40, ...) -- these two behaviors are distinguishable,
    unlike a plain lag-echo estimator."""

    class _IncrementingEstimator:
        def fit(self, X, y):
            return self

        def predict(self, X):
            return X["lag_1"].to_numpy() + 1.0

    class _IncrementModel(_SklearnRecursiveModel):
        name = "increment_test"

        def _build_estimator(self):
            return _IncrementingEstimator()

    series_df = pd.DataFrame(
        {"date": pd.date_range("2026-01-01", periods=40, freq="D"), "y": np.arange(40, dtype="float64")}
    )
    config = FeatureConfig(lags=(1,), rolling_windows=(7,))
    model = _IncrementModel()
    model.fit(series_df, config)
    result = model.predict(5)

    assert result.point == pytest.approx([40.0, 41.0, 42.0, 43.0, 44.0])
