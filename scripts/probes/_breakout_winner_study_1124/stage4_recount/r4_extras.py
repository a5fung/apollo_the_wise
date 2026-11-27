"""R4 stage 1d/1e extras (blind): (a) era-B overlap bridge: nights D 2022-04-01..2022-06-29 built from BOTH stores, agreement per gate for names in both;
(b) era-B volume-underflow count (name-nights failing only the dollar-volume half of the universe gate with a zero-volume row in the 20-session window)."""
import json, time
from collections import Counter, defaultdict
from datetime import date
import numpy as np, pandas as pd
import r4_common as C
import v1_replay as R
from agents.market_intelligence import breakout_v1 as bv
from agents.market_intelligence import consolidation_breakout as cb
from scripts.probes._cb_backtest import runner

C.assert_pins()
log = open(C.OUTD / "stage1d_extras.log", "w")


def P(*a):
    s = " ".join(str(x) for x in a); print(s, flush=True); log.write(s + "\n"); log.flush()


GATES = list(bv.GATES)


def night_rows(S, nights, tag):
    D = S.D
    facts = [R.ticker_facts(S, k) for k in range(len(D.tickers))]
    row_tid = np.repeat(np.arange(len(D.tickers), dtype=np.int64), (D.stop - D.start).astype(np.int64))
    order = np.argsort(D.ci, kind="stable")
    rows_at = R._RowsAt(order, D.ci[order], row_tid)
    out = {}
    cache = {}
    for ci in nights:
        members, _ = R.night_members(S, facts, ci, rows_at)
        rs_best, _, _, _ = cb.cross_section_one_date([m["r21"] for m in members], [m["r63"] for m in members], [m["r126"] for m in members], [None] * len(members))
        for m, rb in zip(members, rs_best):
            if rb is None or rb < bv.RS_MIN or not m["listable"] or not m["history"]:
                continue
            k = m["k"]
            if k not in cache: cache[k] = runner.bars_for(D, k)
            bars, cidx = cache[k]
            Di = m["i"] - facts[k]["a"]
            g = bv.v1_gates(bars, Di, rs_best=rb, raw_close=m["raw_close"], cidx=cidx)
            has_e = Di + 1 < len(bars) and int(cidx[Di + 1]) == ci + 1
            fire = bool(has_e and bars.h[Di + 1] > g["level"]) if g.get("level") is not None else False
            out[(D.cal[ci], m["ticker"])] = ({k_: bool(g["gates"][k_]["pass"]) for k_ in GATES if k_ in g["gates"]}, bool(g["ok"]), fire, g["level"])
    return out, facts, D


SA = R.load_store("A")
SB = R.load_store("B")
dates = [d for d in SB.D.cal if date(2022, 4, 1) <= d <= date(2022, 6, 29)]
ciA = {d: i for i, d in enumerate(SA.D.cal)}; ciB = {d: i for i, d in enumerate(SB.D.cal)}
assert all(d in ciA for d in dates)
oA, _, _ = night_rows(SA, [ciA[d] for d in dates], "A")
oB, factsB, DB = night_rows(SB, [ciB[d] for d in dates], "B")
both = sorted(set(oA) & set(oB))
P(f"OVERLAP BRIDGE: nights {dates[0]}..{dates[-1]} ({len(dates)}); rs>=35 listable-with-history name-nights: store A {len(oA):,}, store B {len(oB):,}, in both {len(both):,}")
res = {"nights": len(dates), "nA": len(oA), "nB": len(oB), "both": len(both), "gates": {}}
for gname in GATES:
    a = np.array([oA[k][0].get(gname) for k in both], dtype=object); b = np.array([oB[k][0].get(gname) for k in both], dtype=object)
    ag = float((a == b).mean())
    res["gates"][gname] = ag
    P(f"  gate {gname:11s} agreement {ag:.4%}  (differences {int((a != b).sum())})")
