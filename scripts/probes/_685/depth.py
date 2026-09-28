"""#685 follow-up — the slice rule as a DEPTH trigger (2026-09-28).

================================ PRE-REGISTRATION ==================================
Written BEFORE any arm was scored. Reuses scripts/probes/_685/study.py's functions
by import (load_all, harness_walk, day0_state, walk_hybrid_arm, Arm, ARM_DEFS,
block_signflip_p, drop_best_two, HORIZON, SPLIT_DATE) — nothing here re-implements
them; the walker body is untouched. $0: no new data pull — the same capture files
study.py already reads (pull_main_out.txt, pull_min_out.tsv.gz, the 09-01/#562
captures).

OPERATOR'S POINT: FTK (alert 08-03, sold 08-17, line 34.35, low 27.30 = 20.5%
below the line) and INFQ (alert 05-21, sold 06-05, line 16.48, low 14.30 = 13.2%
below) are real slice-throughs he sells; the 2-bar confirmation caught both only
after price had already fallen 13-20% below the line. OKTA's 09-28 recovery
dipped at most 1.4% below its line and closed back above the same window. The
hypothesis under test: a DEPTH trigger (sell the instant price is far enough below
the line, no bar-shape pattern needed) may separate these without the slice
signature's wait.

NEW ARMS (A0/A1/A2k2/A3 are UNCHANGED — read from study.py's own already-produced
arms_per_trade.tsv, not rewalked, so the 79-trade scoring can never drift from the
closed #685 study):
  D05  once the day's line is breached (trail_governed and the day's low <= the
       line), sell AT ONCE the first time price trades 0.5 x ADR below the line,
       AT THAT PRICE; a bar/day whose open is already below that level books the
       open instead (the gap is charged at the open). If that depth is never
       reached, hold and sell at the CLOSE if the close is below the line —
       IDENTICAL to A1's close test (see MECHANISM below).
  D10  the same with 1.0 x ADR.
  ADR = the harness' adr20_pct at entry x that day's line price — study.py's own
  A3 formula (`line_r - MULT * adr_pct * line_r`), MULT = 0.5 / 1.0 here instead of
  A3's fixed 1.0. Both arms keep today's hard stop and breakeven exactly as every
  other arm; nothing else changes.

MECHANISM = study.py's existing `Arm(adr_stop=True)` branch inside
  `walk_hybrid_arm`, completely unmodified. D05/D10 = `Arm(name, line_rests=False,
  k=None, grace=False, adr_stop=True)` (no slice signature, no first-hour grace —
  those only apply when `k is not None`), with the module constant `ADR_MULT`
  monkeypatched to 0.5 / 1.0 immediately before each call and reset to 1.0 (A3's
  value) immediately after, since A3 is walked interleaved with D05/D10 in the
  same per-trade loop. No new branch is written in study.py; study.py itself is
  not edited.
  Proof the close test really is A1's (checked empirically below, not just
  asserted): on any day a D-arm does not fire intraday, its resting stop for that
  day is `rest = max(floor, line - MULT*ADR) <= line`, and the walker sets
  `state["hard_stop"] = rest` before the daily-grain step; `apply_daily_exit_step`
  then computes `effective_stop = max(hard_stop, SMA-line, breakeven)`. Since
  `rest <= line` and the SMA-line IS that day's line, `effective_stop` collapses to
  the same line for every arm — so the close-below-line verdict cannot differ from
  A1's. Every line-test day where a D-arm's close action differs from A1's is
  reported as a fidelity failure, not silently accepted.

POPULATION — SCORING: the SAME 79 trades study.py scored (paired vs A0: A0, A1,
  A2k2, A2k3, A3 all settled and readable), read directly from
  `arms_per_trade.tsv` — not re-derived, so the denominator cannot drift. A0/A1/
  A2k2/A3 R values for the scoring table come from THAT FILE (already validated by
  study.py's own anchor + fidelity checks); D05/D10 are walked fresh via
  `day0_state` + `walk_hybrid_arm` on exactly those 79 keys.
  FIDELITY GATE (run before anything is reported): re-derive `day0_state`
  independently (harness_walk on era_d, the same population rule study.py's
  default run uses) and re-walk A0 and A1 myself on every campaign that reaches
  day 1; HALT if either disagrees with `arms_per_trade.tsv` by > 0.005R or on
  status, on the 79 or the broader set below — a silent population/state drift
  would invalidate D05/D10 too, since they share the same day0_state.
  POPULATION — DESCRIPTIVE (the per-line-test table, Step 0, matching study.py's
  own LINE TESTS section): every campaign study.py walked past day 0 (~51, not
  just the 79-paired subset) — because D05/D10, unlike the slice signature, need
  no minute bars (the daily open/low/close alone resolve a depth touch and the
  close test), so THC/HTFL/ARGX/U/ROIV (unreadable for the signature arms) are
  included here and flagged `in79` for whether they are also in the scored 79.

MEASURES (study.py's own stats functions, same seed=685, same ISO-week blocks,
  same two-sided 5000-draw sign-flip permutation): on the 79, per arm (A1
  close-only, A2k2 slice k=2, A3 first-hour grace, D05, D10) vs A0 — total and
  per-trade money-R, paired diff, p, better/worse, >=3 ORB-R and >=8 ORB-R
  winners, worst single trade, losses beyond -1.5 money-R — reported WITH the 79
  and again WITHOUT FTK (2026-08-03) and INFQ (2026-05-21), for DISCOVERY (alert
  <= 08-31) and HELD-OUT (alert >= 09-01) separately.
  Pre-committed to ALSO report, regardless of how it comes out: the false-sell
  count for D05/D10 on the 19 RECLAIM days (closed back above the line) — the same
  "would this have sold a day that recovered" question the slice signature's
  6-of-16 / 2-of-14 already answer — and FTK/INFQ's own breach depth in ADR
  multiples (their % depth, 20.5% / 13.2%, is already known from line_tests.tsv;
  whether either sits under 1.0 ADR — meaning D10 would NOT catch it early and
  falls back to A1's close fill — is not known yet and is reported either way.

STATED PLAINLY, not proposed as a result: the 0.5x/1.0x thresholds were chosen
  AFTER seeing FTK, INFQ and OKTA's depths — this is a LEAN for his read, not an
  out-of-sample test. Nothing here touches live code, PLAN.md, or CHANGE_PROCESS;
  nothing here is a decision.
====================================================================================
"""
from __future__ import annotations

