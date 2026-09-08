"""Cleaning and standardisation pipeline for the DAY WISE SALE fact table plus
the two supporting worksheets. Every function returns both the transformed
data and a dict of counters so the caller can build the Data Quality panel
without re-scanning the frame. Never mutates the source workbook.
"""
from __future__ import annotations

import re

import pandas as pd

from config.settings import STORE_NAME_TO_CODE, VALID_GST_SLABS

_CURRENCY_STRIP_RE = re.compile(r"[₹$,\s]")

NUMERIC_FIELDS = [
    "tax_rate", "mrp", "retail_selling_price", "standard_rate",
    "bill_quantity", "gross_amount", "promo_amount", "discount_amount",
    "net_amount", "cogs", "cogs_with_gst",
]

# Categorical fields scanned for numeric-value contamination, reported (not
# blindly scrubbed) in the Data Quality panel.
CATEGORICAL_TEXT_FIELDS = [
    "division", "section", "department", "product_brand",
    "vendors", "ageing", "promo_type", "promo_name",
]

# Product hierarchy fields that must hold text codes only. Workbook inspection
# showed Excel auto-converted some cells to numbers or dates (e.g. a design
# code like "1-25" becoming the date Jan-2025, or a blank "type" cell leaking
# the row's MRP as a number) -- any non-string, non-null value in these
# columns is contamination and gets nulled, not just numeric-looking ones.
PRODUCT_HIERARCHY_FIELDS = ["product_design_no", "product_style", "product_type", "product_size"]


def strip_whitespace(df: pd.DataFrame) -> pd.DataFrame:
    """Strip leading/trailing spaces from headers and all text cell values."""
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    for col in df.columns:
        if df[col].dtype == object or "str" in str(df[col].dtype).lower():
            df[col] = df[col].astype("string").str.strip()
    return df


def coerce_numeric(series: pd.Series) -> pd.Series:
    """Strip currency symbols/thousands separators and convert to numeric,
    preserving valid negative values used for returns."""
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(series, errors="coerce")
    cleaned = series.astype("string").str.replace(_CURRENCY_STRIP_RE, "", regex=True)
    return pd.to_numeric(cleaned, errors="coerce")


