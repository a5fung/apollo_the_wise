"""#327 H8 — the report phase: reads h8_rows.tsv + h8_ctl.tsv (written once by h8_run.py run), applies the bar
pre-registered in h8_run.py's docstring, writes h8_out.txt. No settlement or walk is computed here."""
from __future__ import annotations

import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
for p in (REPO, REPO / "scripts" / "probes", REPO / "scripts" / "probes" / "_327_block5", HERE):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import rerun                                   # noqa: E402
from hyptests_report import perm_group         # noqa: E402  the 09-27 week-shuffle, seed 327, 2000 draws

MIN_HELDOUT = 8
TAIL_R = 3.0
BAR_EDGE, BAR_N, BAR_NAMES = 5.0, 100, 60


def rd(name):
    return rerun.read_tsv(HERE / name)


def fl(v):
    return rerun._f(v)


def mean(v):
    return statistics.mean(v) if v else None


def fm(x, f="{:+.2f}"):
    return "—" if x is None else f.format(x)


def in_split(r, sp):
    if sp == "A":
        return r["era"] == "A"
    if sp == "exMay":
        return r["era"] == "A" and r["month"] != "2026-05"
    return r["split"] == sp


def edge(F, C, okey="o_fill_orig", ckey="o_orig", perm=False):
    fr = [r for r in F if r.get(okey) not in (None, "", "abstain")]
    co = [r for r in C if r.get(ckey) not in (None, "", "abstain")]
    out = {"n": len(fr), "names": len({r["ticker"] for r in fr}), "n_ctl": len(co),
           "abstain": sum(1 for r in F if r.get(okey) == "abstain")}
    if not fr or not co:
        return out
    rate = lambda rows, k, v: 100 * sum(1 for r in rows if r[k] == v) / len(rows)
    out.update({"f2": rate(fr, okey, "target"), "c2": rate(co, ckey, "target"), "f1": rate(fr, okey, "stop"), "c1": rate(co, ckey, "stop")})
    out["gap"], out["gap1"] = out["f2"] - out["c2"], out["f1"] - out["c1"]
    hits = Counter(r["ticker"] for r in fr if r[okey] == "target")
    for k in (1, 2):
        top = {t for t, _ in hits.most_common(k)}
        fr2 = [r for r in fr if r["ticker"] not in top]
        co2 = [r for r in co if r["ticker"] not in top]
        if fr2 and co2:
            out[f"drop{k}"] = rate(fr2, okey, "target") - rate(co2, ckey, "target")
            out[f"drop{k}_names"] = sorted(top)
    if perm:
        allr = [(1.0 if r[okey] == "target" else 0.0, True, r["week"]) for r in fr] + [(1.0 if r[ckey] == "target" else 0.0, False, r["week"]) for r in co]
        out["p"] = perm_group([a for a, _, _ in allr], [b for _, b, _ in allr], [c for _, _, c in allr])
    return out


def fmt_edge(o):
    if not o.get("n"):
        return f"fires 0 (abstain {o.get('abstain', 0)})"
    s = (f"fires {o['n']:3d} on {o['names']:3d} names (abstain {o['abstain']}) vs ctl {o['n_ctl']:4d} | +2 first {fm(o.get('f2'), '{:.1f}')}% vs {fm(o.get('c2'), '{:.1f}')}% "
         f"-> {fm(o.get('gap'), '{:+.1f}')} pts (drop-1 {fm(o.get('drop1'), '{:+.1f}')} {o.get('drop1_names', '')}; drop-2 {fm(o.get('drop2'), '{:+.1f}')} {o.get('drop2_names', '')})"
         f" | -1 first {fm(o.get('f1'), '{:.1f}')}% vs {fm(o.get('c1'), '{:.1f}')}% -> {fm(o.get('gap1'), '{:+.1f}')}")
    if "p" in o:
        s += f" | week-shuffle p {fm(o['p'], '{:.3f}')}"
    return s


