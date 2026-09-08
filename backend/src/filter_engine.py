"""Cascading filter application (master prompt Section 9). Each filter level
narrows based on every level above it in FILTER_HIERARCHY; every filter
degrades gracefully to "no rows" instead of crashing when a combination has
no data.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from config.settings import FILTER_CHECKBOX_MAX_VALUES, TIME_SLOT_ORDER

# Order matters: each field's available options are computed from store+date
# plus every field listed *before* it here (Section 9: "options must update
# based on selected stores/date/higher filters"). The last five (product
# design no/style/type/size/vendors) are flat attributes of the same product
# row -- they all narrow off division/section/department but not off each
# other, so picking one doesn't hide options in the rest.
FILTER_HIERARCHY: list[str] = [
    "division",
    "section",
    "department",
    "product_design_no",
    "product_style",
    "product_type",
    "product_size",
    "vendors",
]


@dataclass
class FilterState:
    stores: list[str] | None = None  # store codes, e.g. ["NM", "HB"]
    start_date: date | None = None
    end_date: date | None = None
    time_slot: list[str] | None = None  # e.g. ["11.00 AM - 01.59 PM"], see TIME_SLOT_ORDER
    division: list[str] | None = None
    section: list[str] | None = None
    department: list[str] | None = None
    product_design_no: list[str] | None = None
    product_style: list[str] | None = None
    product_type: list[str] | None = None
    product_size: list[str] | None = None
    vendors: list[str] | None = None

    def get(self, field_name: str) -> list[str] | None:
        return getattr(self, field_name, None)


def dataset_date_bounds(df: pd.DataFrame) -> tuple[date | None, date | None]:
    if df.empty or "date" not in df.columns:
        return None, None
    dt = pd.to_datetime(df["date"], errors="coerce").dropna()
    if dt.empty:
        return None, None
    return dt.min().date(), dt.max().date()


def default_filter_state(df: pd.DataFrame) -> FilterState:
    start, end = dataset_date_bounds(df)
    stores = sorted(df["store_code"].dropna().unique().tolist()) if "store_code" in df.columns else []
    return FilterState(stores=stores, start_date=start, end_date=end)


def time_slot_options() -> list[str]:
    """The time-slot filter is a fixed 4-value facet (TIME_SLOT_ORDER), not
    data-driven/cascading like the product hierarchy fields, so it doesn't
    need an available_values()-style scoped lookup."""
    return list(TIME_SLOT_ORDER)


def _apply_store_date(df: pd.DataFrame, state: FilterState) -> pd.DataFrame:
    if df.empty:
        return df
    mask = pd.Series(True, index=df.index)
    if state.stores:
        mask &= df["store_code"].isin(state.stores)
    if state.start_date is not None and state.end_date is not None:
        # Vectorized datetime64 comparison, not `.dt.date` -- boxing every row
        # into a Python `date` object is O(n) Python-level overhead that
        # measured at ~160ms alone on the 354K-row fact table (most of
        # apply_filters' cost), on every single chart/KPI request. The
        # half-open upper bound (`end_date` + 1 day, `<` not `<=`) stays
        # correct even if a "date" column ever carries a time-of-day
        # component, without needing `.dt.date` to strip it.
        dt = pd.to_datetime(df["date"], errors="coerce")
        start_ts = pd.Timestamp(state.start_date)
        end_ts = pd.Timestamp(state.end_date) + pd.Timedelta(days=1)
        mask &= (dt >= start_ts) & (dt < end_ts)
    if state.time_slot and "time_slot" in df.columns:
        mask &= df["time_slot"].isin(state.time_slot)
    return df.loc[mask]


def filter_store_level_table(df: pd.DataFrame, state: FilterState) -> pd.DataFrame:
    """For SALES TARGET / TIME WISE FOOTFALL-NOB: store+date(+time slot where
    the sheet has that column -- footfall does, target doesn't) only. These
    sheets have no section/department/product granularity, so applying those
    filters here would either no-op or (if columns were ever added) silently
    duplicate/misattribute store-level figures across product filters."""
    return _apply_store_date(df, state)


def apply_filters(df: pd.DataFrame, state: FilterState) -> pd.DataFrame:
    """Full filter chain: store -> date -> every FILTER_HIERARCHY field."""
    if df.empty:
        return df
    filtered = _apply_store_date(df, state)
    for field_name in FILTER_HIERARCHY:
        selected = state.get(field_name)
        if selected and field_name in filtered.columns:
            filtered = filtered.loc[filtered[field_name].isin(selected)]
    return filtered


def available_values(df: pd.DataFrame, state: FilterState, field_name: str) -> list[str]:
    """Available values for `field_name`, scoped by store+date plus every
    FILTER_HIERARCHY field *before* it (Section 9.3/9.4's cascading rule
    generalised to the full product hierarchy)."""
    if df.empty or field_name not in df.columns:
        return []
    scoped = _apply_store_date(df, state)
    for higher_field in FILTER_HIERARCHY:
        if higher_field == field_name:
            break
        selected = state.get(higher_field)
        if selected and higher_field in scoped.columns:
            scoped = scoped.loc[scoped[higher_field].isin(selected)]
    values = scoped[field_name].dropna().unique().tolist()
    return sorted(str(v) for v in values if str(v).strip())


def available_sections(df: pd.DataFrame, state: FilterState) -> list[str]:
    return available_values(df, state, "section")


def available_departments(df: pd.DataFrame, state: FilterState) -> list[str]:
    return available_values(df, state, "department")


def section_filter_widget(df: pd.DataFrame, state: FilterState) -> str:
    """Per Section 9.3: checkboxes up to FILTER_CHECKBOX_MAX_VALUES unique
    values, otherwise a searchable multiselect."""
    n = len(available_sections(df, state))
    return "checkbox" if n <= FILTER_CHECKBOX_MAX_VALUES else "searchable_multiselect"


def reset_unavailable_selections(selected: list[str] | None, available: list[str]) -> list[str] | None:
    """Preserve valid selections when other filters change; drop selections
    that are no longer in the available set instead of crashing."""
    if not selected:
        return selected
    available_set = set(available)
    kept = [s for s in selected if s in available_set]
    return kept or None
