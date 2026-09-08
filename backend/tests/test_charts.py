"""Non-gauge src/charts.py builders. Gauges live in test_charts_gauge.py; the
chart-type post-process transform lives in test_chart_types.py."""
import pandas as pd
import plotly.graph_objects as go

from src import charts


def _traces(fig_dict: dict) -> dict:
    """Rehydrate so base64-packed x/y arrays come back as plain lists, keyed by name."""
    fig = go.Figure(charts._deep_decode_arrays(fig_dict))
    return {t.name: t for t in fig.data}


def _fact() -> pd.DataFrame:
    return pd.DataFrame({
        "date": pd.to_datetime(["2026-07-05", "2026-07-20", "2026-08-03", "2026-08-25"]),
        "net_amount": [1000.0, 500.0, 2000.0, 800.0],
        "gross_amount": [1100.0, 550.0, 2200.0, 900.0],
    })


def _target() -> pd.DataFrame:
    return pd.DataFrame({
        "date": pd.to_datetime(["2026-07-05", "2026-08-03"]),
        "target": [2000.0, 3000.0],
    })


def test_sales_overview_chart_drops_gross_keeps_net_remaining_target():
    fig = charts.sales_overview_chart(_fact(), _target(), granularity="month")
    names = {t["name"] for t in fig["data"]}
    assert names == {"Net Sales", "Remaining", "Sales Target"}
    assert "Gross Sales" not in names


def test_sales_overview_chart_respects_granularity():
    monthly = _traces(charts.sales_overview_chart(_fact(), _target(), granularity="month"))
    daily = _traces(charts.sales_overview_chart(_fact(), _target(), granularity="day"))
    assert list(monthly["Net Sales"].x) == ["Jul 2026", "Aug 2026"]
    assert len(daily["Net Sales"].x) == 4


def test_sales_overview_chart_remaining_is_target_minus_net():
    t = _traces(charts.sales_overview_chart(_fact(), _target(), granularity="month"))
    for tv, nv, rv in zip(t["Sales Target"].y, t["Net Sales"].y, t["Remaining"].y):
        assert rv == tv - nv


def test_sales_overview_chart_empty_fact_is_empty_figure():
    fig = charts.sales_overview_chart(pd.DataFrame(), _target(), granularity="month")
    assert not fig["data"]


# --- Section 2 (Sales Performance), Phase 3 -----------------------------------

def _footfall_timeslot() -> pd.DataFrame:
    return pd.DataFrame({
        "date": pd.to_datetime(["2026-07-05", "2026-07-05", "2026-08-03"]),
        "time_slot": ["11.00 AM - 01.59 PM", "05.00 PM - 07.59 PM", "11.00 AM - 01.59 PM"],
        "footfall": [100.0, 200.0, 50.0],
        "nob": [40.0, 90.0, 20.0],
    })


def _comparison_fact() -> pd.DataFrame:
    from src.period_engine import WEEKDAY_TO_LABEL

    dates = pd.to_datetime(["2026-07-03", "2026-07-10", "2026-08-03", "2026-08-10", "2026-08-25"])
    return pd.DataFrame({
        "date": dates,
        "net_amount": [1000.0, 500.0, 2000.0, 800.0, 300.0],
        "day_name": [WEEKDAY_TO_LABEL[d] for d in dates.dayofweek],
        "day_of_month": dates.day,
        "year_month": dates.strftime("%Y-%m"),
        "month_name": dates.month_name(),
        "year": dates.year,
    })


def test_sales_trend_period_mode_has_rolling_avg_only_for_day():
    day = _traces(charts.sales_trend_chart(_fact(), pd.DataFrame(), dimension="period", granularity="day"))
    month = _traces(charts.sales_trend_chart(_fact(), pd.DataFrame(), dimension="period", granularity="month"))
    assert "7-Day Rolling Avg" in day
    assert "7-Day Rolling Avg" not in month
    assert "Net Sales" in month


def test_sales_trend_timeslot_mode_plots_footfall_and_nob():
    fig = charts.sales_trend_chart(pd.DataFrame(), _footfall_timeslot(), dimension="timeslot")
    names = {t["name"] for t in fig["data"]}
    assert names == {"Footfall", "NOB"}


def test_avg_sales_chart_is_a_mean_per_cyclic_bucket():
    t = _traces(charts.avg_sales_chart(_comparison_fact(), granularity="month"))
    bar = t["Avg Net Sales"]
    # August: mean(2000, 800, 300) = 1033.33...
    aug_idx = list(bar.x).index("August")
    assert round(bar.y[aug_idx], 2) == round((2000 + 800 + 300) / 3, 2)


def test_period_comparison_dispatch_per_dimension():
    fact = _comparison_fact()
    monthly = charts.period_comparison_chart(fact, dimension="monthly_same_day")
    weekly = charts.period_comparison_chart(fact, dimension="weekly_same_day")
    yearly = charts.period_comparison_chart(fact, dimension="yearly_month")
    assert "Monthly Same-Day" in monthly["layout"]["title"]["text"]
    assert "Weekly Same-Day" in weekly["layout"]["title"]["text"]
    assert "Yearly Same-Month" in yearly["layout"]["title"]["text"]


# --- Section 3 (Customer & Conversion) --------------------------------------

def _conversion_footfall() -> pd.DataFrame:
    # 2026-07-05 is a Sunday, 2026-08-03 a Monday.
    return pd.DataFrame({
        "date": pd.to_datetime(["2026-07-05", "2026-07-05", "2026-08-03"]),
        "time_slot": ["11.00 AM - 01.59 PM", "05.00 PM - 07.59 PM", "11.00 AM - 01.59 PM"],
        "footfall": [100.0, 200.0, 50.0],
        "nob": [40.0, 90.0, 20.0],
    })


