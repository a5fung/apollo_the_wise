"""#579 — extend the strength-map ETF daily history so the spread alert can measure.

WHY: `evaluate_spread_crossing` needs `_SPREAD_ALERT_MIN_JUDGED` (240) judged days, and the chain
costs 51 bars before the first judged day (`_SPREAD_ALERT_WINDOW_BARS` 21 + `_SPREAD_ALERT_MOVE_SESSIONS`
30). So it needs 291 trading days; on 2026-09-15 all eight tickers held 275 (all starting 2025-08-11),
giving judged=224 — under the floor, so the 17:40 job SKIPPED both complexes silently and wrote no
audit row. Operator ruled 2026-09-15: backfill rather than wait ~16 trading days for a knife-edge 240.

⚠ STRICTLY ADDITIVE BY CONSTRUCTION. `upsert_ticker_history` is the SSoT writer for split
adjustments and DOES overwrite close+volume on conflict — so this filters every fetched bar to
dates STRICTLY EARLIER than the ticker's existing minimum before writing. Not one existing row is
touched, which keeps the blast radius to "older history appears" and off every other reader of
mi_daily_closes.

Read-only without --commit. No strategy, entry, exit, sizing or safeguard is touched (THE LINE);
the only consumer affected is an advisory Telegram.
"""
import asyncio, sys
from datetime import datetime, timezone

TICKERS = ["GLD", "SLV", "GDX", "GDXJ", "USO", "UNG", "XLE", "XOP"]
LOOKBACK_DAYS = 900          # ~620 trading days — ample margin over the 291 needed
COMMIT = "--commit" in sys.argv


async def main() -> int:
    from agents.market_intelligence.db import get_pool, upsert_ticker_history
    from agents.market_intelligence.splits_ingest import fetch_ticker_history

    pool = await get_pool()
    async with pool.acquire() as conn:
        before = {r["ticker"]: (r["n"], r["mn"]) for r in await conn.fetch(
            "SELECT ticker, count(*) AS n, min(trade_date) AS mn FROM mi_daily_closes "
            "WHERE ticker = ANY($1::text[]) GROUP BY ticker", TICKERS)}

    print(f"{'ticker':<7}{'have':>6}{'from':>13}{'fetched':>9}{'NEW(older)':>12}{'overlap_ok':>11}{'written':>9}")
    total_new = 0
    for tk in TICKERS:
        have, oldest = before.get(tk, (0, None))
        bars = await fetch_ticker_history(tk, days=LOOKBACK_DAYS)
        # ADDITIVE FILTER — strictly older than what we already hold.
        new = [b for b in bars
               if oldest is None
               or datetime.fromtimestamp(b["t"] / 1000, tz=timezone.utc).date() < oldest]
        # BASIS CHECK, before a single row is written. The fetch is adjusted=true, i.e. adjusted
        # to TODAY's split basis; the stored rows were adjusted at THEIR write time. If a split
        # had landed in between, the two segments would sit on different bases and the join would
        # be a silent discontinuity rather than a longer history. mi_splits shows none for these
        # eight — but that is a table, not a measurement, so compare the overlap directly.
        overlap = {datetime.fromtimestamp(b["t"] / 1000, tz=timezone.utc).date(): b["c"]
                   for b in bars if oldest is not None
                   and datetime.fromtimestamp(b["t"] / 1000, tz=timezone.utc).date() >= oldest}
        async with pool.acquire() as conn:
            stored = {r["trade_date"]: float(r["close"]) for r in await conn.fetch(
                "SELECT trade_date, close FROM mi_daily_closes WHERE ticker = $1", tk)}
        shared = sorted(set(overlap) & set(stored))
        drift = [d for d in shared if abs(overlap[d] - stored[d]) > 0.01 * max(stored[d], 1e-9)]
        if shared and drift:
            print(f"  ⛔ {tk}: {len(drift)} of {len(shared)} overlapping bars differ >1% between "
                  f"the fresh adjusted feed and stored history (e.g. {drift[0]}: "
                  f"feed {overlap[drift[0]]:.2f} vs stored {stored[drift[0]]:.2f}) — "
                  f"DIFFERENT ADJUSTMENT BASES. Refusing to write; this would be a discontinuity.")
            return 1
        written = 0
        if COMMIT and new:
            written = await upsert_ticker_history(tk, new)
        total_new += len(new)
        print(f"{tk:<7}{have:>6}{str(oldest):>13}{len(bars):>9}{len(new):>12}"
              f"{str(len(shared)) + ' same':>11}{written:>9}")

    print(f"\n{'COMMITTED' if COMMIT else 'DRY RUN — nothing written'}; "
          f"{total_new} older bar(s) identified across {len(TICKERS)} tickers.")
    if not COMMIT:
        print("Re-run with --commit to write.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
