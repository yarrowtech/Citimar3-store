"""Plotly figure builders (master prompt Section 13). Every chart: has a
business title, currency/percent/count formatting, hover info, empty-data
handling, and returns a plain dict (via _fig_to_dict(fig)) that the API layer
serialises to JSON for Plotly.js on the frontend. Charts never aggregate raw
rows themselves in a way that could double-count -- callers pass an
already-filtered fact/footfall/target frame.
"""
from __future__ import annotations

import base64
import json
import struct

import pandas as pd
import plotly.graph_objects as go

from config.kpi_thresholds import get_thresholds
from config.settings import CURRENCY_SYMBOL, TIME_SLOT_ORDER
from src import period_engine
from src.theme import apply_theme as apply_theme  # re-export: charts.apply_theme mirrors charts.apply_chart_type

DAY_ORDER = ["Mon", "Tues", "Weds", "Thurs", "Fri", "Sat", "Sun"]
MONTH_ORDER = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]
# pandas dt.dayofweek (Monday=0) -> the same abbreviations DAY_ORDER/fact's
# day_name column use, so day-of-week grouping stays consistent everywhere
# regardless of which frame (fact vs. footfall) supplies the date.
WEEKDAY_TO_LABEL = {0: "Mon", 1: "Tues", 2: "Weds", 3: "Thurs", 4: "Fri", 5: "Sat", 6: "Sun"}

# Week special-case (master prompt "Special Cases (only for WEEK and DAY)"):
# a coarser 3-bucket cut of the week instead of all 7 days.
WEEK_SEGMENT_ORDER = ["Startweek", "Midweek", "Endweek"]
WEEK_SEGMENT_BY_DAY = {
    "Mon": "Startweek", "Tues": "Startweek",
    "Weds": "Midweek", "Thurs": "Midweek", "Fri": "Midweek",
    "Sat": "Endweek", "Sun": "Endweek",
}


# Single source of truth for chart heights so every figure of a given kind
# renders at a consistent, readable size regardless of data volume. Width is
# left responsive (Plotly.newPlot is called with {responsive: true} on the
# frontend) so figures still fill their container on any screen size. These
# must stay in lockstep with the matching h-[..px] container classes on each
# <ChartPanel> in frontend/src/pages -- Plotly renders at the literal
# layout.height set here, so a mismatch produces clipping/whitespace.
STANDARD_CHART_HEIGHT = 460
GAUGE_HEIGHT = 360
FUNNEL_HEIGHT = 400
SUNBURST_HEIGHT = 640
BRIDGE_HEIGHT = 480
STANDARD_MARGIN = {"l": 60, "r": 40, "t": 70, "b": 60}

# Matches the app UI: Geist Variable for chart chrome (titles/axes/legend),
# Fira Code Variable for the gauge's big numeric readout -- both are already
# self-hosted/loaded by the React frontend, so referencing them here keeps
# chart typography visually consistent with the surrounding KPI cards
# instead of falling back to Plotly's small default sans-serif.
CHART_FONT_FAMILY = "'Geist Variable', -apple-system, 'Segoe UI', sans-serif"
CHART_MONO_FONT_FAMILY = "'Fira Code Variable', ui-monospace, monospace"
CHART_TRANSITION = {"duration": 400, "easing": "cubic-in-out"}

# Categorical palette for traces that don't have a fixed brand meaning (e.g.
# one line per month, one bar per year) and so can't hardcode a single color
# the way "Net Sales is always blue" does. Order is fixed and validated for
# CVD-safe adjacent-pair separation -- never cycle/reassign per render, and
# never let these fall back to Plotly's implicit colorway (see CHART_TEMPLATE).
CATEGORICAL_PALETTE = [
    "#2a78d6", "#eb6834", "#1baf7a", "#eda100",
    "#e87ba4", "#008300", "#4a3aa7", "#e34948",
]

# Pinned explicitly so every figure's JSON always embeds Plotly's own factory
# template, never whatever happens to be process-wide `pio.templates.default`
# at build time. Without this, importing `streamlit` (which registers its own
# "streamlit" template -- placeholder near-black colors like #000001..#000010
# meant to be swapped client-side only when st.plotly_chart(theme="streamlit")
# does the substitution) silently becomes the ambient default template for
# every go.Figure() built anywhere in that process, including here. Any trace
# below that doesn't set an explicit color then renders in those unreadable
# placeholder colors instead of Plotly's normal palette. "plotly" (not
# "plotly_white") matches what this app has always rendered before Streamlit
# entered the picture, so this is a no-op for the FastAPI/React app.
CHART_TEMPLATE = "plotly"


def _size(fig: go.Figure, height: int, margin: dict | None = None) -> go.Figure:
    """Applies the shared size/typography/animation theme. Called last by
    every chart builder below, after any chart-specific layout tweaks --
    Plotly's update_layout merges nested dicts recursively, so this never
    clobbers a title/axis-title string set earlier in the same function."""
    fig.update_layout(
        template=CHART_TEMPLATE,
        height=height,
        margin=margin or STANDARD_MARGIN,
        autosize=True,
        font={"family": CHART_FONT_FAMILY, "size": 13, "color": "#1e293b"},
        title={"font": {"size": 19, "family": CHART_FONT_FAMILY}},
        legend={"font": {"size": 13}},
        xaxis={"tickfont": {"size": 12}, "title": {"font": {"size": 14}}},
        yaxis={"tickfont": {"size": 12}, "title": {"font": {"size": 14}}},
        transition=CHART_TRANSITION,
    )
    return fig


def _fig_to_dict(fig: go.Figure) -> dict:
    """Plotly's Figure.to_dict() can leave numpy arrays / binary-packed
    typed arrays in the output (a Plotly 6 perf optimisation), which
    FastAPI's default JSON encoder can't serialise. Round-tripping through
    Figure.to_json() (which uses Plotly's own JSON encoder) guarantees a
    plain, JSON-safe dict of lists instead."""
    return json.loads(fig.to_json())


def _empty_figure(title: str, message: str = "No data available for the selected filters", height: int = STANDARD_CHART_HEIGHT) -> dict:
    fig = go.Figure()
    fig.update_layout(
        title=title,
        annotations=[{"text": message, "xref": "paper", "yref": "paper", "showarrow": False, "font": {"size": 14}}],
        xaxis={"visible": False},
        yaxis={"visible": False},
    )
    _size(fig, height)
    return _fig_to_dict(fig)


# ---------------------------------------------------------------------------
# Chart-type switcher (Historical Analytics Overhaul, Part A4)
# ---------------------------------------------------------------------------

# The curated set the frontend's <ChartTypeToggle> offers. "column" = vertical
# bars (the usual default), "bar" = horizontal. "bar3d" is deliberately
# live-view only -- never pin it into a REPORT_MANIFESTS `extra` (Kaleido
# renders 3D via headless WebGL, unreliable on a GPU-less server).
CURATED_CHART_TYPES = {"column", "bar", "line", "area", "pie", "bar3d"}

# A figure containing any of these carries bespoke geometry a mark swap would
# corrupt -- apply_chart_type is a no-op on it.
_UNSWITCHABLE_TRACE_TYPES = {
    "indicator", "funnel", "funnelarea", "sunburst", "treemap", "pie", "waterfall",
}

_MESH3D_FACES = [
    (0, 1, 2), (0, 2, 3), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4),
    (1, 2, 6), (1, 6, 5), (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7),
]


def _primary_series_index(names: list[str]) -> int:
    """Which trace a pie collapses to: the one literally named "Net Sales",
    else the first not named like a target/goal line, else the first."""
    for i, name in enumerate(names):
        if (name or "").strip().lower() == "net sales":
            return i
    for i, name in enumerate(names):
        if "target" not in (name or "").strip().lower():
            return i
    return 0


def _is_categorical(values) -> bool:
    if values is None:
        return False
    return any(not isinstance(v, (int, float)) or isinstance(v, bool) for v in values if v is not None)


# Plotly 6's Figure.to_json() can base64-pack a numeric array as {dtype, bdata}
# instead of a plain JSON list (a perf optimisation the frontend's Plotly.js and
# chartTable.ts both decode). go.Figure() does NOT decode it on the way back in,
# so apply_chart_type has to before it can read x/y values.
_TYPED_ARRAY_FORMATS = {"i1": "b", "u1": "B", "i2": "h", "u2": "H", "i4": "i", "u4": "I", "f4": "f", "f8": "d"}


def _decode_typed_array(spec: dict) -> list:
    fmt = _TYPED_ARRAY_FORMATS.get(spec.get("dtype"))
    if fmt is None:
        return []
    buffer = base64.b64decode(spec["bdata"])
    item_size = struct.calcsize(fmt)
    count = len(buffer) // item_size
    return list(struct.unpack(f"<{count}{fmt}", buffer[: count * item_size]))


def _deep_decode_arrays(obj):
    if isinstance(obj, dict):
        if "bdata" in obj and "dtype" in obj:
            return _decode_typed_array(obj)
        return {key: _deep_decode_arrays(value) for key, value in obj.items()}
    if isinstance(obj, list):
        return [_deep_decode_arrays(value) for value in obj]
    return obj


def _trace_xy(trace) -> tuple[list, list]:
    return (list(trace.x) if trace.x is not None else [], list(trace.y) if trace.y is not None else [])


def _trace_line_color(trace) -> str | None:
    """A single color to carry onto a converted line/scatter -- from a bar's
    marker.color or a scatter's line.color, ignoring per-point color arrays."""
    marker = getattr(trace, "marker", None)
    if marker is not None and isinstance(getattr(marker, "color", None), str):
        return marker.color
    line = getattr(trace, "line", None)
    if line is not None and isinstance(getattr(line, "color", None), str):
        return line.color
    return None


