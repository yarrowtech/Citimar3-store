"""Feature construction shared verbatim between batch training
(build_feature_matrix) and single-step recursive inference (build_feature_row),
so train/predict feature computation can never drift apart. Owns lag/rolling/
calendar/cyclical/promo/target features and the FeatureConfig dataclass.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from config.forecast_settings import FORECAST_LAG_FEATURES, FORECAST_ROLLING_WINDOWS, SEASONAL_PERIOD

# Columns build_feature_row must never emit: their "future" value is either
# unknowable (no forward promo calendar exists in the source data) or only a
# flat extrapolation (target beyond the last known SALES TARGET row) -- see
# add_promo_features/add_target_features docstrings.
_FUTURE_UNSAFE_PREFIXES = ("promo_", "discount_rate", "target_")


@dataclass
class FeatureConfig:
    lags: tuple[int, ...] = FORECAST_LAG_FEATURES
    rolling_windows: tuple[int, ...] = FORECAST_ROLLING_WINDOWS
    seasonal_period: int = SEASONAL_PERIOD
    include_promo_features: bool = True
    include_target_features: bool = True


def add_lag_features(df: pd.DataFrame, value_col: str, lags: tuple[int, ...]) -> pd.DataFrame:
    df = df.sort_values("date").reset_index(drop=True).copy()
    for k in lags:
        df[f"lag_{k}"] = df[value_col].shift(k)
    return df


def add_rolling_features(df: pd.DataFrame, value_col: str, windows: tuple[int, ...]) -> pd.DataFrame:
    df = df.sort_values("date").reset_index(drop=True).copy()
    shifted = df[value_col].shift(1)  # exclude the current row's own value from its own rolling stat
    for w in windows:
        df[f"roll_mean_{w}"] = shifted.rolling(w).mean()
        df[f"roll_std_{w}"] = shifted.rolling(w).std()
    return df


def add_calendar_features(df: pd.DataFrame, date_col: str = "date") -> pd.DataFrame:
    df = df.copy()
    dt = df[date_col]
    df["dow"] = dt.dt.dayofweek
    df["is_weekend"] = dt.dt.dayofweek.isin([5, 6]).astype(int)
    df["day_of_month"] = dt.dt.day
    df["month"] = dt.dt.month
    df["quarter"] = dt.dt.quarter
    df["is_month_start"] = dt.dt.is_month_start.astype(int)
    df["is_month_end"] = dt.dt.is_month_end.astype(int)
    return df


def add_cyclical_encodings(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "dow" not in df.columns or "month" not in df.columns or "day_of_month" not in df.columns:
        df = add_calendar_features(df)
    df["dow_sin"] = (2 * math.pi * df["dow"] / 7).apply(math.sin)
    df["dow_cos"] = (2 * math.pi * df["dow"] / 7).apply(math.cos)
    df["month_sin"] = (2 * math.pi * df["month"] / 12).apply(math.sin)
    df["month_cos"] = (2 * math.pi * df["month"] / 12).apply(math.cos)
    df["day_of_month_sin"] = (2 * math.pi * df["day_of_month"] / 30.44).apply(math.sin)
    df["day_of_month_cos"] = (2 * math.pi * df["day_of_month"] / 30.44).apply(math.cos)
    return df


def add_promo_features(df: pd.DataFrame, raw_regressors: pd.DataFrame | None) -> pd.DataFrame:
    """HISTORICAL ONLY: raw_regressors (from series_prep.build_daily_sales_series)
    only exists for dates already in DATASET.xlsx -- there is no forward promo
    calendar, so these columns are never populated for future dates. Callers
    building a future/recursive feature row must not include them (build_feature_row
    never calls this)."""
    df = df.copy()
    if raw_regressors is None or raw_regressors.empty:
        return df
    merged = df.merge(raw_regressors, on="date", how="left")
    total = merged["total_lines"].replace(0, pd.NA)
    merged["promo_share_p"] = (merged["promo_lines_p"] / total).astype("float64").fillna(0.0)
    merged["promo_share_f"] = (merged["promo_lines_f"] / total).astype("float64").fillna(0.0)
    merged["promo_share_a"] = (merged["promo_lines_a"] / total).astype("float64").fillna(0.0)
    gross = merged["gross_amount"].replace(0, pd.NA)
    merged["discount_rate"] = (merged["discount_amount"] / gross).astype("float64").fillna(0.0)
    return merged.drop(columns=["total_lines", "promo_lines_p", "promo_lines_f", "promo_lines_a", "discount_amount", "gross_amount"])


def add_target_features(df: pd.DataFrame, target_series: pd.Series | None) -> pd.DataFrame:
    """target_gap = target - y.shift(1) (yesterday's shortfall/surplus vs that
    day's target). Dates beyond the last known SALES TARGET row are filled with
    the trailing 28-day average target -- a flat, defensible extrapolation,
    never left NaN."""
    df = df.copy()
    if target_series is None or target_series.empty:
        df["target_value"] = 0.0
        df["target_gap"] = 0.0
        return df

    aligned = df["date"].map(target_series)
    trailing_avg = target_series.tail(28).mean()
    df["target_value"] = aligned.fillna(trailing_avg).astype("float64")
    df["target_gap"] = df["target_value"] - df["y"].shift(1)
    return df


def build_feature_matrix(
    series_df: pd.DataFrame,
    config: FeatureConfig,
    raw_regressors: pd.DataFrame | None = None,
    target_series: pd.Series | None = None,
) -> tuple[pd.DataFrame, pd.Series, list[str]]:
    min_rows = max((*config.lags, *config.rolling_windows, 1))
    if series_df.empty or len(series_df) <= min_rows:
        return pd.DataFrame(), pd.Series(dtype="float64"), []

    df = series_df.sort_values("date").reset_index(drop=True).copy()
    df = add_lag_features(df, "y", config.lags)
    df = add_rolling_features(df, "y", config.rolling_windows)
    df = add_calendar_features(df)
    df = add_cyclical_encodings(df)
    if config.include_promo_features:
        df = add_promo_features(df, raw_regressors)
    if config.include_target_features:
        df = add_target_features(df, target_series)

    df = df.iloc[min_rows:].reset_index(drop=True)
    feature_names = [c for c in df.columns if c not in ("date", "y")]
    return df[feature_names], df["y"], feature_names


def future_calendar_frame(last_date: pd.Timestamp, horizon: int) -> pd.DataFrame:
    """Calendar-only frame for the forecast horizon -- every column here is
    knowable arbitrarily far into the future, safe as SARIMAX exog."""
    dates = pd.date_range(last_date + pd.Timedelta(days=1), periods=horizon, freq="D")
    df = pd.DataFrame({"date": dates})
    df = add_calendar_features(df)
    df = add_cyclical_encodings(df)
    return df


def build_feature_row(history_df: pd.DataFrame, next_date: pd.Timestamp, config: FeatureConfig) -> pd.DataFrame:
    """Single-row feature builder used ONLY by the recursive multi-step ML loop.
    history_df must already contain next_date-1's actual-or-previously-predicted
    y, and must retain at least max(lags+rolling_windows) trailing rows.
    Delegates to the exact same helpers build_feature_matrix uses -- guarantees
    feature parity between training and recursive inference. Always excludes
    promo/target-gap columns (future values are unknown/flat-fallback by design,
    see _FUTURE_UNSAFE_PREFIXES)."""
    working = pd.concat(
        [history_df[["date", "y"]], pd.DataFrame({"date": [next_date], "y": [float("nan")]})],
        ignore_index=True,
    )
    working = add_lag_features(working, "y", config.lags)
    working = add_rolling_features(working, "y", config.rolling_windows)
    working = add_calendar_features(working)
    working = add_cyclical_encodings(working)

    last_row = working.iloc[[-1]].copy()
    feature_cols = [
        c for c in last_row.columns
        if c not in ("date", "y") and not c.startswith(_FUTURE_UNSAFE_PREFIXES)
    ]
    return last_row[feature_cols]
