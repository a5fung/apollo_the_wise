"""#327 H11 — the report: reads h11_rows.tsv (Part A), h11_marows.tsv (Part B), h11_habitual.tsv; applies the bar
pre-registered in h11_run.py's docstring; writes h11_out.txt. No settlement is computed here.

Verdict rule (fixed before outcomes were read): a READABLE leg that misses its bar -> FAIL; all readable legs clear
but a leg unreadable on n -> CAN'T TELL (n); all three legs readable and clear -> PASS. Leg (1) readable when the
matched arm has >= 60 ERA A fires; legs (2)/(3) readable when each arm has >= 8 fires."""
from __future__ import annotations

import csv
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
for p in (REPO, REPO / "scripts" / "probes", REPO / "scripts" / "probes" / "_327_block5", HERE):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from hyptests_report import perm_group      # noqa: E402  the 09-27 within-week label shuffle (2000 draws, seed 327)

BAR_PTS, BAR_N, MIN_READ = 8.0, 60, 8
BUCKETS = ("s01-02", "s03-05", "s06-10", "s11+")


def rd(name):
    with open(HERE / name) as fh:
        return list(csv.DictReader(fh, delimiter="|"))


def f(v):
    return None if v in (None, "") else float(v)


def i(v):
    return None if v in (None, "") else int(float(v))


def mean(v):
    return statistics.mean(v) if v else None


def fm(x, s="{:+.1f}"):
    return "—" if x is None else s.format(x)


def items():
    out = []
    for r in rd("h11_rows.tsv"):
        if r["status"] != "ok":
            continue
        out.append({"part": "A", "ticker": r["ticker"], "ep_date": r["ep_date"], "era": r["era"], "split": r["split"],
                    "month": r["month"], "week": r["week"], "rung": r["rung"], "bucket": r["bucket"], "s": i(r["session_idx"]),
                    "m_either": i(r["m_either"]), "m_sma20": i(r["m_sma20"]), "m_ema21": i(r["m_ema21"]),
                    "m_atfire": i(r["m_either_atfire"]), "m_hab": i(r["m_hab"]), "mis_hab": i(r["mis_hab"]), "hab": r["hab"],
                    "o": r["o_orig"] or None, "o_scaled": r["o_scaled"] or None, "o_fill": r["o_fill"] or None,
                    "lane_trail": f(r["lane_trail_r"]), "adr_trail": f(r["adr100_trail_r"]),
                    "lane_none": f(r["lane_none_r"]), "adr_none": f(r["adr100_none_r"]),
                    "runner": i(r["runner"]), "labelled": i(r["labelled"]), "m_eplow": None})
    for r in rd("h11_marows.tsv"):
        if r["status"] != "fire":
            continue
        out.append({"part": "B", "ticker": r["ticker"], "ep_date": r["ep_date"], "era": r["era"], "split": r["split"],
                    "month": r["month"], "week": r["week"], "rung": "ma20_21_reclaim", "bucket": r["bucket"], "s": i(r["session_idx"]),
                    "m_either": i(r["m_either"]), "m_sma20": i(r["m_sma20"]), "m_ema21": i(r["m_ema21"]),
                    "m_atfire": i(r["m_either"]), "m_hab": i(r["m_hab"]), "mis_hab": i(r["mis_hab"]), "hab": r["hab"],
                    "o": r.get("o_orig") or None, "o_scaled": r.get("o_scaled") or None, "o_fill": None,
                    "lane_trail": f(r.get("lane_trail_r")), "adr_trail": f(r.get("adr100_trail_r")),
                    "lane_none": f(r.get("lane_none_r")), "adr_none": f(r.get("adr100_none_r")),
                    "runner": i(r["runner"]), "labelled": i(r["labelled"]), "m_eplow": i(r["m_eplow_only"])})
    return out


