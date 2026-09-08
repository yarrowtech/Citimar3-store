"""Forecast-specific Plotly figure builders. Reuses src/charts.py's shared
sizing/typography/template helpers (_size, _fig_to_dict, _empty_figure,
CATEGORICAL_PALETTE, STANDARD_CHART_HEIGHT, STANDARD_MARGIN, CHART_TEMPLATE)
rather than redefining them, so forecast charts stay visually consistent with
the base KPI dashboard's charts -- same pinned template, same font/size/margin
defaults, same categorical palette. Every function here returns a plain
JSON-safe dict, same contract as src/charts.py.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from config.forecast_settings import OTHER_BUCKET_LABEL
from config.settings import CURRENCY_SYMBOL
from src.charts import CATEGORICAL_PALETTE, STANDARD_CHART_HEIGHT, _empty_figure, _fig_to_dict, _size
from src.forecasting.backtesting import FoldScore
from src.forecasting.orchestrator import ForecastBundle

FORECAST_LINE_COLOR = "#2563eb"  # matches src/charts.py's "Net Sales" brand blue
FORECAST_DASH_COLOR = "#eb6834"
FORECAST_BAND_COLOR = "rgba(37, 99, 235, 0.15)"


def forecast_line_chart(history: pd.DataFrame, forecast: pd.DataFrame, title: str, y_label: str) -> dict:
    has_history = history is not None and not history.empty
    has_forecast = forecast is not None and not forecast.empty
    if not has_history and not has_forecast:
        return _empty_figure(title)

    fig = go.Figure()
    if has_history:
        fig.add_trace(go.Scatter(x=history["date"], y=history["y"], name="Actual", mode="lines", line={"color": FORECAST_LINE_COLOR, "width": 2}))

    if has_forecast:
        fig.add_trace(go.Scatter(x=forecast["date"], y=forecast["upper"], name="Upper Bound", mode="lines", line={"width": 0}, showlegend=False, hoverinfo="skip"))
        fig.add_trace(
            go.Scatter(
                x=forecast["date"], y=forecast["lower"], name="Confidence Interval", mode="lines",
                line={"width": 0}, fill="tonexty", fillcolor=FORECAST_BAND_COLOR, hoverinfo="skip",
            )
        )
        fig.add_trace(go.Scatter(x=forecast["date"], y=forecast["point"], name="Forecast", mode="lines", line={"color": FORECAST_DASH_COLOR, "width": 2, "dash": "dash"}))

        if has_history:
            forecast_start = pd.Timestamp(forecast["date"].min()).strftime("%Y-%m-%d")
            fig.add_vline(x=forecast_start, line_width=1, line_dash="dot", line_color="#94a3b8")

    fig.update_layout(title=title, yaxis={"title": y_label}, hovermode="x unified")
    _size(fig, STANDARD_CHART_HEIGHT)
    return _fig_to_dict(fig)


def leaderboard_chart(leaderboard: pd.DataFrame, primary_metric: str = "mape") -> dict:
    """Horizontal bar of the primary metric per model, best (lowest) at top
    and highlighted; a model that failed every backtest fold is shown as a
    zero-length bar labeled explicitly -- makes the 'proper model selection'
    requirement's transparency ask literal, not just a raw table."""
    title = f"Model Leaderboard ({primary_metric.upper()})"
    col = f"mean_{primary_metric}"
    if leaderboard is None or leaderboard.empty or col not in leaderboard.columns:
        return _empty_figure(title)

    df = leaderboard.copy()
    display_value = df[col].fillna(0.0)
    labels = [("failed on every fold" if pd.isna(v) else f"{v:.2f}") for v in df[col]]
    best_idx = df[col].idxmin() if df[col].notna().any() else None
    colors = [
        "#1baf7a" if i == best_idx else ("#e34948" if pd.isna(df.loc[i, col]) else "#2a78d6")
        for i in df.index
    ]

    fig = go.Figure(
        go.Bar(x=display_value, y=df["model"], orientation="h", marker_color=colors, text=labels, textposition="outside")
    )
    fig.update_layout(title=title, xaxis={"title": f"Mean {primary_metric.upper()}"}, yaxis={"autorange": "reversed"})
    _size(fig, STANDARD_CHART_HEIGHT)
    return _fig_to_dict(fig)