def _category_bars_to_mesh3d(categories: list, values: list, name: str) -> tuple:
    xs: list[float] = []
    ys: list[float] = []
    zs: list[float] = []
    i_idx: list[int] = []
    j_idx: list[int] = []
    k_idx: list[int] = []
    half = 0.3
    for n, raw in enumerate(values):
        try:
            height = float(raw)
        except (TypeError, ValueError):
            height = 0.0
        corners = [
            (n - half, -half, 0.0), (n + half, -half, 0.0), (n + half, half, 0.0), (n - half, half, 0.0),
            (n - half, -half, height), (n + half, -half, height), (n + half, half, height), (n - half, half, height),
        ]
        base = len(xs)
        for cx, cy, cz in corners:
            xs.append(cx)
            ys.append(cy)
            zs.append(cz)
        for a, b, c in _MESH3D_FACES:
            i_idx.append(base + a)
            j_idx.append(base + b)
            k_idx.append(base + c)
    mesh = go.Mesh3d(
        x=xs, y=ys, z=zs, i=i_idx, j=j_idx, k=k_idx,
        name=name, color=CATEGORICAL_PALETTE[0], opacity=1.0, flatshading=True, hoverinfo="skip",
    )
    return mesh, list(range(len(categories))), [str(c) for c in categories]


def apply_chart_type(fig_dict: dict, chart_type: str | None) -> dict:
    """Post-process a finished figure dict into an alternative mark type for the
    frontend's chart-type switcher. Returns ``fig_dict`` unchanged when
    ``chart_type`` is falsy / not curated, or the figure carries a bespoke
    trace (gauge / funnel / sunburst / bridge). Output is a complete, valid
    figure dict -- the report rasterizer runs the same bytes through Kaleido.

    column = vertical bars (default) | bar = horizontal | line = lines+markers
    | area = filled lines | pie = primary series only | bar3d = mesh3d cuboids
    (single categorical series only; otherwise falls back to ``column``).
    """
    if not chart_type or chart_type not in CURATED_CHART_TYPES:
        return fig_dict
    raw = list(fig_dict.get("data") or [])
    if not raw:
        return fig_dict
    kinds = [(t.get("type") or "scatter") for t in raw]
    if any(k in _UNSWITCHABLE_TRACE_TYPES for k in kinds) or any(k not in ("bar", "scatter") for k in kinds):
        return fig_dict

    # Decode any base64-packed x/y arrays, then rehydrate into a real Figure so
    # every read below sees plain Python values.
    src_fig = go.Figure(_deep_decode_arrays(fig_dict))
    traces = list(src_fig.data)
    names = [t.name for t in traces]
    title_text = src_fig.layout.title.text if src_fig.layout.title else None

    if chart_type == "bar3d":
        if len(traces) == 1 and _is_categorical(_trace_xy(traces[0])[0]):
            xvals, yvals = _trace_xy(traces[0])
            mesh, tickvals, ticktext = _category_bars_to_mesh3d(xvals, yvals, names[0] or "Value")
            fig = go.Figure(mesh)
            fig.update_layout(
                title=title_text,
                scene={
                    "xaxis": {"tickvals": tickvals, "ticktext": ticktext, "title": ""},
                    "yaxis": {"visible": False},
                    "zaxis": {"title": ""},
                    "aspectmode": "cube",
                },
            )
            _size(fig, STANDARD_CHART_HEIGHT)
            return _fig_to_dict(fig)
        chart_type = "column"  # fall through

    if chart_type == "pie":
        idx = _primary_series_index(names)
        xvals, yvals = _trace_xy(traces[idx])
        fig = go.Figure(go.Pie(labels=xvals, values=yvals, name=names[idx] or ""))
        fig.update_layout(title=title_text)
        if len(traces) > 1:
            fig.add_annotation(
                text=f"Pie shows {names[idx] or 'the primary series'} only",
                xref="paper", yref="paper", x=0.5, y=-0.08, showarrow=False, font={"size": 12},
            )
        _size(fig, STANDARD_CHART_HEIGHT)
        return _fig_to_dict(fig)

    new_traces = []
    for trace in traces:
        xvals, yvals = _trace_xy(trace)
        name = trace.name
        color = _trace_line_color(trace)
        # Carry a secondary-axis assignment (e.g. a Conversion % / Net Sales line
        # on "y2") through the mark swap -- without this, a dual-axis chart
        # collapses every series onto the primary axis when toggled. Horizontal
        # "bar" isn't offered for those charts (the axis swap has no clean
        # dual-axis form), so only column/line/area need it.
        yaxis = getattr(trace, "yaxis", None)
        if chart_type == "column":
            new_traces.append(
                go.Bar(x=xvals, y=yvals, name=name, orientation="v", marker={"color": color} if color else None, yaxis=yaxis)
            )
        elif chart_type == "bar":
            new_traces.append(go.Bar(x=yvals, y=xvals, name=name, orientation="h", marker={"color": color} if color else None))
        else:  # line / area
            new_traces.append(
                go.Scatter(
                    x=xvals, y=yvals, name=name,
                    mode="lines" if chart_type == "area" else "lines+markers",
                    fill="tozeroy" if chart_type == "area" else None,
                    line={"color": color} if color else None,
                    yaxis=yaxis,
                )
            )

    fig = go.Figure(data=new_traces, layout=src_fig.layout)
    fig.update_layout(scene=None)
    if chart_type == "bar":
        x_title = fig.layout.xaxis.title.text
        fig.update_layout(
            xaxis={"title": {"text": fig.layout.yaxis.title.text}},
            yaxis={"title": {"text": x_title}},
        )
    return _fig_to_dict(fig)


def net_vs_gross_sales_chart(fact: pd.DataFrame, granularity: str = "month_name") -> dict:
    title = "Net vs Gross Sales"
    if fact.empty:
        return _empty_figure(title)
    group_col = {"year": "year", "quarter": "quarter", "month": "year_month", "week": "week", "day": "date_display"}.get(
        granularity, "year_month"
    )
    grouped = fact.groupby(group_col, dropna=True).agg(net=("net_amount", "sum"), gross=("gross_amount", "sum")).reset_index()
    grouped["discount_gap"] = grouped["gross"] - grouped["net"]
    fig = go.Figure()
    fig.add_bar(x=grouped[group_col], y=grouped["gross"], name="Gross Sales", marker_color="#94a3b8")
    fig.add_bar(x=grouped[group_col], y=grouped["net"], name="Net Sales", marker_color="#2563eb")
    fig.add_trace(go.Scatter(x=grouped[group_col], y=grouped["discount_gap"], name="Discount Gap", mode="lines+markers", yaxis="y2", line={"color": "#f59e0b"}, marker={"color": "#f59e0b"}))
    fig.update_layout(
        title=title,
        barmode="group",
        yaxis={"title": f"Sales ({CURRENCY_SYMBOL})"},
        yaxis2={"title": f"Discount Gap ({CURRENCY_SYMBOL})", "overlaying": "y", "side": "right"},
        hovermode="x unified",
    )
    _size(fig, STANDARD_CHART_HEIGHT)
    return _fig_to_dict(fig)


def week_segment_chart(fact: pd.DataFrame) -> dict:
    """Week special case: Startweek (Mon-Tue) / Midweek (Wed-Fri) / Endweek
    (Sat-Sun) net sales -- a coarser cut than the 7-day breakdown in
    avg_sales_by_day_of_week_chart, for spotting whether sales lean toward
    the start, middle, or weekend of the week."""
    title = "Weekly Trend: Startweek vs Midweek vs Endweek"
    if fact.empty or "day_name" not in fact.columns:
        return _empty_figure(title)
    segment = fact["day_name"].map(WEEK_SEGMENT_BY_DAY)
    grouped = fact.groupby(segment, dropna=True)["net_amount"].sum().reindex(WEEK_SEGMENT_ORDER)
    fig = go.Figure(go.Bar(x=WEEK_SEGMENT_ORDER, y=grouped.values, marker_color=["#2563eb", "#0ea5e9", "#f59e0b"]))
    fig.update_layout(title=title, yaxis={"title": f"Net Sales ({CURRENCY_SYMBOL})"})
    _size(fig, STANDARD_CHART_HEIGHT)
    return _fig_to_dict(fig)


