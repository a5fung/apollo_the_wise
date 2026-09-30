"""READ-ONLY replay of the /themes (Telegram) render path against captured prod inputs.
Runs the REAL repo functions (_compute_scored_themes, format_ecosystem_board) on the rows captured
by fetch_580_theme_inputs.sql. No DB, no network. Output -> replay_themes_output.txt
"""
import json, sys, pathlib, collections
ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
raw = (pathlib.Path(__file__).parent / "theme_inputs_raw.txt").read_text()
dec, i, docs = json.JSONDecoder(), 0, []
while i < len(raw):
    while i < len(raw) and raw[i].isspace(): i += 1
    if i >= len(raw): break
    obj, i = dec.raw_decode(raw, i); docs.append(obj)
docs += [[]] * (6 - len(docs))  # json_agg over zero rows prints nothing (no active dynamic ecosystems)
meta, themes, prior_rows, rs_rows, eco_rows, dyn_rows = docs
print("meta", meta)
print("rows: themes", len(themes), "prior", len(prior_rows), "rs", len(rs_rows), "eco", len(eco_rows), "dyn", len(dyn_rows))

from agents.market_intelligence import theme_ecosystems as te
from agents.market_intelligence.briefing import _compute_scored_themes
# dynamic taxonomy exactly as refresh_dynamic_taxonomy() would cache it
te._DYNAMIC_CACHE = [{"e_code": r["e_code"], "name": r.get("name") or r["e_code"], "description": r.get("description") or "",
                      "keyword_stems": list(r.get("keyword_stems") or []), "exemplars": list(r.get("exemplars") or []),
                      "dynamic": True} for r in dyn_rows]
theme_rs = {r["ticker"]: r for r in rs_rows}
prior = {r["name"]: r["rs_avg"] for r in prior_rows}
eco_map = {r["theme_name"]: r["e_code"] for r in eco_rows}
# handler-shape: get_today_themes returns all rows, ORDER BY score DESC
scored, fading = _compute_scored_themes(themes, theme_rs, prior)
by_stage = collections.Counter(t["stage"] for t in themes)
print("stages on theme_date:", dict(by_stage))
print("scored (non-Fading, incl any Retired):", len(scored), " fading:", len(fading))
print("Retired themes that reached scored_themes:", [(s["name"], s["stage"]) for s in scored if s["stage"] == "Retired"])
print("Retired rows tickers len:", [(t["name"], len(t["tickers"] or [])) for t in themes if t["stage"] == "Retired"])
print("scored dict keys:", sorted(scored[0].keys()))
print("has pct_above_20sma / days_active in scored dict:", "pct_above_20sma" in scored[0], "days_active" in scored[0])
print("\n== TOP 20 by /themes flat rank (comp desc) vs stored score ==")
stored = {t["name"]: t for t in themes}
sr = {n: i for i, n in enumerate(sorted(stored, key=lambda n: -(stored[n]["score"] or 0)), 1)}
print(f"{'rk':>3} {'comp':>6} {'stored':>6} {'stRk':>4} {'n_tk':>4} {'nSc':>3} {'brd':>5} stage / name")
for i, s in enumerate(scored[:20], 1):
    t = stored[s["name"]]
    print(f"{i:>3} {s['comp']:6.1f} {t['score']:6.1f} {sr[s['name']]:>4} {s['n_stocks']:>4} {s['n_scored']:>3} {str(t['pct_above_20sma']):>5} {s['stage'][:4]} / {s['name']}")
# rank agreement
comp_rank = {s["name"]: i for i, s in enumerate(scored, 1)}
common = [n for n in comp_rank if n in sr]
top15_comp = set(sorted(common, key=lambda n: comp_rank[n])[:15]); top15_st = set(sorted(common, key=lambda n: sr[n])[:15])
print("\ntop15 overlap comp-vs-stored:", len(top15_comp & top15_st), "/15")
exact = sum(1 for n in common if comp_rank[n] == sr[n]); print("themes with identical rank:", exact, "of", len(common))
print("\n== FULL RENDER (format_ecosystem_board), first 60 lines ==")
lines = te.format_ecosystem_board(scored, fading, theme_rs, eco_map)
for ln in lines[:60]: print(ln)
print("... total lines", len(lines))
print("\nAny per-theme line containing 'brd' or member-count token?", any("brd" in l for l in lines), any(" names" in l for l in lines if not l.startswith("\n") and "RS80+" not in l))
print("ecosystem header lines (with names count):")
for l in lines:
    if "RS80+" in l: print("  ", l.strip())
print("\n== delta-vs-self check (prior_date == themes_date?) ==", meta["prior_date"], meta["themes_date"])
same = [(s["name"], round(s["delta"],2)) for s in scored[:10] if s["delta"] is not None]
print("first 10 deltas:", same)