def filter_void_rows(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Mandatory rule: drop every row where ISVOID == 'Yes' (case-insensitive)."""
    is_void = df["isvoid"].astype("string").str.strip().str.casefold() == "yes"
    dropped = int(is_void.sum())
    return df.loc[~is_void].copy(), dropped


def drop_exact_duplicates(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    dup_mask = df.duplicated(keep="first")
    dropped = int(dup_mask.sum())
    return df.loc[~dup_mask].copy(), dropped


def flag_zero_amount_duplicates(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Rows sharing bill_no+item_code+date with another line, where this
    specific line has net_amount == 0, are kept but tagged so the Data
    Quality panel can surface them for investigation (user decision: keep,
    don't drop -- amount is 0 so revenue totals are unaffected)."""
    df = df.copy()
    key_cols = [c for c in ["bill_no", "item_code", "date"] if c in df.columns]
    if not key_cols:
        df["is_zero_amount_duplicate"] = False
        return df, 0
    group_sizes = df.groupby(key_cols, dropna=False)[key_cols[0]].transform("size")
    tag = (group_sizes > 1) & (df["net_amount"].fillna(0) == 0)
    df["is_zero_amount_duplicate"] = tag
    return df, int(tag.sum())


_DATE_LIKE_STRING_RE = re.compile(r"^\d{2,4}[-/]\d{1,2}[-/]\d{1,2}([ T]\d{1,2}:\d{2}(:\d{2})?)?$")


def clean_product_hierarchy_fields(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    """Nulls out contamination in the product hierarchy fields: (1) non-string
    values (numbers, real datetime.datetime/Timestamp objects) -- must run on
    the raw, freshly-read frame BEFORE strip_whitespace()'s astype("string")
    call, because that cast would stringify a datetime.datetime cell into
    ordinary-looking text and hide the very contamination this is meant to
    catch; and (2) values that were already plain text but still spell out a
    date (e.g. a handful of rows hold the literal string "0168-09-01
    00:00:00" -- text, not a real datetime object, but still a "Years" value
    the field shouldn't hold)."""
    df = df.copy()
    counts: dict[str, int] = {}
    for col in PRODUCT_HIERARCHY_FIELDS:
        if col not in df.columns:
            continue
        series = df[col]
        is_non_string = series.notna() & ~series.map(lambda v: isinstance(v, str))
        is_date_like_text = series.notna() & series.map(
            lambda v: isinstance(v, str) and bool(_DATE_LIKE_STRING_RE.match(v.strip()))
        )
        is_contaminated = is_non_string | is_date_like_text
        count = int(is_contaminated.sum())
        counts[col] = count
        if count:
            df.loc[is_contaminated, col] = pd.NA
    return df, counts


def scan_categorical_numeric_contamination(df: pd.DataFrame, columns: list[str]) -> dict[str, int]:
    """Report-only scan (does not modify data): counts values in text
    categorical columns that are purely numeric, i.e. the semi-labelled
    mismatch the master prompt warns about, for the Data Quality panel."""
    counts: dict[str, int] = {}
    for col in columns:
        if col not in df.columns:
            continue
        numeric_like = pd.to_numeric(df[col], errors="coerce")
        counts[col] = int(numeric_like.notna().sum())
    return counts


def flag_tax_rate_outliers(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    df = df.copy()
    outlier = ~df["tax_rate"].isin(VALID_GST_SLABS)
    df["tax_rate_outlier"] = outlier
    return df, int(outlier.sum())


def add_store_code(df: pd.DataFrame) -> pd.DataFrame:
    """Maps the free-text STORE column to a standard code (NM/HB/CHW)."""
    df = df.copy()
    normalised = df["store"].astype("string").str.strip().str.upper().to_numpy(dtype=object)
    lookup = {store_name.upper(): store_code for store_name, store_code in STORE_NAME_TO_CODE.items()}
    df["store_code"] = [lookup.get(v) if v is not None else None for v in normalised]
    return df


def add_derived_date_fields(df: pd.DataFrame, date_col: str = "date") -> pd.DataFrame:
    df = df.copy()
    dt = pd.to_datetime(df[date_col], errors="coerce", dayfirst=True)
    df["date_display"] = dt.dt.strftime("%d-%m-%Y")
    df["day_of_month"] = dt.dt.day
    day_names = ["Mon", "Tues", "Weds", "Thurs", "Fri", "Sat", "Sun"]
    df["day_name"] = dt.dt.dayofweek.map(lambda i: day_names[i] if pd.notna(i) else pd.NA)
    df["week"] = dt.dt.isocalendar().week.astype("Int64")
    df["month_number"] = dt.dt.month
    month_names = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ]
    df["month_name"] = dt.dt.month.map(lambda m: month_names[m - 1] if pd.notna(m) else pd.NA)
    df["quarter"] = dt.dt.quarter
    df["year"] = dt.dt.year
    df["year_month"] = dt.dt.to_period("M").astype("string")
    df["is_weekend"] = dt.dt.dayofweek.isin([5, 6])
    return df


def clean_day_wise_sale(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Runs the full cleaning pipeline (see plan / README for the mandated
    order) and returns (cleaned_df, stats) where stats feeds the Data
    Quality panel."""
    stats: dict = {"rows_before": len(df)}

    # Must run before strip_whitespace(): it needs to see the raw Python
    # types (datetime.datetime, int, float) that Excel/openpyxl leaked into
    # these text columns, before they get stringified away.
    df, hierarchy_contamination = clean_product_hierarchy_fields(df)
    stats["product_hierarchy_values_nulled"] = hierarchy_contamination

    df = strip_whitespace(df)

    df, void_dropped = filter_void_rows(df)
    stats["void_rows_dropped"] = void_dropped

    df, exact_dupes = drop_exact_duplicates(df)
    stats["exact_duplicate_rows_dropped"] = exact_dupes

    df, zero_amount_tagged = flag_zero_amount_duplicates(df)
    stats["zero_amount_duplicate_rows_flagged"] = zero_amount_tagged

    for field in NUMERIC_FIELDS:
        if field in df.columns:
            df[field] = coerce_numeric(df[field])
    stats["invalid_numeric_values"] = {
        field: int(df[field].isna().sum()) for field in NUMERIC_FIELDS if field in df.columns
    }

    stats["categorical_numeric_contamination_scan"] = scan_categorical_numeric_contamination(
        df, CATEGORICAL_TEXT_FIELDS
    )

    df, tax_outliers = flag_tax_rate_outliers(df)
    stats["tax_rate_outlier_rows"] = tax_outliers

    df = add_store_code(df)
    stats["unmapped_store_rows"] = int(df["store_code"].isna().sum())

    df = add_derived_date_fields(df, date_col="date")

    stats["negative_value_rows"] = {
        field: int((df[field] < 0).sum()) for field in NUMERIC_FIELDS if field in df.columns
    }
    stats["rows_after"] = len(df)
    return df, stats


def melt_sales_target(df: pd.DataFrame) -> pd.DataFrame:
    """Wide (one column per store) -> long (date, store_code, target)."""
    df = strip_whitespace(df)
    store_cols = {"nm_target": "NM", "hb_target": "HB", "chw_target": "CHW"}
    frames = []
    for col, code in store_cols.items():
        if col not in df.columns:
            continue
        sub = df[["date", col]].rename(columns={col: "target"})
        sub["store_code"] = code
        sub["target"] = coerce_numeric(sub["target"])
        frames.append(sub)
    if not frames:
        return pd.DataFrame(columns=["date", "store_code", "target"])
    long_df = pd.concat(frames, ignore_index=True)
    long_df["date"] = pd.to_datetime(long_df["date"], errors="coerce", dayfirst=True)
    return long_df


def melt_footfall_nob(df: pd.DataFrame) -> pd.DataFrame:
    """Wide (footfall/NOB per store per time slot) -> long (date, time_slot,
    store_code, footfall, nob). DATE is forward-filled first because the
    workbook only stamps it on the first of each 4-row time-slot block."""
    df = strip_whitespace(df)
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce", dayfirst=True).ffill()
    store_pairs = {"NM": ("nm_footfall", "nm_nob"), "HB": ("hb_footfall", "hb_nob"), "CHW": ("chw_footfall", "chw_nob")}
    frames = []
    for code, (footfall_col, nob_col) in store_pairs.items():
        if footfall_col not in df.columns or nob_col not in df.columns:
            continue
        sub = df[["date", "time_slot", footfall_col, nob_col]].rename(
            columns={footfall_col: "footfall", nob_col: "nob"}
        )
        sub["store_code"] = code
        sub["footfall"] = coerce_numeric(sub["footfall"])
        sub["nob"] = coerce_numeric(sub["nob"])
        frames.append(sub)
    if not frames:
        return pd.DataFrame(columns=["date", "time_slot", "store_code", "footfall", "nob"])
    return pd.concat(frames, ignore_index=True)