def footfall_vs_nob_chart(footfall: pd.DataFrame, *, dimension: str = "date") -> dict:
    """Footfall + NOB grouped bars with a Conversion % (NOB / Footfall) line on
    a secondary axis. ``dimension="date"`` plots the raw over-time trend;
    ``dimension="timeslot"`` sums into the workbook's four
    TIME WISE FOOTFALL-NOB bands instead (which store hours convert best).
    The route may run apply_chart_type() over the result for <ChartTypeToggle>."""
    if dimension == "timeslot":
        title = "Footfall vs Number of Bills & Conversion % (by Time Slot)"
        if footfall.empty or "time_slot" not in footfall.columns:
            return _empty_figure(title)
        grouped = (
            footfall.groupby("time_slot").agg(footfall=("footfall", "sum"), nob=("nob", "sum")).reindex(TIME_SLOT_ORDER).reset_index()
        )
        x = grouped["time_slot"]
    else:
        title = "Footfall vs Number of Bills & Conversion %"
        if footfall.empty:
            return _empty_figure(title)
        # `.dt.normalize()` (zeroes time-of-day, keeps datetime64) instead of
        # `.dt.date` (boxes every row into a Python `date` object) -- see
        # filter_engine._apply_store_date's comment; Plotly's JSON encoder
        # handles datetime64 groupby keys the same as python `date` objects.
        grouped = footfall.groupby(footfall["date"].dt.normalize()).agg(footfall=("footfall", "sum"), nob=("nob", "sum")).reset_index()
        x = grouped["date"]
    grouped["conversion_pct"] = (grouped["nob"] / grouped["footfall"] * 100).where(grouped["footfall"] != 0)
    fig = go.Figure()
    fig.add_bar(x=x, y=grouped["footfall"], name="Footfall", marker_color="#94a3b8")
    fig.add_bar(x=x, y=grouped["nob"], name="NOB", marker_color="#2563eb")
    fig.add_trace(
        go.Scatter(x=x, y=grouped["conversion_pct"], name="Conversion %", mode="lines+markers", yaxis="y2", line={"color": "#f59e0b"})
    )
    fig.update_layout(
        title=title,
        barmode="group",
        yaxis={"title": "Count"},
        yaxis2={"title": "Conversion %", "overlaying": "y", "side": "right"},
        hovermode="x unified",
    )
    _size(fig, STANDARD_CHART_HEIGHT)
    return _fig_to_dict(fig)


# Footfall / NOB grouped-bar breakdown -- Customer & Conversion tab. Three
# cyclic/linear cuts of the same TIME WISE FOOTFALL-NOB frame, merged into one
# switchable chart (was footfall_nob_by_dayofweek_chart +
# footfall_nob_by_timeslot_chart as two separate panels).
_FOOTFALL_NOB_BREAKDOWN_TITLES = {
    "dayofweek": "Footfall vs NOB: Day-of-Week Performance",
    "timeslot": "Footfall vs NOB: Time-of-Day Performance",
    "date": "Footfall vs NOB: Daily Trend",
}


def _footfall_nob_breakdown_grouped(footfall: pd.DataFrame, dimension: str) -> tuple[list, pd.DataFrame] | None:
    """(x labels, grouped frame with footfall/nob columns) for the requested
    dimension, or None when the source frame can't support it."""
    if footfall.empty:
        return None
    if dimension == "timeslot":
        if "time_slot" not in footfall.columns:
            return None
        grouped = footfall.groupby("time_slot").agg(footfall=("footfall", "sum"), nob=("nob", "sum")).reindex(TIME_SLOT_ORDER)
        return TIME_SLOT_ORDER, grouped
    if dimension == "date":
        grouped = footfall.groupby(footfall["date"].dt.normalize()).agg(footfall=("footfall", "sum"), nob=("nob", "sum"))
        return list(grouped.index), grouped
    # dayofweek (default)
    df = footfall.copy()
    df["day_name"] = df["date"].dt.dayofweek.map(WEEKDAY_TO_LABEL)
    grouped = df.groupby("day_name").agg(footfall=("footfall", "sum"), nob=("nob", "sum")).reindex(DAY_ORDER)
    return DAY_ORDER, grouped


def footfall_nob_breakdown_chart(footfall: pd.DataFrame, *, dimension: str = "dayofweek") -> dict:
    """Footfall vs NOB grouped bars, cut by ``dimension``: ``dayofweek``
    (Mon..Sun), ``timeslot`` (the workbook's four bands), or ``date`` (raw
    daily trend). The route may run apply_chart_type() over the result."""
    title = _FOOTFALL_NOB_BREAKDOWN_TITLES.get(dimension, _FOOTFALL_NOB_BREAKDOWN_TITLES["dayofweek"])
    grouped = _footfall_nob_breakdown_grouped(footfall, dimension)
    if grouped is None:
        return _empty_figure(title)
    x, frame = grouped
    fig = go.Figure()
    fig.add_bar(x=x, y=frame["footfall"], name="Footfall", marker_color="#94a3b8")
    fig.add_bar(x=x, y=frame["nob"], name="NOB", marker_color="#2563eb")
    layout: dict = {"title": title, "barmode": "group", "yaxis": {"title": "Count"}}
    if dimension in ("dayofweek", "timeslot"):
        layout["xaxis"] = {"categoryorder": "array", "categoryarray": list(x)}
    fig.update_layout(**layout)
    _size(fig, STANDARD_CHART_HEIGHT)
    return _fig_to_dict(fig)


def _visitor_vs_net_sales_grouped(footfall: pd.DataFrame, fact: pd.DataFrame, metric: str, dimension: str):
    """(x labels, visitor-metric series, net-sales series) aligned on the
    requested dimension, or None when neither frame has any rows.

    Net Sales is joined to Footfall/NOB by *date* only -- DAY WISE SALE has no
    bill-time column, so there is no time-slot cut of Net Sales to offer here
    (see CLAUDE.md). Days present in one frame but not the other stay NaN
    rather than a fabricated 0."""
    if footfall.empty and fact.empty:
        return None
    if dimension == "dayofweek":
        f = (
            footfall.assign(_k=footfall["date"].dt.dayofweek.map(WEEKDAY_TO_LABEL)).groupby("_k")[metric].sum()
            if not footfall.empty else pd.Series(dtype=float)
        )
        s = (
            fact.assign(_k=fact["date"].dt.dayofweek.map(WEEKDAY_TO_LABEL)).groupby("_k")["net_amount"].sum()
            if not fact.empty else pd.Series(dtype=float)
        )
        f, s = f.reindex(DAY_ORDER), s.reindex(DAY_ORDER)
        return DAY_ORDER, f, s
    # date (default)
    f = footfall.groupby(footfall["date"].dt.normalize())[metric].sum() if not footfall.empty else pd.Series(dtype=float)
    s = fact.groupby(fact["date"].dt.normalize())["net_amount"].sum() if not fact.empty else pd.Series(dtype=float)
    idx = f.index.union(s.index).sort_values()
    f, s = f.reindex(idx), s.reindex(idx)
    return list(idx), f, s


def footfall_vs_net_sales_chart(
    footfall: pd.DataFrame, fact: pd.DataFrame, *, metric: str = "footfall", dimension: str = "date"
) -> dict:
    """``metric`` ("footfall" | "nob") grouped bars against a Net Sales line on
    a secondary currency axis. ``dimension`` is ``date`` (daily trend) or
    ``dayofweek`` -- no time-slot cut (Net Sales has no bill-time granularity).
    The route may run apply_chart_type() over the result."""
    metric_label = "Footfall" if metric == "footfall" else "NOB"
    title = f"{metric_label} vs Net Sales" + (" (Day of Week)" if dimension == "dayofweek" else "")
    grouped = _visitor_vs_net_sales_grouped(footfall, fact, metric, dimension)
    if grouped is None:
        return _empty_figure(title)
    x, visitor, net = grouped
    fig = go.Figure()
    fig.add_bar(x=x, y=visitor.values, name=metric_label, marker_color="#94a3b8")
    fig.add_trace(
        go.Scatter(x=x, y=net.values, name="Net Sales", mode="lines+markers", yaxis="y2", line={"color": "#f59e0b"})
    )
    layout: dict = {
        "title": title,
        "yaxis": {"title": "Count"},
        "yaxis2": {"title": f"Net Sales ({CURRENCY_SYMBOL})", "overlaying": "y", "side": "right"},
        "hovermode": "x unified",
    }
    if dimension == "dayofweek":
        layout["xaxis"] = {"categoryorder": "array", "categoryarray": list(x)}
    fig.update_layout(**layout)
    _size(fig, STANDARD_CHART_HEIGHT)
    return _fig_to_dict(fig)


def nob_vs_net_sales_chart(footfall: pd.DataFrame, fact: pd.DataFrame, *, dimension: str = "date") -> dict:
    """NOB (number of bills) vs Net Sales -- see footfall_vs_net_sales_chart."""
    return footfall_vs_net_sales_chart(footfall, fact, metric="nob", dimension=dimension)


def footfall_nob_by_dayofweek_chart(footfall: pd.DataFrame) -> dict:
    """Day special case: Footfall vs NOB summed by day-of-week (Mon..Sun),
    a performance-by-weekday view rather than footfall_vs_nob_chart's raw
    over-time trend."""
    title = "Footfall vs NOB: Day-of-Week Performance"
    if footfall.empty:
        return _empty_figure(title)
    df = footfall.copy()
    df["day_name"] = df["date"].dt.dayofweek.map(WEEKDAY_TO_LABEL)
    grouped = df.groupby("day_name").agg(footfall=("footfall", "sum"), nob=("nob", "sum")).reindex(DAY_ORDER)
    fig = go.Figure()
    fig.add_bar(x=DAY_ORDER, y=grouped["footfall"], name="Footfall", marker_color="#94a3b8")
    fig.add_bar(x=DAY_ORDER, y=grouped["nob"], name="NOB", marker_color="#2563eb")
    fig.update_layout(
        title=title,
        barmode="group",
        yaxis={"title": "Count"},
        xaxis={"categoryorder": "array", "categoryarray": DAY_ORDER},
    )
    _size(fig, STANDARD_CHART_HEIGHT)
    return _fig_to_dict(fig)


