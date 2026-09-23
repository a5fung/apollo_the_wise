"""Backward check: Pradeep "rallying into catalyst" filter.

Trigger: Pradeep quote 2026-05-22 — "If a stock is rallying into catalyst
it has high probability of failure. Look at RKLB — sideways for months
pre-breakout, gaps slightly, did 50%+. Very few stocks meet that criteria."

Current methodology proxy: `breakdown["neglect"]` awards 0/8/15 points
based on price vs 52-week high (<0.5 / <0.7 / ≥0.7). This is a coarse
proxy — misses the edge case of "rallied +50% recently but still 40%
off ATH."

Question: does our HIGH cohort actually show worse outcomes for tickers
that rallied INTO the catalyst vs those that were sideways?

Method:
  1. Pull HIGH alerts last 60d (deduped, CS/ADRC-only per #59 hygiene)
  2. For each, compute pre-catalyst 20d return = close[alert_date-1] /
     close[alert_date-21] - 1 (the 20-trading-day window ending the day
     BEFORE the catalyst)
  3. Categorize by rally band: <-5% / -5 to +5% / +5 to +20% / +20 to +40% / +40%+
  4. Forward 5d return + win rate per band
  5. Decision matrix per `feedback_sample_size_discipline`: only ship a
     methodology change if a clearly-worse band has N≥10

Run: docker exec apollo-market python -m scripts._b77_pradeep_neglect_backward_check
"""
import asyncio
from collections import defaultdict


RALLY_BANDS = [
    (-5,  "  pre_20d <-5%       (declining)"),
    (5,   "  pre_20d -5 to +5%  (sideways — Pradeep RKLB-class)"),
    (20,  "  pre_20d +5 to +20% (modest uptrend)"),
    (40,  "  pre_20d +20 to +40% (rallying)"),
    (1e9, "  pre_20d +40%+      (strong rally into catalyst — Pradeep filter target)"),
]


def band_for(pct: float | None) -> str:
    if pct is None:
        return "  N/A                 (insufficient history)"
    for upper, label in RALLY_BANDS:
        if pct < upper:
            return label
    return RALLY_BANDS[-1][1]


