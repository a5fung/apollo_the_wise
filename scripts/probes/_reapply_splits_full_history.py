"""One-shot: re-adjust the WHOLE stored history of every ticker that split since a date.

WHY (2026-09-24): until today a split re-fetch covered only 250 calendar days
(`splits_ingest.HISTORY_DAYS`), so every older row of a split ticker stayed in pre-split units.
While mi_daily_closes held ~13 months that hid in the oldest few months (QH's rows before
2025-11-10 read in the tens of thousands). The five-year reload of 2026-09-24 fills 2021-09 ->
2025-08-17 in TODAY's adjusted units, which turns each of those pockets into a series with two
cliffs. `splits_ingest` now re-fetches the whole stored history going forward; this repairs the
splits that already happened.

WHICH SPLITS: Polygon's split list since `--since` (default 2025-08-18, the first day of the
pre-reload history), read from Polygon rather than mi_splits because mi_splits only starts
2026-03-02. A split before `--since` needs nothing: the reload's rows and the rows we already
held are both post-split. Future-dated splits are skipped.

WHAT IT WRITES: Polygon's adjusted daily bars for the ticker's full stored window, through the
same writer the nightly split job uses (`upsert_ticker_history`). Re-writing a ticker that was
already right writes the same values. It must run AFTER the reload: the reload only fetches
dates missing from the WHOLE table, so a re-fetch that ran first would make those dates look
present and the reload would skip them for every other ticker.

USAGE (in the container):  python scripts/probes/_reapply_splits_full_history.py [--apply]
Default is a dry run: it lists the tickers and fetches no bars.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agents.market_intelligence.collector import et_today  # noqa: E402
from agents.market_intelligence.db import (  # noqa: E402
    get_pool, log_audit_event, upsert_ticker_history)
from agents.market_intelligence.splits_ingest import (  # noqa: E402
    _stored_history_days, fetch_splits, fetch_ticker_history)

PACE_SECONDS = 0.35
PROGRESS_EVERY = 100


async def _tickers_with_rows_before(splits: list[dict]) -> list[str]:
    """Tickers we hold, with at least one stored row before their split — the only ones a
    short re-fetch could have left in two scales. Derived from the table, not listed."""
    first_split: dict[str, date] = {}
    for s in splits:
        t, d = s.get("ticker"), s.get("execution_date")
        if not t or not d:
            continue
        d = date.fromisoformat(d) if isinstance(d, str) else d
        if d > et_today():
            continue
        first_split[t] = min(d, first_split.get(t, d))
    if not first_split:
        return []
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT c.ticker FROM mi_daily_closes c
               JOIN unnest($1::text[], $2::date[]) AS s(ticker, exec_date) USING (ticker)
               WHERE c.trade_date < s.exec_date
               GROUP BY c.ticker""",
            list(first_split), [first_split[t] for t in first_split])
    return sorted(r["ticker"] for r in rows)


async def main(since: date, apply: bool) -> None:
    splits = await fetch_splits(since)
    tickers = await _tickers_with_rows_before(splits)
    print(f"splits since {since}: {len(splits)} Polygon records")
    print(f"tickers we hold with rows before their split: {len(tickers)}")
    print(f"est. time at {PACE_SECONDS}s pacing: ~{len(tickers) * (PACE_SECONDS + 0.5) / 60:.0f} min")
    if not apply:
        print("DRY RUN — nothing fetched or written. First 40:", ", ".join(tickers[:40]))
        return
    ok = empty = failed = bars_written = 0
    for i, t in enumerate(tickers, 1):
        try:
            bars = await fetch_ticker_history(t, days=await _stored_history_days(t))
            if bars:
                bars_written += await upsert_ticker_history(t, bars)
                ok += 1
            else:
                empty += 1
        except Exception as e:  # one ticker must not stop the rest
            failed += 1
            print(f"  FAILED {t}: {e}")
        if i % PROGRESS_EVERY == 0 or i == len(tickers):
            print(f"  {i}/{len(tickers)}  ok={ok} empty={empty} failed={failed} bars={bars_written:,}")
        await asyncio.sleep(PACE_SECONDS)
    summary = (f"re-adjusted full stored history for {ok} of {len(tickers)} split tickers since "
               f"{since} ({bars_written:,} bars; {empty} returned no data; {failed} failed)")
    await log_audit_event("split_full_history_reapplied", summary)
    print(summary)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", type=date.fromisoformat, default=date(2025, 8, 18))
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    asyncio.run(main(a.since, a.apply))
