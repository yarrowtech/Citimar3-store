"""Period bucketing / resampling shared across the Historical Analytics charts
and tables (Historical Analytics Overhaul, Part A).

Sibling of ``filter_engine`` / ``comparison_engine``. Works off a single
datetime64 ``date`` column only -- it never touches the derived calendar fields
``data_cleaner.add_derived_date_fields`` adds to the fact table, so it serves
the fact frame **and** the ``SALES TARGET`` / ``TIME WISE FOOTFALL-NOB`` frames
(which have no derived columns) with the same code path.

Two distinct groupings:

* ``period_start`` -> a *linear* time axis: consecutive Mondays, first-of-month,
  first-of-quarter, ... Used by ``resample_frame`` / ``per_period_kpi_table`` for
  "Net Sales per week over the selected range" style views.
* ``seasonal_key`` -> a *cyclic* bucket: Mon..Sun, Jan..Dec, Q1..Q4, ISO week #.
  Used by the "Average Sales by <period>" view, where every Monday in the range
  collapses into one bar.

Every function is NaT-safe: an unparseable / missing date flows through as
``NaT`` (linear) or is dropped (``resample_frame``), never raises.
"""
from __future__ import annotations

import pandas as pd

PERIODS: tuple[str, ...] = ("day", "week", "month", "quarter", "year")

# Kept local (not imported from src/charts.py) so this module has no plotly /
# config import chain -- charts.py can import these from here instead. The
# abbreviations match the fact table's ``day_name`` column and charts.py's own
# DAY_ORDER, so day-of-week grouping stays consistent whichever frame supplies
# the date.
WEEKDAY_TO_LABEL = {0: "Mon", 1: "Tues", 2: "Weds", 3: "Thurs", 4: "Fri", 5: "Sat", 6: "Sun"}
DAY_ORDER = ["Mon", "Tues", "Weds", "Thurs", "Fri", "Sat", "Sun"]
MONTH_ORDER = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]
QUARTER_ORDER = ["Q1", "Q2", "Q3", "Q4"]


def _validate(period: str) -> str:
    if period not in PERIODS:
        raise ValueError(f"Unknown period {period!r}; expected one of {PERIODS}")
    return period


def _as_datetime(values) -> pd.Series:
    """Coerce anything Series-like to a tz-naive datetime64 Series, bad values
    -> NaT. Accepts a scalar too (wrapped into a 1-element Series)."""
    if not isinstance(values, pd.Series):
        values = pd.Series(values if hasattr(values, "__iter__") and not isinstance(values, str) else [values])
    return pd.to_datetime(values, errors="coerce")


def period_start(dt, period: str) -> pd.Series:
    """The linear bucket anchor for each date: the Monday of its week, the
    first of its month/quarter/year, or the date itself for ``day``. NaT in ->
    NaT out (same length as the input)."""
    _validate(period)
    s = _as_datetime(dt)
    if period == "day":
        return s.dt.normalize()
    if period == "week":
        # Monday anchor. NaT.dayofweek is NaN -> to_timedelta(NaN) is NaT ->
        # normalize(NaT) - NaT stays NaT.
        offset = pd.to_timedelta(s.dt.dayofweek, unit="D")
        return s.dt.normalize() - offset
    freq = {"month": "M", "quarter": "Q", "year": "Y"}[period]
    return s.dt.to_period(freq).dt.start_time


def _label_one(ts, period: str) -> str:
    if ts is None or pd.isna(ts):
        return "Unknown"
    ts = pd.Timestamp(ts)
    if period == "day":
        return ts.strftime("%d %b %Y")
    if period == "week":
        return f"Wk of {ts.strftime('%d %b %Y')}"
    if period == "month":
        return ts.strftime("%b %Y")
    if period == "quarter":
        return f"Q{ts.quarter} {ts.year}"
    return str(ts.year)


def period_label(start, period: str):
    """Human label for a bucket anchor. Scalar in -> ``str``; Series in ->
    Series of ``str`` (aligned to the input index)."""
    _validate(period)
    if isinstance(start, pd.Series):
        return start.map(lambda t: _label_one(t, period))
    return _label_one(start, period)


def resample_frame(df: pd.DataFrame, period: str, *, date_col: str = "date", **named_aggs) -> pd.DataFrame:
    """Group ``df`` into linear ``period`` buckets and aggregate. ``named_aggs``
    is the usual pandas named-aggregation mapping, e.g.
    ``net_sales=("net_amount", "sum")``.

    Returns ``["Date", "period_start", *named_aggs]`` sorted ascending by
    ``period_start``, NaT buckets dropped. Empty / column-missing input ->
    an empty frame with those same columns so callers can rely on the shape.
    """
    _validate(period)
    out_cols = ["Date", "period_start", *named_aggs.keys()]
    if df.empty or date_col not in df.columns or not named_aggs:
        return pd.DataFrame(columns=out_cols)

    anchor = period_start(df[date_col], period).rename("period_start")
    grouped = df.groupby(anchor, dropna=True).agg(**named_aggs).reset_index()
    # reset_index() restores the grouper as the first column ("period_start");
    # the aggregates follow in named_aggs order. Pin the names explicitly.
    grouped.columns = ["period_start", *named_aggs.keys()]
    grouped = grouped.dropna(subset=["period_start"]).sort_values("period_start").reset_index(drop=True)
    grouped.insert(0, "Date", period_label(grouped["period_start"], period))
    return grouped


def seasonal_key(dt, period: str) -> tuple[pd.Series, list]:
    """The *cyclic* bucket for each date plus the category display order.
    ``day`` -> weekday abbreviation (Mon..Sun); ``week`` -> ISO week number;
    ``month`` -> month name; ``quarter`` -> "Q1".."Q4"; ``year`` -> year int.
    """
    _validate(period)
    s = _as_datetime(dt)
    if period == "day":
        keys = s.dt.dayofweek.map(WEEKDAY_TO_LABEL)
        return keys, list(DAY_ORDER)
    if period == "week":
        keys = s.dt.isocalendar().week.astype("Int64")
        order = sorted(int(w) for w in keys.dropna().unique())
        return keys, order
    if period == "month":
        keys = s.dt.month_name()
        return keys, list(MONTH_ORDER)
    if period == "quarter":
        keys = s.dt.quarter.map(lambda q: f"Q{int(q)}" if pd.notna(q) else pd.NA)
        return keys, list(QUARTER_ORDER)
    keys = s.dt.year.astype("Int64")
    order = sorted(int(y) for y in keys.dropna().unique())
    return keys, order
