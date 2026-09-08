"""CITIMART Sales Forecasting -- standalone Streamlit app (Phase B).

Run with:
    streamlit run streamlit_forecast_app.py

Sibling to streamlit_app.py: reuses src/data_loader, src/formatting,
src/tables (CSV export), config/settings (STORE_CODE_TO_NAME, TIME_SLOT_ORDER)
and the new config/forecast_settings + src/forecasting/ package. Does not
touch app.py/FastAPI/React. Shares DATASET.xlsx and .cache/cleaned_master.pkl
(read-only) with streamlit_app.py; forecast results get their own
.cache/forecasts/ namespace (src/forecasting/cache.py).
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config.forecast_settings import (
    DEFAULT_HORIZON,
    FORECAST_HORIZON_CHOICES,
    MIN_HISTORY_DAYS_FOR_FORECAST,
    PRIMARY_MODEL_ROSTER,
    PRODUCT_FORECAST_LEVELS,
    TOP_N_PRODUCTS,
    TOP_N_VENDORS,
)
from config.settings import DATASET_PATH, STORE_CODE_TO_NAME, TIME_SLOT_ORDER
from src import formatting, tables
from src.data_loader import load_master_dataset
from src.forecasting import charts as fcharts
from src.forecasting.cache import forecast_cache_key, load_cached_forecast, save_forecast_cache
from src.forecasting.orchestrator import (
    ForecastBundle,
    forecast_daily_sales,
    forecast_footfall_nob,
    forecast_products,
    forecast_vendors,
    growth_trajectory_needed,
)
from src.forecasting.promo_effectiveness import promo_uplift_table, top_promo_campaigns_table
from src.forecasting.series_prep import build_target_aligned_series, daily_sales_series_id, footfall_nob_series_id
from src.streamlit_theme import theme_selector, themed_figure

st.set_page_config(page_title="CITIMART Sales Forecasting", page_icon="📈", layout="wide")


@st.cache_resource(show_spinner="Loading and cleaning DATASET.xlsx (cached after first run)...")
def get_dataset():
    return load_master_dataset()


def to_figure(fig_dict: dict) -> go.Figure:
    # Neon-recoloured when the sidebar Theme toggle is on Neon; identity otherwise.
    return themed_figure(fig_dict)


def download_button(df: pd.DataFrame, filename: str, label: str = "Download CSV") -> None:
    if df.empty:
        return
    st.download_button(label, data=tables.dataframe_to_csv_bytes(df), file_name=filename, mime="text/csv")


def scope_to_selected_stores(df: pd.DataFrame, stores: list[str]) -> pd.DataFrame:
    if "store_code" not in df.columns:
        return df
    return df.loc[df["store_code"].isin(stores)]


def cached_result(series_id: str, horizon: int, model_set: list[str], compute_fn, force_refresh: bool):
    """Generic over a single ForecastBundle (Sales/Footfall tabs) or a
    dict[str, ForecastBundle] (Products/Vendors tabs) -- src/forecasting/cache.py's
    pickle layer doesn't care which, it just round-trips whatever compute_fn
    returns. Two cache layers: that on-disk pickle (cross-process, invalidated
    by DATASET.xlsx mtime -- survives closing and reopening this app) plus
    st.cache_resource's own in-process caching for repeat calls within one
    live session on top of that. Both are keyed off the same (series_id,
    horizon, model_set) triple."""
    model_set_tuple = tuple(sorted(model_set))
    key = forecast_cache_key(series_id, horizon, model_set_tuple)
    source_mtime = DATASET_PATH.stat().st_mtime
    if not force_refresh:
        cached = load_cached_forecast(key, source_mtime)
        if cached is not None:
            return cached
    bundle = compute_fn()
    save_forecast_cache(key, bundle, source_mtime)
    return bundle


def cached_result_with_button(series_id: str, horizon: int, model_set: list[str], compute_fn, force_refresh: bool, session_key: str, button_label: str, pending_message: str):
    """Like cached_result, but for the multi-series Products/Vendors tabs --
    Streamlit runs every tab's code on every script rerun regardless of which
    tab is visually active (st.tabs() only toggles CSS visibility), so an
    auto-computing top-N forecast (21 series x several models each, with a
    per-series ARIMA order search) would make EVERY page load slow even for a
    user who never opens these tabs. This only computes when: an on-disk
    cache already exists for the exact (series_id, horizon, model_set) triple
    (silent, instant), a matching result is already in this session's state
    (also instant, avoids re-reading the pickle every rerun), or the user
    explicitly clicks the button."""
    model_set_tuple = tuple(sorted(model_set))
    key = forecast_cache_key(series_id, horizon, model_set_tuple)
    source_mtime = DATASET_PATH.stat().st_mtime
    cache_identity = (key, source_mtime)

    session_entry = st.session_state.get(session_key)
    if not force_refresh and session_entry is not None and session_entry["identity"] == cache_identity:
        return session_entry["result"]

    if not force_refresh:
        cached = load_cached_forecast(key, source_mtime)
        if cached is not None:
            st.session_state[session_key] = {"identity": cache_identity, "result": cached}
            return cached

    run_clicked = st.button(button_label, key=f"{session_key}_button")
    if not run_clicked:
        st.info(pending_message)
        return None

    with st.spinner("Training and backtesting models — this can take a few minutes for many series..."):
        result = compute_fn()
    save_forecast_cache(key, result, source_mtime)
    st.session_state[session_key] = {"identity": cache_identity, "result": result}
    return result


def sidebar_controls(dataset) -> dict:
    fact = dataset.fact
    theme_selector()
    st.sidebar.header("Forecast Controls")

    store_options = sorted(fact["store_code"].dropna().unique().tolist()) if "store_code" in fact.columns else []
    selected_stores = st.sidebar.multiselect(
        "Store",
        options=store_options,
        default=store_options,
        format_func=lambda code: STORE_CODE_TO_NAME.get(code, code),
        key="fc_stores",
    )
    horizon = st.sidebar.selectbox(
        "Forecast Horizon (days)", options=FORECAST_HORIZON_CHOICES,
        index=FORECAST_HORIZON_CHOICES.index(DEFAULT_HORIZON), key="fc_horizon",
    )
    model_set = st.sidebar.multiselect("Models to Compare", options=PRIMARY_MODEL_ROSTER, default=PRIMARY_MODEL_ROSTER, key="fc_model_set")
    force_refresh = st.sidebar.checkbox("Force refresh (ignore cache)", value=False, key="fc_force_refresh")

    st.sidebar.caption(
        "Only 181 days of history exist (Jan-Jun 2026, one calendar year) -- "
        "there is no learnable yearly seasonality yet. Confidence bands widen "
        "the further out a forecast goes; treat long horizons as directional, "
        "not precise."
    )

    if not selected_stores:
        st.sidebar.warning("Select at least one store.")

    return {
        "stores": selected_stores or store_options,
        "horizon": horizon,
        "model_set": model_set or PRIMARY_MODEL_ROSTER,
        "force_refresh": force_refresh,
    }


def render_sales_forecast(fact: pd.DataFrame, target: pd.DataFrame, controls: dict) -> ForecastBundle | None:
    st.subheader("Sales Forecast")
    stores = controls["stores"]
    horizon, model_set = controls["horizon"], controls["model_set"]

    store_choice = st.selectbox(
        "Store",
        options=["All Stores"] + stores,
        format_func=lambda s: s if s == "All Stores" else STORE_CODE_TO_NAME.get(s, s),
        key="sf_store_choice",
    )
    store_code = None if store_choice == "All Stores" else store_choice

    scoped_fact = scope_to_selected_stores(fact, stores)
    scoped_target = scope_to_selected_stores(target, stores)
    series_id = daily_sales_series_id(store_code)

    def _compute() -> ForecastBundle:
        return forecast_daily_sales(scoped_fact, scoped_target, store_code=store_code, horizon=horizon, model_set=model_set)

    with st.spinner("Training and backtesting models — first run only, cached after..."):
        bundle = cached_result(series_id, horizon, model_set, _compute, controls["force_refresh"])

    if bundle.insufficient_history:
        st.warning(f"Not enough history to forecast this series yet (need at least {MIN_HISTORY_DAYS_FOR_FORECAST} days).")
        return None

    st.plotly_chart(
        to_figure(fcharts.forecast_line_chart(bundle.history, bundle.forecast, f"{bundle.label} — {horizon}-Day Forecast", "Net Sales")),
        width="stretch", theme=None,
    )
    st.caption(f"Best model: **{bundle.best_model}** (lowest backtest MAPE) — see the leaderboard below for every model tried.")

    with st.expander("Model Leaderboard"):
        st.plotly_chart(to_figure(fcharts.leaderboard_chart(bundle.leaderboard, "mape")), width="stretch", theme=None)
        st.dataframe(bundle.leaderboard, width="stretch")
        download_button(bundle.leaderboard, "sales_forecast_leaderboard.csv")

    download_button(bundle.forecast, "sales_forecast.csv")

    st.markdown("#### Growth / Up-Scaling Goal")
    target_series = build_target_aligned_series(scoped_target, store_code=store_code)
    default_daily_target = float(target_series.tail(28).mean()) if not target_series.empty else 0.0
    default_target_total = default_daily_target * horizon

    target_total_input = st.number_input(
        f"Target Net Sales for the next {horizon} days",
        min_value=0.0, value=float(default_target_total), step=1000.0, key="sf_target_total",
        help="Defaults to the trailing daily SALES TARGET x horizon; override with your own goal.",
    )
    recent_avg_daily = float(bundle.history["y"].tail(28).mean()) if not bundle.history.empty else 0.0
    goal = growth_trajectory_needed(recent_avg_daily, target_total_input, horizon)

    g1, g2, g3 = st.columns(3)
    g1.metric("Current Avg Daily Sales", formatting.format_currency(goal["current_avg_daily"]))
    g2.metric("Required Avg Daily Sales", formatting.format_currency(goal["required_avg_daily"]))
    uplift_display = f"{goal['uplift_pct']:.1f}%" if goal["uplift_pct"] is not None else "N/A"
    g3.metric("Uplift Needed", uplift_display)
    st.caption("✅ Achievable at current pace" if goal["achievable_at_current_pace"] else "⚠️ Needs acceleration above current pace")

    st.plotly_chart(
        to_figure(fcharts.growth_trajectory_chart(goal["current_avg_daily"], goal["required_avg_daily"], target_total_input)),
        width="stretch", theme=None,
    )

    return bundle


def render_footfall_forecast(footfall: pd.DataFrame, controls: dict) -> ForecastBundle | None:
    st.subheader("Footfall & NOB Forecast — by Time Slot")
    stores = controls["stores"]
    horizon, model_set = controls["horizon"], controls["model_set"]

    c1, c2, c3 = st.columns(3)
    store_code = c1.selectbox("Store", options=stores, format_func=lambda s: STORE_CODE_TO_NAME.get(s, s), key="ff_store")
    slot_choice = c2.selectbox("Time Slot", options=["All Slots Summed"] + TIME_SLOT_ORDER, key="ff_slot")
    time_slot = None if slot_choice == "All Slots Summed" else slot_choice
    value_label = c3.selectbox("Metric", options=["Footfall", "NOB (Transactions)"], key="ff_value_col")
    value_col = "footfall" if value_label == "Footfall" else "nob"

    series_id = footfall_nob_series_id(store_code, time_slot, value_col)

    def _compute() -> ForecastBundle:
        return forecast_footfall_nob(footfall, store_code, time_slot, value_col, horizon=horizon, model_set=model_set)

    with st.spinner("Training and backtesting models — first run only, cached after..."):
        bundle = cached_result(series_id, horizon, model_set, _compute, controls["force_refresh"])

    if bundle.insufficient_history:
        st.warning(f"Not enough history to forecast this series yet (need at least {MIN_HISTORY_DAYS_FOR_FORECAST} days).")
        return None

    y_label = "Number of Bills" if value_col == "nob" else "Footfall Count"
    st.plotly_chart(
        to_figure(fcharts.forecast_line_chart(bundle.history, bundle.forecast, f"{bundle.label} — {horizon}-Day Forecast", y_label)),
        width="stretch", theme=None,
    )
    st.caption(f"Best model: **{bundle.best_model}** (lowest backtest MAPE) — see the leaderboard below for every model tried.")
    if time_slot is not None:
        st.caption(
            "This forecast is scoped to a single time-of-day band (from TIME WISE FOOTFALL-NOB), "
            "not summed across the whole day -- switch 'Time Slot' to 'All Slots Summed' for a store-level daily view."
        )

    with st.expander("Model Leaderboard"):
        st.plotly_chart(to_figure(fcharts.leaderboard_chart(bundle.leaderboard, "mape")), width="stretch", theme=None)
        st.dataframe(bundle.leaderboard, width="stretch")
        download_button(bundle.leaderboard, "footfall_nob_forecast_leaderboard.csv")

    download_button(bundle.forecast, "footfall_nob_forecast.csv")

    return bundle


def render_backtest_tab(sales_bundle: ForecastBundle | None, footfall_bundle: ForecastBundle | None) -> None:
    st.subheader("Actual vs Estimation (Backtest)")
    st.info(
        "This compares each model's held-out backtest predictions against what actually happened on those "
        "same historical days -- it is not a preview of the real future (DATASET.xlsx has no actuals beyond "
        "its own last date yet). It will keep working the same way once new months are appended to the workbook."
    )

    available: dict[str, ForecastBundle] = {}
    if sales_bundle is not None and not sales_bundle.leaderboard.empty:
        available[f"Sales Forecast: {sales_bundle.label}"] = sales_bundle
    if footfall_bundle is not None and not footfall_bundle.leaderboard.empty:
        available[f"Footfall/NOB Forecast: {footfall_bundle.label}"] = footfall_bundle

    if not available:
        st.warning("No backtested forecast is available yet — visit the Sales Forecast or Footfall & NOB tabs first.")
        return

    series_choice = st.selectbox("Series", options=list(available.keys()), key="bt_series_choice")
    bundle = available[series_choice]

    model_options = list(bundle.backtest_results.keys())
    default_model = bundle.best_model if bundle.best_model in model_options else (model_options[0] if model_options else None)
    model_choice = st.selectbox(
        "Model", options=model_options,
        index=model_options.index(default_model) if default_model else 0,
        key="bt_model_choice",
    )

    backtest_result = bundle.backtest_results[model_choice]
    st.plotly_chart(to_figure(fcharts.backtest_actual_vs_predicted_chart(backtest_result.fold_scores)), width="stretch", theme=None)

    fold_table = pd.DataFrame(
        [
            {
                "fold": fs.fold_index, "test_start": fs.test_start, "test_end": fs.test_end,
                "mape": fs.mape, "rmse": fs.rmse, "mae": fs.mae, "wape": fs.wape, "error": fs.error,
            }
            for fs in backtest_result.fold_scores
        ]
    )
    st.dataframe(fold_table, width="stretch")
    download_button(fold_table, "backtest_fold_scores.csv")


def _render_topn_drill_in(bundles: dict[str, ForecastBundle], entity_key: str, horizon: int, download_prefix: str) -> None:
    entity_choice = st.selectbox("Drill in", options=list(bundles.keys()), key=entity_key)
    entity_bundle = bundles[entity_choice]
    if entity_bundle.insufficient_history:
        st.warning("Not enough history to forecast this entity yet.")
        return
    st.plotly_chart(
        to_figure(fcharts.forecast_line_chart(entity_bundle.history, entity_bundle.forecast, f"{entity_bundle.label} — {horizon}-Day Forecast", "Net Sales")),
        width="stretch", theme=None,
    )
    st.caption(f"Best model: **{entity_bundle.best_model}** (lowest backtest WAPE — the zero-sales-day-robust metric used for per-entity series).")
    with st.expander("Model Leaderboard"):
        st.plotly_chart(to_figure(fcharts.leaderboard_chart(entity_bundle.leaderboard, "wape")), width="stretch", theme=None)
        st.dataframe(entity_bundle.leaderboard, width="stretch")
    download_button(entity_bundle.forecast, f"{download_prefix}_{entity_choice}.csv")


def _topn_summary_table(bundles: dict[str, ForecastBundle], entity_label: str) -> pd.DataFrame:
    rows = [
        {
            entity_label: name,
            "forecast_total": float(b.forecast["point"].sum()) if not b.insufficient_history and not b.forecast.empty else None,
            "best_model": b.best_model,
        }
        for name, b in bundles.items()
    ]
    return pd.DataFrame(rows).sort_values("forecast_total", ascending=False, na_position="last").reset_index(drop=True)


def render_products_tab(fact: pd.DataFrame, controls: dict) -> None:
    st.subheader("Best Products — Future Sales Forecast")
    st.caption("Forecast at product_style/department level -- item_code has 35,559 unique values, too granular to forecast individually.")
    horizon, model_set = controls["horizon"], controls["model_set"]
    scoped_fact = scope_to_selected_stores(fact, controls["stores"])

    c1, c2 = st.columns(2)
    level = c1.radio("Forecast Level", options=PRODUCT_FORECAST_LEVELS, format_func=lambda l: l.replace("_", " ").title(), key="pr_level", horizontal=True)
    top_n = c2.slider("Top N", min_value=5, max_value=30, value=TOP_N_PRODUCTS, key="pr_top_n")

    series_id = f"products|level={level}|top_n={top_n}|stores={','.join(sorted(controls['stores']))}"

    def _compute() -> dict[str, ForecastBundle]:
        return forecast_products(scoped_fact, level, horizon=horizon, top_n=top_n, model_set=model_set)

    bundles = cached_result_with_button(
        series_id, horizon, model_set, _compute, controls["force_refresh"],
        session_key="pr_bundles",
        button_label=f"Run Product Forecast ({top_n + 1} series)",
        pending_message=f"Backtests {len(model_set)} model(s) across {top_n + 1} series (top {top_n} {level.replace('_', ' ')}s + Other) — can take a few minutes on first run, instant once cached.",
    )
    if bundles is None:
        return  # pending message already shown above
    if not bundles:
        st.info("No product data available for the selected stores.")
        return

    st.plotly_chart(
        to_figure(fcharts.topn_forecast_bar_chart(bundles, f"Top {top_n} {level.replace('_', ' ').title()}s — {horizon}-Day Forecast Total")),
        width="stretch", theme=None,
    )
    _render_topn_drill_in(bundles, "pr_drill_in", horizon, "product_forecast")

    summary_table = _topn_summary_table(bundles, level)
    st.dataframe(summary_table, width="stretch")
    download_button(summary_table, "products_forecast_summary.csv")


def render_vendors_tab(fact: pd.DataFrame, controls: dict) -> None:
    st.subheader("Vendor Performance — Future Sales Forecast")
    st.caption("1,320 unique vendors exist -- forecasting scopes to the top-N by revenue, with everything else rolled into 'Other'.")
    horizon, model_set = controls["horizon"], controls["model_set"]
    scoped_fact = scope_to_selected_stores(fact, controls["stores"])

    top_n = st.slider("Top N Vendors", min_value=5, max_value=30, value=TOP_N_VENDORS, key="ve_top_n")
    series_id = f"vendors|top_n={top_n}|stores={','.join(sorted(controls['stores']))}"

    def _compute() -> dict[str, ForecastBundle]:
        return forecast_vendors(scoped_fact, horizon=horizon, top_n=top_n, model_set=model_set)

    bundles = cached_result_with_button(
        series_id, horizon, model_set, _compute, controls["force_refresh"],
        session_key="ve_bundles",
        button_label=f"Run Vendor Forecast ({top_n + 1} series)",
        pending_message=f"Backtests {len(model_set)} model(s) across {top_n + 1} series (top {top_n} vendors + Other) — can take a few minutes on first run, instant once cached.",
    )
    if bundles is None:
        return  # pending message already shown above
    if not bundles:
        st.info("No vendor data available for the selected stores.")
        return

    st.plotly_chart(
        to_figure(fcharts.topn_forecast_bar_chart(bundles, f"Top {top_n} Vendors — {horizon}-Day Forecast Total")),
        width="stretch", theme=None,
    )
    _render_topn_drill_in(bundles, "ve_drill_in", horizon, "vendor_forecast")

    summary_table = _topn_summary_table(bundles, "vendor")
    st.dataframe(summary_table, width="stretch")
    download_button(summary_table, "vendors_forecast_summary.csv")


def render_promotions_tab(fact: pd.DataFrame, controls: dict) -> None:
    st.subheader("Promotions Effectiveness")
    st.info(
        "DATASET.xlsx has no forward-looking promo calendar -- there is no signal to forecast 'which promotions "
        "will run when.' This tab instead measures how much each historical promo type and named campaign lifted "
        "sales versus a no-promo baseline, to help plan future promotions rather than predict them."
    )

    scoped_fact = scope_to_selected_stores(fact, controls["stores"])

    st.markdown("#### Promo Type Effectiveness")
    uplift_table = promo_uplift_table(scoped_fact)
    if uplift_table.empty:
        st.warning("No promo_type data available for the selected stores.")
    else:
        st.plotly_chart(to_figure(fcharts.promo_uplift_chart(uplift_table)), width="stretch", theme=None)
        st.dataframe(uplift_table, width="stretch")
        download_button(uplift_table, "promo_type_effectiveness.csv")

    st.markdown("#### Top Named Campaigns")
    top_n = st.slider("Top N Campaigns", min_value=5, max_value=30, value=15, key="pm_top_n")
    campaigns_table = top_promo_campaigns_table(scoped_fact, top_n=top_n)
    if campaigns_table.empty:
        st.info("No named promo campaigns found in the selected stores.")
    else:
        st.dataframe(campaigns_table, width="stretch")
        download_button(campaigns_table, "top_promo_campaigns.csv")


def render_overview_tab(sales_bundle: ForecastBundle | None, footfall_bundle: ForecastBundle | None, controls: dict) -> None:
    st.subheader("Forecasting Overview")
    horizon = controls["horizon"]

    if sales_bundle is None:
        st.info(
            "Not enough history to build a Sales Forecast yet, so there's nothing to summarize here — "
            "see the 'Sales Forecast & Growth Goals' tab for details."
        )
        return

    total_forecast = float(sales_bundle.forecast["point"].sum())
    total_lower = float(sales_bundle.forecast["lower"].sum())
    total_upper = float(sales_bundle.forecast["upper"].sum())
    recent_avg_daily = float(sales_bundle.history["y"].tail(28).mean()) if not sales_bundle.history.empty else 0.0
    flat_continuation = recent_avg_daily * horizon

    c1, c2 = st.columns(2)
    c1.metric("Flat Continuation of Current Pace", formatting.format_currency(flat_continuation), help="Last 28 days' average daily sales x horizon -- what you'd get with zero growth or decline.")
    c2.metric(f"Model Forecast Total ({horizon} days)", formatting.format_currency(total_forecast))
    st.caption(f"90% confidence range: {formatting.format_currency(total_lower)} – {formatting.format_currency(total_upper)}")

    delta = total_forecast - flat_continuation
    if delta > 0:
        st.caption(f"The model-based forecast total is **above** a flat continuation of current pace by {formatting.format_currency(delta)}.")
    elif delta < 0:
        st.caption(f"The model-based forecast total is **below** a flat continuation of current pace by {formatting.format_currency(abs(delta))}.")
    else:
        st.caption("The model-based forecast total is in line with a flat continuation of current pace.")

    st.markdown("#### Model Selection Summary")
    summary_rows = []
    for bundle in (sales_bundle, footfall_bundle):
        if bundle is None or bundle.leaderboard.empty:
            continue
        best_row = bundle.leaderboard.loc[bundle.leaderboard["model"] == bundle.best_model]
        summary_rows.append(
            {
                "series": bundle.label,
                "best_model": bundle.best_model,
                "backtest_mape": float(best_row["mean_mape"].iloc[0]) if not best_row.empty and pd.notna(best_row["mean_mape"].iloc[0]) else None,
            }
        )
    if summary_rows:
        st.dataframe(pd.DataFrame(summary_rows), width="stretch")

    st.caption(
        "This overview covers the Sales Forecast and Footfall & NOB series computed above. "
        "Time-slot footfall/NOB, top-product/vendor forecasts, and promo effectiveness each have their own "
        "model leaderboard and backtest view on their own tabs."
    )


def main() -> None:
    st.title("📈 CITIMART Sales Forecasting")
    st.caption("Standalone Streamlit build — Phase B forecasting engine on top of the same data pipeline as the KPI dashboard.")

    dataset = get_dataset()
    controls = sidebar_controls(dataset)

    tab_overview, tab_sales, tab_footfall, tab_backtest, tab_products, tab_vendors, tab_promo = st.tabs(
        [
            "Overview",
            "Sales Forecast & Growth Goals",
            "Footfall & NOB by Time Slot",
            "Actual vs Estimation (Backtest)",
            "Products",
            "Vendors",
            "Promotions Effectiveness",
        ]
    )

    with tab_sales:
        sales_bundle = render_sales_forecast(dataset.fact, dataset.target, controls)
    with tab_footfall:
        footfall_bundle = render_footfall_forecast(dataset.footfall, controls)
    with tab_backtest:
        render_backtest_tab(sales_bundle, footfall_bundle)
    with tab_products:
        render_products_tab(dataset.fact, controls)
    with tab_vendors:
        render_vendors_tab(dataset.fact, controls)
    with tab_promo:
        render_promotions_tab(dataset.fact, controls)
    with tab_overview:
        render_overview_tab(sales_bundle, footfall_bundle, controls)


if __name__ == "__main__":
    main()
