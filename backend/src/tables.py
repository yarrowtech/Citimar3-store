"""Table-view builders shared by every analytical section (master prompt
Section 16): sortable, downloadable, currency/percentage formatted, always
scoped to the currently active filters -- never the raw unfiltered dataset.
"""
from __future__ import annotations

import io
from datetime import date, timedelta

import pandas as pd

from src import period_engine
from src.comparison_engine import same_period_last_year_window


def dataframe_to_csv_bytes(df: pd.DataFrame) -> bytes:
    buffer = io.StringIO()
    df.to_csv(buffer, index=False)
    return buffer.getvalue().encode("utf-8-sig")  # BOM so Excel renders ₹ correctly


def same_period_year_over_year_table(fact: pd.DataFrame, start: date | None, end: date | None) -> pd.DataFrame:
    """Day-by-day Net Sales for the selected period next to the same
    calendar day one year earlier -- the "yearly / same month / same day"
    comparison. Day-offset aligned via comparison_engine's own
    same_period_last_year_window, the identical clamp the KPI cards'
    same-period-last-year delta already uses, so a Feb 29 in either window
    doesn't misalign this table by a day the way a naive
    `date.replace(year=...)` would. `fact` must be filtered by store/product
    only, not by date -- the caller's date_free_state pattern (see
    api/routes_tables.py's kpi_table branch) -- since a row here can fall in
    either this year's or last year's window. charts.py's
    same_period_year_over_year_chart visualizes this table's own output
    directly, so the two views can never drift apart.

    A day outside `fact`'s actual date coverage (e.g. last year's date, when
    the dataset is still a single calendar year with no prior-year history)
    is None/N/A here, never a fabricated 0 -- a day *within* coverage that
    genuinely had no bills is a real 0, so the two aren't conflated."""
    if fact.empty or start is None or end is None or "date" not in fact.columns:
        return pd.DataFrame()
    prev_start, _ = same_period_last_year_window(start, end)
    days = (end - start).days + 1

    dt = fact["date"].dt.normalize()
    daily = fact.groupby(dt)["net_amount"].sum()
    data_min, data_max = dt.min(), dt.max()

    def _value_for(d: date) -> float | None:
        ts = pd.Timestamp(d)
        if pd.isna(data_min) or ts < data_min or ts > data_max:
            return None
        value = daily.get(ts)
        return float(value) if pd.notna(value) else 0.0

    rows = []
    for i in range(days):
        cur_date = start + timedelta(days=i)
        prev_date = prev_start + timedelta(days=i)
        cur_val = _value_for(cur_date)
        prev_val = _value_for(prev_date)
        abs_var = (cur_val - prev_val) if (cur_val is not None and prev_val is not None) else None
        pct_var = (abs_var / prev_val * 100) if (abs_var is not None and prev_val) else None
        rows.append(
            {
                "date": cur_date.isoformat(),
                "current_year_net_sales": cur_val,
                "previous_year_date": prev_date.isoformat(),
                "previous_year_net_sales": prev_val,
                "absolute_variance": abs_var,
                "percentage_variance": pct_var,
            }
        )
    return pd.DataFrame(rows)


def _first_non_null(series: pd.Series):
    non_null = series.dropna()
    return non_null.iloc[0] if not non_null.empty else pd.NA


def top_products_table(fact: pd.DataFrame, measure: str = "net_amount", top_n: int | None = 10) -> pd.DataFrame:
    if fact.empty or "item_code" not in fact.columns:
        return pd.DataFrame()
    # Group by item_code alone, not [item_code, product_style]: a handful of
    # a product's line items can have product_style nulled by
    # clean_product_hierarchy_fields's contamination scrub while the rest of
    # that same item's rows keep it, and grouping on both would silently
    # split one product's sales across two rows -- product_style here is
    # just a representative display label, not part of the product's identity.
    grouped = (
        fact.groupby("item_code", dropna=False)
        .agg(
            product_style=("product_style", _first_non_null),
            net_sales=("net_amount", "sum"),
            quantity=("bill_quantity", "sum"),
            cost=("cogs_with_gst", "sum"),
            transactions=("bill_no", "nunique"),
        )
        .reset_index()
    )
    grouped["gross_profit"] = grouped["net_sales"] - grouped["cost"]
    total = grouped["net_sales"].sum()
    grouped["share_pct"] = (grouped["net_sales"] / total * 100) if total else 0.0
    sort_col = {"net_amount": "net_sales", "quantity": "quantity", "gross_profit": "gross_profit", "transactions": "transactions"}.get(
        measure, "net_sales"
    )
    grouped = grouped.sort_values(sort_col, ascending=False).reset_index(drop=True)
    grouped.insert(0, "rank", grouped.index + 1)
    if top_n:
        grouped = grouped.head(top_n)
    return grouped


