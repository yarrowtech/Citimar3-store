"""Per-store Daily Operations report -- builds a Phase C ReportPayload
(src/reports/models.py) straight from the live MongoDB daily logs for one
store, covering *all* recorded dates.

This is a standalone export path, separate from Historical Analytics'
frontend-assembled ReportBuilder flow: the block list is built here on the
backend and handed straight to the same renderers (src/reports/dispatch.py).
Two shapes:

  * xlsx (``include_visuals=False``) -- the two data tables only, no charts:
    the xlsx renderer emits a Summary sheet + one sheet per TableBlock.
  * pdf  (``include_visuals=True``)  -- an overall-summary KPI grid, the three
    gauges (Conversion % / Achievement % / Remaining %), the Today's Sales
    Performance chart, a Today's Context line (weather / holiday / election),
    then the same two tables.

Every figure comes from src/daily_dashboard_store.compute_live_kpis /
compute_live_timeslot_breakdown, so a manager's KPI overrides
(targets.overrides) flow through unchanged. Nothing is re-derived from
DATASET.xlsx.
"""
from __future__ import annotations

from datetime import date, datetime

from pymongo.database import Database

from config.settings import CURRENCY_SYMBOL, STORE_CODE_TO_NAME, TIME_SLOT_ORDER
from db.models import BILLS, FOOTFALL, NOB, TARGETS
from src import charts, daily_context, daily_dashboard_store
from src.data_loader import MasterDataset
from src.filter_engine import FilterState, apply_filters, filter_store_level_table
from src.kpi_engine import safe_divide
from src.reports.models import (
    ChartBlock,
    GaugeBlock,
    KpiGridBlock,
    KpiItem,
    ReportMeta,
    ReportPayload,
    TableBlock,
    TextBlock,
    TitleBlock,
)

_TIMESLOT_COLUMNS = [
    "Date", "Time Slot", "Net Sales", "Remaining", "Bill Quantity", "Footfall",
    "Transactions (NOB)", "ATV", "RPV", "Basket Size", "Conversion %",
    "Achievement %", "Remaining %",
]
_DATEWISE_COLUMNS = [
    "Date", "Sales Target", "Net Sales", "Remaining", "Bill Quantity", "Footfall",
    "Transactions (NOB)", "ATV", "RPV", "Basket Size", "Conversion %",
    "Achievement %", "Remaining %", "Remarks",
]


def _round(value: float | None, digits: int = 2) -> float | None:
    return None if value is None else round(float(value), digits)


def _pct(numerator: float | None, denominator: float | None) -> float | None:
    ratio = safe_divide(numerator, denominator)
    return None if ratio is None else ratio * 100


def report_dates(db: Database, store: str) -> list[str]:
    """Every ISO date this store has any bill / footfall / NOB / target row
    for, sorted. Collected from find() rather than distinct() so the local
    xlsx fallback (db/xlsx_fallback.py) keeps working."""
    seen: set[str] = set()
    for collection in (BILLS, FOOTFALL, NOB, TARGETS):
        for doc in db[collection].find({"store_code": store}):
            if doc.get("entry_date"):
                seen.add(doc["entry_date"])
    return sorted(seen)


def build_timeslot_rows(db: Database, store: str, dates: list[str]) -> list[dict]:
    rows: list[dict] = []
    for iso in dates:
        d = date.fromisoformat(iso)
        breakdown = daily_dashboard_store.compute_live_timeslot_breakdown(db, store, d)
        target = daily_dashboard_store.read_store_target(db, store, d)
        for slot in TIME_SLOT_ORDER:
            cell = breakdown[slot]
            net_sales = cell["net_sales"]
            bill_quantity = cell["bill_quantity"]
            footfall = cell["footfall"]
            nob = cell["nob"]
            if not any((net_sales, bill_quantity, footfall, nob)):
                continue
            achievement_pct = _pct(net_sales, target)
            rows.append({
                "Date": iso,
                "Time Slot": slot,
                "Net Sales": _round(net_sales),
                "Remaining": _round(target - net_sales) if target is not None else None,
                "Bill Quantity": _round(bill_quantity),
                "Footfall": _round(footfall),
                "Transactions (NOB)": _round(nob),
                "ATV": _round(safe_divide(net_sales, nob)),
                "RPV": _round(safe_divide(net_sales, footfall)),
                "Basket Size": _round(safe_divide(bill_quantity, nob)),
                "Conversion %": _round(_pct(nob, footfall), 1),
                "Achievement %": _round(achievement_pct, 1),
                "Remaining %": _round(None if achievement_pct is None else 100 - achievement_pct, 1),
            })
    return rows