import csv
import statistics
import sys
from datetime import date, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import study as ST  # noqa: E402

FTK_KEY = ("FTK", date(2026, 8, 3))
INFQ_KEY = ("INFQ", date(2026, 5, 21))
SPLIT_DATE = ST.SPLIT_DATE
HORIZON = ST.HORIZON
OUT = HERE

ARM_DEFS_D = {
    "D05": ST.Arm("D05", False, None, False, True),
    "D10": ST.Arm("D10", False, None, False, True),
}
ADR_MULT_D = {"D05": 0.5, "D10": 1.0}
ORIG_ARMS = ("A0", "A1", "A2k2", "A2k3", "A3")          # study.py's own arms
TABLE_ARMS = ("A1", "A2k2", "A3", "D05", "D10")          # scored vs A0 in the report
LINE_TEST_ARMS = ("A0", "A1", "D05", "D10")               # per task: what these 4 did


def fmt(x, nd=2):
    return "—" if x is None else f"{x:+.{nd}f}"


# ── load the frozen 79-trade population + its stored arm results ──────────────────

def load_stored():
    stored = {}
    with open(HERE / "arms_per_trade.tsv") as fh:
        for row in csv.DictReader(fh, delimiter="|"):
            k = (row["ticker"], date.fromisoformat(row["alert_date"]))
            stored[k] = row
    keys79 = {k for k, row in stored.items()
              if all(row[f"{a}_status"] == "settled" for a in ORIG_ARMS)
              and all(row[f"{a}_unreadable"] == "False" for a in ORIG_ARMS)}
    return stored, keys79


def stored_r(row, arm):
    v = row[f"{arm}_R"]
    return float(v) if v else None


# ── rebuild the population + day0 states via study.py's own functions ─────────────