def top_brands_table(fact: pd.DataFrame, top_n: int | None = None) -> pd.DataFrame:
    if fact.empty or "product_brand" not in fact.columns:
        return pd.DataFrame()
    agg_kwargs = {
        "net_sales": ("net_amount", "sum"),
        "quantity": ("bill_quantity", "sum"),
        "transactions": ("bill_no", "nunique"),
    }
    # cost/discount/gross_amount are optional source fields (see
    # column_aliases.py) -- only aggregate what's actually resolved instead
    # of raising a KeyError on a plausible partial-schema workbook.
    for out_col, src_col in (("cost", "cogs_with_gst"), ("discount", "discount_amount"), ("gross_amount", "gross_amount")):
        if src_col in fact.columns:
            agg_kwargs[out_col] = (src_col, "sum")
    grouped = fact.groupby("product_brand", dropna=True).agg(**agg_kwargs).reset_index()
    grouped["gross_profit"] = grouped["net_sales"] - grouped["cost"] if "cost" in grouped.columns else pd.NA
    total = grouped["net_sales"].sum()
    if "discount" in grouped.columns and "gross_amount" in grouped.columns:
        grouped["discount_pct"] = (grouped["discount"] / grouped["gross_amount"] * 100).where(grouped["gross_amount"] != 0)
    else:
        grouped["discount_pct"] = pd.NA
    grouped["contribution_pct"] = (grouped["net_sales"] / total * 100) if total else 0.0
    grouped = grouped.sort_values("net_sales", ascending=False).reset_index(drop=True)
    grouped.insert(0, "rank", grouped.index + 1)
    if top_n:
        grouped = grouped.head(top_n)
    return grouped


_MEASURE_COLUMNS = {"net_amount": "net_sales", "quantity": "quantity", "gross_profit": "gross_profit", "transactions": "transactions"}


def performer_pairing_table(
    fact: pd.DataFrame,
    measure: str = "net_amount",
    group_by: str = "section",
    top_n: int | None = 10,
    min_group_size: int = 4,
) -> pd.DataFrame:
    """Within each category, pair the strongest products with the weakest so a
    low performer is always matched to a strong one of comparable rank
    distance (best with worst, 2nd-best with 2nd-worst, ...) instead of every
    pair anchoring to the single #1 product in the category.
    """
    if fact.empty or "item_code" not in fact.columns or group_by not in fact.columns:
        return pd.DataFrame()

    # Group by [group_by, item_code] alone, not also product_style -- see
    # top_products_table's comment on why including it as a groupby key
    # fragments a single product's sales.
    grouped = (
        fact.groupby([group_by, "item_code"], dropna=False)
        .agg(
            product_style=("product_style", _first_non_null),
            net_sales=("net_amount", "sum"),
            quantity=("bill_quantity", "sum"),
            cost=("cogs_with_gst", "sum"),
            transactions=("bill_no", "nunique"),
        )
        .reset_index()
    )
    grouped["gross_profit"] = grouped["net_sales"] - grouped["cost"]
    value_col = _MEASURE_COLUMNS.get(measure, "net_sales")

    pairs = []
    for category, block in grouped.groupby(group_by, dropna=False):
        if len(block) < min_group_size:
            continue
        block = block.sort_values(value_col, ascending=False).reset_index(drop=True)
        half = len(block) // 2
        for i in range(half):
            strong = block.iloc[i]
            weak = block.iloc[len(block) - 1 - i]
            strong_value = strong[value_col]
            weak_value = weak[value_col]
            gap = strong_value - weak_value
            pairs.append(
                {
                    "category": category,
                    "strong_item_code": strong["item_code"],
                    "strong_product": strong["product_style"],
                    f"strong_{value_col}": strong_value,
                    "weak_item_code": weak["item_code"],
                    "weak_product": weak["product_style"],
                    f"weak_{value_col}": weak_value,
                    f"gap_{value_col}": gap,
                    "gap_pct": (gap / strong_value * 100) if strong_value else 0.0,
                }
            )

    result = pd.DataFrame(pairs)
    if result.empty:
        return result
    result = result.sort_values(f"gap_{value_col}", ascending=False).reset_index(drop=True)
    result.insert(0, "rank", result.index + 1)
    if top_n:
        result = result.head(top_n)
    return result


# --- Product & Brand: Division / Section / Department reorganisation --------
#
# Three builders keyed on the DIVISION -> SECTION -> DEPARTMENT hierarchy that
# already backs charts.category_drilldown_chart. They replace the old per-item
# Top Products / Top Brands / (section-wise) Performer Pairing views *on the
# Product & Brand tab only* -- top_products_table / top_brands_table /
# performer_pairing_table all stay for the Detailed Tables tab, the Streamlit
# UI and api/routes_forecast.py's /huddle.

_HIERARCHY_LEVELS = ("division", "section", "department")
_LEVEL_NAME = {1: "Division", 2: "Section", 3: "Department"}


