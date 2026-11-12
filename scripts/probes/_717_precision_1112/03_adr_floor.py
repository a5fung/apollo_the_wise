#!/usr/bin/env python3
"""#717 THE DAILY-RANGE FLOOR — what the list, the fires and the picks look like at ADR20 floors 2.1% (live), 3%, 4%,
4.26% (the floor before 2026-11-02), 5% (2026-11-12; offline, $0, read-only, ERA A ONLY; measures, changes no rule).

Reads ONLY the 02 capture (`list_eraA.parquet`, the 11-11 list rows with the live gate's own ADR20 =
mean((high - low) / close) of the 20 sessions to D — `breakout_v1.adr20_at`) and the Qullamaggie scorecard fixture.
A floor is applied to the LIST (a name under it is off the list); the order score is then re-ranked inside the night's
remaining list, as `rank_rows` would. Picks: model A (as wired: the top of the list rests, all 5 slots free each
morning — the upper bound) and model B (the day's top 5 fires by order score), both from 02_picks.py.

Part 3 reads the scorecard's own bars (tests/fixtures/qm_breakout_scorecard, all 757 buys, listed or not): ADR20 at the
night before the buy (dated: E - 1; widened: the night before the window's first session), and what the low-ADR buys are
— 20-day median dollar volume, the gap on the buy day, a fund, the setup tag of Qullamaggie's positions panel.

    python3 scripts/probes/_717_precision_1112/03_adr_floor.py > scripts/probes/_717_precision_1112/03_adr_floor.out
"""
import contextlib, importlib.util, io, os, sys
from datetime import date

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("p02", os.path.join(HERE, "02_picks.py"))
P2 = importlib.util.module_from_spec(spec); spec.loader.exec_module(P2)
P, bv = P2.P, P2.bv
os.chdir(P.REPO)
sys.path.insert(0, os.path.join(P.REPO, "scripts/probes/_717_qm_confidence_1111"))
import rating as RT  # noqa: E402
FLOORS = (0.021, 0.03, 0.04, 0.0426, 0.05)
WIN = P.WIN

df = pd.read_parquet(P2.CAPTURE)
cal = [date.fromisoformat(s) for s in open(P2.CAL).read().split()]
nights = sorted(df.ci.unique()); nN = len(nights)
df["E"] = [cal[c + 1].isoformat() for c in df.ci]

# Qullamaggie: bought within +-5 (the panel) and the scorecard buys — the same code path as 02 (kept identical)
e = pd.read_csv(f"{P.HOLD}/entries.tsv", sep="\t", dtype=str, keep_default_na=False)
snaps = pd.read_csv(f"{P.HOLD}/snapshots.tsv", sep="\t", dtype=str, keep_default_na=False)
snap_ci = np.array(sorted({np.searchsorted(cal, date.fromisoformat(x)) for x in snaps.date if x and date.fromisoformat(x) <= cal[-1]}))
def ci_at(s, side):
    d = date.fromisoformat(s); i = int(np.searchsorted(cal, d, "left"))
    return i if (i < len(cal) and cal[i] == d) or side == "lo" else i - 1
bought = {}
for r in e.itertuples():
    if r.initial == "True":
        continue
    if r.E:
        if date.fromisoformat(r.E) > cal[-1]:
            continue
        b0 = b1 = ci_at(r.E, "lo")
    elif r.lo and r.hi and int(r.window_len or 99) <= 10 and date.fromisoformat(r.lo) <= cal[-1]:
        b0, b1 = ci_at(r.lo, "lo"), ci_at(r.hi, "hi")
    else:
        continue
    bought.setdefault(r.sym_a or r.sym, []).append((b0 - WIN, b1 + WIN))
eci = df.ci.to_numpy() + 1
df["bought"] = [any(a <= c <= b for a, b in bought.get(t, ())) for t, c in zip(df.ticker, eci)]
pos = np.searchsorted(snap_ci, eci)
df["covered"] = np.minimum(np.abs(snap_ci[np.clip(pos, 0, len(snap_ci) - 1)] - eci), np.abs(snap_ci[np.clip(pos - 1, 0, len(snap_ci) - 1)] - eci)) <= WIN
last_e = cal[nights[-1] + 1].isoformat()
by_t, big_ids, n_buys = {}, set(), 0
b = pd.read_csv(f"{P2.FX}/buys.tsv", sep="\t", dtype=str, keep_default_na=False)
w = pd.read_csv(f"{P2.FX}/buys_undated_widened.tsv", sep="\t", dtype=str, keep_default_na=False)
for bid, t, lo, hi, big in [("d" + r.eid, r.ticker, r.E, r.E, r.big_winner == "1") for r in b.itertuples()] + [("w" + r.eid, r.ticker, r.lo, r.hi, False) for r in w.itertuples()]:
    if hi <= last_e:
        by_t.setdefault(t, []).append((bid, lo, hi)); n_buys += 1
        if big:
            big_ids.add(bid)
df["qm"] = [[bid for bid, lo, hi in by_t.get(t, ()) if lo <= E <= hi] for t, E in zip(df.ticker, df.E)]
def taken(x):
    s = {i for l in x.qm for i in l}
    return len(s), len(s & big_ids)

print(f"#717 the daily-range floor — ERA A ONLY, {nN} nights {cal[nights[0]]} .. {cal[nights[-1]]}; live ADR_MIN = {bv.ADR_MIN}; "
      f"Qullamaggie scorecard buys in era A {n_buys} ({len(big_ids)} big winners)")
