#!/usr/bin/env python3
"""Rehearsal analysis for alert_rank_shadow_out_of_sample (2026-08-18). READ-ONLY,
offline, over the one-time capture `_rehearsal_rank_shadow_join_out_2026-08-18.psv`
(produced by `_rehearsal_rank_shadow_join_2026-08-18.sql` against prod, read-only).
Proves the join from mi_alert_rank_shadow (no forward-outcome column) to a forward
outcome (R geometry 1, matching scripts/probes/_expectedness_and_ranking.py
cohort_features) is EXECUTABLE and produces a number -- NOT a verdict (far too
early; most rows are heavily right-censored, see fwd_n coverage below). THE LINE:
analysis only, no writes.

BOTH-DIRECTIONS (per the GOAL section's SELECTION rule, 2026-08-18): winners admitted
AND losers excluded, not a numerator-only "how many winners". Loser proxy: forward
path broke the EP-day low (fwd_low <= day_low) -- the -1R stop-out class -- which is
computable from the same join (fwd_low was added on the 2nd capture pass per advisor
review; the 1st pass only pulled fwd_high and could not answer the losers side at all).

Run: python3 scripts/probes/_rehearsal_rank_shadow_analysis_2026-08-18.py
(re-pull first with the .sql file in this directory if the .psv capture is stale)
"""
import statistics as st
from pathlib import Path

HERE = Path(__file__).parent
rows = []
for line in (HERE / "_rehearsal_rank_shadow_join_out_2026-08-18.psv").read_text().splitlines():
    p = line.split("|")
    (alert_id, ticker, alert_date, day_high, day_low,
     qual_eod, comp_eod, pool_eod,
     qual_asof, comp_asof, pool_asof,
     trade_exists, trade_filled,
     fwd_high, fwd_low, fwd_n) = p
    rows.append(dict(
        alert_id=alert_id, ticker=ticker, alert_date=alert_date,
        day_high=float(day_high), day_low=float(day_low),
        qual_eod=(qual_eod == "t"), comp_eod=float(comp_eod) if comp_eod else None,
        pool_eod=int(pool_eod) if pool_eod else None,
        qual_asof=(qual_asof == "t"), comp_asof=float(comp_asof) if comp_asof else None,
        pool_asof=int(pool_asof) if pool_asof else None,
        trade_exists=(trade_exists == "t"), trade_filled=(trade_filled == "t"),
        fwd_high=float(fwd_high) if fwd_high else None,
        fwd_low=float(fwd_low) if fwd_low else None,
        fwd_n=int(fwd_n) if fwd_n else 0,
    ))

print(f"rows joined: {len(rows)}  (denominator = ALL alerts, not just filled trades -- "
      f"{sum(1 for r in rows if r['trade_filled'])} of {len(rows)} were actually filled)")
n_fwd = sum(1 for r in rows if r["fwd_n"] > 0)
print(f"rows with >=1 forward session: {n_fwd}")
print(f"fwd_n distribution: min={min(r['fwd_n'] for r in rows)} "
      f"median={st.median(r['fwd_n'] for r in rows)} max={max(r['fwd_n'] for r in rows)} "
      f"(cap=60; a full read needs 60)")
full60 = sum(1 for r in rows if r["fwd_n"] >= 60)
print(f"rows with a FULL 60-session forward window (uncensored): {full60} of {len(rows)}")

# R1 geometry: entry=day_high, stop=day_low, R = (fwd_high - day_high)/(day_high-day_low)
for r in rows:
    risk = r["day_high"] - r["day_low"]
    if r["fwd_high"] is not None and risk > 0:
        r["r1"] = (r["fwd_high"] - r["day_high"]) / risk
    else:
        r["r1"] = None
    # loser proxy: forward path ever traded AT OR BELOW the EP-day low (the natural
    # stop reference this whole program uses) -- a -1R-or-worse outcome by construction.
    if r["fwd_low"] is not None:
        r["broke_day_low"] = r["fwd_low"] <= r["day_low"]
    else:
        r["broke_day_low"] = None

have_r1 = [r for r in rows if r["r1"] is not None]
print(f"rows with a computed R1 (join produced a number): {len(have_r1)} of {len(rows)}")
winners10 = [r for r in have_r1 if r["r1"] >= 10]
print(f">=10R (censored floor -- windows are incomplete): {len(winners10)} of {len(have_r1)}")
print("NOTE: 0 is the EXPECTED result here, not a signal that the rule is dead -- the "
      "doc's own 26 tradeable >=10R winners are NOT in the alert table (0 of 26 were "
      "live-alerted); this population structurally cannot reproduce them.")

def both_directions(key_qual, key_comp, label):
    pool = [r for r in have_r1 if r[key_qual] and r[key_comp] is not None and r["broke_day_low"] is not None]
    print(f"\n-- {label}: qualifying+scored+has-outcome = {len(pool)} of {len(have_r1)} --")
    if not pool:
        print("   (empty pool)")
        return
    top_q = [r for r in pool if r[key_comp] >= 0.75]
    rest = [r for r in pool if r[key_comp] < 0.75]
    for name, grp in (("top-quartile composite", top_q), ("remaining 3 quartiles", rest)):
        if not grp:
            print(f"   {name}: n=0")
            continue
        winners = sum(1 for x in grp if x["r1"] >= 10)
        losers = sum(1 for x in grp if x["broke_day_low"])
        print(f"   {name}: n={len(grp)}"
              f" | winners admitted (>=10R) = {winners} ({100*winners/len(grp):.1f}%)"
              f" | losers admitted (broke EP-day low) = {losers} ({100*losers/len(grp):.1f}%)"
              f" | median R1 = {st.median(x['r1'] for x in grp):.2f}")
    print("   MECHANISM OUTPUT ONLY, NOT A READ: in-sample dates dominate this pool, "
          "windows are censored (median 32/60 sessions), and the rule was validated on "
          "TAIL CATCH-RATE, never on a median (the doc's own Spearman(tail, R-from-entry) "
          "= -0.013) -- a median or quartile-loser-rate comparison here is not the tested "
          "claim and must not be read as one.")

both_directions("qual_eod", "comp_eod", "EOD composite rank")
both_directions("qual_asof", "comp_asof", "AS-OF-09:45 composite rank")

print("\nDone. This is a MECHANISM rehearsal only -- see caveats in the report.")
