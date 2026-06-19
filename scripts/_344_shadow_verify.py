"""#344 shadow verifier — read the live web-inclusive shadow rows and summarize the
production net-correctness the FLIP gate needs. READ-ONLY.

Built ahead of the data (feedback_build_scaffolding_ahead_of_data): the shadow deploys
6/19 but only writes rows during a live market scan (Monday+). Run this after the first
scan day(s) to get a turnkey read instead of ad-hoc SQL.

Reads two audit event types:
  ep_grade_enrich_shadow  — uncached, once/ticker/day: current vs enriched grade (web-incl)
  ep_repoll_shadow        — cached path: re-grade once when a new source lands post-routine

What the FLIP gate is looking for (advisor 6/19):
  - NET catalyst-correctness: enriched LIFTS true catalysts, INFLATES nothing (the
    would-change list is for operator labeling).
  - re-poll fires EXACTLY ONCE per ticker/day (no thrash) and never on a firing grade.
  - latency doesn't bite (p95/max of shadow_latency_s).

    docker exec apollo-market python scripts/_344_shadow_verify.py            # today
    docker exec apollo-market python scripts/_344_shadow_verify.py 2026-06-22 # a date
    docker exec apollo-market python scripts/_344_shadow_verify.py --since 7  # last 7d
"""
import asyncio
import json
import sys
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")
_TIER = {"routine": 0, "strong": 1, "game_changer": 2, "mna": -1}


def _pctile(vals, p):
    if not vals:
        return 0.0
    s = sorted(vals)
    return s[min(len(s) - 1, int(p / 100 * len(s)))]


async def main():
    args = [a for a in sys.argv[1:]]
    since_days = None
    target = None
    if "--since" in args:
        since_days = int(args[args.index("--since") + 1])
    elif args:
        target = args[0]
    else:
        target = datetime.now(_ET).date().isoformat()

    from agents.market_intelligence.db import get_pool
    pool = await get_pool()
    async with pool.acquire() as c:
        if since_days:
            where = ("created_at AT TIME ZONE 'America/New_York' >= "
                     "(CURRENT_DATE - $1::int)")
            params = (since_days,)
            scope = f"last {since_days}d"
        else:
            where = "created_at AT TIME ZONE 'America/New_York' >= $1::date " \
                    "AND created_at AT TIME ZONE 'America/New_York' < $1::date + 1"
            params = (target,)
            scope = target

        async def _pull(evt):
            rows = await c.fetch(
                f"SELECT detail FROM mi_audit_log WHERE event_type = '{evt}' AND {where} "
                f"ORDER BY created_at", *params)
            out = []
            for r in rows:
                try:
                    out.append(json.loads(r["detail"]))
                except Exception:
                    pass
            return out

        enrich = await _pull("ep_grade_enrich_shadow")
        repoll = await _pull("ep_repoll_shadow")

    print(f"\n{'='*78}\n#344 SHADOW VERIFY — {scope}\n{'='*78}")

    # ── Enrichment shadow ──
    print(f"\n[ep_grade_enrich_shadow]  graded={len(enrich)}  "
          f"with_prior_agreement={sum(1 for d in enrich if d.get('has_prior_agreement'))}  "
          f"with_dilution={sum(1 for d in enrich if d.get('has_dilution'))}  (#238)")
    if not enrich:
        print("  (no rows yet — run after a live market scan)")
    else:
        cur = Counter(d.get("current_quality") for d in enrich)
        enr = Counter(d.get("enriched_quality") for d in enrich)
        print("  distribution (current → enriched):")
        for t in ("game_changer", "strong", "routine", "mna"):
            print(f"    {t:>12}: {cur.get(t,0):>3}  →  {enr.get(t,0):>3}")
        lat = [d.get("shadow_latency_s", 0) for d in enrich if d.get("shadow_latency_s")]
        print(f"  latency s: p50={_pctile(lat,50):.1f} p95={_pctile(lat,95):.1f} "
              f"max={max(lat) if lat else 0:.1f}")
        changed = [d for d in enrich if d.get("changed")]
        print(f"\n  ⚖️ CHANGES ({len(changed)}) — operator labels: true catalyst or inflation?")
        for d in changed:
            arrow = "↑" if _TIER.get(d.get("enriched_quality"), 0) > _TIER.get(d.get("current_quality"), 0) else "↓"
            print(f"    {arrow} {d.get('ticker'):6} {d.get('alert_date')}  "
                  f"{d.get('current_quality')} → {d.get('enriched_quality')}  "
                  f"prior_1.01={d.get('prior_agreement_filed') or 'none'}  "
                  f"dilution={d.get('dilution_form') or 'none'}")
            print(f"        {(d.get('enriched_analysis') or '')[:200]}")

        # ── #238 suppression-value read (the dilution cases the FLIP gate watches) ──
        dil = [d for d in enrich if d.get("has_dilution")]
        print(f"\n  💧 DILUTION CASES ({len(dil)}) — #238 suppression value: does a "
              f"catalyst-less pump-into-dilution stay routine? (real-EP+raise must STILL fire)")
        for d in dil:
            print(f"    {d.get('ticker'):6} {d.get('alert_date')}  {d.get('dilution_form')}@"
                  f"{d.get('dilution_filed')}  current={d.get('current_quality')} → "
                  f"enriched={d.get('enriched_quality')}")

    # ── Re-poll shadow ──
    print(f"\n[ep_repoll_shadow]  fired={len(repoll)}")
    tickers = Counter(d.get("ticker") for d in repoll)
    thrash = {t: n for t, n in tickers.items() if n > 1}
    print(f"  THRASH CHECK (each ticker/day must fire exactly once): "
          f"{'⚠️ ' + str(thrash) if thrash else 'OK (no ticker fired >1×)'}")
    if thrash:
        print("    NOTE: a mid-day container RESTART clears _repoll_shadow_state, so a "
              "ticker can legitimately fire twice across a restart — check mi_job_runs / "
              "container uptime before reading this as a logic bug (advisor 6/19).")
    if repoll:
        lat = [d.get("shadow_latency_s", 0) for d in repoll if d.get("shadow_latency_s")]
        print(f"  latency s: p50={_pctile(lat,50):.1f} p95={_pctile(lat,95):.1f} "
              f"max={max(lat) if lat else 0:.1f}")
        wf = [d for d in repoll if d.get("would_change")]
        print(f"\n  ⚖️ WOULD-FIRE on re-poll ({len(wf)}) — the BFLY class (late source rescues):")
        for d in wf:
            print(f"    {d.get('ticker'):6} {d.get('alert_date')}  routine → {d.get('repoll_quality')}  "
                  f"(+{d.get('current_src_count',0) - d.get('grade_src_count',0)} src, "
                  f"prior_agreement={d.get('has_prior_agreement')})")
            print(f"        {(d.get('repoll_analysis') or '')[:200]}")

    print(f"\n{'='*78}")
    print("GATE: enriched lifts true catalysts + inflates nothing (label CHANGES) · re-poll "
          "fires once, no thrash · latency tolerable. Clean over enough days + sign-off → flip.")
    print(f"{'='*78}\n")


if __name__ == "__main__":
    asyncio.run(main())
