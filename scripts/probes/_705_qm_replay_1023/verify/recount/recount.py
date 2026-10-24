#!/usr/bin/env python3
"""Independent recount of the frozen #705 QM replay headline numbers from its OUTPUT tables only (no 01_replay.py import, no walk).
Reads: qm_replay_1023/trades.tsv.gz, account_his.tsv, the era-A daily export (for the calendar / opens / closes), candidates_tl_com.tsv."""
import gzip, sys, collections, bisect
import numpy as np, pandas as pd

OUT = "/Users/alvinfung/apollo_data/cb702/qm_streams/qm_replay_1023/"
EXPORT_A = "/Users/alvinfung/apollo_data/cb702_pre_v2/daily_closes_all.csv.gz"
CAND_A = "/Users/alvinfung/apollo_data/cb702_pre_v2/out/candidates_tl_com.tsv"
ARM = "p33_s3_t10"

t = pd.read_csv(OUT + "trades.tsv.gz", sep="\t", dtype=str, keep_default_na=False)
for c in ("realized_r", "fill", "stop", "fill_minute", "sessions_held"):
    t[c] = pd.to_numeric(t[c].replace("", np.nan))
A = t[(t.era == "A") & (t.variant == "orh5")]
his_ev = A[A.is_his == "1"].drop_duplicates(["ticker", "E"])
ctl_ev = A[A.is_ctl == "1"].drop_duplicates(["ticker", "E"])
print("1. EVENT/TRADE STATS")
print("  his events (unique ticker,E):", len(his_ev), "| rows with both flags is_his&is_ctl:", int(((A.is_his == "1") & (A.is_ctl == "1")).sum()))
print("  his entry_status:", his_ev.entry_status.value_counts().to_dict(), "| reason:", his_ev.entry_reason.value_counts().to_dict())

def stats(df, label):
    df = df[(df.arm == ARM) & (df.entry_status == "filled")]
    mat = df[df.mature == "1"]
    r = mat.realized_r.to_numpy()
    n = len(r)
    print(f"  {label}: filled(arm rows)={len(df)} mature={n} mean={r.mean():+.4f} win={np.mean(r>0)*100:.2f}% ({int((r>0).sum())}/{n}) "
          f">=10R={int((r>=10).sum())} ({(r>=10).sum()/n*100:.2f}/100) >=5R={int((r>=5).sum())} ({(r>=5).sum()/n*100:.2f}/100) "
          f"max={r.max():+.2f} worst={r.min():+.2f} median={np.median(r):+.3f}")
    return mat
his = stats(A[A.is_his == "1"], "HIS")
ctl = stats(A[A.is_ctl == "1"], "CTL")
print("  control events:", len(ctl_ev), "| his arm-rows uniqueness (ticker,E):", his.duplicated(["ticker", "E"]).sum(), "dups")
print("\n5. BY YEAR OF E (his)")
for y, g in his.groupby("year"):
    print(f"  {y}: filled mature n={len(g)} mean={g.realized_r.mean():+.4f}")
print("  by-year events:", his_ev.groupby("year").size().to_dict())

print("\n2. ENTRY FACTS (his, era A, orh5)")
tw = his_ev[his_ev.entry_reason == "too_wide"].sort_values(["E", "ticker"])
nm = his_ev[his_ev.entry_reason == "no_minute_above_level"].sort_values(["E", "ticker"])
print(f"  too_wide={len(tw)}  no_minute_above_level={len(nm)}")
print("  LIST no_minute_above_level (ticker E):", "; ".join(f"{a} {b}" for a, b in zip(nm.ticker, nm.E)))
print("  LIST too_wide (ticker E width%):", "; ".join(f"{a} {b} {float(w)*100:.1f}" if w not in ("", None) else f"{a} {b}" for a, b, w in zip(tw.ticker, tw.E, tw.width_pct)))

