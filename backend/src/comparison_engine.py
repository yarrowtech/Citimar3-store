"""Computes KPI-card deltas vs previous period / previous month / same period
last year / target (master prompt Section 11.3). Reuses kpi_engine so no
formula is duplicated between the "current" and "comparison" calculations.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, timedelta

import pandas as pd

from config.kpi_thresholds import delta_status
from src.kpi_engine import KpiBundle, compute_kpis

# KPIs where a rise is not automatically "good" (master prompt Section 11.3).
# remaining/remaining_pct: a bigger gap to target is worse.
LOWER_IS_BETTER = {"discounts", "returned_units", "returned_value", "remaining", "remaining_pct"}


@dataclass
class KpiDelta:
    kpi: str
    current: float | None
    previous: float | None
    absolute_variance: float | None
    percentage_variance: float | None
    status: str


def previous_period_window(start: date, end: date) -> tuple[date, date]:
    span = (end - start).days + 1
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=span - 1)
    return prev_start, prev_end


def previous_month_window(start: date, end: date) -> tuple[date, date]:
    first_of_month = start.replace(day=1)
    prev_month_end = first_of_month - timedelta(days=1)
    prev_month_start = prev_month_end.replace(day=1)
    days_selected = (end - start).days
    prev_end = min(prev_month_end, prev_month_start + timedelta(days=days_selected))
    return prev_month_start, prev_end


def same_period_last_year_window(start: date, end: date) -> tuple[date, date]:
    # start/end are clamped independently: if only one of them is a 29 Feb,
    # the other must not also be forced to day=28.
    try:
        prev_start = start.replace(year=start.year - 1)
    except ValueError:
        prev_start = start.replace(year=start.year - 1, day=28)
    try:
        prev_end = end.replace(year=end.year - 1)
    except ValueError:
        prev_end = end.replace(year=end.year - 1, day=28)
    return prev_start, prev_end


def _slice_by_date(df: pd.DataFrame, start: date, end: date, date_col: str = "date") -> pd.DataFrame:
    if df.empty or date_col not in df.columns:
        return df
    # See filter_engine._apply_store_date's comment: `.dt.date` boxes every
    # row into a Python object before comparing, which is expensive and,
    # here, paid 3x per /api/kpis request (once per comparison window) on
    # top of filter_engine's own call -- a vectorized datetime64 comparison
    # with a half-open upper bound is both faster and dtype-agnostic.
    dt = pd.to_datetime(df[date_col], errors="coerce")
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end) + pd.Timedelta(days=1)
    mask = (dt >= start_ts) & (dt < end_ts)
    return df.loc[mask]


def kpis_for_window(
    fact: pd.DataFrame, footfall: pd.DataFrame, target: pd.DataFrame, start: date, end: date
) -> KpiBundle:
    return compute_kpis(
        _slice_by_date(fact, start, end),
        _slice_by_date(footfall, start, end),
        _slice_by_date(target, start, end),
    )


def build_deltas(current: KpiBundle, previous: KpiBundle) -> dict[str, KpiDelta]:
    deltas: dict[str, KpiDelta] = {}
    current_dict = asdict(current)
    previous_dict = asdict(previous)
    for field_name, current_value in current_dict.items():
        if not isinstance(current_value, (int, float)) or field_name.endswith("_is_derived"):
            continue
        previous_value = previous_dict.get(field_name)
        abs_var = None
        pct_var = None
        if isinstance(previous_value, (int, float)):
            abs_var = current_value - previous_value
            pct_var = (abs_var / previous_value * 100) if previous_value not in (0, None) else None
        higher_is_better = field_name not in LOWER_IS_BETTER
        status = delta_status(current_value, previous_value, higher_is_better=higher_is_better)
        deltas[field_name] = KpiDelta(
            kpi=field_name,
            current=current_value,
            previous=previous_value,
            absolute_variance=abs_var,
            percentage_variance=pct_var,
            status=status,
        )
    return deltas
