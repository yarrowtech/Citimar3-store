"""Plain helper functions shared by api/routes_forecast*.py -- not FastAPI
dependencies, just the cache-key/status-shaping logic every forecast route
needs, mirroring streamlit_forecast_app.py's equivalents so both frontends
compute identical cache keys for identical inputs.
"""
from __future__ import annotations

import pandas as pd

from src.forecasting.orchestrator import ForecastBundle
from src.forecasting.series_prep import daily_sales_series_id, footfall_nob_series_id

from .deps import ForecastState


def scope_to_stores(df: pd.DataFrame, stores: list[str]) -> pd.DataFrame:
    if "store_code" not in df.columns:
        return df
    return df.loc[df["store_code"].isin(stores)]


def products_series_id(level: str, top_n: int, stores: list[str]) -> str:
    return f"products|level={level}|top_n={top_n}|stores={','.join(sorted(stores))}"


def vendors_series_id(top_n: int, stores: list[str]) -> str:
    return f"vendors|top_n={top_n}|stores={','.join(sorted(stores))}"


def series_identity(
    kind: str,
    state: ForecastState,
    store: str | None = None,
    time_slot: str | None = None,
    metric: str = "footfall",
    level: str = "product_style",
    top_n: int = 20,
) -> str:
    """Single source of truth for a forecast series' cache-key identity string
    -- used by the status/compute control-plane routes AND the chart/table
    read routes, so both always agree on which cache entry a given set of
    request params points at."""
    if kind == "sales":
        return daily_sales_series_id(store)
    if kind == "footfall":
        return footfall_nob_series_id(store or "", time_slot, metric)
    if kind == "products":
        return products_series_id(level, top_n, state.stores)
    return vendors_series_id(top_n, state.stores)


def bundle_status(bundle: ForecastBundle | None, model_set: list[str]) -> dict:
    if bundle is None:
        return {"computed": False}
    return {
        "computed": True,
        "series_id": bundle.series_id,
        "label": bundle.label,
        "horizon": bundle.horizon,
        "insufficient_history": bundle.insufficient_history,
        "best_model": bundle.best_model,
        "model_set": model_set,
    }


def bundles_status(bundles: dict[str, ForecastBundle] | None) -> dict:
    if bundles is None:
        return {"computed": False}
    return {
        "computed": True,
        "entity_count": len(bundles),
        "entities": [
            {"name": name, "insufficient_history": b.insufficient_history, "best_model": b.best_model}
            for name, b in bundles.items()
        ],
    }


def topn_summary_table(bundles: dict[str, ForecastBundle], entity_label: str) -> pd.DataFrame:
    rows = [
        {
            entity_label: name,
            "forecast_total": float(b.forecast["point"].sum()) if not b.insufficient_history and not b.forecast.empty else None,
            "best_model": b.best_model,
        }
        for name, b in bundles.items()
    ]
    return pd.DataFrame(rows).sort_values("forecast_total", ascending=False, na_position="last").reset_index(drop=True)
