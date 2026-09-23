"""Is the EXTENDED cohort tradeable under OUR OWN mechanics? (2026-08-16)

THE QUESTION. The winner-reference read found that the extension filter — skip when
the prior close is >= 50% above the lowest close of the last 5 sessions
(`ep_detector.MAX_EXTENSION_PCT`) — rejects the highest-variance cohort we have:
median 20-day return -38%, but 34.6% reach a +50% max excursion and 17.6% DOUBLE,
against 13.0% / 4.0% for everything else (n=159 over 70 sessions).

⚠ Max favourable excursion is NOT money. It is the best price the stock touched,
not what our bracket would have kept. This probe answers the only question that
matters before anyone discusses the filter:

    Entered at the ORB high with the ORB low as the stop, under the live MAGNA53
    geometry, what is the REALIZED-R distribution of that cohort?

If the tail survives our own mechanics it is a real fork for the operator. If the
-38% median eats it at our stop, the filter is doing its job and the question is
closed.

METHOD. Reuses `_468_moderate_realized_r.py` UNCHANGED for the simulation —
`eligibility()` (the live submission-window rule) and `reconstruct()` (stop-limit
buy at the ORB high, stop at the ORB low, the live validation gates, the +2R
partial). Only the COHORT changes. Bars come from Polygon via the same in-container
read path, so NOTHING is written to prod and no backfill is needed.

⚠ READ ONLY. No prod writes, no orders, no LLM spend. Extension is entry discipline
= THE LINE: this probe MEASURES and proposes nothing.

⚠ WHAT WOULD MAKE IT CONCLUSIVE, stated up front: realized-R is reconstructed, not
lived — no slippage model, fills assumed at the trigger, and the cohort is names we
never entered so there is no fill evidence. Report the tail (P90/share>=+2R/+5R)
alongside the median, per the standing rule that a median cannot see a 10x.
"""
from __future__ import annotations

import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import _468_moderate_realized_r as M   # noqa: E402  (sibling probe, reused verbatim)

HERE = Path(__file__).resolve().parent
OUT = HERE.parent.parent / "docs" / "analysis" / "extension_cohort_replay_2026-08-16.txt"

# Point the reused module at OUR cohort/bar caches so its own _468 files are untouched.
M.COHORT = HERE / "_ext_cohort.tsv"
M.DAILY = HERE / "_ext_daily.tsv"
M.MINUTE = HERE / "_ext_minute.tsv"
M.TRADES = HERE / "_ext_trades.tsv"

# Same column order load_cohort() expects; the extension cohort is defined by the
# skip_reason the live filter wrote, joined back to the alert row for its fields.
# 🔴 STRUCTURAL FACT found while building this: the extension filter fires BEFORE a
# name becomes an alert, so only 3 of 159 have a `mi_ep_alerts` row at all. There is
# therefore NO recorded detection timestamp for this cohort, and the cohort must be
# built from `mi_ep_missed_outcomes` alone.
# ASSUMPTION, stated because it is load-bearing: submission at 09:31 ET — the live
# cron default for anything detected pre-open, which a gap name normally is. Names
# actually detected intraday would have submitted later (or been out-of-ORB), so this
# assumption is GENEROUS to the cohort. Say so wherever the result is cited.
EXT_SQL = """
SELECT DISTINCT ON (m.ticker, m.alert_date)
       m.ticker, m.alert_date, 'EXTENDED',
       0, COALESCE(round(m.gap_pct::numeric, 2), 0),
       m.alert_date || ' 09:31:00',
       COALESCE(m.catalyst_quality, ''), '', '',
       COALESCE(round((m.max_high_20d*100)::numeric, 1)::text, '')
FROM mi_ep_missed_outcomes m
WHERE m.skip_reason LIKE 'already up%extended%' AND m.max_high_20d IS NOT NULL
ORDER BY m.ticker, m.alert_date
"""


def pull() -> None:
    M.COHORT.write_text(M.run_select(EXT_SQL), encoding="utf-8")
    n = len([l for l in M.COHORT.read_text().splitlines() if l.strip()])
    print(f"extension cohort rows -> {n}")
    M.pull_bars()


