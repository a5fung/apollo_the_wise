#!/usr/bin/env python3
"""#482 — the first cross-arm read, run EXACTLY as pre-registered (2026-11-06).

The bar:  scripts/probes/_482_read_1106/PREREG.md   (committed 392ab704 before any outcome row was read)
The steps: scripts/probes/_482_read_1106/ANALYSIS_PLAN.md (steps 3-6; this file is the plan's
           `cross_arm_read.py`, renamed read_482.py by the task that ran it)

READ-ONLY, $0. CSV in (data/, captured once from prod on 2026-11-06 — never re-captured), stdout out.
No DB connection, no API call, no write anywhere except out/ (the two script copies' text + dumps).

Run:  .venv/bin/python scripts/probes/_482_read_1106/read_482.py > scripts/probes/_482_read_1106/read_482.out

ERAS ARE NEVER POOLED. No line in this script's output sums or counts across exit eras.

INTERPRETATIONS PINNED BEFORE ANY ARM NUMBER WAS COMPUTED (the prereg is silent on each; stated
again in the RESULT section):
  I1 label precedence — a readable era that is not WON makes the arm NOT A CANDIDATE even when it is
     the only readable era ("any readable era is not WON" carries no qualifier); UNREADABLE only when
     fewer than 2 eras are readable and none is lost. Readable-era count + per-era WON/LOST print
     beside every label.
  I2 "disappoints" is computed on ALL cohort fills of the era (live_actual is the real trade;
     fidelity gates only arm-vs-live numbers). The paired-fills-only version prints beside it.
  I3 hour-bar / book arms: a no-entry fill is IN the R_cap set at 0 and OUT of the R_own set. Tail
     counts and rescues run on the full paired set with the arm's R_own at 0 on no-entry fills (the
     stricter direction for the arm); the entered-only version prints beside.
  I4 a settled row whose R_cap cannot be computed (its stop sits at/above the trigger, so the sizing
     frame is invalid) is its own counted class `rcap_uncomputable`: out of every R_cap metric and of
     the readable count, kept in R_own. No substitute trigger is invented.
  I5 "survives drop-best" in the Tier 2 / Tier 3 nominate rules is applied in BOTH units.
  I6 the engine check sums (arm - live_replay) in R_cap over paired fills where BOTH rows are settled
     (the prereg's words), so a book arm's no-entry fills are out of it; the variant with no-entry at
     0 prints beside it.
  I7 a no-entry fill scores 0 in adr as well as pct (the prereg names R_cap and pct only; adr is
     context, never part of a label).
  I8 an era is "readable" for an arm when its R_cap paired set holds >= 3 fills.
"""
from __future__ import annotations

import csv
import json
import statistics as st
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
DATA = HERE / "data"
OUT = HERE / "out"
sys.path.insert(0, str(REPO))

from agents.market_intelligence.book_geometry_arms import (  # noqa: E402
    capped_dollar_r,
    risk_pct_at,
)
from agents.market_intelligence.broker.exit_logic import TRAIL_ARM_LIVE_FROM  # noqa: E402
from agents.market_intelligence.constants import regime_risk_multiplier  # noqa: E402

_ET = ZoneInfo("America/New_York")
_UTC = ZoneInfo("UTC")

ERA_D_START = date(2026, 9, 6)
PREDICATE_FROM = date(2026, 8, 17)   # bracket_geometry_variants_parked: closed, alert_date >= 08-17
COHORT_FILL_FROM = date(2026, 8, 16)  # recorder BACKFILL_FROM: filled on/after 08-16 ET
ERAS = ("C", "D", "E")
FIDELITY_TOL = 0.25
TIE = 0.05

CONTROLS = ("live_actual", "live_replay")
STOP_ARMS = ("stop_orb_low", "stop_adr_050", "stop_adr_075", "stop_orb_3r", "stop_low_of_day")
ENTRY_BOOK_ARMS = ("entry_first_hour_bar", "book_first_hour_low_of_day")
HARVEST_ARMS = ("harvest_no_breakeven", "harvest_trail_only", "harvest_t3", "harvest_legacy_2r")
TRAIL_ARMS = ("trail_pivot_swing", "trail_character_ma")
WALKED = CONTROLS + STOP_ARMS + ENTRY_BOOK_ARMS + HARVEST_ARMS + TRAIL_ARMS  # 15
TESTED = STOP_ARMS + ENTRY_BOOK_ARMS + HARVEST_ARMS + TRAIL_ARMS  # 13 labelled arms
FILL_FACTS = "fill_facts"
FOLLOWS_LIVE = frozenset(CONTROLS + ("stop_orb_low", "stop_adr_050", "stop_adr_075", "stop_orb_3r",
                                     "trail_pivot_swing", "trail_character_ma") + ENTRY_BOOK_ARMS
                         + ("stop_low_of_day",))
ERA_EXPECT = {"C": ("2", None), "D": ("8", "3"), "E": ("8", "3")}  # (target_r, breakeven_arm_r)


def f(x):
    if x is None or x == "":
        return None
    try:
        return float(x)
    except ValueError:
        return None


def fmt(v, w=7, p=2):
    return f"{v:+{w}.{p}f}" if v is not None else " " * (w - 3) + "n/a"


def num_eq(a, b):
    """Numeric equality of two stored strings ('8' == '8.0'); both empty = equal."""
    if (a in (None, "")) and (b in (None, "")):
        return True
    fa, fb = f(a), f(b)
    return fa is not None and fb is not None and abs(fa - fb) < 1e-9


def rows(name):
    with open(DATA / name, newline="") as fh:
        rd = csv.reader(fh)
        header = next(rd)
        return header, [dict(zip(header, r)) for r in rd]


def hr(title, ch="="):
    print()
    print(ch * 104)
    print(title)
    print(ch * 104)


def derived_era(live_row):
    if (live_row.get("exit_rule") or "") == "depth":
        return "E"
    if date.fromisoformat(live_row["alert_date"]) >= ERA_D_START:
        return "D"
    return "C"


def fill_minute_et(live_row):
    fa = (live_row.get("filled_at") or "").strip()
    if not fa:
        return None
    return datetime.fromisoformat(fa[:19]).replace(tzinfo=_UTC).astimezone(_ET).strftime("%H:%M")


