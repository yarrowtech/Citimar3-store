"""Forecasting control-plane routes: cache status checks, the one slow
"compute" trigger per series kind, and small derived-arithmetic endpoints
(growth goal, overview). Mirrors streamlit_forecast_app.py's cached_result/
cached_result_with_button pattern via src/forecasting/cache.py, but every
kind here is button-gated uniformly (see the plan doc for why): /status
NEVER computes, only /compute does, and the frontend only ever calls
/compute from an explicit user-triggered mutation, never an auto-fetching
query.
"""
from __future__ import annotations

import math
from datetime import timedelta

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query

from config.forecast_settings import (
    DEFAULT_HORIZON,
    FORECAST_HORIZON_CHOICES,
    MIN_HISTORY_DAYS_FOR_FORECAST,
    PRIMARY_MODEL_ROSTER,
    PRODUCT_FORECAST_LEVELS,
    PRODUCT_VENDOR_MODEL_ROSTER,
    TOP_N_PRODUCTS,
    TOP_N_PROMO_CAMPAIGNS,
    TOP_N_VENDORS,
)
from config.settings import STORE_CODE_TO_NAME, TIME_SLOT_ORDER
from src.comparison_engine import build_deltas, kpis_for_window, previous_period_window
from src.data_loader import MasterDataset
from src.forecasting.cache import forecast_cache_key, load_cached_forecast, save_forecast_cache
from src.forecasting.orchestrator import (
    ForecastBundle,
    forecast_daily_sales,
    forecast_footfall_nob,
    forecast_products,
    forecast_vendors,
    growth_trajectory_needed,
)
from src.forecasting.series_prep import build_target_aligned_series, daily_sales_series_id, footfall_nob_series_id
from src.tables import performer_pairing_table

from .deps import ForecastState, get_dataset, parse_forecast_state
from .forecast_support import bundle_status, bundles_status, scope_to_stores, series_identity


def _json_safe(value):
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if pd.isna(value):
        return None
    return value


def _records(df: pd.DataFrame) -> list[dict]:
    if df.empty:
        return []
    records = df.to_dict(orient="records")
    return [{k: _json_safe(v) for k, v in row.items()} for row in records]

router = APIRouter(prefix="/api/forecast", tags=["forecast"])
_VALID_KINDS = {"sales", "footfall", "products", "vendors"}


@router.get("/meta")
def get_forecast_meta(dataset: MasterDataset = Depends(get_dataset)):
    active_stores = sorted(dataset.fact["store_code"].dropna().unique().tolist()) if "store_code" in dataset.fact.columns else []
    return {
        "horizon_choices": FORECAST_HORIZON_CHOICES,
        "default_horizon": DEFAULT_HORIZON,
        "primary_model_roster": PRIMARY_MODEL_ROSTER,
        "product_vendor_model_roster": PRODUCT_VENDOR_MODEL_ROSTER,
        "product_forecast_levels": PRODUCT_FORECAST_LEVELS,
        "top_n_products_default": TOP_N_PRODUCTS,
        "top_n_vendors_default": TOP_N_VENDORS,
        "top_n_promo_campaigns_default": TOP_N_PROMO_CAMPAIGNS,
        "min_history_days": MIN_HISTORY_DAYS_FOR_FORECAST,
        "time_slot_order": TIME_SLOT_ORDER,
        "active_stores": active_stores,
        "store_names": {code: STORE_CODE_TO_NAME.get(code, code) for code in active_stores},
    }


def _resolve_kind_or_404(kind: str) -> None:
    if kind not in _VALID_KINDS:
        raise HTTPException(status_code=404, detail=f"Unknown forecast kind: {kind}")


def _compute_bundle(kind: str, dataset: MasterDataset, state: ForecastState, store: str | None, time_slot: str | None, metric: str, level: str, top_n: int):
    if kind == "sales":
        scoped_fact = scope_to_stores(dataset.fact, state.stores)
        scoped_target = scope_to_stores(dataset.target, state.stores)
        return forecast_daily_sales(scoped_fact, scoped_target, store, state.horizon, model_set=state.models)
    if kind == "footfall":
        return forecast_footfall_nob(dataset.footfall, store or "", time_slot, metric, state.horizon, model_set=state.models)
    scoped_fact = scope_to_stores(dataset.fact, state.stores)
    if kind == "products":
        return forecast_products(scoped_fact, level, state.horizon, top_n=top_n, model_set=state.models)
    return forecast_vendors(scoped_fact, state.horizon, top_n=top_n, model_set=state.models)