def footfall_nob_by_timeslot_chart(footfall: pd.DataFrame, title: str = "Footfall vs NOB: Time-of-Day Performance") -> dict:
    """Day special case: Footfall vs NOB summed by the workbook's own
    TIME WISE FOOTFALL-NOB time-slot bands -- which store hours actually
    convert footfall into transactions best. `title` is overridable so
    daily_footfall_vs_nob_chart below can reuse this exact bar-building
    logic (DRY -- one place draws a Footfall-vs-NOB-by-time-slot chart) for
    the Daily Dashboard's live data under its own, differently-worded title,
    without duplicating the trace/layout code a second time."""
    if footfall.empty or "time_slot" not in footfall.columns:
        return _empty_figure(title)
    grouped = footfall.groupby("time_slot").agg(footfall=("footfall", "sum"), nob=("nob", "sum")).reindex(TIME_SLOT_ORDER)
    fig = go.Figure()
    fig.add_bar(x=TIME_SLOT_ORDER, y=grouped["footfall"], name="Footfall", marker_color="#94a3b8")
    fig.add_bar(x=TIME_SLOT_ORDER, y=grouped["nob"], name="NOB", marker_color="#2563eb")
    fig.update_layout(title=title, barmode="group", yaxis={"title": "Count"})
    _size(fig, STANDARD_CHART_HEIGHT)
    return _fig_to_dict(fig)


def daily_footfall_vs_nob_chart(breakdown: dict[str, dict[str, float]]) -> dict:
    """The Daily Dashboard's own simple Footfall-vs-NOB-by-Time-Slot view --
    just the two bars, no Conversion % line, for a reader who wants the
    plainest possible side-by-side comparison (daily_timeslot_breakdown_chart
    above is the richer version, with a Conversion % line, for the same live
    data). `breakdown` is src/daily_dashboard_store.compute_live_timeslot_breakdown's
    output, already keyed by TIME_SLOT_ORDER."""
    title = "Footfall vs NOB (based on Time Slot)"
    footfall_vals = [breakdown[slot]["footfall"] for slot in TIME_SLOT_ORDER]
    nob_vals = [breakdown[slot]["nob"] for slot in TIME_SLOT_ORDER]
    if not any(footfall_vals) and not any(nob_vals):
        return _empty_figure(title)
    df = pd.DataFrame({"time_slot": TIME_SLOT_ORDER, "footfall": footfall_vals, "nob": nob_vals})
    return footfall_nob_by_timeslot_chart(df, title=title)


def daily_timeslot_breakdown_chart(breakdown: dict[str, dict[str, float]], day_target: float | None = None) -> dict:
    """The Daily Dashboard's own Time Slot view -- now sales-based: Net Sales
    per time slot (bars) against the whole-day admin Sales Target drawn as a
    horizontal reference line. There is no per-slot target in the data, so
    every slot is compared to the full-day target -- the same convention
    src/daily_report.py's slot-level table already uses (it repeats the
    whole-day target on every slot row rather than fabricating a per-slot
    split). Footfall/NOB/Conversion by time slot is the separate
    daily_footfall_vs_nob_chart shown alongside this on the same page, so
    that view isn't lost -- this one just answers "which part of the day
    earned the money, and how far are we from target". `breakdown` is
    src/daily_dashboard_store.compute_live_timeslot_breakdown's output --
    already keyed by TIME_SLOT_ORDER, so no reindex is needed here."""
    title = "Today's Performance by Time Slot"
    net_sales_vals = [breakdown[slot]["net_sales"] for slot in TIME_SLOT_ORDER]
    if not any(net_sales_vals) and not day_target:
        return _empty_figure(title)
    fig = go.Figure()
    fig.add_bar(x=TIME_SLOT_ORDER, y=net_sales_vals, name="Net Sales", marker_color="#2563eb")
    if day_target:
        fig.add_hline(
            y=day_target,
            line={"color": "#f59e0b", "width": 2, "dash": "dash"},
            annotation_text=f"Day Sales Target: {CURRENCY_SYMBOL}{day_target:,.0f}",
            annotation_position="top left",
        )
    fig.update_layout(
        title=title,
        yaxis={"title": f"Net Sales ({CURRENCY_SYMBOL})"},
        hovermode="x unified",
    )
    _size(fig, STANDARD_CHART_HEIGHT)
    return _fig_to_dict(fig)


# Vivid speedometer-band colors -- same red/yellow/green hue families as the
# KPI card status colors (frontend/src/index.css's --status-*), just more
# saturated than a status badge/pill needs to be, since these fill an entire
# dial band rather than a small chip. Kept as their own constants (not
# config/kpi_thresholds.py, which owns the *numeric* red/yellow/green
# breakpoints, not colors) so every gauge_chart() caller renders an
# identical dial.
_GAUGE_RED = "#dc2626"
_GAUGE_YELLOW = "#eab308"
_GAUGE_GREEN = "#16a34a"
_GAUGE_BEZEL = "#1e293b"
_GAUGE_NEEDLE = "#111827"


def _gauge_axis_range(value: float, red_below: float, green_at: float, reverse: bool) -> tuple[float, float]:
    """The gauge's [min, max] axis bounds -- padded past the red/green
    thresholds (and past the live value, if it's off-scale) so all 3 bands
    keep real width and the value never clamps to an axis endpoint it
    hasn't actually reached.

    reverse=True gauges (Remaining %) put the "good" (green) zone at the LOW
    end, and that zone can be *negative* -- Remaining % goes below 0 once
    Achievement % passes 100 (over-target), and green_at itself mirrors
    Achievement %'s strict >100 rule (100-100=0), so the green cutoff is
    already right at 0 with nothing below it. A hardcoded axis min of 0 (the
    right choice for every non-reverse gauge here, since ATV/Conversion
    %/Achievement % can't go negative) would leave the green zone exactly
    zero-width forever and clamp any negative value to the same spot as
    zero -- this is the bug that made Remaining % never show green and
    stick its needle at the start on an over-achieved day. Padding the
    minimum below green_at (and below the value itself, if it's already
    lower) fixes both at once."""
    if reverse:
        pad = max(red_below - green_at, 1) * 0.3
        axis_min = min(0.0, green_at - pad, value - pad)
        axis_max = max(red_below * 1.3, green_at * 1.3, value * 1.2, axis_min + 1)
    else:
        axis_min = 0.0
        axis_max = max(red_below * 1.3, green_at * 1.3, value * 1.2, 1)
    return axis_min, axis_max


def gauge_chart(
    value: float | None,
    title: str,
    target: float | None,
    red_below: float,
    green_at: float,
    suffix: str = "",
    prefix: str = "",
    reverse: bool = False,
) -> dict:
    """Plotly Indicator version of the gauge -- used only by the Streamlit
    apps (streamlit_app.py calls this directly). The FastAPI/React path uses
    gauge_spec() below instead: frontend/src/components/GlossyGauge.tsx
    draws a real analog-speedometer needle in SVG, which Plotly's Indicator
    can't (it has no true needle primitive, only a `threshold` line as a
    stand-in, which is what this function still uses).

    reverse=True is for "lower is better" metrics (e.g. Remaining %): the
    red/yellow/green band order flips so red still means "bad", even though
    it now sits at the high end of the axis rather than the low end."""
    if value is None:
        return _empty_figure(title, "N/A — required source field not available", height=GAUGE_HEIGHT)
    axis_min, axis_max = _gauge_axis_range(value, red_below, green_at, reverse)
    if reverse:
        steps = [
            {"range": [axis_min, green_at], "color": _GAUGE_GREEN},
            {"range": [green_at, red_below], "color": _GAUGE_YELLOW},
            {"range": [red_below, axis_max], "color": _GAUGE_RED},
        ]
    else:
        steps = [
            {"range": [axis_min, red_below], "color": _GAUGE_RED},
            {"range": [red_below, green_at], "color": _GAUGE_YELLOW},
            {"range": [green_at, axis_max], "color": _GAUGE_GREEN},
        ]
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number+delta",
            value=value,
            number={"suffix": suffix, "prefix": prefix, "font": {"size": 42, "family": CHART_MONO_FONT_FAMILY, "color": "#0f172a"}},
            delta={"reference": target, "font": {"size": 16, "family": CHART_MONO_FONT_FAMILY}} if target is not None else None,
            gauge={
                "axis": {"range": [axis_min, axis_max], "tickfont": {"size": 12}, "tickcolor": _GAUGE_BEZEL, "tickwidth": 2},
                "bar": {"color": "rgba(0,0,0,0)"},
                "bgcolor": "white",
                "bordercolor": _GAUGE_BEZEL,
                "borderwidth": 4,
                "steps": steps,
                "threshold": {"line": {"color": _GAUGE_NEEDLE, "width": 6}, "thickness": 0.9, "value": value},
            },
            title={"text": title, "font": {"size": 17, "family": CHART_FONT_FAMILY}},
        )
    )
    _size(fig, GAUGE_HEIGHT, margin={"l": 30, "r": 30, "t": 70, "b": 20})
    # Unlike every other chart here, a gauge's visible label lives on the
    # Indicator trace's own `title` above -- the figure-level layout.title
    # is never set to a string first, so _size()'s title={"font": ...} merge
    # leaves layout.title.text unset. Plotly.js then renders that as the
    # literal word "undefined" instead of nothing, so it must be cleared
    # explicitly here.
    fig.update_layout(title_text="")
    return _fig_to_dict(fig)