def build_states():
    alerts, regime_rows, adv, daily, day0, held, mincov, trades, S = ST.load_all()
    rs_d = ST.ep.RULESETS["era_d"]
    H0 = ST.harness_walk(alerts, regime_rows, adv, daily, day0, rs_d, HORIZON)
    key = lambda r: (r["ticker"], r["alert_date"])
    H0m = {key(r): r for r in H0}
    live_high_abstain = [r for r in H0 if str(r["admit"]).startswith("abstain")
                          and r["alert"].get("score_tier") == "HIGH"]
    adm = [r for r in H0 if r["admit"] == "admit"] + live_high_abstain
    adm.sort(key=lambda r: (r["alert_date"], r["ticker"]))

    states, day0_only = {}, {}
    for h in adm:
        k = key(h)
        bars0 = day0.get(k, [])
        orb = next((b for b in bars0 if b["m"].time() == time(9, 30)), None)
        h["orb_low"] = orb["l"] if orb else None
        h["orb_high"] = orb["h"] if orb else None
        if h["entered"] and orb:
            f = ST.ep.entry_walk(bars0, orb["h"], h["submit"], rs_d.entry_cancel)
            h["fill_minute"] = f.get("minute") if f["status"] == "filled" else None
        else:
            h["fill_minute"] = None
        st = ST.day0_state(h, bars0, rs_d)
        if st is None:
            continue
        if st["settled_d0"]:
            day0_only[k] = h["realized_r"]
            continue
        states[k] = st
    return daily, held, mincov, H0m, states, day0_only


def walk_one(arm_name, k, st, daily, held, mincov):
    arm_def = ARM_DEFS_D.get(arm_name) or ST.ARM_DEFS[arm_name]
    mult = ADR_MULT_D.get(arm_name, 1.0)          # A0/A1/A2k2 ignore it; A3 pinned to 1.0
    ST.ADR_MULT = mult
    try:
        return ST.walk_hybrid_arm(ticker=k[0], alert_date=k[1], st=st, arm=arm_def,
                                   daily=daily, held=held, horizon=HORIZON, mincov=mincov)
    finally:
        ST.ADR_MULT = 1.0


def day0_result(k, day0_only):
    return {"status": "settled", "realized_r": day0_only[k], "mark_r": None,
            "exit_day": None, "final_reason": "stop_hit", "line_tests": []}


