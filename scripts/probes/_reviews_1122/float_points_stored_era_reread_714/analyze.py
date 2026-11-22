"""float_points_stored_era_reread_714 — local analysis of 60_fresh_block.out. $0, no prod. Run from repo root:
   python scripts/probes/_reviews_1122/float_points_stored_era_reread_714/analyze.py <60_fresh_block.out> > analyze.out
Definitions are the FROZEN ones of docs/analysis/ep_float_neglect_prereg_2026-10-31.md (§3 runner, §5.1 F1, §5.3 strata,
§7.1 MH risk difference + stratified permutation, seed 714, 20,000 draws, §5.5 counterfactual). Nothing re-fitted."""
import sys, os, re, io, csv, json, math
import numpy as np, pandas as pd
sys.path.insert(0, os.getcwd())

def sections(path):
    out, cur = {}, None
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        if line.startswith("=== "):
            cur = line[4:].strip(); out[cur] = []; continue
        if cur is None or not line or re.fullmatch(r"\(\d+ rows?\)", line): continue
        out[cur].append(line)
    return out
def tab(lines):
    if len(lines) < 1: return pd.DataFrame()
    return pd.read_csv(io.StringIO("\n".join(lines)), sep="|", quoting=csv.QUOTE_NONE, dtype=str, keep_default_na=False)
def num(s): return pd.to_numeric(s.replace("", np.nan), errors="coerce")

S = sections(sys.argv[1])
pop = tab(S["FRESH_POP"]); bars = tab(S["FRESH_BARS"])
for c in ["ep_score","ep_bar","gap_pct","float_shares","float_any_tick","n_float_ticks","fwd_10d_pct"]: pop[c] = num(pop[c])
for c in ["open_price","high_price","low_price","close","volume"]: bars[c] = num(bars[c])
bars["trade_date"] = pd.to_datetime(bars["trade_date"]); pop["scan_date"] = pd.to_datetime(pop["scan_date"])
print(f"POP rows {len(pop)}  tickers {pop.ticker.nunique()}  dates {pop.scan_date.min().date()}..{pop.scan_date.max().date()}")
print("scored-row float coverage: chosen tick", int(pop.float_shares.notna().sum()), " any tick", int(pop.float_shares.fillna(pop.float_any_tick).notna().sum()))
spy = bars[bars.ticker == "SPY"].sort_values("trade_date"); cal = list(spy.trade_date)
print("SPY last bar", cal[-1].date())
B = {t: g.sort_values("trade_date").reset_index(drop=True) for t, g in bars.groupby("ticker")}

def outcome(tk, d):
    g = B.get(tk)
    if g is None or d not in cal: return None
    fwd_dates = [x for x in cal if x > d][:15]
    if len(fwd_dates) < 15: return "CENSORED"
    row = g[g.trade_date == d]
    if row.empty: return None
    gc = float(row.close.iloc[0]); pre = g[g.trade_date < d].tail(20)
    if len(pre) < 20: return None
    adr = float(((pre.high_price - pre.low_price) / pre.close).mean()) * gc
    f = g[g.trade_date.isin(fwd_dates)]
    if len(f) < 15 or adr <= 0: return None
    return dict(run_xadr=(float(f.high_price.max()) - gc) / adr, maxexc=float(f.high_price.max()) / gc - 1,
                advd=float((pre.close * pre.volume).mean()))
rows = []
for r in pop.itertuples():
    o = outcome(r.ticker, r.scan_date)
    rows.append(o if isinstance(o, dict) else {"run_xadr": np.nan, "maxexc": np.nan, "advd": np.nan, "_why": o})
pop = pd.concat([pop.reset_index(drop=True), pd.DataFrame(rows)], axis=1)
print("outcome status: ok", int(pop.run_xadr.notna().sum()), " censored", int((pop["_why"] == "CENSORED").sum()) if "_why" in pop else 0, " unreadable", int(pop.run_xadr.isna().sum()))
pop["flt"] = pop.float_shares.fillna(pop.float_any_tick)
pop["lowfloat"] = ((pop.flt > 0) & (pop.flt < 5e7)).astype(float).where(pop.flt.notna())
pop["runner"] = (pop.run_xadr >= 5.0).astype(float).where(pop.run_xadr.notna())
d = pop[pop.runner.notna() & pop.lowfloat.notna() & pop.advd.notna()].copy()
print(f"READABLE n={len(d)} runners={int(d.runner.sum())} ({d.runner.mean():.1%}); lowfloat n={int(d.lowfloat.sum())}")
print(f"  >=8ADR {(d.run_xadr>=8).mean():.1%}   max-excursion>=+50% {(d.maxexc>=.5).mean():.1%}   P90 max excursion {d.maxexc.quantile(.9):.1%}")

# frozen strata ladder (§5.3), merge <15 into next lower
cuts = [0, 5e7, 1e8, 2.5e8, 5e8, np.inf]
d["st"] = pd.cut(d.advd, cuts, right=False, labels=False).astype(int)
cnt = d.st.value_counts().to_dict()
for s in range(4, 0, -1):
    if cnt.get(s, 0) < 15 and cnt.get(s, 0) > 0:
        d.loc[d.st == s, "st"] = s - 1; cnt = d.st.value_counts().to_dict()
