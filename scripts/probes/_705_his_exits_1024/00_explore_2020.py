"""2020 FIT-SET exploration (allowed: 2020 is the fit set): extra fast-exit markers vs his window."""
import importlib.util, sys, os, bisect
from collections import Counter
from datetime import date
import numpy as np
REPO = "/Users/alvinfung/apollo_the_wise"
spec = importlib.util.spec_from_file_location("hx", f"{REPO}/scripts/probes/_705_his_exits_1024/01_his_exits.py")
M = importlib.util.module_from_spec(spec); sys.modules["hx"] = M; spec.loader.exec_module(M)
say = M.Quiet()
S = M.load(say)
sel = M.select(S, M.FIT_WINDOW)
res, tally = M.walk_all(S, sel, say, "x")
rows = M.describe_rows(sel, res, S)
rows = [r for r in rows if r["filled"]]
by_eid = {e.eid: e for e in sel}
def first_of(pred, c_all, o_all, h_all, l_all, closes_through, nb, n_avail):
    for s in range(1, n_avail + 1):
        if pred(s): return s
    return None
out = Counter()
recs = []
for r in rows:
    ev = by_eid[r["eid"]]; w = res[ev.eid]
    bars, e, fwd = w["bars"], w["e"], w["fwd"]
    c_all = np.concatenate(([float(bars.c[e])], fwd.c)); o_all = np.concatenate(([float(bars.o[e])], fwd.o))
    h_all = np.concatenate(([float(bars.h[e])], fwd.h)); l_all = np.concatenate(([float(bars.l[e])], fwd.l))
    ct = np.concatenate((w["closes_before"], fwd.c)); nb = len(w["closes_before"]); n_avail = len(fwd)
    def sma(s, k):
        hi = nb + s
        return float(ct[hi-k:hi].mean()) if hi-k >= 0 else None
    m = {}
    m["red_close"] = first_of(lambda s: c_all[s] < c_all[s-1], *(c_all, o_all, h_all, l_all, ct, nb, n_avail))
    m["close_lt_prev_low"] = first_of(lambda s: c_all[s] < l_all[s-1], *(c_all, o_all, h_all, l_all, ct, nb, n_avail))
    m["low_lt_prev_low"] = first_of(lambda s: l_all[s] < l_all[s-1], *(c_all, o_all, h_all, l_all, ct, nb, n_avail))
    m["close_lt_sma5"] = first_of(lambda s: sma(s,5) is not None and c_all[s] < sma(s,5), *(c_all, o_all, h_all, l_all, ct, nb, n_avail))
    m["close_lt_open"] = first_of(lambda s: c_all[s] < o_all[s], *(c_all, o_all, h_all, l_all, ct, nb, n_avail))
    m["close_lt_fill"] = first_of(lambda s: c_all[s] < r["fill"], *(c_all, o_all, h_all, l_all, ct, nb, n_avail))
    m["two_red"] = first_of(lambda s: s >= 2 and c_all[s] < c_all[s-1] and c_all[s-1] < c_all[s-2], *(c_all, o_all, h_all, l_all, ct, nb, n_avail))
    m["close_lt_ema10"] = None
    for k, v in m.items():
        out[(k, M.rel(v, r["s_lo"], r["s_hi"]))] += 1
    recs.append((r, m))
print("n", len(rows))
for k in ["red_close","close_lt_prev_low","low_lt_prev_low","close_lt_sma5","close_lt_open","close_lt_fill","two_red"]:
    print(f"{k:20s}", {p: out[(k,p)] for p in ("before","within","after","never")})
# his exits by R bucket: hold length and what preceded
print("\nby R(exit_hi) bucket: n, median s_hi, median s_lo, share red_close within/before, share of windows with a red close on exit_hi")
import math
def bucket(r):
    x = r["r_hi"]
    return "<=-1" if x <= -1 else ("(-1,0)" if x < 0 else ("[0,2)" if x < 2 else ("[2,5)" if x < 5 else ">=5")))
for b in ("<=-1","(-1,0)","[0,2)","[2,5)",">=5"):
    g = [(r,m) for r,m in recs if bucket(r)==b]
    if not g: continue
    print(b, len(g), "s_hi med", np.median([r["s_hi"] for r,m in g]), "s_lo med", np.median([r["s_lo"] for r,m in g]),
          "red_close before/within", sum(1 for r,m in g if M.rel(m["red_close"], r["s_lo"], r["s_hi"]) in ("before","within")),
          "sma10 before/within", sum(1 for r,m in g if r["rel_sma10"] in ("before","within")),
          "ours before", sum(1 for r,m in g if r["our_vs_his"]=="before"), "ours after", sum(1 for r,m in g if r["our_vs_his"]=="after"),
          "our R mean", round(float(np.mean([r["our_r"] for r,m in g])),2), "his R(hi) mean", round(float(np.mean([r["r_hi"] for r,m in g])),2))
# the <= -1 exits: what are they? did our stop fire earlier (day0?)
g = [(r,m) for r,m in recs if r["r_hi"] <= -1]
print("\nR<=-1 exits:", Counter(r["our_status"] for r,m in g), "s_hi", Counter(r["s_hi"] for r,m in g))
print("  e.g.", [(r["ticker"], r["E"], r["s_lo"], r["s_hi"], round(r["r_lo"],2), round(r["r_hi"],2), r["our_status"], round(r["our_r"],2)) for r,m in g[:12]])
# the big ones
g = sorted([(r,m) for r,m in recs if r["r_hi"] >= 5], key=lambda x: -x[0]["r_hi"])
print("\nR>=5 exits:")
for r,m in g:
    print(f"  {r['ticker']:6s} {r['E']} his [{r['r_lo']:+.1f}..{r['r_hi']:+.1f}] s {r['s_lo']}-{r['s_hi']} | ours {r['our_r']:+.1f}@{r['our_s']} {r['our_status']} | sma10 {r['first_sma10']} sma20 {r['first_sma20']} red {m['red_close']} prevlow {m['close_lt_prev_low']} sma5 {m['close_lt_sma5']} maxR_to_hi {r['max_r_to_hi']:+.1f} | S1 {r['r_S1_r2_p33_tspd']:+.1f} S2 {r['r_S2_hold_t20']:+.1f} S3 {r['r_S3_c3_p33_tspd_cut3']:+.1f} S4 {r['r_S4_d3profit_p33_tspd']:+.1f}")
# sum R per candidate on 2020 filled
print("\nsum R 2020 filled: ours", round(sum(r["our_r"] for r in rows),1), "his(hi)", round(sum(r["r_hi"] for r in rows),1),
      {k: round(sum(r[f"r_{k}"] for r in rows),1) for k in M.RULES})
# hypothetical: sell at close of first red close after +2R? quick scoring of simple fast trails as whole-position rules (R at that close, else stop/our horizon)
