"""Authoritative split-handling — supersedes the rs_engine reverse-split heuristic.

Pipeline (runs as Phase 0 of nightly_data_pull, before grouped daily fetch):

    1. Fetch splits from Polygon /v3/reference/splits since (today - LOOKBACK_DAYS).
       Idempotent upsert into mi_splits (PRIMARY KEY ticker+execution_date).
    2. For every row where adjustment_applied = FALSE:
         - Re-fetch the ticker's daily history with adjusted=true (Polygon
           normalizes BOTH price and volume to post-split units).
         - Overwrite mi_daily_closes via upsert_ticker_history (close + volume
           overwritten, OHLC COALESCEd).
         - mark_split_applied.
    3. Audit events: split_detected (new row) / split_applied (re-fetch ok) /
       split_apply_failed (per-ticker error) / splits_ingest_summary.

The heuristic blocks in rs_engine.py (MAX_1D_RETURN, MAX_PERIOD_RETURN) become
unnecessary once cached history is split-adjusted. They false-positive on
recently-listed tickers in genuine vertical runups (XNDU 2026-05-01).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta

from agents.market_intelligence.collector import _polygon_get, et_today
from agents.market_intelligence.db import (
    get_unapplied_splits,
    log_audit_event,
    mark_split_applied,
    upsert_split,
    upsert_ticker_history,
)

logger = logging.getLogger(__name__)

# Polygon caps split queries — 60 calendar days is wide enough to catch missed
# weekend/holiday runs without hammering the endpoint.
LOOKBACK_DAYS = 60
# History to overwrite per affected ticker — 250 calendar days ≈ 180 trading
# bars, which is wider than the 6M RS lookback. Polygon caps day-aggs limit at
# 50000, so 250 days fits in a single page.
HISTORY_DAYS = 250
# Concurrency cap — splits-ingest typically touches < 30 tickers/day; Sem(5)
# keeps Polygon happy and finishes in seconds.
_SEM = asyncio.Semaphore(5)


async def _fetch_splits_page(since: date, cursor_url: str | None = None) -> dict:
    """Single page from /v3/reference/splits (or follow next_url cursor)."""
    if cursor_url:
        # next_url already includes apiKey (Polygon convention) — strip leading
        # base if present so _polygon_get's path concat works.
        path = cursor_url.replace("https://api.polygon.io", "")
        return await _polygon_get(path)
    return await _polygon_get(
        "/v3/reference/splits",
        {"execution_date.gte": since.isoformat(), "limit": 1000, "order": "asc"},
    )


async def fetch_splits(since: date) -> list[dict]:
    """All Polygon split records with execution_date >= `since`. Paginated."""
    all_results: list[dict] = []
    page = await _fetch_splits_page(since)
    while True:
        all_results.extend(page.get("results") or [])
        next_url = page.get("next_url")
        if not next_url:
            break
        page = await _fetch_splits_page(since, cursor_url=next_url)
    return all_results


async def fetch_ticker_history(ticker: str, days: int = HISTORY_DAYS) -> list[dict]:
    """Per-ticker daily aggs with adjusted=true. Polygon adjusts BOTH price and
    volume to post-split units, so a single re-fetch reconciles cached history.
    """
    today = et_today()
    from_d = (today - timedelta(days=days)).isoformat()
    to_d = today.isoformat()
    try:
        data = await _polygon_get(
            f"/v2/aggs/ticker/{ticker}/range/1/day/{from_d}/{to_d}",
            {"adjusted": "true", "sort": "asc", "limit": 50000},
        )
        return data.get("results") or []
    except Exception as e:
        logger.warning(f"Split re-fetch failed for {ticker}: {e}")
        return []


async def _get_old_close(ticker: str, trade_date) -> float | None:
    """Look up the close in mi_daily_closes for (ticker, date), if any.

    Used by `_apply_one`'s phantom-split sanity check: comparing the fresh
    adjusted-feed pre-split close against whatever was previously written
    distinguishes a real split (Polygon multiplied historical bars by
    split_factor) from a phantom (Polygon left bars un-adjusted because
    no actual event occurred).
    """
    from agents.market_intelligence.db import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT close FROM mi_daily_closes WHERE ticker=$1 AND trade_date=$2",
            ticker, trade_date,
        )


async def _apply_one(split_row: dict) -> tuple[str, bool, int]:
    """Re-fetch + overwrite cached history for one (ticker, execution_date).
    Returns (ticker, success, n_bars_written)."""
    ticker = split_row["ticker"]
    exec_date = split_row["execution_date"]
    split_from = int(split_row["split_from"])
    split_to = int(split_row["split_to"])
    async with _SEM:
        bars = await fetch_ticker_history(ticker)
        if not bars:
            # Polygon Starter doesn't carry OTC / pink-sheet / foreign-suffix
            # tickers (.F / .Y / etc.). They re-queue every nightly run and
            # spam split_apply_failed (152 events on 2026-05-08, all foreign
            # F/Y suffix). Mark applied so we don't retry — same idiom as the
            # phantom-detected branch. Operator can `reset_split_applied`
            # one-shot if Polygon coverage changes. Foreign tickers aren't in
            # the RS universe (CS + ADRC only) so adjustment_applied=TRUE
            # has no downstream effect; this is purely log-noise hygiene.
            await log_audit_event(
                "split_apply_skipped_no_data",
                f"{ticker} {exec_date} {split_from}:{split_to} — Polygon returned no bars; marking applied to stop retry",
            )
            await mark_split_applied(ticker, exec_date)
            return (ticker, False, 0)

        # Phantom-split sanity check (AGL 3/31 25:1 incident class). Polygon
        # sometimes reports a split that didn't actually execute. The adjusted
        # feed then returns un-adjusted history (since no adjustment is needed),
        # but Apollo records adjustment_applied=TRUE — leaving downstream
        # detectors (parabolic, RS) reading wrong-units pre-execution data.
        #
        # Compare the FRESH adjusted-feed pre-split close against whatever is
        # currently in mi_daily_closes for that date (un-adjusted, written by
        # prior nightly grouped-daily ingests OR a premature-apply leftover).
        #
        #   Real split with proper Polygon adjustment:
        #     new_close_pre ≈ old_close_pre × (split_from / split_to)
        #     adjustment_factor (new/old) ≈ split_factor → APPLY
        #
        #   Phantom split (Polygon mis-reported, no actual event):
        #     new_close_pre ≈ old_close_pre (no adjustment applied either way)
        #     adjustment_factor ≈ 1.0 → SKIP
        #
        # 2026-05-14 fix: the previous formula (`close_pre / close_post` vs
        # `split_from / split_to`) was wrong for adjusted-feed data — both
        # real and phantom splits yield close_pre/close_post ≈ 1.0 after
        # Polygon's adjustment, so every real split was wrongly flagged
        # phantom and skipped. 10 tickers affected 5/08-5/14 including AIXI
        # and CVNA. See incident write-up in CLAUDE.md.
        from datetime import datetime, timezone
        bars_by_date = {
            datetime.fromtimestamp(b["t"] / 1000, tz=timezone.utc).date(): b
            for b in bars
            if "t" in b and "c" in b
        }
        # Find the trading day on/before exec_date - 1 (the last pre-split bar).
        prev_date = exec_date - timedelta(days=1)
        for _ in range(7):  # walk back through weekend/holidays
            if prev_date in bars_by_date:
                break
            prev_date -= timedelta(days=1)

        if prev_date in bars_by_date:
            new_close_pre = float(bars_by_date[prev_date]["c"])
            # Query whatever is currently in mi_daily_closes for that date.
            # If no row (first-ever apply), skip the check — can't compare,
            # default to apply (Polygon reported a split, trust it).
            old_close_pre = await _get_old_close(ticker, prev_date)
            if old_close_pre is not None and old_close_pre > 0 and new_close_pre > 0:
                adjustment_factor = new_close_pre / old_close_pre
                # Tolerance: 10% — adjustment_factor should be very close to
                # 1.0 for phantoms (same un-adjusted data both reads) or very
                # close to split_factor for real splits. Tight tolerance is OK
                # because we're comparing the SAME date across two fetches.
                if abs(adjustment_factor - 1.0) < 0.10:
                    await log_audit_event(
                        "split_phantom_detected",
                        f"{ticker} {exec_date} {split_from}:{split_to} — "
                        f"adjustment_factor {adjustment_factor:.3f} ≈ 1.0 "
                        f"(old close {old_close_pre:.4f}, new close {new_close_pre:.4f}); "
                        f"Polygon did not apply an adjustment. Skipping apply; mark phantom.",
                    )
                    # Don't write any bars; mark applied so we don't retry every
                    # nightly run. Operator can manually reset if Polygon corrects.
                    await mark_split_applied(ticker, exec_date)
                    return (ticker, False, 0)

        n_written = await upsert_ticker_history(ticker, bars)
        await mark_split_applied(ticker, exec_date)
        await log_audit_event(
            "split_applied",
            f"{ticker} {exec_date} {split_from}:{split_to} — {n_written} bars overwritten",
        )
        return (ticker, True, n_written)


async def run_splits_ingest(since: date | None = None) -> dict:
    """Top-level: fetch new splits → apply unapplied. Returns summary dict.

    Designed to run as Phase 0 of nightly_data_pull. Safe to invoke from
    backfill_splits.py with `since` set to a wider window for one-shot
    historical reconciliation.
    """
    if since is None:
        since = et_today() - timedelta(days=LOOKBACK_DAYS)

    # 1. Fetch + upsert
    n_new = 0
    try:
        results = await fetch_splits(since)
        for r in results:
            try:
                exec_date = date.fromisoformat(r["execution_date"])
            except (KeyError, ValueError):
                continue
            inserted = await upsert_split(
                ticker=r["ticker"],
                execution_date=exec_date,
                split_from=int(r["split_from"]),
                split_to=int(r["split_to"]),
                polygon_id=r.get("id"),
            )
            if inserted:
                n_new += 1
                await log_audit_event(
                    "split_detected",
                    f"{r['ticker']} {r['execution_date']} {r['split_from']}:{r['split_to']}",
                )
    except Exception as e:
        logger.error(f"Splits fetch failed: {e}")
        await log_audit_event("splits_ingest_error", f"fetch failed: {e}")

    # 2. Apply unapplied (includes both newly inserted + any leftover from prior failures)
    unapplied = await get_unapplied_splits(since=since)
    n_ok = 0
    n_fail = 0
    if unapplied:
        outcomes = await asyncio.gather(
            *[_apply_one(s) for s in unapplied], return_exceptions=True
        )
        for o in outcomes:
            if isinstance(o, Exception):
                n_fail += 1
                logger.exception(f"Split apply raised: {o}")
                continue
            _, ok, _ = o
            if ok:
                n_ok += 1
            else:
                n_fail += 1

    summary = {
        "splits_detected_new": n_new,
        "splits_applied_ok": n_ok,
        "splits_applied_failed": n_fail,
        "splits_pending": len(unapplied) - n_ok - n_fail if unapplied else 0,
    }
    await log_audit_event(
        "splits_ingest_summary",
        f"new={n_new} applied={n_ok} failed={n_fail}",
    )
    logger.info(f"Splits ingest: {summary}")
    return summary
