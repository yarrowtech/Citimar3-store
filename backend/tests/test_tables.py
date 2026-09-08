import pandas as pd

from src.kpi_engine import compute_kpis
from src.tables import (
    avg_sales_table,
    category_net_sales_table,
    conversion_funnel_table,
    department_performer_pairing_table,
    discount_impact_table,
    footfall_nob_breakdown_table,
    footfall_vs_nob_table,
    per_period_kpi_table,
    promotion_breakdown_table,
    performer_pairing_table,
    top_category_table,
    period_comparison_table,
    sales_overview_table,
    sales_trend_table,
    secondary_gauge_values_table,
    visitor_vs_net_sales_table,
)


def _fact() -> pd.DataFrame:
    # Section "A": 4 products -> pairs (P1,P4) and (P2,P3).
    # Section "B": only 2 products -> below default min_group_size, excluded.
    rows = [
        # item_code, product_style, section, net_amount, bill_quantity, cogs_with_gst, bill_no
        ("P1", "Style1", "A", 400.0, 4, 200.0, "B1"),
        ("P2", "Style2", "A", 300.0, 3, 150.0, "B2"),
        ("P3", "Style3", "A", 200.0, 2, 100.0, "B3"),
        ("P4", "Style4", "A", 100.0, 1, 50.0, "B4"),
        ("P5", "Style5", "B", 500.0, 5, 250.0, "B5"),
        ("P6", "Style6", "B", 10.0, 1, 5.0, "B6"),
    ]
    return pd.DataFrame(
        rows,
        columns=["item_code", "product_style", "section", "net_amount", "bill_quantity", "cogs_with_gst", "bill_no"],
    )


def test_empty_fact_returns_empty_dataframe():
    assert performer_pairing_table(pd.DataFrame()).empty


def test_pairs_best_with_worst_within_each_category():
    result = performer_pairing_table(_fact(), min_group_size=4)
    # Only section "A" has enough products to pair.
    assert set(result["category"]) == {"A"}
    assert len(result) == 2
    assert result.iloc[0]["strong_product"] == "Style1"
    assert result.iloc[0]["weak_product"] == "Style4"
    assert result.iloc[1]["strong_product"] == "Style2"
    assert result.iloc[1]["weak_product"] == "Style3"


def test_gap_and_rank_sorted_descending_by_gap():
    result = performer_pairing_table(_fact(), min_group_size=4)
    assert result.iloc[0]["gap_net_sales"] == 300.0
    assert result.iloc[1]["gap_net_sales"] == 100.0
    assert list(result["rank"]) == [1, 2]


def test_top_n_limits_row_count():
    result = performer_pairing_table(_fact(), min_group_size=4, top_n=1)
    assert len(result) == 1


def test_group_below_min_group_size_is_excluded():
    result = performer_pairing_table(_fact(), min_group_size=6)
    assert result.empty


# --- per_period_kpi_table -------------------------------------------------

def _period_fact() -> pd.DataFrame:
    return pd.DataFrame({
        "date": pd.to_datetime(["2026-08-05", "2026-08-20", "2026-09-03"]),
        "net_amount": [1000.0, 500.0, 2000.0],
        "bill_quantity": [10.0, 5.0, 20.0],
        "bill_no": ["A", "B", "C"],
    })


def _period_footfall() -> pd.DataFrame:
    return pd.DataFrame({
        "date": pd.to_datetime(["2026-08-05", "2026-09-03"]),
        "footfall": [100.0, 200.0],
        "nob": [40.0, 80.0],
    })


def _period_target() -> pd.DataFrame:
    return pd.DataFrame({
        "date": pd.to_datetime(["2026-08-05", "2026-09-03"]),
        "target": [2000.0, 2500.0],
    })


def test_per_period_one_row_per_bucket_sorted():
    out = per_period_kpi_table(_period_fact(), _period_footfall(), _period_target(), "month")
    assert list(out["Date"]) == ["Aug 2026", "Sep 2026"]
    assert out.iloc[0]["net_sales"] == 1500.0
    assert out.iloc[1]["net_sales"] == 2000.0