def _share(rs, thr):
    return (100.0 * sum(1 for r in rs if r >= thr) / len(rs)) if rs else 0.0


def report() -> None:
    rows = M.load_cohort()
    daily, minute = M.load_daily(), M.load_minute()
    outs, skipped = [], defaultdict(int)
    for r in rows:
        why, sub = M.eligibility(r)
        if why != "ok":
            skipped[why] += 1
            continue
        dbars = daily.get(r["ticker"], [])
        i = M.idx_of_date(dbars, r["alert_date"])
        if i is None:
            skipped["no_daily"] += 1
            continue
        raw = minute.get((r["ticker"], r["alert_date"]), [])
        if not raw:
            skipped["no_minute"] += 1
            continue
        try:
            rth = M.de.polygon_to_rth_minutes(raw, r["alert_date"])
        except Exception as e:
            skipped[f"rth_error:{type(e).__name__}"] += 1
            continue
        if not rth:
            skipped["rth_empty"] += 1
            continue
        atr = M.atr14_prior_close(dbars, i)
        try:
            res = M.reconstruct(rth, sub, atr, dbars[i:])
        except Exception as e:                       # one bad name must not kill the run
            skipped[f"reconstruct_error:{type(e).__name__}"] += 1
            continue
        if not isinstance(res, dict) or res.get("outcome") != "filled":
            skipped["outcome:" + str(res.get("outcome") if isinstance(res, dict) else "?")] += 1
            continue
        res["ticker"], res["alert_date"] = r["ticker"], r["alert_date"]
        res["mfe20"] = r["fwd_5d"]                   # column reused to carry max_high_20d %
        outs.append(res)

    lines = []
    P = lines.append
    P("=" * 96)
    P("EXTENSION COHORT — REALIZED-R UNDER OUR OWN MECHANICS (ORB-high entry, ORB-low stop)")
    P("=" * 96)
    P(f"cohort rows={len(rows)}  simulated={len(outs)}")
    P("not simulated: " + (", ".join(f"{k}={v}" for k, v in sorted(skipped.items())) or "none"))
    P("")
    P("⚠ Extension is entry discipline = THE LINE. This is measurement; nothing is proposed.")
    P("⚠ Realized-R is RECONSTRUCTED, not lived: no slippage model, fills assumed at the")
    P("  trigger, and these are names we never entered so there is no fill evidence.")
    P("")
    rkey = "r" if outs and "r" in outs[0] else None
    if not rkey:
        P("!! reconstruct() returned no recognisable R field — keys: "
          + (", ".join(sorted(outs[0].keys())) if outs else "(no rows simulated)"))
    else:
        rs = sorted(x[rkey] for x in outs if isinstance(x.get(rkey), (int, float)))
        if rs:
            P(f"REALIZED R  n={len(rs)}")
            P(f"  median   {M._median(rs):+.2f}R      mean {sum(rs)/len(rs):+.2f}R")
            P(f"  P10/P90  {rs[len(rs)//10]:+.2f}R / {rs[9*len(rs)//10]:+.2f}R")
            P(f"  max      {rs[-1]:+.2f}R   min {rs[0]:+.2f}R")
            P(f"  share >= +2R  {_share(rs, 2.0):.1f}%   >= +5R  {_share(rs, 5.0):.1f}%"
              f"   >= +10R  {_share(rs, 10.0):.1f}%")
            P(f"  share <= -1R  {_share([-x for x in rs], 1.0):.1f}%  (full stop-outs)")
            P(f"  SUM of R across the cohort: {sum(rs):+.1f}R  <- the number that decides it")
            P("")
            P("  TOP 10 by realized R:")
            for x in sorted(outs, key=lambda z: z.get(rkey, -99), reverse=True)[:10]:
                P(f"    {x['ticker']:<6} {x['alert_date']}  {x.get(rkey, 0):+7.2f}R"
                  f"   (20d MFE {x.get('mfe20')}%)")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\n-> {OUT}")


if __name__ == "__main__":
    if "--pull" in sys.argv:
        pull()
    report()
