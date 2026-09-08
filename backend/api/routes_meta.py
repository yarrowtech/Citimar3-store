from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from config.settings import STORE_CODE_TO_NAME
from src.data_loader import MasterDataset
from src.filter_engine import dataset_date_bounds

from .deps import get_dataset

router = APIRouter(prefix="/api/meta", tags=["meta"])


@router.get("")
def get_meta(request: Request, dataset: MasterDataset = Depends(get_dataset)):
    min_date, max_date = dataset_date_bounds(dataset.fact)
    active_stores = sorted(dataset.fact["store_code"].dropna().unique().tolist()) if not dataset.fact.empty else []
    store_names = [STORE_CODE_TO_NAME.get(code, code) for code in active_stores]
    return {
        "active_stores": active_stores,
        "store_names": store_names,
        "date_range": (
            f"{min_date.strftime('%d-%m-%Y') if min_date else 'N/A'} – "
            f"{max_date.strftime('%d-%m-%Y') if max_date else 'N/A'}"
        ),
        "last_refresh": request.app.state.loaded_at.strftime("%d-%m-%Y %H:%M"),
    }
