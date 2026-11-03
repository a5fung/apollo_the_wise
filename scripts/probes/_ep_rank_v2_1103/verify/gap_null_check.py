"""Discrimination check: does raw gap % (open / prior close) reproduce bar (ii) and the A read?
Output: gap_null_check.txt. Reuses verify_v2.py's loaders/features (imported, stdout muted)."""
import contextlib, importlib.util, io, os, statistics as st
os.chdir(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("v", "verify_v2.py")
v = importlib.util.module_from_spec(spec)
with contextlib.redirect_stdout(io.StringIO()):
    spec.loader.exec_module(v)
def gap(t, d):
    days = v.window(t, d)
    if days is None: return None
    i = {r[0]: k for k, r in enumerate(days)}.get(d)
    return None if i is None else days[i][1] / days[i - 1][4] - 1
ks = sorted(v.yesA | v.noA)
ys = [gap(*k) for k in sorted(v.yesA)]; ns = [gap(*k) for k in sorted(v.noA)]
a = sum((x > y) + 0.5 * (x == y) for x in ys for y in ns) / (len(ys) * len(ns))
out = [f"gap% (bigger) on A: P(yes > no) = {a:.3f} (n {len(ys)}/{len(ns)})"]
zs = [v.features(*k)['zones_cleared'] for k in ks]; gs = [gap(*k) for k in ks]
rk = lambda x: [v.pct_rank(sorted(x), e) for e in x]
rz, rg = rk(zs), rk(gs); mz, mg = st.fmean(rz), st.fmean(rg)
sp = sum((p-mz)*(q-mg) for p, q in zip(rz, rg)) / (sum((p-mz)**2 for p in rz) * sum((q-mg)**2 for q in rg))**0.5
out.append(f"Spearman(zones_cleared, gap%) on the 54 A pairs = {sp:.2f}")
def day_rank(t, d):
    pool = sorted(set(x for x in v.alerts_by_day.get(d, ()) if x in v.daily_full) | {t})
    vals = {x: g for x in pool if (g := gap(x, d)) is not None}
    return (None, len(vals)) if len(vals) < 2 else (1 - v.pct_rank(sorted(vals.values()), vals[t]), len(vals))
rb = [(t, d, *day_rank(t, d)) for t, d in v.B_op]; rb = [r for r in rb if r[2] is not None]
out.append(f"bar (ii) ranked by raw gap% alone: {sum(1 for r in rb if r[2] < 0.5)}/{len(rb)} strictly in the top half: "
           + ", ".join(f"{t} {r:.3f}(pool {n})" for t, d, r, n in rb))
ya = [day_rank(*k)[0] for k in sorted(v.yesA) if day_rank(*k)[0] is not None]
na = [day_rank(*k)[0] for k in sorted(v.noA) if day_rank(*k)[0] is not None]
ai = sum((x < y) + 0.5 * (x == y) for x in ya for y in na) / (len(ya) * len(na))
out.append(f"bar (i) analogue, gap% ranked within day on rankable A: {ai:.3f} (n {len(ya)}/{len(na)})")
open('gap_null_check.txt', 'w').write("\n".join(out) + "\n"); print("\n".join(out))
