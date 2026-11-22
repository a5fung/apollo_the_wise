"""The shelf-distance lead (ep_rank_v2_prereg_2026-11-03.md PRE-REG 5, same rule and bar as RESULT 6) re-tested on sample 10's fresh labels (ruled 2026-11-21)."""
import importlib.util, statistics as st, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
f3 = _load("f3_def", REPO / "scripts/probes/_ep_rank_v2_1103/build_f3/f3_def.py")
nbis = _load("nbis", REPO / "scripts/probes/_533_nbis_structure_encoder.py")
from tests.fixtures.must_not_trade_charts import CHART_RULINGS, GOOD_CHART, OKISH_CHART

def read_bars(path, into):
    cur = None
    for line in open(path):
        line = line.rstrip("\n")
        if line.startswith("== "):
            t, d = line[3:].split(); cur = (t, d); into[cur] = []
        elif cur and line and line[0].isdigit() and "|" in line:
            td, o, h, l, c, v = line.split("|"); into[cur].append((td, float(o), float(h), float(l), float(c), float(v)))
    return into

def score(rows, bars):
    out = []
    for r in rows:
        days = bars[(r.ticker, r.alert_date)]; ia = len(days) - 1
        assert days[ia][0] == r.alert_date, (r.ticker, days[ia][0])
        adr = nbis.adr20_pct(days, ia); res = f3.f3_new(days, ia, adr)
        out.append((r.ticker, r.alert_date, r.verdict, r.verdict in (GOOD_CHART, OKISH_CHART), res["dmin"], res["held"], res["into"], res["structure"], res["null"], res["shelf_date"], res["shelf"], adr))
    return out

def p_of(out):
    Y = [o[4] for o in out if o[3] and o[4] is not None]; N = [o[4] for o in out if not o[3] and o[4] is not None]
    pairs = [(y, n) for y in Y for n in N]
    return Y, N, pairs, (sum(1.0 if y > n else 0.5 if y == n else 0.0 for y, n in pairs) / len(pairs) if pairs else None)

bars = read_bars(REPO / "scripts/probes/_594_sample10_1121/q2_bars.out", {})
rows = [r for r in CHART_RULINGS if r.ruling_date == "2026-11-21"]
assert len(rows) == 11, len(rows)  # sample 10: 12 drawn, 1 he left undecided (C INSM "maybe")
out = score(rows, bars)
print("ticker|date|verdict|yes|dmin_adr|held|into|structure|null|shelf_date|shelf|adr20_pct")
for o in out: print("|".join("" if x is None else (f"{x:.3f}" if isinstance(x, float) else str(x)) for x in o))
Y, N, pairs, p = p_of(out)
print(f"\nyes n={len(Y)} no n={len(N)} pairs={len(pairs)} dropped(NULL)={[o[0] for o in out if o[4] is None]}")
print(f"P(yes dmin > no dmin) = {p:.3f}  (bar >= 0.65; directional only)")
print("VERDICT:", "HOLDS on fresh labels (directional)" if p is not None and p >= 0.65 else "DOES NOT REPLICATE")
if Y and N: print(f"median dmin: yes {st.median(Y):.2f} ADR, no {st.median(N):.2f} ADR")

allbars = {}
for s in ("_594_sample6_1104", "_594_sample7_1107", "_594_sample8_1109", "_594_sample9_1115", "_594_sample10_1121"):
    read_bars(REPO / f"scripts/probes/{s}/q2_bars.out", allbars)
pool = score([r for r in CHART_RULINGS if r.ruling_date in ("2026-11-04", "2026-11-07", "2026-11-09", "2026-11-15", "2026-11-21")], allbars)
PY, PN, pp, P = p_of(pool)
print(f"\nPOOLED samples 6-10 (description only): yes n={len(PY)} no n={len(PN)} pairs={len(pp)} P = {P:.3f}")
