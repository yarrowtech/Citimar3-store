import json

import pandas as pd
import plotly.graph_objects as go

from src import charts


def _fig(*traces, layout=None) -> dict:
    fig = go.Figure()
    for t in traces:
        fig.add_trace(t)
    if layout:
        fig.update_layout(**layout)
    return json.loads(fig.to_json())


def _two_bar_series() -> dict:
    return _fig(
        go.Bar(x=["Jan", "Feb", "Mar"], y=[1.0, 2.0, 3.0], name="Gross Sales"),
        go.Bar(x=["Jan", "Feb", "Mar"], y=[4.0, 5.0, 6.0], name="Net Sales"),
        layout={"xaxis": {"title": {"text": "Month"}}, "yaxis": {"title": {"text": "Sales"}}},
    )


def test_noop_when_chart_type_missing_or_unknown():
    src = _two_bar_series()
    assert charts.apply_chart_type(src, None) is src
    assert charts.apply_chart_type(src, "spider") is src


def test_noop_on_bespoke_figure():
    gauge = _fig(go.Indicator(mode="gauge+number", value=42))
    assert charts.apply_chart_type(gauge, "line") is gauge
    funnel = _fig(go.Funnel(y=["a", "b"], x=[10, 5]))
    assert charts.apply_chart_type(funnel, "bar") is funnel


def test_column_keeps_bars_vertical():
    out = charts.apply_chart_type(_two_bar_series(), "column")
    assert [t["type"] for t in out["data"]] == ["bar", "bar"]
    assert all(t.get("orientation", "v") == "v" for t in out["data"])


def test_bar_is_horizontal_and_swaps_axes():
    out = charts.apply_chart_type(_two_bar_series(), "bar")
    assert all(t["type"] == "bar" and t["orientation"] == "h" for t in out["data"])
    # x/y swapped: the category labels now sit on y
    assert list(out["data"][0]["y"]) == ["Jan", "Feb", "Mar"]
    assert list(out["data"][0]["x"]) == [1.0, 2.0, 3.0]


def test_line_converts_bars_to_scatter_lines():
    out = charts.apply_chart_type(_two_bar_series(), "line")
    assert all(t["type"] == "scatter" and t["mode"] == "lines+markers" for t in out["data"])


def test_area_fills_to_zero():
    out = charts.apply_chart_type(_two_bar_series(), "area")
    assert all(t["type"] == "scatter" and t["fill"] == "tozeroy" for t in out["data"])


def test_pie_collapses_to_primary_series():
    out = charts.apply_chart_type(_two_bar_series(), "pie")
    assert len(out["data"]) == 1
    assert out["data"][0]["type"] == "pie"
    assert list(out["data"][0]["labels"]) == ["Jan", "Feb", "Mar"]
    assert list(out["data"][0]["values"]) == [4.0, 5.0, 6.0]  # "Net Sales" series
    assert out["layout"].get("annotations")  # "shows Net Sales only" note


def test_bar3d_single_categorical_series_becomes_mesh3d():
    single = _fig(go.Bar(x=["A", "B", "C"], y=[10.0, 20.0, 30.0], name="Net Sales"))
    out = charts.apply_chart_type(single, "bar3d")
    assert out["data"][0]["type"] == "mesh3d"
    assert "scene" in out["layout"]


def test_bar3d_falls_back_to_column_for_multi_series():
    out = charts.apply_chart_type(_two_bar_series(), "bar3d")
    assert [t["type"] for t in out["data"]] == ["bar", "bar"]


def test_handles_base64_packed_arrays_from_a_real_builder():
    # A real src/charts.py figure whose x/y come back base64-packed ({dtype,bdata})
    # -- apply_chart_type must decode before transforming.
    fact = pd.DataFrame({"date": pd.to_datetime(["2026-07-01", "2026-08-01"]), "net_amount": [100.0, 200.0]})
    target = pd.DataFrame({"date": pd.to_datetime(["2026-07-01", "2026-08-01"]), "target": [300.0, 300.0]})
    fig_dict = charts.sales_overview_chart(fact, target, granularity="month")
    line = charts.apply_chart_type(fig_dict, "line")
    assert all(t["type"] == "scatter" for t in line["data"])
    pie = charts.apply_chart_type(fig_dict, "pie")
    assert pie["data"][0]["type"] == "pie"
    assert list(pie["data"][0]["values"]) == [100.0, 200.0]  # decoded Net Sales series
