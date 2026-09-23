"""ORB bar-1 wick-outlier backward-check (#122, 2026-05-26).

Per advisor 2026-05-26: before shipping a 1-second-bar persistence filter on
ORB entries, measure how often the bar-1 high is actually an outlier (wick)
that didn't hold — and whether those entries went on to stop out same-day.

Pulls historical ORB-triggered entries (mi_live_trades + mi_orb_shadow_trades)
from last `LOOKBACK_DAYS` days, joins to `mi_intraday_bars` to recover the
9:30 minute-bar OHLC, computes wick_ratio for the high, classifies outcome,
reports cohort size + signature counts.

Output: by-cohort breakdown so we can see if N is sufficient to ship a fix
OR whether this drops to data-gated review for accrual.

Run on PROD (where DB lives):
    docker exec apollo-market python -m scripts.orb_wick_outlier_backwardcheck
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import date, timedelta

# Allow running as `python scripts/...` (path tweak so package imports work).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.market_intelligence.db import get_pool  # noqa: E402

LOOKBACK_DAYS = 90
WICK_THRESHOLD = 0.70  # high − max(open, close) ≥ 70% of bar-1 range


async def main():
    pool = await get_pool()

    # ── A. Live-trade ORB entries (small cohort but ground-truth outcome) ───
    async with pool.acquire() as conn:
        live_rows = await conn.fetch(
            f"""
            WITH bars AS (
                SELECT ticker,
                       bar_time::date AS bar_date,
                       open  AS bar_open,
                       high  AS bar_high,
                       low   AS bar_low,
                       close AS bar_close
                FROM mi_intraday_bars
                WHERE bar_time::date > NOW()::date - INTERVAL '{LOOKBACK_DAYS} days'
                  AND EXTRACT(hour FROM bar_time AT TIME ZONE 'America/New_York') = 9
                  AND EXTRACT(minute FROM bar_time AT TIME ZONE 'America/New_York') = 30
            )
            SELECT lt.id, lt.ticker, lt.alert_date,
                   lt.orb_high, lt.orb_low, lt.entry_price, lt.stop_price,
                   lt.status, lt.total_pnl, lt.closed_at,
                   b.bar_open, b.bar_high, b.bar_low, b.bar_close
            FROM mi_live_trades lt
            LEFT JOIN bars b ON b.ticker = lt.ticker AND b.bar_date = lt.alert_date
            WHERE lt.alert_date > NOW()::date - INTERVAL '{LOOKBACK_DAYS} days'
              AND lt.orb_high IS NOT NULL
              AND lt.entry_price IS NOT NULL  -- only entries that actually fired
            ORDER BY lt.alert_date DESC
            """,
        )

        shadow_rows = await conn.fetch(
            f"""
            WITH bars AS (
                SELECT ticker,
                       bar_time::date AS bar_date,
                       open  AS bar_open,
                       high  AS bar_high,
                       low   AS bar_low,
                       close AS bar_close
                FROM mi_intraday_bars
                WHERE bar_time::date > NOW()::date - INTERVAL '{LOOKBACK_DAYS} days'
                  AND EXTRACT(hour FROM bar_time AT TIME ZONE 'America/New_York') = 9
                  AND EXTRACT(minute FROM bar_time AT TIME ZONE 'America/New_York') = 30
            )
            SELECT s.id, s.ticker, s.alert_date,
                   s.bar_size_minutes,
                   s.signal_type, s.shape_tag, s.score_tier,
                   s.orb_high, s.orb_low, s.entry_price, s.stop_price,
                   s.status, s.exits,
                   b.bar_open, b.bar_high, b.bar_low, b.bar_close
            FROM mi_orb_shadow_trades s
            LEFT JOIN bars b ON b.ticker = s.ticker AND b.bar_date = s.alert_date
            WHERE s.alert_date > NOW()::date - INTERVAL '{LOOKBACK_DAYS} days'
              AND s.bar_size_minutes = 1     -- bar-1 outlier only applies to 1-min
              AND s.orb_high IS NOT NULL
              AND s.entry_price IS NOT NULL
            ORDER BY s.alert_date DESC
            """,
        )

    print(f"\n=== ORB bar-1 wick-outlier backward-check (last {LOOKBACK_DAYS}d) ===\n")
    print(f"Live  cohort:   {len(live_rows)} entries")
    print(f"Shadow cohort:  {len(shadow_rows)} entries (1-min only)\n")

    for label, rows in (("LIVE", live_rows), ("SHADOW", shadow_rows)):
        if not rows:
            print(f"-- {label}: empty cohort, skipping --\n")
            continue

        analyzed = 0
        no_bar = 0
        wick_outliers = []     # wick_ratio >= WICK_THRESHOLD
        wick_then_stopout = [] # outliers that also stopped out same-day
        wick_winners = []      # outliers that did NOT stop out same-day

        for r in rows:
            if r["bar_open"] is None or r["bar_high"] is None:
                no_bar += 1
                continue
            analyzed += 1
            bar_high = float(r["bar_high"])
            bar_low = float(r["bar_low"])
            bar_open = float(r["bar_open"])
            bar_close = float(r["bar_close"])
            bar_range = bar_high - bar_low
            if bar_range <= 0:
                continue  # zero-range bar, separate edge case
            wick_size = bar_high - max(bar_open, bar_close)
            wick_ratio = wick_size / bar_range
            if wick_ratio < WICK_THRESHOLD:
                continue

            # Classify outcome
            stopped_out_same_day = False
            if label == "LIVE":
                if r["status"] == "closed" and r["total_pnl"] is not None and float(r["total_pnl"]) < 0:
                    if r["closed_at"] and r["alert_date"] and \
                       r["closed_at"].date() == r["alert_date"]:
                        stopped_out_same_day = True
            else:  # SHADOW
                if r["status"] in ("closed_stop", "stopped_out"):
                    exits = r.get("exits") or []
                    # exits is JSONB list of dicts; same-day if first exit on alert_date
                    if exits and isinstance(exits, list) and exits[0].get("exit_date"):
                        try:
                            from datetime import datetime as _dt
                            exit_d = _dt.fromisoformat(str(exits[0]["exit_date"])).date()
                            if exit_d == r["alert_date"]:
                                stopped_out_same_day = True
                        except Exception:
                            pass

            entry = {
                "ticker": r["ticker"],
                "alert_date": str(r["alert_date"]),
                "wick_ratio": round(wick_ratio, 3),
                "bar_high": bar_high, "bar_open": bar_open,
                "bar_close": bar_close, "bar_low": bar_low,
                "outcome": "STOP-OUT same-day" if stopped_out_same_day else "held/winner",
            }
            wick_outliers.append(entry)
            (wick_then_stopout if stopped_out_same_day else wick_winners).append(entry)

        print(f"-- {label} cohort breakdown --")
        print(f"  Analyzed (bar found):           {analyzed}")
        print(f"  No bar-1 data:                  {no_bar}")
        print(f"  Wick outliers (ratio ≥ {WICK_THRESHOLD}): {len(wick_outliers)} ({len(wick_outliers)/max(analyzed,1)*100:.1f}%)")
        print(f"     ↳ stopped out same-day:      {len(wick_then_stopout)}")
        print(f"     ↳ held / winner:             {len(wick_winners)}")
        print()

        if wick_then_stopout:
            print(f"  Outlier + same-day stop-out signature (top 15):")
            for e in wick_then_stopout[:15]:
                print(f"    {e['alert_date']} {e['ticker']:<6}  "
                      f"wick={e['wick_ratio']:.2f}  "
                      f"H={e['bar_high']:.2f} O={e['bar_open']:.2f} "
                      f"C={e['bar_close']:.2f} L={e['bar_low']:.2f}")
            print()

        if wick_winners:
            print(f"  Outlier but HELD (counter-evidence, top 10):")
            for e in wick_winners[:10]:
                print(f"    {e['alert_date']} {e['ticker']:<6}  "
                      f"wick={e['wick_ratio']:.2f}  "
                      f"H={e['bar_high']:.2f} O={e['bar_open']:.2f} "
                      f"C={e['bar_close']:.2f} L={e['bar_low']:.2f}")
            print()

    # ── Verdict ─────────────────────────────────────────────────────────────
    total_outlier_stopouts = 0
    for rows in (live_rows, shadow_rows):
        for r in rows:
            if r["bar_open"] is None or r["bar_high"] is None:
                continue
            br = float(r["bar_high"]) - float(r["bar_low"])
            if br <= 0:
                continue
            wr = (float(r["bar_high"]) - max(float(r["bar_open"]), float(r["bar_close"]))) / br
            if wr >= WICK_THRESHOLD:
                total_outlier_stopouts += 1

    print("=== VERDICT ===")
    print(f"Total wick-outlier-class entries across both cohorts: {total_outlier_stopouts}")
    if total_outlier_stopouts >= 10:
        print("→ N ≥ 10. Cohort sufficient to design a structural fix.")
        print("  Next: pick filter shape from data (wick_ratio cap? bar-1-close gate?).")
    else:
        print(f"→ N = {total_outlier_stopouts} < 10. INSUFFICIENT for ship.")
        print("  File as data-gated review with accrual condition.")
        print("  Don't ship 1-second-bar fetcher on hypothesized problem.")


if __name__ == "__main__":
    asyncio.run(main())
