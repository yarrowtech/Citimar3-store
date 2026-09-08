import openpyxl
import pandas as pd

from src import data_loader
from src.schema_detector import normalise_header, rename_to_canonical, resolve_schema


def test_normalise_header_case_whitespace_punctuation():
    assert normalise_header("  Bill Quentity ") == "bill quentity"
    assert normalise_header("BILL_QUANTITY") == "bill quantity"
    assert normalise_header("Bill-Quantity!!") == "bill quantity"


def test_resolve_schema_matches_aliases_case_insensitively():
    alias_map = {"net_amount": ["net amount", "net sales"], "date": ["date"]}
    columns = ["DATE", "Net Amount"]
    schema = resolve_schema("TEST", columns, alias_map)
    assert schema.get("date") == "DATE"
    assert schema.get("net_amount") == "Net Amount"
    assert schema.unresolved_canonical == []


def test_resolve_schema_reports_unresolved_fields():
    alias_map = {"net_amount": ["net amount"], "footfall": ["footfall"]}
    columns = ["Net Amount"]
    schema = resolve_schema("TEST", columns, alias_map)
    assert schema.unresolved_canonical == ["footfall"]


def test_rename_to_canonical_only_touches_resolved_columns():
    alias_map = {"net_amount": ["net amount"]}
    df = pd.DataFrame({"Net Amount": [1, 2], "Some Other Col": [3, 4]})
    schema = resolve_schema("TEST", list(df.columns), alias_map)
    renamed = rename_to_canonical(df, schema)
    assert "net_amount" in renamed.columns
    assert "Some Other Col" in renamed.columns


def _write_workbook(path, sheets: dict[str, pd.DataFrame]):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, df in sheets.items():
        ws = wb.create_sheet(name)
        ws.append(list(df.columns))
        for row in df.itertuples(index=False):
            ws.append(list(row))
    wb.save(path)


def test_load_master_dataset_skips_missing_sheet_without_crashing(tmp_path, monkeypatch):
    day_wise = pd.DataFrame(
        {
            "DATE": ["2026-01-01"],
            "STORE": ["CITIMART - NEW MARKET"],
            "DIVISION": ["Mens"],
            "SECTION": ["A"],
            "DEPARTMENT": ["A1"],
            "ITEM CODE": ["C1"],
            "PRODUCT DESIGN NO.": ["D1"],
            "PRODUCT BRAND": ["B1"],
            "PRODUCT STYLE": ["S1"],
            "PRODUCT TYPE": ["PLAIN"],
            "PRODUCT SIZE": ["M"],
            "ISVOID": ["No"],
            "VENDORS": ["V1"],
            "AGEING": ["1/1"],
            "TAX RATE": [5],
            "MAXIMUM RETAIL PRICE": [199],
            "RETAIL SELLING PRICE": [199],
            "PROMO TYPE": [""],
            "PROMO NAME": [""],
            "STANDARD RATE": [100.0],
            "BILL QUENTITY": [1],
            "GROSS AMOUNT": [199.0],
            "PROMO AMOUNT": [0.0],
            "DISCOUNT AMOUNT": [0.0],
            "NET AMOUNT": [199.0],
            "COST OF GOODS SOLD": [100.0],
            "COST OF GOODS SOLDS WITH GST": [105.0],
            "BILL NO.": ["B1"],
        }
    )
    # Intentionally omit SALES TARGET and TIME WISE FOOTFALL-NOB sheets.
    workbook_path = tmp_path / "DATASET.xlsx"
    _write_workbook(workbook_path, {"DAY WISE SALE": day_wise})

    monkeypatch.setattr(data_loader, "DATASET_PATH", workbook_path)
    monkeypatch.setattr(data_loader, "CLEANED_CACHE_PATH", tmp_path / "cache.pkl")

    dataset = data_loader.load_master_dataset(force_reload=True)

    assert dataset.loaded_sheets == ["DAY WISE SALE"]
    assert set(dataset.skipped_sheets) == {"SALES TARGET", "TIME WISE FOOTFALL-NOB"}
    assert len(dataset.fact) == 1
    assert dataset.target.empty
    assert dataset.footfall.empty
