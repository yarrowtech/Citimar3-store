import math

import pandas as pd
import pytest

from src.kpi_engine import compute_kpis, safe_divide


def test_safe_divide_normal():
    assert safe_divide(100, 4) == 25


def test_safe_divide_zero_denominator_returns_none():
    assert safe_divide(100, 0) is None


def test_safe_divide_none_inputs_return_none():
    assert safe_divide(None, 5) is None
    assert safe_divide(5, None) is None


def test_safe_divide_nan_returns_none():
    assert safe_divide(float("nan"), 5) is None


def _fact(**overrides) -> pd.DataFrame:
    base = {
        "bill_no": ["B1", "B1", "B2", "B3"],  # B1 has 2 line items -> 1 distinct transaction
        "net_amount": [100.0, 50.0, 200.0, 150.0],
        "gross_amount": [110.0, 55.0, 210.0, 160.0],
        "discount_amount": [10.0, 5.0, 10.0, 10.0],
        "bill_quantity": [1, 1, 2, 1],
        "cogs_with_gst": [60.0, 30.0, 120.0, 90.0],
    }
    base.update(overrides)
    return pd.DataFrame(base)


def _footfall(**overrides) -> pd.DataFrame:
    base = {"footfall": [100.0, 150.0], "nob": [40.0, 60.0]}
    base.update(overrides)
    return pd.DataFrame(base)


def _target(**overrides) -> pd.DataFrame:
    base = {"target": [400.0, 400.0]}
    base.update(overrides)
    return pd.DataFrame(base)


def test_net_and_gross_sales_sum():
    kpis = compute_kpis(_fact(), _footfall(), _target())
    assert kpis.net_sales == 500.0
    assert kpis.gross_sales == 535.0
    assert kpis.gross_sales_is_derived is False


def test_gross_sales_derived_when_missing():
    fact = _fact()
    fact = fact.drop(columns=["gross_amount"])
    kpis = compute_kpis(fact, _footfall(), _target())
    # derived gross = net + discount = 500 + 35
    assert kpis.gross_sales == 535.0
    assert kpis.gross_sales_is_derived is True


def test_nob_sourced_from_footfall_sheet_not_line_items():
    kpis = compute_kpis(_fact(), _footfall(), _target())
    # NOB is SUM(nob) from TIME WISE FOOTFALL-NOB (40 + 60 = 100), the
    # source of record -- not a distinct-bill-no count from the fact table.
    assert kpis.nob == 100.0


def test_nob_transaction_count_counts_distinct_transactions_not_line_items():
    kpis = compute_kpis(_fact(), _footfall(), _target())
    # 4 line items but bill_no has only 3 distinct values (B1, B2, B3) --
    # kept only as a cross-check field, not used in any formula.
    assert kpis.nob_transaction_count == 3.0


def test_atv_uses_footfall_sheet_nob():
    kpis = compute_kpis(_fact(), _footfall(), _target())
    assert kpis.atv == pytest.approx(500.0 / 100.0)


def test_rpv_uses_footfall_total():
    kpis = compute_kpis(_fact(), _footfall(), _target())
    assert kpis.rpv == pytest.approx(500.0 / 250.0)


def test_basket_size_quantity_over_footfall_sheet_nob():
    kpis = compute_kpis(_fact(), _footfall(), _target())
    total_qty = 1 + 1 + 2 + 1
    assert kpis.basket_size == pytest.approx(total_qty / 100.0)


def test_conversion_percentage():
    kpis = compute_kpis(_fact(), _footfall(), _target())
    # nob=100 (from footfall sheet), footfall=250 -> 40%
    assert kpis.conversion_pct == pytest.approx(100 / 250 * 100)


def test_achievement_percentage():
    kpis = compute_kpis(_fact(), _footfall(), _target())
    assert kpis.achievement_pct == pytest.approx(500.0 / 800.0 * 100)


def test_remaining_pct_is_100_minus_achievement():
    kpis = compute_kpis(_fact(), _footfall(), _target())
    assert kpis.remaining_pct == pytest.approx(100 - kpis.achievement_pct)


def test_remaining_pct_none_when_achievement_none():
    empty = pd.DataFrame(columns=["bill_no", "net_amount", "gross_amount", "discount_amount", "bill_quantity", "cogs_with_gst"])
    kpis = compute_kpis(empty, pd.DataFrame(columns=["footfall", "nob"]), pd.DataFrame(columns=["target"]))
    assert kpis.achievement_pct is None
    assert kpis.remaining_pct is None


def test_net_and_gross_profit_use_cogs_with_gst():
    kpis = compute_kpis(_fact(), _footfall(), _target())
    total_cogs = 60 + 30 + 120 + 90
    assert kpis.net_profit == pytest.approx(500.0 - total_cogs)
    assert kpis.gross_profit == pytest.approx(500.0 - total_cogs)


def test_returns_tracked_from_negative_rows():
    fact = _fact(bill_quantity=[1, 1, -1, 1], net_amount=[100.0, 50.0, -80.0, 150.0])
    kpis = compute_kpis(fact, _footfall(), _target())
    assert kpis.returned_units == 1.0
    assert kpis.returned_value == 80.0


def test_no_data_state_returns_none_not_crash():
    empty = pd.DataFrame(columns=["bill_no", "net_amount", "gross_amount", "discount_amount", "bill_quantity", "cogs_with_gst"])
    kpis = compute_kpis(empty, pd.DataFrame(columns=["footfall", "nob"]), pd.DataFrame(columns=["target"]))
    assert kpis.net_sales is None
    assert kpis.atv is None
    assert kpis.conversion_pct is None
    assert not (isinstance(kpis.net_sales, float) and math.isnan(kpis.net_sales))
