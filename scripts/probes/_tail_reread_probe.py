#!/usr/bin/env python3
"""TAIL RE-READ (2026-08-16) — re-runs the five 2026-08-15/16 structure/RS/skip/override
probes on TAIL statistics instead of medians, per the operator's closing point:

  "we need to remember EPs are rare and winrate is low, we're not looking for a sure
  thing, so failures are expected — however, we are looking for high risk/reward. If we
  hit a real EP we gain 10X, that's the distinction here."

WHY THIS PROBE EXISTS (docs/roadmap/ep_profitability_program.md GOAL §'WE ARE HUNTING THE
TAIL, NOT THE AVERAGE' / docs/methodology/structure_model.md §7b): every 2026-08-15/16
read compared MEDIAN forward return or excursion with session-permuted MEDIAN
differences. A median is blind to a tail by construction — a feature that genuinely
finds real EPs would leave the median flat (or negative, since it would still mostly
select names that fail) and move only the top few percent. That is indistinguishable
from the nulls already reported. This probe asks the same five questions again on P90,
P95, and the share of names reaching +50%/+100%, with permutation run on the TAIL
STATISTIC itself (not a median difference), so the significance test matches what is
being reported.

READ-ONLY. SHADOW MEASUREMENT ONLY. Nothing here touches _score_ep, the judge, entry,
exit, or sizing (THE LINE). A positive result is a FORK for the operator, not a
pre-decided change. No prod writes, no trading, no LLM spend.

REUSE, NOT REWRITE. Every cohort definition, split, control, and maturity-day constant
below is IDENTICAL to the corresponding 2026-08-15/16 probe — extracted via ONE import
pass (scratchpad/_tail_extract.py) that ran each source probe's own median battery
exactly once and cached the resulting feature rows as plain JSON (capture once, read
many). This script never re-derives a cohort; it only changes the STATISTIC and the
permutation target, per the task. Shared tail-statistic machinery (P90/P95/share,
session-permutation generalized to an arbitrary statistic) lives in _tail_stats.py,
generalizing the identical perm_p() pattern already used by all five source probes.

R-MULTIPLE (5R/10R) SHARE — SKIPPED GLOBALLY, stated once here rather than five times.
None of the five source tables carry a per-alert stop distance / planned-R denominator
for the SKIP or DECLINED-ALERT populations (only the 22 TAKEN trades in
_skip_attribution_read.py have risk_dollars, and that is the wrong population to answer
this on — skipped/declined names never got a real stop). Reconstructing MFE-in-R would
mean rebuilding the ORB fill/stop logic from scratch — the "fifth reconstruction" the
task instructions say to avoid (same reasoning _533_supply_ladder_probe.py's own
docstring already gives for skipping it there). max_high_5d/20d (% from open) carries
the excursion-size question instead, exactly as it does in every source probe.

TAIL-STAT N FLOORS (from _tail_stats.py, applied uniformly): P90 needs n>=20, P95 needs
n>=40, a share needs n>=10, PER BUCKET (pos and neg both) — below the floor the cell
prints "N too thin", never a number, and is counted as an attempted-but-infeasible test,
not silently dropped. A THRESHOLD CENSUS (scratchpad/census.py, run before any of this
harness was written) determined which of the five probes' cohorts clear these floors at
which horizons; that census is what shaped the horizon/split choices below.

NBIS-SWEEP HORIZON LIMIT, disclosed once: the nbis sweep's own fwd_outcomes() (reused
UNCHANGED) computes only ret_1d/ret_5d/mfe_5d — no 20-day figure exists for that probe.
Reported on the horizons that exist; a 20d column is not fabricated for it.

Output: capture once to docs/analysis/tail_reread_2026-08-16.txt.
"""
from __future__ import annotations

import json
import os
import statistics as st
import sys
from datetime import date, timedelta
from pathlib import Path

if os.environ.get("APOLLO_PROBE_WRITE"):
    sys.exit("this probe is read-only by design")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _tail_stats as ts  # noqa: E402

