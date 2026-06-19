#!/usr/bin/env python3
"""#343 chart-vision SHADOW VERIFY-LIVE — run INSIDE the market-agent container:

    docker exec <market-container> python scripts/_verify_chart_axis_shadow.py --cohort-only
    docker exec <market-container> python scripts/_verify_chart_axis_shadow.py --run

SHADOW / read-only telemetry (writes only mi_audit_log + delta PNGs, never trade state) — acceptable
via docker exec. The first real cron fire is Mon 6/22 (Fri 6/19 is a holiday); this proves the
machinery TODAY so "Done = VERIFIED-LIVE" doesn't slip 4 days. Any delta emitted before 2026-06-19
is UNCOUNTED by the registry predicate (created_at >= '2026-06-19'), so a 6/18 run can't pollute the
decision N — a clean same-day machinery check with zero downside (advisor 6/18).

--cohort-only [--date D] : print the HIGH+MODERATE shadow cohort (get_chart_axis_shadow_cohort SQL)
                 for D (default et_today()) + render-check each. ZERO Anthropic spend — proves the
                cohort selection + the prior-day chart render only.
--run [--date D]         : run the REAL shadow core (_run_chart_axis_shadow) once for D (grades B/C
                ×3, emits the audit rows), then SELECT D's chart_axis_shadow_* events. Point --date
                at the last real trading day to exercise the emit path on a holiday; graded markers
                are UNCOUNTED by the registry (only `_delta` counts), so this is a safe integration
                check. A 0-cohort day is a legitimate clean no-op.
"""
import argparse
import asyncio
import sys
from datetime import date


def _resolve_date(arg):
    if arg:
        return date.fromisoformat(arg)
    from agents.market_intelligence.collector import et_today
    return et_today()


async def _cohort_only(d):
    from agents.market_intelligence import chart_axis as ca
    from agents.market_intelligence.db import (
        get_chart_axis_shadow_cohort, get_chart_axis_shadow_processed_tickers,
    )
    cohort = await get_chart_axis_shadow_cohort(d, limit=8)
    already = await get_chart_axis_shadow_processed_tickers(d)
    print(f"== chart-axis shadow cohort {d} ==  {len(cohort)} candidate(s), "
          f"{len(already)} already processed")
    for r in cohort:
        png, n_daily = await ca.render_prior_day_chart(r["ticker"], r["alert_date"])
        flag = "✓chart" if png else f"✗no-chart(n_daily={n_daily})"
        mark = " [processed]" if r["ticker"] in already else ""
        print(f"  {r['ticker']:6} {r['alert_date']}  floor={r['floor_tier']:8} "
              f"score={r['score_tier']:8} ep={r['ep_score']}  {flag}{mark}")
    if not cohort:
        print("  (empty — no HIGH/MODERATE EP alerts; the EOD job is a clean no-op)")


async def _run(d):
    from agents.market_intelligence.db import get_audit_log
    from agents.market_intelligence.scheduler import _run_chart_axis_shadow
    print(f"== running _run_chart_axis_shadow({d}) once (real grade calls) ==")
    await _run_chart_axis_shadow(d)
    print(f"\n== {d}'s chart_axis_shadow_* audit events ==")
    for et in ("chart_axis_shadow_graded", "chart_axis_shadow_delta", "chart_axis_shadow_norender"):
        rows = await get_audit_log(event_type=et, since_hours=24, limit=50)
        print(f"\n  [{et}] {len(rows)}")
        for r in rows:
            print(f"    {r['created_at']:%H:%M}  {r['summary']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cohort-only", action="store_true",
                    help="print the cohort + render check; ZERO spend")
    ap.add_argument("--run", action="store_true",
                    help="run the real shadow core once, then dump that date's audit rows")
    ap.add_argument("--date", type=str, default="",
                    help="ISO date (default et_today()); point at the last trading day on a holiday")
    args = ap.parse_args()
    if not (args.cohort_only or args.run):
        ap.error("pass --cohort-only (free) or --run (grades)")
    d = _resolve_date(args.date)
    asyncio.run(_cohort_only(d) if args.cohort_only else _run(d))


if __name__ == "__main__":
    sys.exit(main())