def category_net_sales_table(fact: pd.DataFrame) -> pd.DataFrame:
    """Companion to charts.category_drilldown_chart -- the Division -> Section
    -> Department hierarchy with a roll-up row at *every* level (not only the
    leaves), so one table reads top-down (generalise) and bottom-up
    (specialise). Every metric the drill-down's hover shows is a column here.

    ``cogs_with_gst`` / ``discount_amount`` are optional source fields (see
    column_aliases.py) -- guarded the same way top_brands_table does, surfaced
    as N/A (never a fabricated 0) when the workbook doesn't carry them."""
    levels = [c for c in _HIERARCHY_LEVELS if c in fact.columns]
    if fact.empty or not levels or "net_amount" not in fact.columns:
        return pd.DataFrame()

    has_cogs = "cogs_with_gst" in fact.columns
    has_discount = "discount_amount" in fact.columns
    grand_total = fact["net_amount"].sum()

    def _agg(group_cols: list[str]) -> pd.DataFrame:
        agg_kwargs = {
            "net_sales": ("net_amount", "sum"),
            "quantity": ("bill_quantity", "sum"),
            "transactions": ("bill_no", "nunique"),
        }
        if has_cogs:
            agg_kwargs["cogs_gst"] = ("cogs_with_gst", "sum")
        if has_discount:
            agg_kwargs["discount"] = ("discount_amount", "sum")
        return fact.groupby(group_cols, dropna=True).agg(**agg_kwargs).reset_index()

    # Aggregate each depth once (O(rows), not O(rows x nodes)); the recursive
    # walk below only slices these pre-computed frames.
    by_depth = {d: _agg(list(levels[:d])) for d in range(1, len(levels) + 1)}
    rows: list[dict] = []

    def _emit(depth: int, parent_values: tuple) -> None:
        frame = by_depth[depth]
        for col, val in zip(levels[: depth - 1], parent_values):
            frame = frame[frame[col] == val]
        for _, r in frame.sort_values("net_sales", ascending=False).iterrows():
            values = tuple(r[c] for c in levels[:depth])
            net = r["net_sales"]
            cogs = r["cogs_gst"] if has_cogs else pd.NA
            gross_profit = (net - cogs) if has_cogs else pd.NA
            rows.append(
                {
                    "level": _LEVEL_NAME[depth],
                    "division": str(values[0]) if depth >= 1 else "",
                    "section": str(values[1]) if depth >= 2 else "",
                    "department": str(values[2]) if depth >= 3 else "",
                    "net_sales": net,
                    "quantity": r["quantity"],
                    "transactions": r["transactions"],
                    "cogs_gst": cogs,
                    "discount": r["discount"] if has_discount else pd.NA,
                    "gross_profit": gross_profit,
                    "gross_margin_pct": (gross_profit / net * 100) if (has_cogs and net) else pd.NA,
                    "share_pct": (net / grand_total * 100) if grand_total else 0.0,
                }
            )
            if depth < len(levels):
                _emit(depth + 1, values)

    _emit(1, ())
    return pd.DataFrame(rows)


_TOP_CATEGORY_SORT = {"net_amount": "net_sales", "quantity": "quantity", "transactions": "transactions"}
# The 6 columns the Product & Brand table view is trimmed to (api/routes_tables.py).
TOP_CATEGORY_DISPLAY_COLUMNS = ["rank", "category", "net_sales", "transactions", "cogs_gst", "discount"]


def top_category_table(
    fact: pd.DataFrame, category: str = "division", measure: str = "net_amount", top_n: int | None = 10
) -> pd.DataFrame:
    """Ranked Division / Section / Department table -- the merged replacement
    for the old per-item Top Products + Top Brands tables. Ranked by ``measure``
    (``net_amount`` | ``quantity`` | ``transactions``); the returned frame also
    carries ``quantity`` for the chart, and the route trims to
    ``TOP_CATEGORY_DISPLAY_COLUMNS`` for the on-screen/report table."""
    if fact.empty or category not in fact.columns or "net_amount" not in fact.columns:
        return pd.DataFrame()
    agg_kwargs = {
        "net_sales": ("net_amount", "sum"),
        "quantity": ("bill_quantity", "sum"),
        "transactions": ("bill_no", "nunique"),
    }
    for out_col, src_col in (("cogs_gst", "cogs_with_gst"), ("discount", "discount_amount")):
        if src_col in fact.columns:
            agg_kwargs[out_col] = (src_col, "sum")
    grouped = (
        fact.groupby(category, dropna=True).agg(**agg_kwargs).reset_index().rename(columns={category: "category"})
    )
    for col in ("cogs_gst", "discount"):
        if col not in grouped.columns:
            grouped[col] = pd.NA
    sort_col = _TOP_CATEGORY_SORT.get(measure, "net_sales")
    grouped = grouped.sort_values(sort_col, ascending=False).reset_index(drop=True)
    grouped.insert(0, "rank", grouped.index + 1)
    if top_n:
        grouped = grouped.head(top_n)
    return grouped[["rank", "category", "net_sales", "quantity", "transactions", "cogs_gst", "discount"]]