def build_datewise_rows(db: Database, store: str, dates: list[str]) -> list[dict]:
    rows: list[dict] = []
    for iso in dates:
        k = daily_dashboard_store.compute_live_kpis(db, store, date.fromisoformat(iso))
        rows.append({
            "Date": iso,
            "Sales Target": _round(k["sales_target"]),
            "Net Sales": _round(k["net_sales"]),
            "Remaining": _round(k["remaining"]),
            "Bill Quantity": _round(k["bill_quantity"]),
            "Footfall": _round(k["footfall"]),
            "Transactions (NOB)": _round(k["nob"]),
            "ATV": _round(k["atv"]),
            "RPV": _round(k["rpv"]),
            "Basket Size": _round(k["basket_size"]),
            "Conversion %": _round(k["conversion_pct"], 1),
            "Achievement %": _round(k["achievement_pct"], 1),
            "Remaining %": _round(k["remaining_pct"], 1),
            "Remarks": k["reason"] or "",
        })
    return rows


def _fmt_currency(value: float | None) -> str:
    return "N/A" if value is None else f"{CURRENCY_SYMBOL}{value:,.0f}"


def _fmt_number(value: float | None) -> str:
    return "N/A" if value is None else f"{value:,.0f}"


def _fmt_pct(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.1f}%"


def build_overall_summary(db: Database, store: str, dates: list[str]) -> list[KpiItem]:
    bundles = [daily_dashboard_store.compute_live_kpis(db, store, date.fromisoformat(iso)) for iso in dates]
    total_net = sum(b["net_sales"] or 0.0 for b in bundles)
    total_qty = sum(b["bill_quantity"] or 0.0 for b in bundles)
    total_footfall = sum(b["footfall"] or 0.0 for b in bundles)
    total_nob = sum(b["nob"] or 0.0 for b in bundles)
    targets = [b["sales_target"] for b in bundles if b["sales_target"] is not None]
    total_target = sum(targets) if targets else None
    achievement_pct = _pct(total_net, total_target)
    return [
        KpiItem(label="Days Recorded", value=str(len(dates))),
        KpiItem(label="Date Range", value=f"{dates[0]} to {dates[-1]}" if dates else "N/A"),
        KpiItem(label="Total Sales Target", value=_fmt_currency(total_target)),
        KpiItem(label="Total Net Sales", value=_fmt_currency(total_net)),
        KpiItem(label="Overall Achievement %", value=_fmt_pct(achievement_pct)),
        KpiItem(label="Total Bill Quantity", value=_fmt_number(total_qty)),
        KpiItem(label="Total Footfall", value=_fmt_number(total_footfall)),
        KpiItem(label="Total Transactions (NOB)", value=_fmt_number(total_nob)),
        KpiItem(label="Blended ATV", value=_fmt_currency(safe_divide(total_net, total_nob))),
        KpiItem(label="Blended RPV", value=_fmt_currency(safe_divide(total_net, total_footfall))),
        KpiItem(label="Blended Basket Size", value=_fmt_number(safe_divide(total_qty, total_nob))),
        KpiItem(label="Blended Conversion %", value=_fmt_pct(_pct(total_nob, total_footfall))),
    ]


def _prev_year_line(
    target_date: date, store: str, kpis: dict, dataset: MasterDataset | None
) -> str:
    """One "Previous year same day" summary line for the PDF context block.
    "No historical data found" whenever DATASET.xlsx has no prior-year rows
    for this store (the usual case today) or no dataset was supplied."""
    matrix = None
    if dataset is not None:
        store_state = FilterState(stores=[store])
        matrix = daily_context.previous_year_same_day(
            target_date,
            kpis,
            apply_filters(dataset.fact, store_state),
            filter_store_level_table(dataset.footfall, store_state),
            filter_store_level_table(dataset.target, store_state),
        )
    if matrix is None:
        return "<b>Previous year same day:</b> No historical data found"
    net = next((r for r in matrix["rows"] if r["kpi"] == "net_sales"), None)
    if net is None or net["previous"] is None:
        return f"<b>Previous year same day ({matrix['date']}):</b> No historical data found"
    delta = "" if net["variance_pct"] is None else f" ({net['variance_pct']:+.1f}% vs today)"
    return (
        f"<b>Previous year same day ({matrix['date']}):</b> "
        f"Net Sales {_fmt_currency(net['previous'])}{delta}"
    )


