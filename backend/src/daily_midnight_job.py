"""Midnight auto-finalize job for the Daily Dashboard (Asia/Kolkata).

At 00:00 IST every day, for each store, re-runs the equivalent of a Manual
Daily Entry Final Submission for both the day that just ended AND the day
that's just starting -- refreshing NET SALES/FOOTFALL/NOB/ATV/RPV/Basket
Size/Conversion %/Achievement % against each day's live bill/footfall/NOB
logs (all three are always live sums, so they never need a manual resubmit
either), while leaving Remarks exactly as last entered (finalize_day passes
reason=None, and save_target_entry's None-means-"leave unchanged" semantics
apply to it). Finalizing the day that just ended is the safety net for "if
you forget to click Update/Final Submission, the system submits it for
you"; finalizing the day that's just starting means a fresh day gets a
non-N/A achievement_pct/remaining_pct from the moment the store opens,
instead of only retroactively the following midnight.

TEMPORARY: until Phase 2's Admin UI ships real target-setting, a store/date
with no admin-set SALES TARGET gets one auto-assigned here first
(daily_dashboard_store.auto_assign_target_if_missing, seeded from
daily_context.suggested_daily_target's historical-median-Net-Sales
estimate over DATASET.xlsx's `fact` for that store) rather than being
skipped outright -- see CLAUDE.md's Daily Dashboard section. A store with
no historical fact data at all (so no estimate can be made) is still
skipped, same as before.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from config.settings import STORE_CODE_TO_NAME
from db.session import session_scope
from src import daily_context, daily_dashboard_store
from src.filter_engine import FilterState, apply_filters

logger = logging.getLogger(__name__)

IST = ZoneInfo("Asia/Kolkata")


def _seconds_until_next_midnight(now: datetime | None = None) -> float:
    now = now or datetime.now(IST)
    next_midnight = datetime.combine(now.date() + timedelta(days=1), datetime.min.time(), tzinfo=IST)
    return (next_midnight - now).total_seconds()


def finalize_day(target_date: date, fact: pd.DataFrame) -> None:
    # One session_scope() per store, not one shared session for the whole
    # loop -- session_scope() commits (or rolls back) on exit, so an
    # isolated session per store means one store's failure can't also
    # discard another store's already-computed finalize in the same run.
    # No per-request `Depends(get_db)` is available here (this isn't a
    # FastAPI request) -- session_scope() is db/session.py's equivalent for
    # exactly this kind of background-task/script caller.
    for store in STORE_CODE_TO_NAME:
        try:
            with session_scope() as db:
                if daily_dashboard_store.read_store_target(db, store, target_date) is None:
                    store_fact = apply_filters(fact, FilterState(stores=[store]))
                    suggested = daily_context.suggested_daily_target(store_fact)
                    if suggested is None:
                        continue  # no historical data to estimate from either -- nothing to finalize
                    daily_dashboard_store.auto_assign_target_if_missing(db, store, target_date, suggested)
                daily_dashboard_store.save_target_entry(db, store, target_date, None)
            logger.info("Midnight auto-finalize: %s %s done.", store, target_date)
        except Exception:
            logger.exception("Midnight auto-finalize failed for %s %s.", store, target_date)


async def run_midnight_finalizer(fact: pd.DataFrame) -> None:
    """Runs forever as a background task (started from app.py's lifespan);
    cancel it on shutdown. Blocking DB I/O (psycopg is a sync driver) is
    offloaded via asyncio.to_thread so a slow query never stalls the event
    loop or other requests. `fact` is app.state.dataset.fact, passed in once
    at startup -- DATASET.xlsx is only ever reloaded on process restart, so
    this stays the same frame for the process's whole lifetime.

    Correct as long as the deployed app is a single instance -- if this
    ever runs as multiple replicas, each one starts this same in-process
    task, and all of them would fire finalize_day at the same midnight,
    redundantly (each save_target_entry/auto_assign_target_if_missing call
    is idempotent, so this isn't a correctness bug today, just wasted
    duplicate work) -- moving to a platform cron hitting a protected
    endpoint, or a Postgres advisory lock so only one replica actually runs
    it, is the real fix if that happens."""
    while True:
        await asyncio.sleep(_seconds_until_next_midnight())
        now = datetime.now(IST)
        finished_date = (now - timedelta(minutes=1)).date()
        starting_date = now.date()
        logger.info("Midnight auto-finalize starting for %s (ended) and %s (starting).", finished_date, starting_date)
        await asyncio.to_thread(finalize_day, finished_date, fact)
        await asyncio.to_thread(finalize_day, starting_date, fact)