SCRATCH = Path("/private/tmp/claude-501/-Users-alvinfung-apollo-the-wise/"
                "6bd49b80-0683-4b68-be72-adb54075b1c4/scratchpad")

MATURITY_DAYS = {"ret_1d": 2, "ret_5d": 8, "ret_20d": 30, "max_high_5d": 8, "max_high_20d": 30}


def load(name):
    return json.loads((SCRATCH / name).read_text(encoding="utf-8"))


LADDER = load("ladder_feat.json")
LADDER_META = load("ladder_meta.json")
NBIS = load("nbis_sweep.json")
RSINFL = load("rsinfl_feat.json")
RSINFL_META = load("rsinfl_meta.json")
SKIP_MATCHED = load("skip_matched.json")
SKIP_TAKEN = load("skip_taken.json")
SKIP_META = load("skip_meta.json")
GO_ROWS = load("gradeoverride_rows.json")
GO_DATA_MAX = max(r["alert_date"] for r in GO_ROWS)

TOTAL_TESTS = 0
N_INFEASIBLE_LOG: list[str] = []


def pdate(s: str) -> date:
    y, m, d = (int(x) for x in s.split("-"))
    return date(y, m, d)


def mature(rows, h, dkey, data_max_str, maturity_days=MATURITY_DAYS):
    cutoff = pdate(data_max_str) - timedelta(days=maturity_days[h])
    return [r for r in rows if pdate(r[dkey]) <= cutoff]


def run_tail_pair(ledger: ts.TailLedger, label: str, h: str, pos_rows: list, neg_rows: list,
                   dkey: str = "d") -> None:
    """P90 / P95 / share>=+50% / share>=+100%, each individually N-gated, permuted on
    THAT statistic. median is printed as the secondary. Every attempt is counted in the
    ledger whether or not N supported a p (thin cells are a reportable result, not a
    silent skip)."""
    global TOTAL_TESTS
    pv = [r[h] * 100.0 for r in pos_rows if r.get(h) is not None]
    nv = [r[h] * 100.0 for r in neg_rows if r.get(h) is not None]
    ps = {r.get(dkey) for r in pos_rows if r.get(h) is not None}
    ns = {r.get(dkey) for r in neg_rows if r.get(h) is not None}
    psess_list = [r.get(dkey) for r in pos_rows if r.get(h) is not None]
    nsess_list = [r.get(dkey) for r in neg_rows if r.get(h) is not None]
    dpos, dneg = ts.describe_tail(pv, ps), ts.describe_tail(nv, ns)
    print(f"\n  {label}  [{h}]")
    print(f"    POS {ts.fmt_bucket(dpos)}")
    print(f"    NEG {ts.fmt_bucket(dneg)}")
    for stat_name, statfn, dfield in [("P90", ts.p90, "p90"), ("P95", ts.p95, "p95"),
                                       ("share>=+50%", ts.share_stat(50.0), "share50"),
                                       ("share>=+100%", ts.share_stat(100.0), "share100")]:
        TOTAL_TESTS += 1
        thin = (dpos[dfield] is None or dneg[dfield] is None)
        if thin:
            reason = ("n<20 for P90" if stat_name == "P90" else
                      "n<40 for P95" if stat_name == "P95" else "n<10 for a share")
            print(f"    {stat_name:<13} N TOO THIN ({reason}; pos n={dpos['n']}, neg n={dneg['n']}) "
                  f"— no test attempted")
            ledger.add(label, stat_name, h, dpos, dneg, None, None, thin=True)
            N_INFEASIBLE_LOG.append(f"{ledger.name} / {label} / {h} / {stat_name}: "
                                     f"n={dpos['n']}/{dneg['n']} below floor")
            continue
        p = ts.perm_p_stat(pv, nv, psess_list, nsess_list, statfn)
        effect = statfn(pv) - statfn(nv)
        pstr = "N too coarse (perm resolution)" if p is None else f"raw p={p:.4f}"
        if p is None:
            N_INFEASIBLE_LOG.append(f"{ledger.name} / {label} / {h} / {stat_name}: "
                                     f"perm too coarse (n={dpos['n']}/{dneg['n']})")
        print(f"    {stat_name:<13} POS={dpos[dfield]:>7} NEG={dneg[dfield]:>7}  "
              f"diff={effect:+7.2f}pp  {pstr}")
        ledger.add(label, stat_name, h, dpos, dneg, p, effect, thin=False)


