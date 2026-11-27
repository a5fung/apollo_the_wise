"""R4 stage 1f recount: Qullamaggie coverage (1.4.1) and position (1.4.2) tables, outcome-free. buys read with usecols ticker/E/lo/hi only."""
import bisect, json, re
from collections import defaultdict
import numpy as np, pandas as pd
import r4_common as C
import r4_features as F
import v1_replay as R
from scripts.probes._cb_backtest import runner
from scipy_free import wilson  # noqa
bd = pd.read_csv(C.BUYS, sep="\t", usecols=["ticker", "E"], dtype=str, keep_default_na=False)
bu = pd.read_csv(C.BUYS_W, sep="\t", usecols=["ticker", "lo", "hi"], dtype=str, keep_default_na=False)
W = pd.read_parquet(C.BIG / f"r4_events_postdrop{C.SUF}.parquet"); Kp = pd.read_parquet(C.BIG / f"r4_events_kept{C.SUF}.parquet")
pool = {e: pd.read_parquet(C.BIG / f"r4_pool_era{e}.parquet") for e in "AB"}
live = pd.concat([pool[e][pool[e].ok & pool[e].has_e & (pool[e].hE > pool[e].level)].assign(era=e) for e in "AB"], ignore_index=True)
live = live[live.D <= "2024-10-03"]          # last D whose E+60 is a session <= 2024-12-31 (the nights built for the study)
bridge = pd.concat([pool[e][pool[e].has_e & (pool[e].hE > pool[e].level)].assign(era=e) for e in "AB"], ignore_index=True)
bridge = bridge[bridge.D <= "2024-10-03"]
def place(rows):
    byt = defaultdict(list)
    for r in rows[["ticker", "E", "era", "D"]].itertuples(index=False):
        byt[r.ticker].append((r.E, r.era, r.D))
    for t in byt: byt[t].sort()
    out = []
    for t, e in zip(bd.ticker, bd.E):
        hit = [x for x in byt.get(t, ()) if x[0] == e]
        out.append(("dated", t, hit[0] if hit else None, e))
    for t, lo, hi in zip(bu.ticker, bu.lo, bu.hi):
        es = byt.get(t, []); i = bisect.bisect_left(es, (lo,))
        out.append(("undated", t, es[i] if i < len(es) and es[i][0] <= hi else None, lo))
    return out
res = {}
pl = {k: place(v) for k, v in (("bridge", bridge), ("live", live), ("postdrop", W))}
kept_keys = set(zip(Kp.era, Kp.ticker, Kp.D)); kept2411 = set(zip(W[W.kept2411].era, W[W.kept2411].ticker, W[W.kept2411].D))
print("buys", len(bd) + len(bu))
for k, v in pl.items():
    res[k] = sum(1 for x in v if x[2])
    print(k, res[k], "dated", sum(1 for x in v if x[2] and x[0] == "dated"), "undated", sum(1 for x in v if x[2] and x[0] == "undated"))
kp = [x for x in pl["postdrop"] if x[2] and (x[2][1], x[1], x[2][2]) in kept_keys]
k2 = [x for x in pl["postdrop"] if x[2] and (x[2][1], x[1], x[2][2]) in kept2411]
print("kept 1124", len(kp), "dated", sum(1 for x in kp if x[0] == "dated"), "undated", sum(1 for x in kp if x[0] == "undated"), "| by era", pd.Series([x[2][1] for x in kp]).value_counts().to_dict(), "| kept 2411", len(k2))
print("live by era:", pd.Series([x[2][1] for x in pl["live"] if x[2]]).value_counts().to_dict(), "| distinct live rows", len({(x[2][1], x[1], x[2][2]) for x in pl["live"] if x[2]}))
yrs = defaultdict(lambda: defaultdict(int))
for name in ("bridge", "live", "postdrop"):
    for x in pl[name]:
        if x[2]: yrs[int(x[2][0][:4])][name] += 1
for x in kp: yrs[int(x[2][0][:4])]["kept"] += 1
for x in k2: yrs[int(x[2][0][:4])]["kept2411"] += 1
allb = defaultdict(int)
for x in pl["live"]:
    pass