print("strata sizes", dict(sorted(cnt.items())))

def mh(y, g, s):
    num_ = den = 0.0
    for k in np.unique(s):
        m = s == k; n1 = (g[m] == 1).sum(); n0 = (g[m] == 0).sum()
        if n1 == 0 or n0 == 0: continue
        w = n1 * n0 / m.sum(); rd = y[m][g[m] == 1].mean() - y[m][g[m] == 0].mean()
        num_ += w * rd; den += w
    return num_ / den if den else float("nan")
def perm(y, g, s, draws=20000, seed=714):
    rng = np.random.default_rng(seed); obs = mh(y, g, s); ge = le = 0
    idx = {k: np.where(s == k)[0] for k in np.unique(s)}
    for _ in range(draws):
        gp = g.copy()
        for ix in idx.values(): gp[ix] = rng.permutation(g[ix])
        v = mh(y, gp, s); ge += v >= obs - 1e-12; le += v <= obs + 1e-12
    return obs, (1 + ge) / (draws + 1), (1 + le) / (draws + 1)
def read(df, label):
    y, g, s = df.runner.values.astype(float), df.lowfloat.values.astype(float), df.st.values
    n1 = int(g.sum())
    if n1 == 0 or n1 == len(g): print(label, "no variation"); return
    rd, p, prev = perm(y, g, s)
    u = y[g == 1].mean() - y[g == 0].mean()
    print(f"{label}: low {int(y[g==1].sum())}/{n1} ({y[g==1].mean():.1%}) vs rest {int(y[g==0].sum())}/{int((g==0).sum())} ({y[g==0].mean():.1%});"
          f" unstratified {u*100:+.1f}pp; MH RD {rd*100:+.1f}pp; one-sided p {p:.4f} (p_rev {prev:.4f})")
    for k in sorted(np.unique(s)):
        m = s == k; a = y[m & (g == 1)]; b = y[m & (g == 0)]
        print(f"   stratum {k}: low {int(a.sum())}/{len(a)} vs rest {int(b.sum())}/{len(b)}")
read(d, "FRESH BLOCK (all, stored float)")
ds = d[d.float_shares.notna()]
read(ds, "FRESH BLOCK (chosen-tick stored float only)")
print("BAR: Confirmed = RD>0 AND one-sided p<=0.10 (prereg §10). At n~100 it can contradict, not establish.")

# per-row listing of low-float rows (no hiding)
print("\nLOW-FLOAT ROWS: ticker scan_date float ep_score tier ep_bar advd run_xadr runner")
for r in d[d.lowfloat == 1].sort_values("scan_date").itertuples():
    print(f"  {r.ticker} {r.scan_date.date()} {r.flt:,.0f} {r.ep_score} {r.score_tier} {r.ep_bar} {r.advd:,.0f} {r.run_xadr:.2f} {int(r.runner)}")

# counterfactual: alerts that exist only because of the +5 (prereg §5.5)
print("\nCOUNTERFACTUAL (float points -> 0), era rows with score_breakdown + ep_bar")
try:
    from agents.market_intelligence import ep_rubric as R, ep_score_math as M
    w = R.SCORE_WEIGHTS; scale = w["output_scale"]; rules = w["conviction_floor"]["rules"]
    era = pop[(pop.score_breakdown != "") & pop.ep_bar.notna()]
    n_ok = n_flip = 0; flips = []
    for r in era.itertuples():
        parts = {k: float(v) for k, v in json.loads(r.score_breakdown).items()}
        raw = sum(parts.values()); score = float(r.ep_score); bar = float(r.ep_bar)
        mult = round((score - scale["offset"]) / scale["mult"], 1) / raw if raw > 0 else np.nan
        if not np.isfinite(mult): continue
        fact = R.apply_output_scale(round(raw * mult, 1), scale); n_ok += abs(fact - score) <= 0.05
        floor = R.resolve_conviction_floor(float(r.gap_pct), r.catalyst_quality, rules) if np.isfinite(r.gap_pct) else None
        p2 = dict(parts); p2["float"] = 0.0
        o2 = sum(v for k, v in p2.items() if k != "conviction_floor"); raw2 = max(o2, floor) if floor is not None else o2
        cf = R.apply_output_scale(round(raw2 * mult, 1), scale)
        if score >= bar and cf < bar and parts.get("float", 0) > 0:
            flips.append((r.ticker, r.scan_date.date(), score, round(cf, 1), r.score_tier, r.any_high_alert, r.runner))
    print(f"era rows {len(era)}; factual rebuild matches {int(n_ok)}/{len(era)} (C5 bar: >=99%, else withhold)")
    print(f"N_flip (clears bar with float, not without) = {len(flips)}; each: ticker date score score_cf tier any_high ran_big")
    for f in flips: print("  ", f)
except Exception as e:
    print("COUNTERFACTUAL FAILED:", repr(e))
