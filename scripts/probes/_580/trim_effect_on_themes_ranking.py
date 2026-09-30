"""READ-ONLY, $0: how much does constants.trimmed_mean (one-sided: drops only LOWEST) move the /themes score
vs the plain mean and vs a two-sided trim, on the captured 2026-09-29 rows (79 scored themes)? Not a change proposal."""
import json, sys, pathlib, statistics as st, collections
ROOT = pathlib.Path(__file__).resolve().parents[3]; sys.path.insert(0, str(ROOT))
raw = (pathlib.Path(__file__).parent / "theme_inputs_raw.txt").read_text()
dec, i, docs = json.JSONDecoder(), 0, []
while i < len(raw):
    while i < len(raw) and raw[i].isspace(): i += 1
    if i >= len(raw): break
    o, i = dec.raw_decode(raw, i); docs.append(o)
docs += [[]] * (6 - len(docs)); meta, themes, *_r = docs; rs_rows = docs[3]
rs = {r["ticker"]: r["rs_composite"] for r in rs_rows if r["rs_composite"] is not None}
from agents.market_intelligence.constants import trimmed_mean
rows = []
for t in themes:
    if t["stage"] in ("Fading", "Retired") or not t["tickers"]: continue
    v = [rs[k] for k in t["tickers"] if k in rs]
    if not v: continue
    plain = sum(v) / len(v); trim = trimmed_mean(v)
    s = sorted(v); n = len(s)
    med = st.median(v)
    rows.append((t["name"], n, plain, trim, med))
print("themes:", len(rows))
b = collections.defaultdict(list)
for _, n, p, tr, m in rows: b["n=2" if n == 2 else "n=3-5" if n <= 5 else "n=6-10" if n <= 10 else "n=11+"].append(tr - p)
for k in ["n=2", "n=3-5", "n=6-10", "n=11+"]:
    if b[k]: print(f"  {k:7} count={len(b[k]):>2}  mean uplift trimmed-plain = {st.mean(b[k]):+.2f}  max {max(b[k]):+.2f}")
def top(idx, k=15): return [r[0] for r in sorted(rows, key=lambda r: -r[idx])[:k]]
for label, idx in (("plain mean", 2), ("median", 4)):
    a, c = set(top(3)), set(top(idx))
    print(f"top-15 overlap trimmed vs {label}: {len(a & c)}/15;  members of top-15 with n<=4 -> trimmed {sum(1 for r in rows if r[0] in a and r[1] <= 4)}, {label} {sum(1 for r in rows if r[0] in c and r[1] <= 4)}")
rk_t = {n: k for k, n in enumerate(top(3, 999), 1)}; rk_p = {n: k for k, n in enumerate(top(2, 999), 1)}
print("rank shift trimmed vs plain: median |shift| =", st.median(abs(rk_t[n] - rk_p[n]) for n in rk_t), " max =", max(abs(rk_t[n] - rk_p[n]) for n in rk_t))
print("top-20 by trimmed comp, size n<=4:", sum(1 for n in top(3, 20) if next(r for r in rows if r[0] == n)[1] <= 4), "of 20")