# ---------------- calendar / bars
ex = pd.read_csv(EXPORT_A, header=None, names=["ticker", "d", "o", "h", "l", "c", "v"], dtype={"ticker": str, "d": str})
cal = sorted(ex.loc[ex.ticker == "SPY", "d"].unique())
sess = [l.strip() for l in open("/Users/alvinfung/apollo_data/cb702_pre_v2/sessions.txt") if l.strip()]
print("\ncalendar: SPY dates", len(cal), "== sessions.txt", len(sess), "identical:", cal == sess)
ci = {d: i for i, d in enumerate(cal)}
tks = set(his.ticker) | set(his_ev.ticker)
bars = {}
for tk, g in ex[ex.ticker.isin(tks)].groupby("ticker"):
    bars[tk] = {d: (o, c) for d, o, c in zip(g.d, g.o, g.c)}
del ex

# ---------------- 4. re-entries
print("\n4. RE-ENTRIES")
cand = pd.read_csv(CAND_A, sep="\t", dtype=str, keep_default_na=False, usecols=["K", "ticker", "E", "base_id"])
cand = cand[cand.K == "tl"]
print("  tl candidates:", len(cand))
later = collections.defaultdict(list)
for tk, b, E in zip(cand.ticker, cand.base_id, cand.E):
    later[(tk, b)].append(E)
his_keys = set(zip(his_ev.ticker, his_ev.E))
stopped = his[his.status.isin(["stopped", "stopped_day0"])]
n_with = n_rows = n_his = 0
for r in stopped.itertuples():
    e = ci[r.E]
    exit_d = cal[e + int(r.sessions_held)]
    lim = cal[min(len(cal) - 1, e + 20)]
    nxt = [E for E in later[(r.ticker, r.base_id)] if exit_d < E <= lim]
    n_with += bool(nxt); n_rows += len(nxt); n_his += sum((r.ticker, E) in his_keys for E in nxt)
print(f"  stopped out={len(stopped)} (stopped {int((stopped.status=='stopped').sum())} + stopped_day0 {int((stopped.status=='stopped_day0').sum())}); "
      f"with later break of same base after exit within 20 sessions of E={n_with}; such breaks={n_rows}; of them his calls={n_his}")

# ---------------- 3. account sim
print("\n3. ACCOUNT SIM (primary: 1% risk, 20% cap, 30%/stock at cost, skip if no room, prior-close MTM sizing)")
def build_trades(df):
    out = []
    for r in df.itertuples():
        e = ci[r.E]
        legs = []
        for lg in r.legs.split(";"):
            j, kind, frac, px = lg.split(":"); j = int(j); frac = float(frac); px = float(px)
            d = cal[e + j]
            o = bars[r.ticker].get(d, (None, None))[0]
            if kind == "trail" or kind == "stop_gap":
                order = 0
            elif kind == "partial":
                order = 3
            else:  # stop, day0_stop, day0_gap
                order = 0 if (j > 0 and o is not None and abs(px - o) < 1e-9) else 2
            legs.append((d, order, frac, px, kind))
        out.append(dict(ticker=r.ticker, E=r.E, fill=r.fill, stop=r.stop, fm=int(r.fill_minute), legs=legs, r=r.realized_r))
    return out