# ── classification of one arm row ─────────────────────────────────────────────────────────


def classify(row, arm):
    """-> (class, r_own, r_cap, pct, adr). class in settled / horizon / no_entry / abstain /
    unscoreable / pending / rcap_uncomputable. Values are None where not defined."""
    if row is None:
        return "pending", None, None, None, None
    out = row["outcome"]
    if out == "settled":
        rr = dict(row)
        if not rr.get("stop_price") and arm in CONTROLS:
            rr["stop_price"] = rr.get("live_stop")  # the plan: a control with NULL stop uses live_stop
        rcap = capped_dollar_r(rr)
        cls = "settled" if rcap is not None else "rcap_uncomputable"
        return cls, f(row["realized_r"]), rcap, f(row["realized_pct"]), f(row["pnl_adr"])
    if out == "horizon":
        rr = dict(row)
        rr["realized_r"] = row.get("mark_r")
        if not rr.get("stop_price") and arm in CONTROLS:
            rr["stop_price"] = rr.get("live_stop")
        return "horizon", f(row["mark_r"]), capped_dollar_r(rr), None, None
    if out == "unscoreable" and arm in ENTRY_BOOK_ARMS and (row.get("final_reason") or "").startswith("no_entry:"):
        return "no_entry", None, 0.0, 0.0, 0.0  # I3 / I7
    if out == "abstain":
        return "abstain", None, None, None, None
    return "unscoreable", None, None, None, None