def gauge_spec(
    value: float | None,
    title: str,
    target: float | None,
    red_below: float,
    green_at: float,
    suffix: str = "",
    prefix: str = "",
    reverse: bool = False,
    zero_if_missing: bool = False,
) -> dict:
    """Plain-JSON gauge description (not a Plotly figure) for the FastAPI/
    React path -- frontend/src/components/GlossyGauge.tsx renders this as a
    true analog speedometer (chrome bezel, needle, tick marks), which Plotly
    can't draw. Same red_below/green_at business thresholds and reverse
    semantics as gauge_chart() above (still config/kpi_thresholds.py-driven,
    nothing duplicated here) -- `_gauge_axis_range` is shared by both so a
    React gauge and its Streamlit counterpart always land on the same
    numbers.

    zero_if_missing renders a missing (None) value as a real gauge with the
    needle parked at 0 instead of the "N/A" placeholder -- the Daily
    Operations gauges pass this so they match that page's KPI cards, which
    already show 0 (not N/A) for an empty value via format.ts's *OrZero
    formatters, on the same "hasn't happened yet today" reasoning. Every
    other (DATASET.xlsx-driven) gauge leaves it False and still shows N/A."""
    if value is None:
        if not zero_if_missing:
            return {"kind": "gauge", "title": title, "value": None}
        value = 0.0
    axis_min, axis_max = _gauge_axis_range(value, red_below, green_at, reverse)
    return {
        "kind": "gauge",
        "title": title,
        "value": value,
        "target": target,
        "min": axis_min,
        "max": axis_max,
        "redBelow": red_below,
        "greenAt": green_at,
        "reverse": reverse,
        "suffix": suffix,
        "prefix": prefix,
    }


# Each gauge reads config/kpi_thresholds.get_thresholds(...) *inside* its body
# (not a module-load snapshot) so an admin's PUT /api/kpi-thresholds shows up on
# the next /api/charts/*_gauge request with no restart.
def atv_gauge(atv: float | None, target: float | None = None, *, zero_if_missing: bool = False) -> dict:
    band = get_thresholds("atv")
    return gauge_spec(atv, "ATV (Average Transaction Value)", target, band["red_below"], band["green_at_or_above"], prefix=f"{CURRENCY_SYMBOL} ", zero_if_missing=zero_if_missing)


def rpv_gauge(rpv: float | None, target: float | None = None, *, zero_if_missing: bool = False) -> dict:
    band = get_thresholds("rpv")
    return gauge_spec(rpv, "RPV (Revenue Per Visitor)", target, band["red_below"], band["green_at_or_above"], prefix=f"{CURRENCY_SYMBOL} ", zero_if_missing=zero_if_missing)


def conversion_gauge(conversion_pct: float | None, target: float = 40.0, *, zero_if_missing: bool = False) -> dict:
    band = get_thresholds("conversion")
    return gauge_spec(conversion_pct, "Conversion %", target, band["red_below"], band["green_at_or_above"], suffix="%", zero_if_missing=zero_if_missing)


def basket_size_gauge(basket_size: float | None, target: float | None = None, *, zero_if_missing: bool = False) -> dict:
    band = get_thresholds("basket_size")
    return gauge_spec(basket_size, "Basket Size", target, band["red_below"], band["green_at_or_above"], zero_if_missing=zero_if_missing)


def achievement_gauge(achievement_pct: float | None, *, zero_if_missing: bool = False) -> dict:
    band = get_thresholds("achievement")
    return gauge_spec(achievement_pct, "Target Achievement %", 100.0, band["red_below"], band["green_above"], suffix="%", zero_if_missing=zero_if_missing)


def remaining_pct_gauge(remaining_pct: float | None, *, zero_if_missing: bool = False) -> dict:
    # Remaining % = 100 - Achievement %, so its bands are the achievement band
    # mirrored around 100 rather than a separately-defined business threshold.
    band = get_thresholds("achievement")
    red_above = 100 - band["red_below"]
    green_at_or_below = 100 - band["green_above"]
    return gauge_spec(remaining_pct, "Remaining %", 0.0, red_above, green_at_or_below, suffix="%", reverse=True, zero_if_missing=zero_if_missing)


def conversion_funnel_chart(footfall_total: float | None, nob_total: float | None) -> dict:
    """Footfall -> Transactions (master prompt 13.6 minimum-support case).
    Units Sold and Net Sales are deliberately excluded: Units Sold is not
    guaranteed to be <= Transactions (multiple items per bill is normal) and
    Net Sales is a currency amount, not a count -- mixing either into this
    funnel produces a broken shape and a meaningless "percent of initial"
    (we saw >100% and >40,000% stages when this was tried)."""
    title = "Conversion Funnel"
    stages, values = [], []
    if footfall_total is not None:
        stages.append("Footfall")
        values.append(footfall_total)
    if nob_total is not None:
        stages.append("Transactions")
        values.append(nob_total)
    if len(stages) < 2:
        return _empty_figure(title, height=FUNNEL_HEIGHT)
    fig = go.Figure(go.Funnel(y=stages, x=values, textinfo="value+percent initial"))
    fig.update_layout(title=title)
    _size(fig, FUNNEL_HEIGHT)
    return _fig_to_dict(fig)


def conversion_funnel_by_timeslot_chart(footfall: pd.DataFrame) -> dict:
    """One Footfall -> Transactions funnel per TIME WISE FOOTFALL-NOB band, so a
    manager can see which store hours leak the most footfall before a bill.
    Same two-stage shape as conversion_funnel_chart (Units Sold / Net Sales
    stay out -- see that function). Slots with no footfall and no NOB are
    dropped rather than drawn as an empty funnel."""
    title = "Conversion Funnel by Time Slot"
    if footfall.empty or "time_slot" not in footfall.columns:
        return _empty_figure(title, height=FUNNEL_HEIGHT)
    grouped = footfall.groupby("time_slot").agg(footfall=("footfall", "sum"), nob=("nob", "sum")).reindex(TIME_SLOT_ORDER)
    fig = go.Figure()
    drawn = 0
    for slot in TIME_SLOT_ORDER:
        raw_f = grouped.loc[slot, "footfall"]
        raw_n = grouped.loc[slot, "nob"]
        f = 0.0 if pd.isna(raw_f) else float(raw_f)
        n = 0.0 if pd.isna(raw_n) else float(raw_n)
        if not f and not n:
            continue
        fig.add_trace(
            go.Funnel(name=slot, y=["Footfall", "Transactions"], x=[f, n], textinfo="value+percent initial")
        )
        drawn += 1
    if drawn == 0:
        return _empty_figure(title, height=FUNNEL_HEIGHT)
    fig.update_layout(title=title)
    _size(fig, FUNNEL_HEIGHT)
    return _fig_to_dict(fig)


def monthly_sales_bridge_chart(fact: pd.DataFrame) -> dict:
    title = "Monthly Sales Bridge (Store Contribution)"
    if fact.empty or "store_code" not in fact.columns:
        return _empty_figure(title, height=BRIDGE_HEIGHT)
    months = sorted(fact["year_month"].dropna().unique())
    if len(months) < 2:
        return _empty_figure(title, "Need at least two months of data for a bridge chart", height=BRIDGE_HEIGHT)
    last_two = months[-2:]
    prev_by_store = fact.loc[fact["year_month"] == last_two[0]].groupby("store_code")["net_amount"].sum()
    curr_by_store = fact.loc[fact["year_month"] == last_two[1]].groupby("store_code")["net_amount"].sum()
    stores = sorted(set(prev_by_store.index) | set(curr_by_store.index))
    deltas = [float(curr_by_store.get(s, 0) - prev_by_store.get(s, 0)) for s in stores]

    labels = [f"{last_two[0]} Total"] + stores + [f"{last_two[1]} Total"]
    measures = ["absolute"] + ["relative"] * len(stores) + ["total"]
    values = [float(prev_by_store.sum())] + deltas + [float(curr_by_store.sum())]

    fig = go.Figure(go.Waterfall(x=labels, measure=measures, y=values, connector={"line": {"color": "#94a3b8"}}))
    fig.update_layout(title=f"{title}: {last_two[0]} → {last_two[1]}", yaxis={"title": f"Net Sales ({CURRENCY_SYMBOL})"})
    _size(fig, BRIDGE_HEIGHT)
    return _fig_to_dict(fig)


def sales_overview_chart(fact: pd.DataFrame, target: pd.DataFrame, *, granularity: str = "month") -> dict:
    """Executive Overview's headline chart (Historical Analytics Overhaul §1):
    Net Sales (bar) + Remaining-to-target (bar) + Sales Target (dashed line) per
    period bucket, the period chosen by the frontend's <PeriodSelect>
    (day/week/month/quarter/year via period_engine). Replaces
    monthly_sales_chart's Gross bar, which §1 dropped. The route may then run
    apply_chart_type() over this for the <ChartTypeToggle>."""
    title = "Sales Overview"
    if fact.empty:
        return _empty_figure(title)
    net = period_engine.resample_frame(fact, granularity, net_sales=("net_amount", "sum"))
    if net.empty:
        return _empty_figure(title)
    if not target.empty and "date" in target.columns:
        tgt = period_engine.resample_frame(target, granularity, sales_target=("target", "sum"))
        merged = net.merge(tgt[["period_start", "sales_target"]], on="period_start", how="left")
    else:
        merged = net.assign(sales_target=pd.NA)
    merged = merged.sort_values("period_start")
    merged["remaining"] = merged["sales_target"] - merged["net_sales"]

    x = merged["Date"]
    fig = go.Figure()
    fig.add_bar(x=x, y=merged["net_sales"], name="Net Sales", marker_color="#2563eb")
    fig.add_bar(x=x, y=merged["remaining"], name="Remaining", marker_color="#f59e0b")
    if merged["sales_target"].notna().any():
        fig.add_trace(
            go.Scatter(x=x, y=merged["sales_target"], name="Sales Target", mode="lines+markers", line={"dash": "dash", "color": "#dc2626"})
        )
    fig.update_layout(title=title, barmode="group", yaxis={"title": f"Sales ({CURRENCY_SYMBOL})"}, hovermode="x unified")
    _size(fig, STANDARD_CHART_HEIGHT)
    return _fig_to_dict(fig)