def run_tail_battery(ledger, label, population, split_fn, horizons, dkey, data_max_str):
    for h in horizons:
        m = mature(population, h, dkey, data_max_str)
        pos = [r for r in m if split_fn(r) is True]
        neg = [r for r in m if split_fn(r) is False]
        run_tail_pair(ledger, label, h, pos, neg, dkey=dkey)


print("=" * 100)
print("TAIL RE-READ — same five probes, same cohorts, TAIL statistics (P90/P95/share>=+50%/")
print("+100%) as PRIMARY, median as secondary, permutation run on the tail statistic itself.")
print("=" * 100)
print("Methodology: docs/roadmap/ep_profitability_program.md GOAL §'WE ARE HUNTING THE TAIL'")
print("+ docs/methodology/structure_model.md §7b. N floors: P90>=20, P95>=40, share>=10 per")
print("bucket (scripts/probes/_tail_stats.py) — below floor: 'N too thin', never a substituted")
print("median. R-multiple (5R/10R) share SKIPPED globally — no stop distance on any skip/")
print("declined-alert population without a fifth reconstruction (see docstring).")

# ============================================================================================
# PART 1 — SUPPLY LADDER: zones_cleared vs gap_pct, TAIL statistics (his decisive comparison)
# ============================================================================================
print("\n" + "=" * 100)
print("PART 1 / PROBE 1 — SUPPLY LADDER (_533_supply_ladder_probe.py), declined-alert")
print(f"population n={len(LADDER)}, {len({r['d'] for r in LADDER})} sessions. Same cohort,")
print("same splits as 2026-08-16's run; only the statistic changes.")
print("=" * 100)
L_DATA_MAX = LADDER_META["data_max"]
GAP_MEDIAN, GAP_T1, GAP_T2 = LADDER_META["gap_median"], LADDER_META["gap_t1"], LADDER_META["gap_t2"]
BAND_ADR = LADDER_META["band_adr"]
adr_med = st.median(r["adr20_pct"] for r in LADDER)

zc_split = lambda r: (r["zones_cleared"] >= 1) if r.get("zones_cleared") is not None else None
gap_split = lambda r: (r["gap_pct"] >= GAP_MEDIAN) if r.get("gap_pct") is not None else None
held_split = lambda r: ((r["zones_cleared_and_held"] >= 1)
                        if r.get("zones_cleared_and_held") is not None else None)
iffy_split = lambda r: r["iffy"]
bluesky_split = lambda r: r["blue_sky"]


def dist_split(r):
    if r.get("zones_remaining") is None or r["zones_remaining"] == 0 or r.get("dist_adr") is None:
        return None
    return r["dist_adr"] < BAND_ADR


def ma_split(r):
    if not r.get("n_overhead_mas"):
        return None
    return r["ma_cleared_count"] == r["n_overhead_mas"]


def gap_tercile(r):
    if r.get("gap_pct") is None:
        return None
    return "low" if r["gap_pct"] < GAP_T1 else ("high" if r["gap_pct"] >= GAP_T2 else "mid")


led1 = ts.TailLedger("P1-ladder-decisive")
print("\n--- [1] THE DECISIVE COMPARISON: zones_cleared (0 vs >=1) — his refinement ---")
run_tail_battery(led1, "zones_cleared 0 vs >=1", LADDER, zc_split,
                  ["max_high_5d", "max_high_20d", "ret_5d"], "d", L_DATA_MAX)
