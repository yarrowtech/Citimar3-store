"""Builds the Data Quality panel payload (master prompt Section 18): a single
structured profile describing what was loaded, skipped, cleaned and is still
questionable in the workbook. Never blocks analysis of otherwise-valid rows.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from config.column_aliases import REQUIRED_FIELDS_FOR_KPI
from src.schema_detector import SchemaMap


@dataclass
class DataQualityProfile:
    worksheets_loaded: list[str]
    worksheets_skipped: list[str]
    total_rows_before_cleaning: int
    rows_retained_after_cleaning: int
    date_range: tuple[str, str] | None
    missing_date_count: int
    missing_product_count: int
    missing_department_count: int
    invalid_sales_count: int
    duplicate_transaction_count: int
    zero_amount_duplicate_flagged_count: int
    negative_sales_or_return_count: int
    missing_cost_count: int
    missing_target_count: int
    missing_footfall_count: int
    unmatched_dates_target_only: list[str]
    unmatched_dates_footfall_only: list[str]
    unmatched_dates_fact_only: list[str]
    product_hierarchy_values_nulled: dict[str, int]
    tax_rate_outlier_rows: int
    categorical_numeric_contamination: dict[str, int]
    unmapped_store_rows: int
    unresolved_columns_by_sheet: dict[str, list[str]]
    kpi_availability: dict[str, bool] = field(default_factory=dict)


def _kpi_availability(schema_maps: dict[str, SchemaMap]) -> dict[str, bool]:
    resolved_fields: set[str] = set()
    for schema in schema_maps.values():
        resolved_fields.update(schema.canonical_to_actual.keys())
    # footfall/target/nob fields live under melted store-suffixed names that
    # are resolved before melting, so they're already in resolved_fields.
    availability = {}
    for kpi, required in REQUIRED_FIELDS_FOR_KPI.items():
        availability[kpi] = all(f in resolved_fields for f in required) if required else True
    return availability


def build_profile(
    fact: pd.DataFrame,
    target: pd.DataFrame,
    footfall: pd.DataFrame,
    loaded_sheets: list[str],
    skipped_sheets: list[str],
    schema_maps: dict[str, SchemaMap],
    cleaning_stats: dict,
) -> DataQualityProfile:
    date_range = None
    if not fact.empty and "date" in fact.columns:
        valid_dates = pd.to_datetime(fact["date"], errors="coerce").dropna()
        if not valid_dates.empty:
            date_range = (valid_dates.min().strftime("%d-%m-%Y"), valid_dates.max().strftime("%d-%m-%Y"))

    fact_dates = set(pd.to_datetime(fact["date"], errors="coerce").dropna().dt.normalize()) if not fact.empty else set()
    target_dates = set(pd.to_datetime(target["date"], errors="coerce").dropna().dt.normalize()) if not target.empty else set()
    footfall_dates = set(pd.to_datetime(footfall["date"], errors="coerce").dropna().dt.normalize()) if not footfall.empty else set()

    unmatched_target_only = sorted(d.strftime("%d-%m-%Y") for d in (target_dates - fact_dates))
    unmatched_footfall_only = sorted(d.strftime("%d-%m-%Y") for d in (footfall_dates - fact_dates))
    unmatched_fact_only = sorted(d.strftime("%d-%m-%Y") for d in (fact_dates - target_dates - footfall_dates))

    negative_counts = cleaning_stats.get("negative_value_rows", {})
    invalid_numeric = cleaning_stats.get("invalid_numeric_values", {})

    unresolved = {name: schema.unresolved_canonical for name, schema in schema_maps.items()}

    return DataQualityProfile(
        worksheets_loaded=loaded_sheets,
        worksheets_skipped=skipped_sheets,
        total_rows_before_cleaning=cleaning_stats.get("rows_before", 0),
        rows_retained_after_cleaning=cleaning_stats.get("rows_after", len(fact)),
        date_range=date_range,
        missing_date_count=int(fact["date"].isna().sum()) if "date" in fact.columns else 0,
        missing_product_count=int(fact["item_code"].isna().sum()) if "item_code" in fact.columns else 0,
        missing_department_count=int(fact["department"].isna().sum()) if "department" in fact.columns else 0,
        invalid_sales_count=int(invalid_numeric.get("net_amount", 0)),
        duplicate_transaction_count=cleaning_stats.get("exact_duplicate_rows_dropped", 0),
        zero_amount_duplicate_flagged_count=cleaning_stats.get("zero_amount_duplicate_rows_flagged", 0),
        negative_sales_or_return_count=int(negative_counts.get("net_amount", 0)),
        missing_cost_count=int(invalid_numeric.get("cogs_with_gst", 0)),
        missing_target_count=int(target["target"].isna().sum()) if not target.empty else 0,
        missing_footfall_count=int(footfall["footfall"].isna().sum()) if not footfall.empty else 0,
        unmatched_dates_target_only=unmatched_target_only,
        unmatched_dates_footfall_only=unmatched_footfall_only,
        unmatched_dates_fact_only=unmatched_fact_only,
        product_hierarchy_values_nulled=cleaning_stats.get("product_hierarchy_values_nulled", {}),
        tax_rate_outlier_rows=cleaning_stats.get("tax_rate_outlier_rows", 0),
        categorical_numeric_contamination=cleaning_stats.get("categorical_numeric_contamination_scan", {}),
        unmapped_store_rows=cleaning_stats.get("unmapped_store_rows", 0),
        unresolved_columns_by_sheet=unresolved,
        kpi_availability=_kpi_availability(schema_maps),
    )
