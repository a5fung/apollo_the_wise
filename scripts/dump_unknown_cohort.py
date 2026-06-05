#!/usr/bin/env python3
"""Dump the production UNKNOWN / coverage-gap EP cohort as model-eval test cases.

READ-ONLY (SELECT only). The "unknown" category is the REAL-WORLD version of the RUM
sourcing-confab probe: actual production cases where sourcing/classification could NOT
confirm a catalyst. These are the hard cases a stronger model/tier should be tested
against in the quarterly model review (docs/model_selection_baseline.md).

Three forward-growing signals (any one flags a row), see [[feedback_label_unknown_not_none]]:
  1. catalyst_type = 'unknown'      — classifier couldn't name a fire type (#155/#190; fwd from ~5/30)
  2. fire_status non-fire           — couldn't confirm a fire: unknown / pre_catalyst_anticipation
                                      / no_fire_confirmed / real_unknown (#201; fwd from 6/5)
  3. catalyst TEXT disclaimer       — Perplexity returned "not clearly identified" / "no clear
                                      catalyst" (the sourcing-MISS signal; available historically;
                                      same markers as collector.strip_perplexity_disclaimer)

ADJUDICATION DISCIPLINE (the RUM lesson — see model_selection_baseline.md Probe Library):
each unknown is a CANDIDATE probe, not a labeled one. Before scoring a model on it, adjudicate
against the actual filing (collector.get_sec_recent_filings) / primary source:
  - TRUE unknown (no real catalyst)      -> a model that stays "unknown" is CORRECT.
  - MISSED catalyst (real, sourcing gap) -> a model/tier that surfaces the real catalyst
                                            (verified vs filing, NOT keyword match) is a WIN.
A keyword-"FOUND" is never a find on its own (RUM: cheap tiers confabulated "Together AI").

Usage (server, read-only):
  docker exec apollo-market python scripts/dump_unknown_cohort.py [--days 120] [--json /tmp/unknown_cohort.json]
The JSON is the eval feed (ticker/date), consumed by scripts/eval_sourcing_perplexity.py
(date-pinned re-source on candidate models) + the quarterly review (#207).
"""
import argparse
import asyncio
import json

DISCLAIMER_SQL = (
    "catalyst ILIKE '%not clearly identified%' OR "
    "catalyst ILIKE '%no clear%catalyst%' OR "
    "catalyst ILIKE '%no fresh%catalyst%' OR "
    "catalyst ILIKE '%no specific news%' OR "
    "catalyst ILIKE '%not driven by a%clear%' OR "
    "catalyst ILIKE '%could not%verify%' OR "
    "catalyst ILIKE '%can%t verify%'"
)

# non-fire fire_status values (#201 NON_FIRE_TYPES + the post-mortem unknown labels)
NON_FIRE = ("unknown", "pre_catalyst_anticipation", "no_fire_confirmed", "real_unknown")


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=120, help="lookback window (default 120)")
    ap.add_argument("--json", default="", help="also write the cohort to this JSON path")
    args = ap.parse_args()

    from agents.market_intelligence.db import get_pool
    pool = await get_pool()
    nf = ",".join(f"'{v}'" for v in NON_FIRE)
    sql = f"""
        SELECT ticker, alert_date, catalyst_quality, catalyst_type, fire_status,
               left(translate(coalesce(catalyst,''), chr(10)||chr(13), '  '), 240) AS catalyst_lead,
               (catalyst_type = 'unknown')                       AS f_type_unknown,
               (fire_status IN ({nf}))                           AS f_fire_nonfire,
               ({DISCLAIMER_SQL})                                AS f_sourcing_miss
        FROM mi_ep_alerts
        WHERE alert_date >= current_date - ($1)::int
          AND (catalyst_type = 'unknown'
               OR fire_status IN ({nf})
               OR ({DISCLAIMER_SQL}))
        ORDER BY alert_date DESC, ticker
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, args.days)

    print(f"UNKNOWN / coverage-gap EP cohort — last {args.days}d — N={len(rows)} candidate probes")
    print("(each needs filing-adjudication before scoring a model; see header + baseline doc)\n")
    hdr = f"{'TICKER':6} {'DATE':11} {'QUAL':12} {'TYPE':14} {'FIRE':16} flags"
    print(hdr); print("-" * len(hdr))
    feed = []
    for r in rows:
        flags = "".join([
            "T" if r["f_type_unknown"] else "-",
            "F" if r["f_fire_nonfire"] else "-",
            "S" if r["f_sourcing_miss"] else "-",
        ])
        print(f"{r['ticker']:6} {str(r['alert_date']):11} "
              f"{str(r['catalyst_quality'] or ''):12} {str(r['catalyst_type'] or ''):14} "
              f"{str(r['fire_status'] or ''):16} {flags}")
        print(f"       « {r['catalyst_lead']} »")
        feed.append({
            "ticker": r["ticker"], "date": str(r["alert_date"]),
            "catalyst_quality": r["catalyst_quality"], "catalyst_type": r["catalyst_type"],
            "fire_status": r["fire_status"],
            "signals": {"type_unknown": r["f_type_unknown"],
                        "fire_nonfire": r["f_fire_nonfire"],
                        "sourcing_miss": r["f_sourcing_miss"]},
        })

    print("\nflags: T=catalyst_type unknown · F=fire_status non-fire · S=sourcing-miss disclaimer text")
    if args.json:
        with open(args.json, "w") as f:
            json.dump(feed, f, indent=2)
        print(f"\nwrote {len(feed)} cases -> {args.json} (eval feed for eval_sourcing_perplexity.py)")


if __name__ == "__main__":
    asyncio.run(main())