def _status_payload(kind: str, cached, state: ForecastState) -> dict:
    if kind in ("products", "vendors"):
        return bundles_status(cached)
    return bundle_status(cached, state.models)


@router.get("/{kind}/status")
def get_forecast_status(
    kind: str,
    dataset: MasterDataset = Depends(get_dataset),
    state: ForecastState = Depends(parse_forecast_state),
    store: str | None = Query(None, description="Required for kind=footfall; optional single store for kind=sales (omitted = All Stores)"),
    time_slot: str | None = Query(None, description="kind=footfall only; omitted = all slots summed"),
    metric: str = Query("footfall", description="kind=footfall only: footfall|nob"),
    level: str = Query("product_style", description="kind=products only: product_style|department"),
    top_n: int = Query(20, ge=5, le=30, description="kind=products|vendors only"),
):
    _resolve_kind_or_404(kind)
    series_id = series_identity(kind, state, store, time_slot, metric, level, top_n)
    key = forecast_cache_key(series_id, state.horizon, tuple(sorted(state.models)))
    cached = load_cached_forecast(key, dataset.source_mtime)
    return _status_payload(kind, cached, state)


@router.get("/{kind}/compute")
def compute_forecast(
    kind: str,
    dataset: MasterDataset = Depends(get_dataset),
    state: ForecastState = Depends(parse_forecast_state),
    store: str | None = Query(None),
    time_slot: str | None = Query(None),
    metric: str = Query("footfall"),
    level: str = Query("product_style"),
    top_n: int = Query(20, ge=5, le=30),
):
    """The only slow endpoint in the app -- trains/backtests every requested
    model for this series (or, for products/vendors, top_n+1 independent
    series). Never called automatically by the frontend, only via an
    explicit user-triggered mutation."""
    _resolve_kind_or_404(kind)
    series_id = series_identity(kind, state, store, time_slot, metric, level, top_n)
    key = forecast_cache_key(series_id, state.horizon, tuple(sorted(state.models)))
    result = _compute_bundle(kind, dataset, state, store, time_slot, metric, level, top_n)
    save_forecast_cache(key, result, dataset.source_mtime)
    return _status_payload(kind, result, state)


@router.get("/sales/growth-goal")
def get_growth_goal(
    dataset: MasterDataset = Depends(get_dataset),
    state: ForecastState = Depends(parse_forecast_state),
    store: str | None = Query(None),
    target_total: float | None = Query(None, description="Override; omitted = trailing daily SALES TARGET x horizon"),
):
    series_id = daily_sales_series_id(store)
    key = forecast_cache_key(series_id, state.horizon, tuple(sorted(state.models)))
    bundle: ForecastBundle | None = load_cached_forecast(key, dataset.source_mtime)
    if bundle is None or bundle.insufficient_history:
        return {"computed": False}

    scoped_target = scope_to_stores(dataset.target, state.stores)
    target_series = build_target_aligned_series(scoped_target, store_code=store)
    default_daily_target = float(target_series.tail(28).mean()) if not target_series.empty else 0.0
    default_target_total = default_daily_target * state.horizon
    resolved_target_total = target_total if target_total is not None else default_target_total

    recent_avg_daily = float(bundle.history["y"].tail(28).mean()) if not bundle.history.empty else 0.0
    goal = growth_trajectory_needed(recent_avg_daily, resolved_target_total, state.horizon)
    return {"computed": True, "default_target_total": default_target_total, "target_total": resolved_target_total, **goal}