def backtest_actual_vs_predicted_chart(fold_scores: list[FoldScore]) -> dict:
    """Concatenates every successful fold's test window chronologically and
    plots actual (solid) vs the model's held-out backtest prediction
    (dashed). This is backtest/held-out data, not a preview of real future
    actuals -- DATASET.xlsx has none beyond its own last date yet -- so the
    caller (streamlit_forecast_app.py) captions this explicitly."""
    title = "Backtest: Actual vs Predicted"
    valid_folds = [fs for fs in fold_scores if fs.error is None and fs.actual and fs.predicted]
    if not valid_folds:
        return _empty_figure(title, "No successful backtest folds to display")

    dates: list[pd.Timestamp] = []
    actual: list[float] = []
    predicted: list[float] = []
    for fs in sorted(valid_folds, key=lambda f: f.test_start):
        fold_dates = pd.date_range(fs.test_start, fs.test_end, freq="D")
        n = min(len(fold_dates), len(fs.actual), len(fs.predicted))
        dates.extend(fold_dates[:n])
        actual.extend(fs.actual[:n])
        predicted.extend(fs.predicted[:n])

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=dates, y=actual, name="Actual", mode="lines+markers", line={"color": FORECAST_LINE_COLOR, "width": 2}))
    fig.add_trace(go.Scatter(x=dates, y=predicted, name="Backtest Predicted", mode="lines+markers", line={"color": FORECAST_DASH_COLOR, "width": 2, "dash": "dash"}))
    fig.update_layout(title=title, yaxis={"title": "Value"}, hovermode="x unified")
    _size(fig, STANDARD_CHART_HEIGHT)
    return _fig_to_dict(fig)


def topn_forecast_bar_chart(bundles: dict[str, ForecastBundle], title: str) -> dict:
    """One bar per top-N entity + 'Other', summed forecast net sales over the
    selected horizon -- descending so the biggest expected contributor reads
    first. 'Other' always gets a fixed neutral grey (never a categorical
    slot) since it isn't a real single entity."""
    if not bundles:
        return _empty_figure(title)

    labels, values, colors = [], [], []
    palette_idx = 0
    for name, bundle in bundles.items():
        labels.append(name)
        total = float(bundle.forecast["point"].sum()) if not bundle.insufficient_history and not bundle.forecast.empty else 0.0
        values.append(total)
        if name == OTHER_BUCKET_LABEL:
            colors.append("#898781")
        else:
            colors.append(CATEGORICAL_PALETTE[palette_idx % len(CATEGORICAL_PALETTE)])
            palette_idx += 1

    order = sorted(range(len(labels)), key=lambda i: values[i], reverse=True)
    labels = [labels[i] for i in order]
    values = [values[i] for i in order]
    colors = [colors[i] for i in order]

    fig = go.Figure(go.Bar(x=labels, y=values, marker_color=colors))
    fig.update_layout(title=title, yaxis={"title": f"Forecasted Net Sales ({CURRENCY_SYMBOL})"}, xaxis={"tickangle": -35})
    _size(fig, STANDARD_CHART_HEIGHT)
    return _fig_to_dict(fig)


_PROMO_TYPE_COLORS = {
    "No Promo": "#94a3b8",
    "Percentage Discount": "#2a78d6",
    "Flat Discount": "#eb6834",
    "Other Promo": "#1baf7a",
}


def promo_uplift_chart(promo_uplift_table: pd.DataFrame) -> dict:
    """Bar per promo_type (incl. the 'No Promo' baseline), annotated with
    uplift_pct vs that baseline. Colors are keyed by promo_type NAME (fixed
    map above), not by row position -- so a color always means the same
    promo type regardless of how the table happens to be sorted."""
    title = "Promotion Effectiveness: Avg Net Sales per Bill by Promo Type"
    if promo_uplift_table is None or promo_uplift_table.empty:
        return _empty_figure(title)

    df = promo_uplift_table
    colors = [_PROMO_TYPE_COLORS.get(t, CATEGORICAL_PALETTE[4]) for t in df["promo_type"]]
    labels = [f"{v:+.1f}% uplift" if pd.notna(v) else "" for v in df["uplift_pct"]]

    fig = go.Figure(go.Bar(x=df["promo_type"], y=df["avg_net_per_bill"], marker_color=colors, text=labels, textposition="outside"))
    fig.update_layout(title=title, yaxis={"title": f"Avg Net Sales per Bill ({CURRENCY_SYMBOL})"})
    _size(fig, STANDARD_CHART_HEIGHT)
    return _fig_to_dict(fig)


def growth_trajectory_chart(current_avg_daily: float | None, required_avg_daily: float | None, target_total: float | None) -> dict:
    title = "Current Pace vs Required Pace"
    if current_avg_daily is None and required_avg_daily is None:
        return _empty_figure(title)

    required = required_avg_daily or 0.0
    current = current_avg_daily or 0.0
    required_color = "#e34948" if required > current else "#1baf7a"
    fig = go.Figure(
        go.Bar(x=["Current Avg Daily", "Required Avg Daily"], y=[current, required], marker_color=["#94a3b8", required_color])
    )
    fig.update_layout(title=title, yaxis={"title": f"Net Sales ({CURRENCY_SYMBOL})"})
    _size(fig, STANDARD_CHART_HEIGHT)
    return _fig_to_dict(fig)
