"""Central paths and configuration for the CITIMART Sales KPI Dashboard."""
from __future__ import annotations

from datetime import time
from pathlib import Path

# backend/ -- the root of the Python side of the project (config/, src/, api/,
# db/, DATASET.xlsx, .cache/, img/ all live directly under it). The repository
# root, which additionally holds frontend/, is PROJECT_ROOT.parent.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATASET_PATH = PROJECT_ROOT / "DATASET.xlsx"
CACHE_DIR = PROJECT_ROOT / ".cache"
CACHE_DIR.mkdir(exist_ok=True)
CLEANED_CACHE_PATH = CACHE_DIR / "cleaned_master.pkl"

# Live, writable workbook backing the Daily Dashboard tab -- unlike
# DATASET_PATH above, this file IS meant to be written to by the app. One
# shared sheet per data type (not one sheet per store) -- every row carries
# a STORE column (NM/HB/CHW) so all three stores' daily details live in one
# place per sheet instead of being scattered across 12 near-identical
# per-store tabs. src/daily_dashboard_store.py creates any of these sheets
# on first use if it doesn't already exist.
DAILY_DASHBOARD_XLSX_PATH = PROJECT_ROOT / "TEST_DAILY_DASHBOARD.xlsx"
DAILY_BILLS_SHEET = "BILLS"
DAILY_TARGETS_SHEET = "TARGETS"
DAILY_FOOTFALL_SHEET = "FOOTFALL"
DAILY_NOB_SHEET = "NOB"

CURRENCY_SYMBOL = "₹"  # INR rupee sign, used when the workbook does not identify a currency

REQUIRED_SHEETS = ["DAY WISE SALE", "SALES TARGET", "TIME WISE FOOTFALL-NOB"]

# Canonical store code -> full store name, matched against the STORE column's
# *actual* spelling found in DATASET.xlsx (verified during workbook inspection).
STORE_CODE_TO_NAME = {
    "NM": "CITIMART - NEW MARKET",
    "HB": "CITIMART - HATIBAGAN",
    "CHW": "CITIMART - CHOWRINGHEE",
}
STORE_NAME_TO_CODE = {v: k for k, v in STORE_CODE_TO_NAME.items()}

# Valid Indian GST slabs. Any TAX RATE outside this set is flagged as an
# outlier in the data-quality panel rather than silently corrected.
VALID_GST_SLABS = {0, 3, 5, 12, 18, 28}

# Sections/departments switch from checkboxes to a searchable multiselect
# once the unique-value count exceeds this threshold (master prompt Section 9.3).
FILTER_CHECKBOX_MAX_VALUES = 12

# Minimum date allowed in the graphical calendar filters (dataset floor is dynamic;
# this is only the outer bound requested by the master prompt: "Add upto 2999").
FILTER_MAX_YEAR = 2999

# The 4 time-of-day bands TIME WISE FOOTFALL-NOB is natively pre-bucketed
# into (verified against the live dataset's time_slot column -- this is the
# literal wording in the source data, not an invented label). DAY WISE SALE
# has no Bill Time column in the workbook, so it has no per-row time slot of
# its own -- the time-slot filter only ever narrows footfall/NOB figures, not
# sales/KPI figures drawn from DAY WISE SALE.
TIME_SLOT_ORDER = [
    "11.00 AM - 01.59 PM",
    "02.00 PM - 04.59 PM",
    "05.00 PM - 07.59 PM",
    "08.00 PM - 11.59 PM",
]

# (label, start-minute-of-day inclusive, end-minute-of-day exclusive) for
# each TIME_SLOT_ORDER band, e.g. 11:00 AM = 660, 2:00 PM = 840.
_TIME_SLOT_BANDS = [
    (TIME_SLOT_ORDER[0], 11 * 60, 14 * 60),
    (TIME_SLOT_ORDER[1], 14 * 60, 17 * 60),
    (TIME_SLOT_ORDER[2], 17 * 60, 20 * 60),
    (TIME_SLOT_ORDER[3], 20 * 60, 24 * 60),
]


def time_slot_for_time(value: time) -> str | None:
    """Buckets a clock time into one of TIME_SLOT_ORDER's 4 bands -- used by
    the Daily Dashboard (src/daily_dashboard_store.py) to compute a system-
    generated, non-editable Time Slot for each bill/footfall/NOB entry at
    write time, since (unlike DATASET.xlsx's TIME WISE FOOTFALL-NOB sheet,
    which comes pre-bucketed from the source workbook) the live daily log
    only has a raw clock time per entry. Returns None for a time outside all
    4 bands (before 11 AM) rather than guessing/clamping to the nearest one,
    matching this project's don't-fabricate rule -- an early-morning entry
    genuinely has no time slot rather than a wrong one."""
    minutes = value.hour * 60 + value.minute
    for label, start, end in _TIME_SLOT_BANDS:
        if start <= minutes < end:
            return label
    return None