def department_performer_pairing_table(
    fact: pd.DataFrame, top_n: int | None = 10, min_group_size: int = 4
) -> pd.DataFrame:
    """One row per department: its strongest and weakest product by Net Sales,
    plus a "Possible Best Paired" cross-sell suggestion for the weak performer
    -- the item most often rung up on the *same bill* as it (market-basket
    co-occurrence). Departments with fewer than ``min_group_size`` distinct
    products are skipped (too small to talk about a strong/weak spread).

    Distinct from performer_pairing_table (kept for /huddle): that one pairs
    best-with-worst *within each section* across many rows; this is a single
    per-department strong/weak summary with a data-driven pairing hint."""
    if fact.empty or "department" not in fact.columns or "item_code" not in fact.columns:
        return pd.DataFrame()

    grouped = (
        fact.groupby(["department", "item_code"], dropna=False)
        .agg(product_style=("product_style", _first_non_null), net_sales=("net_amount", "sum"))
        .reset_index()
    )
    has_bill = "bill_no" in fact.columns

    def _co_purchase(weak_code) -> str | None:
        if not has_bill:
            return None
        bills = set(fact.loc[fact["item_code"] == weak_code, "bill_no"].dropna())
        if not bills:
            return None
        co = fact.loc[fact["bill_no"].isin(bills) & (fact["item_code"] != weak_code)]
        counts = co.groupby("item_code")["bill_no"].nunique().sort_values(ascending=False) if not co.empty else co
        if len(counts) == 0:
            return None
        best_code = counts.index[0]
        style = _first_non_null(co.loc[co["item_code"] == best_code, "product_style"])
        return str(style) if pd.notna(style) else str(best_code)

    rows = []
    for department, block in grouped.groupby("department", dropna=False):
        if block["item_code"].nunique() < min_group_size:
            continue
        block = block.sort_values("net_sales", ascending=False).reset_index(drop=True)
        strong, weak = block.iloc[0], block.iloc[-1]
        rows.append(
            {
                "department": department,
                "strong_performer": strong["product_style"] if pd.notna(strong["product_style"]) else strong["item_code"],
                "strong_net_sales": strong["net_sales"],
                "weak_performer": weak["product_style"] if pd.notna(weak["product_style"]) else weak["item_code"],
                "weak_net_sales": weak["net_sales"],
                "best_paired": _co_purchase(weak["item_code"]),
                "_spread": strong["net_sales"] - weak["net_sales"],
            }
        )

    result = pd.DataFrame(rows)
    if result.empty:
        return result
    result = result.sort_values("_spread", ascending=False).drop(columns="_spread").reset_index(drop=True)
    result.insert(0, "rank", result.index + 1)
    if top_n:
        result = result.head(top_n)
    return result


def store_scorecard_table(fact: pd.DataFrame, footfall: pd.DataFrame, target: pd.DataFrame) -> pd.DataFrame:
    from src.kpi_engine import compute_kpis

    if fact.empty or "store_code" not in fact.columns:
        return pd.DataFrame()
    rows = []
    for store_code in sorted(fact["store_code"].dropna().unique()):
        store_fact = fact.loc[fact["store_code"] == store_code]
        store_footfall = footfall.loc[footfall["store_code"] == store_code] if not footfall.empty else footfall
        store_target = target.loc[target["store_code"] == store_code] if not target.empty else target
        kpis = compute_kpis(store_fact, store_footfall, store_target)
        rows.append({"store_code": store_code, **kpis.__dict__})
    scorecard = pd.DataFrame(rows)
    if not scorecard.empty:
        scorecard["rank"] = scorecard["net_sales"].rank(ascending=False, method="min").astype("Int64")
        scorecard = scorecard.sort_values("rank")
    return scorecard


_PER_PERIOD_DEFAULT_COLUMNS = [
    "net_sales", "sales_target", "remaining", "bill_quantity", "footfall", "nob",
    "atv", "rpv", "basket_size", "conversion_pct", "achievement_pct", "remaining_pct",
]


