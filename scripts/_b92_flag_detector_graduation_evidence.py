"""Backward check: flag detector COILED→TRIGGERED graduation evidence.

Trigger: 2026-05-23 #92 first graduation review. Evaluates whether the
continuation-flag detector (shadow phase since 2026-05-04) earns
graduation to paper trading. Initial finding: NO — forward returns
DECREASE as stage advances toward TRIGGERED.

Method:
  1. For each (ticker, scan_date, stage) row in mi_flag_candidates,
     compute 5d and 10d forward returns from scan_date close
  2. Aggregate by stage; report avg, median, winner rate at +5% and +10%
  3. Decision matrix:
     - TRIGGERED N>=30 AND avg ret_10d > +3% AND wr_5pct_10d > 35%:
       PROMOTE to paper phase
     - TRIGGERED N>=30 AND signal still negative: detector needs
       revision (criteria too aggressive, regime mismatch, etc.)
     - TRIGGERED N<30: continue observing

Current state (2026-05-23, ~19 days of data since 5/04 shadow ship,
entry = D+1 open per realistic-entry fix):

  Stage      | N    | avg 10d  | WR_5pct  | comment
  -----------+------+----------+----------+---------
  TRIGGERED  |   5  |  -2.66%  |    0.0%  | N too small + signal weak
  COILED     |  23  |  -2.27%  |   26.1%  | below baseline
  TIGHTENING | 104  |  +1.73%  |   28.8%  | ★ best stage, gets better
                                            with realistic entry
  WATCH      | ~400 | ~ -2%    | ~25%     | baseline floor

Bright spot: TIGHTENING shows positive 10d returns. Matches Qullamaggie
"enter the base before breakout" framing. Worth a separate alert-class
surface (NOT entry-class — N=198 too many to trade). Cross-reference
to ADR 0004 §4 (Stocks in Play) as a candidate source_detector if
TIGHTENING-tier signal survives N>=30 evaluation.

Run: docker exec apollo-market python -m scripts._b92_flag_detector_graduation_evidence
"""
import asyncio
from collections import defaultdict


