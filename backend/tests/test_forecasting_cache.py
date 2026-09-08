import pandas as pd

from src.forecasting import cache
from src.forecasting.cache import forecast_cache_key, load_cached_forecast, save_forecast_cache
from src.forecasting.orchestrator import ForecastBundle


def _bundle(series_id="daily_sales|store=NM") -> ForecastBundle:
    return ForecastBundle(
        series_id=series_id,
        label="Daily Net Sales — NM",
        horizon=7,
        history=pd.DataFrame({"date": pd.date_range("2026-01-01", periods=3), "y": [1.0, 2.0, 3.0]}),
        leaderboard=pd.DataFrame({"model": ["naive_seasonal"], "mean_mape": [10.0]}),
        backtest_results={},
        best_model="naive_seasonal",
        forecast=pd.DataFrame({"date": pd.date_range("2026-01-04", periods=2), "point": [4.0, 5.0], "lower": [3.0, 4.0], "upper": [5.0, 6.0]}),
        insufficient_history=False,
    )


def test_forecast_cache_key_stable_and_unique():
    k1 = forecast_cache_key("daily_sales|store=NM", 30, ("arima", "naive_seasonal"))
    k2 = forecast_cache_key("daily_sales|store=NM", 30, ("naive_seasonal", "arima"))  # order-independent
    assert k1 == k2

    assert forecast_cache_key("daily_sales|store=NM", 60, ("arima",)) != k1
    assert forecast_cache_key("daily_sales|store=HB", 30, ("arima", "naive_seasonal")) != k1
    assert forecast_cache_key("daily_sales|store=NM", 30, ("arima",)) != k1


def test_load_cached_forecast_missing_file_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "FORECAST_CACHE_DIR", tmp_path)
    assert load_cached_forecast("does-not-exist", source_mtime=123.0) is None


def test_save_and_load_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "FORECAST_CACHE_DIR", tmp_path)
    bundle = _bundle()
    save_forecast_cache("key1", bundle, source_mtime=100.0)

    loaded = load_cached_forecast("key1", source_mtime=100.0)
    assert loaded is not None
    assert loaded.series_id == bundle.series_id
    assert loaded.best_model == bundle.best_model
    pd.testing.assert_frame_equal(loaded.forecast, bundle.forecast)


def test_load_cached_forecast_mtime_mismatch_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "FORECAST_CACHE_DIR", tmp_path)
    save_forecast_cache("key2", _bundle(), source_mtime=100.0)
    assert load_cached_forecast("key2", source_mtime=999.0) is None


def test_load_cached_forecast_stale_schema_version_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "FORECAST_CACHE_DIR", tmp_path)
    save_forecast_cache("key3", _bundle(), source_mtime=100.0)  # written with the real CACHE_SCHEMA_VERSION (1)

    monkeypatch.setattr(cache, "CACHE_SCHEMA_VERSION", 2)  # simulate a ForecastBundle shape change after this entry was written
    assert load_cached_forecast("key3", source_mtime=100.0) is None


def test_load_cached_forecast_corrupted_pickle_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "FORECAST_CACHE_DIR", tmp_path)
    bad_path = tmp_path / "corrupt.pkl"
    bad_path.write_bytes(b"not a real pickle")
    assert load_cached_forecast("corrupt", source_mtime=100.0) is None