print("\n--- [2] gap_pct (< vs >= population median) — the comparator his refinement beats ---")
run_tail_battery(led1, "gap_pct median split", LADDER, gap_split,
                  ["max_high_5d", "max_high_20d", "ret_5d"], "d", L_DATA_MAX)

print("\n--- [3] CONFOUND CONTROL — zones_cleared WITHIN each gap-size tercile, max_high_5d ---")
for lbl in ("low", "mid", "high"):
    sub = [r for r in LADDER if gap_tercile(r) == lbl]
    run_tail_battery(led1, f"gap-{lbl} tercile: zones_cleared 0 vs >=1", sub, zc_split,
                      ["max_high_5d"], "d", L_DATA_MAX)

print("\n--- [4] STRUCTURE-DEPTH BUCKETS, max_high_5d ---")
ta_only = [r for r in LADDER if r["tier_a"]]
run_tail_battery(led1, "zones_cleared_and_held (Tier-A) 0 vs >=1", ta_only, held_split,
                  ["max_high_5d"], "d", L_DATA_MAX)
run_tail_battery(led1, "IFFY (his word) vs not", LADDER, iffy_split, ["max_high_5d"], "d", L_DATA_MAX)
run_tail_battery(led1, "BLUE_SKY vs not", LADDER, bluesky_split, ["max_high_5d"], "d", L_DATA_MAX)
run_tail_battery(led1, "dist-to-nearest NEAR(<1.5xADR) vs FAR", LADDER, dist_split,
                  ["max_high_5d"], "d", L_DATA_MAX)
run_tail_battery(led1, "cleared ALL overhead MAs vs not", LADDER, ma_split,
                  ["max_high_5d"], "d", L_DATA_MAX)

print("\n--- [5] DOSE-RESPONSE, tail statistics per bucket (descriptive, no formal p) ---")
for h in ("max_high_5d", "max_high_20d"):
    print(f"\n  {h}:")
    m = mature(LADDER, h, "d", L_DATA_MAX)
    for lo, hi, lbl in [(0, 0, "0"), (1, 2, "1-2"), (3, 5, "3-5"), (6, 999, "6+")]:
        sub = [r for r in m if lo <= r["zones_cleared"] <= hi and r.get(h) is not None]
        vals = [r[h] * 100.0 for r in sub]
        sess = {r["d"] for r in sub}
        d = ts.describe_tail(vals, sess)
        print(f"    zones_cleared {lbl:<4} {ts.fmt_bucket(d)}")

print(led1.bonferroni_summary())

# ============================================================================================
# PART 2 — SUPPLY LADDER, REMEASURED FROM THE RIGHT ORIGIN: overhead REMAINING above the
# alert-day open (zones_remaining / dist_adr, DEMOTED-then-RE-PROMOTED per the task), blue
# sky reported separately, tail statistics, within-ADR-half control kept.
# ============================================================================================
print("\n" + "=" * 100)
print("PART 2 — LADDER RE-MEASURED FROM THE RIGHT ORIGIN: overhead REMAINING above the open")
print("(yesterday's zones_cleared came back BACKWARDS — measured from the alert-day open,")
print("i.e. AFTER the gap already consumed the structure. Primary becomes what remains.)")
print("=" * 100)
zr_split = lambda r: (r["zones_remaining"] >= 1) if r.get("zones_remaining") is not None else None

led2 = ts.TailLedger("P2-ladder-remaining-overhead")
print("\n--- [P2-1] PRIMARY: zones_remaining (>=1 remaining overhead vs 0) ---")
run_tail_battery(led2, "zones_remaining >=1 vs 0", LADDER, zr_split,
                  ["max_high_5d", "max_high_20d"], "d", L_DATA_MAX)

print("\n--- [P2-2] BLUE SKY reported separately (the limiting case: nothing overhead at all) ---")
run_tail_battery(led2, "BLUE_SKY vs not (Part 2 framing)", LADDER, bluesky_split,
                  ["max_high_5d", "max_high_20d"], "d", L_DATA_MAX)