SPLITS = {
    "ERA A": lambda x: x["era"] == "A",
    "  DISC (<=08-14)": lambda x: x["split"] == "DISC",
    "  ex-May": lambda x: x["era"] == "A" and x["month"] != "2026-05",
    "  HOA (08-15..21)": lambda x: x["split"] == "HOA",
    "ERA B (>=08-22)": lambda x: x["era"] == "B",
    "post-08-14 (HOA+B)": lambda x: x["split"] in ("HOA", "B"),
}


def tv(x, key="o"):
    o = x[key]
    if o in (None, "", "abstain"):
        return None
    return 1.0 if o == "target" else 0.0


def best2(rows):
    """The matched arm's best two names: most +2-first hits, tie-broken by summed 1xADR none-arm R."""
    by = defaultdict(lambda: [0.0, 0.0])
    for x in rows:
        by[x["ticker"]][0] += tv(x) or 0.0
        by[x["ticker"]][1] += x["adr_none"] or 0.0
    return {t for t, _ in sorted(by.items(), key=lambda kv: (-kv[1][0], -kv[1][1], kv[0]))[:2]}


def cell(rows, flag, key="o", perm=False):
    rr = [x for x in rows if x.get(flag) is not None and tv(x, key) is not None]
    m = [x for x in rr if x[flag]]
    n = [x for x in rr if not x[flag]]
    res = {"n_m": len(m), "n_n": len(n), "names_m": len({x["ticker"] for x in m}), "names_n": len({x["ticker"] for x in n})}
    res["rate_m"] = 100 * mean([tv(x, key) for x in m]) if m else None
    res["rate_n"] = 100 * mean([tv(x, key) for x in n]) if n else None
    res["diff"] = (res["rate_m"] - res["rate_n"]) if (m and n) else None
    if m and n:
        top = best2(m)
        m2 = [x for x in m if x["ticker"] not in top]
        res["drop2"] = (100 * mean([tv(x, key) for x in m2]) - res["rate_n"]) if m2 else None
        res["drop2_names"] = ",".join(sorted(top))
        res["n_m_drop2"] = len(m2)
        if perm:
            res["p"] = perm_group([tv(x, key) for x in rr], [bool(x[flag]) for x in rr], [x["week"] for x in rr])
    # R and tail beside (fires whose R exists; no outcome filter)
    for arm in ("lane_none", "adr_none", "lane_trail", "adr_trail"):
        mv = [x[arm] for x in rows if x.get(flag) == 1 and x[arm] is not None]
        nv = [x[arm] for x in rows if x.get(flag) == 0 and x[arm] is not None]
        res[f"{arm}_m"], res[f"{arm}_n"] = mean(mv), mean(nv)
        res[f"{arm}_t3_m"] = (100 * sum(1 for v in mv if v >= 3 - 1e-9) / len(mv)) if mv else None
        res[f"{arm}_t3_n"] = (100 * sum(1 for v in nv if v >= 3 - 1e-9) / len(nv)) if nv else None
        res[f"{arm}_nm"], res[f"{arm}_nn"] = len(mv), len(nv)
    return res


def row_line(name, c, show_p=False):
    p = f" p {c['p']:.3f}" if show_p and c.get("p") is not None else ""
    return (f"  {name:20s} matched n {c['n_m']:3d} ({c['names_m']:3d} names) {fm(c['rate_m'], '{:5.1f}')}% | non-matched n {c['n_n']:3d} "
            f"({c['names_n']:3d} names) {fm(c['rate_n'], '{:5.1f}')}% | diff {fm(c['diff'])} pts | drop-best-2 {fm(c.get('drop2'))} "
            f"[{c.get('drop2_names', '')}]{p} | tail >=3R (1xADR hold) {fm(c['adr_none_t3_m'], '{:.1f}')}% vs {fm(c['adr_none_t3_n'], '{:.1f}')}% "
            f"| mean R 1xADR hold {fm(c['adr_none_m'], '{:+.2f}')} vs {fm(c['adr_none_n'], '{:+.2f}')} · lane-stop hold {fm(c['lane_none_m'], '{:+.2f}')} vs {fm(c['lane_none_n'], '{:+.2f}')}")