@router.get("/overview")
def get_forecast_overview(
    dataset: MasterDataset = Depends(get_dataset),
    state: ForecastState = Depends(parse_forecast_state),
    sales_store: str | None = Query(None),
    footfall_store: str | None = Query(None),
    footfall_time_slot: str | None = Query(None),
    footfall_metric: str = Query("footfall"),
):
    model_set_tuple = tuple(sorted(state.models))
    sales_key = forecast_cache_key(daily_sales_series_id(sales_store), state.horizon, model_set_tuple)
    sales_bundle: ForecastBundle | None = load_cached_forecast(sales_key, dataset.source_mtime)

    footfall_bundle: ForecastBundle | None = None
    if footfall_store:
        footfall_key = forecast_cache_key(
            footfall_nob_series_id(footfall_store, footfall_time_slot, footfall_metric), state.horizon, model_set_tuple
        )
        footfall_bundle = load_cached_forecast(footfall_key, dataset.source_mtime)

    footfall_computed = bool(footfall_bundle and not footfall_bundle.insufficient_history)
    if sales_bundle is None or sales_bundle.insufficient_history:
        return {"sales_computed": False, "footfall_computed": footfall_computed}

    total_forecast = float(sales_bundle.forecast["point"].sum())
    total_lower = float(sales_bundle.forecast["lower"].sum())
    total_upper = float(sales_bundle.forecast["upper"].sum())
    recent_avg_daily = float(sales_bundle.history["y"].tail(28).mean()) if not sales_bundle.history.empty else 0.0
    flat_continuation = recent_avg_daily * state.horizon

    summary = []
    for bundle in (sales_bundle, footfall_bundle if footfall_computed else None):
        if bundle is None or bundle.leaderboard.empty:
            continue
        best_row = bundle.leaderboard.loc[bundle.leaderboard["model"] == bundle.best_model]
        mape = float(best_row["mean_mape"].iloc[0]) if not best_row.empty and pd.notna(best_row["mean_mape"].iloc[0]) else None
        summary.append({"series": bundle.label, "best_model": bundle.best_model, "backtest_mape": mape})

    return {
        "sales_computed": True,
        "footfall_computed": footfall_computed,
        "horizon": state.horizon,
        "flat_continuation": flat_continuation,
        "model_forecast_total": total_forecast,
        "confidence_lower": total_lower,
        "confidence_upper": total_upper,
        "delta_vs_flat": total_forecast - flat_continuation,
        "model_selection_summary": summary,
    }


@router.get("/huddle")
def get_daily_huddle(
    dataset: MasterDataset = Depends(get_dataset),
    state: ForecastState = Depends(parse_forecast_state),
    sales_store: str | None = Query(None, description="Single store to brief on; omitted = all active stores combined"),
    engagement_window_days: int = Query(7, ge=1, le=30),
):
    """Read-only morning-huddle briefing: today's target (configured + model
    next-day forecast), an engagement trend, and upsell/cross-sell pairs from
    performer_pairing_table. Only reads the sales-forecast cache -- like
    /overview, this never triggers a compute (see module docstring)."""
    model_set_tuple = tuple(sorted(state.models))
    sales_key = forecast_cache_key(daily_sales_series_id(sales_store), state.horizon, model_set_tuple)
    sales_bundle: ForecastBundle | None = load_cached_forecast(sales_key, dataset.source_mtime)

    if sales_bundle is None or sales_bundle.insufficient_history or sales_bundle.forecast.empty:
        return {"computed": False}

    store_scope = [sales_store] if sales_store else state.stores
    scoped_fact = scope_to_stores(dataset.fact, store_scope)
    scoped_footfall = scope_to_stores(dataset.footfall, store_scope)
    scoped_target = scope_to_stores(dataset.target, store_scope)

    next_row = sales_bundle.forecast.iloc[0]
    next_day_target = {
        "date": pd.Timestamp(next_row["date"]).date().isoformat(),
        "point": float(next_row["point"]),
        "lower": float(next_row["lower"]),
        "upper": float(next_row["upper"]),
    }

    target_series = build_target_aligned_series(scoped_target, store_code=sales_store)
    configured_daily_target = float(target_series.tail(28).mean()) if not target_series.empty else None

    engagement = None
    if "date" in scoped_fact.columns and not scoped_fact["date"].dropna().empty:
        last_date = pd.to_datetime(scoped_fact["date"]).max().date()
        window_start = last_date - timedelta(days=engagement_window_days - 1)
        prev_start, prev_end = previous_period_window(window_start, last_date)
        current = kpis_for_window(scoped_fact, scoped_footfall, scoped_target, window_start, last_date)
        previous = kpis_for_window(scoped_fact, scoped_footfall, scoped_target, prev_start, prev_end)
        deltas = build_deltas(current, previous)
        engagement = {
            "window_days": engagement_window_days,
            "conversion_pct": current.conversion_pct,
            "conversion_pct_delta": deltas["conversion_pct"].absolute_variance if "conversion_pct" in deltas else None,
            "footfall": current.footfall,
            "footfall_delta": deltas["footfall"].absolute_variance if "footfall" in deltas else None,
        }

    pairing = performer_pairing_table(scoped_fact, top_n=5)

    return {
        "computed": True,
        "next_day_target": next_day_target,
        "configured_daily_target": configured_daily_target,
        "engagement": engagement,
        "upsell_cross_sell": _records(pairing),
    }
