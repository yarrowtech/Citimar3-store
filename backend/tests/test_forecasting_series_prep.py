import pandas as pd

from src.forecasting.series_prep import (
    build_daily_sales_series,
    build_footfall_nob_series,
    build_target_aligned_series,
    top_n_entity_series,
)


def _fact(**overrides) -> pd.DataFrame:
    base = {
        "date": pd.to_datetime(
            ["2026-01-01", "2026-01-01", "2026-01-03", "2026-01-03", "2026-01-03"]
        ),  # 2026-01-02 deliberately missing -> gap-fill check
        "store_code": ["NM", "HB", "NM", "NM", "HB"],
        "net_amount": [100.0, 50.0, 200.0, 20.0, 30.0],
        "product_style": ["A", "B", "A", "C", "D"],
        "vendors": ["V1", "V2", "V1", "V3", "V4"],
        "promo_type": ["P", None, "F", None, None],
        "discount_amount": [10.0, 0.0, 5.0, 0.0, 0.0],
        "gross_amount": [110.0, 50.0, 205.0, 20.0, 30.0],
    }
    base.update(overrides)
    return pd.DataFrame(base)


def _footfall(**overrides) -> pd.DataFrame:
    base = {
        "date": pd.to_datetime(["2026-01-01", "2026-01-01", "2026-01-02", "2026-01-02"]),
        "time_slot": [
            "11.00 AM - 01.59 PM", "02.00 PM - 04.59 PM",
            "11.00 AM - 01.59 PM", "02.00 PM - 04.59 PM",
        ],
        "footfall": [100.0, 200.0, 50.0, 60.0],
        "nob": [30.0, 70.0, 20.0, 25.0],
        "store_code": ["NM", "NM", "NM", "NM"],
    }
    base.update(overrides)
    return pd.DataFrame(base)


def _target(**overrides) -> pd.DataFrame:
    base = {
        "date": pd.to_datetime(["2026-01-01", "2026-01-02"]),
        "target": [300.0, 400.0],
        "store_code": ["NM", "NM"],
    }
    base.update(overrides)
    return pd.DataFrame(base)


# --- build_daily_sales_series ---


def test_daily_sales_series_sums_all_stores_and_fills_gap():
    series = build_daily_sales_series(_fact())
    assert list(series.df["date"].dt.strftime("%Y-%m-%d")) == ["2026-01-01", "2026-01-02", "2026-01-03"]
    assert list(series.df["y"]) == [150.0, 0.0, 250.0]  # Jan 2 has no rows -> real zero-sales day


def test_daily_sales_series_scoped_to_store():
    series = build_daily_sales_series(_fact(), store_code="NM")
    assert list(series.df["y"]) == [100.0, 0.0, 220.0]


def test_daily_sales_series_empty_input_never_raises():
    series = build_daily_sales_series(pd.DataFrame())
    assert series.df.empty
    series2 = build_daily_sales_series(_fact().drop(columns=["net_amount"]))
    assert series2.df.empty


# --- build_footfall_nob_series ---


def test_footfall_series_single_slot_is_not_sum_of_all_slots():
    single_slot = build_footfall_nob_series(_footfall(), "NM", "11.00 AM - 01.59 PM", value_col="footfall")
    all_slots = build_footfall_nob_series(_footfall(), "NM", None, value_col="footfall")
    assert list(single_slot.df["y"]) == [100.0, 50.0]
    assert list(all_slots.df["y"]) == [300.0, 110.0]
    assert list(single_slot.df["y"]) != list(all_slots.df["y"])


def test_footfall_series_nob_value_col():
    series = build_footfall_nob_series(_footfall(), "NM", None, value_col="nob")
    assert list(series.df["y"]) == [100.0, 45.0]


def test_footfall_series_empty_for_unknown_store():
    series = build_footfall_nob_series(_footfall(), "DOES_NOT_EXIST", None)
    assert series.df.empty


# --- build_target_aligned_series ---


def test_target_aligned_series():
    series = build_target_aligned_series(_target(), store_code="NM")
    assert series.loc[pd.Timestamp("2026-01-01")] == 300.0
    assert series.loc[pd.Timestamp("2026-01-02")] == 400.0


def test_target_aligned_series_empty_input():
    series = build_target_aligned_series(pd.DataFrame())
    assert series.empty


# --- top_n_entity_series ---


def test_top_n_entity_series_other_bucket_sums_excluded_entities():
    fact = _fact()
    bundles = top_n_entity_series(fact, "product_style", top_n=2)
    assert set(bundles.keys()) == {"A", "B", "Other"}  # A=300 total, B=50, C=20, D=30 -> top2 A,B; Other=C+D
    other_total = bundles["Other"].df["y"].sum()
    excluded_total = fact.loc[fact["product_style"].isin(["C", "D"]), "net_amount"].sum()
    assert other_total == excluded_total


def test_top_n_entity_series_no_other_bucket_when_top_n_covers_all():
    bundles = top_n_entity_series(_fact(), "product_style", top_n=10)
    assert "Other" not in bundles
    assert set(bundles.keys()) == {"A", "B", "C", "D"}


def test_top_n_entity_series_empty_input():
    assert top_n_entity_series(pd.DataFrame(), "product_style", top_n=5) == {}
    assert top_n_entity_series(_fact(), "does_not_exist", top_n=5) == {}
