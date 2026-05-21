"""Backward check for ATR-normalized gap scoring (#53, IBRX 2026-05-20 trigger).

Current scoring uses absolute gap_pct thresholds:
  gap_pct >= 20 → 25 points
  gap_pct >= 15 → 20 points
  gap_pct >= 10 → 15 points
  gap_pct >= 8  → 10 points

IBRX 2026-05-20 highlighted the issue: gap 10.18% on ATR-14 of 7.43%
= gap/ATR ratio 1.37x. Chart looks normal-range, not an institutional
buying gap. The scoring system can't tell IBRX (1.37x ATR) from a
mega-cap gapping 10% on 1.5% ATR (6.7x ATR — extraordinary).

Method:
  1. Pull HIGH alerts last 60d
  2. Compute ATR-14% (true-range / prev-close) from mi_daily_closes
     using 14 trading days BEFORE alert_date (no look-ahead)
  3. Compute gap/ATR ratio per alert
  4. Compute forward 5d return from mi_daily_closes
  5. Categorize by gap/ATR bands: <1.5x / 1.5-2x / 2-3x / 3-5x / 5x+
  6. Per band: count, avg fwd 5d, win rate (≥+5%)

Decision matrix:
  - Low-ratio band (<1.5x) has materially WORSE outcomes than high-ratio
    bands → ATR normalization adds signal; methodology-defensible to ship
  - Low-ratio band similar or BETTER → absolute gap thresholds are fine;
    don't recalibrate (today's IBRX observation may be one-off)

Run: docker exec apollo-market python -m scripts._b53_atr_normalized_gap_backward_check
"""
import asyncio
import logging
from collections import defaultdict

logging.basicConfig(level=logging.WARNING)


GAP_ATR_BANDS = [
    (1.5,  "  gap/ATR <1.5x   (IBRX-class — normal day's range)"),
    (2.0,  "  gap/ATR 1.5-2x  (modest deviation)"),
    (3.0,  "  gap/ATR 2-3x    (notable)"),
    (5.0,  "  gap/ATR 3-5x    (strong)"),
    (float("inf"), "  gap/ATR 5x+     (extraordinary)"),
]


def band_for(ratio: float | None) -> str:
    if ratio is None:
        return "  N/A             (insufficient history)"
    for upper, label in GAP_ATR_BANDS:
        if ratio < upper:
            return label
    return GAP_ATR_BANDS[-1][1]


