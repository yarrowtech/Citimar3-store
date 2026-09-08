"""Central KPI calculation module (master prompt Section 11). Every formula
lives here exactly once; charts, cards, and tables all call into this module
instead of recomputing. Returns None for any KPI whose source field is
missing or whose denominator is zero/unavailable -- callers render that as
"N/A — required source field not available" via src/formatting.py.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


def safe_divide(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None:
        return None
    if denominator == 0:
        return None
    try:
        if pd.isna(numerator) or pd.isna(denominator):
            return None
    except (TypeError, ValueError):
        pass
    return numerator / denominator


@dataclass
class KpiBundle:
    net_sales: float | None
    gross_sales: float | None
    gross_sales_is_derived: bool
    discounts: float | None
    net_profit: float | None
    gross_profit: float | None
    bill_quantity: float | None
    footfall: float | None
    nob: float | None  # SUM(NOB) from TIME WISE FOOTFALL-NOB -- the source of record for Footfall/NOB
    nob_transaction_count: float | None  # distinct bill_no count from the fact table, kept for cross-checking only
    atv: float | None
    rpv: float | None
    basket_size: float | None
    conversion_pct: float | None
    sales_target: float | None
    achievement_pct: float | None
    remaining: float | None  # Sales Target - Net Sales; how much is left to hit target
    remaining_pct: float | None  # 100 - achievement_pct; how much of target is still unmet, as %
    returned_units: float | None
    returned_value: float | None


def _col_sum(df: pd.DataFrame, col: str) -> float | None:
    if df.empty or col not in df.columns or df[col].isna().all():
        return None
    total = df[col].sum(skipna=True)
    return float(total) if pd.notna(total) else None


def compute_kpis(fact: pd.DataFrame, footfall: pd.DataFrame, target: pd.DataFrame) -> KpiBundle:
    net_sales = _col_sum(fact, "net_amount")

    gross_sales = _col_sum(fact, "gross_amount")
    gross_sales_is_derived = False
    if gross_sales is None and net_sales is not None and "discount_amount" in fact.columns:
        discount_total = _col_sum(fact, "discount_amount") or 0.0
        gross_sales = net_sales + discount_total
        gross_sales_is_derived = True

    discounts = _col_sum(fact, "discount_amount")

    cogs_gst_total = _col_sum(fact, "cogs_with_gst")
    net_profit = None
    gross_profit = None
    if net_sales is not None and cogs_gst_total is not None:
        # No distinct "gross sales profit" business definition exists in the
        # workbook (no store expense data), so both cards use the same
        # Net Sales - COGS-with-GST formula per the master prompt's fallback
        # rule, but stay separately labelled: Net Profit/Loss vs Gross Profit.
        net_profit = net_sales - cogs_gst_total
        gross_profit = net_sales - cogs_gst_total

    bill_quantity = _col_sum(fact, "bill_quantity")

    footfall_total = _col_sum(footfall, "footfall")
    # NOB source of record is TIME WISE FOOTFALL-NOB (store/day level, unaffected
    # by section/department/product filters slicing the transaction line items).
    nob = _col_sum(footfall, "nob")

    nob_transaction_count = (
        float(fact["bill_no"].dropna().nunique()) if "bill_no" in fact.columns and not fact.empty else None
    )

    atv = safe_divide(net_sales, nob)
    rpv = safe_divide(net_sales, footfall_total)
    basket_size = safe_divide(bill_quantity, nob)
    conversion_pct = safe_divide(nob, footfall_total)
    if conversion_pct is not None:
        conversion_pct *= 100

    sales_target = _col_sum(target, "target")
    achievement_pct = safe_divide(net_sales, sales_target)
    if achievement_pct is not None:
        achievement_pct *= 100

    remaining = sales_target - net_sales if sales_target is not None and net_sales is not None else None
    remaining_pct = 100 - achievement_pct if achievement_pct is not None else None

    returned_units = None
    returned_value = None
    if "bill_quantity" in fact.columns and not fact.empty:
        neg_qty = fact.loc[fact["bill_quantity"] < 0, "bill_quantity"]
        returned_units = float(-neg_qty.sum()) if not neg_qty.empty else 0.0
    if "net_amount" in fact.columns and not fact.empty:
        neg_amt = fact.loc[fact["net_amount"] < 0, "net_amount"]
        returned_value = float(-neg_amt.sum()) if not neg_amt.empty else 0.0

    return KpiBundle(
        net_sales=net_sales,
        gross_sales=gross_sales,
        gross_sales_is_derived=gross_sales_is_derived,
        discounts=discounts,
        net_profit=net_profit,
        gross_profit=gross_profit,
        bill_quantity=bill_quantity,
        footfall=footfall_total,
        nob=nob,
        nob_transaction_count=nob_transaction_count,
        atv=atv,
        rpv=rpv,
        basket_size=basket_size,
        conversion_pct=conversion_pct,
        sales_target=sales_target,
        achievement_pct=achievement_pct,
        remaining=remaining,
        remaining_pct=remaining_pct,
        returned_units=returned_units,
        returned_value=returned_value,
    )
