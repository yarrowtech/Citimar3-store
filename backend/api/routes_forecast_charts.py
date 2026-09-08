"""GET /api/forecast-charts/{chart_id} -- mirrors api/routes_charts.py's
dispatcher-by-id pattern exactly, but reads exclusively from the forecast
disk cache (src/forecasting/cache.py) rather than computing anything. A
chart for a not-yet-computed series degrades to src.charts._empty_figure
(the same helper src/forecasting/charts.py already imports) -- never an
exception, matching the rest of this codebase's "missing data is not an
error" contract. Only an unrecognized chart_id raises 404.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from src.charts import _empty_figure
from src.data_loader import MasterDataset
from src.theme import apply_theme
from src.forecasting import charts as fcharts
from src.forecasting import promo_effectiveness
from src.forecasting.cache import forecast_cache_key, load_cached_forecast
from src.forecasting.orchestrator import ForecastBundle, growth_trajectory_needed
from src.forecasting.series_prep import build_target_aligned_series

from .deps import ForecastState, get_dataset, parse_forecast_state
from .forecast_support import scope_to_stores, series_identity

router = APIRouter(prefix="/api/forecast-charts", tags=["forecast-charts"])


def _load_bundle(dataset: MasterDataset, kind: str, state: ForecastState, **kwargs) -> ForecastBundle | None:
    key = forecast_cache_key(series_identity(kind, state, **kwargs), state.horizon, tuple(sorted(state.models)))
    return load_cached_forecast(key, dataset.source_mtime)


def _load_bundles(dataset: MasterDataset, kind: str, state: ForecastState, **kwargs) -> dict[str, ForecastBundle] | None:
    key = forecast_cache_key(series_identity(kind, state, **kwargs), state.horizon, tuple(sorted(state.models)))
    return load_cached_forecast(key, dataset.source_mtime)


@router.get("/{chart_id}")
def get_forecast_chart(
    chart_id: str,
    dataset: MasterDataset = Depends(get_dataset),
    state: ForecastState = Depends(parse_forecast_state),
    store: str | None = Query(None),
    time_slot: str | None = Query(None),
    metric: str = Query("footfall"),
    level: str = Query("product_style"),
    top_n: int = Query(20, ge=5, le=30),
    entity: str | None = Query(None, description="products/vendors drilldown ids only"),
    series_kind: str = Query("sales", description="backtest-actual-vs-predicted only: sales|footfall"),
    model: str | None = Query(None, description="backtest-actual-vs-predicted only"),
    target_total: float | None = Query(None, description="sales-growth-trajectory only"),
    theme: str | None = Query(None, description="Render hint: 'neon' recolours the figure; anything else is unchanged"),
):
    return apply_theme(
        _dispatch_forecast_chart(
            chart_id, dataset, state,
            store=store, time_slot=time_slot, metric=metric, level=level, top_n=top_n,
            entity=entity, series_kind=series_kind, model=model, target_total=target_total,
        ),
        theme,
    )


def _dispatch_forecast_chart(
    chart_id: str,
    dataset: MasterDataset,
    state: ForecastState,
    *,
    store: str | None,
    time_slot: str | None,
    metric: str,
    level: str,
    top_n: int,
    entity: str | None,
    series_kind: str,
    model: str | None,
    target_total: float | None,
) -> dict:
    if chart_id == "sales-line":
        bundle = _load_bundle(dataset, "sales", state, store=store)
        title = f"{bundle.label} — {state.horizon}-Day Forecast" if bundle else "Sales Forecast"
        if bundle is None or bundle.insufficient_history:
            return _empty_figure(title)
        return fcharts.forecast_line_chart(bundle.history, bundle.forecast, title, "Net Sales")

    if chart_id == "sales-leaderboard":
        bundle = _load_bundle(dataset, "sales", state, store=store)
        if bundle is None:
            return _empty_figure("Model Leaderboard (MAPE)")
        return fcharts.leaderboard_chart(bundle.leaderboard, "mape")

    if chart_id == "sales-growth-trajectory":
        bundle = _load_bundle(dataset, "sales", state, store=store)
        if bundle is None or bundle.insufficient_history:
            return _empty_figure("Current Pace vs Required Pace")
        scoped_target = scope_to_stores(dataset.target, state.stores)
        target_series = build_target_aligned_series(scoped_target, store_code=store)
        default_daily_target = float(target_series.tail(28).mean()) if not target_series.empty else 0.0
        resolved_target_total = target_total if target_total is not None else default_daily_target * state.horizon
        recent_avg_daily = float(bundle.history["y"].tail(28).mean()) if not bundle.history.empty else 0.0
        goal = growth_trajectory_needed(recent_avg_daily, resolved_target_total, state.horizon)
        return fcharts.growth_trajectory_chart(goal["current_avg_daily"], goal["required_avg_daily"], resolved_target_total)

    if chart_id == "footfall-line":
        bundle = _load_bundle(dataset, "footfall", state, store=store, time_slot=time_slot, metric=metric)
        title = f"{bundle.label} — {state.horizon}-Day Forecast" if bundle else "Footfall/NOB Forecast"
        y_label = "Number of Bills" if metric == "nob" else "Footfall Count"
        if bundle is None or bundle.insufficient_history:
            return _empty_figure(title)
        return fcharts.forecast_line_chart(bundle.history, bundle.forecast, title, y_label)

    if chart_id == "footfall-leaderboard":
        bundle = _load_bundle(dataset, "footfall", state, store=store, time_slot=time_slot, metric=metric)
        if bundle is None:
            return _empty_figure("Model Leaderboard (MAPE)")
        return fcharts.leaderboard_chart(bundle.leaderboard, "mape")

    if chart_id == "backtest-actual-vs-predicted":
        if series_kind == "footfall":
            bundle = _load_bundle(dataset, "footfall", state, store=store, time_slot=time_slot, metric=metric)
        else:
            bundle = _load_bundle(dataset, "sales", state, store=store)
        if bundle is None or not model or model not in bundle.backtest_results:
            return _empty_figure("Backtest: Actual vs Predicted", "No successful backtest folds to display")
        return fcharts.backtest_actual_vs_predicted_chart(bundle.backtest_results[model].fold_scores)

    if chart_id == "products-topn-bar":
        bundles = _load_bundles(dataset, "products", state, level=level, top_n=top_n)
        title = f"Top {top_n} {level.replace('_', ' ').title()}s — {state.horizon}-Day Forecast Total"
        if not bundles:
            return _empty_figure(title)
        return fcharts.topn_forecast_bar_chart(bundles, title)

    if chart_id in ("products-drilldown-line", "products-drilldown-leaderboard"):
        bundles = _load_bundles(dataset, "products", state, level=level, top_n=top_n)
        entity_bundle = bundles.get(entity) if bundles and entity else None
        if entity_bundle is None or entity_bundle.insufficient_history:
            title = f"{entity} — {state.horizon}-Day Forecast" if entity else "Forecast"
            return _empty_figure(title)
        if chart_id == "products-drilldown-line":
            return fcharts.forecast_line_chart(entity_bundle.history, entity_bundle.forecast, f"{entity_bundle.label} — {state.horizon}-Day Forecast", "Net Sales")
        return fcharts.leaderboard_chart(entity_bundle.leaderboard, "wape")

    if chart_id == "vendors-topn-bar":
        bundles = _load_bundles(dataset, "vendors", state, top_n=top_n)
        title = f"Top {top_n} Vendors — {state.horizon}-Day Forecast Total"
        if not bundles:
            return _empty_figure(title)
        return fcharts.topn_forecast_bar_chart(bundles, title)

    if chart_id in ("vendors-drilldown-line", "vendors-drilldown-leaderboard"):
        bundles = _load_bundles(dataset, "vendors", state, top_n=top_n)
        entity_bundle = bundles.get(entity) if bundles and entity else None
        if entity_bundle is None or entity_bundle.insufficient_history:
            title = f"{entity} — {state.horizon}-Day Forecast" if entity else "Forecast"
            return _empty_figure(title)
        if chart_id == "vendors-drilldown-line":
            return fcharts.forecast_line_chart(entity_bundle.history, entity_bundle.forecast, f"{entity_bundle.label} — {state.horizon}-Day Forecast", "Net Sales")
        return fcharts.leaderboard_chart(entity_bundle.leaderboard, "wape")

    if chart_id == "promo-uplift":
        scoped_fact = scope_to_stores(dataset.fact, state.stores)
        table = promo_effectiveness.promo_uplift_table(scoped_fact)
        return fcharts.promo_uplift_chart(table)

    raise HTTPException(status_code=404, detail=f"Unknown forecast chart_id: {chart_id}")
