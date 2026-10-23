"""Acceptance check for the survivorship refetch (2026-10-23), written before reading its output.
Bar (PLAN #705 / #314 recheck): the refetch must cover >= 90% of the liquid names the 2017-21 export misses, and the named controls
(TWTR, ATVI, EA, MRO, X, WBA) must be present to 2022-06-30. Two populations, both reported:
  A. the audit's known-gone list (runs_2026-10-23/universe/gone_list.tsv): status 'missing', not a derivative, no probable successor;
  B. symbols liquid (median $ volume >= 2M, price >= 2) in the 2022-24 export during Jan-Jun 2022 that the 2017-21 export lacks.
Identity check on B's overlap (Jan-Jun 2022): the refetched close vs the 2022-24 export's close, same symbol and day — a symbol that
names a different company in the two sources shows up as a price mismatch. Every miss is listed so it can be classified by eye
(a rename skipped by FIGI is a correct miss, not a recall failure).
usage: 03_recall_check.py <refetch_bars.csv> <records.tsv> <cb702_pre export> <cb702 export> <gone_list.tsv>"""
import sys, pandas as pd
bars_p, rec_p, pre_p, post_p, gone_p = sys.argv[1:6]
cols = ["ticker", "date", "o", "h", "l", "c", "v"]
rf = pd.read_csv(bars_p, names=cols, dtype={"ticker": str, "date": str})
rec = pd.read_csv(rec_p, sep="\t", dtype=str)
have = set(rf.ticker)
print(f"refetch: {rf.ticker.nunique():,} symbols with bars, {len(rf):,} bars; records {rec.ticker.nunique():,} symbols; "
      f"bars {rf.date.min()} .. {rf.date.max()}")
dup = rf.duplicated(["ticker", "date"]).sum(); print(f"duplicate (ticker, date) rows in the refetch: {dup}")
for s in ["TWTR", "ATVI", "EA", "MRO", "X", "WBA"]:
    x = rf[rf.ticker == s]
    print(f"  control {s}: {len(x)} bars, {x.date.min() if len(x) else '-'} .. {x.date.max() if len(x) else '-'}")
pre = pd.read_csv(pre_p, names=cols, usecols=[0, 1], dtype=str); pre_syms = set(pre.ticker); del pre
g = pd.read_csv(gone_p, sep="\t", dtype=str)
a = g[(g.status == "missing") & (g.deriv == "False") & g.probable_rename_to.isna() & g.bucket.str.startswith("gone")]
ah = a.ticker.isin(have)
print(f"\nA. known-gone, missing from the 2017-21 export, not derivative, no probable successor: {len(a)}; refetched {int(ah.sum())} = {100 * ah.mean():.1f}%")
print("   misses:", " ".join(a.ticker[~ah].tolist()))
post = pd.read_csv(post_p, names=cols, dtype={"ticker": str, "date": str})
w = post[(post.date >= "2022-01-03") & (post.date <= "2022-06-30")].copy(); del post
w["dv"] = w.c * w.v
liq = w.groupby("ticker").agg(dv=("dv", "median"), px=("c", "median"), n=("c", "size"))
liq = liq[(liq.dv >= 2e6) & (liq.px >= 2) & (liq.n >= 20)]
b = liq[~liq.index.isin(pre_syms)]
bh = b.index.isin(have)
print(f"\nB. liquid in the 2022-24 export Jan-Jun 2022 and absent from the 2017-21 export: {len(b)}; refetched {int(bh.sum())} = {100 * bh.mean():.1f}%")
print(f"   their share of B's dollar volume refetched: {100 * b.dv[bh].sum() / b.dv.sum():.1f}%")
print("   misses:", " ".join(sorted(b.index[~bh])))
m = w[w.ticker.isin(b.index[bh])].merge(rf, on=["ticker", "date"], suffixes=("_p", "_r"))
m["ratio"] = m.c_r / m.c_p
per = m.groupby("ticker").ratio.median()
ok = (per - 1).abs() <= 0.01
print(f"\nidentity on the overlap: {len(per)} symbols compared, median close ratio within 1%: {int(ok.sum())} = {100 * ok.mean():.1f}%")
print("   outside 1%:", ", ".join(f"{t} {r:.3f}" for t, r in per[~ok].sort_values().items()))
