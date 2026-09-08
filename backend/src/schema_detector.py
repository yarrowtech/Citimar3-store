"""Resolves a worksheet's actual headers to canonical field names via the
alias tables in config/column_aliases.py. Matching is case-insensitive,
whitespace-normalised and punctuation-tolerant so future workbook versions
can rename headers without touching code.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import pandas as pd

_PUNCT_RE = re.compile(r"[^a-zA-Z0-9\s]")  # underscore is deliberately treated as a separator, not a word char
_WS_RE = re.compile(r"\s+")


def normalise_header(raw: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace: the shared key used
    for alias lookups so 'Bill Quentity', 'BILL_QUANTITY', 'bill-quantity'
    all resolve the same way."""
    text = str(raw).strip().lower()
    text = _PUNCT_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text).strip()
    return text


@dataclass
class SchemaMap:
    sheet_name: str
    canonical_to_actual: dict[str, str] = field(default_factory=dict)
    unresolved_canonical: list[str] = field(default_factory=list)
    unmapped_actual_columns: list[str] = field(default_factory=list)

    def get(self, canonical: str) -> str | None:
        return self.canonical_to_actual.get(canonical)

    def has(self, canonical: str) -> bool:
        return canonical in self.canonical_to_actual


def resolve_schema(sheet_name: str, columns: list[str], alias_map: dict[str, list[str]]) -> SchemaMap:
    """Build a canonical-field -> actual-header mapping for one worksheet."""
    normalised_actual = {normalise_header(c): c for c in columns}
    lookup: dict[str, str] = {}
    for canonical, aliases in alias_map.items():
        for alias in aliases:
            key = normalise_header(alias)
            if key in normalised_actual:
                lookup[canonical] = normalised_actual[key]
                break

    unresolved = [c for c in alias_map if c not in lookup]
    mapped_actual = set(lookup.values())
    unmapped_actual = [c for c in columns if c not in mapped_actual]

    return SchemaMap(
        sheet_name=sheet_name,
        canonical_to_actual=lookup,
        unresolved_canonical=unresolved,
        unmapped_actual_columns=unmapped_actual,
    )


def rename_to_canonical(df: pd.DataFrame, schema: SchemaMap) -> pd.DataFrame:
    """Return a copy of df with resolved columns renamed to their canonical
    names; unresolved/unmapped source columns are left untouched."""
    rename_map = {actual: canonical for canonical, actual in schema.canonical_to_actual.items()}
    return df.rename(columns=rename_map)