async def main():
    from agents.market_intelligence.db import get_pool
    from scripts._backward_check_utils import band_stats, format_band_row, format_header
    pool = await get_pool()

    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            -- Hygiene per #59: dedup + ETF filter
            WITH alerts AS (
                SELECT DISTINCT ON (a.ticker, a.alert_date)
                       a.ticker, a.alert_date, a.ep_score, a.catalyst_quality
                FROM mi_ep_alerts a
                LEFT JOIN mi_security_types st ON st.ticker = a.ticker
                WHERE a.alert_date >= CURRENT_DATE - INTERVAL '60 days'
                  AND a.score_tier = 'HIGH'
                  AND (st.security_type IS NULL
                       OR st.security_type IN ('CS', 'ADRC'))
                ORDER BY a.ticker, a.alert_date, a.ep_score DESC NULLS LAST
            )
            SELECT a.ticker, a.alert_date, a.ep_score, a.catalyst_quality,
                   -- Pre-catalyst 20d return: close[d-1] / close[d-21] - 1
                   d_pre1.close                AS close_pre1,
                   d_pre21.close               AS close_pre21,
                   CASE WHEN d_pre21.close > 0 AND d_pre1.close IS NOT NULL
                        THEN (d_pre1.close / d_pre21.close - 1) * 100
                        ELSE NULL END          AS pre20d_pct,
                   -- Forward 5d return
                   d0.open_price               AS open_d0,
                   d5.close                    AS close_d5,
                   CASE WHEN d0.open_price > 0 AND d5.close IS NOT NULL
                        THEN (d5.close / d0.open_price - 1) * 100
                        ELSE NULL END          AS ret_5d
            FROM alerts a
            LEFT JOIN LATERAL (
                SELECT close FROM mi_daily_closes
                WHERE ticker = a.ticker AND trade_date < a.alert_date
                ORDER BY trade_date DESC LIMIT 1
            ) d_pre1 ON TRUE
            LEFT JOIN LATERAL (
                SELECT close FROM mi_daily_closes
                WHERE ticker = a.ticker AND trade_date < a.alert_date
                ORDER BY trade_date DESC OFFSET 20 LIMIT 1
            ) d_pre21 ON TRUE
            LEFT JOIN mi_daily_closes d0
                ON d0.ticker = a.ticker AND d0.trade_date = a.alert_date
            LEFT JOIN LATERAL (
                SELECT close FROM mi_daily_closes
                WHERE ticker = a.ticker AND trade_date > a.alert_date
                ORDER BY trade_date ASC OFFSET 4 LIMIT 1
            ) d5 ON TRUE
            ORDER BY a.alert_date DESC
        """)

    print(f"Pulled {len(rows)} HIGH alerts from last 60d (deduped, CS/ADRC only).")
    print()

    # Aggregate by rally band
    by_band: dict[str, list] = defaultdict(list)
    for r in rows:
        pre = r["pre20d_pct"]
        band = band_for(pre)
        by_band[band].append({
            "ticker": r["ticker"],
            "alert_date": r["alert_date"],
            "pre20d_pct": pre,
            "ret_5d": r["ret_5d"],
        })

    # Report
    print("=" * 130)
    print(format_header(label_width=60))
    print("-" * 130)
    total = len(rows)
    for _, band_label in RALLY_BANDS + [(None, "  N/A                 (insufficient history)")]:
        items = by_band.get(band_label, [])
        n = len(items)
        if n == 0:
            continue
        stats = band_stats([it["ret_5d"] for it in items])
        print(format_band_row(band_label, n, total, stats, label_width=60))
    print()

    # Detail view of "rallied into catalyst" bands (Pradeep's filter target)
    print("=" * 130)
    print("HIGH-RALLY TICKERS (pre_20d >= +20% — Pradeep would block these):")
    print("=" * 130)
    for upper, band_label in RALLY_BANDS[3:]:  # +20-40% and +40%+ bands
        items = sorted(by_band.get(band_label, []), key=lambda x: x["alert_date"], reverse=True)
        if not items:
            continue
        print(f"\n{band_label}  ({len(items)} alerts)")
        for it in items[:15]:
            pre = f"{it['pre20d_pct']:+.1f}%" if it["pre20d_pct"] is not None else "—"
            ret = f"{it['ret_5d']:+.1f}%" if it["ret_5d"] is not None else "—"
            print(f"    {it['alert_date']}  {it['ticker']:<6}  pre_20d={pre:<8}  ret_5d={ret}")
        if len(items) > 15:
            print(f"    ...{len(items) - 15} more")
    print()

    # Detail view of "sideways into catalyst" (Pradeep's target)
    print("=" * 130)
    print("SIDEWAYS / DECLINING TICKERS (pre_20d < +5% — Pradeep's RKLB-class):")
    print("=" * 130)
    for upper, band_label in RALLY_BANDS[:2]:  # <-5% and -5 to +5%
        items = sorted(by_band.get(band_label, []), key=lambda x: x["alert_date"], reverse=True)
        if not items:
            continue
        print(f"\n{band_label}  ({len(items)} alerts)")
        for it in items[:15]:
            pre = f"{it['pre20d_pct']:+.1f}%" if it["pre20d_pct"] is not None else "—"
            ret = f"{it['ret_5d']:+.1f}%" if it["ret_5d"] is not None else "—"
            print(f"    {it['alert_date']}  {it['ticker']:<6}  pre_20d={pre:<8}  ret_5d={ret}")
        if len(items) > 15:
            print(f"    ...{len(items) - 15} more")


if __name__ == "__main__":
    asyncio.run(main())