def per_period_kpi_table(
    fact: pd.DataFrame,
    footfall: pd.DataFrame,
    target: pd.DataFrame,
    period: str,
    *,
    columns: list[str] | None = None,
    fact_mask: pd.Series | None = None,
    label_prefix: str | None = None,
) -> pd.DataFrame:
    """One row per linear ``period`` bucket (via ``period_engine``), each cell a
    KpiBundle field computed by ``compute_kpis`` on that bucket's slice -- so the
    single formula source is never re-implemented. ``"remaining_pct"`` (``100 -
    achievement_pct``) is available as a pseudo-column even before it lands on
    ``KpiBundle``.

    O(n), not O(n·buckets): every frame is ``groupby``-ed on its period anchor
    **once** into ``{anchor: subframe}`` dicts, then ``compute_kpis`` runs on the
    small subframes. Never re-slice a frame by date per bucket.

    ``fact_mask`` (aligned to ``fact.index``) narrows only the fact frame -- used
    by the Discounted / Non-discounted split in ``discount_impact_table``.
    ``label_prefix`` is prepended to the ``"Date"`` label (e.g. a segment name).
    """
    from dataclasses import asdict

    from src.kpi_engine import compute_kpis

    cols = list(columns) if columns is not None else list(_PER_PERIOD_DEFAULT_COLUMNS)
    scoped_fact = fact.loc[fact_mask] if fact_mask is not None else fact

    def _bucketise(df: pd.DataFrame) -> dict:
        if df.empty or "date" not in df.columns:
            return {}
        anchor = period_engine.period_start(df["date"], period)
        return {key: block for key, block in df.groupby(anchor, dropna=True)}

    fact_buckets = _bucketise(scoped_fact)
    footfall_buckets = _bucketise(footfall)
    target_buckets = _bucketise(target)

    anchors = sorted(set(fact_buckets) | set(footfall_buckets) | set(target_buckets))
    if not anchors:
        return pd.DataFrame(columns=["Date", *cols])

    empty_fact = scoped_fact.iloc[0:0]
    empty_footfall = footfall.iloc[0:0]
    empty_target = target.iloc[0:0]

    rows = []
    for anchor in anchors:
        bundle = compute_kpis(
            fact_buckets.get(anchor, empty_fact),
            footfall_buckets.get(anchor, empty_footfall),
            target_buckets.get(anchor, empty_target),
        )
        values = asdict(bundle)
        ach = values.get("achievement_pct")
        values["remaining_pct"] = (100 - ach) if ach is not None else None
        label = period_engine.period_label(anchor, period)
        if label_prefix:
            label = f"{label_prefix}{label}"
        rows.append({"Date": label, **{col: values.get(col) for col in cols}})

    return pd.DataFrame(rows, columns=["Date", *cols])


_SALES_OVERVIEW_COLUMNS = [
    "sales_target", "net_sales", "remaining", "bill_quantity", "footfall", "nob",
    "atv", "rpv", "basket_size", "conversion_pct", "achievement_pct", "remaining_pct",
]


def sales_overview_table(fact: pd.DataFrame, footfall: pd.DataFrame, target: pd.DataFrame, period: str) -> pd.DataFrame:
    """Executive Overview's per-period KPI table (Historical Analytics Overhaul
    §1) -- a thin `per_period_kpi_table` wrapper pinned to the §1 column set and
    order. The frontend relabels the headers for display; `fmtCell` keys off
    these raw names for currency/percent formatting."""
    return per_period_kpi_table(fact, footfall, target, period, columns=_SALES_OVERVIEW_COLUMNS)


# --- Section 2 (Sales Performance) companions -- Historical Analytics Overhaul, Phase 3 ---


def sales_trend_table(fact: pd.DataFrame, footfall: pd.DataFrame, *, dimension: str = "period", granularity: str = "day") -> pd.DataFrame:
    """Companion for charts.sales_trend_chart. ``period``: Net Sales per linear
    bucket. ``timeslot``: Footfall / NOB / Conversion % across the four time
    slots."""
    if dimension == "timeslot":
        from config.settings import TIME_SLOT_ORDER

        if footfall.empty or "time_slot" not in footfall.columns:
            return pd.DataFrame()
        grouped = (
            footfall.groupby("time_slot").agg(footfall=("footfall", "sum"), nob=("nob", "sum")).reindex(TIME_SLOT_ORDER).reset_index()
        )
        grouped["conversion_pct"] = (grouped["nob"] / grouped["footfall"] * 100).where(grouped["footfall"] != 0)
        return grouped

    resampled = period_engine.resample_frame(fact, granularity, net_sales=("net_amount", "sum"))
    if resampled.empty:
        return pd.DataFrame(columns=["Date", "net_sales"])
    return resampled[["Date", "net_sales"]]


def avg_sales_table(fact: pd.DataFrame, *, granularity: str = "day") -> pd.DataFrame:
    """Companion for charts.avg_sales_chart -- mean Net Sales per cyclic bucket."""
    if fact.empty or "date" not in fact.columns:
        return pd.DataFrame(columns=["bucket", "avg_net_sales"])
    keys, order = period_engine.seasonal_key(fact["date"], granularity)
    grouped = fact.assign(_seasonal_key=keys.values).groupby("_seasonal_key")["net_amount"].mean().reindex(order)
    return pd.DataFrame({"bucket": [str(o) for o in order], "avg_net_sales": grouped.values})


