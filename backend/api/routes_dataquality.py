from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends

from src.data_loader import MasterDataset

from .deps import get_dataset

router = APIRouter(prefix="/api/data-quality", tags=["data-quality"])


@router.get("")
def get_data_quality(dataset: MasterDataset = Depends(get_dataset)):
    return asdict(dataset.profile)
