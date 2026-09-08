import pandas as pd

from src import data_cleaner


def _minimal_fact_df(**overrides) -> pd.DataFrame:
    base = {
        "date": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"]),
        "store": ["CITIMART - NEW MARKET", "CITIMART - HATIBAGAN", "CITIMART - CHOWRINGHEE"],
        "division": ["Mens", "Kids", "Ladies"],
        "section": ["A", "B", "C"],
        "department": ["A1", "B1", "C1"],
        "item_code": ["C1", "C2", "C3"],
        "product_style": ["STYLE1", "STYLE2", "STYLE3"],
        "product_type": ["PLAIN", "199", "PRINTED"],
        "product_size": ["M", "L", "XL"],
        "isvoid": ["No", "No", "No"],
        "vendors": ["V1", "V2", "V3"],
        "ageing": ["1/1", "1/1", "1/1"],
        "tax_rate": [5, 5, 5],
        "mrp": [199, 199, 399],
        "retail_selling_price": [199, 199, 399],
        "promo_type": [None, None, None],
        "promo_name": [None, None, None],
        "standard_rate": [100.0, 150.0, 250.0],
        "bill_quantity": [1, 2, 1],
        "gross_amount": [199.0, 398.0, 399.0],
        "promo_amount": [0.0, 0.0, 0.0],
        "discount_amount": [0.0, 0.0, 0.0],
        "net_amount": [199.0, 398.0, 399.0],
        "cogs": [100.0, 200.0, 200.0],
        "cogs_with_gst": [105.0, 210.0, 210.0],
        "bill_no": ["B1", "B2", "B3"],
    }
    base.update(overrides)
    return pd.DataFrame(base)


def test_filter_void_rows_drops_only_yes():
    df = _minimal_fact_df(isvoid=["No", "Yes", "No"])
    cleaned, dropped = data_cleaner.filter_void_rows(df)
    assert dropped == 1
    assert len(cleaned) == 2
    assert (cleaned["isvoid"] == "Yes").sum() == 0


def test_drop_exact_duplicates():
    df = _minimal_fact_df()
    df_with_dup = pd.concat([df, df.iloc[[0]]], ignore_index=True)
    cleaned, dropped = data_cleaner.drop_exact_duplicates(df_with_dup)
    assert dropped == 1
    assert len(cleaned) == len(df)


def test_clean_product_hierarchy_fields_nulls_non_string_values():
    # Mirrors real Excel contamination: openpyxl/pandas hands back an actual
    # int/datetime object for a numeric/date-formatted cell, not a numeric
    # string -- so the fixture must use raw Python types, not "199" text.
    df = _minimal_fact_df(
        product_type=["PLAIN", 199, "PRINTED"],
        product_style=["STYLE1", pd.Timestamp("2025-01-12"), "STYLE3"],
        product_size=["M", 26, "XL"],
        product_design_no=["D1", "D2", 220989],
    )
    cleaned, counts = data_cleaner.clean_product_hierarchy_fields(df)
    assert counts == {"product_design_no": 1, "product_style": 1, "product_type": 1, "product_size": 1}
    assert cleaned.loc[0, "product_type"] == "PLAIN"
    assert pd.isna(cleaned.loc[1, "product_type"])
    assert cleaned.loc[2, "product_type"] == "PRINTED"
    assert pd.isna(cleaned.loc[1, "product_style"])
    assert pd.isna(cleaned.loc[1, "product_size"])
    assert pd.isna(cleaned.loc[2, "product_design_no"])


def test_clean_product_hierarchy_fields_leaves_legitimate_text_alone():
    df = _minimal_fact_df(product_style=["FRA-DT-001", "CG-1872", "9-14YRS"])
    cleaned, counts = data_cleaner.clean_product_hierarchy_fields(df)
    assert counts["product_style"] == 0
    assert cleaned["product_style"].tolist() == ["FRA-DT-001", "CG-1872", "9-14YRS"]