print("year bridge live postdrop kept kept2411:", {y: (d["bridge"], d["live"], d["postdrop"], d["kept"], d["kept2411"]) for y, d in sorted(yrs.items())})
res["kept"] = len(kp); res["kept2411"] = len(k2)
res["by_year"] = {y: dict(d) for y, d in sorted(yrs.items())}
# ---------- position: feature values at placed post-drop rows
from collections import Counter
mult = Counter((x[2][1], x[1], x[2][2]) for x in pl["postdrop"] if x[2])
placed = {k_: 1 for k_ in mult}
gA, _ = C.load_guard(C.GUARD_A, "A"); gB, _ = C.load_guard(C.GUARD_B, "B"); fA, _ = C.load_flags(C.FLAGS_A); fB, _ = C.load_flags(C.FLAGS_B)
rows = []
for era, guard, flags in (("A", gA, fA), ("B", gB, fB)):
    S = R.load_store(era); Dd = S.D
    sub = W[(W.era == era)]
    sub = sub[[ (era, t, d) in placed for t, d in zip(sub.ticker, sub.D)]]
    for r in sub.itertuples():
        k = Dd.tid[r.ticker]; bars, cidx = runner.bars_for(Dd, k)
        Di = int(np.searchsorted(cidx, r.ci))
        cx = F.Ctx(era, Dd.cal, int(Dd.ci[Dd.start[k]]), guard, flags)
        xs = {"rs_1m": r.rs_1m, "rs_6m": r.rs_6m, "group_strength": r.group_strength, "pick_score": r.pick_score, "order_score": r.order_score}
        vals, why = F.compute(cx, bars, cidx, Di, r.ci, r.ticker, r.rs_best, r.raw_close, r.raw_src, xs)
        rows.append({"era": era, "ticker": r.ticker, "D": r.D, "E": r.E, **{f: vals.get(f, np.nan) for f in F.FEATS}, "f24_above": vals["f24_above"]})
Q = pd.DataFrame(rows)
FT = pd.read_parquet(C.BIG / f"r4_feature_table{C.SUF}.parquet")
FT["month"] = FT.E.str[:7]
Q["month"] = Q.E.str[:7]
def third_of(vals, x):
    """x inserted into vals (a group's scored values); tie block of x -> lower-middle position -> np.array_split third; returns 0/1/2"""
    allv = np.sort(np.append(vals, x)); m = len(allv)
    i = int(np.searchsorted(allv, x, "left")); j = int(np.searchsorted(allv, x, "right")) - 1
    mid = (i + j) // 2
    sizes = [m // 3 + (1 if t < m % 3 else 0) for t in range(3)]
    return int(np.repeat(np.arange(3), sizes)[mid])
out = {}
feats = [f for f in F.FEATS]
for f in feats + ["f24a", "f24b"]:
    if f in ("f24a", "f24b"):
        src = "f24"; msk = lambda df, up: (df.f24_above == 1) if up else (df.f24_above == 0)
    cnt = np.zeros(3); n = 0; yes = 0
    for q in Q.itertuples():
        base = FT[(FT.era == q.era) & (FT.month == q.month)]
        if f in ("f24a", "f24b"):
            up = (f == "f24a")
            if (q.f24_above == 1) != up: continue
            base = base[(base.f24_above == 1) == up]; x = q.f24; col = "f24"
        else:
            x = getattr(q, f); col = f
        if not np.isfinite(x): continue
        w = mult[(q.era, q.ticker, q.D)]
        if f in ("f11", "f14", "f23"):
            n += w; yes += w * int(x == 1.0); continue
        vals = base[col].to_numpy(float); vals = vals[np.isfinite(vals)]
        if len(vals) < 6: continue
        key = (q.era, q.ticker, q.D)
        if key in kept_keys:                      # its own third: re-read inside the group (the buy is a member already)
            a = np.sort(vals); i = int(np.searchsorted(a, x, "left")); j = int(np.searchsorted(a, x, "right")) - 1; mid = (i + j) // 2
            sizes = [len(a) // 3 + (1 if t < len(a) % 3 else 0) for t in range(3)]
            t_ = int(np.repeat(np.arange(3), sizes)[mid])
        else:
            t_ = third_of(vals, x)
        cnt[t_] += w; n += w
    out[f] = (n, cnt.tolist(), yes)
    if f in ("f11", "f14", "f23"):
        print(f"{f:5s} placed {n} yes {yes} = {yes / max(1, n):.1%}")
    else:
        sh = cnt / max(1, n)
        print(f"{f:5s} placed {n:4d} bottom {sh[0]:.1%} middle {sh[1]:.1%} top {sh[2]:.1%}")
json.dump({"coverage": res, "position": out}, open(C.OUTD / f"r4_qm{C.SUF}.json", "w"), indent=1, default=str)