def main():
    log = open(OUT / "depth_out.txt", "w")

    def P(*a):
        s = " ".join(str(x) for x in a)
        print(s); log.write(s + "\n")

    P(f"# #685 depth-trigger follow-up run {ST.datetime.now(ST._ET).isoformat(timespec='seconds')}")

    stored, keys79 = load_stored()
    P(f"## POPULATION (from arms_per_trade.tsv, unchanged): 79-paired = {len(keys79)} "
      f"(expect 79); DISC {sum(1 for k in keys79 if k[1] <= SPLIT_DATE)} "
      f"HELD {sum(1 for k in keys79 if k[1] > SPLIT_DATE)}")
    if len(keys79) != 79:
        P("## POPULATION MISMATCH — HALT"); log.close(); raise SystemExit(2)

    daily, held, mincov, H0m, states, day0_only = build_states()
    all_keys = set(states) | set(day0_only)
    P(f"## REBUILT POPULATION (walked past day 0 or settled day 0): {len(all_keys)} "
      f"({len(states)} reached day 1, {len(day0_only)} settled day 0); "
      f"stored population {len(stored)}; "
      f"79-set present: {len(keys79 & all_keys)}/{len(keys79)}")
    missing = keys79 - all_keys
    if missing or all_keys != set(stored):
        P(f"## POPULATION MISMATCH vs arms_per_trade.tsv — missing from rebuild {sorted(missing)}; "
          f"in rebuild not stored {sorted(all_keys - set(stored))}; "
          f"in stored not rebuild {sorted(set(stored) - all_keys)} — HALT")
        log.close(); raise SystemExit(2)

    # ── walk every campaign that reached day 1, for A0/A1/D05/D10 (all daily-bar-evaluable) ──
    RESULTS = {a: {} for a in ("A0", "A1", "D05", "D10")}
    for k in all_keys:
        if k in day0_only:
            for a in RESULTS:
                RESULTS[a][k] = day0_result(k, day0_only)
            continue
        st = states[k]
        for a in RESULTS:
            RESULTS[a][k] = walk_one(a, k, st, daily, held, mincov)

    # ── FIDELITY GATE: A0/A1 must match arms_per_trade.tsv everywhere ──
    bad = []
    for a in ("A0", "A1"):
        for k in all_keys:
            row = stored.get(k)
            if row is None:
                continue
            want_status = row[f"{a}_status"]
            want_r = stored_r(row, a)
            got = RESULTS[a][k]
            if got["status"] != want_status:
                bad.append(f"{a} {k}: status walker={got['status']} stored={want_status}")
                continue
            if want_status == "settled" and abs((got["realized_r"] or 0) - (want_r or 0)) > 0.005:
                bad.append(f"{a} {k}: R walker={got['realized_r']:+.4f} stored={want_r:+.4f}")
    P(f"## FIDELITY GATE (A0/A1 rewalked vs arms_per_trade.tsv, {len(all_keys)} campaigns): "
      f"{'PASS' if not bad else 'FAIL'} ({len(bad)} mismatches)")
    for s in bad[:30]:
        P("    ", s)
    if bad:
        P("## FIDELITY FAILED — HALT"); log.close(); raise SystemExit(2)

    # ── descriptive Step 0: every line test on the broader (~51) population, A0/A1/D05/D10 ──
    lt_rows = []
    for k, r in RESULTS["A1"].items():
        h = H0m[k]
        adr_pct = states[k]["adr_pct"] if k in states else None
        for x in r["line_tests"]:
            line, low, close = x["line"], x["low"], x["close"]
            depth_d = line - low
            depth_adr = (depth_d / (adr_pct * line)) if adr_pct else None
            depth_pct = depth_d / line * 100
            reclaim = close >= line
            row = {"ticker": k[0], "alert_date": k[1].isoformat(), "day": x["day"].isoformat(),
                   "in79": k in keys79, "line": line, "low": low, "close": close,
                   "depth_$": round(depth_d, 4), "depth_adr": round(depth_adr, 3) if depth_adr else None,
                   "depth_pct": round(depth_pct, 2), "cls": "RECLAIM" if reclaim else "SLICE",
                   "n_bars": x["n_bars"]}
            for a in LINE_TEST_ARMS:
                ra = RESULTS[a][k]
                ed = ra["exit_day"]
                if ed == x["day"]:
                    act = ra["final_reason"]
                elif ed is not None and ed < x["day"]:
                    act = "exited_earlier"
                else:
                    act = "HELD"
                row[f"{a}_action"] = act
            lt_rows.append(row)
    lt_rows.sort(key=lambda r: (r["alert_date"], r["ticker"], r["day"]))
    P(f"## LINE TESTS (descriptive, broader population): {len(lt_rows)} days on "
      f"{len({(r['ticker'], r['alert_date']) for r in lt_rows})} trades "
      f"(in the scored 79: {sum(1 for r in lt_rows if r['in79'])} days); "
      f"RECLAIM {sum(1 for r in lt_rows if r['cls']=='RECLAIM')} / "
      f"SLICE {sum(1 for r in lt_rows if r['cls']=='SLICE')}")
    with open(OUT / "depth_line_tests.tsv", "w") as fh:
        cols = list(lt_rows[0].keys()) if lt_rows else []
        fh.write("|".join(cols) + "\n")
        for r in lt_rows:
            fh.write("|".join("" if r[c] is None else str(r[c]) for c in cols) + "\n")

    # false-sell counts on RECLAIM days, pre-committed
    reclaim_rows = [r for r in lt_rows if r["cls"] == "RECLAIM"]
    for a in ("D05", "D10"):
        fs = sum(1 for r in reclaim_rows if r[f"{a}_action"] == "stop_hit")
        P(f"## {a} false sells on the {len(reclaim_rows)} RECLAIM days: {fs} "
          f"(sold on a day that closed back above the line)")
    # close-test-equivalence check: on days neither D-arm fired intraday, its close
    # verdict must equal A1's
    ce_bad = 0
    for r in lt_rows:
        for a in ("D05", "D10"):
            if r[f"{a}_action"] in ("HELD", "close_below_line") and r["A1_action"] in ("HELD", "close_below_line"):
                if r[f"{a}_action"] != r["A1_action"]:
                    ce_bad += 1
                    P(f"    CLOSE-TEST MISMATCH {a} vs A1: {r['ticker']} {r['day']} "
                      f"{a}={r[f'{a}_action']} A1={r['A1_action']}")
    P(f"## CLOSE-TEST EQUIVALENCE (D05/D10 vs A1, days neither fired intraday): "
      f"{'PASS' if ce_bad == 0 else f'FAIL ({ce_bad})'}")

    # FTK / INFQ breach depth in ADR
    for name, k in (("FTK", FTK_KEY), ("INFQ", INFQ_KEY)):
        hit = [r for r in lt_rows if (r["ticker"], r["alert_date"]) == (k[0], k[1].isoformat())]
        for r in hit:
            P(f"## {name} breach depth: {r['depth_pct']}% = {r['depth_adr']} x ADR "
              f"(line {r['line']}, low {r['low']})")

    # ── per-trade D05/D10 table (79 keys) + combined with stored A0/A1/A2k2/A3 ──
    with open(OUT / "depth_per_trade.tsv", "w") as fh:
        cols = ["ticker", "alert_date", "block", "orb_r_ps", "entry", "hard"] + \
               [f"{a}_R" for a in ("A0", "A1", "A2k2", "A3", "D05", "D10")]
        fh.write("|".join(cols) + "\n")
        for k in sorted(keys79, key=lambda k: (k[1], k[0])):
            row = stored[k]
            vals = [row["A0_R"], row["A1_R"], row["A2k2_R"], row["A3_R"],
                    f"{RESULTS['D05'][k]['realized_r']:.4f}", f"{RESULTS['D10'][k]['realized_r']:.4f}"]
            fh.write("|".join([k[0], k[1].isoformat(), row["block"], row["orb_r_ps"], row["entry"], row["hard"]] + vals) + "\n")

    # ── MEASURES: ALL / DISC / HELD, WITH and WITHOUT FTK+INFQ ──
    def money_per_orb(k):
        row = stored[k]
        return (float(row["entry"]) - float(row["hard"])) / float(row["orb_r_ps"])

    def r_of(a, k):
        if a in ("A0", "A1", "A2k2", "A3"):
            return stored_r(stored[k], a)
        return RESULTS[a][k]["realized_r"]

    summary_rows = []
    for blk in ("ALL", "DISC", "HELD"):
        for excl in (False, True):
            ks = [k for k in keys79 if (blk == "ALL" or (k[1] <= SPLIT_DATE) == (blk == "DISC"))]
            if excl:
                ks = [k for k in ks if k not in (FTK_KEY, INFQ_KEY)]
            if not ks:
                continue
            base = {k: r_of("A0", k) for k in ks}
            label = f"{blk}{'_ex' if excl else ''}"
            P(f"## BLOCK {label}: n={len(ks)} A0 total {sum(base.values()):+.2f}")
            for a in TABLE_ARMS:
                R = {k: r_of(a, k) for k in ks}
                vals = list(R.values())
                diffs = [R[k] - base[k] for k in ks]
                weeks = [f"{k[1].isocalendar()[0]}-W{k[1].isocalendar()[1]:02d}" for k in ks]
                p = ST.block_signflip_p(diffs, weeks, ST.random.Random(ST.SEED * 10 + TABLE_ARMS.index(a)))
                better = sum(1 for x in diffs if x > 1e-9); worse = sum(1 for x in diffs if x < -1e-9)
                orb_vals = [R[k] * money_per_orb(k) for k in ks]
                win3 = sum(1 for x in orb_vals if x >= 3); win8 = sum(1 for x in orb_vals if x >= 8)
                worst = min(vals); worst_k = min(ks, key=lambda k: R[k])
                big_loss = sum(1 for x in vals if x < -1.5)
                row = {"block": label, "arm": a, "n": len(ks), "sum": sum(vals),
                       "mean": statistics.mean(vals), "diff": sum(diffs), "p": p,
                       "better": better, "worse": worse, "win3": win3, "win8": win8,
                       "worst": worst, "worst_ticker": worst_k[0], "big_loss": big_loss}
                summary_rows.append(row)
                P(f"   {a:5s} n={row['n']:3d} total {row['sum']:+7.2f} vs A0 {row['diff']:+6.2f} "
                  f"p={p:.3f} better/worse {better}/{worse} | >=3ORB-R {win3} >=8ORB-R {win8} | "
                  f"worst {fmt(worst)} ({worst_k[0]}) | losses<-1.5R {big_loss}")

    with open(OUT / "depth_summary.tsv", "w") as fh:
        cols = list(summary_rows[0].keys())
        fh.write("|".join(cols) + "\n")
        for r in summary_rows:
            fh.write("|".join(str(r[c]) for c in cols) + "\n")

    P("## DONE")
    log.close()
    return summary_rows, lt_rows


if __name__ == "__main__":
    main()