def monthly_sales_chart(fact: pd.DataFrame, target: pd.DataFrame) -> dict:
    title = "Monthly Sales"
    if fact.empty:
        return _empty_figure(title)
    grouped = fact.groupby("year_month", dropna=True).agg(net=("net_amount", "sum"), gross=("gross_amount", "sum")).reset_index()
    if not target.empty:
        target_monthly = target.copy()
        target_monthly["year_month"] = pd.to_datetime(target_monthly["date"]).dt.to_period("M").astype("string")
        target_by_month = target_monthly.groupby("year_month")["target"].sum().reset_index()
        grouped = grouped.merge(target_by_month, on="year_month", how="left")
        grouped["achievement_pct"] = (grouped["net"] / grouped["target"] * 100).where(grouped["target"] != 0)
    fig = go.Figure()
    fig.add_bar(x=grouped["year_month"], y=grouped["gross"], name="Gross Sales", marker_color="#cbd5e1")
    fig.add_bar(x=grouped["year_month"], y=grouped["net"], name="Net Sales", marker_color="#2563eb")
    if "target" in grouped.columns:
        fig.add_trace(go.Scatter(x=grouped["year_month"], y=grouped["target"], name="Target", mode="lines+markers", line={"dash": "dash", "color": "#dc2626"}))
    fig.update_layout(title=title, barmode="group", yaxis={"title": f"Sales ({CURRENCY_SYMBOL})"}, hovermode="x unified")
    _size(fig, STANDARD_CHART_HEIGHT)
    return _fig_to_dict(fig)


def daily_sales_trend_chart(fact: pd.DataFrame) -> dict:
    title = "Daily Sales Trend (7-Day Rolling Average)"
    if fact.empty:
        return _empty_figure(title)
    # `.dt.normalize()`, not `.dt.date` -- see footfall_vs_nob_chart's comment.
    daily = fact.groupby(fact["date"].dt.normalize())["net_amount"].sum().reset_index().sort_values("date")
    daily["rolling_7d"] = daily["net_amount"].rolling(7, min_periods=1).mean()
    fig = go.Figure()
    fig.add_bar(x=daily["date"], y=daily["net_amount"], name="Daily Net Sales", marker_color="#93c5fd")
    fig.add_trace(go.Scatter(x=daily["date"], y=daily["rolling_7d"], name="7-Day Rolling Avg", mode="lines", line={"color": "#1e3a8a", "width": 2}))
    fig.update_layout(title=title, yaxis={"title": f"Net Sales ({CURRENCY_SYMBOL})"}, hovermode="x unified")
    _size(fig, STANDARD_CHART_HEIGHT)
    return _fig_to_dict(fig)


def avg_sales_by_day_of_week_chart(fact: pd.DataFrame, footfall: pd.DataFrame) -> dict:
    title = "Average Sales by Day of Week"
    if fact.empty:
        return _empty_figure(title)
    grouped = fact.groupby("day_name", dropna=True)["net_amount"].mean().reindex(DAY_ORDER)
    fig = go.Figure(go.Bar(x=DAY_ORDER, y=grouped.values, marker_color="#2563eb"))
    fig.update_layout(title=title, yaxis={"title": f"Avg Net Sales ({CURRENCY_SYMBOL})"}, xaxis={"categoryorder": "array", "categoryarray": DAY_ORDER})
    _size(fig, STANDARD_CHART_HEIGHT)
    return _fig_to_dict(fig)


def monthly_same_day_comparison_chart(fact: pd.DataFrame, day_limit: int = 20) -> dict:
    """Compares day-of-month 1..day_limit across the months present in the
    filtered data (Section 13.12). Warns rather than silently comparing a
    full month to a partial one when the latest month hasn't reached
    day_limit yet."""
    title = f"Monthly Same-Day Comparison (Day 1–{day_limit})"
    if fact.empty:
        return _empty_figure(title)
    months = sorted(fact["year_month"].dropna().unique())
    if not months:
        return _empty_figure(title)
    latest_month_max_day = fact.loc[fact["year_month"] == months[-1], "day_of_month"].max()
    warning = None
    if pd.notna(latest_month_max_day) and latest_month_max_day < day_limit:
        warning = f"{months[-1]} only has data through day {int(latest_month_max_day)} — treat as MTD, not a full-month comparison."

    scoped = fact.loc[fact["day_of_month"] <= day_limit]
    grouped = scoped.groupby(["year_month", "day_of_month"])["net_amount"].sum().reset_index()
    fig = go.Figure()
    for i, ym in enumerate(months):
        sub = grouped.loc[grouped["year_month"] == ym].set_index("day_of_month").reindex(range(1, day_limit + 1))
        color = CATEGORICAL_PALETTE[i % len(CATEGORICAL_PALETTE)]
        fig.add_trace(go.Scatter(x=list(range(1, day_limit + 1)), y=sub["net_amount"].values, name=ym, mode="lines+markers", line={"color": color}, marker={"color": color}))
    layout_extra = {}
    if warning:
        layout_extra["annotations"] = [{"text": warning, "xref": "paper", "yref": "paper", "x": 0.5, "y": 1.12, "showarrow": False, "font": {"color": "#b45309", "size": 12}}]
    fig.update_layout(title=title, xaxis={"title": "Day of Month"}, yaxis={"title": f"Net Sales ({CURRENCY_SYMBOL})"}, **layout_extra)
    _size(fig, STANDARD_CHART_HEIGHT)
    return _fig_to_dict(fig)


_DRILLDOWN_META_COLS = ["quantity", "transactions", "cogs_gst", "discount", "gross_profit", "margin_pct", "share_pct"]


def _category_hierarchy_nodes(fact: pd.DataFrame, levels: list[str]) -> pd.DataFrame:
    """One row per sunburst node across every level of ``levels``, carrying the
    full metric set (not just Net Sales) so the drill-down's hover -- and its
    companion table (tables.category_net_sales_table) -- can show quantity,
    transactions, COGS+GST, discount, gross profit, margin % and share %.
    ``cogs_with_gst`` / ``discount_amount`` are optional source fields (see
    column_aliases.py): NaN, not a fabricated 0, when absent."""
    has_cogs = "cogs_with_gst" in fact.columns
    has_discount = "discount_amount" in fact.columns
    grand_total = fact["net_amount"].sum()

    agg_kwargs = {
        "net_sales": ("net_amount", "sum"),
        "quantity": ("bill_quantity", "sum"),
        "transactions": ("bill_no", "nunique"),
    }
    if has_cogs:
        agg_kwargs["cogs_gst"] = ("cogs_with_gst", "sum")
    if has_discount:
        agg_kwargs["discount"] = ("discount_amount", "sum")

    # Aggregate at the deepest level first and keep only positive leaves, THEN
    # roll every parent level UP from those surviving leaves -- so a parent is
    # always the sum of kept children and can never be dropped (net-negative
    # from returns) while a child survives, which would orphan the child and
    # make Plotly refuse to draw the whole sunburst. `transactions` is
    # re-counted per level from the fact rows of the kept leaves (nunique
    # doesn't roll up additively).
    leaves = fact.groupby(levels, dropna=True).agg(**agg_kwargs).reset_index()
    leaves = leaves.loc[leaves["net_sales"] > 0]
    if leaves.empty:
        return leaves.assign(id=[], parent=[], label=[])
    kept = fact.merge(leaves[levels], on=levels, how="inner")

    frames = []
    for depth in range(1, len(levels) + 1):
        group_cols = levels[:depth]
        g = kept.groupby(group_cols, dropna=True).agg(**agg_kwargs).reset_index()
        g["id"] = g[group_cols].astype(str).agg(" / ".join, axis=1)
        g["parent"] = "" if depth == 1 else g[group_cols[:-1]].astype(str).agg(" / ".join, axis=1)
        g["label"] = g[group_cols[-1]].astype(str)
        frames.append(g)
    nodes = pd.concat(frames, ignore_index=True)
    if not has_cogs:
        nodes["cogs_gst"] = pd.NA
    if not has_discount:
        nodes["discount"] = pd.NA
    nodes["gross_profit"] = (nodes["net_sales"] - nodes["cogs_gst"]) if has_cogs else pd.NA
    nodes["margin_pct"] = (nodes["gross_profit"] / nodes["net_sales"] * 100).where(nodes["net_sales"] != 0) if has_cogs else pd.NA
    nodes["share_pct"] = (nodes["net_sales"] / grand_total * 100) if grand_total else 0.0
    return nodes


