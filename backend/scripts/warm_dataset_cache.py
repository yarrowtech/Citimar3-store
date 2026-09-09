"""Pre-warm backend/.cache/cleaned_master.pkl during the Render *build* step,
instead of paying the ~1-2 minute (often longer on a small instance) openpyxl
parse of DATASET.xlsx after the container is already live and serving traffic.

Why this fixes the post-deploy 502/503 window: `src.data_loader.load_master_dataset`
already skips re-parsing when a cache file exists whose stored `source_mtime`
matches DATASET.xlsx's current mtime (see its docstring). On Render's native
(non-Docker) runtime, files written during the Build Command are present on the
same filesystem the Start Command boots from, and idle spin-down -> spin-up on
the free tier restarts that same slug without re-running the build -- so a cache
warmed once here survives both the initial deploy AND every subsequent free-tier
sleep/wake cycle. It's invalidated (and rebuilt for free, same as always) the
moment DATASET.xlsx's mtime changes, e.g. a fresh deploy after replacing the
workbook.

Run from `backend/` (Render Build Command, appended after the pip install):

    python scripts/warm_dataset_cache.py

Safe to run repeatedly and safe if DATASET.xlsx is missing (e.g. a preview
environment with no dataset yet) -- it logs and exits 0 rather than failing
the build, since a missing/unreadable dataset should surface as the existing
runtime 503 (api/deps.get_dataset), not a failed deploy.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data_loader import load_master_dataset  # noqa: E402


def main() -> None:
    try:
        dataset = load_master_dataset()
    except FileNotFoundError as error:
        print(f"warm_dataset_cache: skipping -- {error}")
        return
    print(
        "warm_dataset_cache: cache ready "
        f"({len(dataset.fact):,} fact rows, {len(dataset.target):,} target rows, "
        f"{len(dataset.footfall):,} footfall rows)."
    )


if __name__ == "__main__":
    main()
