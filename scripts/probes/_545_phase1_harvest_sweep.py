#!/usr/bin/env python3
"""#545 Phase 1 — THE DAY-1 HARVEST HOLE (docs/design/545_entry_exit_program_2026-09-05.md §7).

READ-ONLY, $0, captures only (scripts/ep_replay_data/ + scripts/probes/_562bf_minute.tsv.gz).
Nothing live is touched; THE LINE applies. Walks the SAME 267 live-source alert campaigns
(05-11 -> 08-28) Phase 3 walked, under the harvest cells Phase 3 never ran:

  - the LIVE ladder (entry-2R stop, +2R partial, breakeven-at-partial, SMA10/20 trail) — the
    baseline every cell below is paired against. This is RULESETS["era_c"], the "LIVE" tag
    used throughout the design doc's own tables (the doc predates the 09-06 era-D flip to an
    8R partial / breakeven-at-3R; era D is a SEPARATE, later change and out of this card's
    scope — see "what this does not answer").
  - no partial at all: stop + trail only (era_c_partial_none, already in RULESETS) and stop +
    hold with the trail also removed (era_c_partial_none, trail_mode="none" — one new cell,
    no new code: RuleSet already exposes trail_mode="none").
  - partial without breakeven: era_c_no_breakeven (ladder trail stays active, breakeven never
    arms) and runner_rule="hard" (no trail either — rides the ORIGINAL stop). Both already
    expressible; "hard" is the Phase 3 cell the design doc calls "already run".
  - a SECOND partial rung (5R/8R/10R) on top of a tight stop (0.5xADR, ORB low), riding
    "hard" or "t3" after — the one genuinely new mechanism (RuleSet.second_partial_r, added
    to scripts/ep_replay.py this card, 2026-09-22).

Output: scripts/probes/_545_phase1_harvest_sweep_out.txt (this script's stdout) and
scripts/probes/_545_phase1_harvest_sweep.tsv (one row per cell x campaign, for drop-best /
per-name lookups). docs/analysis/545_phase1_harvest_hole_2026-09-22.md reads the .txt.
"""
from __future__ import annotations

import statistics as st
import sys
from collections import Counter
from dataclasses import replace
from datetime import date, datetime, time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import ep_replay as ep  # noqa: E402
from ep_replay import (  # noqa: E402
    DATA, RULESETS, LAST_SETTLED, load_minutes, load_daily, load_minutes_extra,
    walk_campaign, _scoring_context, _score_one,
)

MAY = "2026-05"
OUT_TSV = REPO / "scripts" / "probes" / "_545_phase1_harvest_sweep.tsv"
OPERATOR_NAMES = [("PLTR", "2026-08-04"), ("TEAM", "2026-08-07"), ("HTFL", "2026-08-14"),
                  ("MRNA", "2026-08-19")]
LIVE = "live_2r_partial_be_trail"


# ── population (identical dedupe rule to phase_replay / _545p3_sweep.py) ────────────────

def load_all():
    s2, s3, conf, adv, regime_rows = _scoring_context()
    minutes, daily, extra = load_minutes(), load_daily(), load_minutes_extra()
    alerts, seen = [], set()
    for a in s2["ALERTS"]:
        # 270 rows -> 267 campaigns: MANE 07-15, KMT 08-05, ACMR 08-07 duplicate-inserted
        # within one millisecond (same score, same tier). One campaign per (ticker, day).
        if (a["ticker"], a["alert_date"]) in seen:
            continue
        seen.add((a["ticker"], a["alert_date"]))
        a = {**a, "confidence_multiplier": conf.get(a["id"])}
        ad, sc = _score_one(a, RULESETS["era_c"], daily, adv, regime_rows)
        submit = time(9, 31)
        if a["detected_at_et"]:
            det = datetime.fromisoformat(a["detected_at_et"]).time()
            submit = max(submit, time(det.hour, det.minute))
        alerts.append({"id": a["id"], "ticker": a["ticker"], "alert_date": ad, "submit": submit,
                       "admit": sc["admit"], "tier": a["score_tier"]})
    return s2, alerts, minutes, daily, extra, regime_rows


def walk_alerts(alerts, rs, minutes, daily, extra) -> dict[tuple, dict]:
    res = {}
    for a in alerts:
        r = walk_campaign(ticker=a["ticker"], alert_date=a["alert_date"], rs=rs,
                          minutes=minutes, daily=daily, submit=a["submit"],
                          minutes_extra=extra)
        r["admit"] = a["admit"]
        r["id"] = a["id"]
        res[a["id"]] = r
    return res


def regime_before(regime_rows, alert_date: date):
    """Strictly-prior regime row — live_tracker.py:523 / ep_replay._score_one's own rule:
    the trade's stamp is the PRIOR session's regime, never same-day (look-ahead)."""
    best = None
    ad = alert_date.isoformat()
    for r in regime_rows:
        if r["regime_date"] < ad:
            best = r["regime"]
        else:
            break
    return best


