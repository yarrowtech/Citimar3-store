from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from api.auth import CurrentUser, get_current_user, require_store_access
from src import charts, daily_dashboard_store, tables
from src.data_loader import MasterDataset
from src.filter_engine import FilterState, apply_filters, filter_store_level_table
from src.kpi_engine import compute_kpis

from db.session import session_scope
from .deps import get_dataset, parse_filter_state

router = APIRouter(prefix="/api/charts", tags=["charts"])

# Opt-in allowlist for the frontend's <ChartTypeToggle>: {chart_id: {allowed
# curated types}}. Empty until a phase of the Historical Analytics Overhaul
# wires a given chart's toggle -- apply_chart_type is only ever called for a
# (chart_id, chart_type) pair listed here, so an un-migrated chart is untouched.
_LINEAR_CHART_TYPES = {"column", "bar", "line", "area"}
# Dual-axis charts (a secondary Conversion % / Net Sales line): horizontal
# "bar" has no clean axis-swapped form, so it's left out.
_DUAL_AXIS_CHART_TYPES = {"column", "line", "area"}

CHART_TYPE_ENABLED: dict[str, set[str]] = {
    "sales_overview": set(charts.CURATED_CHART_TYPES),
    "monthly_sales": set(charts.CURATED_CHART_TYPES),  # alias of sales_overview
    # Section 2 (Sales Performance) mode-toggled charts.
    "sales_trend": set(_LINEAR_CHART_TYPES),
    "avg_sales": set(_LINEAR_CHART_TYPES),
    "period_comparison": set(_LINEAR_CHART_TYPES),
    # Section 3 (Customer & Conversion) mode-toggled charts. The dual-axis
    # comparison charts offer column/line/area only (pie/3d would drop the
    # secondary Conversion %/Net Sales series, horizontal bar has no clean
    # dual-axis form); the single-axis Footfall/NOB breakdown offers the full
    # curated set.
    "footfall_vs_nob": set(_DUAL_AXIS_CHART_TYPES),
    "customer_footfall_net": set(_DUAL_AXIS_CHART_TYPES),
    "customer_nob_net": set(_DUAL_AXIS_CHART_TYPES),
    "footfall_nob_breakdown": set(charts.CURATED_CHART_TYPES),
    # Product & Brand: the merged Top <category> ranking + the department
    # strong/weak pairing -- both plain single/grouped bar, full curated set.
    "top_category": set(charts.CURATED_CHART_TYPES),
    "performer_pairing": set(charts.CURATED_CHART_TYPES),
}

# mode-toggle `dimension` vocabulary per chart_id (Historical Analytics
# Overhaul A5 -- also mirrored in the frontend pages' <Select>/<DimensionSelect>):
#   sales_trend           : period (default) | timeslot
#   period_comparison     : monthly_same_day (default) | weekly_same_day | yearly_month | same_period_yoy
#   footfall_vs_nob        : date (default) | timeslot
#   customer_footfall_net  : date (default) | dayofweek
#   customer_nob_net       : date (default) | dayofweek
#   footfall_nob_breakdown : dayofweek (default) | timeslot | date
#   funnel                 : date (default) | timeslot


@router.get("/{chart_id}")
def get_chart(
    chart_id: str,
    dataset: MasterDataset = Depends(get_dataset),
    state=Depends(parse_filter_state),
    user: CurrentUser = Depends(get_current_user),
    granularity: str = Query("month"),
    measure: str = Query("net_amount"),
    top_n: int = Query(10, ge=1, le=200),
    day_limit: int = Query(20, ge=1, le=31),
    chart_type: str | None = Query(None),
    dimension: str | None = Query(None),
    category: str | None = Query(None),
    theme: str | None = Query(None, description="Render hint: 'neon' recolours the figure; anything else is unchanged"),
):
    result = _dispatch_chart(
        chart_id, dataset, state, user,
        granularity=granularity, measure=measure, top_n=top_n, day_limit=day_limit,
        dimension=dimension, category=category,
    )
    if chart_type in CHART_TYPE_ENABLED.get(chart_id, set()):
        result = charts.apply_chart_type(result, chart_type)
    return charts.apply_theme(result, theme)