async def main():
    from agents.market_intelligence.db import get_pool
    pool = await get_pool()

    print("=" * 100)
    print("#92 Flag detector graduation evidence — shadow-phase telemetry")
    print("=" * 100)
    print()

    # ENTRY CONVENTION (2026-05-23 user-caught look-ahead bug fixed):
    # Flag scan runs at 5:25 PM ET — AFTER scan_date's close. So entry
    # cannot fire on scan_date itself; the earliest realistic entry is
    # the NEXT trading day's open. Using D+1 open as entry corrects for
    # the look-ahead bias that the original close-to-close calc had.
    #
    # The bias varied by stage. TRIGGERED stocks fade ~2% overnight on
    # average (sellers-into-strength after breakout-day close); COILED
    # gaps up slightly (+0.4%); TIGHTENING fades slightly (-0.7%). Net:
    # realistic D+1-open returns are different from D-close drift by
    # +1.85% (TRIGGERED), -0.32% (COILED), +0.59% (TIGHTENING). Honest
    # entry-aware metric per feedback_validate_metric_before_decision.
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            WITH stage_rows AS (
                SELECT DISTINCT ON (ticker, scan_date)
                       ticker, scan_date, stage
                FROM mi_flag_candidates
                WHERE scan_date <= CURRENT_DATE - INTERVAL '7 days'
                  AND stage IN ('TRIGGERED', 'COILED', 'TIGHTENING', 'WATCH')
                ORDER BY ticker, scan_date, stage
            )
            SELECT s.ticker, s.scan_date, s.stage,
                   -- Entry = D+1 open (first trading day after classification)
                   CASE WHEN d_entry.open_price > 0 AND d5.close IS NOT NULL
                        THEN (d5.close / d_entry.open_price - 1) * 100 END AS ret_5d,
                   CASE WHEN d_entry.open_price > 0 AND d10.close IS NOT NULL
                        THEN (d10.close / d_entry.open_price - 1) * 100 END AS ret_10d
            FROM stage_rows s
            -- d_entry: next trading day's open (realistic entry)
            LEFT JOIN LATERAL (
                SELECT open_price FROM mi_daily_closes
                WHERE ticker = s.ticker AND trade_date > s.scan_date
                ORDER BY trade_date ASC LIMIT 1
            ) d_entry ON TRUE
            -- d5: 5 trading days after entry (so OFFSET 4 from D+1 = D+5 total)
            LEFT JOIN LATERAL (
                SELECT close FROM mi_daily_closes
                WHERE ticker = s.ticker AND trade_date > s.scan_date
                ORDER BY trade_date ASC OFFSET 4 LIMIT 1
            ) d5 ON TRUE
            -- d10: 10 trading days after entry
            LEFT JOIN LATERAL (
                SELECT close FROM mi_daily_closes
                WHERE ticker = s.ticker AND trade_date > s.scan_date
                ORDER BY trade_date ASC OFFSET 9 LIMIT 1
            ) d10 ON TRUE
        """)

    by_stage: dict[str, list] = defaultdict(list)
    for r in rows:
        by_stage[r["stage"]].append({
            "ret_5d": r["ret_5d"],
            "ret_10d": r["ret_10d"],
        })

    print(f"Total observations: {len(rows)} rows across "
          f"{len({(r['ticker'], r['scan_date']) for r in rows})} unique (ticker, scan_date) pairs")
    print()

    print(f"{'STAGE':<11} {'N_5d':>6} {'avg_5d':>10} {'WR≥+5% 5d':>12} "
          f"{'N_10d':>6} {'avg_10d':>10} {'WR≥+5% 10d':>13} {'WR≥+10% 10d':>13}")
    print("-" * 90)

    stage_order = ["TRIGGERED", "COILED", "TIGHTENING", "WATCH"]
    summary = {}
    for stage in stage_order:
        items = by_stage.get(stage, [])
        n_5d = [it["ret_5d"] for it in items if it["ret_5d"] is not None]
        n_10d = [it["ret_10d"] for it in items if it["ret_10d"] is not None]
        if not n_5d and not n_10d:
            print(f"{stage:<11} (no data)")
            continue
        avg_5d = sum(n_5d) / len(n_5d) if n_5d else 0
        avg_10d = sum(n_10d) / len(n_10d) if n_10d else 0
        win5_5d = sum(1 for v in n_5d if v >= 5)
        win5_10d = sum(1 for v in n_10d if v >= 5)
        win10_10d = sum(1 for v in n_10d if v >= 10)
        wr5_5d = 100 * win5_5d // len(n_5d) if n_5d else 0
        wr5_10d = 100 * win5_10d // len(n_10d) if n_10d else 0
        wr10_10d = 100 * win10_10d // len(n_10d) if n_10d else 0
        print(f"{stage:<11} {len(n_5d):>6} {avg_5d:>+9.2f}% {win5_5d}/{len(n_5d):<3} ({wr5_5d:>2}%)   "
              f"{len(n_10d):>6} {avg_10d:>+9.2f}% {win5_10d}/{len(n_10d):<3} ({wr5_10d:>2}%)   "
              f"{win10_10d}/{len(n_10d):<3} ({wr10_10d:>2}%)")
        summary[stage] = {"n_10d": len(n_10d), "avg_10d": avg_10d, "wr5_10d": wr5_10d}

    print()
    print("=" * 100)
    print("DECISION GATE — flag detector shadow → paper graduation")
    print("=" * 100)
    triggered = summary.get("TRIGGERED", {"n_10d": 0})
    n_t = triggered.get("n_10d", 0)
    avg_t = triggered.get("avg_10d", 0)
    wr_t = triggered.get("wr5_10d", 0)

    if n_t < 30:
        print(f"→ N<30 ({n_t} TRIGGERED settled 10d). CONTINUE OBSERVING in shadow.")
        print(f"  Current rate ≈ 5-8 TRIGGERED/month — N≥30 needs ~3-6 more months.")
        print(f"  Re-evaluate via this script monthly via quarterly_review.py.")
    elif avg_t > 3 and wr_t > 35:
        print(f"→ PROMOTE to paper. TRIGGERED N={n_t}, avg={avg_t:+.2f}%, WR={wr_t}%.")
        print(f"  Design paper-phase implementation: entry trigger, sizing, stop placement.")
    else:
        print(f"→ TRIGGERED at N≥30 but signal weak (avg={avg_t:+.2f}%, WR={wr_t}%).")
        print(f"  Detector NEEDS REVISION before graduation. Investigation areas:")
        print(f"    - COILED/TRIGGERED criteria may be too aggressive")
        print(f"    - Regime mismatch (continuation flags underperform in choppy markets)")
        print(f"    - Forward-window mismatch (10d may be too short for continuation hold)")
        print(f"    - Consider TIGHTENING × cohort overlap as more selective signal")
    print()

    # TIGHTENING bright-spot callout
    tightening = summary.get("TIGHTENING", {"n_10d": 0})
    if tightening["n_10d"] >= 50:
        print(f"BRIGHT-SPOT: TIGHTENING N={tightening['n_10d']} shows "
              f"avg_10d={tightening['avg_10d']:+.2f}%, WR={tightening['wr5_10d']}%.")
        print(f"  Worth investigating as separate alert-class surface "
              f"(NOT entry-class — too many candidates). Matches Qullamaggie")
        print(f"  'enter the base before breakout' framing. Cross-reference")
        print(f"  ADR 0004 §4 as candidate source_detector if N≥30 cohort holds.")
    print()
    print("Cross-references:")
    print("  - feedback_methodology_insights_need_periodic_revalidation.md")
    print("  - data_gated_reviews.yaml::flag_detector_graduation_evidence_n30")
    print("  - ADR 0004 §7 Phase 4 (shadow detectors) — flag detector migration")
    print("    into mi_stocks_in_play awaits this signal validation")


if __name__ == "__main__":
    asyncio.run(main())