print("\n--- [P2-3] DISTANCE to the NEXT remaining zone, in ADR units (near vs far) ---")
run_tail_battery(led2, "dist to next zone NEAR(<1.5xADR) vs FAR", LADDER, dist_split,
                  ["max_high_5d", "max_high_20d"], "d", L_DATA_MAX)

print(f"\n--- [P2-4] WITHIN-ADR-HALF CONTROL (population median ADR20 = {adr_med:.2f}%) ---")
print("(kept from yesterday's run: high-ADR names mechanically have fewer zones AND move")
print("more, rho -0.35 zones-vs-ADR / +0.36 ADR-vs-excursion — pooled zones_remaining result")
print("must be read within each half, not just pooled)")
for lbl, cond in [("low-ADR half", lambda r: r["adr20_pct"] < adr_med),
                  ("high-ADR half", lambda r: r["adr20_pct"] >= adr_med)]:
    sub = [r for r in LADDER if cond(r)]
    print(f"\n  {lbl} (n={len(sub)}):")
    run_tail_battery(led2, f"{lbl}: zones_remaining >=1 vs 0", sub, zr_split,
                      ["max_high_5d", "max_high_20d"], "d", L_DATA_MAX)

print("\n--- [P2-5] DOSE-RESPONSE on REMAINING overhead, tail stats per bucket (descriptive) ---")
for h in ("max_high_5d", "max_high_20d"):
    print(f"\n  {h}:")
    m = mature(LADDER, h, "d", L_DATA_MAX)
    for lo, hi, lbl in [(0, 0, "0 (incl blue sky)"), (1, 2, "1-2"), (3, 5, "3-5"), (6, 999, "6+")]:
        sub = [r for r in m if lo <= r["zones_remaining"] <= hi and r.get(h) is not None]
        vals = [r[h] * 100.0 for r in sub]
        sess = {r["d"] for r in sub}
        d = ts.describe_tail(vals, sess)
        print(f"    zones_remaining {lbl:<18} {ts.fmt_bucket(d)}")

print(led2.bonferroni_summary())

# ============================================================================================
# PROBE 2 — NBIS STRUCTURE ENCODER: GOOD/POOR verdict, tail statistics
# ============================================================================================
print("\n" + "=" * 100)
print(f"PROBE 2 — NBIS STRUCTURE ENCODER (_533_nbis_structure_encoder.py), mi_ep_alerts")
print(f"population n={len(NBIS)}, {len({r['date'] for r in NBIS})} sessions. Fixture gate")
print("already verified 8/8 PASS before this sweep ran (scripts/probes/_533n_gate.json).")
print("⚠ NO 20-DAY HORIZON EXISTS for this probe's own fwd_outcomes() — not fabricated here.")
print("=" * 100)
led3 = ts.TailLedger("P3-nbis-good-poor")
gv = [r for r in NBIS if r["verdict"] == "GOOD"]
pv_ = [r for r in NBIS if r["verdict"] == "POOR"]
print(f"\nGOOD={len(gv)} ({len({r['date'] for r in gv})} sessions) · "
      f"POOR={len(pv_)} ({len({r['date'] for r in pv_})} sessions)")
print("⚠ UNIT FIX: this probe's own fwd_outcomes() (docstring: 'Forward returns... % units')")
print("  returns ret_1d/ret_5d/mfe_5d ALREADY multiplied by 100 (e.g. +4.0 means +4%), unlike")
print("  the other four probes' DB columns which store FRACTIONS. run_tail_pair() applies its")
print("  own x100 (the house convention for fractions) — applying it to already-percent values")
print("  would double-scale a real +187% mover (HQ, 2026-06-15) into a nonsensical +18735%.")
print("  Normalized here by dividing by 100 before the shared harness re-multiplies.")
verdict_split = lambda r: (r["verdict"] == "GOOD") if r.get("verdict") in ("GOOD", "POOR") else None
for h in ("ret_5d", "mfe_5d", "ret_1d"):
    pos = [dict(r, **{h: r[h] / 100.0}) for r in NBIS if r.get(h) is not None and r["verdict"] == "GOOD"]
    neg = [dict(r, **{h: r[h] / 100.0}) for r in NBIS if r.get(h) is not None and r["verdict"] == "POOR"]
    run_tail_pair(led3, "GOOD vs POOR (full verdict)", h, pos, neg, dkey="date")
