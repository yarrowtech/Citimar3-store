from datetime import date

import pandas as pd

from src.filter_engine import (
    FilterState,
    apply_filters,
    available_departments,
    available_sections,
    available_values,
    default_filter_state,
    reset_unavailable_selections,
    section_filter_widget,
)


def _fact_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.to_datetime(
                ["2026-01-01", "2026-01-05", "2026-02-01", "2026-02-10", "2026-03-01"]
            ),
            "store_code": ["NM", "NM", "HB", "HB", "CHW"],
            "division": ["Mens", "Mens", "Kids", "Kids", "Ladies"],
            "section": ["Mens", "Mens", "Kids", "Kids", "Ladies"],
            "department": ["Shirts", "Trousers", "Toys", "Toys", "Sarees"],
            "product_design_no": ["D1", "D2", "D3", "D3", "D4"],
            "product_style": ["S1", "S2", "S3", "S3", "S4"],
            "product_type": ["PLAIN", "PRINTED", "PLAIN", "PLAIN", "PRINTED"],
            "product_size": ["M", "L", "S", "S", "XL"],
            "vendors": ["V1", "V1", "V2", "V2", "V3"],
            "net_amount": [100.0, 200.0, 300.0, 400.0, 500.0],
        }
    )


def test_apply_filters_by_store():
    df = _fact_df()
    state = FilterState(stores=["NM"])
    result = apply_filters(df, state)
    assert set(result["store_code"]) == {"NM"}
    assert len(result) == 2


def test_apply_filters_by_date_range():
    df = _fact_df()
    state = FilterState(start_date=date(2026, 2, 1), end_date=date(2026, 2, 28))
    result = apply_filters(df, state)
    assert len(result) == 2
    assert set(result["store_code"]) == {"HB"}


def test_apply_filters_section_and_department_intersection():
    df = _fact_df()
    state = FilterState(section=["Kids"], department=["Toys"])
    result = apply_filters(df, state)
    assert len(result) == 2
    assert set(result["department"]) == {"Toys"}


def test_apply_filters_product_hierarchy_fields():
    df = _fact_df()
    state = FilterState(product_style=["S3"], product_size=["S"], vendors=["V2"])
    result = apply_filters(df, state)
    assert len(result) == 2
    assert set(result["product_design_no"]) == {"D3"}


def test_available_sections_respond_to_store_selection():
    df = _fact_df()
    state = FilterState(stores=["NM"])
    sections = available_sections(df, state)
    assert sections == ["Mens"]


def test_available_departments_respond_to_section_selection():
    df = _fact_df()
    state = FilterState(section=["Kids"])
    departments = available_departments(df, state)
    assert departments == ["Toys"]


def test_available_values_product_style_responds_to_department():
    df = _fact_df()
    state = FilterState(department=["Toys"])
    styles = available_values(df, state, "product_style")
    assert styles == ["S3"]


def test_available_values_vendors_does_not_narrow_from_product_style():
    # vendors sits after product_style/type/size in FILTER_HIERARCHY, so
    # picking a product_style should still narrow vendors (vendors is scoped
    # by everything above it, including product_style).
    df = _fact_df()
    state = FilterState(product_style=["S3"])
    vendors = available_values(df, state, "vendors")
    assert vendors == ["V2"]


def test_no_data_filter_state_returns_empty_without_crash():
    df = _fact_df()
    state = FilterState(stores=["NM"], section=["Kids"])  # NM never sells Kids in this data
    result = apply_filters(df, state)
    assert result.empty


def test_default_filter_state_covers_full_range():
    df = _fact_df()
    state = default_filter_state(df)
    assert set(state.stores) == {"NM", "HB", "CHW"}
    assert state.start_date == date(2026, 1, 1)
    assert state.end_date == date(2026, 3, 1)


def test_section_filter_widget_switches_to_searchable_above_threshold():
    df = _fact_df()
    state = FilterState()
    assert section_filter_widget(df, state) == "checkbox"

    many_sections = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-01-01"] * 20),
            "store_code": ["NM"] * 20,
            "section": [f"Section{i}" for i in range(20)],
            "department": [f"Dept{i}" for i in range(20)],
            "net_amount": [100.0] * 20,
        }
    )
    assert section_filter_widget(many_sections, FilterState()) == "searchable_multiselect"


def test_reset_unavailable_selections_drops_stale_values():
    result = reset_unavailable_selections(["Kids", "Mens"], available=["Mens"])
    assert result == ["Mens"]


def test_reset_unavailable_selections_returns_none_when_nothing_valid():
    result = reset_unavailable_selections(["Kids"], available=["Mens"])
    assert result is None
