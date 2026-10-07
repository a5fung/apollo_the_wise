"""#624 backfill — STAGE 1 lists (outcome-blind: inputs only). Writes:
  list_min_s1.txt   minute pulls: L19 + F300 + the live-window (2026-09-09..10-05) superset after the prefilter
  list_ref_s1a.txt  reference reads: L19 + S300 + the point-in-time cap spot-check (10 names x 2 dates)
  s1_samples.json   the F300 / S300 / spot-check draws (seed 624) and the prefilter counts
"""
import json
import random
from collections import Counter, defaultdict
from datetime import date, time

import lib624 as L

L.assert_frozen()
daily = L.load_daily()
cand = L.load_cand()
sect = L.load_sectypes()
splits = L.load_splits()
sig = json.load(open(L.HERE / "s0_lane_signals.json"))

out = {}
# L19
l19 = sorted({(s["ticker"], s["scan_date"]) for s in sig})
out["L19"] = l19

# F300 — seed 624, proportional by tick
pool = []
for line in list(open(L.HERE / "s0_f300_pool.tsv"))[1:]:
    p = line.rstrip("\n").split("|")
    msoo = int(p[2])
    tick = "09:30" if msoo == 1 else f"09:{30 + msoo:02d}"
    pool.append({"d": p[0], "t": p[1], "msoo": msoo, "tick": tick, "vol": float(p[3])})
pool.sort(key=lambda r: (r["d"], r["t"]))
by_tick = defaultdict(list)
for r in pool:
    by_tick[r["tick"]].append(r)
N = 300
raw_alloc = {k: N * len(v) / len(pool) for k, v in by_tick.items()}
alloc = {k: int(x) for k, x in raw_alloc.items()}
for k in sorted(raw_alloc, key=lambda k: -(raw_alloc[k] - alloc[k]))[:N - sum(alloc.values())]:
    alloc[k] += 1
rng = random.Random(624)
f300 = []
for k in sorted(by_tick):
    f300 += rng.sample(by_tick[k], alloc[k])
out["F300"] = f300
out["F300_alloc"] = alloc

# S300 — up to 150 below / 150 at-or-above $500M, seed 624
s_pool = []
for line in list(open(L.HERE / "s0_s300_pool.tsv"))[1:]:
    p = line.rstrip("\n").split("|")
    s_pool.append({"t": p[0], "d": p[1], "cap": float(p[2]), "pc": L.fnum(p[3]), "px": L.fnum(p[4]), "gap": L.fnum(p[5]),
                   "t_et": p[6], "msoo": p[7]})
s_pool.sort(key=lambda r: (r["d"], r["t"]))
below = [r for r in s_pool if r["cap"] < 5e8]
above = [r for r in s_pool if r["cap"] >= 5e8]
rng = random.Random(624)
s300 = rng.sample(below, min(150, len(below))) + rng.sample(above, min(150, len(above)))
out["S300"] = s300
out["S300_pool"] = {"below": len(below), "above": len(above)}

# the prefilter (no look-ahead: it only drops rows the rule can never admit)
pref = Counter()
lw, bw = [], []
for r in cand:
    t, d = r["t"], r["d"]
    if t in L.SKIP_TICKERS:
        pref["skip_tickers"] += 1; continue
    st = sect.get(t)
    if st in L.NONSTOCK_TODAY:
        pref["nonstock_today"] += 1; continue
    hist = L.vol_history(daily.get(t), d)
    if not hist:
        pref["no_volume_history"] += 1; continue
    pct = L.LL._volume_percentile(r["v"], hist)
    if pct < 90.0:
        pref["day_volume_below_p90"] += 1; continue
    row = {"t": t, "d": d.isoformat(), "typed": st or "untyped_today"}
    (lw if d >= date(2026, 9, 9) else bw).append(row)
pref["pass_live_window"] = len(lw)
pref["pass_backfill_window"] = len(bw)
pref["pass_backfill_typed_stock"] = sum(1 for r in bw if r["typed"] in L.STOCK_TYPES)
pref["pass_backfill_untyped_today"] = sum(1 for r in bw if r["typed"] == "untyped_today")
pref["pass_backfill_other_type"] = sum(1 for r in bw if r["typed"] not in L.STOCK_TYPES + ("untyped_today",))
pref["pass_backfill_names"] = len({r["t"] for r in bw})
out["prefilter"] = dict(pref)
out["LW"] = lw
out["BW"] = bw

# point-in-time cap spot-check: 10 prefilter-passing 2024-25 names with a LATER >= 1:5 reverse split
spot_pool = sorted({(r["t"], r["d"]) for r in bw if r["d"] < "2026-01-01"
                    and L.fac_prior(splits, r["t"], date.fromisoformat(r["d"])) <= 0.2})
rng = random.Random(624)
spot = rng.sample(spot_pool, min(10, len(spot_pool)))
out["SPOT"] = [{"t": t, "d": d, "fac": L.fac_prior(splits, t, date.fromisoformat(d))} for t, d in spot]
out["SPOT_pool_n"] = len(spot_pool)

mins = sorted(set([(t, d) for t, d in l19] + [(r["t"], r["d"]) for r in f300] + [(r["t"], r["d"]) for r in lw]),
              key=lambda x: (x[1], x[0]))
refs = sorted(set([(t, d) for t, d in l19] + [(r["t"], r["d"]) for r in s300]
                  + [(s["t"], s["d"]) for s in out["SPOT"]] + [(s["t"], "2026-10-01") for s in out["SPOT"]]),
              key=lambda x: (x[1], x[0]))
open(L.HERE / "list_min_s1.txt", "w").write("\n".join(f"{t}|{d}" for t, d in mins) + "\n")
open(L.HERE / "list_ref_s1a.txt", "w").write("\n".join(f"{t}|{d}" for t, d in refs) + "\n")
json.dump(out, open(L.HERE / "s1_samples.json", "w"), indent=0, default=str)
print("prefilter", dict(pref))
print("F300 alloc", alloc, "S300 pool", out["S300_pool"], "S300 drawn", len(s300), "SPOT pool", len(spot_pool))
print("minute pulls s1", len(mins), "ref reads s1a", len(refs))