def category_drilldown_chart(fact: pd.DataFrame) -> dict:
    """Sunburst using the levels that exist in the workbook: Division ->
    Section -> Department -- a dynamic, drillable pie. Each node's hover
    carries the full metric set; deeper levels (Item Code, Brand, Style, ...)
    are too granular for one chart and are explored via the Top <category>
    table instead. Companion table: tables.category_net_sales_table."""
    title = "Category Drill-Down (Division → Section → Department)"
    if fact.empty:
        return _empty_figure(title, height=SUNBURST_HEIGHT)
    levels = [c for c in ["division", "section", "department"] if c in fact.columns]
    if not levels:
        return _empty_figure(title, height=SUNBURST_HEIGHT)
    nodes = _category_hierarchy_nodes(fact, levels)
    if nodes.empty:
        return _empty_figure(title, height=SUNBURST_HEIGHT)
    customdata = nodes[_DRILLDOWN_META_COLS].apply(pd.to_numeric, errors="coerce").to_numpy()
    fig = go.Figure(
        go.Sunburst(
            ids=nodes["id"],
            labels=nodes["label"],
            parents=nodes["parent"],
            values=nodes["net_sales"],
            branchvalues="total",
            customdata=customdata,
            hovertemplate=(
                "<b>%{label}</b><br>"
                f"Net Sales: {CURRENCY_SYMBOL}%{{value:,.0f}}<br>"
                "Quantity: %{customdata[0]:,.0f}<br>"
                "Transactions: %{customdata[1]:,.0f}<br>"
                f"COGS + GST: {CURRENCY_SYMBOL}%{{customdata[2]:,.0f}}<br>"
                f"Discount: {CURRENCY_SYMBOL}%{{customdata[3]:,.0f}}<br>"
                f"Gross Profit: {CURRENCY_SYMBOL}%{{customdata[4]:,.0f}}<br>"
                "Margin: %{customdata[5]:.1f}%<br>"
                "Share of total: %{customdata[6]:.1f}%<extra></extra>"
            ),
        )
    )
    fig.update_layout(title=title)
    _size(fig, SUNBURST_HEIGHT, margin={"l": 10, "r": 10, "t": 60, "b": 10})
    return _fig_to_dict(fig)


def target_achievement_by_month_chart(fact: pd.DataFrame, target: pd.DataFrame) -> dict:
    title = "Target Achievement by Month"
    fig_dict = monthly_sales_chart(fact, target)
    fig_dict["layout"]["title"]["text"] = title
    return fig_dict


def yearly_same_month_comparison_chart(fact: pd.DataFrame) -> dict:
    title = "Yearly Same-Month Comparison"
    if fact.empty or "year" not in fact.columns:
        return _empty_figure(title)
    grouped = fact.groupby(["month_name", "year"], dropna=True)["net_amount"].sum().reset_index()
    fig = go.Figure()
    for i, yr in enumerate(sorted(grouped["year"].dropna().unique())):
        sub = grouped.loc[grouped["year"] == yr].set_index("month_name").reindex(MONTH_ORDER)
        color = CATEGORICAL_PALETTE[i % len(CATEGORICAL_PALETTE)]
        fig.add_trace(go.Bar(x=MONTH_ORDER, y=sub["net_amount"].values, name=str(int(yr)), marker_color=color))
    fig.update_layout(title=title, barmode="group", yaxis={"title": f"Net Sales ({CURRENCY_SYMBOL})"}, xaxis={"categoryorder": "array", "categoryarray": MONTH_ORDER})
    _size(fig, STANDARD_CHART_HEIGHT)
    return _fig_to_dict(fig)


def same_period_year_over_year_chart(comparison_table: pd.DataFrame) -> dict:
    """The "yearly / same month / same day" comparison -- day-by-day Net
    Sales for the selected period plotted against the same calendar day one
    year earlier. Distinct from the two comparisons above: monthly_same_day_
    comparison_chart lines up day-of-month across whichever month cohorts
    are in the filtered data (not necessarily different years), and
    yearly_same_month_comparison_chart compares whole-month totals by
    month name across years -- neither tracks the exact matched calendar
    day, day by day, across a year. Visualizes
    tables.same_period_year_over_year_table's own output directly (not a
    second independent computation), so this chart and its table companion
    can never disagree. Missing values (e.g. the previous-year side, while
    the dataset is still a single calendar year with no prior-year history)
    are gaps in the line, not a fabricated 0."""
    title = "Year-over-Year: Same Period Comparison"
    if comparison_table.empty:
        return _empty_figure(title)
    x_labels = pd.to_datetime(comparison_table["date"]).dt.strftime("%d %b %Y")
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(x=x_labels, y=comparison_table["current_year_net_sales"], name="Current Period", mode="lines+markers", line={"color": "#2563eb"})
    )
    fig.add_trace(
        go.Scatter(
            x=x_labels,
            y=comparison_table["previous_year_net_sales"],
            name="Same Period Last Year",
            mode="lines+markers",
            line={"color": "#94a3b8", "dash": "dash"},
        )
    )
    fig.update_layout(title=title, yaxis={"title": f"Net Sales ({CURRENCY_SYMBOL})"}, hovermode="x unified")
    _size(fig, STANDARD_CHART_HEIGHT)
    return _fig_to_dict(fig)


# ---------------------------------------------------------------------------
# Section 2 (Sales Performance) -- Historical Analytics Overhaul, Phase 3
#
# Three mode-toggled charts replacing six single-purpose ones. The originals
# (net_vs_gross_sales_chart / week_segment_chart / monthly_sales_bridge_chart /
# target_achievement_by_month_chart / daily_sales_trend_chart /
# avg_sales_by_day_of_week_chart / monthly_same_day_comparison_chart /
# yearly_same_month_comparison_chart) all stay -- streamlit_app.py + pytest
# still call them, and period_comparison_chart delegates to two of them.
# ---------------------------------------------------------------------------

_AVG_SALES_TITLE = {
    "day": "Average Sales by Day of Week",
    "week": "Average Sales by ISO Week",
    "month": "Average Sales by Month",
    "quarter": "Average Sales by Quarter",
    "year": "Average Sales by Year",
}


def sales_trend_chart(
    fact: pd.DataFrame,
    footfall: pd.DataFrame,
    *,
    dimension: str = "period",
    granularity: str = "day",
) -> dict:
    """2b -- one chart, two modes. ``period``: Net Sales per linear
    ``period_engine`` bucket (plus a 7-day rolling average when the bucket is a
    day). ``timeslot``: Footfall + NOB summed across the workbook's four
    TIME WISE FOOTFALL-NOB bands. The route may run apply_chart_type() over the
    result for the <ChartTypeToggle> (column/bar/line/area)."""
    if dimension == "timeslot":
        title = "Footfall & NOB by Time Slot"
        if footfall.empty or "time_slot" not in footfall.columns:
            return _empty_figure(title)
        grouped = footfall.groupby("time_slot").agg(footfall=("footfall", "sum"), nob=("nob", "sum")).reindex(TIME_SLOT_ORDER)
        fig = go.Figure()
        fig.add_bar(x=TIME_SLOT_ORDER, y=grouped["footfall"], name="Footfall", marker_color="#94a3b8")
        fig.add_bar(x=TIME_SLOT_ORDER, y=grouped["nob"], name="NOB", marker_color="#2563eb")
        fig.update_layout(title=title, barmode="group", yaxis={"title": "Count"})
        _size(fig, STANDARD_CHART_HEIGHT)
        return _fig_to_dict(fig)

    title = "Sales Trend"
    if fact.empty:
        return _empty_figure(title)
    resampled = period_engine.resample_frame(fact, granularity, net_sales=("net_amount", "sum"))
    if resampled.empty:
        return _empty_figure(title)
    fig = go.Figure()
    fig.add_bar(x=resampled["Date"], y=resampled["net_sales"], name="Net Sales", marker_color="#2563eb")
    if granularity == "day":
        rolling = resampled["net_sales"].rolling(7, min_periods=1).mean()
        fig.add_trace(
            go.Scatter(x=resampled["Date"], y=rolling, name="7-Day Rolling Avg", mode="lines", line={"color": "#1e3a8a", "width": 2})
        )
    fig.update_layout(title=title, yaxis={"title": f"Net Sales ({CURRENCY_SYMBOL})"}, hovermode="x unified")
    _size(fig, STANDARD_CHART_HEIGHT)
    return _fig_to_dict(fig)


def avg_sales_chart(fact: pd.DataFrame, *, granularity: str = "day") -> dict:
    """2c -- average (not total) Net Sales per *cyclic* bucket: every Monday in
    the range collapses into one bar, every August into one bar, etc., via
    ``period_engine.seasonal_key``."""
    title = _AVG_SALES_TITLE.get(granularity, "Average Sales")
    if fact.empty or "date" not in fact.columns:
        return _empty_figure(title)
    keys, order = period_engine.seasonal_key(fact["date"], granularity)
    grouped = fact.assign(_seasonal_key=keys.values).groupby("_seasonal_key")["net_amount"].mean()
    grouped = grouped.reindex(order)
    labels = [str(o) for o in order]
    fig = go.Figure(go.Bar(x=labels, y=grouped.values, name="Avg Net Sales", marker_color="#2563eb"))
    fig.update_layout(
        title=title,
        yaxis={"title": f"Avg Net Sales ({CURRENCY_SYMBOL})"},
        xaxis={"categoryorder": "array", "categoryarray": labels},
    )
    _size(fig, STANDARD_CHART_HEIGHT)
    return _fig_to_dict(fig)