def main():
    # ── load ──────────────────────────────────────────────────────────────────────────────
    files = ("live_all.csv", "lfc_arms.csv", "shadow_closed.csv", "shadow_open.csv", "adr.csv",
             "daily_bars.csv", "minute_bars_cohort.csv")
    hr("#482 FIRST CROSS-ARM READ — run as pre-registered (PREREG.md, commit 392ab704). Read-only, $0.")
    print("Inputs (captured once from prod 2026-11-06; line 1 of each must be its header):")
    for name in files:
        header, body = rows(name)
        assert header and not any(c.replace(".", "").replace("-", "").isdigit() for c in header), name
        print(f"  {name:<24} header ok, {len(body)} data rows")
    _, live_all = rows("live_all.csv")
    _, lfc = rows("lfc_arms.csv")
    print(f"  live_all captured_at: {sorted(set(r['captured_at'][:19] for r in live_all))}")

    # ── SECTION 0 — population ────────────────────────────────────────────────────────────
    hr("SECTION 0 — POPULATION (printed before any arm number)")
    closed = [r for r in live_all if r["status"] == "closed"]
    not_closed = [r for r in live_all if r["status"] != "closed"]
    pred = [r for r in closed if date.fromisoformat(r["alert_date"]) >= PREDICATE_FROM]
    cohort_rows = [r for r in closed if date.fromisoformat(r["fill_day_et"]) >= COHORT_FILL_FROM]
    print(f"(a) predicate count (closed live MAGNA53, alert_date >= 2026-08-17): {len(pred)}")
    print(f"    cohort count   (closed live MAGNA53, filled on/after 2026-08-16 ET): {len(cohort_rows)}"
          f"   [prereg expectation: 20 -> {'as expected' if len(cohort_rows) == 20 else 'DIFFERS'}]")
    print(f"    captured live MAGNA53 fills not closed (open/other): {len(not_closed)}"
          + (f" {[(r['id'], r['ticker'], r['status']) for r in not_closed]}" if not_closed else ""))
    by_trade = defaultdict(dict)
    for r in lfc:
        by_trade[int(r["trade_id"])][r["arm"]] = r
    live_by_id = {int(r["id"]): r for r in cohort_rows}
    print("\n    id   ticker alert_date fill_day   fill_ET exit_rule era status  entry_attempt")
    for tid, lr in live_by_id.items():
        print(f"    {tid:<4} {lr['ticker']:<6} {lr['alert_date']} {lr['fill_day_et']} {fill_minute_et(lr)}   "
              f"{(lr['exit_rule'] or 'NULL'):<9} {derived_era(lr)}   {lr['status']}  {lr['entry_attempt']}")
    era_of_trade = {tid: derived_era(lr) for tid, lr in live_by_id.items()}
    cnt = Counter(era_of_trade.values())
    print(f"    by exit era: C {cnt['C']} / D {cnt['D']} / E {cnt['E']}   (prereg expected about C 7 / D 8 / E 5)")

    # (b) era check — a mismatch STOPS the read
    print("\n(b) derived era vs the recorder's exit_era, every row of every cohort trade:")
    mism, no_rows = [], []
    for tid, era in era_of_trade.items():
        arms = by_trade.get(tid)
        if not arms:
            no_rows.append(tid)
            continue
        for arm, r in arms.items():
            if r["exit_era"] != f"era_{era.lower()}":
                mism.append((tid, arm, era, r["exit_era"]))
    stray = sorted(set(by_trade) - set(era_of_trade))
    print(f"    mismatches: {len(mism)}   cohort trades with no recorder row: {no_rows or 'none'}   "
          f"recorder trade_ids outside the cohort: {stray or 'none'}")
    if mism:
        for m in mism:
            print(f"    MISMATCH trade {m[0]} arm {m[1]}: derived {m[2]} vs recorder {m[3]}")
        print("\nSTOP — the prereg says a derived-era mismatch stops the read.")
        sys.exit(2)
    print("    -> every row agrees; the read proceeds.")

    # (c) rows per arm per fill by outcome class
    print("\n(c) recorder rows by arm and outcome class (cohort fills); pending = no row yet:")
    print(f"    expected per fill: {len(WALKED)} walked arms + fill_facts")
    for era in ERAS:
        tids = [t for t in era_of_trade if era_of_trade[t] == era]
        print(f"    era {era} ({len(tids)} fills):")
        for arm in WALKED + (FILL_FACTS,):
            c = Counter()
            for t in tids:
                r = by_trade[t].get(arm)
                c[(r["outcome"] + (":" + r["final_reason"] if r["outcome"] != "settled" else "")) if r else "PENDING"] += 1
            print(f"      {arm:<28} " + "  ".join(f"{k}={v}" for k, v in sorted(c.items())))
    pend = [(t, live_by_id[t]["ticker"], a) for t in era_of_trade for a in WALKED + (FILL_FACTS,)
            if a not in by_trade[t]]
    print(f"    pending (no row yet) — excluded and counted: {len(pend)}: "
          + ", ".join(f"{tk}({era_of_trade[t]}) {a}" for t, tk, a in pend))
    abst = [(live_by_id[t]["ticker"], era_of_trade[t], a, by_trade[t][a]["final_reason"])
            for t in era_of_trade for a in WALKED if a in by_trade[t] and by_trade[t][a]["outcome"] == "abstain"]
    print(f"    abstain rows: {abst or 'none'}")

    # (d) follows-live target / breakeven vs era expectation
    print("\n(d) follows-live rows: target_r / breakeven_arm_r vs the era expectation "
          "(C 2/NULL, D and E 8/3):")
    dis = []
    for t, era in era_of_trade.items():
        et, eb = ERA_EXPECT[era]
        for arm in FOLLOWS_LIVE:
            r = by_trade[t].get(arm)
            if r is None:
                continue
            if not (num_eq(r["target_r"], et) and num_eq(r["breakeven_arm_r"], eb)):
                dis.append((t, live_by_id[t]["ticker"], era, arm, r["target_r"], r["breakeven_arm_r"] or "NULL"))
    by_fill_dis = defaultdict(list)
    for d_ in dis:
        by_fill_dis[(d_[0], d_[1], d_[2], d_[4], d_[5])].append(d_[3])
    print(f"    disagreeing rows: {len(dis)} on {len(by_fill_dis)} fill(s)")
    for (t, tk, era, tr, br), arms in by_fill_dis.items():
        print(f"      {tk} (trade {t}, era {era}) walked {tr}/{br} on {len(arms)} follows-live rows: {sorted(arms)}")
    print("    -> per the prereg the fidelity check (below) decides whether such a fill stays.")

    # (e) exclusions / flags
    attr = [(int(r["id"]), r["ticker"], r["pnl_attribution"]) for r in cohort_rows if r["pnl_attribution"]]
    attr_lfc = sorted({(int(r["trade_id"]), r["ticker"], r["pnl_attribution"]) for r in lfc if r["pnl_attribution"]})
    att2 = [(int(r["id"]), r["ticker"]) for r in cohort_rows if r["entry_attempt"] == "2"]
    print(f"\n(e) excluded — non-NULL pnl_attribution: trade rows {attr or 'none'}; recorder rows {attr_lfc or 'none'}")
    print(f"    flagged (kept) — entry_attempt = 2: {att2 or 'none'}")
    excluded_attr = {t for t, _, _ in attr} | {t for t, _, _ in attr_lfc}

    # (f) admission-era mix per exit era
    print("\n(f) admission_era mix per exit era (reported, not split):")
    for era in ERAS:
        c = Counter(by_trade[t]["live_actual"]["admission_era"] for t in era_of_trade
                    if era_of_trade[t] == era and "live_actual" in by_trade[t])
        print(f"    era {era}: " + "; ".join(f"{k} x{v}" for k, v in sorted(c.items())))
    e_tids = [t for t in era_of_trade if era_of_trade[t] == "E"]
    pre = [live_by_id[t]["ticker"] for t in e_tids if date.fromisoformat(live_by_id[t]["fill_day_et"]) < TRAIL_ARM_LIVE_FROM]
    post = [live_by_id[t]["ticker"] for t in e_tids if date.fromisoformat(live_by_id[t]["fill_day_et"]) >= TRAIL_ARM_LIVE_FROM]
    print(f"    era E sub-change (exit_logic.TRAIL_ARM_LIVE_FROM = {TRAIL_ARM_LIVE_FROM}): filled before it "
          f"{pre}, on/after it {post} — the recorder models it; not split.")

    # (g) recorder identity checks
    print("\n(g) recorder checks:")
    for t in [t for t in era_of_trade if era_of_trade[t] == "C"]:
        a, b = by_trade[t].get("harvest_legacy_2r"), by_trade[t].get("live_replay")
        if a and b:
            ra, rb = f(a["realized_r"]), f(b["realized_r"])
            same = ra is not None and rb is not None and abs(ra - rb) < 1e-9
            print(f"    era C {live_by_id[t]['ticker']:<6} harvest_legacy_2r R_own {fmt(ra, 8, 4)} vs live_replay "
                  f"{fmt(rb, 8, 4)} -> {'EQUAL' if same else 'DIFFERENT'}")
    same_n = tot_n = same931 = tot931 = 0
    for t in era_of_trade:
        a, b = by_trade[t].get("stop_low_of_day"), by_trade[t].get("stop_orb_low")
        if not (a and b):
            continue
        same = num_eq(a["stop_price"], b["stop_price"]) and num_eq(a["realized_r"], b["realized_r"]) \
            and a["outcome"] == b["outcome"]
        tot_n += 1
        same_n += same
        if fill_minute_et(live_by_id[t]) == "09:31":
            tot931 += 1
            same931 += same
    print(f"    stop_low_of_day identical to stop_orb_low (same stop, same R, same outcome): {same_n} of {tot_n} "
          f"fills; on 09:31 fills {same931} of {tot931}. Where identical, the two arms are ONE confirmation, not two.")
    print("    hour-bar arms (entry_first_hour_bar, book_first_hour_low_of_day): SELECTION EFFECT — they see only "
          "fills whose 1-minute ORB high filled; an alert that never took the 1-minute high is invisible to them.")

    # ── R_cap ─────────────────────────────────────────────────────────────────────────────
    hr("SECTION 1 — R_cap (capped-dollar R, book_geometry_arms.capped_dollar_r imported offline)")
    chk = bad = 0
    for r in lfc:
        if r["realized_r_capped"]:
            got = capped_dollar_r(r)
            chk += 1
            if got is None or abs(got - float(r["realized_r_capped"])) > 1e-9:
                bad += 1
                print(f"    MISMATCH {r['trade_id']} {r['arm']} stored {r['realized_r_capped']} recomputed {got}")
    assert bad == 0, "stored realized_r_capped disagrees with the recomputation"
    print(f"  stored realized_r_capped == recomputed on {chk} of {chk} book-module rows (tolerance 1e-9).")
    print("  sizing frame per fill (live_actual row): regime -> multiplier, fill-day risk %:")
    for t in era_of_trade:
        la = by_trade[t]["live_actual"]
        print(f"    {la['ticker']:<6} era {era_of_trade[t]} regime {la['regime']:<11} mult {regime_risk_multiplier(la['regime']):.2f} "
              f"risk% {100 * risk_pct_at(date.fromisoformat(la['fill_day'])):.0f}")

    # classify everything once
    cls = {}  # (tid, arm) -> tuple
    for t in era_of_trade:
        for arm in WALKED:
            cls[(t, arm)] = classify(by_trade[t].get(arm), arm)
    unc = [(live_by_id[t]["ticker"], era_of_trade[t], arm, by_trade[t][arm]["stop_price"][:8],
            by_trade[t][arm]["orb_high"]) for (t, arm), v in cls.items() if v[0] == "rcap_uncomputable"]
    print(f"  settled rows whose R_cap cannot be computed (I4: stop at/above the trigger -> invalid sizing frame): "
          f"{len(unc)}: " + "; ".join(f"{tk} (era {e}) {a} stop {s} vs trigger {tr}" for tk, e, a, s, tr in unc))

    # ── fidelity ──────────────────────────────────────────────────────────────────────────
    hr("SECTION 2 — FIDELITY (live_replay vs live_actual, own R; pass when both settled and |diff| <= 0.25R)")
    fid_pass = {}
    for era in ERAS:
        print(f"  era {era}:")
        for t in [t for t in era_of_trade if era_of_trade[t] == era]:
            a, rp = cls[(t, "live_actual")], cls[(t, "live_replay")]
            ok = a[0] == "settled" and rp[0] == "settled" and abs(rp[1] - a[1]) <= FIDELITY_TOL
            if t in excluded_attr:
                ok = False
            fid_pass[t] = ok
            diff = (rp[1] - a[1]) if (a[1] is not None and rp[1] is not None) else None
            print(f"    {live_by_id[t]['ticker']:<6} live_actual {fmt(a[1], 8, 4)}  live_replay {fmt(rp[1], 8, 4)}  "
                  f"replay-actual {fmt(diff, 8, 4)}  -> {'PASS' if ok else 'FAIL'}")
        tids = [t for t in era_of_trade if era_of_trade[t] == era]
        fails = [live_by_id[t]["ticker"] for t in tids if not fid_pass[t]]
        print(f"    era {era}: {sum(fid_pass[t] for t in tids)} of {len(tids)} fills pass; failures excluded from "
              f"every arm-vs-live number: {fails or 'none'}")
    for era in ERAS:
        tids = [t for t in era_of_trade if era_of_trade[t] == era]
        big = [live_by_id[t]["ticker"] for t in tids if (cls[(t, "live_actual")][1] or 0) >= 4]
        big_fail = [tk for tk in big if not fid_pass[[t for t in tids if live_by_id[t]["ticker"] == tk][0]]]
        print(f"  era {era}: live fills that reached >= +4R: {big or 'none'}; of those, failing fidelity "
              f"(so absent from every paired table): {big_fail or 'none'}")

    # ── per arm per era ───────────────────────────────────────────────────────────────────
    hr("SECTION 3 — TIER 1: EACH ARM, EACH ERA, ON PAIRED FILLS (tail first). Deltas are arm - live_actual.")
    print("  Units: R_cap = capped-dollar R (the decision unit) · R_own = the arm's own realized R · "
          "pct = realized % · adr = P&L in ADR units.")
    print("  Sets: P_all = paired fills where the arm is settled or a book no-entry; P_cap = P_all minus "
          "rcap_uncomputable (R_cap metrics, readable count);")
    print("        P_own = P_all minus no-entry (R_own deltas). Tie = |delta| <= 0.05.")

    def era_metrics(arm, era, marks_counted):
        tids = [t for t in era_of_trade if era_of_trade[t] == era]
        excl = Counter()
        P = []  # (t, cls, arm_own, arm_cap, arm_pct, arm_adr, live_own, live_cap, live_pct, live_adr, rep_cap)
        for t in tids:
            la = cls[(t, "live_actual")]
            if t in excluded_attr:
                excl["excluded_pnl_attribution"] += 1
                continue
            if la[0] != "settled":
                excl["live_actual_not_settled"] += 1
                continue
            if not fid_pass[t]:
                excl["fidelity_fail"] += 1
                continue
            c = cls[(t, arm)]
            k = c[0]
            if k == "horizon" and not marks_counted:
                excl["horizon_mark_excluded"] += 1
                continue
            if k in ("abstain", "unscoreable", "pending"):
                excl[k] += 1
                continue
            rp = cls[(t, "live_replay")]
            P.append(dict(t=t, tk=live_by_id[t]["ticker"], k=k, own=c[1], cap=c[2], pct=c[3], adr=c[4],
                          l_own=la[1], l_cap=la[2], l_pct=la[3], l_adr=la[4], rep_cap=rp[2],
                          rep_settled=rp[0] == "settled"))
        P_cap = [p for p in P if p["k"] != "rcap_uncomputable"]
        P_own = [p for p in P if p["k"] != "no_entry"]
        excl_rcap = sum(1 for p in P if p["k"] == "rcap_uncomputable")
        n_noentry = sum(1 for p in P if p["k"] == "no_entry")
        m = dict(n_cap=len(P_cap), n_own=len(P_own), n_all=len(P), excl=dict(excl), rcap_unc=excl_rcap,
                 n_noentry=n_noentry, rows=P)

        def a0(p):  # arm R_own with no-entry at 0 (I3)
            return 0.0 if p["k"] == "no_entry" else p["own"]
        m["arm_ge2"] = sum(1 for p in P if a0(p) >= 2)
        m["arm_ge4"] = sum(1 for p in P if a0(p) >= 4)
        m["live_ge2"] = sum(1 for p in P if p["l_own"] >= 2)
        m["live_ge4"] = sum(1 for p in P if p["l_own"] >= 4)
        m["arm_ge2_entered"] = sum(1 for p in P_own if p["own"] >= 2)
        m["arm_ge4_entered"] = sum(1 for p in P_own if p["own"] >= 4)
        m["live_ge2_entered"] = sum(1 for p in P_own if p["l_own"] >= 2)
        m["live_ge4_entered"] = sum(1 for p in P_own if p["l_own"] >= 4)
        m["arm_max"] = max((p["own"] for p in P_own), default=None)
        m["live_max"] = max((p["l_own"] for p in P), default=None)
        m["arm_le15"] = sum(1 for p in P_own if p["own"] <= -1.5)
        m["live_le15"] = sum(1 for p in P if p["l_own"] <= -1.5)

        def dstats(vals):
            if not vals:
                return dict(sum=None, med=None, better=0, worse=0, tie=0, dropbest=None)
            return dict(sum=sum(vals), med=st.median(vals), better=sum(1 for x in vals if x > TIE),
                        worse=sum(1 for x in vals if x < -TIE), tie=sum(1 for x in vals if abs(x) <= TIE),
                        dropbest=sum(vals) - max(vals))
        m["d_cap"] = dstats([p["cap"] - p["l_cap"] for p in P_cap])
        m["d_own"] = dstats([p["own"] - p["l_own"] for p in P_own])
        m["tailclip"] = sum(1 for p in P_cap if p["l_own"] >= 2 and p["cap"] < p["l_cap"] - 0.5)
        m["tailclip_n"] = sum(1 for p in P_cap if p["l_own"] >= 2)
        m["rescue"] = sum(1 for p in P if p["l_own"] <= -0.9 and p["k"] != "no_entry" and p["own"] > 0)
        m["rescue_n"] = sum(1 for p in P if p["l_own"] <= -0.9)
        m["noentry_on_live_loser"] = sum(1 for p in P if p["l_own"] <= -0.9 and p["k"] == "no_entry")
        eng = [p["cap"] - p["rep_cap"] for p in P_cap if p["k"] in ("settled", "horizon") and p["rep_settled"]
               and p["rep_cap"] is not None]
        eng0 = [p["cap"] - p["rep_cap"] for p in P_cap if p["rep_settled"] and p["rep_cap"] is not None]
        m["engine"] = sum(eng) if eng else None
        m["engine_n"] = len(eng)
        m["engine0"] = sum(eng0) if eng0 else None
        m["engine0_n"] = len(eng0)

        def sgn(x):
            return 0 if (x is None or x == 0) else (1 if x > 0 else -1)
        m["engine_agrees"] = (m["engine"] is not None and m["d_cap"]["sum"] is not None
                              and sgn(m["engine"]) == sgn(m["d_cap"]["sum"]))
        m["engine0_agrees"] = (m["engine0"] is not None and m["d_cap"]["sum"] is not None
                               and sgn(m["engine0"]) == sgn(m["d_cap"]["sum"]))
        pd = [p["pct"] - p["l_pct"] for p in P if p["pct"] is not None and p["l_pct"] is not None]
        ad = [p["adr"] - p["l_adr"] for p in P if p["adr"] is not None and p["l_adr"] is not None]
        m["d_pct"] = (sum(pd), st.median(pd), len(pd)) if pd else (None, None, 0)
        m["d_adr"] = (sum(ad), st.median(ad), len(ad)) if ad else (None, None, 0)
        m["readable"] = m["n_cap"] >= 3
        conds = dict(
            rcap_sum_pos=(m["d_cap"]["sum"] or 0) > 0,
            rown_sum_pos=(m["d_own"]["sum"] or 0) > 0,
            dropbest_rcap_pos=(m["d_cap"]["dropbest"] or 0) > 0,
            engine_sign_agrees=m["engine_agrees"],
            tailclip_zero=m["tailclip"] == 0,
            ge4_at_least_live=m["arm_ge4"] >= m["live_ge4"])
        m["conds"] = conds
        m["won"] = m["readable"] and all(conds.values())
        conds0 = dict(conds, engine_sign_agrees=m["engine0_agrees"])
        m["won_engine0"] = m["readable"] and all(conds0.values())
        return m

    def label_for(ms):
        readable = [e for e in ERAS if ms[e]["readable"]]
        lost = [e for e in readable if not ms[e]["won"]]
        if lost:
            lab = "NOT A CANDIDATE"
        elif len(readable) < 2:
            lab = "UNREADABLE"
        elif "E" in readable:
            lab = "WATCH-LIST"
        else:
            lab = "WATCH-LIST, pending era E"
        return lab, readable, lost

    results = {}
    for marks_counted in (False, True):
        for arm in TESTED:
            results[(arm, marks_counted)] = {e: era_metrics(arm, e, marks_counted) for e in ERAS}

    n_horizon = sum(1 for v in cls.values() if v[0] == "horizon")
    for arm in TESTED:
        ms = results[(arm, False)]
        print()
        print("-" * 104)
        print(f"ARM {arm}")
        print("-" * 104)
        for era in ERAS:
            m = ms[era]
            print(f"  era {era}: paired n (R_cap set) = {m['n_cap']}  | R_own set n = {m['n_own']}"
                  f"  | no-entry (0 in R_cap) = {m['n_noentry']}  | rcap_uncomputable = {m['rcap_unc']}"
                  f"  | excluded: {m['excl'] or 'none'}  -> {'READABLE' if m['readable'] else 'not readable (< 3)'}")
            if not m["rows"]:
                continue
            print(f"    TAIL  arm >=+2R {m['arm_ge2']}  >=+4R {m['arm_ge4']}  | live >=+2R {m['live_ge2']}  >=+4R {m['live_ge4']}"
                  f"   (entered-only: arm {m['arm_ge2_entered']}/{m['arm_ge4_entered']}, live {m['live_ge2_entered']}/{m['live_ge4_entered']})")
            print(f"          max R_own: arm {fmt(m['arm_max'])}  live {fmt(m['live_max'])}  | <= -1.5R: arm {m['arm_le15']}  live {m['live_le15']}")
            dc, do = m["d_cap"], m["d_own"]
            print(f"    R_cap delta: sum {fmt(dc['sum'])}  median {fmt(dc['med'])}  better/worse/tie {dc['better']}/{dc['worse']}/{dc['tie']}"
                  f"  drop-best {fmt(dc['dropbest'])}")
            print(f"    R_own delta: sum {fmt(do['sum'])}  median {fmt(do['med'])}  better/worse/tie {do['better']}/{do['worse']}/{do['tie']}"
                  f"  drop-best {fmt(do['dropbest'])}")
            print(f"    tail-clip {m['tailclip']} (of {m['tailclip_n']} fills with live >= +2R)  | rescues {m['rescue']} "
                  f"(of {m['rescue_n']} live losers <= -0.9R; no-entry on a live loser: {m['noentry_on_live_loser']})")
            print(f"    engine check: sum(arm - live_replay) R_cap {fmt(m['engine'], 8, 4)} on {m['engine_n']} both-settled fills "
                  f"-> sign {'AGREES' if m['engine_agrees'] else 'DISAGREES'}   [I6 variant, no-entry at 0: {fmt(m['engine0'], 8, 4)} "
                  f"on {m['engine0_n']} -> {'agrees' if m['engine0_agrees'] else 'disagrees'}]")
            print(f"    context: pct delta sum {fmt(m['d_pct'][0])} median {fmt(m['d_pct'][1])} (n {m['d_pct'][2]})  | "
                  f"adr delta sum {fmt(m['d_adr'][0])} median {fmt(m['d_adr'][1])} (n {m['d_adr'][2]})")
            won_txt = ("WON" if m["won"] else "LOST") if m["readable"] else "n/a (not readable)"
            print(f"    WON test: " + "  ".join(f"{k}={'Y' if v else 'n'}" for k, v in m["conds"].items())
                  + f"  -> {won_txt}")
            print("    per fill:  ticker   cls          live_own  arm_own  d_own  | live_cap  arm_cap  d_cap  | replay_cap")
            for p in m["rows"]:
                d_own = (p["own"] - p["l_own"]) if p["own"] is not None else None
                d_cap = (p["cap"] - p["l_cap"]) if p["cap"] is not None else None
                print(f"               {p['tk']:<7}  {p['k']:<17} {fmt(p['l_own'])} {fmt(p['own'])} {fmt(d_own)} | "
                      f"{fmt(p['l_cap'])} {fmt(p['cap'])} {fmt(d_cap)} | {fmt(p['rep_cap'])}")

    # ── horizon rows ──────────────────────────────────────────────────────────────────────
    hr("SECTION 4 — HORIZON ROWS (marks, never returns)")
    hz = [(live_by_id[t]["ticker"], era_of_trade[t], a, by_trade[t][a]["mark_r"]) for (t, a), v in cls.items() if v[0] == "horizon"]
    print(f"  horizon rows in the cohort: {len(hz)} {hz if hz else ''}")
    if not hz:
        print("  -> no marks exist, so the two label passes below (marks excluded / marks counted) are computed on "
              "identical rows and cannot differ.")

    # ── labels ────────────────────────────────────────────────────────────────────────────
    hr("SECTION 5 — PRE-REGISTERED LABELS (mechanical; computed twice — marks excluded / marks counted)")
    print(f"  {'arm':<28} {'marks excluded':<28} {'marks counted':<28} readable eras -> per-era result")
    labels = {}
    for arm in TESTED:
        l1, rd1, lost1 = label_for(results[(arm, False)])
        l2, rd2, lost2 = label_for(results[(arm, True)])
        final = l1 if l1 == l2 else "UNRESOLVED (horizon)"
        labels[arm] = final
        ms = results[(arm, False)]
        per = "  ".join(f"{e}:{('WON' if ms[e]['won'] else 'LOST') if ms[e]['readable'] else 'unreadable'}(n{ms[e]['n_cap']})"
                        for e in ERAS)
        print(f"  {arm:<28} {l1:<28} {l2:<28} {len(rd1)} -> {per}")
    print("\n  FINAL LABEL per arm:")
    for arm in TESTED:
        print(f"    {arm:<28} {labels[arm]}")
    # I6 sensitivity
    flips = []
    for arm in TESTED:
        ms = results[(arm, False)]
        for e in ERAS:
            if ms[e]["readable"] and ms[e]["won"] != ms[e]["won_engine0"]:
                flips.append((arm, e))
    print(f"\n  I6 sensitivity — eras whose WON/LOST would change if the engine check scored no-entry at 0: "
          f"{flips or 'none'}")
    for arm, e in flips:
        ms = results[(arm, False)]
        others_lost = [x for x in ERAS if x != e and ms[x]["readable"] and not ms[x]["won"]]
        print(f"    {arm} era {e}: label unchanged by it? {'YES — still lost in ' + str(others_lost) if others_lost else 'NO'}")
    alt = []
    for arm in TESTED:
        ms = results[(arm, False)]
        readable = [e for e in ERAS if ms[e]["readable"]]
        if len(readable) < 2:
            alt.append((arm, len(readable), "UNREADABLE"))
    print(f"  I1 sensitivity — arms whose label would read UNREADABLE (not NOT A CANDIDATE) if fewer-than-2-readable "
          f"took precedence over a lost era: {alt or 'none'}")
    print("  harvest_* and trail_* labels are for completeness only; their decision belongs to "
          "live_fill_counterfactuals_first_read_482 (era E, 20 paired fills), which this read does not satisfy.")

    # ── disappoints + fill facts ──────────────────────────────────────────────────────────
    hr("SECTION 6 — 'DISAPPOINTS' PER ERA (live_actual R_cap sum < 0 AND no fill >= +4R) and FILL FACTS")
    for era in ERAS:
        tids = [t for t in era_of_trade if era_of_trade[t] == era and t not in excluded_attr
                and cls[(t, "live_actual")][0] == "settled"]
        caps = [cls[(t, "live_actual")][2] for t in tids]
        owns = [cls[(t, "live_actual")][1] for t in tids]
        dis_all = sum(caps) < 0 and not any(o >= 4 for o in owns)
        ptids = [t for t in tids if fid_pass[t]]
        pc = [cls[(t, "live_actual")][2] for t in ptids]
        po = [cls[(t, "live_actual")][1] for t in ptids]
        dis_p = sum(pc) < 0 and not any(o >= 4 for o in po)
        print(f"  era {era} — ALL cohort fills (I2, the fact): n {len(tids)}  live_actual R_cap sum {fmt(sum(caps))}  "
              f"fills >= +4R {sum(1 for o in owns if o >= 4)}  -> {'DISAPPOINTS' if dis_all else 'does not disappoint'}")
        print(f"           fidelity-passing fills only (beside it): n {len(ptids)}  R_cap sum {fmt(sum(pc))}  "
              f"fills >= +4R {sum(1 for o in po if o >= 4)}  -> {'disappoints' if dis_p else 'does not disappoint'}")
    print("\n  fill facts (fill_facts rows, every cohort fill; descriptive, no threshold):")
    for era in ERAS:
        ff = [by_trade[t][FILL_FACTS] for t in era_of_trade if era_of_trade[t] == era and FILL_FACTS in by_trade[t]]
        fv = [f(r["fill_vs_trigger_pct"]) for r in ff if f(r["fill_vs_trigger_pct"]) is not None]
        rv = [f(r["real_risk_vs_trigger_risk"]) for r in ff if f(r["real_risk_vs_trigger_risk"]) is not None]
        above = [r["ticker"] for r in ff if (f(r["fill_vs_trigger_pct"]) or 0) > 1]
        print(f"    era {era}: n {len(ff)}  fill_vs_trigger_pct median {fmt(st.median(fv))}% max {fmt(max(fv))}% "
              f"count above +1% {len(above)} {above}  | real_risk_vs_trigger_risk median {st.median(rv):.3f} max {max(rv):.3f}")

    # ── Tier 2 ────────────────────────────────────────────────────────────────────────────
    hr("SECTION 7 — TIER 2: 5-MINUTE ORB SHADOW LANE vs the live twin (DESCRIPTIVE; can only nominate)")
    OUT.mkdir(exist_ok=True)
    py = sys.executable
    b_txt, b_json = OUT / "b482_cde.txt", OUT / "b482_dump.json"
    s_txt, s_json = OUT / "s572_cde.txt", OUT / "s572_dump.json"
    with open(b_txt, "w") as fh:
        rc = subprocess.run([py, str(HERE / "bracket_geometry_read_482_cde.py"), "--data-dir", str(DATA),
                             "--dump-json", str(b_json)], stdout=fh, stderr=subprocess.STDOUT, cwd=HERE).returncode
    assert rc == 0, f"bracket_geometry_read_482_cde.py exited {rc} — see {b_txt}"
    with open(s_txt, "w") as fh:
        rc = subprocess.run([py, str(HERE / "geometry_sweep_572_cde.py"), "--data-dir", str(DATA),
                             "--dump-json", str(s_json)], stdout=fh, stderr=subprocess.STDOUT, cwd=HERE).returncode
    assert rc == 0, f"geometry_sweep_572_cde.py exited {rc} — see {s_txt}"
    print(f"  copies run: out/b482_cde.txt, out/s572_cde.txt (their pooled sections are not read).")
    print("  CONFOUND: the 5-minute lane exits on a daily-bar ladder (day-3/5 partial, no +8R partial, no price-armed "
          "breakeven, no depth rule) — entry, stop AND exit all differ from live in every era.")
    print("  The recorder's fidelity check does not apply here: both sides are real rows (live actual vs the shadow lane).")
    bd = json.load(open(b_json))
    sh = {(r["ticker"], r["alert_date"]): r for r in bd if r["lane"] == "5m"}
    lv = {(r["ticker"], r["alert_date"]): r for r in bd if r["lane"] == "1m"}
    cohort_keys = {(lr["ticker"], lr["alert_date"]): t for t, lr in live_by_id.items()}
    pairs = defaultdict(list)
    for k, s in sh.items():
        if k in lv and k in cohort_keys:
            pairs[era_of_trade[cohort_keys[k]]].append((s, lv[k]))
    print(f"  shadow closed rows: {len(sh)}; paired to a cohort fill: {sum(len(v) for v in pairs.values())}; "
          f"era taken from the live twin.")
    t2_ok_eras, t2_fail = [], []
    for era in ERAS:
        ps = sorted(pairs.get(era, []), key=lambda p: p[0]["alert_date"])
        print(f"  era {era}: pairs n = {len(ps)}")
        for s, l in ps:
            dr = s["r"] - l["r"]
            da = (s["adr_units"] - l["adr_units"]) if (s["adr_units"] is not None and l["adr_units"] is not None) else None
            print(f"    {s['ticker']:<6} {s['alert_date']}  R live {fmt(l['r'])}  R 5m {fmt(s['r'])}  dR {fmt(dr)}   "
                  f"ADR live {fmt(l['adr_units'])}  ADR 5m {fmt(s['adr_units'])}  dADR {fmt(da)}   stop% live "
                  f"{l['stop_dist_pct']:.2f} 5m {s['stop_dist_pct']:.2f}")
        if not ps:
            continue
        drs = [s["r"] - l["r"] for s, l in ps]
        das = [s["adr_units"] - l["adr_units"] for s, l in ps if s["adr_units"] is not None and l["adr_units"] is not None]
        print(f"    sums: R live {fmt(sum(l['r'] for _, l in ps))}  5m {fmt(sum(s['r'] for s, _ in ps))}  delta {fmt(sum(drs))}"
              f" drop-best {fmt(sum(drs) - max(drs))}  | ADR live {fmt(sum(l['adr_units'] for _, l in ps if l['adr_units'] is not None))}"
              f"  5m {fmt(sum(s['adr_units'] for s, _ in ps if s['adr_units'] is not None))}  delta {fmt(sum(das))}"
              f" drop-best {fmt(sum(das) - max(das)) if das else 'n/a'}")
        if len(ps) >= 3:
            beats = sum(drs) > 0 and sum(das) > 0 and (sum(drs) - max(drs)) > 0 and (sum(das) - max(das)) > 0
            (t2_ok_eras if beats else t2_fail).append(era)
            print(f"    era with >= 3 pairs -> 5m beats live in both units and survives drop-best (I5): {'YES' if beats else 'NO'}")
    t2_elig = t2_ok_eras + t2_fail
    t2_nom = len(t2_elig) >= 2 and not t2_fail
    print(f"  NOMINATE RULE: eras with >= 3 pairs {sorted(t2_elig)}; beaten in {sorted(t2_ok_eras)} -> "
          f"{'NOMINATE a 5-minute-bar entry arm on the live ladder (shadow only)' if t2_nom else 'NOTHING NOMINATED — the 08-18 finding stands: widening the opening-range bar does not help'}")

    # ── Tier 3 ────────────────────────────────────────────────────────────────────────────
    hr("SECTION 8 — TIER 3: SWEEP COPY (DESCRIPTIVE; can only nominate a recorder arm)")
    print("  EXIT: the sweep's single policy in every era (half off at +2R own unit -> breakeven -> SMA trail -> 20 days);"
          " not the live ladder in D/E, so era slices separate populations, not exits.")
    print("  CONTROL for W is B2 (the live stop inside this engine), never B0. Re-entry is scored as the increment over B0"
          " on days a re-entry fired; conservative sequencing decides, optimistic shown.")
    sd = json.load(open(s_json))
    ex = sd["excluded"]
    print(f"  excluded lists: thin {ex['thin'] or 'none'}; no bars {ex['no_bars'] or 'none'}; "
          f"odd fills (entry <= ORB low) {ex['odd_fills'] or 'none'}; CPDL invalid {ex['cpdl_invalid'] or 'none'}")
    roll = defaultdict(dict)
    for r in sd["rollups"]:
        roll[r["lane"]][r["trade_id"]] = r
    lanes = sorted(roll)
    print("  horizon (closed by the 20-day / data-end stop, marked to last close) per lane per era:")
    for era in ERAS:
        hz_l = {ln: sum(1 for r in roll[ln].values() if r["era"] == era and r["horizon"]) for ln in lanes}
        print(f"    era {era}: " + "  ".join(f"{ln}={v}" for ln, v in hz_l.items()))
    for era in ERAS:
        ne = [r["ticker"] for r in roll["W"].values() if r["era"] == era and not r["entered"]]
        print(f"  W no-entry (scored 0) in era {era}: {len(ne)} {ne}")

    def rule_line(name, per_era):
        elig = [e for e in ERAS if per_era[e] is not None]
        ok = [e for e in elig if per_era[e]]
        nom = len(elig) >= 2 and len(ok) == len(elig)
        print(f"  NOMINATE RULE {name}: eras with >= 3 rows {elig}; beaten in both units + drop-best in {ok} -> "
              f"{'NOMINATE as a recorder arm (shadow only, no money)' if nom else 'not nominated'}")
        return nom

    # W vs B2
    print("\n  W (established intraday low) vs B2, every full-session day, W no-entry = 0:")
    w_res = {}
    for era in ERAS:
        rows_ = []
        for tid, b2 in roll["B2"].items():
            if b2["era"] != era or not b2["entered"]:
                continue
            w = roll["W"][tid]
            wr = w["r"] if w["entered"] else 0.0
            wa = (w["adr_u"] if w["entered"] else 0.0)
            rows_.append((b2["ticker"], wr, b2["r"], wa, b2["adr_u"], w["entered"]))
        print(f"    era {era}: n = {len(rows_)}")
        for tk, wr, br, wa, ba, ent in rows_:
            print(f"      {tk:<6} W R {fmt(wr)} {'(no entry)' if not ent else '          '} B2 R {fmt(br)}  dR {fmt(wr - br)}"
                  f"  | W ADR {fmt(wa)}  B2 ADR {fmt(ba)}  dADR {fmt(wa - ba if (wa is not None and ba is not None) else None)}")
        if rows_:
            dr = [w - b for _, w, b, _, _, _ in rows_]
            da = [w - b for _, _, _, w, b, _ in rows_ if w is not None and b is not None]
            print(f"      sums: W R {fmt(sum(r[1] for r in rows_))}  B2 R {fmt(sum(r[2] for r in rows_))}  dR {fmt(sum(dr))} "
                  f"drop-best {fmt(sum(dr) - max(dr))}  | dADR {fmt(sum(da))} drop-best {fmt(sum(da) - max(da)) if da else 'n/a'}")
            w_res[era] = (sum(dr) > 0 and sum(da) > 0 and sum(dr) - max(dr) > 0 and sum(da) - max(da) > 0) \
                if len(rows_) >= 3 else None
        else:
            w_res[era] = None
    rule_line("W vs B2", w_res)

    # re-entry increments
    for lane_c, lane_o in (("A_cons", "A_opt"), ("Apdl_c", "Apdl_o")):
        print(f"\n  {lane_c} - B0 on days {lane_c} fired a re-entry (conservative decides; {lane_o} shown):")
        res = {}
        for era in ERAS:
            rows_ = []
            for tid, a in roll[lane_c].items():
                if a["era"] != era or a["n_attempts"] <= 1:
                    continue
                b0 = roll["B0"][tid]
                o = roll[lane_o][tid]
                rows_.append((a["ticker"], a["r"] - b0["r"],
                              (a["adr_u"] - b0["adr_u"]) if (a["adr_u"] is not None and b0["adr_u"] is not None) else None,
                              (o["r"] - b0["r"]) if o["entered"] else None, o["n_attempts"]))
            print(f"    era {era}: re-entry days n = {len(rows_)}")
            for tk, dr, da, dro, no in rows_:
                print(f"      {tk:<6} increment R {fmt(dr)}  ADR {fmt(da)}   | {lane_o}: increment R {fmt(dro)} (attempts {no})")
            if rows_:
                drs = [x[1] for x in rows_]
                das = [x[2] for x in rows_ if x[2] is not None]
                print(f"      sums: R {fmt(sum(drs))} drop-best {fmt(sum(drs) - max(drs))}  | ADR {fmt(sum(das))} "
                      f"drop-best {fmt(sum(das) - max(das)) if das else 'n/a'}")
                res[era] = (sum(drs) > 0 and sum(das) > 0 and sum(drs) - max(drs) > 0 and sum(das) - max(das) > 0) \
                    if len(rows_) >= 3 else None
            else:
                res[era] = None
        rule_line(f"{lane_c} (re-entry)", res)
    print("\n  C05 / C10 / CPDL: printed by the copy (out/s572_cde.txt), NOT read — the recorder's ADR and ORB stop arms "
          "answer that question on the live ladder.")

    hr("END — no line above pools eras. Interpretation: PREREG.md '## RESULT — 2026-11-06' and "
       "docs/analysis/482_cross_arm_read_2026-11-06.md")


if __name__ == "__main__":
    main()