print("NOT MEASURED: 2022-04 .. 2024. Daily-bar proxy; picks as in 02_picks.py (A = as wired, all 5 slots free each morning = upper bound; B = the day's top 5 fires).")
print("\n== 1+2. BY FLOOR (11-11 rules otherwise unchanged) ==")
print(f"{'floor':>6s} | {'listed':>7s} {'fires':>6s} {'bought':>7s} {'QM buys':>8s} {'big':>4s} | {'A: buys/day':>11s} {'bought':>7s} {'(n)':>6s} {'taken':>6s} {'big':>4s} | {'B: bought':>9s} {'(n)':>6s} {'taken':>6s} {'big':>4s}")
print(f"{'':>6s} | {'median':>7s} {'median':>6s} {'+-5':>7s} {'fired':>8s} {'':>4s} | {'':>11s} {'+-5':>7s} {'':>6s} {'':>6s} {'':>4s} | {'+-5':>9s}")
for fl in FLOORS:
    d = df[df.adr20 >= fl].copy()
    d["s"] = P2.order_score(d)
    per = d.groupby("ci").agg(l=("ticker", "size"), f=("new_fire", "sum")).reindex(nights).fillna(0)
    f = d[d.new_fire]; fc = f[f.covered]; nf, bf = taken(f)
    xa, _ = P2.live_like(d, d.s, "new_fire", 0); ac = xa[xa.covered]; na, ba = taken(xa)
    xb = P2.top_k(f, f.s); bc = xb[xb.covered]; nb, bb = taken(xb)
    print(f"{fl:6.2%} | {per.l.median():7.0f} {per.f.median():6.0f} {fc.bought.mean():7.2%} {nf:8d} {bf:4d} | {len(xa) / nN:11.2f} {ac.bought.mean():7.2%} {len(ac):6d} {na:6d} {ba:4d} | "
          f"{bc.bought.mean():9.2%} {len(bc):6d} {nb:6d} {bb:4d}")
print("(QM buys fired = distinct scorecard buys that are on the list at that floor and fire; 'taken' = of those, the ones a pick lands on.)")

# ── part 3: Qullamaggie's low-ADR buys, from the scorecard's own bars (all 757)
setup = {r.eid: r.setup for r in e.itertuples()}
with contextlib.redirect_stdout(io.StringIO()):
    buys = RT.load()
rows = []
for x in buys:
    t0 = x["win"][0]; D = t0 - 1
    h, l, c, v, o = x["h"], x["l"], x["c"], x["v"], x["o"]
    if D < 20:
        continue
    with np.errstate(invalid="ignore", divide="ignore"):
        adr = bv.adr20_at((h - l) / c, D)
    if adr is None:
        continue
    gaps = [o[t] / c[t - 1] - 1 for t in x["win"]]
    rows.append(dict(set=x["set"], eid=x["eid"], ticker=x["ticker"], day=x["lo"] if x["set"] == "dated" else f"{x['lo']}..{x['hi']}",
                     adr=float(adr), dv=float(np.median((c * v)[D - 19:D + 1])), gap=float(max(gaps)), close=float(c[D]),
                     fund=x["ticker"] in RT.FUNDS, panel=setup.get(x["eid"], ""), big=x["row"].get("big_winner") == "1"))
q = pd.DataFrame(rows)
print(f"\n== 3. QULLAMAGGIE'S BUYS BY DAILY RANGE (scorecard bars, {len(q)} of 757 with 20 sessions before the buy; ADR20 = the gate's own) ==")
print(f"median ADR20 {q.adr.median():.2%}; under 2.1%: {np.mean(q.adr < .021):.1%}; under 3%: {np.mean(q.adr < .03):.1%}; under 4%: {np.mean(q.adr < .04):.1%}; "
      f"under 4.26%: {np.mean(q.adr < .0426):.1%}; under 5%: {np.mean(q.adr < .05):.1%}; big winners under 4%: {int((q.big & (q.adr < .04)).sum())}, under 5%: {int((q.big & (q.adr < .05)).sum())} of {int(q.big.sum())}")
def band(name, x, rest):
    print(f"\n{name}: {len(x)} buys — funds {x.fund.mean():.0%}; gap up >= 9% on the buy day {np.mean(x.gap >= RT.EP_GAP):.0%} (the rest of the buys: {np.mean(rest.gap >= RT.EP_GAP):.0%}); "
          f"median dollar volume ${x.dv.median() / 1e6:,.0f}M (rest ${rest.dv.median() / 1e6:,.0f}M); over $500M a day {np.mean(x.dv >= 5e8):.0%} (rest {np.mean(rest.dv >= 5e8):.0%}); "
          f"median close ${x.close.median():.0f} (rest ${rest.close.median():.0f}); dated {np.mean(x.set == 'dated'):.0%}; panel tag {x.panel.value_counts().to_dict()}; big winners {int(x.big.sum())}")
    for r in x.sort_values("adr").head(18).itertuples():
        print(f"    {r.ticker:6s} {r.day:24s} ADR {r.adr:5.2%}  ${r.dv / 1e6:7,.0f}M/day  gap {r.gap:+6.1%}  {'FUND ' if r.fund else ''}{'BIG ' if r.big else ''}{r.panel}")
band("UNDER 4%", q[q.adr < .04], q[q.adr >= .04])
band("4% to 5%", q[(q.adr >= .04) & (q.adr < .05)], q[q.adr >= .05])
print("\n(18 lowest of each band shown. Dollar volume is on split-adjusted bars; the gap is the largest open-vs-prior-close of the buy window.)")