def _dispatch_chart(
    chart_id: str,
    dataset: MasterDataset,
    state,
    user: CurrentUser,
    *,
    granularity: str = "month",
    measure: str = "net_amount",
    top_n: int = 10,
    day_limit: int = 20,
    dimension: str | None = None,
    category: str | None = None,
) -> dict:
    fact = apply_filters(dataset.fact, state)
    footfall = filter_store_level_table(dataset.footfall, state)
    target = filter_store_level_table(dataset.target, state)

    if chart_id == "net_vs_gross":
        return charts.net_vs_gross_sales_chart(fact, granularity)
    if chart_id == "footfall_vs_nob":
        return charts.footfall_vs_nob_chart(footfall, dimension=dimension or "date")
    if chart_id == "customer_footfall_net":
        return charts.footfall_vs_net_sales_chart(footfall, fact, metric="footfall", dimension=dimension or "date")
    if chart_id == "customer_nob_net":
        return charts.nob_vs_net_sales_chart(footfall, fact, dimension=dimension or "date")
    if chart_id == "footfall_nob_breakdown":
        return charts.footfall_nob_breakdown_chart(footfall, dimension=dimension or "dayofweek")
    if chart_id == "week_segment":
        return charts.week_segment_chart(fact)
    if chart_id == "footfall_nob_dayofweek":
        return charts.footfall_nob_by_dayofweek_chart(footfall)
    if chart_id == "footfall_nob_timeslot":
        return charts.footfall_nob_by_timeslot_chart(footfall)
    if chart_id in ("atv_gauge", "rpv_gauge", "basket_size_gauge", "conversion_gauge", "achievement_gauge", "remaining_pct_gauge"):
        kpis = compute_kpis(fact, footfall, target)
        if chart_id == "atv_gauge":
            return charts.atv_gauge(kpis.atv)
        if chart_id == "rpv_gauge":
            return charts.rpv_gauge(kpis.rpv)
        if chart_id == "basket_size_gauge":
            return charts.basket_size_gauge(kpis.basket_size)
        if chart_id == "conversion_gauge":
            return charts.conversion_gauge(kpis.conversion_pct)
        if chart_id == "achievement_gauge":
            return charts.achievement_gauge(kpis.achievement_pct)
        return charts.remaining_pct_gauge(kpis.remaining_pct)
    if chart_id in (
        "daily_conversion_gauge", "daily_achievement_gauge", "daily_remaining_gauge",
        "daily_atv_gauge", "daily_rpv_gauge", "daily_basket_size_gauge",
    ):
        if not state.stores or state.start_date is None:
            raise HTTPException(status_code=400, detail="A single store and date are required for daily gauges.")
        # session_scope(), not a route-level `Depends(get_db)` -- this
        # dispatcher's other ~20 chart_ids are pure DATASET.xlsx/pandas and
        # never touch the database, so a route-level DB dependency would
        # require MONGODB_URI to be set just to render an unrelated
        # historical chart. Scoping the session to only the daily_* branches
        # that actually need it avoids that.
        if len(state.stores) > 1:
            # The admin's "Overall Stores Summary" passes every store -- blend
            # them. state.stores is clamped to the caller's allowed set in
            # parse_filter_state, so a manager can never reach this branch,
            # but check explicitly.
            if not user.is_admin:
                raise HTTPException(status_code=403, detail="Administrator access required.")
            with session_scope() as db:
                daily_kpis = daily_dashboard_store.compute_live_kpis_all_stores(db, state.start_date)["combined"]
        else:
            # Belt-and-braces authz check for the single store this resolves against.
            require_store_access(state.stores[0], user)
            with session_scope() as db:
                daily_kpis = daily_dashboard_store.compute_live_kpis(db, state.stores[0], state.start_date)
        # zero_if_missing=True: a blank value on this live manual-entry page
        # means "hasn't happened yet today", not "source column absent" -- so
        # these gauges park the needle at 0 rather than showing "N/A",
        # matching the Daily Dashboard's KPI cards (format.ts's *OrZero
        # formatters). The DATASET.xlsx-driven gauges above keep the default
        # N/A behaviour.
        if chart_id == "daily_conversion_gauge":
            return charts.conversion_gauge(daily_kpis["conversion_pct"], zero_if_missing=True)
        if chart_id == "daily_achievement_gauge":
            return charts.achievement_gauge(daily_kpis["achievement_pct"], zero_if_missing=True)
        if chart_id == "daily_atv_gauge":
            return charts.atv_gauge(daily_kpis["atv"], zero_if_missing=True)
        if chart_id == "daily_rpv_gauge":
            return charts.rpv_gauge(daily_kpis["rpv"], zero_if_missing=True)
        if chart_id == "daily_basket_size_gauge":
            return charts.basket_size_gauge(daily_kpis["basket_size"], zero_if_missing=True)
        return charts.remaining_pct_gauge(daily_kpis["remaining_pct"], zero_if_missing=True)
    if chart_id in ("daily_timeslot_breakdown", "daily_footfall_nob"):
        if not state.stores or state.start_date is None:
            raise HTTPException(status_code=400, detail="A single store and date are required for the daily time-slot breakdown.")
        require_store_access(state.stores[0], user)
        with session_scope() as db:
            breakdown = daily_dashboard_store.compute_live_timeslot_breakdown(db, state.stores[0], state.start_date)
            day_target = daily_dashboard_store.read_store_target(db, state.stores[0], state.start_date)
        if chart_id == "daily_footfall_nob":
            return charts.daily_footfall_vs_nob_chart(breakdown)
        return charts.daily_timeslot_breakdown_chart(breakdown, day_target)
    if chart_id == "funnel":
        if dimension == "timeslot":
            return charts.conversion_funnel_by_timeslot_chart(footfall)
        kpis = compute_kpis(fact, footfall, target)
        return charts.conversion_funnel_chart(kpis.footfall, kpis.nob)
    if chart_id == "bridge":
        return charts.monthly_sales_bridge_chart(fact)
    if chart_id in ("sales_overview", "monthly_sales"):
        # "monthly_sales" is kept as a back-compat alias -- both now render the
        # §1 Sales Overview chart (Net Sales + Remaining + Target, period-switchable).
        # charts.monthly_sales_chart() itself stays for the Streamlit app.
        return charts.sales_overview_chart(fact, target, granularity=granularity)
    if chart_id == "daily_trend":
        return charts.daily_sales_trend_chart(fact)
    if chart_id == "day_of_week":
        return charts.avg_sales_by_day_of_week_chart(fact, footfall)
    if chart_id == "target_achievement_month":
        return charts.target_achievement_by_month_chart(fact, target)
    if chart_id == "same_day_comparison":
        return charts.monthly_same_day_comparison_chart(fact, day_limit)
    if chart_id == "yearly_month_comparison":
        return charts.yearly_same_month_comparison_chart(fact)
    if chart_id == "sales_trend":
        return charts.sales_trend_chart(fact, footfall, dimension=dimension or "period", granularity=granularity)
    if chart_id == "avg_sales":
        return charts.avg_sales_chart(fact, granularity=granularity)
    if chart_id == "period_comparison" and (dimension or "monthly_same_day") != "same_period_yoy":
        return charts.period_comparison_chart(fact, dimension=dimension or "monthly_same_day", day_limit=day_limit)
    if chart_id == "same_period_yoy" or chart_id == "period_comparison":
        # `period_comparison` with dimension=same_period_yoy funnels here too --
        # this mode needs the date-free fact slice + the shared YoY table
        # builder (so chart and table companion can't disagree), unlike the
        # other three period-comparison modes handled just above.
        # Same date_free_state pattern as api/routes_tables.py's
        # same_period_yoy table branch -- see that branch's comment. Reuses
        # tables.same_period_year_over_year_table's own row-building (not a
        # second computation of it) so this chart and its table companion
        # can never disagree.
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
        comparison_table = tables.same_period_year_over_year_table(comparison_fact, state.start_date, state.end_date)
        return charts.same_period_year_over_year_chart(comparison_table)
    if chart_id == "category_drilldown":
        return charts.category_drilldown_chart(fact)
    if chart_id == "top_products":
        table = tables.top_products_table(fact, measure, top_n)
        return charts.top_products_chart(table, measure)
    if chart_id == "top_brands":
        table = tables.top_brands_table(fact, top_n)
        return charts.top_brands_chart(table)
    if chart_id == "top_category":
        table = tables.top_category_table(fact, category or "division", measure, top_n)
        return charts.top_category_chart(table, category or "division", measure)
    if chart_id == "performer_pairing":
        table = tables.department_performer_pairing_table(fact, top_n=top_n)
        return charts.department_performer_pairing_chart(table, top_n)
    if chart_id == "discount_impact":
        table = tables.discount_impact_table(fact, footfall, target, granularity)
        return charts.discount_impact_chart(table)
    if chart_id == "promotion_breakdown":
        table = tables.promotion_breakdown_table(fact)
        return charts.promotion_breakdown_chart(table)

    raise HTTPException(status_code=404, detail=f"Unknown chart_id: {chart_id}")
