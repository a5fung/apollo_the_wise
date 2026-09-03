#!/usr/bin/env python3
"""#545 Phase 3 — the joint day-1 stop × target × runner sweep on scripts/ep_replay.py.

READ-ONLY, $0, captures only (scripts/ep_replay_data/ + scripts/probes/_562bf_minute.tsv.gz).
Pre-registered in docs/design/545_entry_exit_program_v2_2026-09-02.md §7 Phase 3; the pass bar
is written there and is not moved here. THE LINE: evidence only — nothing live is touched.

What this runs (every cell = the same 270 live-source alert campaigns, 05-11 → 08-31, walked
under the CURRENT (era C) admission + exit stack with ONE axis varied at a time, plus the
pre-registered joint cells):
  1. prerequisite 2 — the 26 closed live trades (22 pre-2R + 4 era C) re-walked under era_c and
     every ADR-anchored stop: how many still die on the entry day, at equal dollar risk;
  2. the stop grid — orb_low · entry−2R (live) · entry − k×ADR20$ for k = 0.5/0.75/1.0/1.25,
     target PINNED to the ORB frame (live) AND, as the 08-06 mechanism check only, +2R of the
     stop's own distance;
  3. the runner grid — the #2 lineage's 13 post-partial rules at every stop (pinned frame);
  4. the attempt-2 leg — the #5 lineage's three placeable re-entries at the live stop and at the
     ORB-low stop (the operator's tight-stop-more-tries shape), per-name accounting;
  5. the retirement reproductions — #2 (+0.33R scratch share, median flip), #5 (SD-5mclear on the
     17 live stop-outs), #8 (volatility-stop ordering on the live day-0 cohort);
  6. the internal consistency check — runner "live_trail_be" (harness-side) vs "live" (the ladder).

Outputs (capture once, read many): scripts/probes/_545p3_cells.tsv (one row per cell × campaign)
and scripts/probes/_545p3_report.txt (this script's stdout). The analysis doc reads those.
"""
from __future__ import annotations

import statistics as st
import sys
from collections import Counter, defaultdict
from dataclasses import replace
from datetime import date, datetime, time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import ep_replay as ep  # noqa: E402
from ep_replay import (  # noqa: E402
    DATA, RULESETS, RUNNER_RULES, REENTRY_SIGNALS, LAST_SETTLED, read_sections,
    load_minutes, load_daily, load_minutes_extra, walk_campaign, ruleset_as_of,
    _scoring_context, _score_one,
)

_f = ep._f
OUT_TSV = REPO / "scripts" / "probes" / "_545p3_cells.tsv"
ADR_KS = (0.5, 0.75, 1.0, 1.25)
MAY = "2026-05"
ERA_C_ADMISSION = "2026-08-22"       # rubric separation date — the current admission stack


def stop_rulesets() -> dict[str, ep.RuleSet]:
    base = RULESETS["era_c"]
    out = {
        "orb_low": replace(base, name="orb_low", stop_mode="orb_low"),
        "entry_minus_2r": base,
    }
    for k in ADR_KS:
        out[f"adr_{k}"] = replace(base, name=f"adr_{k}", stop_mode="adr_k", adr_k=k)
    return out


def cell_name(stop: str, frame: str, runner: str, attempts: int = 1, sig: str = "") -> str:
    s = f"{stop}/{frame}/{runner}"
    if attempts > 1:
        s += f"/x{attempts}:{sig}"
    return s


# ── population & walkers ─────────────────────────────────────────────────────────────

def load_all():
    s2, s3, conf, adv, regime_rows = _scoring_context()
    minutes, daily, extra = load_minutes(), load_daily(), load_minutes_extra()
    alerts, seen = [], set()
    for a in s2["ALERTS"]:
        # 270 rows = 267 campaigns: MANE 07-15, KMT 08-05, ACMR 08-07 were inserted twice
        # within a millisecond (same score, same tier). One campaign per (ticker, day).
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
    return s2, alerts, minutes, daily, extra