async def main():
    from agents.market_intelligence.db import get_pool
    pool = await get_pool()

    async with pool.acquire() as conn:
        # Pull HIGH alerts + ATR-14 computed from 14 trading days before
        # alert_date (no look-ahead) + forward 5d return.
        rows = await conn.fetch("""
            WITH alerts AS (
                -- Hygiene rules (#59 2026-05-21):
                -- (1) Exclude non-stock (ETFs, ETNs, warrants). Pre-P2.0b fix
                --     5/17 leaked USAX/USGG-class alerts.
                -- (2) DISTINCT ON (ticker, alert_date) — same EP fired multiple
                --     times in a session creates duplicate rows. Dedup keeps the
                --     first (highest ep_score) row per ticker+date.
                SELECT DISTINCT ON (a.ticker, a.alert_date)
                       a.ticker, a.alert_date, a.gap_pct, a.ep_score, a.catalyst_quality
                FROM mi_ep_alerts a
                LEFT JOIN mi_security_types st ON st.ticker = a.ticker
                WHERE a.alert_date >= CURRENT_DATE - INTERVAL '60 days'
                  AND a.score_tier = 'HIGH'
                  AND a.gap_pct IS NOT NULL
                  AND (st.security_type IS NULL
                       OR st.security_type IN ('CS', 'ADRC'))
                ORDER BY a.ticker, a.alert_date, a.ep_score DESC NULLS LAST
            ),
            atr_bars AS (
                SELECT a.ticker, a.alert_date,
                       d.trade_date,
                       d.high_price, d.low_price, d.close,
                       LAG(d.close) OVER (PARTITION BY a.ticker, a.alert_date
                                          ORDER BY d.trade_date) AS prev_close
                FROM alerts a
                JOIN mi_daily_closes d ON d.ticker = a.ticker
                WHERE d.trade_date < a.alert_date
                  AND d.trade_date >= a.alert_date - INTERVAL '30 days'
            ),
            atr_calc AS (
                SELECT ticker, alert_date,
                       AVG(
                           GREATEST(
                               high_price - low_price,
                               ABS(high_price - prev_close),
                               ABS(low_price - prev_close)
                           ) / NULLIF(prev_close, 0) * 100
                       ) AS atr14_pct
                FROM (
                    SELECT *,
                           ROW_NUMBER() OVER (PARTITION BY ticker, alert_date
                                              ORDER BY trade_date DESC) AS rn
                    FROM atr_bars
                    WHERE prev_close IS NOT NULL
                ) sub
                WHERE rn <= 14
                GROUP BY ticker, alert_date
            )
            SELECT a.ticker, a.alert_date, a.gap_pct, a.ep_score,
                   atr.atr14_pct,
                   d0.open_price AS open_d0,
                   d5.close      AS close_d5,
                   CASE WHEN d0.open_price > 0 AND d5.close IS NOT NULL
                        THEN (d5.close / d0.open_price - 1) * 100
                        ELSE NULL END AS ret_5d
            FROM alerts a
            LEFT JOIN atr_calc atr
              ON atr.ticker = a.ticker AND atr.alert_date = a.alert_date
            LEFT JOIN mi_daily_closes d0
              ON d0.ticker = a.ticker AND d0.trade_date = a.alert_date
            LEFT JOIN LATERAL (
                SELECT close FROM mi_daily_closes
                WHERE ticker = a.ticker AND trade_date > a.alert_date
                ORDER BY trade_date ASC OFFSET 4 LIMIT 1
            ) d5 ON TRUE
            ORDER BY a.alert_date DESC
        """)

    print(f"Pulled {len(rows)} HIGH alerts from last 60d.")
    print()

    # Aggregate by gap/ATR band
    by_band: dict[str, list] = defaultdict(list)
    for r in rows:
        gap = r["gap_pct"]
        atr = r["atr14_pct"]
        ratio = (gap / atr) if (gap is not None and atr and atr > 0) else None
        band = band_for(ratio)
        by_band[band].append({
            "ticker": r["ticker"],
            "alert_date": r["alert_date"],
            "gap_pct": gap,
            "atr14_pct": atr,
            "ratio": ratio,
            "ep_score": r["ep_score"],
            "ret_5d": r["ret_5d"],
        })

    # Report — uses shared helpers (#59 hygiene)
    from scripts._backward_check_utils import band_stats, format_band_row, format_header
    print("=" * 130)
    print(format_header())
    print("-" * 130)
    total = len(rows)
    for _, band_label in GAP_ATR_BANDS + [(None, "  N/A             (insufficient history)")]:
        items = by_band.get(band_label, [])
        n = len(items)
        if n == 0:
            continue
        stats = band_stats([it["ret_5d"] for it in items])
        print(format_band_row(band_label, n, total, stats))
    print()

    # Detailed view of low-ratio band (the ones a normalization would block/downscore)
    print("=" * 100)
    print("LOW-RATIO TICKERS (gap/ATR < 1.5x — IBRX-class):")
    print("=" * 100)
    items = sorted(by_band.get(GAP_ATR_BANDS[0][1], []),
                   key=lambda x: x["alert_date"], reverse=True)
    if items:
        print(f"\nTotal: {len(items)} alerts")
        for it in items[:25]:
            r = f"{it['ratio']:.2f}x" if it['ratio'] is not None else "—"
            atr_disp = f"{it['atr14_pct']:.2f}%" if it['atr14_pct'] else "—"
            gap = f"{it['gap_pct']:.1f}%" if it['gap_pct'] else "—"
            ret_disp = f"{it['ret_5d']:+.1f}%" if it['ret_5d'] is not None else "—"
            print(f"    {it['alert_date']}  {it['ticker']:<6}  gap={gap:<7}  ATR={atr_disp:<7}  ratio={r:<7}  ret_5d={ret_disp}")
        if len(items) > 25:
            print(f"    ...{len(items) - 25} more")
    else:
        print("  (none in cohort)")


if __name__ == "__main__":
    asyncio.run(main())
