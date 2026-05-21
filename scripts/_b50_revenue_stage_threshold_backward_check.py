"""Backward check for revenue-stage threshold calibration (#50).

2026-05-20: ratcheted is_revenue_stage threshold from >0 to $5M on N=2
cases (IMVT, ROIV) during market hours. Rolled back to 0.01 via env
pending proper evidence. This script provides that evidence.

Method:
  1. Pull all HIGH EP alerts from last 60d (mi_ep_alerts)
  2. For each, fetch yfinance Ticker.calendar.Revenue Average
  3. Join to mi_ep_missed_outcomes for forward 5d/20d returns
  4. Categorize by Revenue Average band: $0 / $0-5M / $5-10M / $10-25M /
     $25-100M / $100M+
  5. Per band: count, % of all HIGH, average forward 5d return, %
     winners (>+5% fwd 5d)

Decision matrix:
  - If the $0-5M band has POSITIVE-edge winners → don't raise above $5M
    (we'd over-block real EPs)
  - If the $0-5M band is all losers/no-edge → safe to raise to $5M
  - Threshold ships only if the chosen band has N≥10 outcomes with
    clear delta vs higher bands.

Run: docker exec apollo-market python -m scripts._b50_revenue_stage_threshold_backward_check
"""
import asyncio
import logging
from datetime import date, timedelta
from collections import defaultdict

logging.basicConfig(level=logging.WARNING)


REVENUE_BANDS = [
    (0.0,          "  $0          (IMVT-class, true pre-revenue)"),
    (5_000_000,    "  $0-$5M      (ROIV-class, clinical-stage holding)"),
    (10_000_000,   "  $5-$10M     (small-cap revenue start)"),
    (25_000_000,   "  $10-$25M    (small-cap revenue)"),
    (100_000_000,  "  $25-$100M   (mid small-cap)"),
    (500_000_000,  "  $100-$500M  (mid-cap)"),
    (float("inf"), "  $500M+      (large-cap)"),
]


def band_for(rev_avg: float | None) -> str:
    if rev_avg is None:
        return "  N/A         (no yfinance data)"
    for upper, label in REVENUE_BANDS:
        if rev_avg < upper:
            return label
        if upper == 0.0 and rev_avg == 0.0:
            return label
    return REVENUE_BANDS[-1][1]


async def fetch_revenue_avg(ticker: str) -> float | None:
    """yfinance Revenue Average via Ticker.calendar. None on any failure."""
    try:
        import yfinance as yf
        loop = asyncio.get_event_loop()
        def _sync():
            cal = yf.Ticker(ticker).calendar
            if not isinstance(cal, dict):
                return None
            return cal.get("Revenue Average")
        rev = await loop.run_in_executor(None, _sync)
        return float(rev) if rev is not None else None
    except Exception:
        return None


