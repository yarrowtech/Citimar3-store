"""GET /api/forecast-tables/{table_id} -- mirrors api/routes_tables.py's
dispatcher-by-id + format=json|csv pattern exactly, reading exclusively from
the forecast disk cache. "Not computed yet" degrades to an empty DataFrame
(-> {"table_id":..., "columns":[], "rows":[]} in JSON mode, a valid empty
CSV in CSV mode) -- never an exception. Only an unrecognized table_id 404s.
"""
from __future__ import annotations

import math

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, Response

from src import tables
from src.data_loader import MasterDataset
from src.forecasting import promo_effectiveness
from src.forecasting.cache import forecast_cache_key, load_cached_forecast
from src.forecasting.orchestrator import ForecastBundle

from .deps import ForecastState, get_dataset, parse_forecast_state
from .forecast_support import scope_to_stores, series_identity, topn_summary_table

router = APIRouter(prefix="/api/forecast-tables", tags=["forecast-tables"])


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


def _load_bundle(dataset: MasterDataset, kind: str, state: ForecastState, **kwargs) -> ForecastBundle | None:
    key = forecast_cache_key(series_identity(kind, state, **kwargs), state.horizon, tuple(sorted(state.models)))
    return load_cached_forecast(key, dataset.source_mtime)


def _load_bundles(dataset: MasterDataset, kind: str, state: ForecastState, **kwargs) -> dict[str, ForecastBundle] | None:
    key = forecast_cache_key(series_identity(kind, state, **kwargs), state.horizon, tuple(sorted(state.models)))
    return load_cached_forecast(key, dataset.source_mtime)


def _fold_scores_table(bundle: ForecastBundle | None, model: str | None) -> pd.DataFrame:
    if bundle is None or not model or model not in bundle.backtest_results:
        return pd.DataFrame()
    rows = [
        {
            "fold": fs.fold_index, "test_start": fs.test_start, "test_end": fs.test_end,
            "mape": fs.mape, "rmse": fs.rmse, "mae": fs.mae, "wape": fs.wape, "error": fs.error,
        }
        for fs in bundle.backtest_results[model].fold_scores
    ]
    return pd.DataFrame(rows)


def _build_table(
    table_id: str,
    dataset: MasterDataset,
    state: ForecastState,
    store: str | None,
    time_slot: str | None,
    metric: str,
    level: str,
    top_n: int,
    entity: str | None,
    series_kind: str,
    model: str | None,
) -> pd.DataFrame:
    if table_id == "sales-leaderboard":
        bundle = _load_bundle(dataset, "sales", state, store=store)
        return bundle.leaderboard if bundle else pd.DataFrame()
    if table_id == "sales-forecast":
        bundle = _load_bundle(dataset, "sales", state, store=store)
        return bundle.forecast if bundle else pd.DataFrame()
    if table_id == "footfall-leaderboard":
        bundle = _load_bundle(dataset, "footfall", state, store=store, time_slot=time_slot, metric=metric)
        return bundle.leaderboard if bundle else pd.DataFrame()
    if table_id == "footfall-forecast":
        bundle = _load_bundle(dataset, "footfall", state, store=store, time_slot=time_slot, metric=metric)
        return bundle.forecast if bundle else pd.DataFrame()
    if table_id == "backtest-folds":
        bundle = _load_bundle(dataset, series_kind, state, store=store, time_slot=time_slot, metric=metric)
        return _fold_scores_table(bundle, model)
    if table_id == "products-summary":
        bundles = _load_bundles(dataset, "products", state, level=level, top_n=top_n)
        return topn_summary_table(bundles, level) if bundles else pd.DataFrame()
    if table_id == "products-drilldown-forecast":
        bundles = _load_bundles(dataset, "products", state, level=level, top_n=top_n)
        entity_bundle = bundles.get(entity) if bundles and entity else None
        return entity_bundle.forecast if entity_bundle else pd.DataFrame()
    if table_id == "vendors-summary":
        bundles = _load_bundles(dataset, "vendors", state, top_n=top_n)
        return topn_summary_table(bundles, "vendor") if bundles else pd.DataFrame()
    if table_id == "vendors-drilldown-forecast":
        bundles = _load_bundles(dataset, "vendors", state, top_n=top_n)
        entity_bundle = bundles.get(entity) if bundles and entity else None
        return entity_bundle.forecast if entity_bundle else pd.DataFrame()
    if table_id == "promo-uplift":
        scoped_fact = scope_to_stores(dataset.fact, state.stores)
        return promo_effectiveness.promo_uplift_table(scoped_fact)
    if table_id == "promo-campaigns":
        scoped_fact = scope_to_stores(dataset.fact, state.stores)
        return promo_effectiveness.top_promo_campaigns_table(scoped_fact, top_n=top_n)
    raise HTTPException(status_code=404, detail=f"Unknown forecast table_id: {table_id}")


@router.get("/{table_id}")
def get_forecast_table(
    table_id: str,
    dataset: MasterDataset = Depends(get_dataset),
    state: ForecastState = Depends(parse_forecast_state),
    store: str | None = Query(None),
    time_slot: str | None = Query(None),
    metric: str = Query("footfall"),
    level: str = Query("product_style"),
    top_n: int = Query(20, ge=5, le=30),
    entity: str | None = Query(None),
    series_kind: str = Query("sales"),
    model: str | None = Query(None),
    format: str = Query("json", pattern="^(json|csv)$"),
):
    df = _build_table(table_id, dataset, state, store, time_slot, metric, level, top_n, entity, series_kind, model)

    if format == "csv":
        csv_bytes = tables.dataframe_to_csv_bytes(df)
        return Response(
            content=csv_bytes,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{table_id}.csv"'},
        )

    return {"table_id": table_id, "columns": list(df.columns), "rows": _records(df)}