def _weekly_same_day_comparison_chart(fact: pd.DataFrame) -> dict:
    """2e ``weekly_same_day`` mode -- Mon..Sun Net Sales, one line per week
    cohort in the filtered range (the weekly analogue of
    monthly_same_day_comparison_chart's day-of-month lines)."""
    title = "Weekly Same-Day Comparison (Mon–Sun)"
    if fact.empty or "day_name" not in fact.columns or "date" not in fact.columns:
        return _empty_figure(title)
    df = fact.copy()
    anchor = period_engine.period_start(df["date"], "week")
    df["_anchor"] = anchor.values
    df["_week"] = period_engine.period_label(anchor, "week").values
    grouped = df.groupby(["_anchor", "_week", "day_name"], dropna=True)["net_amount"].sum().reset_index()
    cohorts = grouped[["_anchor", "_week"]].drop_duplicates().sort_values("_anchor")
    fig = go.Figure()
    for i, (_, cohort) in enumerate(cohorts.iterrows()):
        sub = grouped.loc[grouped["_week"] == cohort["_week"]].set_index("day_name").reindex(DAY_ORDER)
        color = CATEGORICAL_PALETTE[i % len(CATEGORICAL_PALETTE)]
        fig.add_trace(
            go.Scatter(x=DAY_ORDER, y=sub["net_amount"].values, name=str(cohort["_week"]), mode="lines+markers", line={"color": color}, marker={"color": color})
        )
    fig.update_layout(
        title=title,
        xaxis={"title": "Day of Week", "categoryorder": "array", "categoryarray": DAY_ORDER},
        yaxis={"title": f"Net Sales ({CURRENCY_SYMBOL})"},
    )
    _size(fig, STANDARD_CHART_HEIGHT)
    return _fig_to_dict(fig)


def period_comparison_chart(fact: pd.DataFrame, *, dimension: str = "monthly_same_day", day_limit: int = 20) -> dict:
    """2e -- dispatcher over the period-comparison modes. ``monthly_same_day``
    and ``yearly_month`` delegate to the retained standalone builders;
    ``weekly_same_day`` is new. The fourth mode the frontend offers,
    ``same_period_yoy``, is handled in the route (it needs the date-free fact
    slice + tables.same_period_year_over_year_table), not here."""
    if dimension == "yearly_month":
        return yearly_same_month_comparison_chart(fact)
    if dimension == "weekly_same_day":
        return _weekly_same_day_comparison_chart(fact)
    # monthly_same_day (default)
    return monthly_same_day_comparison_chart(fact, day_limit)


def top_products_chart(top_products: pd.DataFrame, measure_label: str = "Net Sales") -> dict:
    title = f"Top Products by {measure_label}"
    if top_products.empty:
        return _empty_figure(title)
    fig = go.Figure(go.Bar(x=top_products["net_sales"], y=top_products["product_style"].fillna(top_products["item_code"]), orientation="h", marker_color="#2563eb"))
    fig.update_layout(title=title, yaxis={"autorange": "reversed"}, xaxis={"title": f"Net Sales ({CURRENCY_SYMBOL})"})
    _size(fig, max(STANDARD_CHART_HEIGHT, 40 * len(top_products) + 120))
    return _fig_to_dict(fig)


def top_brands_chart(top_brands: pd.DataFrame) -> dict:
    title = "Top Brands by Net Sales"
    if top_brands.empty:
        return _empty_figure(title)
    fig = go.Figure(go.Bar(x=top_brands["net_sales"], y=top_brands["product_brand"], orientation="h", marker_color="#0ea5e9"))
    fig.update_layout(title=title, yaxis={"autorange": "reversed"}, xaxis={"title": f"Net Sales ({CURRENCY_SYMBOL})"})
    _size(fig, max(STANDARD_CHART_HEIGHT, 40 * len(top_brands) + 120))
    return _fig_to_dict(fig)


_PAIRING_VALUE_LABELS = {"net_sales": "Net Sales", "quantity": "Quantity", "gross_profit": "Gross Profit", "transactions": "Transactions"}
_PAIRING_CURRENCY_COLS = {"net_sales", "gross_profit"}


def _pairing_value_column(pairing_table: pd.DataFrame) -> str:
    for col in pairing_table.columns:
        if col.startswith("strong_") and col not in ("strong_item_code", "strong_product"):
            return col[len("strong_"):]
    return "net_sales"


def performer_pairing_chart(pairing_table: pd.DataFrame, top_n: int = 10) -> dict:
    value_col = _pairing_value_column(pairing_table)
    measure_label = _PAIRING_VALUE_LABELS.get(value_col, value_col.replace("_", " ").title())
    title = f"Performer Pairing: Strong vs Weak by {measure_label}"
    if pairing_table.empty:
        return _empty_figure(title)
    top = pairing_table.head(top_n)
    labels = [
        f"{s} vs {w}"
        for s, w in zip(
            top["strong_product"].fillna(top["strong_item_code"]),
            top["weak_product"].fillna(top["weak_item_code"]),
        )
    ]
    axis_title = f"{measure_label} ({CURRENCY_SYMBOL})" if value_col in _PAIRING_CURRENCY_COLS else measure_label
    fig = go.Figure()
    fig.add_trace(go.Bar(x=top[f"strong_{value_col}"], y=labels, orientation="h", name="Strong Performer", marker_color=CATEGORICAL_PALETTE[0]))
    fig.add_trace(go.Bar(x=top[f"weak_{value_col}"], y=labels, orientation="h", name="Weak Performer", marker_color=CATEGORICAL_PALETTE[1]))
    fig.update_layout(title=title, barmode="group", yaxis={"autorange": "reversed"}, xaxis={"title": axis_title})
    _size(fig, max(STANDARD_CHART_HEIGHT, 50 * len(top) + 120))
    return _fig_to_dict(fig)


_TOP_CATEGORY_MEASURE = {
    "net_amount": ("net_sales", "Net Sales"),
    "quantity": ("quantity", "Quantity"),
    "transactions": ("transactions", "Transactions"),
}


def top_category_chart(table: pd.DataFrame, category: str = "division", measure: str = "net_amount") -> dict:
    """Column chart for tables.top_category_table -- the merged replacement for
    top_products_chart + top_brands_chart. Bars are the ranking ``measure``
    (Net Sales / Quantity / Transactions); ``category`` picks the label
    dimension (Division / Section / Department). Vertical (x = category labels,
    y = value) so charts.apply_chart_type's column/bar/line/pie/3d swaps stay
    correct -- it assumes that shape."""
    value_col, measure_label = _TOP_CATEGORY_MEASURE.get(measure, ("net_sales", "Net Sales"))
    cat_label = str(category).replace("_", " ").title()
    title = f"Top {cat_label} by {measure_label}"
    if table.empty or value_col not in table.columns or "category" not in table.columns:
        return _empty_figure(title)
    axis_title = f"{measure_label} ({CURRENCY_SYMBOL})" if measure == "net_amount" else measure_label
    fig = go.Figure(go.Bar(x=table["category"].astype(str), y=table[value_col], name=measure_label, marker_color="#2563eb"))
    fig.update_layout(title=title, xaxis={"title": cat_label, "tickangle": -35}, yaxis={"title": axis_title})
    _size(fig, STANDARD_CHART_HEIGHT)
    return _fig_to_dict(fig)


def department_performer_pairing_chart(pairing_table: pd.DataFrame, top_n: int = 10) -> dict:
    """Grouped column chart for tables.department_performer_pairing_table --
    each department's strong vs weak product Net Sales side by side. Plain
    go.Bar so charts.apply_chart_type can switch the mark."""
    title = "Performer Pairing: Strong vs Weak by Department"
    if pairing_table.empty or "department" not in pairing_table.columns:
        return _empty_figure(title)
    top = pairing_table.head(top_n)
    x = top["department"].astype(str)
    fig = go.Figure()
    fig.add_bar(x=x, y=top["strong_net_sales"], name="Strong Performer", marker_color=CATEGORICAL_PALETTE[0])
    fig.add_bar(x=x, y=top["weak_net_sales"], name="Weak Performer", marker_color=CATEGORICAL_PALETTE[1])
    fig.update_layout(
        title=title, barmode="group", yaxis={"title": f"Net Sales ({CURRENCY_SYMBOL})"}, xaxis={"tickangle": -35}
    )
    _size(fig, STANDARD_CHART_HEIGHT)
    return _fig_to_dict(fig)


def discount_impact_chart(discount_table: pd.DataFrame) -> dict:
    """Grouped bar: Net Sales per period bucket, one series per segment
    (Discounted / Non-discounted). ``discount_table`` is
    ``tables.discount_impact_table``'s output."""
    title = "Discounted vs Non-Discounted Net Sales"
    if discount_table.empty or "segment" not in discount_table.columns:
        return _empty_figure(title)
    order = list(dict.fromkeys(discount_table["Date"]))
    fig = go.Figure()
    for i, (segment, sub) in enumerate(discount_table.groupby("segment", sort=False)):
        sub = sub.set_index("Date").reindex(order)
        fig.add_trace(go.Bar(
            x=order, y=sub["net_sales"], name=str(segment),
            marker_color=CATEGORICAL_PALETTE[i % len(CATEGORICAL_PALETTE)],
        ))
    fig.update_layout(title=title, barmode="group", yaxis={"title": f"Net Sales ({CURRENCY_SYMBOL})"})
    _size(fig, STANDARD_CHART_HEIGHT)
    return _fig_to_dict(fig)


def promotion_breakdown_chart(promo_table: pd.DataFrame) -> dict:
    """Net Sales by raw promo-type code. ``promo_table`` is
    ``tables.promotion_breakdown_table``'s output."""
    title = "Net Sales by Promo Type"
    if promo_table.empty or "promo_type" not in promo_table.columns:
        return _empty_figure(title)
    fig = go.Figure(go.Bar(
        x=promo_table["promo_type"], y=promo_table["net_sales"],
        marker_color=CATEGORICAL_PALETTE[0],
    ))
    fig.update_layout(title=title, yaxis={"title": f"Net Sales ({CURRENCY_SYMBOL})"}, xaxis={"title": "Promo Type"})
    _size(fig, STANDARD_CHART_HEIGHT)
    return _fig_to_dict(fig)
