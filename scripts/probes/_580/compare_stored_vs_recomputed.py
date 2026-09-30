"""READ-ONLY: compare stored mi_themes.rs_avg / score with the /themes recomputed comp, on the captured 2026-09-29 rows."""
import json, sys, pathlib, statistics as st
ROOT = pathlib.Path(__file__).resolve().parents[3]; sys.path.insert(0, str(ROOT))
raw = (pathlib.Path(__file__).parent / "theme_inputs_raw.txt").read_text()
dec, i, docs = json.JSONDecoder(), 0, []
while i < len(raw):
    while i < len(raw) and raw[i].isspace(): i += 1
    if i >= len(raw): break
    o, i = dec.raw_decode(raw, i); docs.append(o)
docs += [[]] * (6 - len(docs)); meta, themes, prior_rows, rs_rows, eco_rows, dyn = docs
from agents.market_intelligence.briefing import _compute_scored_themes
scored, fading = _compute_scored_themes(themes, {r["ticker"]: r for r in rs_rows}, {})
by = {t["name"]: t for t in themes}
d_rsavg = [(abs(s["comp"] - by[s["name"]]["rs_avg"]), s["name"]) for s in scored if by[s["name"]]["rs_avg"] is not None]
print("scored themes:", len(scored), " with stored rs_avg:", len(d_rsavg), " without (NULL rs_avg):", len(scored) - len(d_rsavg))
print("|comp - rs_avg|: max %.2f  median %.3f  >1.0: %d  >0.5: %d" % (max(d)[0] if (d:=d_rsavg) else 0, st.median(x for x, _ in d_rsavg), sum(x > 1 for x,_ in d_rsavg), sum(x > .5 for x,_ in d_rsavg)))
print("worst 5:", [(round(x,2), n[:40]) for x, n in sorted(d_rsavg, reverse=True)[:5]])
# rank agreement comp vs rs_avg
rk_c = {s["name"]: k for k, s in enumerate(scored, 1)}
ra = sorted([n for _, n in d_rsavg], key=lambda n: -by[n]["rs_avg"]); rk_r = {n: k for k, n in enumerate(ra, 1)}
print("rank(comp) vs rank(rs_avg) exact-equal:", sum(rk_c[n] == rk_r[n] for n in ra), "of", len(ra), " max |rank diff|:", max(abs(rk_c[n]-rk_r[n]) for n in ra))
sc = sorted([n for _, n in d_rsavg], key=lambda n: -by[n]["score"]); rk_s = {n: k for k, n in enumerate(sc, 1)}
print("rank(comp) vs rank(stored score) exact-equal:", sum(rk_c[n] == rk_s[n] for n in ra), " max |rank diff|:", max(abs(rk_c[n]-rk_s[n]) for n in ra))
# member-count semantics
diff = [(s["name"], s["n_stocks"], s["n_scored"]) for s in scored if s["n_stocks"] != s["n_scored"]]
print("themes where len(tickers) != n_scored (member lacks RS row):", len(diff), diff[:6])
print("non-Retired non-Fading rows with NULL pct_above_20sma:", sum(1 for s in scored if by[s['name']]['pct_above_20sma'] is None), "of", len(scored))
print("Fading rows: rs_avg NULL count:", sum(1 for f in fading if f["rs_avg"] is None), "of", len(fading), "; breadth NULL:", sum(1 for f in fading if f["pct_above_20sma"] is None))