def _context_text(
    target_date: date,
    store: str | None = None,
    kpis: dict | None = None,
    dataset: MasterDataset | None = None,
) -> str:
    weather = daily_context.get_weather(target_date)
    if weather is not None:
        bits = [weather.condition]
        if weather.temp_max_c is not None:
            bits.append(f"{weather.temp_max_c:.0f}°C / {(weather.temp_min_c or weather.temp_max_c):.0f}°C")
        if weather.precipitation_mm:
            bits.append(f"{weather.precipitation_mm:.0f}mm rain")
        weather_line = ", ".join(bits)
    else:
        weather_line = "unavailable"
    holiday = daily_context.get_holiday_name(target_date)
    election = daily_context.get_election_info(target_date)
    lines = [
        f"<b>Weather (Kolkata):</b> {weather_line}",
        f"<b>Day type:</b> {daily_context.day_type(target_date)}",
        f"<b>Holiday:</b> {holiday or 'none'}",
        f"<b>Election:</b> {election or 'none'}",
    ]
    if store is not None:
        lines.append(_prev_year_line(target_date, store, kpis or {}, dataset))
    return "<br/>".join(lines)


def build_daily_report_payload(
    db: Database, store: str, *, include_visuals: bool, dataset: MasterDataset | None = None
) -> ReportPayload:
    if store not in STORE_CODE_TO_NAME:
        raise ValueError(f"Unknown store code: {store!r}")
    store_name = STORE_CODE_TO_NAME[store]
    dates = report_dates(db, store)

    blocks: list = [TitleBlock(text=f"{store_name} — Daily Operations Report")]

    if include_visuals:
        today = date.today()
        today_kpis = daily_dashboard_store.compute_live_kpis(db, store, today)
        today_breakdown = daily_dashboard_store.compute_live_timeslot_breakdown(db, store, today)
        blocks.append(KpiGridBlock(heading="Overall Summary (All Recorded Days)", items=build_overall_summary(db, store, dates)))
        # zero_if_missing=True to match the live Daily Dashboard's gauges and
        # its *OrZero KPI cards -- a blank on this manual-entry surface means
        # "not logged yet today", not "column absent".
        blocks.append(GaugeBlock(spec=charts.conversion_gauge(today_kpis["conversion_pct"], zero_if_missing=True)))
        blocks.append(GaugeBlock(spec=charts.achievement_gauge(today_kpis["achievement_pct"], zero_if_missing=True)))
        blocks.append(GaugeBlock(spec=charts.remaining_pct_gauge(today_kpis["remaining_pct"], zero_if_missing=True)))
        blocks.append(GaugeBlock(spec=charts.atv_gauge(today_kpis["atv"], zero_if_missing=True)))
        blocks.append(GaugeBlock(spec=charts.rpv_gauge(today_kpis["rpv"], zero_if_missing=True)))
        blocks.append(GaugeBlock(spec=charts.basket_size_gauge(today_kpis["basket_size"], zero_if_missing=True)))
        blocks.append(ChartBlock(
            title="Today's Sales Performance",
            figure=charts.daily_timeslot_breakdown_chart(today_breakdown, today_kpis["sales_target"]),
        ))
        blocks.append(TextBlock(
            heading="Today's Context",
            text=_context_text(today, store=store, kpis=today_kpis, dataset=dataset),
        ))

    blocks.append(TableBlock(title="Date & Time Slot Wise", columns=_TIMESLOT_COLUMNS, rows=build_timeslot_rows(db, store, dates)))
    blocks.append(TableBlock(title="Date Wise Store Summary", columns=_DATEWISE_COLUMNS, rows=build_datewise_rows(db, store, dates)))

    span = f"{dates[0]} to {dates[-1]}" if dates else "no recorded dates"
    meta = ReportMeta(
        title=f"{store_name} — Daily Operations Report",
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        filters_summary_text=f"Store: {store_name} | All recorded dates ({span})",
        workbook_note="Figures are live Daily Operations data (MongoDB), not DATASET.xlsx.",
    )
    return ReportPayload(meta=meta, blocks=blocks)
