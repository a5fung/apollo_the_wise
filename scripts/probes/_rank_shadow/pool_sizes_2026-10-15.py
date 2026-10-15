"""Local post-process of verify_rank_shadow_2026-10-15.out: medians, pool sizes, chance numbers, maturity calendar."""
import sys, statistics as st
from math import comb
sys.argv = ["x"]
exec(open("analyze_cells.py").read().split("main(*sys.argv")[0])  # reuse load()/x()
rows = load("verify_rank_shadow_2026-10-15.out")
pool = {}
for r in rows: pool[r["date"]] = r["pool_eod"]
singles = sorted(d for d, p in pool.items() if p == 1)
print("sessions", len(pool), "single-alert sessions", len(singles), "pools>=2", len(pool) - len(singles))
m = [r for r in rows if r["sess"] >= 6 and r["h5"] is not None]
m20 = [r for r in rows if r["sess"] >= 21 and r["h20"] is not None]
print("matured5", len(m), "in pools>=2", sum(1 for r in m if r["pool_eod"] >= 2), "top-q EOD", sum(1 for r in m if r["r_eod"] <= 0.25))
print("matured20", len(m20), "top-q EOD", sum(1 for r in m20 if r["r_eod"] <= 0.25), "top-q 0945", sum(1 for r in m20 if r["r_0945"] <= 0.25))
for rk, lab in (("r_eod", "EOD"), ("r_0945", "09:45")):
    top = [x(r, r["h5"]) for r in m if r[rk] <= 0.25]; rest = [x(r, r["h5"]) for r in m if r[rk] > 0.25]
    print(f"5d median best-high xADR {lab}: top {st.median(top):.2f} (n={len(top)}) vs rest {st.median(rest):.2f} (n={len(rest)})")
    top = [x(r, r["h20"]) for r in m20 if r[rk] <= 0.25]; rest = [x(r, r["h20"]) for r in m20 if r[rk] > 0.25]
    print(f"20d median best-high xADR {lab}: top {st.median(top):.2f} (n={len(top)}) vs rest {st.median(rest):.2f} (n={len(rest)})")
big5 = [r for r in m if x(r, r["h5"]) >= 8]
N, W, T = len(m), len(big5), sum(1 for r in m if r["r_eod"] <= 0.25)
print(f"5d: P(0 of {W} winners land in a {T}-row top cell | {N} matured, random) = {comb(N-T, W)/comb(N, W):.3f}; top cell is {T/N:.3f} of matured")
big20 = [r for r in m20 if x(r, r["h20"]) >= 8]
N2, W2, T2 = len(m20), len(big20), sum(1 for r in m20 if r["r_eod"] <= 0.25)
print(f"20d: winners {[r['ticker'] for r in big20]}; P(>=1 of {W2} winners lands in a {T2}-row top cell | {N2} matured, random) = {1 - comb(N2-T2, W2)/comb(N2, W2):.3f}; top cell is {T2/N2:.3f} of matured")
print("broke-low rate EOD: top", sum(1 for r in m if r["r_eod"] <= 0.25 and r["l5"] < r["low"]), "of", T, "| rest", sum(1 for r in m if r["r_eod"] > 0.25 and r["l5"] is not None and r["l5"] < r["low"]), "of", N - T)
# floors: unmatured-20d rows already past 8x on the partial window (a floor, can only rise)
print("20d floors already >=8x but unmatured:", [(r["ticker"], r["date"], r["sess"], round(x(r, r["h20"]), 2), r["r_eod"], r["pool_eod"]) for r in rows if r["sess"] < 21 and r["h20"] is not None and x(r, r["h20"]) >= 8])
print("rows reaching exactly 6 sessions today:", [(r["ticker"], r["date"]) for r in rows if r["sess"] == 6])
print("rows reaching exactly 21 sessions today:", [(r["ticker"], r["date"], r["r_eod"], r["pool_eod"]) for r in rows if r["sess"] == 21])
print("unmatured5:", [(r["ticker"], r["date"], r["sess"], round(r["r_eod"], 3), r["pool_eod"]) for r in rows if r["sess"] < 6])
print("next 20d maturities:", sorted((r["sess"], r["ticker"], r["date"]) for r in rows if 17 <= r["sess"] < 21))