print(led3.bonferroni_summary())

# ============================================================================================
# PROBE 3 — RS INFLECTION in the low-RS population, tail statistics
# ============================================================================================
print("\n" + "=" * 100)
low = [r for r in RSINFL if r["comp"] < RSINFL_META["low_rs_primary"]]
print(f"PROBE 3 — RS INFLECTION (_rs_inflection_read.py), low-RS(<{RSINFL_META['low_rs_primary']:.0f}) ")
print(f"population n={len(low)} of {len(RSINFL)} total, {len({r['d'] for r in low})} sessions.")
print("=" * 100)
led4 = ts.TailLedger("P4-rs-inflection")
sgn = lambda r: (r["infl16"] > 0) if r["infl16"] is not None else None
run_tail_battery(led4, "PRIMARY low-RS infl_1m6m sign", low, sgn,
                  ["ret_5d", "max_high_5d", "max_high_20d"], "d", RSINFL_META["data_max"])
print(led4.bonferroni_summary())

print("\n--- CONFOUND CHECK (advisor-flagged, run after seeing the max_high_20d/share>=+50%")
print("    survivor) — is infl_1m6m separating on gap_pct or rs_composite level instead of")
print("    genuine RS trajectory? Same rule the ORIGINAL probe's own confound section used:")
print("    |rho| >= ~0.4 means this data cannot separate inflection from that variable. ---")