async def main():
    from agents.market_intelligence.db import get_pool
    pool = await get_pool()

    # Pull HIGH alerts + compute forward returns from mi_daily_closes.
    # Methodology: gap-day open → close at d+5 / d+20. mi_ep_missed_outcomes
    # uses the same shape but only covers missed (un-entered) alerts; we
    # want EVERY HIGH alert (entered or not).
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            -- Exclude non-stock (ETFs, ETNs, warrants). Pre-2026-05-17
            -- P2.0b fix shipped, legacy ETF entries can pollute cohort.
            -- Hygiene rule from task #59 (2026-05-21).
            WITH alerts AS (
                SELECT a.ticker, a.alert_date, a.ep_score, a.catalyst_quality
                FROM mi_ep_alerts a
                LEFT JOIN mi_security_types st ON st.ticker = a.ticker
                WHERE a.alert_date >= CURRENT_DATE - INTERVAL '60 days'
                  AND a.score_tier = 'HIGH'
                  AND (st.security_type IS NULL
                       OR st.security_type IN ('CS', 'ADRC'))
            )
            SELECT a.ticker, a.alert_date, a.ep_score, a.catalyst_quality,
                   d0.open_price                      AS open_d0,
                   d5.close                           AS close_d5,
                   d20.close                          AS close_d20,
                   d5h.max_high_5d                    AS max_high_5d,
                   CASE WHEN d0.open_price > 0 AND d5.close IS NOT NULL
                        THEN (d5.close / d0.open_price - 1) * 100
                        ELSE NULL END AS ret_5d,
                   CASE WHEN d0.open_price > 0 AND d20.close IS NOT NULL
                        THEN (d20.close / d0.open_price - 1) * 100
                        ELSE NULL END AS ret_20d
            FROM alerts a
            LEFT JOIN mi_daily_closes d0
              ON d0.ticker = a.ticker AND d0.trade_date = a.alert_date
            LEFT JOIN LATERAL (
                SELECT close FROM mi_daily_closes
                WHERE ticker = a.ticker AND trade_date > a.alert_date
                ORDER BY trade_date ASC OFFSET 4 LIMIT 1
            ) d5 ON TRUE
            LEFT JOIN LATERAL (
                SELECT close FROM mi_daily_closes
                WHERE ticker = a.ticker AND trade_date > a.alert_date
                ORDER BY trade_date ASC OFFSET 19 LIMIT 1
            ) d20 ON TRUE
            LEFT JOIN LATERAL (
                SELECT MAX(high_price) AS max_high_5d FROM mi_daily_closes
                WHERE ticker = a.ticker AND trade_date > a.alert_date
                  AND trade_date <= a.alert_date + INTERVAL '7 days'
            ) d5h ON TRUE
            ORDER BY a.alert_date DESC
        """)

    print(f"Pulled {len(rows)} HIGH alerts from last 60d.")
    print()

    # Aggregate by band
    by_band: dict[str, list] = defaultdict(list)
    unique_tickers = set(r["ticker"] for r in rows)
    print(f"Fetching Revenue Average for {len(unique_tickers)} unique tickers...")
    rev_cache: dict[str, float | None] = {}
    for i, ticker in enumerate(sorted(unique_tickers)):
        if i > 0 and i % 20 == 0:
            print(f"  ... {i}/{len(unique_tickers)}")
        rev_cache[ticker] = await fetch_revenue_avg(ticker)
        await asyncio.sleep(0.05)  # polite throttle
    print()

    for r in rows:
        rev = rev_cache[r["ticker"]]
        band = band_for(rev)
        by_band[band].append({
            "ticker": r["ticker"],
            "alert_date": r["alert_date"],
            "rev_avg": rev,
            "ret_5d": r["ret_5d"],
            "ret_20d": r["ret_20d"],
            "max_high_5d": r["max_high_5d"],
        })

    # Report by band — uses shared helpers (#59 hygiene)
    from scripts._backward_check_utils import band_stats, format_band_row, format_header
    print("=" * 130)
    print(format_header())
    print("-" * 130)
    total = len(rows)
    for _, band_label in REVENUE_BANDS + [(None, "  N/A         (no yfinance data)")]:
        items = by_band.get(band_label, [])
        n = len(items)
        if n == 0:
            continue
        stats = band_stats([it["ret_5d"] for it in items])
        print(format_band_row(band_label, n, total, stats))
    print()

    # Show the tickers in low bands (decision-critical)
    print("=" * 90)
    print("LOW-REVENUE-BAND TICKERS (the ones a higher threshold would block):")
    print("=" * 90)
    for upper, band_label in REVENUE_BANDS[:3]:  # $0, $0-5M, $5-10M
        items = sorted(by_band.get(band_label, []), key=lambda x: x["alert_date"], reverse=True)
        if not items:
            continue
        print(f"\n{band_label}  ({len(items)} alerts)")
        for it in items[:15]:
            rev_disp = f"${it['rev_avg']:,.0f}" if it["rev_avg"] is not None else "N/A"
            ret_disp = f"{it['ret_5d']:+.1f}%" if it["ret_5d"] is not None else "—"
            print(f"    {it['alert_date']}  {it['ticker']:<6}  rev_avg={rev_disp:<14}  ret_5d={ret_disp}")
        if len(items) > 15:
            print(f"    ...{len(items) - 15} more")


if __name__ == "__main__":
    asyncio.run(main())
