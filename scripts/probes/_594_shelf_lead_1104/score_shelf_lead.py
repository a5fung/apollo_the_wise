"""PRE-REGISTRATION 3 of docs/analysis/ep_rank_v2_prereg_2026-11-03.md — the shelf-distance lead on sample 6's fresh labels."""
import importlib.util, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
f3 = _load("f3_def", REPO / "scripts/probes/_ep_rank_v2_1103/build_f3/f3_def.py")
nbis = _load("nbis", REPO / "scripts/probes/_533_nbis_structure_encoder.py")
from tests.fixtures.must_not_trade_charts import CHART_RULINGS, GOOD_CHART, OKISH_CHART, BAD_CHART

bars, cur = {}, None
for line in open(REPO / "scripts/probes/_594_sample6_1104/q2_bars.out"):
    line = line.rstrip("\n")
    if line.startswith("== "):
        t, d = line[3:].split(); cur = (t, d); bars[cur] = []
    elif cur and line and line[0].isdigit() and "|" in line:
        td, o, h, l, c, v = line.split("|")
        bars[cur].append((td, float(o), float(h), float(l), float(c), float(v)))

rows = [r for r in CHART_RULINGS if r.ruling_date == "2026-11-04"]
assert len(rows) == 12, len(rows)
out = []
for r in rows:
    days = bars[(r.ticker, r.alert_date)]
    ia = len(days) - 1
    assert days[ia][0] == r.alert_date, (r.ticker, days[ia][0])
    adr = nbis.adr20_pct(days, ia)
    res = f3.f3_new(days, ia, adr)
    yes = r.verdict in (GOOD_CHART, OKISH_CHART)
    out.append((r.ticker, r.alert_date, r.verdict, yes, res["dmin"], res["held"], res["into"], res["structure"], res["null"], res["shelf_date"], res["shelf"], adr))
print("ticker|date|verdict|yes|dmin_adr|held|into|structure|null|shelf_date|shelf|adr20_pct")
for o in out:
    print("|".join("" if x is None else (f"{x:.3f}" if isinstance(x, float) else str(x)) for x in o))
Y = [o[4] for o in out if o[3] and o[4] is not None]
N = [o[4] for o in out if not o[3] and o[4] is not None]
dropped = [o[0] for o in out if o[4] is None]
pairs = [(y, n) for y in Y for n in N]
p = sum(1.0 if y > n else 0.5 if y == n else 0.0 for y, n in pairs) / len(pairs) if pairs else None
print(f"\nyes n={len(Y)} no n={len(N)} pairs={len(pairs)} dropped(NULL)={dropped}")
print(f"P(yes dmin > no dmin) = {p:.3f}  (bar >= 0.65; directional only)")
print("VERDICT:", "HOLDS on fresh labels (directional)" if p is not None and p >= 0.65 else "DOES NOT REPLICATE")
import statistics as st
if Y and N: print(f"median dmin: yes {st.median(Y):.2f} ADR, no {st.median(N):.2f} ADR")