def rstats(F, ek, sk):
    st = [r for r in F if r.get(f"{ek}_{sk}_status") in ("settled", "marked")]
    o = {"n": len(st), "killed_or_abstain": len(F) - len(st)}
    if not st:
        return o
    for arm in ("trail", "none"):
        v = [fl(r[f"{ek}_{sk}_{arm}_r"]) for r in st]
        v10 = [fl(r[f"{ek}_{sk}_{arm}_s10"]) for r in st if r.get(f"{ek}_{sk}_{arm}_s10") not in (None, "")]
        by = defaultdict(float)
        for r, x in zip(st, v):
            by[r["ticker"]] += x
        top = sorted(by.items(), key=lambda kv: -kv[1])[:2]
        o[arm] = {"mean": mean(v), "sum": sum(v), "s10": mean(v10), "n10": len(v10),
                  "tail": sum(1 for x in v if x >= TAIL_R), "tail_pct": 100 * sum(1 for x in v if x >= TAIL_R) / len(v),
                  "worst": min(v), "best": max(v), "drop2_sum": sum(v) - sum(x for _, x in top),
                  "drop2_mean": (sum(v) - sum(x for _, x in top)) / max(1, len([1 for r in st if r["ticker"] not in {t for t, _ in top}])),
                  "drop2_names": [f"{t} {x:+.1f}" for t, x in top],
                  "stops": sum(1 for r in st if r[f"{ek}_{sk}_{arm}_oc"] == "stop"),
                  "day0_stops": sum(1 for r in st if r[f"{ek}_{sk}_{arm}_oc"] == "stop" and r.get(f"{ek}_{sk}_stop_idx") == "0")}
    o["w_adr_med"] = statistics.median([fl(r[f"{ek}_{sk}_w_adr"]) for r in st])
    o["w_pct_med"] = statistics.median([fl(r[f"{ek}_{sk}_w_pct"]) for r in st])
    return o


def fmt_r(o):
    if not o.get("n"):
        return "n 0"
    t, n_ = o["trail"], o["none"]
    return (f"n {o['n']:3d} (killed/abstain {o['killed_or_abstain']}) stop width med {o['w_adr_med']:.2f} ADR / {o['w_pct_med']:.1f}% | "
            f"TRAIL: >= 3R {t['tail']} ({t['tail_pct']:.1f}%) · mean {fm(t['mean'])}R · at s10 {fm(t['s10'])}R (n {t['n10']}) · sum {t['sum']:+.1f}R · "
            f"drop-2 sum {t['drop2_sum']:+.1f}R {t['drop2_names']} · worst {t['worst']:+.2f} · stops {t['stops']} (day-0 {t['day0_stops']}) | "
            f"NONE: >= 3R {n_['tail']} ({n_['tail_pct']:.1f}%) · mean {fm(n_['mean'])}R · at s10 {fm(n_['s10'])}R · worst {n_['worst']:+.2f}")


