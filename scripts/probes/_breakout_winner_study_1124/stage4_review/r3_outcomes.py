#!/usr/bin/env python3
"""Stage 4 review, part 3. Reads ONLY captured files: stage-1f feature table (DISC kept rows), stage3/discovery_outcomes.tsv.gz (discovery,
E <= 2020-12-31 asserted), stage-1e kept-events tsv, audit flag DATES (klass / ticker / date columns only). NO BAR IS OPENED. No check
row is joined to anything after E. The `qm` column is never read. Output -> r3_outcomes.txt"""
import hashlib, sys, datetime as dt
from pathlib import Path
import numpy as np, pandas as pd
HERE = Path(__file__).resolve().parent; ST = HERE.parent; DATA = Path("/Users/alvinfung/apollo_data")
sys.path.insert(0, str(ST / "stage2"))
import s2lib as SL                                  # defs only (thirds helper the floors were calibrated on)
SL.assert_docs()
L = []
def P(s=""):
    print(s); L.append(str(s))
T = pd.read_csv(SL.TABLE, sep="\t", keep_default_na=False, na_values=[""], dtype={"ticker": str}, low_memory=False,
                usecols=lambda c: c != "qm")
D = T[(T.set == "DISC") & (T.kept == True)].reset_index(drop=True); del T
assert len(D) == 5330 and D.E.max() <= "2020-12-31"
O = pd.read_csv(ST / "stage3/discovery_outcomes.tsv.gz", sep="\t", keep_default_na=False, na_values=["nan"], dtype={"ticker": str, "truncated": str})
assert hashlib.sha256((ST / "stage3/discovery_outcomes.tsv.gz").read_bytes()).hexdigest().startswith("89f590d6") and O.E.max() <= "2020-12-31"
X = D.merge(O.drop(columns=["era", "D", "E", "kept", "kept2411", "Ey", "month"]), on=["ci", "ticker"], how="left", validate="1:1")
assert X.big.notna().all()
y = X.big.to_numpy(int)
P(f"discovery kept events {len(X)}, big winners {int(y.sum())} ({100 * y.mean():.2f}%)")

P("\n== A. WHO THE WINNERS ARE (composition of the 846; description) ==")
P("per year: " + ", ".join(f"{k} {int(v.sum())}/{len(v)}" for k, v in X.groupby("Ey").big))
st = X.sectype.fillna("unknown")
P("by security type (winners / events): " + ", ".join(f"{k} {int(v.sum())}/{len(v)} ({100 * v.mean():.1f}%)" for k, v in X.groupby(st).big))
px = X.raw_close_s.astype(float)
for lab, a, b in (("<$5", 0, 5), ("$5-10", 5, 10), ("$10-20", 10, 20), ("$20-50", 20, 50), (">=$50", 50, 1e12)):
    m = (px >= a) & (px < b); P(f"   raw price {lab}: {int(y[m].sum())}/{int(m.sum())} = {100 * y[m].mean():.1f}%")
w = X[X.big == 1]
nd = w.groupby("E").size()
P(f"winners sit on {len(nd)} break days; top days: " + ", ".join(f"{d} {n}" for d, n in nd.sort_values(ascending=False).head(8).items()))
wm = w.groupby("month").size().sort_values(ascending=False)
P(f"winners per month, top 8: " + ", ".join(f"{m} {n}" for m, n in wm.head(8).items()) + f"; the top 8 months hold {100 * wm.head(8).sum() / len(w):.1f}% of winners; months with no winner {int((X.groupby('month').big.sum() == 0).sum())} of {X.month.nunique()}")
wk = w.groupby("key").size()
P(f"winner identities {len(wk)}; identities with >= 2 winning events {int((wk >= 2).sum())} (max {wk.max()})")
P(f"winner on E's own close (first_hit = 0): {int((w.first_hit == 0).sum())}; first +50% close within 5 bars {int((w.first_hit <= 5).sum())}; median bar of first hit {w.first_hit.median():.0f}")
P(f"winners whose bars end inside the window: {int(w.ends_inside.sum())} of {int(X.ends_inside.sum())} such events; truncated events {int((X.truncated.fillna('') != '').sum())}, winners among them {int(w.truncated.fillna('').ne('').sum())}")
P("largest max-close / buy-point multiples (data-error watch list; a real 5x in 60 sessions is rare): ")
for r in X.sort_values("maxc", ascending=False).head(15).itertuples():
    P(f"   {r.ticker:6s} E {r.E} maxc {r.maxc:6.2f}x  bars {r.nbars}  price ${r.raw_close_s:.2f}  ADR {r.f01:.1f}%  type {r.sectype}  first hit bar {r.first_hit}")
