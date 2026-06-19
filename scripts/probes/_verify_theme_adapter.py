"""Scratch: exercise the portfolio-app2 theme_data adapter against the real
snapshot + import-check the ported views. Run: python scripts/_verify_theme_adapter.py"""
import sys
sys.path.insert(0, r"C:\Users\lasto\Documents\portfolio-app2")

import theme_data as td

grid = td.get_weekly_grid(24)
print("grid.shape", grid.shape, "| cols:", list(grid.columns))
assert not grid.empty, "grid empty!"
for c in ["name", "week_start", "as_of_date", "stage", "rs_avg", "week_rank", "week_universe", "tickers"]:
    assert c in grid.columns, f"missing grid col {c}"
lw = grid["week_start"].max()
latest = grid[grid.week_start == lw].sort_values("week_rank")
print(f"latest week {lw} | n_themes {len(latest)} | universe {latest['week_universe'].iloc[0]}")
print(latest[["name", "rs_avg", "week_rank"]].head(6).to_string(index=False))
# rank sanity: rank 1 has the max rs_avg in that week
ranked = latest.dropna(subset=["week_rank"])
top = ranked.sort_values("week_rank").iloc[0]
assert top["rs_avg"] == ranked["rs_avg"].max(), "rank#1 is not max rs_avg"
print("rank#1 == max rs_avg OK")

active = td.get_active_themes(14)
print("active_themes", len(active), "| sample:", active[:3])
assert active, "no active themes"

theme, det = None, None
for t in active:
    d = td.get_theme_detail(t, 12)
    if d and not d["members"].empty:
        theme, det = t, d
        break
assert det, "no theme with members found"
print(f"\ndetail: {theme!r}")
print("  stage", det["stage"], "| rank", det["current_rank"], "| rs", det["rs_avg"], "| breadth", det["pct_above_20sma"])
print("  arc_weeks", len(det["arc"]), "| current_tickers", len(det["current_tickers"]), "| members", det["members"].shape, "| as_of", det["members_as_of"])
for c in ["ticker", "rs_composite", "rs_rank", "sector", "close", "sma_50"]:
    assert c in det["members"].columns, f"missing member col {c}"
print(det["members"].head(4).to_string(index=False))
print("  joined", det["joined"][:4], "| exited", det["exited"][:4])

prev = td.get_top_members_by_rs({theme: tuple(det["current_tickers"])}, 4)
print("\npreview:", prev[theme])

corr = td.get_correlated_themes(theme, 0.30)
print("correlated.shape", corr.shape)
if not corr.empty:
    print(corr[["name", "overlap_pct", "shared_count", "other_size"]].head(4).to_string(index=False))

# Import-check the ported view modules (catches syntax / NameError / bad imports)
import theme_grid  # noqa: F401
import theme_detail  # noqa: F401
print("\nVIEW IMPORTS OK")
print("ALL CHECKS PASSED")
