"""CITIMART Sales KPI Dashboard -- standalone Streamlit app.

Run with:
    streamlit run streamlit_app.py

An independent alternative frontend to the FastAPI/React app (app.py). It
reuses the exact same data pipeline and business logic -- src/data_loader,
src/filter_engine, src/kpi_engine, src/comparison_engine, src/charts,
src/tables, src/formatting, and config/ -- so no formula, chart, or cleaning
rule is duplicated. The two apps only share DATASET.xlsx (read-only) and the
.cache/ derived-dataset cache; running one does not affect the other.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config.kpi_thresholds import (
    ACHIEVEMENT_THRESHOLDS,
    ATV_THRESHOLDS,
    CONVERSION_THRESHOLDS,
    achievement_status,
    atv_status,
    basket_size_status,
    conversion_status,
    rpv_status,
)
from config.settings import CURRENCY_SYMBOL, STORE_CODE_TO_NAME
from src import charts, formatting, period_engine, tables
from src.data_loader import load_master_dataset
from src.streamlit_theme import theme_selector, themed_figure
from src.filter_engine import (
    FILTER_HIERARCHY,
    FilterState,
    apply_filters,
    available_values,
    dataset_date_bounds,
    default_filter_state,
    filter_store_level_table,
    reset_unavailable_selections,
)
from src.kpi_engine import compute_kpis

st.set_page_config(page_title="CITIMART Sales KPI Dashboard", page_icon="🛒", layout="wide")

STATUS_COLOR = {"red": "red", "yellow": "orange", "green": "green"}


@st.cache_resource(show_spinner="Loading and cleaning DATASET.xlsx (cached after first run)...")
def get_dataset():
    return load_master_dataset()


def to_figure(fig_dict: dict) -> go.Figure:
    # Recoloured to the neon palette when the sidebar Theme toggle is on Neon;
    # an identity wrapper around go.Figure otherwise.
    return themed_figure(fig_dict)


def metric(col, label: str, value_str: str, status: str | None = None) -> None:
    col.metric(label, value_str)
    if status:
        color = STATUS_COLOR[status]
        col.markdown(f":{color}[●] {status.title()}")


def download_button(df: pd.DataFrame, filename: str, label: str = "Download CSV") -> None:
    if df.empty:
        return
    st.download_button(label, data=tables.dataframe_to_csv_bytes(df), file_name=filename, mime="text/csv")


def sidebar_filters(dataset) -> FilterState:
    fact = dataset.fact
    theme_selector()
    st.sidebar.header("Filters")

    default_state = default_filter_state(fact)
    min_date, max_date = dataset_date_bounds(fact)

    store_options = sorted(fact["store_code"].dropna().unique().tolist()) if "store_code" in fact.columns else []
    selected_stores = st.sidebar.multiselect(
        "Store",
        options=store_options,
        default=st.session_state.get("f_stores", store_options),
        format_func=lambda code: STORE_CODE_TO_NAME.get(code, code),
        key="f_stores",
    )

    date_cols = st.sidebar.columns(2)
    start_date = date_cols[0].date_input(
        "Start date", value=default_state.start_date, min_value=min_date, max_value=max_date, key="f_start_date"
    )
    end_date = date_cols[1].date_input(
        "End date", value=default_state.end_date, min_value=min_date, max_value=max_date, key="f_end_date"
    )
    if start_date > end_date:
        st.sidebar.error("Start date must be on or before end date.")

    state = FilterState(stores=selected_stores or None, start_date=start_date, end_date=end_date)

    for field_name in FILTER_HIERARCHY:
        key = f"f_{field_name}"
        options = available_values(fact, state, field_name)
        cleaned = reset_unavailable_selections(st.session_state.get(key, []), options) or []
        if cleaned != st.session_state.get(key, []):
            st.session_state[key] = cleaned
        selected = st.sidebar.multiselect(field_name.replace("_", " ").title(), options=options, key=key)
        setattr(state, field_name, selected or None)

    if st.sidebar.button("Reset all filters"):
        for key in [k for k in st.session_state if k.startswith("f_")]:
            del st.session_state[key]
        st.rerun()

    return state


def render_overview(kpis, filtered_fact: pd.DataFrame) -> None:
    st.subheader("KPI Summary")
    st.caption(f"{len(filtered_fact):,} transaction rows in the current filter selection")

    # KPI cards: missing -> 0 (Historical Analytics Overhaul decision); the
    # gauges/charts/tables below keep the N/A convention.
    row1 = st.columns(4)
    metric(row1[0], "Net Sales", formatting.format_currency_or_zero(kpis.net_sales))
    gross_label = "Gross Sales *" if kpis.gross_sales_is_derived else "Gross Sales"
    metric(row1[1], gross_label, formatting.format_currency_or_zero(kpis.gross_sales))
    metric(row1[2], "Discounts", formatting.format_currency_or_zero(kpis.discounts))
    metric(row1[3], "Gross Profit", formatting.format_currency_or_zero(kpis.gross_profit))

    row2 = st.columns(4)
    metric(row2[0], "Bill Quantity", formatting.format_number_or_zero(kpis.bill_quantity))
    metric(row2[1], "Footfall", formatting.format_number_or_zero(kpis.footfall))
    metric(row2[2], "Transactions (NOB)", formatting.format_number_or_zero(kpis.nob))
    metric(row2[3], "Sales Target", formatting.format_currency_or_zero(kpis.sales_target))

    row3 = st.columns(4)
    metric(row3[0], "ATV", formatting.format_currency_or_zero(kpis.atv), atv_status(kpis.atv))
    metric(row3[1], "RPV", formatting.format_currency_or_zero(kpis.rpv), rpv_status(kpis.rpv))
    metric(row3[2], "Basket Size", formatting.format_number_or_zero(kpis.basket_size, decimals=2), basket_size_status(kpis.basket_size))
    metric(row3[3], "Conversion %", formatting.format_percent_or_zero(kpis.conversion_pct), conversion_status(kpis.conversion_pct))

    row4 = st.columns(4)
    metric(row4[0], "Achievement %", formatting.format_percent_or_zero(kpis.achievement_pct), achievement_status(kpis.achievement_pct))
    metric(row4[1], "Returned Units", formatting.format_number_or_zero(kpis.returned_units))
    metric(row4[2], "Returned Value", formatting.format_currency_or_zero(kpis.returned_value))

    if kpis.gross_sales_is_derived:
        st.caption("* Gross Sales derived as Net Sales + Discounts (no Gross Amount column found in the workbook).")

    st.subheader("Status Gauges")
    # Calls charts.gauge_chart() directly (not atv_gauge()/conversion_gauge()/
    # achievement_gauge(), which now return the React app's plain-JSON
    # gauge_spec() instead) -- same thresholds, same numbers, Plotly-rendered
    # for this Streamlit UI specifically (see gauge_chart()'s docstring).
    g1, g2, g3 = st.columns(3)
    g1.plotly_chart(
        to_figure(charts.gauge_chart(kpis.atv, "ATV (Average Transaction Value)", None, ATV_THRESHOLDS["red_below"], ATV_THRESHOLDS["green_at_or_above"], prefix=f"{CURRENCY_SYMBOL} ")),
        width="stretch", theme=None,
    )
    g2.plotly_chart(
        to_figure(charts.gauge_chart(kpis.conversion_pct, "Conversion %", 40.0, CONVERSION_THRESHOLDS["red_below"], CONVERSION_THRESHOLDS["green_at_or_above"], suffix="%")),
        width="stretch", theme=None,
    )
    g3.plotly_chart(
        to_figure(charts.gauge_chart(kpis.achievement_pct, "Target Achievement %", 100.0, ACHIEVEMENT_THRESHOLDS["red_below"], ACHIEVEMENT_THRESHOLDS["green_above"], suffix="%")),
        width="stretch", theme=None,
    )

    st.plotly_chart(to_figure(charts.conversion_funnel_chart(kpis.footfall, kpis.nob)), width="stretch", theme=None)


def render_trends(fact: pd.DataFrame, footfall: pd.DataFrame, target: pd.DataFrame) -> None:
    st.plotly_chart(to_figure(charts.net_vs_gross_sales_chart(fact)), width="stretch", theme=None)
    st.plotly_chart(to_figure(charts.monthly_sales_chart(fact, target)), width="stretch", theme=None)
    st.plotly_chart(to_figure(charts.daily_sales_trend_chart(fact)), width="stretch", theme=None)

    c1, c2 = st.columns(2)
    c1.plotly_chart(to_figure(charts.avg_sales_by_day_of_week_chart(fact, footfall)), width="stretch", theme=None)
    c2.plotly_chart(to_figure(charts.week_segment_chart(fact)), width="stretch", theme=None)

    st.plotly_chart(to_figure(charts.monthly_sales_bridge_chart(fact)), width="stretch", theme=None)
    st.plotly_chart(to_figure(charts.target_achievement_by_month_chart(fact, target)), width="stretch", theme=None)
    st.plotly_chart(to_figure(charts.monthly_same_day_comparison_chart(fact)), width="stretch", theme=None)
    st.plotly_chart(to_figure(charts.yearly_same_month_comparison_chart(fact)), width="stretch", theme=None)


def render_footfall(footfall: pd.DataFrame) -> None:
    st.plotly_chart(to_figure(charts.footfall_vs_nob_chart(footfall)), width="stretch", theme=None)
    c1, c2 = st.columns(2)
    c1.plotly_chart(to_figure(charts.footfall_nob_by_dayofweek_chart(footfall)), width="stretch", theme=None)
    c2.plotly_chart(to_figure(charts.footfall_nob_by_timeslot_chart(footfall)), width="stretch", theme=None)


def render_category(fact: pd.DataFrame) -> None:
    st.markdown("#### Category Drill-Down (Division → Section → Department)")
    st.plotly_chart(to_figure(charts.category_drilldown_chart(fact)), width="stretch", theme=None)
    drilldown = tables.category_net_sales_table(fact)
    st.dataframe(drilldown, width="stretch")
    download_button(drilldown, "category_net_sales.csv")

    st.markdown("#### Top Category by Measure")
    c1, c2 = st.columns(2)
    category = c1.selectbox("Category", ["division", "section", "department"], format_func=str.capitalize, key="cat_dim")
    measure = c2.selectbox(
        "Measure", ["net_amount", "quantity", "transactions"],
        format_func=lambda m: {"net_amount": "Net Sales", "quantity": "Quantity", "transactions": "Transactions"}[m],
        key="cat_measure",
    )
    top_category = tables.top_category_table(fact, category, measure, top_n=15)
    st.plotly_chart(to_figure(charts.top_category_chart(top_category, category, measure)), width="stretch", theme=None)
    st.dataframe(top_category, width="stretch")
    download_button(top_category, "top_category.csv")

    st.markdown("#### Performer Pairing (Strong vs Weak) by Department")
    performer_pairing = tables.department_performer_pairing_table(fact, top_n=15)
    st.plotly_chart(
        to_figure(charts.department_performer_pairing_chart(performer_pairing, top_n=15)), width="stretch", theme=None
    )
    st.dataframe(performer_pairing, width="stretch")
    download_button(performer_pairing, "performer_pairing.csv")


def render_profitability(fact: pd.DataFrame, footfall: pd.DataFrame, target: pd.DataFrame) -> None:
    st.markdown("#### Discounted vs Non-Discounted Sales")
    period = st.selectbox(
        "Period", list(period_engine.PERIODS), index=list(period_engine.PERIODS).index("month"),
        format_func=str.capitalize, key="profit_period",
    )
    discount_table = tables.discount_impact_table(fact, footfall, target, period)
    st.plotly_chart(to_figure(charts.discount_impact_chart(discount_table)), width="stretch", theme=None)
    st.dataframe(discount_table, width="stretch")
    download_button(discount_table, "discount_impact.csv")

    st.markdown("#### Promotion Breakdown")
    promo_table = tables.promotion_breakdown_table(fact)
    st.plotly_chart(to_figure(charts.promotion_breakdown_chart(promo_table)), width="stretch", theme=None)
    st.dataframe(promo_table, width="stretch")
    download_button(promo_table, "promotion_breakdown.csv")


def render_scorecard(fact: pd.DataFrame, footfall: pd.DataFrame, target: pd.DataFrame) -> None:
    scorecard = tables.store_scorecard_table(fact, footfall, target)
    st.dataframe(scorecard, width="stretch")
    download_button(scorecard, "store_scorecard.csv")


def render_data_quality(dataset) -> None:
    profile = dataset.profile

    st.write(f"**Worksheets loaded:** {', '.join(profile.worksheets_loaded) or 'none'}")
    if profile.worksheets_skipped:
        st.warning(f"Worksheets skipped: {', '.join(profile.worksheets_skipped)}")

    c1, c2, c3 = st.columns(3)
    c1.metric("Rows before cleaning", formatting.format_number(profile.total_rows_before_cleaning))
    c2.metric("Rows retained", formatting.format_number(profile.rows_retained_after_cleaning))
    c3.metric("Date range", f"{profile.date_range[0]} – {profile.date_range[1]}" if profile.date_range else "N/A")

    st.subheader("Row-level issues")
    issues = {
        "Missing date": profile.missing_date_count,
        "Missing product": profile.missing_product_count,
        "Missing department": profile.missing_department_count,
        "Invalid sales values": profile.invalid_sales_count,
        "Exact duplicate rows dropped": profile.duplicate_transaction_count,
        "Zero-amount duplicates flagged": profile.zero_amount_duplicate_flagged_count,
        "Negative sales/returns": profile.negative_sales_or_return_count,
        "Missing cost": profile.missing_cost_count,
        "Missing target": profile.missing_target_count,
        "Missing footfall": profile.missing_footfall_count,
        "Tax rate outliers": profile.tax_rate_outlier_rows,
        "Unmapped store rows": profile.unmapped_store_rows,
    }
    st.dataframe(pd.DataFrame(issues.items(), columns=["Check", "Count"]), width="stretch")

    if profile.product_hierarchy_values_nulled:
        st.subheader("Product hierarchy values nulled")
        st.dataframe(
            pd.DataFrame(profile.product_hierarchy_values_nulled.items(), columns=["Field", "Count"]),
            width="stretch",
        )

    if profile.categorical_numeric_contamination:
        st.subheader("Categorical/numeric contamination scan")
        st.dataframe(
            pd.DataFrame(profile.categorical_numeric_contamination.items(), columns=["Field", "Count"]),
            width="stretch",
        )

    st.subheader("KPI source-field availability")
    st.dataframe(pd.DataFrame(profile.kpi_availability.items(), columns=["KPI", "Available"]), width="stretch")

    unresolved_rows = [(sheet, col) for sheet, cols in profile.unresolved_columns_by_sheet.items() for col in cols]
    if unresolved_rows:
        st.subheader("Unresolved columns by sheet")
        st.dataframe(pd.DataFrame(unresolved_rows, columns=["Sheet", "Unresolved column"]), width="stretch")

    for label, dates in [
        ("Dates only in SALES TARGET", profile.unmatched_dates_target_only),
        ("Dates only in TIME WISE FOOTFALL-NOB", profile.unmatched_dates_footfall_only),
        ("Dates only in DAY WISE SALE", profile.unmatched_dates_fact_only),
    ]:
        if dates:
            with st.expander(f"{label} ({len(dates)})"):
                st.write(", ".join(dates))


def main() -> None:
    st.title("🛒 CITIMART Sales KPI Dashboard")
    st.caption("Standalone Streamlit build — same data pipeline and KPI/chart engines as the FastAPI/React app.")

    dataset = get_dataset()
    state = sidebar_filters(dataset)

    filtered_fact = apply_filters(dataset.fact, state)
    filtered_footfall = filter_store_level_table(dataset.footfall, state)
    filtered_target = filter_store_level_table(dataset.target, state)
    kpis = compute_kpis(filtered_fact, filtered_footfall, filtered_target)

    tab_overview, tab_trends, tab_footfall, tab_category, tab_profit, tab_scorecard, tab_quality = st.tabs(
        [
            "Overview",
            "Sales Trends",
            "Footfall & Conversion",
            "Category & Products",
            "Profitability & Discounts",
            "Store Scorecard",
            "Data Quality",
        ]
    )

    with tab_overview:
        render_overview(kpis, filtered_fact)
    with tab_trends:
        render_trends(filtered_fact, filtered_footfall, filtered_target)
    with tab_footfall:
        render_footfall(filtered_footfall)
    with tab_category:
        render_category(filtered_fact)
    with tab_profit:
        render_profitability(filtered_fact, filtered_footfall, filtered_target)
    with tab_scorecard:
        render_scorecard(filtered_fact, filtered_footfall, filtered_target)
    with tab_quality:
        render_data_quality(dataset)


if __name__ == "__main__":
    main()