def walk_alerts(alerts, rs, minutes, daily, extra) -> dict[tuple, dict]:
    res = {}
    for a in alerts:
        r = walk_campaign(ticker=a["ticker"], alert_date=a["alert_date"], rs=rs,
                          minutes=minutes, daily=daily, submit=a["submit"],
                          minutes_extra=extra)
        r["admit"] = a["admit"]
        r["id"] = a["id"]
        res[a["id"]] = r          # keyed by ALERT ID — one (ticker, date) pair alerts twice
    return res


def walk_trades(trades, alerts_by, rs_for, minutes, daily, extra, shares_none=True):
    """Re-walk the closed real trades from their STORED ORB (a fact of the day) under rs_for(t).
    Sizing normalised to 1 risk unit on each cell's own stop (equal dollar risk)."""
    rows = []
    for t in trades:
        ad = date.fromisoformat(t["alert_date"])
        al = alerts_by.get((t["ticker"], t["alert_date"]))
        submit = time(9, 31)
        if al and al["detected_at_et"]:
            det = datetime.fromisoformat(al["detected_at_et"]).time()
            submit = max(submit, time(det.hour, det.minute))
        rs = rs_for(t)
        r = walk_campaign(ticker=t["ticker"], alert_date=ad, rs=rs, minutes=minutes,
                          daily=daily, submit=submit, orb_high=_f(t["orb_high"]),
                          orb_low=_f(t["orb_low"]), atr_14=_f(t["atr_14"]),
                          shares=None if shares_none else _f(t["entry_shares"]),
                          integer_shares=not shares_none, minutes_extra=extra)
        r["live_r"] = None
        risk = _f(t["risk_dollars_actual"]) or _f(t["risk_dollars"])
        if risk:
            r["live_r"] = _f(t["total_pnl"]) / risk
        r["live_day0"] = (t["closed_at_et"] or "")[:10] == t["alert_date"]
        r["era"] = ruleset_as_of(ad).stop_mode
        r["day0_stop"] = any(e["reason"] == "stop_hit" and str(e["time"])[:10] == t["alert_date"]
                             for e in r["exits"])
        rows.append(r)
    return rows


# ── summaries ────────────────────────────────────────────────────────────────────────

def _p90(xs):
    xs = sorted(xs)
    if not xs:
        return None
    k = max(0, int(round(0.9 * (len(xs) - 1))))
    return xs[k]


def summarise(rows: list[dict], key="realized_r") -> dict:
    """P3 order: sum · ≥4R · ≥2R · P90 · ex-best · then mean/median/win. Settled only; open
    rows reported beside as MARKS."""
    settled = [r for r in rows if r["status"] == "settled" and r.get(key) is not None]
    xs = [r[key] for r in settled]
    opens = [r for r in rows if r["status"] == "open_at_horizon"]
    marks = [r["mark_r"] for r in opens if r.get("mark_r") is not None]
    adr = [r["pnl_adr"] for r in settled if r.get("pnl_adr") is not None]
    out = {"n": len(xs), "n_open": len(opens), "n_abstain": sum(1 for r in rows if r["status"] == "abstain"),
           "sum": sum(xs) if xs else None, "ge4": sum(1 for x in xs if x >= 4),
           "ge2": sum(1 for x in xs if x >= 2), "p90": _p90(xs),
           "ex_best": (sum(xs) - max(xs)) if xs else None,
           "mean": st.mean(xs) if xs else None, "median": st.median(xs) if xs else None,
           "win": (sum(1 for x in xs if x > 0) / len(xs)) if xs else None,
           "losers": sum(1 for x in xs if x < 0),
           "sum_adr": sum(adr) if adr else None,
           "mark_sum": sum(marks) if marks else None,
           "partials": sum(1 for r in settled if r["partial_fired"]),
           "scratch_third": sum(1 for r in settled if r["partial_fired"]
                                and abs((r[key] or 0) - 1 / 3) < 0.02)}
    return out


