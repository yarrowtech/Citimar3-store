from __future__ import annotations

import math

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, Response

from src import tables
from src.comparison_engine import build_deltas, kpis_for_window, previous_period_window
from src.data_loader import MasterDataset
from src.filter_engine import FilterState, apply_filters, filter_store_level_table
from src.kpi_engine import compute_kpis

from .deps import get_dataset, parse_filter_state

router = APIRouter(prefix="/api/tables", tags=["tables"])


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


def _build_table(
    table_id: str,
    dataset: MasterDataset,
    state,
    measure: str,
    top_n: int | None,
    *,
    granularity: str = "month",
    dimension: str | None = None,
    category: str | None = None,
) -> pd.DataFrame:
    fact = apply_filters(dataset.fact, state)
    footfall = filter_store_level_table(dataset.footfall, state)
    target = filter_store_level_table(dataset.target, state)

    if table_id == "sales_overview":
        return tables.sales_overview_table(fact, footfall, target, granularity)
    if table_id == "sales_trend":
        return tables.sales_trend_table(fact, footfall, dimension=dimension or "period", granularity=granularity)
    if table_id == "avg_sales":
        return tables.avg_sales_table(fact, granularity=granularity)
    if table_id == "period_comparison":
        if (dimension or "monthly_same_day") == "same_period_yoy":
            date_free_state = FilterState(
                stores=state.stores,
                time_slot=state.time_slot,
                division=state.division,
                section=state.section,
                department=state.department,
                product_design_no=state.product_design_no,
                product_style=state.product_style,
                product_type=state.product_type,
                product_size=state.product_size,
                vendors=state.vendors,
            )
            comparison_fact = apply_filters(dataset.fact, date_free_state)
            return tables.same_period_year_over_year_table(comparison_fact, state.start_date, state.end_date)
        return tables.period_comparison_table(fact, dimension=dimension or "monthly_same_day")
    if table_id == "secondary_gauge_values":
        return tables.secondary_gauge_values_table(fact, footfall, target)
    if table_id == "footfall_vs_nob":
        return tables.footfall_vs_nob_table(footfall, dimension=dimension or "date")
    if table_id == "customer_footfall_net":
        return tables.visitor_vs_net_sales_table(footfall, fact, metric="footfall", dimension=dimension or "date")
    if table_id == "customer_nob_net":
        return tables.visitor_vs_net_sales_table(footfall, fact, metric="nob", dimension=dimension or "date")
    if table_id == "footfall_nob_breakdown":
        return tables.footfall_nob_breakdown_table(footfall, dimension=dimension or "dayofweek")
    if table_id == "conversion_funnel":
        if (dimension or "date") == "timeslot":
            return tables.conversion_funnel_table(footfall, None, None, dimension="timeslot")
        k = compute_kpis(fact, footfall, target)
        return tables.conversion_funnel_table(footfall, k.footfall, k.nob, dimension="date")
    if table_id == "top_products":
        return tables.top_products_table(fact, measure, top_n)
    if table_id == "top_brands":
        return tables.top_brands_table(fact, top_n)
    if table_id == "category_drilldown":
        return tables.category_net_sales_table(fact)
    if table_id == "top_category":
        # The chart consumes the full frame (needs `quantity`); the table view
        # is trimmed to the fixed 6 display columns.
        full = tables.top_category_table(fact, category or "division", measure, top_n)
        cols = [c for c in tables.TOP_CATEGORY_DISPLAY_COLUMNS if c in full.columns]
        return full[cols] if cols else full
    if table_id == "performer_pairing":
        return tables.department_performer_pairing_table(fact, top_n=top_n)
    if table_id == "store_scorecard":
        return tables.store_scorecard_table(fact, footfall, target)
    if table_id == "discount_impact":
        return tables.discount_impact_table(fact, footfall, target, granularity)
    if table_id == "promotion_breakdown":
        return tables.promotion_breakdown_table(fact)
    if table_id == "same_period_yoy":
        # Needs the store/product-filtered fact WITHOUT the date bound (the
        # date_free_state pattern below, same as kpi_table's own previous-
        # period comparison just below) -- a row here can fall in either
        # this year's or last year's window, and `fact` above is already
        # narrowed to state's date range so it alone could never supply
        # last year's side.
        date_free_state = FilterState(
            stores=state.stores,
            time_slot=state.time_slot,
            division=state.division,
            section=state.section,
            department=state.department,
            product_design_no=state.product_design_no,
            product_style=state.product_style,
            product_type=state.product_type,
            product_size=state.product_size,
            vendors=state.vendors,
        )
        comparison_fact = apply_filters(dataset.fact, date_free_state)
        return tables.same_period_year_over_year_table(comparison_fact, state.start_date, state.end_date)
    if table_id == "kpi_table":
        current = compute_kpis(fact, footfall, target)
        if state.start_date and state.end_date:
            # fact/footfall/target above are already narrowed to state's date
            # window, so re-slicing them for the (necessarily earlier)
            # previous-period window always comes back empty. Re-apply
            # everything except the date bound to the full dataset instead,
            # the same date_free_state pattern api/routes_kpis.py uses, then
            # let kpis_for_window slice the comparison window from that.
            date_free_state = FilterState(
                stores=state.stores,
                time_slot=state.time_slot,
                division=state.division,
                section=state.section,
                department=state.department,
                product_design_no=state.product_design_no,
                product_style=state.product_style,
                product_type=state.product_type,
                product_size=state.product_size,
                vendors=state.vendors,
            )
            store_only_state = FilterState(stores=state.stores, time_slot=state.time_slot)
            comparison_fact = apply_filters(dataset.fact, date_free_state)
            comparison_footfall = filter_store_level_table(dataset.footfall, store_only_state)
            comparison_target = filter_store_level_table(dataset.target, store_only_state)
            win_start, win_end = previous_period_window(state.start_date, state.end_date)
            previous = kpis_for_window(comparison_fact, comparison_footfall, comparison_target, win_start, win_end)
        else:
            previous = current
        deltas = build_deltas(current, previous)
        rows = [
            {
                "kpi": d.kpi,
                "current_value": d.current,
                "previous_period_value": d.previous,
                "absolute_variance": d.absolute_variance,
                "percentage_variance": d.percentage_variance,
                "status": d.status,
            }
            for d in deltas.values()
        ]
        return pd.DataFrame(rows)

    raise HTTPException(status_code=404, detail=f"Unknown table_id: {table_id}")


@router.get("/{table_id}")
def get_table(
    table_id: str,
    dataset: MasterDataset = Depends(get_dataset),
    state=Depends(parse_filter_state),
    measure: str = Query("net_amount"),
    top_n: int | None = Query(None, ge=1, le=1000),
    granularity: str = Query("month"),
    dimension: str | None = Query(None),
    category: str | None = Query(None),
    format: str = Query("json", pattern="^(json|csv)$"),
):
    df = _build_table(
        table_id, dataset, state, measure, top_n,
        granularity=granularity, dimension=dimension, category=category,
    )

    if format == "csv":
        csv_bytes = tables.dataframe_to_csv_bytes(df)
        filename = f"{table_id}.csv"
        return Response(
            content=csv_bytes,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    return {"table_id": table_id, "columns": list(df.columns), "rows": _records(df)}
