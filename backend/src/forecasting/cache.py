"""Mirrors src/data_loader.py's mtime-keyed pickle cache pattern exactly
(try/except around load AND save, so a bad cache never crashes the app),
extended with a compound key -- series identity + horizon + model set + a
schema version -- since forecasting produces many independent cacheable
ForecastBundles, not the single MasterDataset object data_loader caches.
"""
from __future__ import annotations

import hashlib
import logging
import pickle
from dataclasses import dataclass
from pathlib import Path

from config.forecast_settings import CACHE_SCHEMA_VERSION, FORECAST_CACHE_DIR
from src.forecasting.orchestrator import ForecastBundle

logger = logging.getLogger(__name__)


def forecast_cache_key(series_id: str, horizon: int, model_set: tuple[str, ...]) -> str:
    """Never a raw filename -- product/vendor names can contain path-unsafe
    characters (e.g. '/')."""
    raw = f"{series_id}|{horizon}|{'+'.join(sorted(model_set))}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


@dataclass
class ForecastCacheEntry:
    bundle: ForecastBundle
    source_mtime: float
    schema_version: int = CACHE_SCHEMA_VERSION


def _cache_path(key: str) -> Path:
    return FORECAST_CACHE_DIR / f"{key}.pkl"


def load_cached_forecast(key: str, source_mtime: float) -> ForecastBundle | None:
    """None on: missing file, any pickle-load exception, mtime mismatch, or
    stale schema_version -- same try/except-everything contract as
    data_loader.load_master_dataset, so a corrupted/stale cache file never
    crashes the app, only forces a recompute."""
    path = _cache_path(key)
    if not path.exists():
        return None
    try:
        with open(path, "rb") as f:
            entry: ForecastCacheEntry = pickle.load(f)
    except Exception:
        logger.exception("load_cached_forecast: failed to read cache for key=%s", key)
        return None
    if entry.source_mtime != source_mtime or entry.schema_version != CACHE_SCHEMA_VERSION:
        return None
    return entry.bundle


def save_forecast_cache(key: str, bundle: ForecastBundle, source_mtime: float) -> None:
    """Best-effort; a failed write never blocks showing the forecast, only
    slows the next run."""
    try:
        entry = ForecastCacheEntry(bundle=bundle, source_mtime=source_mtime)
        with open(_cache_path(key), "wb") as f:
            pickle.dump(entry, f)
    except Exception:
        logger.exception("save_forecast_cache: failed to write cache for key=%s", key)