def test_per_period_ratio_kpis_match_direct_compute_on_the_same_slice():
    fact, footfall, target = _period_fact(), _period_footfall(), _period_target()
    aug_fact = fact[fact["date"].dt.month == 8]
    aug_ff = footfall[footfall["date"].dt.month == 8]
    aug_tgt = target[target["date"].dt.month == 8]
    direct = compute_kpis(aug_fact, aug_ff, aug_tgt)
    row = per_period_kpi_table(fact, footfall, target, "month").iloc[0]
    assert row["atv"] == direct.atv
    assert row["rpv"] == direct.rpv
    assert row["conversion_pct"] == direct.conversion_pct
    assert row["achievement_pct"] == direct.achievement_pct


def test_per_period_remaining_pct_is_100_minus_achievement():
    out = per_period_kpi_table(_period_fact(), _period_footfall(), _period_target(), "month")
    for _, row in out.iterrows():
        if row["achievement_pct"] is not None:
            assert row["remaining_pct"] == 100 - row["achievement_pct"]


def test_per_period_empty_frames_return_empty_with_columns():
    out = per_period_kpi_table(pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), "week", columns=["net_sales"])
    assert out.empty
    assert list(out.columns) == ["Date", "net_sales"]


def test_per_period_fact_mask_and_label_prefix():
    fact = _period_fact()
    mask = fact["net_amount"] >= 1000.0
    out = per_period_kpi_table(fact, _period_footfall(), _period_target(), "month",
                               columns=["net_sales"], fact_mask=mask, label_prefix="Promo · ")
    assert out.iloc[0]["Date"] == "Promo · Aug 2026"
    assert out.iloc[0]["net_sales"] == 1000.0  # the 500.0 Aug row is masked out


# --- discount_impact_table / promotion_breakdown_table ------------------

def _promo_fact() -> pd.DataFrame:
    return pd.DataFrame({
        "date": pd.to_datetime(["2026-08-05", "2026-08-20", "2026-09-03", "2026-09-10"]),
        "net_amount": [1000.0, 500.0, 2000.0, 300.0],
        "bill_quantity": [10.0, 5.0, 20.0, 3.0],
        "bill_no": ["A", "B", "C", "D"],
        "promo_type": ["P", None, "F", None],
        "promo_name": ["20% OFF", None, "@ 99/-", None],
        "promo_amount": [40.0, 0.0, 15.0, 0.0],
        "discount_amount": [0.0, 0.0, 0.0, 0.0],
    })


def test_discount_impact_table_segments_and_period_buckets():
    out = discount_impact_table(_promo_fact(), _period_footfall(), _period_target(), "month")
    assert set(out["segment"]) == {"Discounted", "Non-discounted"}
    assert "gross_amount" not in out.columns and "gross_profit" not in out.columns
    for col in ("rpv", "basket_size", "achievement_pct", "transactions"):
        assert col in out.columns
    disc_aug = out[(out["segment"] == "Discounted") & (out["Date"] == "Aug 2026")].iloc[0]
    assert disc_aug["net_sales"] == 1000.0  # only the promo row, not the 500.0 Aug row


def test_discount_impact_table_ratio_matches_direct_compute():
    fact, footfall, target = _promo_fact(), _period_footfall(), _period_target()
    aug_disc = fact[(fact["date"].dt.month == 8) & fact["promo_type"].notna()]
    direct = compute_kpis(aug_disc, footfall[footfall["date"].dt.month == 8], target[target["date"].dt.month == 8])
    row = discount_impact_table(fact, footfall, target, "month")
    row = row[(row["segment"] == "Discounted") & (row["Date"] == "Aug 2026")].iloc[0]
    assert row["rpv"] == direct.rpv
    assert row["basket_size"] == direct.basket_size
    assert row["achievement_pct"] == direct.achievement_pct


def test_discount_impact_table_empty_fact():
    assert discount_impact_table(pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), "month").empty


def test_promotion_breakdown_table_groups_by_promo_type():
    out = promotion_breakdown_table(_promo_fact())
    assert list(out["promo_type"]) == ["F", "P"] or list(out["promo_type"]) == ["P", "F"]
    p_row = out[out["promo_type"] == "P"].iloc[0]
    assert p_row["promo_amount"] == 40.0
    assert p_row["net_sales"] == 1000.0
    assert p_row["promo_names"] == 1


def test_promotion_breakdown_table_no_promo_columns_is_empty():
    assert promotion_breakdown_table(_period_fact()).empty


