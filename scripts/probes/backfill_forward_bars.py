#!/usr/bin/env python3
"""
Forward-day minute-bar backfill for #327 (delayed-entry definitions) —
sessions +1..+20 AFTER the EP day, not the EP day itself (that was
backfill_orb_bars.py, 2026-08-29, day-0 only). See
docs/design/delayed_entry_definitions_327_2026-08-29.md §"Not computable":
every intraday delayed-entry tactic (base breakout, pivot reclaim, EMA
touch) needs bars on the days it actually fires, and forward-day coverage
was measured at only 15-21%.

Population = mi_ep_alerts (ALL rows, every score_tier, 2026-05-11..08-28)
UNION the backtest population in _bt_population_capture.psv filtered to
max(gap_pct_open, scanlog_max_gap) >= 9.0 (the same population day-0 used —
narrowing to HIGH-alert-only would reintroduce the exact coverage-artifact
bias the day-0 backfill was built to remove). Anchors dedup by (ticker,
anchor_date); forward sessions 1..20 come from mi_daily_closes — the real
per-ticker trading calendar, never a generated Mon-Fri calendar.

"Covered" = ANY existing bar that trade_date (matches the 327_q5.sql
before/after measurement exactly, so before/after numbers are apples to
apples) — NOT specifically a 09:30 bar, since forward-day triggers can
fire at any minute. A ticker-day with a single stray print counts as
covered; this is a known coarsening, stated in the report, not hidden.

MUST run inside apollo-execution (only container with Alpaca data creds).

Safety:
  - INSERT only. ON CONFLICT (ticker, bar_time) DO NOTHING.
  - Never UPDATE/DELETE/DDL.
  - Idempotent/resumable: re-derives "need" from mi_ep_alerts + the psv +
    mi_daily_closes + a live mi_intraday_bars coverage check at the START
    of every date, so a restart naturally shrinks the work list. A
    zero-bars resolved-file additionally skips names that are genuinely
    never going to have bars (delisted/halted/OTC), so those are not
    re-fetched forever across restarts.
  - INSERT statements are capped at MAX_ROWS_PER_INSERT records — a
    forward-day chunk can cover 500+ tickers (vs day-0's ~40/date), so a
    single unnest() insert could otherwise carry tens of thousands of
    rows; capping keeps each statement fast against a live prod table.

Usage (inside apollo-execution):
    python /tmp/backfill_forward_bars.py /tmp/_bt_population_capture.psv /tmp/backfill_fwd_progress.log
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from collections import defaultdict
from datetime import date as date_cls, datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, "/app")

from alpaca.data.requests import StockBarsRequest  # noqa: E402
from alpaca.data.timeframe import TimeFrame  # noqa: E402

from agents.market_intelligence.broker.alpaca_client import _get_data_client, get_data_feed  # noqa: E402
from agents.market_intelligence.db import get_pool  # noqa: E402

ET = ZoneInfo("America/New_York")
GAP_FLOOR = 9.0
MAX_SESSIONS_FORWARD = 20
CHUNK_SIZE_START = 200
MIN_CHUNK_SIZE = 10
SLEEP_BETWEEN_REQUESTS = 0.35
MAX_RETRIES = 4
MAX_SHRINKS_PER_SLICE = 2
MAX_ROWS_PER_INSERT = 25_000


def _log(msg: str, logf) -> None:
    line = f"{datetime.now(ET).isoformat()} {msg}"
    print(line, flush=True)
    logf.write(line + "\n")
    logf.flush()


def load_psv_anchors(path: str) -> set[tuple]:
    anchors = set()
    with open(path) as f:
        for line in f:
            line = line.rstrip("\n")
            if not line:
                continue
            parts = line.split("|")
            if len(parts) != 13:
                continue
            (trade_date, ticker, _open, _prev_close, _prev_volume, gap_pct_open,
             scanlog_max_gap, _in_open_seed, _in_scanlog_seed, _has_orb_bar,
             _has_any_bar, _prev_trade_date, _gap_days) = parts

            def to_f(s):
                try:
                    return float(s)
                except ValueError:
                    return None

            vals = [v for v in (to_f(gap_pct_open), to_f(scanlog_max_gap)) if v is not None]
            if not vals:
                continue
            if max(vals) >= GAP_FLOOR:
                d = datetime.strptime(trade_date, "%Y-%m-%d").date()
                anchors.add((d, ticker))
    return anchors


async def load_ep_alert_anchors(pool) -> set[tuple]:
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT DISTINCT ticker, alert_date FROM mi_ep_alerts")
    return {(r["alert_date"], r["ticker"]) for r in rows}


async def build_forward_need(pool, anchors: set[tuple]) -> dict:
    """Returns {trade_date: sorted[tickers]} — every (ticker, trade_date) pair
    inside sessions +1..+20 of ANY anchor, deduped across overlapping anchors."""
    dates = [d for d, _t in anchors]
    tickers = [t for _d, t in anchors]
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            WITH anchors AS (
              SELECT * FROM unnest($1::date[], $2::text[]) AS a(anchor_date, ticker)
            ),
            fwd AS (
              SELECT a.ticker, d.trade_date,
                     row_number() OVER (PARTITION BY a.ticker, a.anchor_date ORDER BY d.trade_date) AS day_idx
              FROM anchors a
              JOIN mi_daily_closes d ON d.ticker = a.ticker AND d.trade_date > a.anchor_date
            )
            SELECT DISTINCT ticker, trade_date FROM fwd WHERE day_idx <= $3
        """, dates, tickers, MAX_SESSIONS_FORWARD)
    by_date = defaultdict(list)
    for r in rows:
        by_date[r["trade_date"]].append(r["ticker"])
    return {d: sorted(set(ts)) for d, ts in by_date.items()}


