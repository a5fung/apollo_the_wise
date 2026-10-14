"""Local post-process of verify_rank_shadow_2026-10-14.out: sessions by EOD pool size, chance of 0-of-6, matured counts."""
import sys
from math import comb
sys.argv = ["x"]
exec(open("analyze_cells.py").read().split("main(*sys.argv")[0])  # reuse load()/x()
rows = load("verify_rank_shadow_2026-10-14.out")
pool = {}
for r in rows: pool[r["date"]] = r["pool_eod"]
singles = sorted(d for d, p in pool.items() if p == 1)
print("sessions", len(pool), "single-alert sessions", len(singles), "pools>=2", len(pool) - len(singles))
m = [r for r in rows if r["sess"] >= 6 and r["h5"] is not None]
print("matured", len(m), "matured in pools>=2", sum(1 for r in m if r["pool_eod"] >= 2), "matured top-q", sum(1 for r in m if r["r_eod"] <= 0.25))
big = [r for r in m if x(r, r["h5"]) >= 8]
print("8x winners:", [(r["ticker"], r["pool_eod"], r["r_eod"]) for r in big])
N, W, T = len(m), len(big), sum(1 for r in m if r["r_eod"] <= 0.25)
print(f"P(0 of {W} winners land in a {T}-row top cell | {N} matured, winners placed at random) = {comb(N-T, W)/comb(N, W):.3f}")
print("fraction of matured rows in top cell:", round(T/N, 3))
newly = [r for r in rows if r["sess"] == 6]
print("rows reaching exactly 6 sessions today:", [(r["ticker"], r["date"]) for r in newly])
print("rows reaching exactly 21 sessions today:", [(r["ticker"], r["date"]) for r in rows if r["sess"] == 21])
# maturity calendar for unmatured rows: need 6 sessions
print("unmatured:", [(r["ticker"], r["date"], r["sess"], r["r_eod"], r["pool_eod"]) for r in rows if r["sess"] < 6])