def period_comparison_table(fact: pd.DataFrame, *, dimension: str = "monthly_same_day", day_limit: int = 20) -> pd.DataFrame:
    """Companion for charts.period_comparison_chart -- long format (one row per
    bucket × cohort) so `net_sales` keeps its currency formatting rather than
    spreading across dynamically-named wide columns. ``same_period_yoy`` mode
    reuses same_period_year_over_year_table in the route instead of this."""
    if fact.empty:
        return pd.DataFrame()
    from src.charts import DAY_ORDER, MONTH_ORDER

    if dimension == "yearly_month":
        if "year" not in fact.columns or "month_name" not in fact.columns:
            return pd.DataFrame()
        grouped = fact.groupby(["month_name", "year"], dropna=True)["net_amount"].sum().reset_index()
        grouped["month_name"] = pd.Categorical(grouped["month_name"], categories=MONTH_ORDER, ordered=True)
        grouped = grouped.sort_values(["year", "month_name"])
        return pd.DataFrame(
            {"month": grouped["month_name"].astype(str), "year": grouped["year"].astype("Int64"), "net_sales": grouped["net_amount"].values}
        )

    if dimension == "weekly_same_day":
        if "day_name" not in fact.columns or "date" not in fact.columns:
            return pd.DataFrame()
        df = fact.copy()
        anchor = period_engine.period_start(df["date"], "week")
        df["_anchor"] = anchor.values
        df["week"] = period_engine.period_label(anchor, "week").values
        grouped = df.groupby(["_anchor", "week", "day_name"], dropna=True)["net_amount"].sum().reset_index()
        grouped["day_name"] = pd.Categorical(grouped["day_name"], categories=DAY_ORDER, ordered=True)
        grouped = grouped.sort_values(["_anchor", "day_name"])
        return pd.DataFrame(
            {"day_of_week": grouped["day_name"].astype(str), "week": grouped["week"].values, "net_sales": grouped["net_amount"].values}
        )

    # monthly_same_day (default)
    if "day_of_month" not in fact.columns or "year_month" not in fact.columns:
        return pd.DataFrame()
    scoped = fact.loc[fact["day_of_month"] <= day_limit]
    grouped = scoped.groupby(["year_month", "day_of_month"], dropna=True)["net_amount"].sum().reset_index()
    grouped = grouped.sort_values(["year_month", "day_of_month"])
    return pd.DataFrame(
        {"day_of_month": grouped["day_of_month"].astype("Int64"), "month": grouped["year_month"].astype(str), "net_sales": grouped["net_amount"].values}
    )


# --- Section 3 (Customer & Conversion) companions ---------------------------


def _weekday_labels(dates: pd.Series) -> pd.Series:
    from src.charts import WEEKDAY_TO_LABEL

    return dates.dt.dayofweek.map(WEEKDAY_TO_LABEL)


def footfall_vs_nob_table(footfall: pd.DataFrame, *, dimension: str = "date") -> pd.DataFrame:
    """Companion for charts.footfall_vs_nob_chart -- Footfall / NOB / Conversion %
    per date (``date``) or per TIME WISE FOOTFALL-NOB band (``timeslot``)."""
    from config.settings import TIME_SLOT_ORDER

    if footfall.empty:
        return pd.DataFrame(columns=["time_slot" if dimension == "timeslot" else "date", "footfall", "nob", "conversion_pct"])
    if dimension == "timeslot":
        if "time_slot" not in footfall.columns:
            return pd.DataFrame(columns=["time_slot", "footfall", "nob", "conversion_pct"])
        grouped = (
            footfall.groupby("time_slot").agg(footfall=("footfall", "sum"), nob=("nob", "sum")).reindex(TIME_SLOT_ORDER).reset_index()
        )
    else:
        grouped = (
            footfall.groupby(footfall["date"].dt.normalize().dt.strftime("%Y-%m-%d"))
            .agg(footfall=("footfall", "sum"), nob=("nob", "sum"))
            .reset_index()
        )
    grouped["conversion_pct"] = (grouped["nob"] / grouped["footfall"] * 100).where(grouped["footfall"] != 0)
    return grouped