def load_resolved_skip(path: str) -> set:
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


async def already_covered_any_bar(conn, d: date_cls, tickers: list[str]) -> set:
    """Tickers with >=1 existing bar on trade_date d, ANY minute (not
    specifically 09:30 — forward-day triggers fire at any time)."""
    if not tickers:
        return set()
    rows = await conn.fetch("""
        SELECT DISTINCT ticker FROM mi_intraday_bars
        WHERE ticker = ANY($1::text[])
          AND (bar_time AT TIME ZONE 'America/New_York')::date = $2::date
    """, tickers, d)
    return {r["ticker"] for r in rows}


async def insert_bars(conn, records: list[tuple]) -> tuple[int, int]:
    """records: (ticker, bar_time, open, high, low, close, volume, vwap).
    Returns (inserted, already_present). Splits into MAX_ROWS_PER_INSERT
    sub-batches — a forward-day chunk of 200 tickers can carry ~78k bar
    rows, too big for one unnest() statement against a live prod table."""
    if not records:
        return 0, 0
    inserted = 0
    already = 0
    for i in range(0, len(records), MAX_ROWS_PER_INSERT):
        batch = records[i:i + MAX_ROWS_PER_INSERT]
        cols = list(zip(*batch))
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
        inserted += len(rows)
        already += len(batch) - len(rows)
    return inserted, already


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
        except Exception as e:  # noqa: BLE001
            last_exc = e
            _log(f"    fetch attempt {attempt}/{MAX_RETRIES} failed for {len(tickers)} tickers: {str(e)[:200]}", logf)
            if attempt < MAX_RETRIES:
                await asyncio.sleep(delay)
                delay *= 2
    raise last_exc