def test_flag_tax_rate_outliers():
    df = _minimal_fact_df(tax_rate=[5, 52, 18])
    cleaned, count = data_cleaner.flag_tax_rate_outliers(df)
    assert count == 1
    assert cleaned["tax_rate_outlier"].tolist() == [False, True, False]


def test_add_store_code_maps_known_stores():
    df = _minimal_fact_df()
    result = data_cleaner.add_store_code(df)
    assert result["store_code"].tolist() == ["NM", "HB", "CHW"]


def test_add_store_code_unmapped_store_is_none():
    df = _minimal_fact_df(store=["CITIMART - NEW MARKET", "UNKNOWN STORE", "CITIMART - CHOWRINGHEE"])
    result = data_cleaner.add_store_code(df)
    assert result["store_code"].tolist()[0] == "NM"
    assert pd.isna(result["store_code"].tolist()[1])
    assert result["store_code"].tolist()[2] == "CHW"


def test_add_derived_date_fields():
    df = _minimal_fact_df(date=pd.to_datetime(["2026-01-03", "2026-01-10", "2026-06-01"]))  # Sat, Sat, Mon
    result = data_cleaner.add_derived_date_fields(df)
    assert result.loc[0, "day_name"] == "Sat"
    assert bool(result.loc[0, "is_weekend"]) is True
    assert result.loc[2, "day_name"] == "Mon"
    assert bool(result.loc[2, "is_weekend"]) is False
    assert result.loc[0, "month_name"] == "January"
    assert result.loc[2, "month_name"] == "June"
    assert result.loc[0, "quarter"] == 1
    assert result.loc[2, "quarter"] == 2
    assert result.loc[0, "year"] == 2026


def test_flag_zero_amount_duplicates_tags_only_zero_line():
    df = _minimal_fact_df(
        bill_no=["B1", "B1", "B2"],
        item_code=["C1", "C1", "C2"],
        date=pd.to_datetime(["2026-01-01", "2026-01-01", "2026-01-02"]),
        net_amount=[199.0, 0.0, 399.0],
    )
    result, count = data_cleaner.flag_zero_amount_duplicates(df)
    assert count == 1
    assert result["is_zero_amount_duplicate"].tolist() == [False, True, False]


def test_clean_day_wise_sale_full_pipeline_reconciles_totals():
    df = _minimal_fact_df(isvoid=["No", "Yes", "No"])
    cleaned, stats = data_cleaner.clean_day_wise_sale(df)
    assert stats["void_rows_dropped"] == 1
    assert stats["rows_after"] == 2
    assert cleaned["net_amount"].sum() == 199.0 + 399.0


def test_melt_sales_target_produces_long_format():
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-01-01", "2026-01-02"]),
            "nm_target": [1000, 2000],
            "hb_target": [500, 600],
            "chw_target": [300, 400],
        }
    )
    long_df = data_cleaner.melt_sales_target(df)
    assert set(long_df["store_code"].unique()) == {"NM", "HB", "CHW"}
    assert len(long_df) == 6
    nw_total = long_df.loc[long_df["store_code"] == "NM", "target"].sum()
    assert nw_total == 3000


def test_melt_footfall_nob_forward_fills_date():
    df = pd.DataFrame(
        {
            "date": [pd.Timestamp("2026-01-01"), None, None, None],
            "time_slot": ["11-14", "14-17", "17-20", "20-23"],
            "nm_footfall": [10, 20, 30, 40],
            "nm_nob": [5, 10, 15, 20],
            "hb_footfall": [1, 2, 3, 4],
            "hb_nob": [1, 1, 1, 1],
            "chw_footfall": [1, 1, 1, 1],
            "chw_nob": [1, 1, 1, 1],
        }
    )
    long_df = data_cleaner.melt_footfall_nob(df)
    nw_rows = long_df.loc[long_df["store_code"] == "NM"]
    assert nw_rows["date"].nunique() == 1
    assert nw_rows["footfall"].sum() == 100
