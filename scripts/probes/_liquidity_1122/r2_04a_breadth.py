"""r2_04a: breadth (B3) and Amihud daily series from the common-stock universe closes (already cut at 2024-12-31 by awk). Run AFTER the selection freeze and the readings file."""
import pandas as pd, numpy as np
O = "build_r2"; CUT = pd.Timestamp("2024-12-31")
grid = pd.read_csv(f"{O}/legs_votes.csv", index_col=0, parse_dates=True).index
U = pd.read_csv(f"{O}/universe_cs_closes.csv.gz", names=["src", "t", "d", "c", "v"], parse_dates=["d"], dtype={"t": str}); assert U.d.max() <= CUT
out = [f"universe rows {len(U)}; tickers {U.t.nunique()}; max date {U.d.max().date()}"]
piv = lambda s, col: U[U.src == s].pivot_table(index="d", columns="t", values=col, aggfunc="last")
c1, v1, c2, v2 = piv("cb702_pre_v2", "c"), piv("cb702_pre_v2", "v"), piv("cb702", "c"), piv("cb702", "v")
# overlap price-base check
ov = c1.index.intersection(c2.index); both = c1.columns.intersection(c2.columns)
r = (c2.loc[ov, both] / c1.loc[ov, both]); med = r.median(); spread = r.max() / r.min() - 1; nobs = r.notna().sum()
same = (abs(med - 1) <= 0.005) & (spread <= 0.02); resc = (abs(med - 1) > 0.005) & (spread <= 0.02); unst = (spread > 0.02); noov = nobs == 0
out.append(f"overlap {ov[0].date()} -> {ov[-1].date()} ({len(ov)} sessions); tickers in both files {len(both)}: same base {int(same.sum())}, constant different base (rescaled) {int(resc.sum())}, unstable ratio (dropped after 2022-06-30) {int(unst.sum())}, in both but no shared session {int(noov.sum())}")
out.append(f"tickers only in pre_v2 {len(c1.columns.difference(c2.columns))}; only in cb702 {len(c2.columns.difference(c1.columns))}")
SPL = pd.Timestamp("2022-06-30"); cols = c1.columns.union(c2.columns)
fac = pd.Series(1.0, cols); fac[med[resc].index] = 1 / med[resc]
post = c2.loc[c2.index > SPL].reindex(columns=cols) * fac; post[list(unst[unst].index)] = np.nan
C = pd.concat([c1.reindex(columns=cols), post]).reindex(grid)
DV = pd.concat([(c1 * v1).reindex(columns=cols), (c2 * v2).loc[c2.index > SPL].reindex(columns=cols)]).reindex(grid)
out.append(f"universe sessions missing from the grid: {int(C.isna().all(axis=1).sum())}; grid {len(grid)}")
dv20 = DV.rolling(20, min_periods=20).mean(); pmax = C.shift(1).rolling(252, min_periods=252).max(); pmin = C.shift(1).rolling(252, min_periods=252).min()
el = (C >= 5) & (dv20 >= 5e6) & pmax.notna()
N = el.sum(axis=1); H = (el & (C > pmax)).sum(axis=1); L = (el & (C < pmin)).sum(axis=1)
b = ((H - L) / N).where(N > 0); B3 = b.rolling(10, min_periods=10).mean()
el2 = (C >= 5) & (dv20 >= 5e6); ill = (C.pct_change(fill_method=None).abs() / DV).where(el2 & (DV > 0)); am = ill.median(axis=1); AM = am.rolling(20, min_periods=20).mean()
pd.DataFrame({"N": N, "highs": H, "lows": L, "b": b, "B3": B3, "amihud_d": am, "amihud20": AM}).to_csv(f"{O}/breadth.csv")
out.append(f"breadth daily first {b.first_valid_index().date()}; B3 (10-day mean) first {B3.first_valid_index().date()} last {B3.last_valid_index().date()}; Amihud 20-day first {AM.first_valid_index().date()}")
out.append("N (eligible common stocks with 252 prior closes), median per year: " + str({int(y): int(x) for y, x in N[N > 0].groupby(N[N > 0].index.year).median().items()}))
last = C.apply(lambda s: s.last_valid_index()); first = C.apply(lambda s: s.first_valid_index())
out.append(f"survivorship: tickers with any close {int(last.notna().sum())}; whose LAST close is before 2024-12-01: {int((last < pd.Timestamp('2024-12-01')).sum())} (of which the unstable-ratio drops {int(unst.sum())}); whose first close is after 2016-03-01: {int((first > pd.Timestamp('2016-03-01')).sum())}")
out.append("-> the CS list is dated 2026-10-16: a ticker is in the universe only if it is on that list, so names delisted before then are absent = SURVIVORS-ONLY universe (breadth lows in 2016-24 are under-counted)." if (last < pd.Timestamp('2024-12-01')).sum() - unst.sum() < 50 else "-> some names end before 2024-12; see counts.")
print("\n".join(out))
