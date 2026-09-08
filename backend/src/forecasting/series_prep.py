"""Turns already-filtered fact/footfall/target DataFrames into the canonical
(date, y) series shape every other src/forecasting module consumes. This is
the only forecasting module allowed to know the real fact/footfall/target
column names -- everything downstream (feature_engineering, model_registry,
backtesting) just sees 'date'/'y'.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from config.forecast_settings import OTHER_BUCKET_LABEL


@dataclass
class SeriesFrame:
    series_id: str  # e.g. "daily_sales|store=ALL", "footfall|store=NM|slot=11.00 AM - 01.59 PM"
    label: str  # human-readable, for chart titles/legends
    df: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=["date", "y"]))  # date (daily freq, no gaps), y (float)
    raw_regressors: pd.DataFrame | None = None  # promo/discount columns aligned to date, for feature_engineering.add_promo_features


def _empty_series_frame(series_id: str, label: str) -> SeriesFrame:
    return SeriesFrame(series_id=series_id, label=label, df=pd.DataFrame(columns=["date", "y"]))


def daily_sales_series_id(store_code: str | None) -> str:
    """Single source of truth for this series kind's id, so callers (the
    Streamlit cache layer) can compute the same cache key build_daily_sales_series
    will produce WITHOUT re-running the (comparatively expensive) aggregation --
    used to check the on-disk forecast cache before doing any real work."""
    return f"daily_sales|store={store_code or 'ALL'}"


def footfall_nob_series_id(store_code: str, time_slot: str | None, value_col: str) -> str:
    return f"{value_col}|store={store_code}|slot={time_slot or 'ALL'}"


def _zero_fill_daily(df: pd.DataFrame, date_col: str = "date", value_col: str = "y") -> pd.DataFrame:
    """Reindexes df to a full daily date_range(min, max) and fills any gap
    with 0.0 -- a day with no matching rows in a daily retail export is a
    real zero-activity day, not missing data."""
    if df.empty:
        return df
    full_range = pd.date_range(df[date_col].min(), df[date_col].max(), freq="D")
    reindexed = df.set_index(date_col).reindex(full_range)
    reindexed[value_col] = reindexed[value_col].fillna(0.0)
    reindexed.index.name = date_col
    return reindexed.reset_index()


def build_daily_sales_series(fact: pd.DataFrame, store_code: str | None = None) -> SeriesFrame:
    label = f"Daily Net Sales — {store_code}" if store_code else "Daily Net Sales — All Stores"
    series_id = daily_sales_series_id(store_code)
    if fact.empty or "date" not in fact.columns or "net_amount" not in fact.columns:
        return _empty_series_frame(series_id, label)

    scoped = fact
    if store_code is not None and "store_code" in fact.columns:
        scoped = scoped.loc[scoped["store_code"] == store_code]
    if scoped.empty:
        return _empty_series_frame(series_id, label)

    daily = scoped.groupby(scoped["date"].dt.normalize())["net_amount"].sum().reset_index()
    daily.columns = ["date", "y"]
    daily = _zero_fill_daily(daily)

    raw_regressors = None
    if {"promo_type", "discount_amount", "gross_amount"}.issubset(scoped.columns):
        grouped = scoped.groupby(scoped["date"].dt.normalize())
        raw_regressors = grouped.apply(
            lambda g: pd.Series(
                {
                    "total_lines": len(g),
                    "promo_lines_p": (g["promo_type"] == "P").sum(),
                    "promo_lines_f": (g["promo_type"] == "F").sum(),
                    "promo_lines_a": (g["promo_type"] == "A").sum(),
                    "discount_amount": g["discount_amount"].sum(),
                    "gross_amount": g["gross_amount"].sum(),
                }
            ),
            include_groups=False,
        ).reset_index()
        raw_regressors.columns = [
            "date", "total_lines", "promo_lines_p", "promo_lines_f", "promo_lines_a",
            "discount_amount", "gross_amount",
        ]

    return SeriesFrame(series_id=series_id, label=label, df=daily, raw_regressors=raw_regressors)


def build_footfall_nob_series(
    footfall: pd.DataFrame,
    store_code: str,
    time_slot: str | None,
    value_col: str = "footfall",
) -> SeriesFrame:
    slot_label = time_slot if time_slot else "All Time Slots"
    label = f"{value_col.upper() if value_col == 'nob' else value_col.title()} — {store_code} — {slot_label}"
    series_id = footfall_nob_series_id(store_code, time_slot, value_col)
    required = {"date", "time_slot", value_col, "store_code"}
    if footfall.empty or not required.issubset(footfall.columns):
        return _empty_series_frame(series_id, label)

    scoped = footfall.loc[footfall["store_code"] == store_code]
    if time_slot is not None:
        scoped = scoped.loc[scoped["time_slot"] == time_slot]
    if scoped.empty:
        return _empty_series_frame(series_id, label)

    daily = scoped.groupby(scoped["date"].dt.normalize())[value_col].sum().reset_index()
    daily.columns = ["date", "y"]
    before_fill = len(daily)
    daily = _zero_fill_daily(daily)
    if len(daily) != before_fill:
        import logging

        logging.getLogger(__name__).warning(
            "build_footfall_nob_series: %d gap day(s) zero-filled for series_id=%s "
            "(TIME WISE FOOTFALL-NOB is expected to be gapless -- check the source workbook)",
            len(daily) - before_fill,
            series_id,
        )

    return SeriesFrame(series_id=series_id, label=label, df=daily)


def build_target_aligned_series(target: pd.DataFrame, store_code: str | None = None) -> pd.Series:
    if target.empty or "date" not in target.columns or "target" not in target.columns:
        return pd.Series(dtype="float64", name="target")

    scoped = target
    if store_code is not None and "store_code" in target.columns:
        scoped = scoped.loc[scoped["store_code"] == store_code]
    if scoped.empty:
        return pd.Series(dtype="float64", name="target")

    daily = scoped.groupby(scoped["date"].dt.normalize())["target"].sum()
    daily.name = "target"
    daily.index.name = "date"
    return daily


def top_n_entity_series(
    fact: pd.DataFrame,
    entity_col: str,
    top_n: int,
    other_label: str = OTHER_BUCKET_LABEL,
) -> dict[str, SeriesFrame]:
    if fact.empty or entity_col not in fact.columns or "net_amount" not in fact.columns or "date" not in fact.columns:
        return {}

    scoped = fact.loc[fact[entity_col].notna()]
    if scoped.empty:
        return {}

    totals = scoped.groupby(entity_col)["net_amount"].sum()
    # Deterministic ranking: total descending, entity name ascending as tiebreak.
    ranked = totals.reset_index().sort_values(by=["net_amount", entity_col], ascending=[False, True])
    top_entities = ranked[entity_col].head(top_n).tolist()
    other_entities = ranked[entity_col].iloc[top_n:].tolist()

    result: dict[str, SeriesFrame] = {}
    for entity in top_entities:
        entity_rows = scoped.loc[scoped[entity_col] == entity]
        daily = entity_rows.groupby(entity_rows["date"].dt.normalize())["net_amount"].sum().reset_index()
        daily.columns = ["date", "y"]
        daily = _zero_fill_daily(daily)
        series_id = f"{entity_col}|entity={entity}"
        result[str(entity)] = SeriesFrame(series_id=series_id, label=str(entity), df=daily)

    if other_entities:
        other_rows = scoped.loc[scoped[entity_col].isin(other_entities)]
        daily = other_rows.groupby(other_rows["date"].dt.normalize())["net_amount"].sum().reset_index()
        daily.columns = ["date", "y"]
        daily = _zero_fill_daily(daily)
        series_id = f"{entity_col}|entity={other_label}"
        result[other_label] = SeriesFrame(series_id=series_id, label=other_label, df=daily)

    return result