def test_sales_overview_table_column_set_and_one_row_per_bucket():
    out = sales_overview_table(_period_fact(), _period_footfall(), _period_target(), "month")
    assert list(out.columns) == [
        "Date", "sales_target", "net_sales", "remaining", "bill_quantity", "footfall", "nob",
        "atv", "rpv", "basket_size", "conversion_pct", "achievement_pct", "remaining_pct",
    ]
    assert list(out["Date"]) == ["Aug 2026", "Sep 2026"]
    assert out.iloc[0]["net_sales"] == 1500.0


# --- Section 2 (Sales Performance) companions, Phase 3 --------------------

def _sales_perf_fact() -> pd.DataFrame:
    from src.period_engine import WEEKDAY_TO_LABEL

    dates = pd.to_datetime(["2026-08-03", "2026-08-10", "2026-09-03", "2026-09-10"])
    return pd.DataFrame({
        "date": dates,
        "net_amount": [1000.0, 500.0, 2000.0, 800.0],
        "bill_quantity": [10.0, 5.0, 20.0, 8.0],
        "bill_no": ["A", "B", "C", "D"],
        "day_name": [WEEKDAY_TO_LABEL[d] for d in dates.dayofweek],
        "day_of_month": dates.day,
        "year_month": dates.strftime("%Y-%m"),
        "month_name": dates.month_name(),
        "year": dates.year,
    })


def test_sales_trend_table_period_and_timeslot():
    period = sales_trend_table(_sales_perf_fact(), pd.DataFrame(), dimension="period", granularity="month")
    assert list(period.columns) == ["Date", "net_sales"]
    assert list(period["net_sales"]) == [1500.0, 2800.0]

    footfall = pd.DataFrame({
        "time_slot": ["11.00 AM - 01.59 PM", "05.00 PM - 07.59 PM"],
        "footfall": [100.0, 200.0],
        "nob": [40.0, 90.0],
    })
    ts = sales_trend_table(pd.DataFrame(), footfall, dimension="timeslot")
    assert "conversion_pct" in ts.columns
    assert ts.loc[ts["time_slot"] == "11.00 AM - 01.59 PM", "conversion_pct"].iloc[0] == 40.0


def test_avg_sales_table_is_mean_per_bucket():
    out = avg_sales_table(_sales_perf_fact(), granularity="month")
    assert list(out.columns) == ["bucket", "avg_net_sales"]
    aug = out.loc[out["bucket"] == "August", "avg_net_sales"].iloc[0]
    assert aug == 750.0


def test_period_comparison_table_modes():
    fact = _sales_perf_fact()
    monthly = period_comparison_table(fact, dimension="monthly_same_day")
    assert list(monthly.columns) == ["day_of_month", "month", "net_sales"]
    weekly = period_comparison_table(fact, dimension="weekly_same_day")
    assert list(weekly.columns) == ["day_of_week", "week", "net_sales"]
    yearly = period_comparison_table(fact, dimension="yearly_month")
    assert list(yearly.columns) == ["month", "year", "net_sales"]


def test_secondary_gauge_values_table_rows_and_status():
    out = secondary_gauge_values_table(_period_fact(), _period_footfall(), _period_target())
    assert list(out["metric"]) == ["RPV", "Basket Size", "Remaining %"]
    assert set(out.columns) == {"metric", "value", "status"}
    assert out["status"].isin(["red", "yellow", "green"]).all()


# --- Section 3 (Customer & Conversion) companions ---------------------------

def _conversion_footfall() -> pd.DataFrame:
    return pd.DataFrame({
        "date": pd.to_datetime(["2026-08-03", "2026-08-03", "2026-08-10"]),
        "time_slot": ["11.00 AM - 01.59 PM", "05.00 PM - 07.59 PM", "11.00 AM - 01.59 PM"],
        "footfall": [100.0, 200.0, 50.0],
        "nob": [40.0, 90.0, 20.0],
    })


