"""No forward-looking promo calendar exists in DATASET.xlsx -- promo_type/
promo_name only exist on historical transaction lines. "Future promotions"
is therefore NOT a forecasting target here; this module instead measures how
much each historical promo type/campaign lifted sales versus a no-promo
baseline, to INFORM future promo planning by a human, not to predict which
promos will run when.
"""
from __future__ import annotations

import pandas as pd

from config.forecast_settings import TOP_N_PROMO_CAMPAIGNS

NO_PROMO_LABEL = "No Promo"
_PROMO_TYPE_LABELS = {"P": "Percentage Discount", "F": "Flat Discount", "A": "Other Promo"}


def _no_promo_baseline_avg_net_per_bill(fact: pd.DataFrame) -> float | None:
    if not {"promo_type", "net_amount", "bill_no"}.issubset(fact.columns):
        return None
    no_promo = fact.loc[fact["promo_type"].isna()]
    bills = no_promo["bill_no"].nunique()
    if bills == 0:
        return None
    return float(no_promo["net_amount"].sum() / bills)


def _uplift_pct(avg_net_per_bill: pd.Series, baseline: float | None) -> pd.Series:
    if not baseline:
        return pd.Series([None] * len(avg_net_per_bill), index=avg_net_per_bill.index)
    return (avg_net_per_bill - baseline) / baseline * 100


def promo_uplift_table(fact: pd.DataFrame) -> pd.DataFrame:
    """Groups by promo_type (plus a synthetic 'No Promo' bucket for null),
    computing avg_net_per_bill/total_net_sales/transaction_count and
    uplift_pct versus the 'No Promo' baseline."""
    if fact.empty or not {"promo_type", "net_amount", "bill_no"}.issubset(fact.columns):
        return pd.DataFrame()

    baseline = _no_promo_baseline_avg_net_per_bill(fact)

    df = fact.copy()
    df["promo_type"] = df["promo_type"].astype("object")
    df["promo_type"] = df["promo_type"].where(df["promo_type"].notna(), NO_PROMO_LABEL)
    df["promo_type"] = df["promo_type"].map(lambda v: _PROMO_TYPE_LABELS.get(v, v))

    grouped = (
        df.groupby("promo_type")
        .agg(total_net_sales=("net_amount", "sum"), transaction_count=("bill_no", "nunique"))
        .reset_index()
    )
    grouped["avg_net_per_bill"] = grouped["total_net_sales"] / grouped["transaction_count"].replace(0, pd.NA)
    grouped["uplift_pct"] = _uplift_pct(grouped["avg_net_per_bill"], baseline)

    return grouped.sort_values("total_net_sales", ascending=False).reset_index(drop=True)


def top_promo_campaigns_table(fact: pd.DataFrame, top_n: int = TOP_N_PROMO_CAMPAIGNS) -> pd.DataFrame:
    """Groups by promo_name (non-null), ranked by total net_sales, with
    avg_net_per_bill and uplift_pct versus the same 'No Promo' baseline
    promo_uplift_table uses."""
    if fact.empty or not {"promo_name", "net_amount", "bill_no"}.issubset(fact.columns):
        return pd.DataFrame()

    named = fact.loc[fact["promo_name"].notna()]
    if named.empty:
        return pd.DataFrame()

    baseline = _no_promo_baseline_avg_net_per_bill(fact)

    grouped = (
        named.groupby("promo_name")
        .agg(total_net_sales=("net_amount", "sum"), transaction_count=("bill_no", "nunique"))
        .reset_index()
    )
    grouped["avg_net_per_bill"] = grouped["total_net_sales"] / grouped["transaction_count"].replace(0, pd.NA)
    grouped["uplift_pct"] = _uplift_pct(grouped["avg_net_per_bill"], baseline)

    return grouped.sort_values("total_net_sales", ascending=False).head(top_n).reset_index(drop=True)