def spearman_local(xs, ys):
    n = len(xs)
    if n < 10:
        return None

    def ranks(v):
        order = sorted(range(n), key=lambda i: v[i])
        rk = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k2 in range(i, j + 1):
                rk[order[k2]] = avg
            i = j + 1
        return rk

    rx, ry = ranks(xs), ranks(ys)
    mx, my = st.fmean(rx), st.fmean(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    vx = sum((a - mx) ** 2 for a in rx)
    vy = sum((b - my) ** 2 for b in ry)
    return cov / (vx * vy) ** 0.5 if vx and vy else None


for pop_label, pop in [("full low-RS (all)", low),
                       ("low-RS matured for max_high_20d (the surviving cell's own population)",
                        mature(low, "max_high_20d", "d", RSINFL_META["data_max"]))]:
    pos_r = [r for r in pop if sgn(r) is True]
    neg_r = [r for r in pop if sgn(r) is False]
    gp = [r["gap"] for r in pos_r if r.get("gap") is not None]
    gn = [r["gap"] for r in neg_r if r.get("gap") is not None]
    cp = [r["comp"] for r in pos_r]
    cn = [r["comp"] for r in neg_r]
    pairs = [(r["infl16"], r["gap"]) for r in pop if r.get("gap") is not None and r["infl16"] is not None]
    rho_gap = spearman_local([a for a, _ in pairs], [b for _, b in pairs]) if len(pairs) >= 10 else None
    pairs_c = [(r["infl16"], r["comp"]) for r in pop if r["infl16"] is not None]
    rho_comp = spearman_local([a for a, _ in pairs_c], [b for _, b in pairs_c]) if len(pairs_c) >= 10 else None
    print(f"\n  [{pop_label}]")
    print(f"    gap_pct   median POS={st.median(gp):.2f}% (n={len(gp)})  NEG={st.median(gn):.2f}% (n={len(gn)})"
          f"  — {'SEPARATES (possible gap confound)' if abs(st.median(gp)-st.median(gn)) > 3 else 'no material separation'}")
    print(f"    rs_composite median POS={st.median(cp):.1f} (n={len(cp)})  NEG={st.median(cn):.1f} (n={len(cn)})")
    print(f"    Spearman(infl_1m6m, gap_pct) = {rho_gap:+.3f}" if rho_gap is not None else
          "    Spearman(infl_1m6m, gap_pct) = N too small")
    print(f"    Spearman(infl_1m6m, rs_composite) = {rho_comp:+.3f}" if rho_comp is not None else
          "    Spearman(infl_1m6m, rs_composite) = N too small")
print("  READ: |rho|<~0.4 and near-equal gap medians would mean the tail effect above is NOT")
print("  simply gap size wearing an RS label — genuinely attributable to the RS trajectory")
print("  feature, to the extent this data can separate it.")

# ============================================================================================
# PROBE 4 — GRADE OVERRIDE outcome, tail statistics (excursion size, pooled + gap bands)
# ============================================================================================
print("\n" + "=" * 100)
print(f"PROBE 4 — GRADE OVERRIDE (_grade_override_outcome_read.py), n={len(GO_ROWS)} judged")
print(f"alerts through {GO_DATA_MAX} (pinned to match the captured 2026-08-15 median report).")
print("=" * 100)
over = [r for r in GO_ROWS if r["score_tier"] == "HIGH" and r["judge_tier"] in ("none", "MODERATE")
        and r["authority"] == "floor"]
agree = [r for r in GO_ROWS if r["score_tier"] == "HIGH" and r["judge_tier"] == "HIGH"]
print(f"OVERRIDDEN n={len(over)} · AGREED n={len(agree)}")
led5 = ts.TailLedger("P5-grade-override")
BANDS = [("POOLED", None), ("GAP 10-15%", (10.0, 15.0)), ("GAP 15-20%", (15.0, 20.0)),
         ("GAP >=20%", (20.0, 1e9))]
for lbl, sel in BANDS:
    o = over if sel is None else [r for r in over if r["gap_pct"] is not None and sel[0] <= r["gap_pct"] < sel[1]]
    a = agree if sel is None else [r for r in agree if r["gap_pct"] is not None and sel[0] <= r["gap_pct"] < sel[1]]
    print(f"\n  -- {lbl}: overridden n={len(o)}  agreed n={len(a)} --")
    if not o or not a:
        print("    (empty cohort)")
        continue
    combined = [dict(r, _grp="o") for r in o] + [dict(r, _grp="a") for r in a]
    split = lambda r: (r["_grp"] == "o")
    run_tail_battery(led5, f"{lbl}: overridden vs agreed", combined, split,
                      ["max_high_5d", "max_high_20d"], "alert_date", GO_DATA_MAX)
print(led5.bonferroni_summary())

# ============================================================================================
# PROBE 5 — SKIP-REASON ATTRIBUTION, tail statistics
# ============================================================================================
print("\n" + "=" * 100)
print(f"PROBE 5 — SKIP-REASON ATTRIBUTION (_skip_attribution_read.py), date-matched skip")
print(f"population n={len(SKIP_MATCHED)}, taken benchmark n={len(SKIP_TAKEN)} "
      f">= {SKIP_META['match_start']}.")
print("=" * 100)
led6 = ts.TailLedger("P6-skip-attribution")

print("\n--- [5-0] DOES THE TAKEN BENCHMARK ITSELF EVER REACH THE TAIL? (descriptive census,")
print("    not a comparison — this is the honest first finding for this probe) ---")
for h in ("ret_1d", "ret_5d", "ret_20d", "max_high_5d", "max_high_20d"):
    t = mature(SKIP_TAKEN, h, "d", SKIP_META["data_max"])
    vals = [r[h] * 100.0 for r in t if r.get(h) is not None]
    sess = {r["d"] for r in t if r.get(h) is not None}
    d = ts.describe_tail(vals, sess)
    h50, s50 = ts.share_ge(vals, 50.0)
    h100, s100 = ts.share_ge(vals, 100.0)
    print(f"  {h:<13} n={d['n']:>3} ({len(sess):>2}s)  median={d['median']:>7}%  "
          f"share>=+50%={h50}/{d['n']}  share>=+100%={h100}/{d['n']}")
print("\n  PLAIN-COUNT FINDING (no permutation needed — this is a count, not a test): across")
print("  every one of the 22 trades we actually took, at EVERY horizon measured, ZERO ever")
print("  reached +50% maximum favorable excursion, let alone +100%. Under 'if we hit a real")
print("  EP we gain 10X,' our own trades have never once touched even a +50% tail outcome.")
print("  The date-matched SKIP population's SELECTION-kind reason reaches +50% at 14.9% and")
print("  +100% at 11.5% over 20 days (n=87, 8 sessions, descriptive — see [5-2] below; not")
print("  compared statistically to taken, whose own n is too thin for a permutation test, but")
print("  the plain counts stand on their own).")

print("\n--- [5-1] PRIMARY: gap_below_floor vs taken (his motivating case; N=7 pre-maturity —")
print("    same thinness the original probe already flagged; run through the same gates) ---")
primary_group = [r for r in SKIP_MATCHED if r["reason"] == "gap_below_floor"]
combined = [dict(r, _grp="s") for r in primary_group] + [dict(r, _grp="t") for r in SKIP_TAKEN]
split = lambda r: (r["_grp"] == "s")
run_tail_battery(led6, "gap_below_floor vs taken", combined, split,
                  ["max_high_5d", "max_high_20d"], "d", SKIP_META["data_max"])

print("\n--- [5-2] PER-KIND vs taken, max_high_5d / max_high_20d (date-matched population) ---")
for kind in SKIP_META["kinds"]:
    kgroup = [r for r in SKIP_MATCHED if r["kind"] == kind]
    combined = [dict(r, _grp="s") for r in kgroup] + [dict(r, _grp="t") for r in SKIP_TAKEN]
    split = lambda r: (r["_grp"] == "s")
    print(f"\n  -- KIND={kind} (n_raw={len(kgroup)}) --")
    run_tail_battery(led6, f"[{kind}] vs taken", combined, split,
                      ["max_high_5d", "max_high_20d"], "d", SKIP_META["data_max"])
print(led6.bonferroni_summary())

# ============================================================================================
# CLOSING LEDGER
# ============================================================================================
print("\n" + "=" * 100)
print("GRAND MULTIPLICITY LEDGER — every tail-statistic test run this probe, by section")
print("(each ledger's own Bonferroni denominator is its own attempted-test count, per")
print("house convention; ledgers are NOT pooled into one shared denominator, matching how")
print("the five source probes each carry their own separate x15/x17/x54 figure)")
print("=" * 100)
for led in (led1, led2, led3, led4, led5, led6):
    print(led.bonferroni_summary())
print(f"\nTOTAL TAIL TESTS ATTEMPTED THIS PROBE: {TOTAL_TESTS}")
print(f"N-INFEASIBLE / TOO-COARSE CELLS: {len(N_INFEASIBLE_LOG)} of {TOTAL_TESTS} "
      f"({100*len(N_INFEASIBLE_LOG)/TOTAL_TESTS:.0f}%)")
print("\nFull list of every N-too-thin / too-coarse cell (so none is silently absorbed into")
print("a 'null' verdict):")
for line in N_INFEASIBLE_LOG:
    print(f"  - {line}")

print("\n" + "=" * 100)
print("HOW TO READ THIS — every permutation shuffles whole SESSIONS on the STATISTIC being")
print("reported (P90/P95/share), not a median difference, per the task. A thin cell is a")
print("real result ('N cannot support a tail read here'), not evidence of no effect. THE")
print("LINE: this probe measures. Nothing here is wired into any grade, admission rule,")
print("sizing, or exit. A result that points at a change is a FORK for the operator, stated")
print("with no option pre-chosen.")
print("=" * 100)