okA = np.array([oA[k][1] for k in both]); okB = np.array([oB[k][1] for k in both])
fA = np.array([oA[k][2] for k in both]); fB = np.array([oB[k][2] for k in both])
res["list_membership_agree"] = float((okA == okB).mean()); res["break_agree"] = float((fA == fB).mean())
res["list_rows_A_both"] = int(okA.sum()); res["list_rows_B_both"] = int(okB.sum()); res["list_both_and"] = int((okA & okB).sum())
P(f"  list membership (ok) agreement {(okA == okB).mean():.4%}: A-only {int((okA & ~okB).sum())}, B-only {int((~okA & okB).sum())}, both {int((okA & okB).sum())}; "
  f"break (level taken out on E) agreement {(fA == fB).mean():.4%}")
res["membership_note"] = "ok here is the full live list rule (context gates included); gates needing >130 bars (context) are not compared individually"
# ---------------------------------------------------------------- underflow (era B)
t0 = time.time()
nightsB = [ciB[d] for d in SB.D.cal if d >= date(2022, 4, 1)]
nset = np.zeros(len(SB.D.cal), bool)
for ci in nightsB:
    if ci + 1 < len(SB.D.cal): nset[ci] = True
bands = [(0, 1), (1, 5), (5, 20), (20, 100), (100, 1e9)]
cnt = Counter(); total_nn = 0; alt_cnt = Counter(); alt_total = 0
for k in range(len(DB.tickers)):
    f = factsB[k]; a, b = f["a"], f["b"]
    c = DB.c[a:b]; v = DB.v[a:b]; cidx = f["cidx"]
    n = b - a
    if n < 20: continue
    z = (v == 0).astype(np.int32)
    zc = np.concatenate(([0], np.cumsum(z)))
    zero20 = np.full(n, False); zero20[19:] = (zc[20:] - zc[:-20]) > 0
    dv = f["dv"]; raw = f["raw"]
    sel = nset[cidx] & zero20 & np.isfinite(dv) & (dv < bv.MIN_DOLLAR_VOL) & (raw >= bv.MIN_PRICE)
    for lo_, hi_ in bands:
        cnt[(lo_, hi_)] += int((sel & (c >= lo_) & (c < hi_)).sum())
    total_nn += int(sel.sum())
    # variant: the median over the NON-zero-volume days of the window would pass the floor (zeros read as missing)
    ii = np.flatnonzero(sel)
    if len(ii):
        cv = np.where(v > 0, c * v, np.nan)
        win = np.lib.stride_tricks.sliding_window_view(cv, 20)[ii - 19]
        with np.errstate(all="ignore"):
            med = np.nanmedian(win, axis=1)
        ok = med >= bv.MIN_DOLLAR_VOL
        alt_total += int(ok.sum())
        for lo_, hi_ in bands:
            alt_cnt[(lo_, hi_)] += int((ok & (c[ii] >= lo_) & (c[ii] < hi_)).sum())
listrows = int(pd.read_parquet(C.BIG / "r4_pool_eraB.parquet", columns=["ok"]).ok.sum())
P(f"UNDERFLOW (era B): name-nights with a zero-volume row in the 20-session window, dollar volume under $5M, raw close >= $2: {total_nn:,}; by adjusted-price band {dict(cnt)}; "
  f"vs era-B list rows {listrows:,} = {total_nn / listrows:.2%}  (trigger 1%)  [{time.time() - t0:.0f}s]")
P(f"  variant (zeros read as missing, the non-zero-day median would pass $5M): {alt_total:,} name-nights = {alt_total / listrows:.2%} of era-B list rows; by band {dict(alt_cnt)}")
res["underflow_alt"] = {"name_nights": alt_total, "share": alt_total / listrows, "by_band": {f"{k[0]}-{k[1]}": v for k, v in alt_cnt.items()}}
res["underflow"] = {"name_nights": total_nn, "by_band": {f"{k[0]}-{k[1]}": v for k, v in cnt.items()}, "list_rows_B": listrows, "share": total_nn / listrows}
json.dump(res, open(C.OUTD / "stage1d_extras_results_r4.json", "w"), indent=1, default=str)
