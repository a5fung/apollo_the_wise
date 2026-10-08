"""#327 H6 — report phase. Reads ONLY the row files h6_run.py wrote (h6_census.tsv, h6_fire_rows.tsv, h6_labels.tsv)
and the gate/anchor outputs; computes every leg against the bar pre-registered in h6_run.py's docstring.
Writes h6_report.txt and h6_summary.json."""
from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import rerun
import reentry

HERE = Path(__file__).resolve().parent
TAIL_R = 3.0
_EPS = 1e-9
ERA_SPLIT = date(2026, 8, 22)


def _f(v):
    return rerun._f(v)


def mean(v):
    v = [x for x in v if x is not None]
    return statistics.mean(v) if v else None


def fmt(x, f="{:+.2f}"):
    return "—" if x is None else f.format(x)


def tail(v):
    return sum(1 for x in v if x is not None and x >= TAIL_R - _EPS)


def drop_best_names(rows, key="r_gap", k=2):
    """Mean after dropping the best k NAMES by summed R."""
    by = defaultdict(float)
    for r in rows:
        by[r["ticker"]] += r[key]
    best = sorted(by, key=lambda t: -by[t])[:k]
    rest = [r[key] for r in rows if r["ticker"] not in best]
    return (mean(rest), best, len(rest))


