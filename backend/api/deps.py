"""Shared FastAPI dependencies: dataset access and filter-parameter parsing.
The cleaned dataset is loaded once at app startup (see app.py's lifespan) and
stored on app.state -- request handlers never re-read the workbook.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from fastapi import Depends, HTTPException, Query, Request

from api.auth import CurrentUser, get_current_user
from config.forecast_settings import DEFAULT_HORIZON, FORECAST_HORIZON_CHOICES, PRIMARY_MODEL_ROSTER
from src.data_loader import MasterDataset
from src.filter_engine import FILTER_HIERARCHY, FilterState, dataset_date_bounds


def get_dataset(request: Request) -> MasterDataset:
    """The cleaned workbook, loaded in a background thread at startup (app.py's
    lifespan). Until that finishes, DATASET.xlsx-backed routes return 503 --
    login and Daily Operations (MongoDB) don't depend on this and work right
    away. A load failure is surfaced here too, not as a crashed process."""
    dataset: MasterDataset | None = getattr(request.app.state, "dataset", None)
    if dataset is None:
        error = getattr(request.app.state, "startup_error", None)
        raise HTTPException(
            status_code=503,
            detail=error or "Dataset is still loading; please retry in a few seconds.",
            headers={"Retry-After": "10"},
        )
    return dataset


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def _parse_csv(value: str | None) -> list[str] | None:
    if not value:
        return None
    items = [v.strip() for v in value.split(",") if v.strip()]
    return items or None


def _clamp_stores(requested: list[str] | None, allowed: list[str]) -> list[str]:
    """Turn a client-supplied store list into a server-enforced one: default to
    everything the caller may see, then drop anything outside that set. Empty
    result -> 403 (the caller asked only for stores they can't access)."""
    chosen = requested or list(allowed)
    scoped = [s for s in chosen if s in allowed]
    if not scoped:
        raise HTTPException(status_code=403, detail="No accessible stores in that selection.")
    return scoped


def parse_filter_state(
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    stores: str | None = Query(None, description="Comma-separated store codes, e.g. NM,HB"),
    start: str | None = Query(None, description="YYYY-MM-DD"),
    end: str | None = Query(None, description="YYYY-MM-DD"),
    time_slot: str | None = Query(None, description="Comma-separated time-slot bands, see TIME_SLOT_ORDER"),
    division: str | None = Query(None, description="Comma-separated division names"),
    section: str | None = Query(None, description="Comma-separated section names"),
    department: str | None = Query(None, description="Comma-separated department names"),
    product_design_no: str | None = Query(None, description="Comma-separated product design numbers"),
    product_style: str | None = Query(None, description="Comma-separated product styles"),
    product_type: str | None = Query(None, description="Comma-separated product types"),
    product_size: str | None = Query(None, description="Comma-separated product sizes"),
    vendors: str | None = Query(None, description="Comma-separated vendor names"),
) -> FilterState:
    dataset = get_dataset(request)
    default_start, default_end = dataset_date_bounds(dataset.fact)

    parsed_start = _parse_date(start) or default_start
    parsed_end = _parse_date(end) or default_end
    if parsed_start and parsed_end and parsed_start > parsed_end:
        parsed_start, parsed_end = parsed_end, parsed_start

    all_codes = sorted(dataset.fact["store_code"].dropna().unique().tolist()) if not dataset.fact.empty else []
    parsed_stores = _clamp_stores(_parse_csv(stores), user.allowed_stores(all_codes))

    assert FILTER_HIERARCHY == [
        "division", "section", "department",
        "product_design_no", "product_style", "product_type", "product_size", "vendors",
    ], "parse_filter_state's explicit params must stay in sync with FILTER_HIERARCHY"

    return FilterState(
        stores=parsed_stores,
        start_date=parsed_start,
        end_date=parsed_end,
        time_slot=_parse_csv(time_slot),
        division=_parse_csv(division),
        section=_parse_csv(section),
        department=_parse_csv(department),
        product_design_no=_parse_csv(product_design_no),
        product_style=_parse_csv(product_style),
        product_type=_parse_csv(product_type),
        product_size=_parse_csv(product_size),
        vendors=_parse_csv(vendors),
    )


@dataclass
class ForecastState:
    """Forecasting's own coarse scope -- a store list plus horizon/model roster.
    Deliberately NOT parse_filter_state/FilterState: forecasting never scopes by
    date-range or product-hierarchy (mirrors streamlit_forecast_app.py building its
    own sidebar instead of reusing src/filter_engine)."""

    stores: list[str]
    horizon: int
    models: list[str]


def parse_forecast_state(
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    stores: str | None = Query(None, description="Comma-separated store codes; empty/omitted = every store in the dataset"),
    horizon: int = Query(DEFAULT_HORIZON, description=f"one of {FORECAST_HORIZON_CHOICES}"),
    models: str | None = Query(None, description="Comma-separated model names; empty/omitted = full PRIMARY_MODEL_ROSTER"),
) -> ForecastState:
    dataset = get_dataset(request)
    all_codes = sorted(dataset.fact["store_code"].dropna().unique().tolist()) if not dataset.fact.empty else []
    parsed_stores = _clamp_stores(_parse_csv(stores), user.allowed_stores(all_codes))
    if horizon not in FORECAST_HORIZON_CHOICES:
        horizon = DEFAULT_HORIZON
    return ForecastState(stores=parsed_stores, horizon=horizon, models=_parse_csv(models) or PRIMARY_MODEL_ROSTER)