def visitor_vs_net_sales_table(
    footfall: pd.DataFrame, fact: pd.DataFrame, *, metric: str = "footfall", dimension: str = "date"
) -> pd.DataFrame:
    """Companion for charts.footfall_vs_net_sales_chart -- the visitor metric
    (``footfall`` | ``nob``) next to Net Sales, joined by date, cut by ``date``
    or ``dayofweek``. No time-slot cut (Net Sales has no bill-time granularity)."""
    from src.charts import DAY_ORDER

    label_col = "day_of_week" if dimension == "dayofweek" else "date"
    if footfall.empty and fact.empty:
        return pd.DataFrame(columns=[label_col, metric, "net_sales"])

    if dimension == "dayofweek":
        f = _weekday_labels(footfall["date"]) if not footfall.empty else pd.Series(dtype=object)
        s = _weekday_labels(fact["date"]) if not fact.empty else pd.Series(dtype=object)
        f_sum = footfall.assign(_k=f).groupby("_k")[metric].sum() if not footfall.empty else pd.Series(dtype=float)
        s_sum = fact.assign(_k=s).groupby("_k")["net_amount"].sum() if not fact.empty else pd.Series(dtype=float)
        order = [d for d in DAY_ORDER if d in set(f_sum.index) | set(s_sum.index)]
        f_sum, s_sum = f_sum.reindex(order), s_sum.reindex(order)
        return pd.DataFrame({label_col: order, metric: f_sum.values, "net_sales": s_sum.values})

    f_sum = (
        footfall.groupby(footfall["date"].dt.normalize().dt.strftime("%Y-%m-%d"))[metric].sum()
        if not footfall.empty else pd.Series(dtype=float)
    )
    s_sum = (
        fact.groupby(fact["date"].dt.normalize().dt.strftime("%Y-%m-%d"))["net_amount"].sum()
        if not fact.empty else pd.Series(dtype=float)
    )
    idx = sorted(set(f_sum.index) | set(s_sum.index))
    f_sum, s_sum = f_sum.reindex(idx), s_sum.reindex(idx)
    return pd.DataFrame({label_col: idx, metric: f_sum.values, "net_sales": s_sum.values})


def footfall_nob_breakdown_table(footfall: pd.DataFrame, *, dimension: str = "dayofweek") -> pd.DataFrame:
    """Companion for charts.footfall_nob_breakdown_chart -- Footfall / NOB /
    Conversion % per bucket (``dayofweek`` | ``timeslot`` | ``date``)."""
    from config.settings import TIME_SLOT_ORDER

    from src.charts import DAY_ORDER

    if footfall.empty:
        return pd.DataFrame(columns=["bucket", "footfall", "nob", "conversion_pct"])
    if dimension == "timeslot":
        if "time_slot" not in footfall.columns:
            return pd.DataFrame(columns=["bucket", "footfall", "nob", "conversion_pct"])
        grouped = footfall.groupby("time_slot").agg(footfall=("footfall", "sum"), nob=("nob", "sum")).reindex(TIME_SLOT_ORDER)
        buckets = TIME_SLOT_ORDER
    elif dimension == "date":
        grouped = footfall.groupby(footfall["date"].dt.normalize().dt.strftime("%Y-%m-%d")).agg(
            footfall=("footfall", "sum"), nob=("nob", "sum")
        )
        buckets = list(grouped.index)
    else:
        grouped = (
            footfall.assign(_k=_weekday_labels(footfall["date"]))
            .groupby("_k")
            .agg(footfall=("footfall", "sum"), nob=("nob", "sum"))
            .reindex(DAY_ORDER)
        )
        buckets = DAY_ORDER
    out = pd.DataFrame({
        "bucket": list(buckets),
        "footfall": grouped["footfall"].values,
        "nob": grouped["nob"].values,
    })
    out["conversion_pct"] = (out["nob"] / out["footfall"] * 100).where(out["footfall"] != 0)
    return out


def conversion_funnel_table(
    footfall: pd.DataFrame, footfall_total: float | None, nob_total: float | None, *, dimension: str = "date"
) -> pd.DataFrame:
    """Companion for the Conversion Funnel. ``date``: the two whole-range stages
    with each stage's % of Footfall. ``timeslot``: one row per band with its
    own Footfall / Transactions / Conversion %."""
    from config.settings import TIME_SLOT_ORDER

    if dimension == "timeslot":
        if footfall.empty or "time_slot" not in footfall.columns:
            return pd.DataFrame(columns=["time_slot", "footfall", "nob", "conversion_pct"])
        grouped = (
            footfall.groupby("time_slot").agg(footfall=("footfall", "sum"), nob=("nob", "sum")).reindex(TIME_SLOT_ORDER).reset_index()
        )
        grouped["conversion_pct"] = (grouped["nob"] / grouped["footfall"] * 100).where(grouped["footfall"] != 0)
        return grouped

    if footfall_total is None and nob_total is None:
        return pd.DataFrame(columns=["stage", "value", "conversion_pct"])
    base = footfall_total if footfall_total else None
    rows = [
        {"stage": "Footfall", "value": footfall_total, "conversion_pct": 100.0 if base else None},
        {
            "stage": "Transactions",
            "value": nob_total,
            "conversion_pct": (nob_total / base * 100) if (base and nob_total is not None) else None,
        },
    ]
    return pd.DataFrame(rows)


