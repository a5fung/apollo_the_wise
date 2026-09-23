"""#388 — build the COMPLETE Anticipation labeling fixture from the live DB (replaces the stale
static snapshot that omitted GH/HNGE + rode a hand-frozen 275-name allowlist).

Sweeps every CS/ADRC name (via the mi_security_types SSoT — get_common_stock_tickers, NOT a snapshotted
txt) that satisfies the RAW post-runup condition as-of --asof: a ≥15% advancing leg over a rolling
10-session window, above the price + liquidity floors. DELIBERATELY drops the today-compression gate
(`incl_max` in get_anticipation_universe) so still-basing names that aren't tight on the exact as-of
date — the GH/HNGE failure mode — still qualify ("find them while flat", operator 6/27). Dumps each
qualifier's daily OHLCV to the 7-field pipe fixture the worksheet (_anticipation_shortlist.py) reads.

HINDSIGHT DISCIPLINE: --asof is REQUIRED and should be the pre-breakout BASING date (~2026-06-19),
never today — GH/HNGE look prime only post-breakout; the model must see them while basing.

READ-ONLY. Runs where mi_daily_closes is reachable (market-agent container / prod DB):

  docker exec apollo-market python /app/scripts/build_anticipation_universe.py --asof 2026-06-19

Verifies GH + HNGE are in the candidate list (hard assert — the whole point of the rebuild).
"""
import argparse
import asyncio
from datetime import date

from agents.market_intelligence.db import get_pool, get_common_stock_tickers, get_anticipation_ohlcv

OUT_DEFAULT = "tests/fixtures/anticipation_universe_bars.psv"
# Names that MUST survive the rebuilt sweep (operator's known-good coils + the absences that triggered
# #388). Build fails loudly if any is missing → the board is rigged again.
_MUST_INCLUDE = ("GH", "HNGE")

# RAW post-runup candidate sweep — mirrors get_anticipation_universe MINUS the today-compression gate,
# CS-restricted to the passed allowlist. ($1=asof, $2=cs[], $3=price_min, $4=dvol_min, $5=runup_min)
_SQL = """
WITH p AS (SELECT $1::date AS d),
b AS (
    SELECT dc.ticker, dc.trade_date, dc.close, dc.volume,
           row_number() OVER (PARTITION BY dc.ticker ORDER BY dc.trade_date DESC) AS rn
    FROM mi_daily_closes dc
    CROSS JOIN p
    WHERE dc.trade_date <= p.d AND dc.trade_date > p.d - INTERVAL '60 days'
      AND dc.close > 0 AND dc.volume > 0
      AND dc.ticker = ANY($2)
),
w AS (SELECT * FROM b WHERE rn <= 25),
liq AS (
    SELECT ticker,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY close*volume) AS dvol_med,
           count(*) AS n
    FROM w GROUP BY ticker
),
roll AS (
    SELECT ticker, rn,
           max(close) OVER ww / NULLIF(min(close) OVER ww, 0) AS r10
    FROM w
    WINDOW ww AS (PARTITION BY ticker ORDER BY trade_date
                  ROWS BETWEEN 9 PRECEDING AND CURRENT ROW)
),
ru AS (SELECT ticker, max(r10) FILTER (WHERE rn <= 12) AS best_r10
       FROM roll GROUP BY ticker),
td AS (SELECT ticker, close AS last_close FROM w WHERE rn = 1)
SELECT liq.ticker, ru.best_r10 AS runup_ratio, liq.dvol_med, td.last_close
FROM liq
JOIN ru USING (ticker)
JOIN td USING (ticker)
WHERE liq.n >= 15
  AND td.last_close >= $3
  AND liq.dvol_med >= $4
  AND ru.best_r10 >= $5
ORDER BY ru.best_r10 DESC
"""


async def main(asof: date, price_min: float, dvol_min: float, runup_min: float,
               lookback_days: int, out: str):
    cs = sorted(await get_common_stock_tickers())
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(_SQL, asof, cs, price_min, dvol_min, runup_min)
    tickers = [r["ticker"] for r in rows]

    n_written = 0
    with open(out, "w", encoding="utf-8") as f:
        for tk in tickers:
            bars = await get_anticipation_ohlcv(tk, asof, lookback_days)
            for r in bars:
                f.write("|".join((
                    tk, str(r["trade_date"]),
                    f"{float(r['open_price']) if r['open_price'] is not None else float(r['close']):.4f}",
                    f"{float(r['high_price']):.4f}", f"{float(r['low_price']):.4f}",
                    f"{float(r['close']):.4f}",
                    f"{float(r['volume']) if r['volume'] is not None else 0.0:.0f}")) + "\n")
            n_written += 1

    print(f"wrote {n_written}/{len(cs)} CS post-runup candidates (runup ≥ {runup_min}, "
          f"as-of {asof.isoformat()}) → {out}")
    present = set(tickers)
    missing = [t for t in _MUST_INCLUDE if t not in present]
    if missing:
        raise SystemExit(
            f"❌ #388 FAIL — known-good coil(s) {missing} ABSENT from the rebuilt universe as-of "
            f"{asof.isoformat()}. The board is still rigged. Check the as-of date (must be the BASING "
            f"window, pre-breakout), the CS classification of {missing} in mi_security_types, and the "
            f"runup/liquidity floors.")
    print(f"✅ verified present: {', '.join(_MUST_INCLUDE)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--asof", type=date.fromisoformat, required=True,
                    help="basing as-of date YYYY-MM-DD (pre-breakout, ~2026-06-19 — hindsight discipline)")
    ap.add_argument("--runup-min", type=float, default=1.15)
    ap.add_argument("--price-min", type=float, default=5.0)
    ap.add_argument("--dvol-min", type=float, default=20_000_000.0)
    ap.add_argument("--lookback-days", type=int, default=340)
    ap.add_argument("--out", type=str, default=OUT_DEFAULT)
    args = ap.parse_args()
    asyncio.run(main(args.asof, args.price_min, args.dvol_min, args.runup_min,
                     args.lookback_days, args.out))
