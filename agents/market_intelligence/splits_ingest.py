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
        # Verify by comparing the adjusted close on the day BEFORE execution
        # against the expected pre/post ratio. For a real split:
        #   close_before / close_after ≈ split_to / split_from
        # (e.g. 25:1 reverse: pre-split adjusted close is ~25× the next-day
        # post-split close in Polygon's adjusted units.)
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
        # And the first bar on/after exec_date.
        post_date = exec_date
        for _ in range(7):
            if post_date in bars_by_date:
                break
            post_date += timedelta(days=1)

        if prev_date in bars_by_date and post_date in bars_by_date:
            close_pre = float(bars_by_date[prev_date]["c"])
            close_post = float(bars_by_date[post_date]["c"])
            if close_post > 0 and split_from > 0:
                expected_ratio = split_from / split_to  # >1 for reverse, <1 for forward
                actual_ratio = close_pre / close_post
                # Tolerance: 30% — splits adjust prices but real overnight
                # moves can compound. Wider than typical price moves but tight
                # enough to catch a no-op (ratio ≈ 1.0 instead of 25.0 for AGL).
                tol = 0.30
                ratio_ok = (
                    expected_ratio * (1 - tol) <= actual_ratio <= expected_ratio * (1 + tol)
                )
                if not ratio_ok:
                    await log_audit_event(
                        "split_phantom_detected",
                        f"{ticker} {exec_date} {split_from}:{split_to} — "
                        f"expected ratio {expected_ratio:.2f}, actual "
                        f"close_pre/close_post = {close_pre:.2f}/{close_post:.2f} "
                        f"= {actual_ratio:.2f}. Skipping apply; mark phantom.",
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