def verdict(cA, cX, cB):
    legs = {}
    legs["1 ERA A >= +8 pts, matched n >= 60"] = ("unreadable (matched n %d < 60)" % cA["n_m"]) if cA["n_m"] < BAR_N else (
        f"met ({fm(cA['diff'])} pts; drop-best-2 {fm(cA.get('drop2'))})" if (cA["diff"] is not None and cA["diff"] >= BAR_PTS) else f"missed ({fm(cA['diff'])} pts)")
    legs["2 ex-May >= +8 pts"] = ("unreadable (arm < 8)" if min(cX["n_m"], cX["n_n"]) < MIN_READ else
                                  (f"met ({fm(cX['diff'])} pts; drop-best-2 {fm(cX.get('drop2'))} — the bar is drop-2-blind)" if cX["diff"] >= BAR_PTS else f"missed ({fm(cX['diff'])} pts)"))
    legs["3 ERA B same sign"] = (f"unreadable (matched {cB['n_m']} / non-matched {cB['n_n']}; need >= 8 each; sign {fm(cB['diff'])})"
                                 if min(cB["n_m"], cB["n_n"]) < MIN_READ else ("met" if cB["diff"] > 0 else f"missed ({fm(cB['diff'])} pts)"))
    if any(v.startswith("missed") for v in legs.values()):
        v = "FAIL"
    elif any(v.startswith("unreadable") for v in legs.values()):
        v = "CAN'T TELL (n)"
    else:
        v = "PASS"
    return v, legs