def test_footfall_vs_nob_table_date_and_timeslot():
    ff = _conversion_footfall()
    date_mode = footfall_vs_nob_table(ff, dimension="date")
    assert list(date_mode.columns) == ["date", "footfall", "nob", "conversion_pct"]
    aug3 = date_mode.loc[date_mode["date"] == "2026-08-03"].iloc[0]
    assert aug3["footfall"] == 300.0 and aug3["nob"] == 130.0

    ts = footfall_vs_nob_table(ff, dimension="timeslot")
    assert list(ts["time_slot"]) == list(ts["time_slot"].dropna())
    row = ts.loc[ts["time_slot"] == "11.00 AM - 01.59 PM"].iloc[0]
    assert round(row["conversion_pct"], 2) == 40.0  # 60 / 150 * 100

    assert footfall_vs_nob_table(pd.DataFrame(), dimension="date").empty


def test_visitor_vs_net_sales_table_joins_by_date_and_dayofweek():
    ff = _conversion_footfall()
    fact = _sales_perf_fact()
    date_mode = visitor_vs_net_sales_table(ff, fact, metric="footfall", dimension="date")
    assert list(date_mode.columns) == ["date", "footfall", "net_sales"]
    assert date_mode.loc[date_mode["date"] == "2026-08-03", "net_sales"].iloc[0] == 1000.0

    dow = visitor_vs_net_sales_table(ff, fact, metric="nob", dimension="dayofweek")
    assert list(dow.columns) == ["day_of_week", "nob", "net_sales"]

    assert visitor_vs_net_sales_table(pd.DataFrame(), pd.DataFrame()).empty


def test_footfall_nob_breakdown_table_dimensions():
    ff = _conversion_footfall()
    for dim in ("dayofweek", "timeslot", "date"):
        out = footfall_nob_breakdown_table(ff, dimension=dim)
        assert list(out.columns) == ["bucket", "footfall", "nob", "conversion_pct"]
    assert footfall_nob_breakdown_table(pd.DataFrame()).empty


def test_conversion_funnel_table_date_and_timeslot():
    ff = _conversion_footfall()
    date_mode = conversion_funnel_table(ff, 350.0, 150.0, dimension="date")
    assert list(date_mode["stage"]) == ["Footfall", "Transactions"]
    assert round(date_mode.loc[1, "conversion_pct"], 2) == round(150 / 350 * 100, 2)

    ts = conversion_funnel_table(ff, None, None, dimension="timeslot")
    assert list(ts.columns) == ["time_slot", "footfall", "nob", "conversion_pct"]


# --- Product & Brand: Division / Section / Department reorganisation --------


def _hierarchy_fact() -> pd.DataFrame:
    """DIVISION -> SECTION -> DEPARTMENT fact with >= 4 products per department
    and two shared bills (B1: WK-A + ST-B  |  B2: WK-A + ST-A) so the weak
    performer's market-basket co-purchase is deterministic."""
    rows = [
        # division, section, department, item_code, product_style, net_amount, bill_quantity, cogs_with_gst, discount_amount, bill_no
        ("APPAREL", "MENS", "SHIRTS", "SH1", "Shirt 1", 1000.0, 4, 500.0, 10.0, "A1"),
        ("APPAREL", "MENS", "SHIRTS", "SH2", "Shirt 2", 700.0, 3, 350.0, 5.0, "A2"),
        ("APPAREL", "MENS", "SHIRTS", "SH3", "Shirt 3", 400.0, 2, 200.0, 0.0, "A3"),
        ("APPAREL", "MENS", "SHIRTS", "SH4", "Shirt 4", 100.0, 1, 60.0, 0.0, "A4"),
        ("APPAREL", "MENS", "TROUSERS", "TR1", "Trouser 1", 900.0, 3, 450.0, 0.0, "A5"),
        ("APPAREL", "MENS", "TROUSERS", "TR2", "Trouser 2", 600.0, 2, 300.0, 0.0, "A6"),
        ("APPAREL", "MENS", "TROUSERS", "TR3", "Trouser 3", 300.0, 1, 150.0, 0.0, "A7"),
        ("APPAREL", "MENS", "TROUSERS", "TR4", "Trouser 4", 50.0, 1, 30.0, 0.0, "A7b"),
        ("FOOTWEAR", "MENS", "SNEAKERS", "SN1", "Sneaker 1", 800.0, 2, 400.0, 0.0, "A8"),
        ("FOOTWEAR", "MENS", "SNEAKERS", "SN2", "Sneaker 2", 200.0, 1, 100.0, 0.0, "A9"),
        # weak performer of SHIRTS is SH4 -- share bills with SN1 (x2) and TR1 (x1)
        ("APPAREL", "MENS", "SHIRTS", "SH4", "Shirt 4", 20.0, 1, 12.0, 0.0, "C1"),
        ("FOOTWEAR", "MENS", "SNEAKERS", "SN1", "Sneaker 1", 20.0, 1, 10.0, 0.0, "C1"),
        ("APPAREL", "MENS", "SHIRTS", "SH4", "Shirt 4", 20.0, 1, 12.0, 0.0, "C2"),
        ("FOOTWEAR", "MENS", "SNEAKERS", "SN1", "Sneaker 1", 20.0, 1, 10.0, 0.0, "C2"),
        ("APPAREL", "MENS", "SHIRTS", "SH4", "Shirt 4", 20.0, 1, 12.0, 0.0, "C3"),
        ("APPAREL", "MENS", "TROUSERS", "TR1", "Trouser 1", 20.0, 1, 10.0, 0.0, "C3"),
    ]
    return pd.DataFrame(
        rows,
        columns=[
            "division", "section", "department", "item_code", "product_style",
            "net_amount", "bill_quantity", "cogs_with_gst", "discount_amount", "bill_no",
        ],
    )