def simulate(trs, risk=0.01, cap=0.20, lim=0.30, room="skip", same_ticker="allow", verbose=False):
    byE = collections.defaultdict(list)
    for x in trs: byE[x["E"]].append(x)
    legs_by = collections.defaultdict(list)  # (date) -> list of (order, pos, frac, px)
    start = cal.index(min(byE)) 
    cash, eq_prev = 1.0, 1.0
    pos = []   # dict(tk, shares, fill, rem, legs)
    counts = collections.Counter()
    curve = {}
    yrs = {}
    last_exit = max(l[0] for x in trs for l in x["legs"])
    for i in range(start, ci[last_exit] + 1):
        d = cal[i]
        # sizing equity = prior close MTM = eq_prev
        def do_legs(order):
            nonlocal cash
            for p in pos:
                for k, lg in enumerate(p["legs"]):
                    if lg is not None and lg[0] == d and lg[1] == order:
                        sh = p["shares"] * lg[2]
                        cash += sh * lg[3]
                        p["rem"] -= lg[2]
                        p["legs"][k] = None
        do_legs(0)
        # entries in fill-minute order
        held = collections.defaultdict(float)
        for p in pos:
            held[p["tk"]] += p["shares"] * p["rem"] * p["fill"]
        for x in sorted(byE.get(d, []), key=lambda z: (z["fm"], z["ticker"])):
            width = (x["fill"] - x["stop"]) / x["fill"]
            frac = min(risk / width, cap)
            capb = risk / width > cap
            val = eq_prev * frac
            if same_ticker == "skip" and held[x["ticker"]] > 0:
                counts["skipped_same_ticker"] += 1; continue
            if lim is not None:
                roomleft = lim * eq_prev - held[x["ticker"]]
                if roomleft <= 1e-12:
                    counts["skipped_stock_limit"] += 1; continue
                if val > roomleft:
                    val = roomleft; counts["trimmed_stock_limit"] += 1
            if val > cash + 1e-12:
                if room == "trim" and cash > 1e-12:
                    val = cash; counts["trimmed_room"] += 1
                else:
                    counts["skipped_no_room"] += 1; continue
            cash -= val
            sh = val / x["fill"]
            if held[x["ticker"]] > 0: counts["concurrent_same_ticker"] += 1
            held[x["ticker"]] += val
            pos.append(dict(tk=x["ticker"], shares=sh, fill=x["fill"], rem=1.0, legs=list(x["legs"])))
            counts["entered"] += 1; counts["cap_bound_entered"] += capb
            counts["max_open"] = max(counts["max_open"], len(pos))
        do_legs(2)
        do_legs(3)
        pos = [p for p in pos if p["rem"] > 1e-9 or any(l is not None for l in p["legs"])]
        mtm = cash
        for p in pos:
            c = bars[p["tk"]].get(d)
            if c is None:   # no bar: carry last known close
                p.setdefault("lastc", p["fill"]); cc = p["lastc"]
            else:
                cc = c[1]; p["lastc"] = cc
            mtm += p["shares"] * p["rem"] * cc
        eq_prev = mtm
        curve[d] = mtm
    # yearly
    ye = {}
    for d, v in curve.items(): ye[d[:4]] = v
    prev, yr = 1.0, {}
    for y in sorted(ye):
        yr[y] = ye[y] / prev - 1; prev = ye[y]
    peak, dd = 0, 0
    for v in curve.values():
        peak = max(peak, v); dd = max(dd, 1 - v / peak)
    return dict(curve=curve, yearly=yr, final=eq_prev, dd=dd, counts=counts, open_left=len(pos), cash=cash)

trs = build_trades(his)
print("  trades in table (his, filled, mature, arm):", len(trs), "| sum realized_r:", round(sum(x["r"] for x in trs), 3))
# check legs sum to 1 and R from legs == realized_r
bad = 0
for x in trs:
    fs = sum(l[2] for l in x["legs"]); rr = sum(l[2] * (l[3] - x["fill"]) for l in x["legs"]) / (x["fill"] - x["stop"])
    if abs(fs - 1) > 1e-5 or abs(rr - x["r"]) > 1e-4: bad += 1
print("  trades whose legs do not sum to 1 or whose leg-R != realized_r (tol 1e-4):", bad)
res = {}
for name, kw in [("primary", {}), ("room_trim", dict(room="trim")), ("same_ticker_skip", dict(same_ticker="skip")), ("risk_0.5", dict(risk=0.005)),
                 ("risk_0.25", dict(risk=0.0025)), ("cap_10", dict(cap=0.10)), ("cap_30", dict(cap=0.30))]:
    s = simulate(trs, **kw); res[name] = s
    yy = " ".join(f"{y}:{v*100:+.1f}%" for y, v in s["yearly"].items())
    print(f"  {name:17s} final={s['final']:.3f} dd={s['dd']*100:.1f}% | {yy} | {dict(s['counts'])} open_left={s['open_left']}")

# compare daily curve to the saved account_his.tsv primary
ah = pd.read_csv(OUT + "account_his.tsv", sep="\t")
ap = ah[ah.config == "primary"].set_index("date").equity
mine = pd.Series(res["primary"]["curve"])
common = ap.index.intersection(mine.index)
diff = (ap.loc[common] - mine.loc[common]).abs()
print(f"\n  daily-curve compare vs account_his.tsv primary: days theirs={len(ap)} mine={len(mine)} common={len(common)}; max abs diff={diff.max():.6f} at {diff.idxmax()}; days with |diff|>0.001: {int((diff>0.001).sum())}")