async def fetch_slice(client, need, i, start, end, chunk_size, logf):
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
    log_path = sys.argv[2] if len(sys.argv) > 2 else "/tmp/backfill_fwd_progress.log"
    resolved_path = log_path + ".resolved.tsv"
    summary_path = log_path + ".summary.json"

    logf = open(log_path, "a")

    pool = await get_pool()

    psv_anchors = load_psv_anchors(pop_path)
    alert_anchors = await load_ep_alert_anchors(pool)
    anchors = psv_anchors | alert_anchors
    _log(f"anchors: psv(gap>={GAP_FLOOR})={len(psv_anchors)} mi_ep_alerts={len(alert_anchors)} "
         f"combined_union={len(anchors)}", logf)

    by_date = await build_forward_need(pool, anchors)
    dates = sorted(by_date.keys())
    total_pairs = sum(len(v) for v in by_date.values())
    _log(f"forward-session work list: {total_pairs} (ticker,date) pairs across {len(dates)} dates "
         f"(day_idx 1..{MAX_SESSIONS_FORWARD})", logf)

    resolved_skip = load_resolved_skip(resolved_path)
    if resolved_skip:
        _log(f"resuming: {len(resolved_skip)} (date,ticker) pairs already definitively resolved in a prior run", logf)

    client = _get_data_client()

    resolved_f = open(resolved_path, "a")
    debug_shape_logged = False

    grand_inserted = 0
    grand_already = 0
    grand_zero_bars = 0
    grand_skipped_covered = 0
    failed_dates = []
    zero_bars_samples = []

    t_start = datetime.now(ET)

    for d in dates:
        tickers = by_date[d]
        async with pool.acquire() as conn:
            covered = await already_covered_any_bar(conn, d, tickers)
        need = [t for t in tickers if t not in covered and (d, t) not in resolved_skip]
        already_resolved = sum(1 for t in tickers if (d, t) in resolved_skip)
        grand_skipped_covered += len(covered) + already_resolved
        if not need:
            _log(f"{d}: {len(tickers)} tickers — all covered ({len(covered)}) or already resolved ({already_resolved}), skip", logf)
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
            has_any = set()
            for t in chunk:
                bar_list = bar_data.get(t, []) or []
                if bar_list:
                    has_any.add(t)
                for b in bar_list:
                    if b.timestamp is None:
                        continue
                    records.append((
                        t, b.timestamp, float(b.open), float(b.high), float(b.low),
                        float(b.close), int(b.volume),
                        float(b.vwap) if getattr(b, "vwap", None) is not None else None,
                    ))
            zero_bars = [t for t in chunk if t not in has_any]

            async with pool.acquire() as conn:
                ins, already = await insert_bars(conn, records)
            date_inserted += ins
            date_already += already
            date_zero_bars += len(zero_bars)
            for t in zero_bars:
                resolved_f.write(f"{d}\t{t}\tzero_bars\n")
                if len(zero_bars_samples) < 25:
                    zero_bars_samples.append(f"{d} {t}")
            resolved_f.flush()

            _log(f"  chunk[{i}:{i+len(chunk)}] size={len(chunk)}: {len(records)} bars fetched, "
                 f"{ins} inserted, {already} already present, {len(zero_bars)} zero-bars tickers", logf)

            i += len(chunk)
            await asyncio.sleep(SLEEP_BETWEEN_REQUESTS)
            if chunk_size < CHUNK_SIZE_START:
                chunk_size = min(CHUNK_SIZE_START, chunk_size + 20)

        grand_inserted += date_inserted
        grand_already += date_already
        grand_zero_bars += date_zero_bars
        elapsed_so_far = (datetime.now(ET) - t_start).total_seconds()
        _log(f"{d}: DONE inserted={date_inserted} already={date_already} zero_bars={date_zero_bars}"
             f"{' [HAD PERMANENT CHUNK FAILURE]' if date_error else ''} (elapsed {elapsed_so_far:.0f}s)", logf)

    resolved_f.close()
    elapsed_total = (datetime.now(ET) - t_start).total_seconds()

    summary = {
        "anchors_psv": len(psv_anchors),
        "anchors_ep_alerts": len(alert_anchors),
        "anchors_combined": len(anchors),
        "work_list_pairs": total_pairs,
        "work_list_dates": len(dates),
        "grand_inserted_rows": grand_inserted,
        "grand_already_present_rows": grand_already,
        "grand_zero_bars_ticker_days": grand_zero_bars,
        "grand_skipped_already_covered": grand_skipped_covered,
        "failed_dates": failed_dates,
        "zero_bars_samples": zero_bars_samples,
        "elapsed_seconds": elapsed_total,
    }
    with open(summary_path, "a") as sf:
        sf.write(json.dumps(summary, default=str) + "\n")

    _log(f"=== RUN TOTAL: inserted={grand_inserted} already_present_rows={grand_already} "
         f"zero_bars_ticker_days={grand_zero_bars} skipped_already_covered={grand_skipped_covered} "
         f"failed_dates={len(failed_dates)} elapsed={elapsed_total:.0f}s ===", logf)
    if failed_dates:
        _log(f"FAILED DATES: {[fd['date'] for fd in failed_dates]}", logf)

    logf.close()


if __name__ == "__main__":
    asyncio.run(main())