P(f"events with maxc >= 3x: {int((X.maxc >= 3).sum())}; >= 5x: {int((X.maxc >= 5).sum())}; >= 10x: {int((X.maxc >= 10).sum())}")

P("\n== B. TRUNCATION EXPOSURE from audit-flag DATES (era-A flags file; klass / ticker / date only) ==")
fl = pd.read_csv(DATA / "cb702_pre_v2/audit_1023/price/A_flags.tsv", sep="\t", usecols=["check", "klass", "ticker", "date"], dtype=str, keep_default_na=False)
fl = fl[fl.date <= "2021-03-30"]
cal = [l.strip() for l in open(DATA / "cb702/bws1124_eraA_list_ctx.cal.txt")]
X["lo"] = [cal[c + 2] for c in X.ci]; X["hi"] = [cal[c + 61] for c in X.ci]
for chk, kl in (("splitlike", "volume_confirmed_relevel"), ("splitlike", "unconfirmed"), ("gap", "known_adjustment_event"), ("adj_event", "discontinuous_across_known_adjustment"), ("compare", "constant_ratio_unexplained")):
    f = fl[(fl.check == chk) & (fl.klass == kl)]
    by = f.groupby("ticker").date.apply(list).to_dict()
    hit = np.array([any(lo <= d <= hi for d in by.get(t, ())) for t, lo, hi in zip(X.ticker, X.lo, X.hi)])
    P(f"   {chk}/{kl}: flags dated <= 2021-03-30 {len(f)}; kept discovery events with one in E+1..E+60: {int(hit.sum())}, of which big winners {int(y[hit].sum())}"
      + (": " + ", ".join(f"{t} E {e} ({'W' if b else '-'} {m:.2f}x{' trunc' if tr else ''})" for t, e, b, m, tr in zip(X.ticker[hit], X.E[hit], X.big[hit], X.maxc[hit], X.truncated.fillna('')[hit] != '')) if 0 < hit.sum() <= 40 else ""))

P("\n== C. RATIOS RE-DERIVED (own counts on s2lib thirds) + A WITHIN-WEEK SHUFFLE (description: is the p alive when labels may only move inside one calendar week?) ==")
era, month = X.era.to_numpy(), X.month.to_numpy()
iso = np.array([("%d-%02d" % dt.date.fromisoformat(e).isocalendar()[:2]) for e in X.E])
day = X.E.to_numpy()
rng = np.random.default_rng(4)
def ratio(yy, t):
    return (yy[t == 2].mean()) / (yy[t == 0].mean())
for f, pub in (("f01", 3.245), ("f09", 2.315), ("f04", 1.984), ("f02", 0.584), ("B4", 1.065), ("f13", 1.742), ("f07", 2.219)):
    t = SL.assign_thirds(X[f].to_numpy(float), [era, month], 6)
    r = ratio(y, t)
    out = [f"{f}: n bottom/top {int((t == 0).sum())}/{int((t == 2).sum())} winners {int(y[t == 0].sum())}/{int(y[t == 2].sum())} ratio {r:.3f} (stage 3 printed {pub})"]
    for nm, strat in (("month", month), ("week", iso), ("day", day)):
        codes = pd.factorize(strat)[0]
        order = np.argsort(codes, kind="stable"); cs = codes[order]
        bounds = np.flatnonzero(np.r_[True, cs[1:] != cs[:-1], True])
        lr = np.empty(2000)
        for s in range(2000):
            yp = y.copy()
            for a, b in zip(bounds[:-1], bounds[1:]):
                if b - a > 1:
                    idx = order[a:b]; yp[idx] = y[idx][rng.permutation(b - a)]
            lr[s] = np.log(ratio(yp, t))
        p = (1 + int((np.abs(lr) >= abs(np.log(r)) - 1e-12).sum())) / 2001
        out.append(f"shuffle within {nm}: null median {np.exp(np.median(lr)):.3f}, 95% band {np.exp(np.percentile(lr, 2.5)):.2f}-{np.exp(np.percentile(lr, 97.5)):.2f}, p {p:.4f}")
    P("   " + " | ".join(out))
P("   note: a within-week / within-day shuffle removes everything a feature shares with WHEN the break happened; what is left is the feature's reading among names breaking in the same week / on the same day.")

P("\n== D. IS IT ONE STORY? carried features against each other (Spearman on discovery kept events; outcome-free) and each ratio inside the top ADR third ==")
cols = ["f01", "f02", "f04", "f09", "f07", "f13"]
P(X[cols].corr(method="spearman").round(2).to_string())
(HERE / "r3_outcomes.txt").write_text("\n".join(L) + "\n")
