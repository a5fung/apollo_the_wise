#!/usr/bin/env python3
"""
Backfill missing minute bars into mi_intraday_bars for the EP backtest
population — the goal is to stop bar coverage being a filter artifact
(only ticker-days the OLD live filters alerted on have bars, so a
backtest over that subset can only answer "did big liquid gappers work",
not "does EP work"). See docs/design/ep_backtest_spec_2026-08-29.md and
docs/analysis/482_geometry_counterfactual_2026-08-29.md (the retracted
analysis that motivated this).

Population source: a captured snapshot of ticker-days meeting the 9%
gap floor since 2026-04-13, one row per (trade_date, ticker), with a
`has_orb_bar` flag saying whether mi_intraday_bars already has the
09:30 ET bar. This script re-derives "needs backfill" from that raw
file (max(gap_pct_open, scanlog_max_gap) >= 9.0 AND has_orb_bar != 't')
rather than trusting a pre-filtered list.

MUST run inside apollo-execution (the only container with Alpaca data
creds — ALPACA_PAPER_API_KEY is blanked on apollo-market by design,
see docker/docker-compose.prod.yml).

Safety:
  - INSERT only. ON CONFLICT (ticker, bar_time) DO NOTHING — never
    overwrites a row the live system wrote. Never UPDATE/DELETE/DDL.
  - Idempotent / resumable: at the start of each date, re-queries
    mi_intraday_bars for which tickers already have a 09:30 ET bar and
    skips them. A separate confirmed-no-data skip-list (written next to
    the log file) means a legitimately-empty ticker (delisted / halted
    all day / never traded on the active feed) is not re-fetched forever
    across restarts.

Usage (inside apollo-execution):
    python /tmp/backfill_orb_bars.py /tmp/_bt_population_capture.psv /tmp/backfill_progress.log
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, "/app")  # PYTHONPATH=/app is set in the image; belt-and-suspenders for `python /tmp/x.py`

from alpaca.data.requests import StockBarsRequest  # noqa: E402
from alpaca.data.timeframe import TimeFrame  # noqa: E402

from agents.market_intelligence.broker.alpaca_client import _get_data_client, get_data_feed  # noqa: E402
from agents.market_intelligence.db import get_pool  # noqa: E402

ET = ZoneInfo("America/New_York")
GAP_FLOOR = 9.0
CHUNK_SIZE_START = 200
MIN_CHUNK_SIZE = 10
SLEEP_BETWEEN_REQUESTS = 0.35
MAX_RETRIES = 4


def _log(msg: str, logf) -> None:
    line = f"{datetime.now(ET).isoformat()} {msg}"
    print(line, flush=True)
    logf.write(line + "\n")
    logf.flush()


def load_population(path: str) -> list[tuple]:
    """Re-derive the backfill population from the raw capture file.

    Columns: trade_date|ticker|open|prev_close|prev_volume|gap_pct_open|
    scanlog_max_gap|in_open_seed|in_scanlog_seed|has_orb_bar|has_any_bar|
    prev_trade_date|gap_days
    """
    pop = []
    with open(path) as f:
        for line in f:
            line = line.rstrip("\n")
            if not line:
                continue
            parts = line.split("|")
            if len(parts) != 13:
                continue
            (trade_date, ticker, _open, _prev_close, _prev_volume, gap_pct_open,
             scanlog_max_gap, _in_open_seed, _in_scanlog_seed, has_orb_bar,
             _has_any_bar, _prev_trade_date, _gap_days) = parts

            def to_f(s):
                try:
                    return float(s)
                except ValueError:
                    return None

            vals = [v for v in (to_f(gap_pct_open), to_f(scanlog_max_gap)) if v is not None]
            if not vals:
                continue
            if max(vals) >= GAP_FLOOR and has_orb_bar != "t":
                d = datetime.strptime(trade_date, "%Y-%m-%d").date()
                pop.append((d, ticker))
    return pop


def load_resolved_skip(path: str) -> set:
    """(date, ticker) pairs already given a DEFINITIVE answer in a prior run
    (zero bars all day, OR has bars but none at exactly 09:30) — historical
    data doesn't change, so these are never worth re-fetching on resume.
    Distinct from `already_covered()`, which only catches the case where the
    09:30 bar itself landed."""
    skip = set()
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                line = line.rstrip("\n")
                if not line:
                    continue
                d, t, _bucket = line.split("\t")
                skip.add((datetime.strptime(d, "%Y-%m-%d").date(), t))
    return skip


async def already_covered(conn, pairs: list[tuple]) -> set:
    """Which (trade_date, ticker) pairs already have a bar at exactly 09:30 ET."""
    if not pairs:
        return set()
    tickers, bar_times, lookup = [], [], {}
    for d, t in pairs:
        bt = datetime.combine(d, datetime.min.time().replace(hour=9, minute=30), tzinfo=ET)
        tickers.append(t)
        bar_times.append(bt)
        lookup[(t, bt)] = (d, t)
    rows = await conn.fetch(
        """
        SELECT b.ticker, b.bar_time
        FROM mi_intraday_bars b
        JOIN unnest($1::text[], $2::timestamptz[]) AS q(ticker, bar_time)
          ON b.ticker = q.ticker AND b.bar_time = q.bar_time
        """,
        tickers, bar_times,
    )
    covered = set()
    for r in rows:
        key = (r["ticker"], r["bar_time"])
        if key in lookup:
            covered.add(lookup[key])
    return covered


async def insert_bars(conn, records: list[tuple]) -> tuple[int, int]:
    """records: (ticker, bar_time, open, high, low, close, volume, vwap).
    Returns (inserted, already_present)."""
    if not records:
        return 0, 0
    cols = list(zip(*records))
    rows = await conn.fetch(
        """
        INSERT INTO mi_intraday_bars (ticker, bar_time, open, high, low, close, volume, vwap)
        SELECT * FROM unnest($1::text[], $2::timestamptz[], $3::float8[], $4::float8[],
                              $5::float8[], $6::float8[], $7::bigint[], $8::float8[])
        ON CONFLICT (ticker, bar_time) DO NOTHING
        RETURNING ticker, bar_time
        """,
        list(cols[0]), list(cols[1]), list(cols[2]), list(cols[3]),
        list(cols[4]), list(cols[5]), list(cols[6]), list(cols[7]),
    )
    inserted = len(rows)
    return inserted, len(records) - inserted


def _fetch_bars_sync(client, tickers, start, end):
    req = StockBarsRequest(
        symbol_or_symbols=tickers,
        timeframe=TimeFrame.Minute,
        start=start,
        end=end,
        feed=get_data_feed(),
    )
    return client.get_stock_bars(req)


async def fetch_chunk_with_retry(client, tickers, start, end, logf):
    delay = 1.0
    last_exc = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return await asyncio.to_thread(_fetch_bars_sync, client, tickers, start, end)
        except Exception as e:  # noqa: BLE001 — broad on purpose, retried + logged
            last_exc = e
            _log(f"    fetch attempt {attempt}/{MAX_RETRIES} failed for {len(tickers)} tickers: {str(e)[:200]}", logf)
            if attempt < MAX_RETRIES:
                await asyncio.sleep(delay)
                delay *= 2
    raise last_exc


MAX_SHRINKS_PER_SLICE = 2


async def fetch_slice(client, need, i, start, end, chunk_size, logf):
    """Fetch need[i:i+chunk_size]. On a fetch failure (after MAX_RETRIES
    internal retries), shrink the slice up to MAX_SHRINKS_PER_SLICE times
    rather than retrying forever — a non-size-related failure (auth, feed
    permission, bad date) must terminate, not oscillate.

    Returns (bars_or_None, actual_chunk_used, updated_chunk_size).
    bars is None only when the slice failed permanently even at the
    smallest chunk size tried.
    """
    size = chunk_size
    shrinks = 0
    while True:
        chunk = need[i:i + size]
        try:
            bars = await fetch_chunk_with_retry(client, chunk, start, end, logf)
            return bars, chunk, size
        except Exception as e:  # noqa: BLE001
            shrinks += 1
            if size > MIN_CHUNK_SIZE and shrinks <= MAX_SHRINKS_PER_SLICE:
                size = max(MIN_CHUNK_SIZE, size // 2)
                _log(f"  shrinking chunk_size to {size} after failure (shrink {shrinks}/{MAX_SHRINKS_PER_SLICE})", logf)
                continue
            _log(f"  CHUNK FAILED PERMANENTLY ({len(chunk)} tickers, size={size}): {str(e)[:300]}", logf)
            return None, chunk, size


async def main():
    pop_path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/_bt_population_capture.psv"
    log_path = sys.argv[2] if len(sys.argv) > 2 else "/tmp/backfill_progress.log"
    date_limit = sys.argv[3:] if len(sys.argv) > 3 else None  # optional: restrict to these dates (pilot mode)
    resolved_path = log_path + ".resolved.tsv"
    summary_path = log_path + ".summary.json"

    logf = open(log_path, "a")

    pop = load_population(pop_path)
    by_date: dict = {}
    for d, t in pop:
        by_date.setdefault(d, []).append(t)
    dates = sorted(by_date.keys())
    if date_limit:
        dates = [d for d in dates if str(d) in date_limit]
        _log(f"PILOT MODE: restricted to dates {date_limit}", logf)
    _log(f"population: {len(pop)} ticker-days across {len(by_date)} dates, {len(set(t for _, t in pop))} distinct tickers "
         f"(processing {len(dates)} dates this run)", logf)

    resolved_skip = load_resolved_skip(resolved_path)
    if resolved_skip:
        _log(f"resuming: {len(resolved_skip)} (date,ticker) pairs already definitively resolved in a prior run, will not re-fetch", logf)

    client = _get_data_client()
    pool = await get_pool()

    resolved_f = open(resolved_path, "a")
    debug_shape_logged = False

    grand_inserted = 0
    grand_already = 0
    grand_zero_bars = 0
    grand_bars_not_0930 = 0
    failed_dates = []

    for d in dates:
        tickers = sorted(set(by_date[d]))
        pairs = [(d, t) for t in tickers]
        async with pool.acquire() as conn:
            covered = await already_covered(conn, pairs)
        need = [t for t in tickers if (d, t) not in covered and (d, t) not in resolved_skip]
        already_resolved = sum(1 for t in tickers if (d, t) in resolved_skip)
        if not need:
            _log(f"{d}: {len(tickers)} tickers — all covered or already resolved, skip", logf)
            continue
        _log(f"{d}: {len(need)}/{len(tickers)} tickers need fetch "
             f"({len(covered)} already covered, {already_resolved} already resolved)", logf)

        start = datetime.combine(d, datetime.min.time().replace(hour=9, minute=30), tzinfo=ET)
        end = datetime.combine(d, datetime.min.time().replace(hour=16, minute=0), tzinfo=ET)

        chunk_size = CHUNK_SIZE_START
        i = 0
        date_inserted = 0
        date_already = 0
        date_zero_bars = 0
        date_bars_not_0930 = 0
        date_error = False
        while i < len(need):
            bars, chunk, chunk_size = await fetch_slice(client, need, i, start, end, chunk_size, logf)
            if bars is None:
                date_error = True
                failed_dates.append({"date": str(d), "tickers": chunk, "error": "permanent fetch failure, see log"})
                i += len(chunk)
                continue

            bar_data = bars.data if hasattr(bars, "data") else bars
            if not debug_shape_logged:
                _log(f"  [shape check] type(bars)={type(bars).__name__} type(bar_data)={type(bar_data).__name__} "
                     f"sample_keys={list(bar_data.keys())[:5]} requested_sample={chunk[:5]}", logf)
                debug_shape_logged = True

            records = []
            has_0930 = set()
            has_any = set()
            for t in chunk:
                bar_list = bar_data.get(t, []) or []
                if bar_list:
                    has_any.add(t)
                for b in bar_list:
                    if b.timestamp is None:
                        continue
                    if b.timestamp == start:
                        has_0930.add(t)
                    records.append((
                        t, b.timestamp, float(b.open), float(b.high), float(b.low),
                        float(b.close), int(b.volume),
                        float(b.vwap) if getattr(b, "vwap", None) is not None else None,
                    ))
            zero_bars = [t for t in chunk if t not in has_any]
            bars_not_0930 = [t for t in chunk if t in has_any and t not in has_0930]

            async with pool.acquire() as conn:
                ins, already = await insert_bars(conn, records)
            date_inserted += ins
            date_already += already
            date_zero_bars += len(zero_bars)
            date_bars_not_0930 += len(bars_not_0930)
            for t in zero_bars:
                resolved_f.write(f"{d}\t{t}\tzero_bars\n")
            for t in bars_not_0930:
                resolved_f.write(f"{d}\t{t}\thas_bars_not_0930\n")
            resolved_f.flush()

            _log(f"  chunk[{i}:{i+len(chunk)}] size={len(chunk)}: {len(records)} bars fetched, "
                 f"{ins} inserted, {already} already present, "
                 f"{len(zero_bars)} zero-bars tickers, {len(bars_not_0930)} has-bars-but-not-0930 tickers", logf)

            i += len(chunk)
            await asyncio.sleep(SLEEP_BETWEEN_REQUESTS)
            if chunk_size < CHUNK_SIZE_START:
                chunk_size = min(CHUNK_SIZE_START, chunk_size + 20)

        grand_inserted += date_inserted
        grand_already += date_already
        grand_zero_bars += date_zero_bars
        grand_bars_not_0930 += date_bars_not_0930
        _log(f"{d}: DONE inserted={date_inserted} already={date_already} "
             f"zero_bars={date_zero_bars} bars_not_0930={date_bars_not_0930}"
             f"{' [HAD PERMANENT CHUNK FAILURE]' if date_error else ''}", logf)

    resolved_f.close()

    summary = {
        "population_ticker_days": len(pop),
        "population_dates": len(by_date),
        "dates_processed_this_run": len(dates),
        "grand_inserted_rows": grand_inserted,
        "grand_already_present_rows": grand_already,
        "grand_zero_bars_ticker_days": grand_zero_bars,
        "grand_bars_not_0930_ticker_days": grand_bars_not_0930,
        "failed_dates": failed_dates,
    }
    with open(summary_path, "a") as sf:
        sf.write(json.dumps(summary, default=str) + "\n")

    _log(f"=== RUN TOTAL: inserted={grand_inserted} already_present_rows={grand_already} "
         f"zero_bars_ticker_days={grand_zero_bars} bars_not_0930_ticker_days={grand_bars_not_0930} "
         f"failed_dates={len(failed_dates)} ===", logf)
    if failed_dates:
        _log(f"FAILED DATES: {[fd['date'] for fd in failed_dates]}", logf)

    logf.close()


if __name__ == "__main__":
    asyncio.run(main())
