import math

import pandas as pd
import pytest

from src.forecasting.feature_engineering import (
    FeatureConfig,
    add_calendar_features,
    add_cyclical_encodings,
    add_lag_features,
    add_promo_features,
    add_rolling_features,
    add_target_features,
    build_feature_matrix,
    build_feature_row,
)


def _series_df(n=15, start="2026-01-01") -> pd.DataFrame:
    dates = pd.date_range(start, periods=n, freq="D")
    return pd.DataFrame({"date": dates, "y": [float(i) for i in range(n)]})


def test_add_lag_features_matches_shift():
    df = add_lag_features(_series_df(), "y", (1, 3))
    assert df["lag_1"].tolist()[1:] == df["y"].tolist()[:-1]
    assert pd.isna(df["lag_1"].iloc[0])
    assert pd.isna(df["lag_3"].iloc[:3]).all()
    assert df["lag_3"].iloc[3] == df["y"].iloc[0]


def test_add_rolling_features_excludes_current_row():
    df = _series_df(10)
    out = add_rolling_features(df, "y", (3,))
    # roll_mean_3 at row i = mean(y[i-3:i]) -- NOT including y[i] itself.
    expected_row5 = df["y"].iloc[2:5].mean()
    assert out["roll_mean_3"].iloc[5] == pytest.approx(expected_row5)
    assert pd.isna(out["roll_mean_3"].iloc[0])


def test_add_calendar_features_known_date():
    df = pd.DataFrame({"date": pd.to_datetime(["2026-01-05"])})  # a Monday
    out = add_calendar_features(df)
    assert out["dow"].iloc[0] == 0
    assert out["is_weekend"].iloc[0] == 0
    assert out["month"].iloc[0] == 1
    assert out["day_of_month"].iloc[0] == 5


def test_add_calendar_features_weekend():
    df = pd.DataFrame({"date": pd.to_datetime(["2026-01-10"])})  # a Saturday
    out = add_calendar_features(df)
    assert out["dow"].iloc[0] == 5
    assert out["is_weekend"].iloc[0] == 1


def test_add_cyclical_encodings_monday_is_zero():
    df = pd.DataFrame({"date": pd.to_datetime(["2026-01-05"])})
    out = add_cyclical_encodings(df)
    assert out["dow_sin"].iloc[0] == pytest.approx(0.0, abs=1e-9)
    assert out["dow_cos"].iloc[0] == pytest.approx(1.0, abs=1e-9)


def test_add_promo_features_share_matches_manual_fraction():
    df = pd.DataFrame({"date": pd.to_datetime(["2026-01-01", "2026-01-02"]), "y": [10.0, 20.0]})
    raw = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-01-01", "2026-01-02"]),
            "total_lines": [4, 5],
            "promo_lines_p": [1, 0],
            "promo_lines_f": [0, 5],
            "promo_lines_a": [0, 0],
            "discount_amount": [10.0, 50.0],
            "gross_amount": [100.0, 100.0],
        }
    )
    out = add_promo_features(df, raw)
    assert out["promo_share_p"].iloc[0] == pytest.approx(0.25)
    assert out["promo_share_f"].iloc[1] == pytest.approx(1.0)
    assert out["discount_rate"].iloc[1] == pytest.approx(0.5)


def test_add_promo_features_none_regressors_returns_df_unchanged():
    df = pd.DataFrame({"date": pd.to_datetime(["2026-01-01"]), "y": [10.0]})
    out = add_promo_features(df, None)
    assert "promo_share_p" not in out.columns


def test_add_target_features_gap_and_flat_fallback():
    df = pd.DataFrame({"date": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"]), "y": [90.0, 100.0, 110.0]})
    target_series = pd.Series([100.0, 100.0], index=pd.to_datetime(["2026-01-01", "2026-01-02"]))
    out = add_target_features(df, target_series)
    # Jan-03 has no target -> flat trailing-average fallback (100.0 here).
    assert out["target_value"].iloc[2] == pytest.approx(100.0)
    # target_gap = target - y.shift(1); Jan-02's gap = target(Jan-02) - y(Jan-01)
    assert out["target_gap"].iloc[1] == pytest.approx(100.0 - 90.0)


def test_add_target_features_none_series():
    df = pd.DataFrame({"date": pd.to_datetime(["2026-01-01"]), "y": [10.0]})
    out = add_target_features(df, None)
    assert out["target_value"].iloc[0] == 0.0


def test_build_feature_matrix_drops_leading_undefined_rows():
    config = FeatureConfig(lags=(1, 7), rolling_windows=(7,))
    series_df = _series_df(20)
    X, y, names = build_feature_matrix(series_df, config)
    assert len(X) == 20 - 7  # max(lags + rolling_windows) == 7
    assert len(y) == len(X)
    assert "lag_1" in names and "roll_mean_7" in names


def test_build_feature_matrix_too_short_returns_empty():
    config = FeatureConfig(lags=(1, 7), rolling_windows=(7,))
    X, y, names = build_feature_matrix(_series_df(3), config)
    assert X.empty and y.empty and names == []


def test_build_feature_row_matches_build_feature_matrix_batch_computation():
    # Both must be run with promo/target features OFF -- build_feature_row never
    # emits them (no forward promo calendar / target is a flat guess), so parity
    # is only meaningful for the lag/rolling/calendar/cyclical columns they share.
    config = FeatureConfig(lags=(1, 7), rolling_windows=(7,), include_promo_features=False, include_target_features=False)
    series_df = _series_df(20)

    X, y, names = build_feature_matrix(series_df, config)
    batch_row = X.iloc[[-1]].reset_index(drop=True)

    history = series_df.iloc[:-1]
    next_date = series_df["date"].iloc[-1]
    recursive_row = build_feature_row(history, next_date, config).reset_index(drop=True)

    shared_cols = sorted(set(batch_row.columns) & set(recursive_row.columns))
    assert shared_cols  # sanity: some overlap must exist
    pd.testing.assert_frame_equal(
        batch_row[shared_cols].reset_index(drop=True),
        recursive_row[shared_cols].reset_index(drop=True),
        check_dtype=False,
    )


def test_build_feature_row_never_includes_promo_or_target_columns():
    config = FeatureConfig(lags=(1,), rolling_windows=(7,))
    series_df = _series_df(20)
    row = build_feature_row(series_df.iloc[:-1], series_df["date"].iloc[-1], config)
    assert not any(c.startswith(("promo_", "discount_rate", "target_")) for c in row.columns)