def test_category_net_sales_table_has_rollup_rows_at_every_level():
    out = category_net_sales_table(_hierarchy_fact())
    assert set(out["level"]) == {"Division", "Section", "Department"}
    # Division roll-up == sum of its department leaves.
    div_row = out.loc[out["level"] == "Division"].iloc[0]
    dept_sum = out.loc[(out["level"] == "Department") & (out["division"] == div_row["division"]), "net_sales"].sum()
    assert div_row["net_sales"] == dept_sum
    # share_pct across the top level sums to ~100.
    assert round(out.loc[out["level"] == "Division", "share_pct"].sum(), 6) == 100.0
    # gross_profit / margin present.
    assert "gross_profit" in out.columns and "gross_margin_pct" in out.columns


def test_category_net_sales_table_missing_optional_columns():
    fact = _hierarchy_fact().drop(columns=["cogs_with_gst", "discount_amount"])
    out = category_net_sales_table(fact)
    assert out["cogs_gst"].isna().all() and out["discount"].isna().all()
    assert not out.empty
    assert category_net_sales_table(pd.DataFrame()).empty


def test_top_category_table_switches_dimension_and_measure():
    fact = _hierarchy_fact()
    by_dept = top_category_table(fact, "department", "net_amount", top_n=10)
    assert list(by_dept.columns) == ["rank", "category", "net_sales", "quantity", "transactions", "cogs_gst", "discount"]
    assert list(by_dept["net_sales"]) == sorted(by_dept["net_sales"], reverse=True)
    assert by_dept.iloc[0]["rank"] == 1

    by_txn = top_category_table(fact, "division", "transactions", top_n=10)
    assert list(by_txn["transactions"]) == sorted(by_txn["transactions"], reverse=True)

    assert top_category_table(fact, "nonexistent_col").empty


def test_department_performer_pairing_table_shape_and_co_purchase():
    out = department_performer_pairing_table(_hierarchy_fact(), top_n=10)
    assert list(out.columns) == [
        "rank", "department", "strong_performer", "strong_net_sales",
        "weak_performer", "weak_net_sales", "best_paired",
    ]
    # SNEAKERS has only 2 products -> excluded by default min_group_size.
    assert set(out["department"]) == {"SHIRTS", "TROUSERS"}
    shirts = out.loc[out["department"] == "SHIRTS"].iloc[0]
    assert shirts["strong_performer"] == "Shirt 1"
    assert shirts["weak_performer"] == "Shirt 4"
    # Shirt 4 shares 2 bills with Sneaker 1, 1 with Trouser 1 -> Sneaker 1 wins.
    assert shirts["best_paired"] == "Sneaker 1"
    # ranked by strong-minus-weak spread, descending
    assert list(out["rank"]) == [1, 2]
    assert out.iloc[0]["strong_net_sales"] - out.iloc[0]["weak_net_sales"] >= (
        out.iloc[1]["strong_net_sales"] - out.iloc[1]["weak_net_sales"]
    )


def test_department_performer_pairing_table_guards():
    assert department_performer_pairing_table(pd.DataFrame()).empty
    assert department_performer_pairing_table(_hierarchy_fact(), min_group_size=99).empty