def main():
    rows = rd("h8_rows.tsv")
    ctl = rd("h8_ctl.tsv")
    L = ["#327 H8 — an EP-high reclaim after a dip as a FIRST strength entry. Report of h8_rows.tsv / h8_ctl.tsv (h8_run.py, horizon 10-05).",
         "BAR (verbatim): \"Pass: >= +5 pts · n >= 100 on >= 60 names · survives drop-best · ERA B same sign.\" — on the STRICT primary, fillable entry,",
         "original +-pre-EP-ADR barriers, pess, resolved by session 10 (h8_run.py docstring). Edge = fire +2-first rate minus the same campaigns' control sessions.", ""]
    verdicts = {}
    for pop in ("strict", "variant"):
        F_all = [r for r in rows if r[pop] == "1"]
        C_all = [r for r in ctl if r[pop] == "1"]
        L.append("=" * 140)
        L.append(f"POPULATION {pop.upper()}" + ("  (PRIMARY — verbatim: no lane rung fired before the H8 touch)" if pop == "strict" else
                                                "  (VARIANT beside — only campaigns whose ep_high_break fired are excluded; the row's own ~129)"))
        L.append("=" * 140)
        res = {}
        for sp in ("A", "DISC", "HOA", "exMay", "B"):
            F = [r for r in F_all if in_split(r, sp) and r["readable"] == "1"]
            C = [r for r in C_all if in_split(r, sp)]
            res[sp] = {}
            L.append(f"\n  [{sp}]")
            for okey, ckey, lab in (("o_fill_orig", "o_orig", "FILLABLE entry, original barriers (THE BAR)"), ("o_rec_orig", "o_orig", "recorded entry (= EP high)"),
                                    ("o_close_orig", "o_orig", "at-the-close entry"), ("o_fill_scaled", "o_scaled", "fillable, scaled barriers")):
                o = edge(F, C, okey, ckey, perm=(sp in ("A", "DISC") and okey == "o_fill_orig"))
                res[sp][okey] = o
                L.append(f"    edge {lab:44s} {fmt_edge(o)}")
            if sp in ("A", "B"):
                # sensitivity: same-5-min-bar dip+touch fires kept only when the 1-min bars put the dip first
                Fs = [r for r in F if r["same_bar"] != "1" or r["same_bar_1min"] == "dip_first"]
                o = edge(Fs, C, "o_fill_orig", "o_orig")
                L.append(f"    edge sensitivity: same-bar fires kept only if 1-min = dip first ({len(F) - len(Fs)} dropped) {fmt_edge(o)}")
                for sk, lab in (("dip", "DIP-LOW stop"), ("adr", "1xADR stop")):
                    o = rstats([r for r in F_all if in_split(r, sp)], "fill", sk)
                    res[sp][f"R_{sk}"] = o
                    L.append(f"    R {lab:13s} fillable: {fmt_r(o)}")
                    o2 = rstats([r for r in F_all if in_split(r, sp)], "rec", sk)
                    L.append(f"    R {lab:13s} recorded: {fmt_r(o2)}")
                # dip type (the row's own proxy split) — shown, not counted
                for uc, lab in (("1", "EP low undercut first"), ("0", "close-only dip (EP low held)")):
                    Fu = [r for r in F if r["undercut"] == uc]
                    Cu = [r for r in C if r["undercut"] == uc]
                    o = edge(Fu, Cu)
                    ra = rstats([r for r in F_all if in_split(r, sp) and r["undercut"] == uc], "fill", "adr")
                    L.append(f"    split {lab:30s} edge {fmt_edge(o)}")
                    if ra.get("n"):
                        L.append(f"    {'':36s} 1xADR trail mean {fm(ra['trail']['mean'])}R · none mean {fm(ra['none']['mean'])}R · >= 3R {ra['trail']['tail']} of {ra['n']}")
                # session bucket (shown)
                for bk, lo, hi in (("s1-2", 1, 2), ("s3+", 3, 99)):
                    Fb = [r for r in F if lo <= int(r["s_idx"]) <= hi]
                    o = edge(Fb, C)
                    L.append(f"    bucket {bk:6s} edge {fmt_edge(o)}")
                # context: the lane's own first fires on the SAME campaigns (reentry_rows attempt 1, trail, gap-charged, @ 09-25)
                Fa = [r for r in F_all if in_split(r, sp)]
                for lab, k in (("lane's own stop", "lane"), ("lane fires at 1xADR", "lane_adr")):
                    n = sum(int(r[f"{k}_n"] or 0) for r in Fa)
                    s = sum(fl(r[f"{k}_sum"]) or 0 for r in Fa)
                    t3 = sum(1 for r in Fa if fl(r[f"{k}_max"]) is not None and fl(r[f"{k}_max"]) >= TAIL_R)
                    L.append(f"    context: {lab:22s} on these {len(Fa)} campaigns: {n} first fires, {s:+.1f}R total ({(s / n if n else 0):+.2f}R a fire); campaigns with a lane fire >= 3R: {t3}")
        # tail retention
        L.append("\n  TAIL RETENTION (the rerun's 7 big-winner EPs; his 4 labelled EPs) — fired on, and final trail R at the fillable entry per stop:")
        for r in rows:
            if (r["runner"] == "1" or r["labelled"] == "1") and r[pop] == "1":
                L.append(f"    {'RUNNER ' if r['runner']=='1' else ''}{'LABELLED ' if r['labelled']=='1' else ''}{r['ticker']} {r['ep_date']} -> {r['fire_date']} s{r['s_idx']} | "
                         f"DIP {fm(fl(r.get('fill_dip_trail_r')))}R (width {fm(fl(r.get('fill_dip_w_adr')), '{:.2f}')} ADR, s10 {fm(fl(r.get('fill_dip_trail_s10')))}) · "
                         f"1xADR {fm(fl(r.get('fill_adr_trail_r')))}R (s10 {fm(fl(r.get('fill_adr_trail_s10')))}) · none-arm 1xADR {fm(fl(r.get('fill_adr_none_r')))}R | "
                         f"edge walk {r.get('o_fill_orig')} | lane max R {fm(fl(r.get('lane_adr_max')))} (1xADR) / {fm(fl(r.get('lane_max')))} (own stop)")
        Fa = [r for r in F_all if r["era"] == "A"]
        L.append(f"    runners fired on: {sum(1 for r in Fa if r['runner']=='1')} of 7 · ended >= 3R at 1xADR trail: {sum(1 for r in Fa if r['runner']=='1' and (fl(r.get('fill_adr_trail_r')) or -9) >= TAIL_R)}"
                 f" · at DIP trail: {sum(1 for r in Fa if r['runner']=='1' and (fl(r.get('fill_dip_trail_r')) or -9) >= TAIL_R)}"
                 f" | labelled fired on: {sum(1 for r in Fa if r['labelled']=='1')} of 4")
        # verdict
        a = res["A"]["o_fill_orig"]
        b = res["B"]["o_fill_orig"]
        leg1 = a.get("gap") is not None and a["gap"] >= BAR_EDGE
        leg2 = a.get("n", 0) >= BAR_N and a.get("names", 0) >= BAR_NAMES
        leg3 = a.get("drop1") is not None and a["drop1"] >= BAR_EDGE
        leg3b = a.get("drop2") is not None and a["drop2"] >= BAR_EDGE
        leg4 = "can't tell" if b.get("n", 0) < MIN_HELDOUT else ("+" if (b.get("gap") or 0) > 0 else "-")
        if not leg2 and pop == "strict":
            v = "FAIL-on-n" if not (leg1 and leg3) else "FAIL-on-n (edge legs would pass)"
        elif not (leg1 and leg3):
            v = "FAIL"
        elif leg4 == "can't tell":
            v = "NOT_TESTABLE (ERA B unreadable)" if leg2 else "FAIL-on-n"
        elif leg4 == "+" and leg2:
            v = "PASS"
        else:
            v = "FAIL"
        verdicts[pop] = v
        L.append(f"\n  VERDICT [{pop}]: (1) ERA A edge {fm(a.get('gap'), '{:+.1f}')} pts >= +5 -> {leg1} · (2) n {a.get('n')} on {a.get('names')} names >= 100/60 -> {leg2} · "
                 f"(3) drop-best {fm(a.get('drop1'), '{:+.1f}')} >= +5 -> {leg3} (drop-best-two {fm(a.get('drop2'), '{:+.1f}')} -> {leg3b}) · "
                 f"(4) ERA B n {b.get('n', 0)} edge {fm(b.get('gap'), '{:+.1f}')} -> {leg4}  =>  {v}")
        L.append(f"    program standard beside: week-shuffle p (ERA A) {fm(a.get('p'), '{:.3f}')} · DISC {fm(res['DISC']['o_fill_orig'].get('gap'), '{:+.1f}')} (p {fm(res['DISC']['o_fill_orig'].get('p'), '{:.3f}')}) · "
                 f"HOA {fm(res['HOA']['o_fill_orig'].get('gap'), '{:+.1f}')} (n {res['HOA']['o_fill_orig'].get('n')}) · ex-May {fm(res['exMay']['o_fill_orig'].get('gap'), '{:+.1f}')} (n {res['exMay']['o_fill_orig'].get('n')})")
        L.append("")
    # incumbent ep_high_break edge from the 09-27 rows (horizon 09-25), for scale
    h2 = rd("hyp_rows_h2.tsv")
    L.append("=" * 140)
    L.append("INCUMBENT for scale — the lane's ep_high_break (no dip ever) on the same instrument, from hyp_rows_h2.tsv (09-27, horizon 09-25):")
    for ek in ("fill", "rec"):
        for sp in ("DISC", "HOA", "B"):
            fr = [r for r in h2 if r["pattern"] == "ep_high_break" and r["barrier"] == "orig" and r["bound"] == "pess" and r["is_fire"] == "1" and r["entry_kind"] == ek and r["split"] == sp and r["outcome"] != "abstain"]
            co = [r for r in h2 if r["pattern"] == "ep_high_break" and r["barrier"] == "orig" and r["bound"] == "pess" and r["is_fire"] == "0" and r["split"] == sp and r["outcome"] != "abstain"]
            if fr and co:
                f2 = 100 * sum(1 for r in fr if r["outcome"] == "target") / len(fr)
                c2 = 100 * sum(1 for r in co if r["outcome"] == "target") / len(co)
                L.append(f"    ep_high_break {ek:4s} {sp:4s} fires {len(fr):3d} vs ctl {len(co):4d}: {f2:.1f}% vs {c2:.1f}% -> {f2 - c2:+.1f} pts")
    L.append("")
    L.append(f"FINAL: strict (primary) {verdicts['strict']} · variant (beside) {verdicts['variant']}")
    txt = "\n".join(L) + "\n"
    (HERE / "h8_out.txt").write_text(txt)
    print(txt)


if __name__ == "__main__":
    main()