def main():
    L = []
    p = L.append
    S = {}
    runners = {(t, d) for (t, d) in reentry.load_runners()}
    census = rerun.read_tsv(HERE / "h6_census.tsv")
    labels = rerun.read_tsv(HERE / "h6_labels.tsv")
    fr = rerun.read_tsv(HERE / "h6_fire_rows.tsv")
    for r in fr:
        r["r"], r["r_gap"] = _f(r["r"]), _f(r["r_gap"])
        r["n_after"] = int(r["n_after"]) if r["n_after"] not in ("", None) else 0
        r["winner"] = (r["ticker"], r["ep_date"]) in runners
        r["fid"] = f"{r['ticker']}|{r['ep_date']}|{r['rung']}"
    cell = defaultdict(dict)          # (stop, arm, K) -> fid -> row
    for r in fr:
        if r["arm"] == "ALL":
            continue
        cell[(r["stop"], r["arm"], r["K"])][r["fid"]] = r

    def readable(r):
        return r["kind"] not in ("abstain", "killed_or_no_path") and r.get("floored") != "True" and r["r_gap"] is not None

    # ═════════════ POPULATION ═════════════
    p("═" * 100)
    p("H6 — POPULATION (stated first)")
    gate = (HERE / "h6_gate_out.txt").read_text()
    anchor = (HERE / "h6_anchor_out.txt").read_text()
    p(gate.strip())
    p("")
    p(anchor.strip())
    camp40 = [c for c in census if c["era"] == "A"]
    S["population"] = {"eraA_campaigns": 261, "eraA_arm40": len(camp40),
                       "eraA_arm60": sum(1 for l in labels if l["era"] == "A" and int(l["n_sess"]) >= 60),
                       "eraB_campaigns": 16, "eraB_max_sessions": max(int(l["n_sess"]) for l in labels if l["era"] == "B")}

    # ═════════════ (a) CENSUS ═════════════
    p("")
    p("═" * 100)
    p("(a) 40-SESSION LAUNCH CENSUS — ERA A campaigns with >= 40 sessions (EP <= 08-07)")
    ok = [c for c in census if c["status"] == "ok"]
    launches = [c for c in ok if c["launch"] == "True"]
    p(f"campaigns read {len(ok)} of {len(census)} (holes: {len(census) - len(ok)}); launches (>= +50% from a post-EP "
      f"low, sessions 1-40, high in a later session): {len(launches)} on {len({c['ticker'] for c in launches})} names; "
      f"unique (ticker, start date) {len({(c['ticker'], c['start_date']) for c in launches})}")
    bym = Counter(c["ep_date"][5:7] for c in launches)
    tot_m = Counter(c["ep_date"][5:7] for c in ok)
    p(f"   by EP month (launches / campaigns): " + ", ".join(f"{m}: {bym[m]}/{tot_m[m]}" for m in sorted(tot_m)))
    st = [int(c["start_s"]) for c in launches]
    p(f"   start session (primary = deepest low before the biggest high): <=5 {sum(s <= 5 for s in st)} · 6-10 "
      f"{sum(6 <= s <= 10 for s in st)} · 11-20 {sum(11 <= s <= 20 for s in st)} · 21-30 {sum(21 <= s <= 30 for s in st)}"
      f" · 31-40 {sum(s >= 31 for s in st)}")
    ste = [int(c["earliest_start_s"]) for c in launches]
    p(f"   earliest-qualifying-low variant: start <= 20 {sum(s <= 20 for s in ste)} · > 20 {sum(s > 20 for s in ste)}")
    zones = Counter(c["zone"] for c in launches)
    p(f"   launch low vs the EP-day anchors: {dict(zones)}")
    outside = [c for c in launches if c["outside_every_window"] == "True"]
    in_own = sum(c["in_own_window"] == "True" for c in launches)
    in_re_only = sum(c["in_own_window"] != "True" and (c["in_reentry_window"] or c["in_other_ep_window"]) != ""
                     for c in launches)
    p(f"   start inside the campaign's own 20-session lane window: {in_own}; outside it but inside a re-entry or "
      f"another EP's window: {in_re_only}; OUTSIDE EVERY recorded attempt window: {len(outside)}")
    fam = Counter(c["famA_strict"] for c in launches)
    faml = Counter(c["famA_loose"] for c in launches)
    p(f"   Family A (mi_flag_candidates WATCH/TIGHTENING/COILED/TRIGGERED within 30 days before the start): {dict(fam)}"
      f"; loose (any row): {dict(faml)}")
    both_lo = sum(1 for c in outside if c["famA_strict"] == "not_covered")
    both_hi = sum(1 for c in outside if c["famA_strict"] in ("not_covered", "unknown"))
    half = len(launches) / 2
    if len(launches) < 10:
        va = "FAIL"
    elif both_lo >= half and both_hi >= half:
        va = "PASS"
    elif both_lo < half and both_hi < half:
        va = "FAIL"
    else:
        va = "NOT_TESTABLE"
    p(f"   >> outside every window AND not on Family A: {both_lo} (unknowns as covered) .. {both_hi} (unknowns as "
      f"uncovered) of {len(launches)}; half = {half:.1f}  =>  (a) {va}")
    caught_open = sum(1 for c in launches if c["attempt_open_at_start"])
    caught_fire = sum(1 for c in launches if c["attempt_fired_start_to_cross"])
    neither = sum(1 for c in launches if not c["attempt_open_at_start"] and not c["attempt_fired_start_to_cross"])
    p(f"   lane attempt (incumbent stop) open at the start: {caught_open}; a lane attempt fired between start and the "
      f"+50% cross: {caught_fire}; neither: {neither}")
    np4 = Counter(c["n_patterns_fired_before_start"] for c in launches)
    p(f"   patterns whose first fire was already used before the start: {dict(sorted(np4.items()))}")
    bb = [c for c in launches if c["base_break_s"]]
    p(f"   (b) cheap column — a close above the post-EP base high (sessions 1..start) after the start: {len(bb)} of "
      f"{len(launches)}; before the +50% cross: {sum(c['base_break_before_cross'] == 'True' for c in launches)}; "
      f"median % left from that close to the 40-session peak: "
      f"{fmt(statistics.median([_f(c['base_break_to_peak_pct']) for c in bb if c['base_break_to_peak_pct']]) if [c for c in bb if c['base_break_to_peak_pct']] else None, '{:.1f}')}")
    p("")
    p("   every launch by name (ticker EP · start s/date · low vs EP close · zone · +50% cross s · peak gain · "
      "windows · Family A · lane attempt):")
    for c in sorted(launches, key=lambda c: (c["ep_date"], c["ticker"])):
        win = ("OUTSIDE" if c["outside_every_window"] == "True" else
               "own" if c["in_own_window"] == "True" else
               ("reentry" if c["in_reentry_window"] else "") + ("+otherEP" if c["in_other_ep_window"] else ""))
        att = ("open:" + c["attempt_open_at_start"] if c["attempt_open_at_start"] else "") + \
              (" fired:" + c["attempt_fired_start_to_cross"] if c["attempt_fired_start_to_cross"] else "")
        p(f"   {c['ticker']:5s} {c['ep_date']} · s{c['start_s']:>2s} {c['start_date']} · {fmt(_f(c['low_vs_ep_close_pct']), '{:+.0f}%')} "
          f"· {c['zone']:15s} · cross s{c['cross_s']:>2s} · +{c['best_gain_pct']}% · {win:8s} · famA {c['famA_strict']:11s}"
          f" · {att or 'none'}{'  [HIS LABEL]' if c['his_labelled'] == 'True' else ''}")
    # what the lane's FIRST fires kept on the launch campaigns (best first fire per campaign, judged R)
    kept_rows = []
    for stop, arm, K in (("incumbent", "trail", "20"), ("adr_100", "trail", "20"), ("adr_100", "slow:sma21_2x", "20"),
                         ("adr_100", "handoff:sma21_2x", "60")):
        best = {}
        for r in cell[(stop, arm, K)].values():
            if readable(r):
                k = (r["ticker"], r["ep_date"])
                best[k] = max(best.get(k, -99), r["r_gap"])
        lk = [(c["ticker"], c["ep_date"]) for c in launches]
        fired = [k for k in lk if k in best]
        kept_rows.append((stop, arm, K, len(fired), sum(1 for k in fired if best[k] >= TAIL_R - _EPS)))
        p(f"   launch campaigns where a lane FIRST fire ({stop}, {arm}, s{K}) ended >= 3R: "
          f"{kept_rows[-1][4]} of {len(fired)} that fired (of {len(launches)} launches)")
    S["a_kept"] = [{"stop": a, "arm": b, "K": c, "fired": d, "kept3r": e} for a, b, c, d, e in kept_rows]
    S["a"] = {"campaigns": len(ok), "launches": len(launches), "outside_every_window": len(outside),
              "famA_strict": dict(fam), "outside_and_uncovered_low": both_lo, "outside_and_uncovered_high": both_hi,
              "in_own_window": in_own, "verdict": va,
              "outside_names": [f"{c['ticker']} {c['ep_date']} s{c['start_s']} famA={c['famA_strict']}" for c in outside]}

    # ═════════════ (c) HAND-OFF ═════════════
    p("")
    p("═" * 100)
    p("(c) HAND-OFF EXIT — lane trail until +3R or a new post-EP high, then a runner exit, no 20-session cap")
    p("    judged R = gap-charged (a stop whose session opened below it fills at the open); house R beside")

    def leg(stop, arm, K, era="A", key="r_gap"):
        rows = [r for r in cell[(stop, arm, K)].values() if r["era"] == era]
        rd = [r for r in rows if readable(r)]
        win = [r for r in rd if r["winner"]]
        rest = [r for r in rd if not r["winner"]]
        return {"n_all": len(rows), "n_read": len(rd), "win_n": len(win), "win_kept": tail([r[key] for r in win]),
                "win_mean": mean([r[key] for r in win]), "rest_n": len(rest), "rest_mean": mean([r[key] for r in rest]),
                "all_mean": mean([r[key] for r in rd]), "tail_all": tail([r[key] for r in rd]),
                "rest_settled": mean([r[key] for r in rest if r["kind"] not in ("open", "open_short")]),
                "rest_settled_n": sum(1 for r in rest if r["kind"] not in ("open", "open_short")),
                "rest_open": mean([r[key] for r in rest if r["kind"] in ("open", "open_short")]),
                "rest_open_n": sum(1 for r in rest if r["kind"] in ("open", "open_short")),
                "open_short_n": sum(1 for r in rd if r["kind"] == "open_short"),
                "rows": rd}

    hdr = (f"   {'stop':9s} {'arm':22s} {'K':>3s} | winners kept>=3R of 11 · mean | rest n · mean (settled n·mean / "
           f"open-marked n·mean) | all-fire mean · >=3R | house: kept · win mean · rest mean")
    p(hdr)
    rows_c = []
    combos = [("adr_100", "handoff:sma21_2x", "60"), ("adr_100", "handoff:sma50_1x", "60"),
              ("adr_100", "handoff:ema65_1x", "60"), ("adr_100", "handoff:sma21_2x", "HZ"),
              ("adr_100", "handoff:sma21_2x", "40"),
              ("incumbent", "handoff:sma21_2x", "60"), ("incumbent", "handoff:sma50_1x", "60"),
              ("incumbent", "handoff:ema65_1x", "60"), ("adr_075", "handoff:sma21_2x", "60"),
              ("adr_100", "trail", "20"), ("adr_100", "trail", "60"), ("adr_100", "slow:sma21_2x", "20"),
              ("adr_100", "slow:sma21_2x", "60"), ("adr_100", "none", "20"), ("adr_100", "none", "60"),
              ("incumbent", "trail", "20"), ("incumbent", "trail", "60")]
    for stop, arm, K in combos:
        g, h = leg(stop, arm, K), leg(stop, arm, K, key="r")
        rows_c.append((stop, arm, K, g, h))
        p(f"   {stop:9s} {arm:22s} {K:>3s} | {g['win_kept']:>2d} of {g['win_n']:>2d} · {fmt(g['win_mean'], '{:+.1f}')}"
          f" | {g['rest_n']} · {fmt(g['rest_mean'])} ({g['rest_settled_n']}·{fmt(g['rest_settled'])} / "
          f"{g['rest_open_n']}·{fmt(g['rest_open'])}) | {fmt(g['all_mean'])} · {g['tail_all']} | "
          f"{h['win_kept']} · {fmt(h['win_mean'], '{:+.1f}')} · {fmt(h['rest_mean'])}")
    prim = leg("adr_100", "handoff:sma21_2x", "60")
    primB = leg("adr_100", "handoff:sma21_2x", "60", era="B")
    primH = leg("adr_100", "handoff:sma21_2x", "60", key="r")
    passA = prim["win_kept"] >= 8 and (prim["win_mean"] or -9) >= 5.5 - _EPS and (prim["rest_mean"] or -9) >= -0.14 - _EPS
    passA_h = primH["win_kept"] >= 8 and (primH["win_mean"] or -9) >= 5.5 - _EPS and (primH["rest_mean"] or -9) >= -0.14 - _EPS
    sgnA = (prim["all_mean"] or 0) > 0
    sgnB = (primB["all_mean"] or 0) > 0
    p(f"   PRIMARY (1xADR, hand-off -> sma21_2x, s60), ERA A: kept {prim['win_kept']} of {prim['win_n']} (bar >= 8), "
      f"winner mean {fmt(prim['win_mean'], '{:+.2f}')} (bar >= +5.5), non-winner mean {fmt(prim['rest_mean'], '{:+.3f}')}"
      f" (bar >= -0.14) on n {prim['rest_n']}; open-marked short of s60: {prim['open_short_n']}")
    dbA = drop_best_names(prim["rows"])
    p(f"      ERA A all-fire mean {fmt(prim['all_mean'], '{:+.3f}')} (n {prim['n_read']}); after dropping the best two "
      f"names ({', '.join(dbA[1])}) {fmt(dbA[0], '{:+.3f}')}; >=3R share {prim['tail_all']}/{prim['n_read']} = "
      f"{100 * prim['tail_all'] / max(1, prim['n_read']):.1f}%")
    p(f"      ERA B (direction only; every fire an open mark <= 26 sessions or settled early): n {primB['n_read']} "
      f"readable of {primB['n_all']}, mean {fmt(primB['all_mean'], '{:+.3f}')} (settled {primB['rest_settled_n']} · "
      f"{fmt(primB['rest_settled'])}; open-marked {primB['rest_open_n']} · {fmt(primB['rest_open'])}); >=3R "
      f"{primB['tail_all']}; same sign as ERA A: {sgnA == sgnB}")
    dbB = drop_best_names(primB["rows"])
    p(f"      ERA B after dropping the best two names ({', '.join(dbB[1])}): {fmt(dbB[0], '{:+.3f}')} (n {dbB[2]})")
    lane20B = leg("adr_100", "trail", "20", era="B")
    p(f"      ERA B on the 1xADR trail at s20 (the arm the hand-off replaces): mean {fmt(lane20B['all_mean'], '{:+.3f}')}")
    if passA and sgnA == sgnB:
        vc = "PASS"
    else:
        vc = "FAIL"
    p(f"   >> (c) hand-off {vc} (judged R){'; house R would ' + ('PASS' if passA_h and sgnA == sgnB else 'FAIL') if passA != passA_h else ''}")
    # winners by fire
    p("   the 11 winner fires (1xADR): fire · lane-trail s20 · trail s60 · sma21_2x s20 · hand-off sma21_2x s60 / HZ "
      "(kind, exit session, hand-off session)")
    for fid in sorted({r["fid"] for r in cell[("adr_100", "trail", "20")].values() if r["winner"]}):
        a = cell[("adr_100", "trail", "20")][fid]
        b = cell[("adr_100", "trail", "60")][fid]
        c_ = cell[("adr_100", "slow:sma21_2x", "20")][fid]
        d = cell[("adr_100", "handoff:sma21_2x", "60")][fid]
        e = cell[("adr_100", "handoff:sma21_2x", "HZ")][fid]
        p(f"   {fid:38s} {fmt(a['r_gap'], '{:+.1f}'):>6s} {fmt(b['r_gap'], '{:+.1f}'):>6s} {fmt(c_['r_gap'], '{:+.1f}'):>6s}"
          f"   {fmt(d['r_gap'], '{:+.1f}'):>6s} ({d['kind']} s{d['exit_s']}, h{d['handoff_s'] or '-'})"
          f"  {fmt(e['r_gap'], '{:+.1f}'):>6s} ({e['kind']} s{e['exit_s']})")
    # paired difference vs the 1xADR lane trail s20 on the same ERA A non-winner fires
    base = cell[("adr_100", "trail", "20")]
    diffs = [r["r_gap"] - base[r["fid"]]["r_gap"] for r in prim["rows"] if not r["winner"]
             and readable(base[r["fid"]])]
    p(f"   per-fire difference, hand-off minus the 1xADR lane trail s20, ERA A non-winners: {fmt(mean(diffs), '{:+.3f}')}"
      f" (n {len(diffs)}); share where the hand-off is worse: {100 * sum(d < -_EPS for d in diffs) / max(1, len(diffs)):.0f}%")
    S["c"] = {"primary": {k: v for k, v in prim.items() if k != "rows"}, "eraB": {k: v for k, v in primB.items() if k != "rows"},
              "house": {k: v for k, v in primH.items() if k != "rows"}, "verdict": vc,
              "drop_best_two_all_mean": dbA[0], "drop_best_two_names": dbA[1],
              "cells": [{"stop": s, "arm": a, "K": k, "win_kept": g["win_kept"], "win_mean": g["win_mean"],
                         "rest_mean": g["rest_mean"], "rest_n": g["rest_n"], "all_mean": g["all_mean"],
                         "house_rest_mean": h["rest_mean"]} for s, a, k, g, h in rows_c]}

    # ═════════════ SLOW EXITS s60 vs s20 ═════════════
    p("")
    p("═" * 100)
    p("SLOW-EXIT CELLS — s60 vs s20 on the SAME ERA A first fires with >= 60 sessions after the fire")
    sres = []
    for stop in ("adr_100", "incumbent"):
        for x in ("sma21_2x", "sma50_1x", "ema65_1x", "TRAIL"):
            arm = f"slow:{x}" if x != "TRAIL" else "trail"
            for KL, KH, nmin in (("20", "60", 60), ("20", "40", 40)):
                lo_c, hi_c = cell[(stop, arm, KL)], cell[(stop, arm, KH)]
                pairs = [(lo_c[f], hi_c[f]) for f in hi_c if hi_c[f]["era"] == "A" and hi_c[f]["n_after"] >= nmin
                         and readable(hi_c[f]) and readable(lo_c[f])]
                m_lo, m_hi = mean([a["r_gap"] for a, _ in pairs]), mean([b["r_gap"] for _, b in pairs])
                db = drop_best_names([b for _, b in pairs])
                t_lo, t_hi = tail([a["r_gap"] for a, _ in pairs]), tail([b["r_gap"] for _, b in pairs])
                still_open = sum(1 for _, b in pairs if b["kind"] == "open")
                ok_ = (m_hi is not None and m_lo is not None and m_hi > m_lo + _EPS and db[0] is not None and db[0] > _EPS)
                prim_cell = stop == "adr_100" and x != "TRAIL" and KH == "60"
                verdict = ("PASS" if ok_ else "FAIL") if prim_cell else ("clears" if ok_ else "does not clear")
                sres.append({"stop": stop, "exit": x, "K": f"s{KL}->s{KH}", "n": len(pairs), "mean_lo": m_lo,
                             "mean_hi": m_hi, "drop2": db[0], "drop2_names": db[1], "tail_lo": t_lo, "tail_hi": t_hi,
                             "open_at_hi": still_open, "verdict": verdict, "primary": prim_cell,
                             "total_lo": sum(a["r_gap"] for a, _ in pairs), "total_hi": sum(b["r_gap"] for _, b in pairs)})
                p(f"   {stop:9s} {x:9s} s{KL}->s{KH}: n {len(pairs)} · mean {fmt(m_lo, '{:+.3f}')} -> {fmt(m_hi, '{:+.3f}')}"
                  f" (total {sum(a['r_gap'] for a, _ in pairs):+.1f}R -> {sum(b['r_gap'] for _, b in pairs):+.1f}R) · "
                  f">=3R {t_lo} -> {t_hi} · still open at s{KH} {still_open} · drop best two ({', '.join(db[1])}) "
                  f"{fmt(db[0], '{:+.3f}')}  => {verdict}{'  [PRIMARY]' if prim_cell else ''}")
    n_pass = sum(1 for s in sres if s["primary"] and s["verdict"] == "PASS")
    p(f"   >> primary slow-exit cells (1xADR, s20 -> s60) clearing: {n_pass} of 3")
    S["slow"] = sres

    # ═════════════ (d) LABELS ═════════════
    p("")
    p("═" * 100)
    p("(d) SLOW-LEADER LABEL (s40 close >= +25% over the EP-day close AND above its 50-day SMA) beside the FAST one")
    lA = [l for l in labels if l["era"] == "A"]
    n40 = [l for l in lA if l["n40"] == "True"]
    slow = [l for l in n40 if l["slow"] == "True"]
    fast = [l for l in lA if l["fast"] == "True"]
    fast40 = [l for l in n40 if l["fast"] == "True"]
    both = [l for l in slow if l["fast"] == "True"]
    p(f"   ERA A campaigns with 40 sessions: {len(n40)}; SLOW {len(slow)} ({100 * len(slow) / max(1, len(n40)):.1f}%); "
      f"FAST {len(fast40)} of the same {len(n40)} (FAST on all ERA A with 15 sessions: {len(fast)}); both {len(both)}")
    p(f"   SLOW only: " + ", ".join(f"{l['ticker']} {l['ep_date']} ({fmt(_f(l['s40_pct']), '{:+.0f}%')}, fired "
                                    f"{l['lane_fired']})" for l in slow if l["fast"] != "True"))
    p(f"   FAST and SLOW: " + ", ".join(f"{l['ticker']} {l['ep_date']}" for l in both))
    p(f"   FAST, not SLOW at s40: " + ", ".join(f"{l['ticker']} {l['ep_date']} ({fmt(_f(l['s40_pct']), '{:+.0f}%')})"
                                             for l in fast40 if l["slow"] != "True"))
    for l in labels:
        if l["his_labelled"] == "True":
            p(f"   his labelled {l['ticker']} {l['ep_date']}: sessions {l['n_sess']}; fast {l['fast']}; slow "
              f"{l['slow'] if l['n40'] == 'True' else 'unreadable (< 40 sessions)'}; s40 {fmt(_f(l['s40_pct']), '{:+.1f}%')}"
              f"; max high within 40 {fmt(_f(l['max40_pct']), '{:+.1f}%')}; lane fired {l['lane_fired']}")
    slow_keys = {(l["ticker"], l["ep_date"]) for l in slow}
    p(f"   lane first fires on SLOW-leader campaigns, kept >= 3R per arm (judged R):")
    dres = []
    for stop, arm, K in (("incumbent", "trail", "20"), ("adr_100", "trail", "20"), ("adr_100", "slow:sma21_2x", "20"),
                         ("adr_100", "handoff:sma21_2x", "60"), ("adr_100", "trail", "60"),
                         ("incumbent", "handoff:sma21_2x", "60")):
        rows = [r for r in cell[(stop, arm, K)].values() if (r["ticker"], r["ep_date"]) in slow_keys and readable(r)]
        others = [r for r in cell[(stop, arm, K)].values() if r["era"] == "A" and (r["ticker"], r["ep_date"]) not in slow_keys
                  and readable(r) and not r["winner"]]
        p(f"     {stop:9s} {arm:20s} s{K}: {tail([r['r_gap'] for r in rows])} of {len(rows)} fires on "
          f"{len({(r['ticker'], r['ep_date']) for r in rows})} slow-leader EPs kept >= 3R, mean {fmt(mean([r['r_gap'] for r in rows]))}")
        dres.append({"stop": stop, "arm": arm, "K": K, "kept": tail([r["r_gap"] for r in rows]), "n": len(rows),
                     "mean": mean([r["r_gap"] for r in rows])})
    S["d"] = {"n40": len(n40), "slow": len(slow), "fast_of_n40": len(fast40), "both": len(both),
              "slow_names": [f"{l['ticker']} {l['ep_date']}" for l in slow], "arms": dres}

    p("")
    p("═" * 100)
    from agents.market_intelligence.delayed_entry_shadow import _trading_days
    eb = sorted(date.fromisoformat(l["ep_date"]) for l in labels if l["era"] == "B")
    far = date(2027, 3, 1)
    d40 = [_trading_days(d + __import__("datetime").timedelta(days=1), far)[39] for d in (eb[0], eb[-1])]
    d60 = [_trading_days(d + __import__("datetime").timedelta(days=1), far)[59] for d in (eb[0], eb[-1])]
    p(f"ERA B: 16 campaigns (EP {eb[0]}..{eb[-1]}), max {S['population']['eraB_max_sessions']} sessions by 10-05 — 0 "
      f"can be read at 40 or 60 sessions (census, slow label, s40/s60 cells): NOT_TESTABLE. 40 sessions exist for the "
      f"first ERA B EP on {d40[0]} and for the last on {d40[1]}; 60 on {d60[0]} .. {d60[1]} (production calendar).")
    S["eraB_readable"] = {"s40": [str(x) for x in d40], "s60": [str(x) for x in d60]}
    (HERE / "h6_report.txt").write_text("\n".join(L) + "\n")
    (HERE / "h6_summary.json").write_text(json.dumps(S, indent=1, default=str))
    print("\n".join(L))


if __name__ == "__main__":
    main()