# ── stats (tail-first: >=3R / >=5R / p90, THEN median, THEN sum — analysis_standard.md) ──

def _p90(xs):
    xs = sorted(xs)
    if not xs:
        return None
    return xs[max(0, int(round(0.9 * (len(xs) - 1))))]


def _stats(xs):
    xs = sorted(xs)
    n = len(xs)
    if n == 0:
        return {"n": 0}
    return {"n": n, "sum": sum(xs), "mean": st.mean(xs), "med": st.median(xs), "p90": _p90(xs),
            "ge3": sum(x >= 3 for x in xs), "ge5": sum(x >= 5 for x in xs),
            "max": max(xs), "win": sum(x > 0 for x in xs)}


def _fmt(d):
    if d["n"] == 0:
        return "n=0"
    return (f"n={d['n']:3d}  >=3R={d['ge3']:2d}  >=5R={d['ge5']:2d}  p90={d['p90']:+5.2f}  "
            f"| med={d['med']:+5.2f} mean={d['mean']:+5.2f} sum={d['sum']:+7.1f} "
            f"win={d['win']:2d}")


def drop_best(xs):
    """The pass bar's own drop-best check: does the >=3R count survive removing the single
    largest R in the sample? (a name-concentration check, not a per-ticker one — the ticker
    breakdown sits beside every table this feeds.)"""
    if not xs:
        return 0, 0
    ge3 = sum(x >= 3 for x in xs)
    rest = sorted(xs)[:-1]
    return ge3, sum(x >= 3 for x in rest)


# ── cell definitions (all built from era_c via dataclasses.replace — none touch RULESETS) ─

def build_cells() -> dict[str, ep.RuleSet]:
    base = RULESETS["era_c"]          # the LIVE ladder this whole design doc calls "live"
    cells = {LIVE: base}

    # ── no partial at all ──
    cells["no_partial_trail_only"] = RULESETS["era_c_partial_none"]
    cells["no_partial_hold"] = replace(RULESETS["era_c_partial_none"],
                                       name="no_partial_hold", trail_mode="none")

    # ── partial, no breakeven ──
    cells["partial_no_be_trail"] = RULESETS["era_c_no_breakeven"]          # trail stays live
    cells["partial_no_be_hard"] = replace(base, name="partial_no_be_hard", runner_rule="hard")

    # ── second partial rung on a tight stop (RuleSet.second_partial_r, new this card) ──
    tight_stops = {"adr_0.5": replace(base, name="adr_0.5", stop_mode="adr_k", adr_k=0.5),
                   "orb_low": replace(base, name="orb_low", stop_mode="orb_low")}
    for sname, srs in tight_stops.items():
        for r2 in (5.0, 8.0, 10.0):
            for runner in ("hard", "t3"):
                nm = f"{sname}_2ndR{int(r2)}_{runner}"
                cells[nm] = replace(srs, name=nm, runner_rule=runner, second_partial_r=r2)
    return cells


# ── reporting ─────────────────────────────────────────────────────────────────────────

