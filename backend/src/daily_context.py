"""Supplemental context for the Daily Dashboard tab: weather, public/regional
holidays, and election (ECI-declared poll/counting) dates for whichever
single day is selected -- the signals a store manager actually reaches for
when explaining why a day missed its sales target. Every external call
degrades to None instead of raising, so a network hiccup never takes down
the KPI cards that share the page (same "N/A, don't fabricate, don't crash"
rule the rest of the app follows).

`suggested_daily_target` also lives here -- a historical-median estimate the
midnight job seeds a missing SALES TARGET with (see src/daily_midnight_job.py).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date

import holidays
import pandas as pd
import requests

from config.settings import CACHE_DIR
from src.kpi_engine import compute_kpis

logger = logging.getLogger(__name__)

# All three CITIMART stores (New Market, Hatibagan, Chowringhee) are in
# central Kolkata, a few km apart -- one weather reading is representative
# for all of them, so this doesn't need to be a per-store lookup.
KOLKATA_LAT = 22.5726
KOLKATA_LON = 88.3639

WEATHER_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
WEATHER_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
WEATHER_CACHE_PATH = CACHE_DIR / "weather_cache.json"

# West Bengal holidays (not just national ones): Durga Puja, Poila Boishakh
# etc. move Kolkata retail footfall far more than national bank holidays do.
_INDIA_WB_HOLIDAYS = holidays.country_holidays("IN", subdiv="WB")

# WMO weather codes (Open-Meteo's `weathercode`), collapsed to the bands that
# matter for a retail footfall explanation -- not the full WMO table.
_WEATHER_CODE_LABELS: dict[range, str] = {
    range(0, 1): "Clear sky",
    range(1, 4): "Partly cloudy",
    range(45, 49): "Fog",
    range(51, 58): "Drizzle",
    range(61, 68): "Rain",
    range(71, 78): "Snow",
    range(80, 83): "Rain showers",
    range(95, 100): "Thunderstorm",
}


def _weather_label(code: int | None) -> str:
    if code is None:
        return "Unknown"
    for code_range, label in _WEATHER_CODE_LABELS.items():
        if code in code_range:
            return label
    return "Unknown"


def _load_weather_cache() -> dict:
    if not WEATHER_CACHE_PATH.exists():
        return {}
    try:
        return json.loads(WEATHER_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_weather_cache(cache: dict) -> None:
    try:
        WEATHER_CACHE_PATH.write_text(json.dumps(cache), encoding="utf-8")
    except Exception:
        logger.exception("Failed to persist weather cache; continuing without it.")


@dataclass
class WeatherReading:
    condition: str
    temp_max_c: float | None
    temp_min_c: float | None
    precipitation_mm: float | None


def get_weather(target_date: date) -> WeatherReading | None:
    """Historical reading for dates on/before today (Open-Meteo's archive
    API, typically available with ~a few days' lag), forecast reading for
    future dates (Open-Meteo's forecast API, ~16 day horizon). Returns None
    -- never raises -- on any network failure, missing data, or a date
    outside both APIs' supported range, so callers can render "Weather
    unavailable" instead of breaking the page."""
    cache = _load_weather_cache()
    key = target_date.isoformat()
    if key in cache:
        cached = cache[key]
        return WeatherReading(**cached) if cached else None

    is_past = target_date <= date.today()
    url = WEATHER_ARCHIVE_URL if is_past else WEATHER_FORECAST_URL
    params = {
        "latitude": KOLKATA_LAT,
        "longitude": KOLKATA_LON,
        "start_date": key,
        "end_date": key,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,weathercode",
        "timezone": "Asia/Kolkata",
    }
    try:
        resp = requests.get(url, params=params, timeout=6)
        resp.raise_for_status()
        daily = resp.json().get("daily", {})
        codes = daily.get("weathercode") or []
        maxes = daily.get("temperature_2m_max") or []
        mins = daily.get("temperature_2m_min") or []
        precip = daily.get("precipitation_sum") or []
        if not codes:
            cache[key] = None
            _save_weather_cache(cache)
            return None
        reading = WeatherReading(
            condition=_weather_label(codes[0]),
            temp_max_c=maxes[0] if maxes else None,
            temp_min_c=mins[0] if mins else None,
            precipitation_mm=precip[0] if precip else None,
        )
        cache[key] = reading.__dict__
        _save_weather_cache(cache)
        return reading
    except Exception:
        logger.warning("Weather lookup failed for %s; showing 'unavailable' instead.", key, exc_info=True)
        return None


def get_holiday_name(target_date: date) -> str | None:
    """West Bengal (India) public/regional holiday name for this date, or
    None. Never raises: `holidays` is a local calendar lookup, not a network
    call, but callers still shouldn't have to special-case a bad date."""
    try:
        return _INDIA_WB_HOLIDAYS.get(target_date)
    except Exception:
        logger.exception("Holiday lookup failed for %s.", target_date)
        return None


# ECI-declared election dates relevant to the three Kolkata stores -- polling
# phases (any West Bengal phase; a citywide bandh-like slowdown isn't limited
# to the seats polling that day) and the single statewide counting day, for
# both the central (Lok Sabha) and state (WB Vidhan Sabha) elections. This is
# a hand-maintained list, not a feed: extend it from the ECI's press note
# whenever the next general/assembly election (or a Kolkata by-election) is
# notified. ISO "YYYY-MM-DD" -> label.
_ELECTION_DATES: dict[str, str] = {
    # 2021 West Bengal Legislative Assembly election
    "2021-03-27": "WB Assembly election — Phase 1 polling",
    "2021-04-01": "WB Assembly election — Phase 2 polling",
    "2021-04-06": "WB Assembly election — Phase 3 polling",
    "2021-04-10": "WB Assembly election — Phase 4 polling",
    "2021-04-17": "WB Assembly election — Phase 5 polling",
    "2021-04-22": "WB Assembly election — Phase 6 polling",
    "2021-04-26": "WB Assembly election — Phase 7 polling",
    "2021-04-29": "WB Assembly election — Phase 8 polling",
    "2021-05-02": "WB Assembly election — counting day",
    # 2024 Lok Sabha (general) election — West Bengal polled in all 7 phases
    "2024-04-19": "Lok Sabha election — Phase 1 polling",
    "2024-04-26": "Lok Sabha election — Phase 2 polling",
    "2024-05-07": "Lok Sabha election — Phase 3 polling",
    "2024-05-13": "Lok Sabha election — Phase 4 polling",
    "2024-05-20": "Lok Sabha election — Phase 5 polling",
    "2024-05-25": "Lok Sabha election — Phase 6 polling",
    "2024-06-01": "Lok Sabha election — Phase 7 polling",
    "2024-06-04": "Lok Sabha election — counting day",
}


def get_election_info(target_date: date) -> str | None:
    """Label for an ECI-declared election polling/counting day (central or
    West Bengal state) on this date, or None. Pure local lookup against the
    hand-maintained _ELECTION_DATES table -- never raises, never a network
    call."""
    return _ELECTION_DATES.get(target_date.isoformat())


# Wed/Thu is the reliable mid-week lull for Kolkata retail; Sat/Sun its own
# weekend pattern; Mon/Tue/Fri behave like an ordinary trading day. This is a
# footfall-shape label the store managers already think in, deliberately
# distinct from the plain calendar `is_weekend` flag (weekday() >= 5) the
# /api/daily/live response also carries -- keep both.
_DAY_TYPE_BY_WEEKDAY: dict[int, str] = {
    0: "Regular",    # Monday
    1: "Regular",    # Tuesday
    2: "Mid-Week",   # Wednesday
    3: "Mid-Week",   # Thursday
    4: "Regular",    # Friday
    5: "Weekend",    # Saturday
    6: "Weekend",    # Sunday
}


def day_type(target_date: date) -> str:
    """Coarse day-type bucket for the Daily Dashboard's context strip:
    "Weekend" (Sat/Sun), "Mid-Week" (Wed/Thu), or "Regular" (Mon/Tue/Fri).
    Pure calendar arithmetic -- never raises, never a network call."""
    return _DAY_TYPE_BY_WEEKDAY.get(target_date.weekday(), "Regular")


def _same_day_last_year(target_date: date) -> date:
    """Same calendar day one year earlier, clamping 29 Feb -> 28 Feb (the
    only day with no exact prior-year counterpart) -- mirrors
    src/comparison_engine.same_period_last_year_window's per-date clamp."""
    try:
        return target_date.replace(year=target_date.year - 1)
    except ValueError:
        return target_date.replace(year=target_date.year - 1, day=28)


def _slice_to_single_date(df: pd.DataFrame, day: date) -> pd.DataFrame:
    """Rows of `df` falling on `day` (half-open datetime64 comparison, same
    style as filter_engine._apply_store_date). Empty frame in -> empty out."""
    if df.empty or "date" not in df.columns:
        return df.iloc[0:0]
    dt = pd.to_datetime(df["date"], errors="coerce")
    lo = pd.Timestamp(day)
    return df.loc[(dt >= lo) & (dt < lo + pd.Timedelta(days=1))]


# KPIs shown in the previous-year comparison matrix, in display order.
# Keyed by compute_live_kpis / KpiBundle field name so the frontend can reuse
# DAILY_KPI_LABELS / DAILY_KPI_FORMATTERS (format.ts) without a label map here.
_PREV_YEAR_KPIS: tuple[str, ...] = (
    "net_sales", "footfall", "nob", "bill_quantity",
    "atv", "rpv", "basket_size", "conversion_pct", "achievement_pct",
)


def previous_year_same_day(
    target_date: date,
    current_kpis: dict,
    fact: pd.DataFrame,
    footfall: pd.DataFrame,
    target: pd.DataFrame,
) -> dict | None:
    """Same-calendar-day-last-year performance matrix for the Daily
    Dashboard. `fact` / `footfall` / `target` are DATASET.xlsx frames the
    caller has already narrowed to the one store (same convention as
    `suggested_daily_target`); this slices them to the single prior-year
    date and runs the shared src/kpi_engine. `current_kpis` is
    compute_live_kpis' dict for today, so each row can show
    this-year-vs-last-year side by side.

    Returns None -- the caller renders that as "No historical data found" --
    when DATASET.xlsx holds no rows for that store on that date (the usual
    case today: the workbook is a single calendar year with no prior-year
    history yet, so this mostly exists as scaffolding for when multi-year
    data lands). Never raises."""
    try:
        prev_date = _same_day_last_year(target_date)
        sliced_fact = _slice_to_single_date(fact, prev_date)
        sliced_footfall = _slice_to_single_date(footfall, prev_date)
        if sliced_fact.empty and sliced_footfall.empty:
            return None
        prev = compute_kpis(sliced_fact, sliced_footfall, _slice_to_single_date(target, prev_date))
    except Exception:
        logger.exception("Previous-year comparison failed for %s; hiding the matrix.", target_date)
        return None

    def _num(value) -> float | None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        return float(value) if pd.notna(value) else None

    rows = []
    for key in _PREV_YEAR_KPIS:
        current = _num(current_kpis.get(key))
        previous = _num(getattr(prev, key, None))
        variance_pct = None
        if current is not None and previous:
            variance_pct = (current - previous) / previous * 100
        rows.append({
            "kpi": key,
            "current": current,
            "previous": previous,
            "variance_pct": variance_pct,
        })
    return {"date": prev_date.isoformat(), "rows": rows}


def suggested_daily_target(fact: pd.DataFrame) -> float | None:
    """Deterministic stand-in SALES TARGET (historical median daily Net
    Sales, store-scoped -- caller passes a `fact` frame already narrowed to
    one store, same convention as trailing_comparison above) for a
    store+date an admin hasn't set a real target for yet. Median rather than
    mean so a handful of exceptional days (festival spikes, etc.) in
    DATASET.xlsx's single year of history don't skew the assigned target.
    This only exists to keep achievement_pct/remaining_pct non-N/A until
    Phase 2's Admin UI ships real target-setting -- see
    src/daily_midnight_job.py's docstring and CLAUDE.md's Daily Dashboard
    section for the temporary-mechanism note."""
    if fact.empty or "date" not in fact.columns or "net_amount" not in fact.columns:
        return None
    dt = pd.to_datetime(fact["date"], errors="coerce").dt.date
    daily_totals = fact.groupby(dt)["net_amount"].sum()
    if daily_totals.empty:
        return None
    return float(daily_totals.median())