def main():
    X = items()
    L = ["#327 H11 — confluence + per-stock character on the 277 real EPs. Pre-registration: h11_run.py docstring. $0, local files.",
         "Measure: +2-first rate (stop 1xADR$ / target 2xADR$ from the entry, stop-first on a straddle, by session 10) — H2's fire edge.",
         "Splits: the program's (09-27) — ERA A = alert < 08-22 (the rule change), DISC <= 08-14, HOA 08-15..08-21, ERA B >= 08-22; the row 'post-08-14 (HOA+B)' is the task text's 'after 08-14'. The verdict is the same under either.",
         "Pop: Part A = the 632 first fires (ok = has a reclaimed level + MA history); Part B = one daily-grade SMA20/21-EMA reclaim fire per campaign (entry at the close).",
         ""]
    hab = rd("h11_habitual.tsv")
    L.append("POPULATION (outcome-readable fires, i.e. >= 10 sessions after the fire, non-abstaining)")
    for nm, fn in SPLITS.items():
        rr = [x for x in X if fn(x) and tv(x) is not None]
        a = [x for x in rr if x["part"] == "A"]
        b = [x for x in rr if x["part"] == "B"]
        L.append(f"  {nm:20s} Part A {len(a):3d} (matched {sum(x['m_either'] for x in a):3d}) · Part B {len(b):3d} (matched {sum(x['m_either'] for x in b):3d}) · "
                 f"union {len(rr):3d} (matched {sum(x['m_either'] for x in rr):3d}, {len({x['ticker'] for x in rr if x['m_either']})} names)")
    L.append("  (excluded before this table: 48 ERA A + 2 ERA B high-break fires with no reclaimed level; AVEX 05-12 low reclaim, 18 prior closes; "
             "Part B: 48 ERA A + 3 ERA B campaigns whose EP close never cleared its own SMA20/21-EMA, 38 + 6 with no MA touch in 20 sessions, AVEX no history; "
             "fires with < 10 sessions after them — see h11_pop_out.txt)")
    L.append("")
    summary = {}
    for draw, flag in (("PRIMARY — either MA (SMA20 or 21-EMA)", "m_either"), ("SMA20 only", "m_sma20"), ("21-EMA only", "m_ema21")):
        for popname, pfn in (("UNION A+B", lambda x: True), ("Part A only (632 first fires)", lambda x: x["part"] == "A"),
                             ("Part B only (MA-reclaim fire)", lambda x: x["part"] == "B")):
            L.append(f"── {draw} · {popname} ──")
            cs = {}
            for nm, fn in SPLITS.items():
                c = cell([x for x in X if fn(x) and pfn(x)], flag, perm=nm.strip() in ("ERA A", "DISC (<=08-14)"))
                cs[nm] = c
                L.append(row_line(nm, c, show_p=True))
            v, legs = verdict(cs["ERA A"], cs["  ex-May"], cs["ERA B (>=08-22)"])
            L.append(f"  => VERDICT {v} · " + " · ".join(f"[{k}: {val}]" for k, val in legs.items()))
            summary[(draw, popname)] = (v, cs)
            L.append("")
    # sensitivity rows (shown, not counted) on the primary union, ERA A
    A_ = [x for x in X if x["era"] == "A"]
    L.append("── SHOWN, NOT COUNTED (ERA A unless stated) ──")
    c = cell(A_, "m_either", key="o_scaled")
    L.append("  scaled barriers (trailing 3-session range), union:" + row_line("", c)[22:])
    c = cell([x for x in A_ if x["part"] == "A"], "m_either", key="o_fill")
    L.append("  fillable entry (next 5-min open + 5 bps), Part A:" + row_line("", c)[22:])
    c = cell([x for x in A_ if x["part"] == "A"], "m_atfire")
    L.append("  at-fire MA (entry as today's close), Part A:" + row_line("", c)[22:])
    c = cell([x for x in A_ if x["part"] == "A"], "m_either")
    L.append(f"  Part A trail arm (the lane's own exit): mean R lane-stop {fm(c['lane_trail_m'], '{:+.2f}')} vs {fm(c['lane_trail_n'], '{:+.2f}')} · "
             f"1xADR {fm(c['adr_trail_m'], '{:+.2f}')} vs {fm(c['adr_trail_n'], '{:+.2f}')} · tail >=3R lane-stop {fm(c['lane_trail_t3_m'], '{:.1f}')}% vs "
             f"{fm(c['lane_trail_t3_n'], '{:.1f}')}% · 1xADR {fm(c['adr_trail_t3_m'], '{:.1f}')}% vs {fm(c['adr_trail_t3_n'], '{:.1f}')}%")
    bx = [x for x in A_ if x["part"] == "B"]
    nz = sum(1 for x in bx if x["lane_trail"] is not None and abs(x["lane_trail"]) < 0.05)
    L.append(f"  Part B trail arm is degenerate: {nz} of {len(bx)} ERA A MA-reclaim fires exit the trail at ~0R on the entry bar "
             f"(close < max(SMA10, SMA20)) -> Part B R is read on the hold ('none') arm")
    c = cell(bx, "m_eplow")
    L.append("  Part B two-fold = EP-LOW only (the MNTS blueprint letter):" + row_line("", c)[22:])
    L.append("")
    L.append("  SESSION BUCKETS (union, either MA) — the lateness confound:")
    wsum = wn = 0.0
    for b in BUCKETS:
        c = cell([x for x in A_ if x["bucket"] == b], "m_either")
        L.append(row_line(b, c))
        if c["diff"] is not None and min(c["n_m"], c["n_n"]) >= 3:
            wsum += c["diff"] * c["n_m"]
            wn += c["n_m"]
    L.append(f"  bucket-weighted diff (weights = matched n, buckets with >= 3 per arm): {fm(wsum / wn if wn else None)} pts")
    for part in ("A", "B"):
        wsum = wn = 0.0
        for b in BUCKETS:
            c = cell([x for x in A_ if x["bucket"] == b and x["part"] == part], "m_either")
            if c["diff"] is not None and min(c["n_m"], c["n_n"]) >= 3:
                wsum += c["diff"] * c["n_m"]
                wn += c["n_m"]
        L.append(f"    Part {part} bucket-weighted diff: {fm(wsum / wn if wn else None)} pts")
    c = cell([x for x in A_ if x["s"] is not None and x["s"] >= 6], "m_either")
    L.append(row_line("s6+ (MNTS shape)", c))
    for nm, fn in (("ex-May s6+", lambda x: x["month"] != "2026-05"),):
        c = cell([x for x in A_ if x["s"] is not None and x["s"] >= 6 and fn(x)], "m_either")
        L.append(row_line(nm, c))
    L.append("")
    L.append("  WITHIN RUNG (ERA A, either MA):")
    for rg in ("ep_low_reclaim", "ep_close_reclaim", "ep_close_620_prox", "ma20_21_reclaim"):
        L.append(row_line(rg[:20], cell([x for x in A_ if x["rung"] == rg], "m_either")))
    # EP close never cleared its own MA — Part A matched fires on those campaigns
    excl = {(r["ticker"], r["ep_date"]) for r in rd("h11_marows.tsv") if r["status"] == "ep_close_not_above_ma"}
    aA = [x for x in A_ if x["part"] == "A"]
    m_ex = [x for x in aA if x["m_either"] and (x["ticker"], x["ep_date"]) in excl]
    L.append(f"  Part A matched fires on campaigns whose EP close never cleared its own SMA20/21-EMA: {len(m_ex)} of {sum(x['m_either'] for x in aA)}")
    L.append(row_line("Part A, those excl.", cell([x for x in aA if (x["ticker"], x["ep_date"]) not in excl], "m_either")))
    L.append("")
    # big winners / labelled
    L.append("  THE BIG-WINNER SET (the rerun's 7 >= 3R EPs, his 4 labelled EPs) — which fires were matched:")
    for x in sorted([x for x in X if x["runner"] or x["labelled"]], key=lambda x: (x["ticker"], x["part"], x["rung"])):
        L.append(f"    {x['ticker']:5s} {x['ep_date']} {'runner' if x['runner'] else 'labelled':8s} Part {x['part']} {x['rung']:18s} s{x['s']} "
                 f"matched {x['m_either']} hab {x['hab']}/{x['m_hab']} | +2-first {x['o']} | R 1xADR hold {fm(x['adr_none'], '{:+.2f}')} "
                 f"lane trail {fm(x['lane_trail'], '{:+.2f}')} 1xADR trail {fm(x['adr_trail'], '{:+.2f}')}")
    L.append("")
    # habitual leg
    L.append("── HABITUAL-SUPPORT LEG (per-stock arm; counted draw: matched_hab vs every other fire on labelled stocks) ──")
    for era in ("A", "B"):
        cnt = Counter(r["hab"] for r in hab if r["era"] == era)
        L.append(f"  ERA {era} labels: " + " · ".join(f"{k} {v}" for k, v in cnt.most_common()))
    Xl = [x for x in X if x["m_hab"] is not None]
    cs = {}
    for nm, fn in SPLITS.items():
        c = cell([x for x in Xl if fn(x)], "m_hab", perm=nm.strip() in ("ERA A", "DISC (<=08-14)"))
        cs[nm] = c
        L.append(row_line(nm, c, show_p=True))
    v, legs = verdict(cs["ERA A"], cs["  ex-May"], cs["ERA B (>=08-22)"])
    L.append(f"  => VERDICT {v} · " + " · ".join(f"[{k}: {val}]" for k, val in legs.items()))
    summary[("habitual", "labelled")] = (v, cs)
    mm = [x for x in Xl if x["era"] == "A" and (x["m_hab"] or x["mis_hab"])]
    c = cell(mm, "m_hab")
    L.append("  beside: matched_hab vs MISMATCHED (level near a different MA), ERA A:" + row_line("", c)[22:])
    for hb in ("sma10", "sma20", "sma50"):
        c = cell([x for x in Xl if x["era"] == "A" and x["hab"] == hb], "m_hab")
        L.append(row_line(f"hab={hb}", c))
    L.append("")
    clears = [k for k, (v, _) in summary.items() if v == "PASS"]
    L.append(f"DRAWS CLEARING THE FULL BAR: {len(clears)} {clears} (counted draws: either/SMA20/EMA21 on the union + habitual = 4; noise 0.2)")
    txt = "\n".join(L) + "\n"
    (HERE / "h11_out.txt").write_text(txt)
    print("wrote h11_out.txt")


if __name__ == "__main__":
    main()
