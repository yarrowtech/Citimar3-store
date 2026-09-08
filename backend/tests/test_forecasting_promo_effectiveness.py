import pandas as pd
import pytest

from src.forecasting.promo_effectiveness import promo_uplift_table, top_promo_campaigns_table


def _fact(**overrides) -> pd.DataFrame:
    base = {
        "promo_type": ["P", "P", "F", None, None, None],
        "promo_name": ["SummerSale", "SummerSale", "FlatOff", None, None, None],
        "net_amount": [120.0, 130.0, 200.0, 90.0, 100.0, 110.0],
        "bill_no": ["B1", "B2", "B3", "B4", "B5", "B6"],
    }
    base.update(overrides)
    return pd.DataFrame(base)


# No-promo baseline: bills B4/B5/B6, net = 90+100+110 = 300, 3 bills -> avg 100.0


def test_promo_uplift_table_exact_baseline_and_uplift():
    table = promo_uplift_table(_fact()).set_index("promo_type")

    assert table.loc["No Promo", "avg_net_per_bill"] == pytest.approx(100.0)
    assert table.loc["No Promo", "uplift_pct"] == pytest.approx(0.0)

    assert table.loc["Percentage Discount", "avg_net_per_bill"] == pytest.approx(125.0)  # (120+130)/2
    assert table.loc["Percentage Discount", "uplift_pct"] == pytest.approx(25.0)  # (125-100)/100*100

    assert table.loc["Flat Discount", "avg_net_per_bill"] == pytest.approx(200.0)
    assert table.loc["Flat Discount", "uplift_pct"] == pytest.approx(100.0)


def test_promo_uplift_table_sorted_by_total_net_sales_desc():
    table = promo_uplift_table(_fact())
    totals = table["total_net_sales"].tolist()
    assert totals == sorted(totals, reverse=True)


def test_promo_uplift_table_empty_on_missing_columns():
    assert promo_uplift_table(pd.DataFrame()).empty
    assert promo_uplift_table(_fact().drop(columns=["promo_type"])).empty


def test_top_promo_campaigns_ranking_and_uplift():
    table = top_promo_campaigns_table(_fact(), top_n=5)
    # SummerSale total=250 (120+130) > FlatOff total=200 -> SummerSale ranks first
    # even though FlatOff has the higher avg-per-bill (200 vs 125).
    assert table["promo_name"].tolist() == ["SummerSale", "FlatOff"]

    summer = table.set_index("promo_name").loc["SummerSale"]
    assert summer["avg_net_per_bill"] == pytest.approx(125.0)
    assert summer["uplift_pct"] == pytest.approx(25.0)

    flat = table.set_index("promo_name").loc["FlatOff"]
    assert flat["avg_net_per_bill"] == pytest.approx(200.0)
    assert flat["uplift_pct"] == pytest.approx(100.0)


def test_top_promo_campaigns_respects_top_n():
    fact = _fact(
        promo_type=["P", "F", "P", None],
        promo_name=["A", "B", "C", None],
        net_amount=[100.0, 200.0, 50.0, 10.0],
        bill_no=["B1", "B2", "B3", "B4"],
    )
    table = top_promo_campaigns_table(fact, top_n=2)
    assert len(table) == 2
    assert table["promo_name"].tolist() == ["B", "A"]  # ranked by total_net_sales desc: B=200, A=100, C=50


def test_top_promo_campaigns_empty_on_no_named_campaigns():
    fact = _fact(promo_name=[None] * 6)
    assert top_promo_campaigns_table(fact).empty


def test_top_promo_campaigns_empty_on_missing_columns():
    assert top_promo_campaigns_table(pd.DataFrame()).empty