def main() -> None:
    s2, alerts, minutes, daily, extra, regime_rows = load_all()
    print(f"population: {len(alerts)} distinct live-source alert campaigns (270 rows, 3 "
          f"same-ms duplicate inserts dropped) {min(a['alert_date'] for a in alerts)} -> "
          f"{max(a['alert_date'] for a in alerts)}; horizon {LAST_SETTLED}")
    cells = build_cells()
    print(f"cells: {len(cells)} -> {list(cells)}")

    results: dict[str, dict[tuple, dict]] = {}
    for name, rs in cells.items():
        results[name] = walk_alerts(alerts, rs, minutes, daily, extra)
    live = results[LIVE]
    live_settled_admit = {k for k, r in live.items()
                          if r["status"] == "settled" and r["admit"] == "admit"}

    rows_out = []
    for name, res in results.items():
        for r in res.values():
            rows_out.append({**r, "cell": name})
    cols = ["cell", "id", "ticker", "alert_date", "admit", "status", "reason", "entered",
            "entry_px", "stop", "target", "partial_fired", "partial2_fired", "final_reason",
            "realized_r", "mark_r", "gap_through"]
    with open(OUT_TSV, "w") as fh:
        fh.write("|".join(cols) + "\n")
        for r in rows_out:
            fh.write("|".join("" if r.get(c) is None else str(r.get(c)) for c in cols) + "\n")
    print(f"written: {OUT_TSV} ({len(rows_out)} rows)\n")

    print("R = each cell's OWN unit at equal dollar risk. Near-zero (<0.5% of entry) stops: "
          "0 in the Phase-3 capture this population shares (stated 2026-09-05, re-confirmed "
          "below).")
    degenerate = [r for r in live.values() if r["status"] == "settled" and r["entry_px"]
                 and r["stop"] is not None
                 and abs(r["entry_px"] - r["stop"]) / r["entry_px"] * 100 < 0.5]
    print(f"  near-zero-stop rows excluded from the LIVE cell: {len(degenerate)}\n")

    def rvals(res, pred):
        return [r["realized_r"] for r in res.values()
                if r["status"] == "settled" and r["realized_r"] is not None and pred(r)]

    def mvals(res, pred):
        return [r["mark_r"] for r in res.values()
                if r["status"] == "open_at_horizon" and r["mark_r"] is not None and pred(r)]

    admit = lambda r: r["admit"] == "admit"                                      # noqa: E731
    admit_exmay = lambda r: r["admit"] == "admit" and str(r["alert_date"])[:7] != MAY  # noqa: E731

    for name in cells:
        res = results[name]
        print(f"===== {name} =====")
        for label, pred in (("all alerts", lambda r: True), ("admitted", admit),
                            ("admitted ex-May", admit_exmay)):
            xs = rvals(res, pred)
            s = _stats(xs)
            print(f"  settled, {label:<16} {_fmt(s)}")
        # censoring: settled vs open-at-horizon MARKS, admitted
        xs_settled = rvals(res, admit)
        xs_marks = mvals(res, admit)
        s_s, s_m = _stats(xs_settled), _stats(xs_marks)
        s_both = _stats(xs_settled + xs_marks)
        print(f"  settled+marks, admitted        {_fmt(s_both)}   "
              f"(settled n={s_s['n']} sum={s_s.get('sum', 0) or 0:+.1f} | "
              f"open marks n={s_m['n']} sum={s_m.get('sum', 0) or 0:+.1f})")
        ge3_all, ge3_dropbest = drop_best(xs_settled + xs_marks)
        print(f"  drop-best (admitted, settled+marks): >=3R {ge3_all} -> {ge3_dropbest} "
              "without the single largest R")
        # paired vs LIVE on the live cell's admitted+settled rows
        paired = [(res[k]["realized_r"], live[k]["realized_r"]) for k in live_settled_admit
                  if res[k]["status"] == "settled" and res[k]["realized_r"] is not None]
        dropped = len(live_settled_admit) - len(paired)
        if name != LIVE and paired:
            d = [a - b for a, b in paired]
            a_ge3 = sum(1 for a, _ in paired if a >= 3)
            b_ge3 = sum(1 for _, b in paired if b >= 3)
            print(f"  PAIRED vs live (live's admitted+settled rows): n={len(paired)} "
                  f"dropped={dropped}  d>=3R={a_ge3 - b_ge3:+d} (cell {a_ge3} vs live {b_ge3})  "
                  f"dSum={sum(d):+.1f}  dMed={st.median([a for a, _ in paired]) - st.median([b for _, b in paired]):+.2f}")
        # regime cut
        for reg_label, reg_pred in (("Bull", lambda r: regime_before(regime_rows, r["alert_date"]) == "Bull"),
                                    ("non-Bull", lambda r: regime_before(regime_rows, r["alert_date"]) != "Bull")):
            xs = rvals(res, lambda r: admit(r) and reg_pred(r))
            print(f"  regime {reg_label:<9}              {_fmt(_stats(xs))}")
        # the four operator-labelled names
        vals = {}
        for t, dt in OPERATOR_NAMES:
            row = next((r for r in res.values() if r["ticker"] == t and str(r["alert_date"]) == dt), None)
            if row is None:
                vals[t] = "not in population"
            elif row["status"] == "settled":
                vals[t] = f"{row['realized_r']:+.2f}R"
            elif row["status"] == "open_at_horizon":
                vals[t] = f"open mark {row['mark_r']:+.2f}R" if row["mark_r"] is not None else "open, no mark"
            else:
                vals[t] = row["status"]
        print(f"  operator-labelled: {vals}")
        # ticker breakdown of the >=3R names (settled+marks, admitted) — the concentration check
        by_r: dict[str, float] = {}
        is_mark: dict[str, bool] = {}
        for rr in res.values():
            if not admit(rr):
                continue
            if rr["status"] == "settled" and rr["realized_r"] is not None:
                by_r[rr["id"]] = rr["realized_r"]
                is_mark[rr["id"]] = False
            elif rr["status"] == "open_at_horizon" and rr["mark_r"] is not None:
                by_r[rr["id"]] = rr["mark_r"]
                is_mark[rr["id"]] = True
        names3 = sorted(
            [(v, res[i]["ticker"], str(res[i]["alert_date"]), is_mark[i])
             for i, v in by_r.items() if v >= 3],
            reverse=True)
        print(f"  >=3R names (settled+marks, admitted): "
              f"{[(f'{v:+.1f}', tk, dt, 'MARK' if m else '') for v, tk, dt, m in names3]}")
        print()

    print("abstain reasons (LIVE cell): " +
          str(dict(Counter(r["reason"].split(":")[0] for r in live.values()
                           if r["status"] == "abstain"))))
    print(f"\nwritten: {OUT_TSV}")


if __name__ == "__main__":
    main()