def test_footfall_vs_nob_chart_date_and_timeslot_modes():
    ff = _conversion_footfall()
    date_mode = {t["name"] for t in charts.footfall_vs_nob_chart(ff, dimension="date")["data"]}
    assert date_mode == {"Footfall", "NOB", "Conversion %"}

    ts = _traces(charts.footfall_vs_nob_chart(ff, dimension="timeslot"))
    assert list(ts["Footfall"].x)[:1] == ["11.00 AM - 01.59 PM"]
    # 11 AM slot: nob 60 / footfall 150 * 100 = 40%
    conv = dict(zip(ts["Conversion %"].x, ts["Conversion %"].y))
    assert round(conv["11.00 AM - 01.59 PM"], 2) == 40.0


def test_footfall_vs_nob_chart_backward_compatible_positional_call():
    # streamlit_app.py still calls footfall_vs_nob_chart(footfall) positionally.
    fig = charts.footfall_vs_nob_chart(_conversion_footfall())
    assert {t["name"] for t in fig["data"]} == {"Footfall", "NOB", "Conversion %"}


def test_footfall_vs_net_sales_chart_joins_by_date():
    fig = charts.footfall_vs_net_sales_chart(_conversion_footfall(), _fact(), metric="footfall", dimension="date")
    names = {t["name"] for t in fig["data"]}
    assert names == {"Footfall", "Net Sales"}
    net = next(t for t in fig["data"] if t["name"] == "Net Sales")
    assert net["yaxis"] == "y2"


def test_nob_vs_net_sales_chart_dayofweek_mode():
    t = _traces(charts.nob_vs_net_sales_chart(_conversion_footfall(), _comparison_fact(), dimension="dayofweek"))
    assert list(t["NOB"].x) == charts.DAY_ORDER
    assert "Net Sales" in t


def test_footfall_vs_net_sales_chart_empty_is_empty_figure():
    fig = charts.footfall_vs_net_sales_chart(pd.DataFrame(), pd.DataFrame(), dimension="date")
    assert not fig["data"]


def test_footfall_nob_breakdown_chart_all_dimensions():
    ff = _conversion_footfall()
    dow = _traces(charts.footfall_nob_breakdown_chart(ff, dimension="dayofweek"))
    assert list(dow["Footfall"].x) == charts.DAY_ORDER
    ts = charts.footfall_nob_breakdown_chart(ff, dimension="timeslot")
    assert "Time-of-Day" in ts["layout"]["title"]["text"]
    dt = charts.footfall_nob_breakdown_chart(ff, dimension="date")
    assert {t["name"] for t in dt["data"]} == {"Footfall", "NOB"}


def test_conversion_funnel_by_timeslot_chart_one_trace_per_nonempty_slot():
    fig = charts.conversion_funnel_by_timeslot_chart(_conversion_footfall())
    # only two of the four bands have data
    assert len(fig["data"]) == 2
    assert all(t["type"] == "funnel" for t in fig["data"])
    names = {t["name"] for t in fig["data"]}
    assert names == {"11.00 AM - 01.59 PM", "05.00 PM - 07.59 PM"}


def test_conversion_funnel_by_timeslot_chart_empty_is_empty_figure():
    assert not charts.conversion_funnel_by_timeslot_chart(pd.DataFrame())["data"]


def _hierarchy_fact() -> pd.DataFrame:
    # Section "NEG" is net-negative overall (a big return), but its "KEEP"
    # department is net-positive -- the orphaned-parent case that made Plotly
    # refuse to draw the whole sunburst before the roll-up-from-kept-leaves fix.
    rows = [
        ("APPAREL", "MENS", "SHIRTS", 500.0, 2, "B1"),
        ("APPAREL", "MENS", "TROUSERS", 300.0, 1, "B2"),
        ("APPAREL", "NEG", "KEEP", 100.0, 1, "B3"),
        ("APPAREL", "NEG", "SINK", -900.0, 1, "B4"),
    ]
    return pd.DataFrame(rows, columns=["division", "section", "department", "net_amount", "bill_quantity", "bill_no"])


def test_category_drilldown_chart_no_orphaned_parents():
    fig = charts.category_drilldown_chart(_hierarchy_fact())
    tr = charts._deep_decode_arrays(fig)["data"][0]
    assert tr["type"] == "sunburst"
    ids = set(tr["ids"])
    # every non-root parent id must itself be a node
    assert all(p == "" or p in ids for p in tr["parents"])
    # net-negative leaf dropped, its positive sibling kept, parent present
    assert "APPAREL / NEG / KEEP" in ids
    assert "APPAREL / NEG / SINK" not in ids
    assert "APPAREL / NEG" in ids


def test_category_drilldown_chart_empty_and_no_levels():
    assert charts.category_drilldown_chart(pd.DataFrame())["data"] == []
    assert charts.category_drilldown_chart(pd.DataFrame({"net_amount": [1.0]}))["data"] == []


def test_top_category_chart_is_vertical_column():
    from src import tables

    tbl = tables.top_category_table(_hierarchy_fact(), "section", "net_amount", top_n=10)
    fig = charts.top_category_chart(tbl, "section", "net_amount")
    tr = charts._deep_decode_arrays(fig)["data"][0]
    assert tr["type"] == "bar" and tr.get("orientation") in (None, "v")
    # x is the category labels (so apply_chart_type's column/pie swaps stay valid)
    assert set(tr["x"]) <= {"MENS", "NEG"}
