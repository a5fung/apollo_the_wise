#!/usr/bin/env python3
"""#702 P4b extension - is Alpaca-bar C0 the same C0? ($0: local files only)

On the overlap 2022-05-02..2022-06-30 the production watch table (`cb702/out/watch.tsv.gz`, Polygon bars) and the extension's
evaluator (Alpaca split bars, `ext_c0.Series`) can be compared night by night. For every ticker that has Alpaca bars, take each
night in the overlap that either source calls a C0 pass and compare. Writes EXT/parity.txt.
"""
import datetime as dt
import os
import random
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ext_c0  # noqa: E402

EXT = "/Users/alvinfung/apollo_data/cb702/qm_streams/ext_2016_2022"
LO, HI = dt.date(2022, 5, 2), dt.date(2022, 6, 30)


def main():
    ev = ext_c0.Evaluator(EXT)
    w = pd.read_csv(ext_c0.DATA + "/out/watch.tsv.gz", sep="\t", usecols=["ticker", "watch_date", "pole_date", "base_len", "prior_move", "base_depth"])
    w = w[(w.watch_date >= LO.isoformat()) & (w.watch_date <= HI.isoformat())]
    pw = {(r.ticker, r.watch_date): r for r in w.itertuples()}
    tickers = sorted({t for t in w.ticker if ev.symbol_of(t)})
    random.seed(11)
    sample = random.sample(tickers, min(250, len(tickers)))
    both = only_poly = only_alp = 0
    same_pole = same_len = 0
    prior_rel = []
    reasons = {}
    for t in sample:
        S = ev.series(t)
        for i in range(len(S.d)):
            d = dt.date.fromordinal(int(S.d[i]))
            if d < LO or d > HI:
                continue
            st, ft = S.night(i)
            a_pass = st == "pass"
            p = pw.get((t, d.isoformat()))
            if a_pass and p is not None:
                both += 1
                same_pole += int(ft["pole_date"] == p.pole_date)
                same_len += int(ft["base_len"] == p.base_len)
                prior_rel.append(abs(ft["prior_move"] / p.prior_move - 1))
            elif a_pass:
                only_alp += 1
            elif p is not None:
                only_poly += 1
                reasons[st] = reasons.get(st, 0) + 1
    tot = both + only_poly + only_alp
    L = [f"parity: {len(sample)} random tickers with Alpaca bars, nights {LO}..{HI}, nights where EITHER source passes C0: {tot}",
         f"  both pass {both} ({both / max(tot, 1):.1%}) | only Polygon-bar C0 passes {only_poly} | only Alpaca-bar C0 passes {only_alp}",
         f"  of the both-pass nights: same pole date {same_pole / max(both, 1):.1%}, same base length {same_len / max(both, 1):.1%}, "
         f"median |prior_move ratio - 1| {sorted(prior_rel)[len(prior_rel) // 2] if prior_rel else float('nan'):.4f}",
         f"  Polygon-only nights, why the Alpaca evaluator did not pass: {dict(sorted(reasons.items(), key=lambda x: -x[1])[:8])}"]
    # the full row logic (window match, last matching night, first breakout of the base) on three talk dates inside the watch era
    import match_bars
    wf = match_bars.load_watch(os.path.join(ext_c0.DATA, "out", "watch.tsv.gz"))
    wmap = {t: g for t, g in wf.groupby("ticker")}
    cf = match_bars.load_cands(os.path.join(ext_c0.DATA, "out", "candidates.tsv"))
    cmap = {b: g for b, g in cf.groupby("base_id")}
    n = c0_ok = last_ok = 0
    both_c0 = 0
    for t in sample:
        for ref in (dt.date(2022, 5, 3), dt.date(2022, 5, 17), dt.date(2022, 6, 1)):
            pm = match_bars.match_one(wmap.get(t), cmap, ref)
            am = ev.eval_row(t, ref)
            if not am["elig"] and not pm["c0"]:
                continue
            n += 1
            c0_ok += int(am["c0"] == pm["c0"])
            if am["c0"] == 1 and pm["c0"] == 1:
                both_c0 += 1
                last_ok += int(am["last_watch"] == pm["last_watch"])
    # breakout rows: on every night both sides call a C0 pass, are the breakout levels (k5 / k10 / full / trendline) broken the same way?
    # (compared with the production candidates by (ticker, D, K); the production table keys bases by a drift-robust chain, so the
    # first-pass match_one can miss a breakout of a base whose pole drifted by a session - the by-night comparison is the fair one)
    cf["key"] = list(zip(cf.ticker, cf.D, cf.K))
    pc = set(cf["key"])
    bn = b_same = 0
    for t in sample:
        S = ev.series(t)
        for i in range(len(S.d) - 1):
            d = dt.date.fromordinal(int(S.d[i]))
            if d < LO or d >= HI or (t, d.isoformat()) not in pw:
                continue
            st, ft = S.night(i)
            if st != "pass" or int(S.cidx[i + 1]) != int(S.cidx[i]) + 1:
                continue
            mine = {k for k in ext_c0.KS if ext_c0.cb.breaks_out(float(S.bars.h[i + 1]), ft[f"pivot_{k}"])}
            theirs = {k for k in ext_c0.KS if (t, d.isoformat(), k) in pc}
            bn += 1
            b_same += int(mine == theirs)
    L += [f"  full row logic on {n} (ticker, talk date) cases where either side is eligible/C0: same C0 flag {c0_ok / max(n, 1):.1%}; "
          f"of {both_c0} both-C0 cases: same last matching night {last_ok / max(both_c0, 1):.1%}",
          f"  breakout rows: on {bn} nights both sides pass C0 with a next session, the broken levels (k5/k10/full/trendline) are identical on {b_same / max(bn, 1):.1%}"]
    open(os.path.join(EXT, "parity.txt"), "w").write("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
