"""Top-level ingestion: opens DATASET.xlsx read-only, resolves each sheet's
schema, runs the cleaning pipeline, and caches the result so the ~95s cold
read of the 357k-row DAY WISE SALE sheet only happens once per workbook
version. The source workbook is never modified.
"""
from __future__ import annotations

import logging
import pickle
from dataclasses import dataclass, field

import openpyxl
import pandas as pd

from config.column_aliases import SHEET_ALIASES
from config.settings import CLEANED_CACHE_PATH, DATASET_PATH, REQUIRED_SHEETS
from src import data_cleaner
from src.data_validator import DataQualityProfile, build_profile
from src.schema_detector import SchemaMap, rename_to_canonical, resolve_schema

logger = logging.getLogger(__name__)


@dataclass
class MasterDataset:
    fact: pd.DataFrame
    target: pd.DataFrame
    footfall: pd.DataFrame
    schema_maps: dict[str, SchemaMap]
    loaded_sheets: list[str]
    skipped_sheets: list[str]
    profile: DataQualityProfile
    source_mtime: float
    cleaning_stats: dict = field(default_factory=dict)


def _list_available_sheets(path) -> list[str]:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        return list(wb.sheetnames)
    finally:
        wb.close()


def _read_raw_sheets(path) -> tuple[dict[str, pd.DataFrame], list[str], list[str]]:
    """Reads every worksheet in REQUIRED_SHEETS that actually exists in the
    workbook. Missing/empty sheets are skipped, never crash the loader."""
    available = _list_available_sheets(path)
    loaded: dict[str, pd.DataFrame] = {}
    loaded_names: list[str] = []
    skipped_names: list[str] = []

    for sheet_name in REQUIRED_SHEETS:
        if sheet_name not in available:
            skipped_names.append(sheet_name)
            logger.warning("Worksheet %r not found in workbook; skipping.", sheet_name)
            continue
        df = pd.read_excel(path, sheet_name=sheet_name, engine="openpyxl")
        if df.empty:
            skipped_names.append(sheet_name)
            logger.warning("Worksheet %r is empty; skipping.", sheet_name)
            continue
        loaded[sheet_name] = df
        loaded_names.append(sheet_name)

    return loaded, loaded_names, skipped_names


def _build_master_dataset(path) -> MasterDataset:
    raw_sheets, loaded_sheets, skipped_sheets = _read_raw_sheets(path)

    schema_maps: dict[str, SchemaMap] = {}
    fact = pd.DataFrame()
    target = pd.DataFrame()
    footfall = pd.DataFrame()
    cleaning_stats: dict = {}

    if "DAY WISE SALE" in raw_sheets:
        raw = raw_sheets["DAY WISE SALE"]
        raw.columns = [str(c).strip() for c in raw.columns]
        schema = resolve_schema("DAY WISE SALE", list(raw.columns), SHEET_ALIASES["DAY WISE SALE"])
        schema_maps["DAY WISE SALE"] = schema
        canonical = rename_to_canonical(raw, schema)
        fact, cleaning_stats = data_cleaner.clean_day_wise_sale(canonical)

    if "SALES TARGET" in raw_sheets:
        raw = raw_sheets["SALES TARGET"]
        raw.columns = [str(c).strip() for c in raw.columns]
        schema = resolve_schema("SALES TARGET", list(raw.columns), SHEET_ALIASES["SALES TARGET"])
        schema_maps["SALES TARGET"] = schema
        canonical = rename_to_canonical(raw, schema)
        target = data_cleaner.melt_sales_target(canonical)

    if "TIME WISE FOOTFALL-NOB" in raw_sheets:
        raw = raw_sheets["TIME WISE FOOTFALL-NOB"]
        raw.columns = [str(c).strip() for c in raw.columns]
        schema = resolve_schema("TIME WISE FOOTFALL-NOB", list(raw.columns), SHEET_ALIASES["TIME WISE FOOTFALL-NOB"])
        schema_maps["TIME WISE FOOTFALL-NOB"] = schema
        canonical = rename_to_canonical(raw, schema)
        footfall = data_cleaner.melt_footfall_nob(canonical)

    profile = build_profile(
        fact=fact,
        target=target,
        footfall=footfall,
        loaded_sheets=loaded_sheets,
        skipped_sheets=skipped_sheets,
        schema_maps=schema_maps,
        cleaning_stats=cleaning_stats,
    )

    return MasterDataset(
        fact=fact,
        target=target,
        footfall=footfall,
        schema_maps=schema_maps,
        loaded_sheets=loaded_sheets,
        skipped_sheets=skipped_sheets,
        profile=profile,
        source_mtime=path.stat().st_mtime,
        cleaning_stats=cleaning_stats,
    )


def load_master_dataset(force_reload: bool = False) -> MasterDataset:
    """Cached entry point used by the whole app. Reloads automatically if
    DATASET.xlsx's modification time changes; the cache is a derived
    artifact under .cache/, never the source of truth."""
    if not DATASET_PATH.exists():
        raise FileNotFoundError(f"DATASET.xlsx not found at {DATASET_PATH}")

    current_mtime = DATASET_PATH.stat().st_mtime

    if not force_reload and CLEANED_CACHE_PATH.exists():
        try:
            with open(CLEANED_CACHE_PATH, "rb") as fh:
                cached: MasterDataset = pickle.load(fh)
            if cached.source_mtime == current_mtime:
                logger.info("Loaded cleaned master dataset from cache.")
                return cached
        except Exception:
            logger.exception("Failed to load dataset cache; rebuilding.")

    logger.info("Reading and cleaning DATASET.xlsx (this can take ~1-2 minutes)...")
    dataset = _build_master_dataset(DATASET_PATH)

    try:
        with open(CLEANED_CACHE_PATH, "wb") as fh:
            pickle.dump(dataset, fh)
    except Exception:
        logger.exception("Failed to write dataset cache; continuing without it.")

    return dataset