def fmt(s: dict) -> str:
    if s["n"] == 0:
        return f"n=0 (open {s['n_open']}, abstain {s['n_abstain']})"
    return (f"n={s['n']:<3} sum {s['sum']:+7.2f}R  >=4R {s['ge4']}  >=2R {s['ge2']:<2} "
            f"P90 {s['p90']:+5.2f}  ex-best {s['ex_best']:+7.2f}  mean {s['mean']:+.3f}  "
            f"med {s['median']:+.2f}  win {s['win']:.0%}  losers {s['losers']:<3} "
            f"ADR-units {s['sum_adr']:+7.2f} | open {s['n_open']} mark {(s['mark_sum'] or 0):+.2f}R "
            f"abstain {s['n_abstain']} | partials {s['partials']} scratch@+0.33 {s['scratch_third']}")


def split(rows, which):
    if which == "all":
        return rows
    if which == "ex_may":
        return [r for r in rows if str(r["alert_date"])[:7] != MAY]
    if which == "aug_admission":
        return [r for r in rows if str(r["alert_date"]) >= ERA_C_ADMISSION]
    raise ValueError(which)


def main() -> None:
    s2, alerts, minutes, daily, extra = load_all()
    alerts_by = {(a["ticker"], a["alert_date"]): a for a in s2["ALERTS"]}
    stops = stop_rulesets()
    print(f"population: {len(alerts)} distinct live-source alert campaigns (270 rows, 3 same-ms duplicate inserts dropped) {min(a['alert_date'] for a in alerts)} → "
          f"{max(a['alert_date'] for a in alerts)}; supplementary minute sessions: {len(extra)}; "
          f"horizon {LAST_SETTLED}")

    # ═══ 1. PREREQUISITE 2 — the closed live trades under the current stack ═══
    print("\n══ 1. PREREQUISITE 2 — did the 08-16 widening work? the 26 closed live trades re-walked, "
          "equal dollar risk per cell (stored ORB, first attempts) ══")
    live = [t for t in s2["TRADES"] if t["account_mode"] == "live" and int(t["entry_attempt"]) == 1
            and not any("manual" in (e.get("reason") or "") for e in __import__("json").loads(t["exits_json"] or "[]"))]
    pre = [t for t in live if date.fromisoformat(t["alert_date"]) < ep.STOP_2R_DATE]
    post = [t for t in live if date.fromisoformat(t["alert_date"]) >= ep.STOP_2R_DATE]
    print(f"  live rows: {len(live)} (pre-2R {len(pre)}, era C {len(post)})")
    live_d0_pre = sum(1 for t in pre if (t['closed_at_et'] or '')[:10] == t['alert_date'])
    live_d0_post = sum(1 for t in post if (t['closed_at_et'] or '')[:10] == t['alert_date'])
    print(f"  LIVE as recorded: pre-2R day-0 deaths {live_d0_pre}/{len(pre)}, era C {live_d0_post}/{len(post)}")
    cells = {"era_matched": (lambda t: ruleset_as_of(date.fromisoformat(t["alert_date"])))}
    for name, rs in stops.items():
        cells[name] = (lambda t, rs=rs: rs)
    prereq_rows = []
    for name, rs_for in cells.items():
        rows = walk_trades(live, alerts_by, rs_for, minutes, daily, extra)
        for r in rows:
            r["cell"] = f"live26/{name}"
        prereq_rows += rows
        for label, sub in (("pre-2R 22", [r for r in rows if r["era"] == "orb_low"]),
                           ("era-C 4", [r for r in rows if r["era"] == "entry_minus_2r"])):
            dec = [r for r in sub if r["status"] in ("settled", "open_at_horizon")]
            d0 = sum(1 for r in dec if r["day0_stop"])
            abst = [r["ticker"] for r in sub if r["status"] == "abstain"]
            s = summarise(sub)
            print(f"  {name:<15} {label:<9} decidable {len(dec):<2} day-0 deaths {d0:<2} "
                  f"({d0 / len(dec):.0%} of decidable) | {fmt(s)} | abstain {abst}")
        if name == "era_matched":
            lr = [r["live_r"] for r in rows if r["live_r"] is not None]
            print(f"    (live recorded R, {len(lr)} rows: sum {sum(lr):+.2f}, "
                  f"pre-2R sum {sum(r['live_r'] for r in rows if r['era'] == 'orb_low'):+.2f})")
    # per-name day-0 fate under each stop (the bridge table)
    print("\n  per-name entry-day fate (S = stopped on entry day, P = partial banked, . = survived day 0, a = abstain, - = no fill):")
    names = [(t["ticker"], t["alert_date"]) for t in live]
    hdr = "  " + "ticker/date".ljust(18) + "".join(n[:14].ljust(15) for n in cells)
    print(hdr)
    by = defaultdict(dict)
    for r in prereq_rows:
        by[(r["ticker"], str(r["alert_date"]))][r["cell"].split("/")[1]] = r
    for tk, ad in names:
        line = f"  {tk:<6}{ad[5:]:<12}"
        for n in cells:
            r = by[(tk, ad)].get(n)
            if r is None:
                line += "?".ljust(15)
                continue
            if r["status"] == "abstain":
                mark = "a"
            elif not r["entered"]:
                mark = "-"
            elif r["day0_stop"]:
                mark = "S" + ("P" if r["partial_fired"] else "")
            else:
                mark = ("P" if r["partial_fired"] else ".")
            rr = r["realized_r"] if r["status"] == "settled" else r.get("mark_r")
            line += f"{mark:<3}{(rr if rr is not None else float('nan')):+6.2f}{'*' if r['status']=='open_at_horizon' else ' '}".ljust(15)
        print(line)

    # ═══ 2 + 3. THE GRID on the 270 alerts ═══
    print("\n══ 2. STOP GRID — 270 alert campaigns, current stack, runner = live ladder ══")
    grid: dict[str, dict[tuple, dict]] = {}
    for sname, rs in stops.items():
        for frame in ("orb", "own"):
            if sname == "orb_low" and frame == "own":
                continue          # identical by construction (R frame IS entry − orb_low)
            rsx = replace(rs, name=f"{sname}/{frame}", target_frame=frame)
            grid[cell_name(sname, frame, "live")] = walk_alerts(alerts, rsx, minutes, daily, extra)
    control = grid[cell_name("entry_minus_2r", "orb", "live")]
    ctrl_settled = {k for k, r in control.items() if r["status"] == "settled"}
    print(f"  control (entry−2R, pinned, live ladder): {Counter(r['status'] for r in control.values())}")
    print(f"  no_trade reasons: {Counter(r['reason'].split(':')[0] for r in control.values() if r['status']=='no_trade')}")
    print(f"  abstain reasons: {Counter(r['reason'].split(':')[0] for r in control.values() if r['status']=='abstain')}")
    for frame in ("orb", "own"):
        print(f"\n  ── target frame: {'PINNED to entry−orb_low (live)' if frame=='orb' else 'the stop\'s OWN distance (08-06 frame, mechanism check only)'} ──")
        for sname in stops:
            key = cell_name(sname, frame, "live")
            if key not in grid:
                continue
            rows = list(grid[key].values())
            tight = sum(1 for r in rows if r["entered"] and r["stop"] is not None and r.get("adr_dollar")
                        and sname.startswith("adr") and r["stop"] > (r["entry_px"] or 0) - 1e-9)
            widths = [r["stop_width_adr"] for r in rows if r.get("stop_width_adr")]
            for which in ("all", "ex_may", "aug_admission"):
                s = summarise(split(rows, which))
                print(f"  {sname:<15} {which:<13} {fmt(s)}")
            if widths:
                print(f"  {'':<15} stop width in ADR units: median {st.median(widths):.2f} "
                      f"(min {min(widths):.2f}, max {max(widths):.2f}); abstain reasons "
                      f"{dict(Counter(r['reason'].split(':')[0] for r in rows if r['status']=='abstain'))}")
    # paired deltas vs control on the control's settled cohort
    print("\n  ── PAIRED vs control (campaigns settled under the control; a cell's row that is open/abstain is dropped and counted) ──")
    for key, res in grid.items():
        paired = [(res[k]["realized_r"], control[k]["realized_r"]) for k in ctrl_settled
                  if res[k]["status"] == "settled"]
        dropped = len(ctrl_settled) - len(paired)
        if not paired:
            continue
        d = [a - b for a, b in paired]
        better = sum(1 for x in d if x > 1e-9)
        worse = sum(1 for x in d if x < -1e-9)
        print(f"  {key:<32} pairs {len(paired):<3} dropped {dropped:<2} ΔR sum {sum(d):+7.2f}  "
              f"better {better:<3} worse {worse:<3} Δ≥4R {sum(1 for a,b in paired if a>=4) - sum(1 for a,b in paired if b>=4):+d}")

    print("\n══ 3. RUNNER GRID — the 13 post-partial rules (#2 lineage) at every stop, pinned frame ══")
    for sname, rs in stops.items():
        print(f"\n  ── stop {sname} ──")
        live_cell = grid[cell_name(sname, "orb", "live")]
        takers = {k for k, r in live_cell.items() if r["status"] == "settled" and r["partial_fired"]}
        for runner in RUNNER_RULES:
            rsx = replace(rs, name=f"{sname}/orb/{runner}", target_frame="orb", runner_rule=runner)
            res = walk_alerts(alerts, rsx, minutes, daily, extra)
            grid[cell_name(sname, "orb", runner)] = res
            if runner == "live_trail_be":
                mism = [(k, res[k]["realized_r"], live_cell[k]["realized_r"]) for k in live_cell
                        if (res[k]["status"], round(res[k]["realized_r"] or 0, 6))
                        != (live_cell[k]["status"], round(live_cell[k]["realized_r"] or 0, 6))]
                print(f"  CONSISTENCY live_trail_be vs live ladder: {len(mism)} of {len(live_cell)} campaigns differ "
                      f"{[(live_cell[k]['ticker'], str(live_cell[k]['alert_date']), round(a or 0,2), round(b or 0,2)) for k, a, b in mism][:8]}")
            for which in ("all", "ex_may"):
                rows = split(list(res.values()), which)
                s = summarise(rows)
                tk = [r for r in rows if r["id"] in takers and r["status"] == "settled"]
                st_ = summarise(tk)
                print(f"  {runner:<14} {which:<7} ALL {fmt(s)}")
                print(f"  {'':<14} {'':<7} partial-takers n={st_['n']:<3} sum {st_['sum'] or 0:+7.2f} "
                      f"mean {(st_['mean'] or 0):+.3f} med {(st_['median'] or 0):+.2f} win {(st_['win'] or 0):.0%} "
                      f">=4R {st_['ge4']} scratch@+0.33 {st_['scratch_third']}")

    print("\n══ 4. ATTEMPT-2 LEG — one re-entry after a full stop-out (#5 lineage's signals), per-name accounting ══")
    for sname in ("entry_minus_2r", "orb_low", "adr_0.5"):
        for sig in REENTRY_SIGNALS:
            rsx = replace(stops[sname], name=f"{sname}/orb/live/x2:{sig}", attempts=2, reentry_signal=sig)
            res = walk_alerts(alerts, rsx, minutes, daily, extra)
            grid[cell_name(sname, "orb", "live", 2, sig)] = res
            base = grid[cell_name(sname, "orb", "live")]
            fired = [r for r in res.values() if r["attempts_fired"] == 2]
            eligible = [r for r in res.values() if r["status"] in ("settled", "open_at_horizon")
                        and r["final_reason"] == "stop_hit" and not r["partial_fired"]]
            l2 = [r["leg2_r"] for r in fired if r["leg2_r"] is not None]
            second_stops = sum(1 for x in l2 if x <= -0.5)
            held = sum(1 for x in l2 if x >= 0.5)
            camp = [r for r in res.values() if r["status"] == "settled"]
            cr = [r["campaign_r"] for r in camp]
            base_cr = [base[r["id"]]["realized_r"] for r in camp
                       if base[r["id"]]["status"] == "settled"]
            worst = min(cr) if cr else None
            ge4 = sum(1 for x in cr if x >= 4)
            l2s = Counter(r["leg2_status"] for r in res.values() if r["leg2_status"])
            print(f"  {sname:<15} {sig:<12} eligible stop-outs {len(eligible):<3} fired {len(fired):<3} "
                  f"leg-2 sum {sum(l2):+7.2f}R  second stops {second_stops:<3} held(≥+0.5R) {held:<3} "
                  f"leg-2 ≥4R {sum(1 for x in l2 if x >= 4)} | campaign settled n={len(cr)} sum {sum(cr):+7.2f}R "
                  f"(1-attempt same rows {sum(base_cr):+7.2f}R) ≥4R {ge4} worst/name {worst:+.2f} "
                  f"| leg-2 statuses {dict(l2s)}")
            ex_may = [r for r in camp if str(r["alert_date"])[:7] != MAY]
            print(f"  {'':<15} {'':<12} ex-May campaign n={len(ex_may)} sum {sum(r['campaign_r'] for r in ex_may):+7.2f}R "
                  f"vs 1-attempt {sum(base[r['id']]['realized_r'] for r in ex_may if base[r['id']]['status']=='settled'):+7.2f}R; "
                  f"top leg-2: {sorted([(round(r['leg2_r'],2), r['ticker'], str(r['alert_date'])) for r in fired if r['leg2_r'] is not None], reverse=True)[:4]}")

    # ═══ 5. RETIREMENT REPRODUCTIONS ═══
    print("\n══ 5. RETIREMENT REPRODUCTIONS ══")
    # #5: the 17 live day-1 stop-outs, era-matched (ORB-low stop), SD-5mclear / NDO legs
    stop_outs = [t for t in live if date.fromisoformat(t["alert_date"]) < ep.STOP_2R_DATE]
    for sig in REENTRY_SIGNALS:
        rows = walk_trades(stop_outs, alerts_by,
                           lambda t, sig=sig: replace(ruleset_as_of(date.fromisoformat(t["alert_date"])),
                                                      attempts=2, reentry_signal=sig),
                           minutes, daily, extra)
        so = [r for r in rows if r["status"] in ("settled", "open_at_horizon") and r["final_reason"] == "stop_hit"
              and not r["partial_fired"]]
        fired = [r for r in rows if r["attempts_fired"] == 2]
        l2 = [(r["ticker"], round(r["leg2_r"], 2) if r["leg2_r"] is not None else None, r["leg2_status"]) for r in fired]
        print(f"  #5 {sig:<12} era-matched leg-1 full stop-outs {len(so)} of {len(rows)} live pre-2R rows "
              f"(abstain {[r['ticker'] for r in rows if r['status']=='abstain']}); fired {len(fired)}; "
              f"second stops {sum(1 for r in fired if (r['leg2_r'] or 0) <= -0.5)}; "
              f"leg-2 sum {sum(r['leg2_r'] or 0 for r in fired):+.2f}R; legs {l2}")
    # #2: scratch share + median flip at the live stop (printed in §3); restated here
    lc = grid[cell_name("entry_minus_2r", "orb", "live")]
    tk = [r for r in lc.values() if r["status"] == "settled" and r["partial_fired"]]
    print(f"  #2 partial-takers under the control: {len(tk)}; exactly +0.33R scratch {sum(1 for r in tk if abs(r['realized_r']-1/3)<0.02)}; "
          f"median {st.median([r['realized_r'] for r in tk]):+.2f}; win {sum(1 for r in tk if r['realized_r']>0)/len(tk):.0%}")
    # #8: ordering of volatility stops on the live day-0 cohort — from §1 (equal-$ sums) restated
    print("  #8 ordering: see §1 rows (adr_0.5 … adr_1.25 on the 26 live trades, sum R and ADR-units)")

    # ═══ write the cells TSV ═══
    cols = ["cell", "id", "ticker", "alert_date", "admit", "status", "reason", "entered", "entry_px", "stop",
            "target", "stop_width_adr", "adr_pct", "partial_fired", "final_reason", "realized_r",
            "pnl_adr", "mark_r", "attempts_fired", "leg2_status", "leg2_r", "campaign_r", "gap_through"]
    with open(OUT_TSV, "w") as fh:
        fh.write("|".join(cols) + "\n")
        for key, res in grid.items():
            for r in res.values():
                r = {**r, "cell": key}
                fh.write("|".join("" if r.get(c) is None else str(r.get(c)) for c in cols) + "\n")
        for r in prereq_rows:
            fh.write("|".join("" if r.get(c) is None else str(r.get(c)) for c in cols) + "\n")
    print(f"\nwritten: {OUT_TSV} ({sum(len(v) for v in grid.values()) + len(prereq_rows)} rows)")


if __name__ == "__main__":
    main()
