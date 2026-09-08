from __future__ import annotations

from fastapi import APIRouter, Depends

from config.settings import STORE_CODE_TO_NAME
from src.data_loader import MasterDataset
from src.filter_engine import (
    FILTER_HIERARCHY,
    available_values,
    dataset_date_bounds,
    default_filter_state,
    section_filter_widget,
    time_slot_options,
)

from .deps import get_dataset, parse_filter_state

router = APIRouter(prefix="/api/filters", tags=["filters"])


@router.get("/defaults")
def get_defaults(dataset: MasterDataset = Depends(get_dataset)):
    state = default_filter_state(dataset.fact)
    min_date, max_date = dataset_date_bounds(dataset.fact)
    return {
        "stores": state.stores,
        "store_names": {code: STORE_CODE_TO_NAME.get(code, code) for code in state.stores},
        "start_date": min_date.isoformat() if min_date else None,
        "end_date": max_date.isoformat() if max_date else None,
        "time_slot_options": time_slot_options(),
        **{field_name: available_values(dataset.fact, state, field_name) for field_name in FILTER_HIERARCHY},
    }


@router.get("/options")
def get_options(dataset: MasterDataset = Depends(get_dataset), state=Depends(parse_filter_state)):
    return {
        **{field_name: available_values(dataset.fact, state, field_name) for field_name in FILTER_HIERARCHY},
        "section_widget": section_filter_widget(dataset.fact, state),
    }
