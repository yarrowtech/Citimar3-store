from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends

from config.kpi_thresholds import (
    achievement_status,
    atv_status,
    basket_size_status,
    conversion_status,
    remaining_status,
    rpv_status,
)
from src.comparison_engine import (
    build_deltas,
    kpis_for_window,
    previous_month_window,
    previous_period_window,
    same_period_last_year_window,
)
from src.data_loader import MasterDataset
from src.filter_engine import FilterState, apply_filters, filter_store_level_table
from src.kpi_engine import compute_kpis

from .deps import get_dataset, parse_filter_state

router = APIRouter(prefix="/api/kpis", tags=["kpis"])


def _clean(value):
    if isinstance(value, float) and value != value:  # NaN
        return None
    return value


@router.get("")
def get_kpis(dataset: MasterDataset = Depends(get_dataset), state=Depends(parse_filter_state)):
    fact = apply_filters(dataset.fact, state)
    footfall = filter_store_level_table(dataset.footfall, state)
    target = filter_store_level_table(dataset.target, state)

    current = compute_kpis(fact, footfall, target)
    payload = {k: _clean(v) for k, v in asdict(current).items()}

    statuses = {
        "atv": atv_status(current.atv),
        "rpv": rpv_status(current.rpv),
        "basket_size": basket_size_status(current.basket_size),
        "conversion_pct": conversion_status(current.conversion_pct),
        "achievement_pct": achievement_status(current.achievement_pct),
        "remaining_pct": remaining_status(current.remaining_pct),
    }

    comparisons = {}
    if state.start_date and state.end_date:
        # Comparisons keep the same store + product-hierarchy scope; only the
        # date window changes, so re-apply everything except the date bound
        # and let kpis_for_window slice the comparison window.
        date_free_state = FilterState(
            stores=state.stores,
            time_slot=state.time_slot,
            division=state.division,
            section=state.section,
            department=state.department,
            product_design_no=state.product_design_no,
            product_style=state.product_style,
            product_type=state.product_type,
            product_size=state.product_size,
            vendors=state.vendors,
        )
        store_only_state = FilterState(stores=state.stores, time_slot=state.time_slot)
        comparison_fact = apply_filters(dataset.fact, date_free_state)
        comparison_footfall = filter_store_level_table(dataset.footfall, store_only_state)
        comparison_target = filter_store_level_table(dataset.target, store_only_state)

        windows = {
            "previous_period": previous_period_window(state.start_date, state.end_date),
            "previous_month": previous_month_window(state.start_date, state.end_date),
            "same_period_last_year": same_period_last_year_window(state.start_date, state.end_date),
        }
        for label, (win_start, win_end) in windows.items():
            previous = kpis_for_window(comparison_fact, comparison_footfall, comparison_target, win_start, win_end)
            deltas = build_deltas(current, previous)
            comparisons[label] = {
                k: {kk: _clean(vv) for kk, vv in asdict(v).items()} for k, v in deltas.items()
            }

    return {"kpis": payload, "statuses": statuses, "comparisons": comparisons}