def secondary_gauge_values_table(fact: pd.DataFrame, footfall: pd.DataFrame, target: pd.DataFrame) -> pd.DataFrame:
    """The value + status behind Section 2's RPV / Basket Size / Remaining %
    gauges -- a small companion so the numbers are readable without eyeballing
    a dial."""
    from config.kpi_thresholds import basket_size_status, remaining_status, rpv_status
    from src.kpi_engine import compute_kpis

    if fact.empty:
        return pd.DataFrame()
    k = compute_kpis(fact, footfall, target)
    rows = [
        {"metric": "RPV", "value": k.rpv, "status": rpv_status(k.rpv)},
        {"metric": "Basket Size", "value": k.basket_size, "status": basket_size_status(k.basket_size)},
        {"metric": "Remaining %", "value": k.remaining_pct, "status": remaining_status(k.remaining_pct)},
    ]
    return pd.DataFrame(rows)


# Per-period KpiBundle fields shown for each Discounted / Non-discounted segment.
# "nob_transaction_count" (the fact table's distinct bill count) is renamed to
# "transactions" on the way out.
_DISCOUNT_SEGMENT_COLUMNS = [
    "net_sales", "bill_quantity", "nob_transaction_count", "atv", "rpv",
    "basket_size", "achievement_pct",
]


def _promo_row_mask(fact: pd.DataFrame) -> pd.Series:
    """Rows carrying any promotion: a ``promo_type`` value, or a positive
    ``discount_amount`` / ``promo_amount``. Aligned to ``fact.index``."""
    mask = pd.Series(False, index=fact.index)
    if "promo_type" in fact.columns:
        mask = mask | fact["promo_type"].notna()
    if "discount_amount" in fact.columns:
        mask = mask | (fact["discount_amount"].fillna(0) > 0)
    if "promo_amount" in fact.columns:
        mask = mask | (fact["promo_amount"].fillna(0) > 0)
    return mask


def discount_impact_table(
    fact: pd.DataFrame, footfall: pd.DataFrame, target: pd.DataFrame, period: str
) -> pd.DataFrame:
    """Discounted vs Non-discounted Net Sales / ATV / RPV / Basket Size /
    Achievement % per linear ``period`` bucket -- one row per (segment x bucket),
    each cell a ``compute_kpis`` field on that slice (via ``per_period_kpi_table``,
    so the KPI formulas are never re-implemented).

    ``footfall`` / ``target`` are store-day level and can't be split by promo, so
    a segment's RPV / Achievement % compare that segment's Net Sales against the
    *whole store's* footfall / target -- same behaviour as ``per_period_kpi_table``'s
    ``fact_mask`` path elsewhere, and acceptable for this comparison view.
    """
    if fact.empty:
        return pd.DataFrame()
    promo_mask = _promo_row_mask(fact)
    frames = []
    for label, seg_mask in (("Discounted", promo_mask), ("Non-discounted", ~promo_mask)):
        seg = per_period_kpi_table(
            fact, footfall, target, period,
            columns=_DISCOUNT_SEGMENT_COLUMNS, fact_mask=seg_mask,
        )
        if seg.empty:
            continue
        seg.insert(0, "segment", label)
        frames.append(seg)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    out = out.rename(columns={"nob_transaction_count": "transactions"})
    return out[["segment", "Date", "net_sales", "bill_quantity", "transactions",
               "atv", "rpv", "basket_size", "achievement_pct"]]


def promotion_breakdown_table(fact: pd.DataFrame) -> pd.DataFrame:
    """One row per ``promo_type`` code (P/F/A, raw from the workbook) across every
    promoted line: distinct promo-name count, SUM promo amount, SUM discount
    amount, Net Sales, Transactions, Quantity, ATV. Rows that qualify only via a
    positive amount but have no ``promo_type`` land under ``"(unspecified)"``."""
    if fact.empty or "promo_type" not in fact.columns:
        return pd.DataFrame()
    promo = fact.loc[_promo_row_mask(fact)].copy()
    if promo.empty:
        return pd.DataFrame()
    promo["promo_type"] = promo["promo_type"].fillna("(unspecified)")
    agg_kwargs = {
        "net_sales": ("net_amount", "sum"),
        "transactions": ("bill_no", "nunique"),
        "quantity": ("bill_quantity", "sum"),
    }
    if "promo_name" in promo.columns:
        agg_kwargs["promo_names"] = ("promo_name", "nunique")
    if "promo_amount" in promo.columns:
        agg_kwargs["promo_amount"] = ("promo_amount", "sum")
    if "discount_amount" in promo.columns:
        agg_kwargs["discount_amount"] = ("discount_amount", "sum")
    grouped = promo.groupby("promo_type", dropna=False).agg(**agg_kwargs).reset_index()
    grouped["atv"] = grouped["net_sales"] / grouped["transactions"].replace(0, pd.NA)
    ordered = ["promo_type"]
    for col in ["promo_names", "promo_amount", "discount_amount", "net_sales",
                "transactions", "quantity", "atv"]:
        if col in grouped.columns:
            ordered.append(col)
    return grouped[ordered].sort_values("net_sales", ascending=False).reset_index(drop=True)
