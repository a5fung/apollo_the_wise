#!/usr/bin/env python3
"""#-- STRUCTURE-AXIS REPLAY HARNESS (READ-ONLY, $0, MEASUREMENT ONLY, 2026-08-25).

Runs the LIVE structure axis (`agents.market_intelligence.structure_axis_shadow`) over two
populations it has never scored, to answer: does it separate operator/evidence-labelled real
EPs from the names our gates rejected on the two silent days?

REUSE, NOT RE-IMPLEMENTATION: `compute_structure_features` and `structure_axis_credit` are
IMPORTED from the live module. The only thing reproduced here is the bar ACCESSOR
(`db.get_daily_bars_asof`), because it needs a live asyncpg conn — its SQL predicate
(trade_date < alert_date, >= alert_date - 380 days, high/low NOT NULL, ASC) is mirrored
exactly against a one-shot capture, and STEP 0 below VERIFIES the mirror by reproducing all
116 rows the live path already wrote to `mi_structure_axis_shadow`.

Inputs (captured ONCE from prod, read-only, per the COST EFFICIENCY rule):
  _structax_bars.psv        mi_daily_closes full retention for all 156 tickers
  _structax_scanlog.psv     mi_ep_scan_log rows for 2026-08-24 / 2026-08-25
  _structax_shadow_rows.psv the 116 live-written mi_structure_axis_shadow rows

THE LINE: proposes no threshold, changes no rule, writes nothing to prod.
"""
from __future__ import annotations

import math
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agents.market_intelligence.structure_axis_shadow import (  # noqa: E402
    compute_structure_features, structure_axis_credit, _TIGHT_RMV_MAX,
)
from tests.fixtures.must_not_miss_eps import MUST_NOT_MISS  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT = []


def emit(s=""):
    print(s)
    OUT.append(s)


def _d(s):
    y, m, dd = s.split("-")
    return date(int(y), int(m), int(dd))


def f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


# ── load bars ────────────────────────────────────────────────────────────────────────────
BARS: dict[str, list[dict]] = defaultdict(list)
for ln in (HERE / "_structax_bars.psv").read_text().splitlines():
    p = ln.split("|")
    if len(p) < 7:
        continue
    if p[3] == "" or p[4] == "":     # mirrors the accessor's high/low NOT NULL filter
        continue
    BARS[p[0]].append({
        "trade_date": _d(p[1]), "open_price": f(p[2]), "high_price": f(p[3]),
        "low_price": f(p[4]), "close": f(p[5]), "volume": f(p[6]),
    })
for t in BARS:
    BARS[t].sort(key=lambda r: r["trade_date"])


def bars_asof(ticker: str, alert_date: date, days: int = 380) -> list[dict]:
    """Mirror of db.get_daily_bars_asof (same predicate, same ordering, same default)."""
    lo = alert_date - timedelta(days=days)
    return [b for b in BARS.get(ticker, []) if lo <= b["trade_date"] < alert_date]


def axis(ticker: str, alert_date: date) -> dict:
    bars = bars_asof(ticker, alert_date)
    feats = compute_structure_features(bars, alert_date)
    credit = structure_axis_credit(feats)
    return {"ticker": ticker, "alert_date": alert_date, "n_bars": len(bars), **feats, **credit}


# ── STEP 0 — FIDELITY: reproduce the 116 rows the LIVE path wrote ────────────────────────
def _close(a, b, tol=1e-6):
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b))


emit("=" * 96)
emit("STEP 0 — FIDELITY CHECK: does this harness reproduce the LIVE mi_structure_axis_shadow rows?")
emit("=" * 96)
shadow = []
for ln in (HERE / "_structax_shadow_rows.psv").read_text().splitlines():
    p = ln.split("|")
    if len(p) < 14:
        continue
    shadow.append({
        "ticker": p[0], "alert_date": _d(p[1]), "grade": p[2], "prior_close": f(p[3]),
        "stage2": {"t": True, "f": False, "": None}.get(p[4]),
        "sma_200": f(p[5]), "trailing_high": f(p[6]), "rmv_15": f(p[7]),
        "rmv_tight": {"t": True, "f": False, "": None}.get(p[8]),
        "extension_ratio": f(p[9]), "sma_10": f(p[10]),
        "credit_steps": int(p[11]) if p[11] else None, "marker": p[12],
    })
FIELDS = ["prior_close", "stage2", "sma_200", "trailing_high", "rmv_15", "rmv_tight",
          "extension_ratio", "sma_10", "credit_steps", "marker"]
mismatch = defaultdict(list)
for row in shadow:
    got = axis(row["ticker"], row["alert_date"])
    for k in FIELDS:
        a, b = got.get(k), row[k]
        ok = _close(a, b) if isinstance(b, float) or isinstance(a, float) else a == b
        if not ok:
            mismatch[k].append((row["ticker"], row["alert_date"], b, a))
emit(f"rows replayed: {len(shadow)}")
for k in FIELDS:
    m = mismatch.get(k, [])
    emit(f"  {k:<16} exact matches {len(shadow)-len(m):>3}/{len(shadow)}"
         + ("" if not m else f"   MISMATCHES: {m[:6]}"))
emit()

# ── populations ──────────────────────────────────────────────────────────────────────────
rej_days: list[tuple[str, date]] = []
seen = set()
for ln in (HERE / "_structax_scanlog.psv").read_text().splitlines():
    p = ln.split("|")
    if len(p) < 7:
        continue
    d, t, reason = p[0], p[1], p[6]
    if reason.startswith("filter:universe_"):
        continue
    if (t, d) in seen:
        continue
    seen.add((t, d))
    rej_days.append((t, _d(d)))
rej_days.sort(key=lambda x: (x[1], x[0]))

fix_days = [(m.ticker, _d(m.alert_date)) for m in MUST_NOT_MISS if not m.excluded]

REJ = [axis(t, d) for t, d in rej_days]
FIX = [axis(t, d) for t, d in fix_days]

emit("=" * 96)
emit("STEP 1 — POPULATIONS")
emit("=" * 96)
emit(f"real EPs (tests/fixtures/must_not_miss_eps.py, excluded members dropped): {len(FIX)} name-days")
emit(f"rejects that cleared the $5 / 50k universe floors on 08-24 + 08-25:      {len(REJ)} name-days")
emit()

# ── STEP 2 — coverage: can the axis even compute its own components? ─────────────────────
emit("=" * 96)
emit("STEP 2 — COVERAGE (a None is the axis saying 'I cannot compute this')")
emit("=" * 96)
emit(f"{'field':<18}{'real EPs computable':>22}{'rejects computable':>22}")
for k in ["sma_200", "stage2", "rmv_15", "rmv_tight", "extension_ratio", "trailing_high"]:
    a = sum(1 for r in FIX if r[k] is not None)
    b = sum(1 for r in REJ if r[k] is not None)
    emit(f"{k:<18}{a:>13}/{len(FIX):<8}{b:>13}/{len(REJ):<8}")
emit()
emit("bar counts inside the 380-day accessor window (200 needed for the 200-day SMA):")
for nm, pop in (("real EPs", FIX), ("rejects", REJ)):
    ns = sorted(r["n_bars"] for r in pop)
    emit(f"  {nm:<10} min {ns[0]:>4}  median {ns[len(ns)//2]:>4}  max {ns[-1]:>4}   "
         f"under 200 bars: {sum(1 for n in ns if n < 200)}/{len(ns)}")
emit()

# ── STEP 3 — the credit decision, as it would have fired ─────────────────────────────────
emit("=" * 96)
emit("STEP 3 — WHAT THE AXIS ACTUALLY SAYS (marker + credit_steps)")
emit("=" * 96)
for nm, pop in (("real EPs", FIX), ("rejects", REJ)):
    c = defaultdict(int)
    for r in pop:
        c[r["marker"]] += 1
    emit(f"  {nm:<10} " + "  ".join(f"{k}={v}" for k, v in sorted(c.items()))
         + f"   |  credited (+1): {sum(1 for r in pop if r['credit_steps'] == 1)}/{len(pop)}")
emit()
emit("  same tally restricted to name-days where stage2 was COMPUTABLE (>=200 bars):")
for nm, pop in (("real EPs", FIX), ("rejects", REJ)):
    sub = [r for r in pop if r["stage2"] is not None]
    c = defaultdict(int)
    for r in sub:
        c[r["marker"]] += 1
    emit(f"  {nm:<10} n={len(sub):<3} " + "  ".join(f"{k}={v}" for k, v in sorted(c.items()))
         + f"   |  credited (+1): {sum(1 for r in sub if r['credit_steps'] == 1)}")
emit()


# ── STEP 4 — separation, pre-registered directions ───────────────────────────────────────
def auc(pos: list[float], neg: list[float]) -> tuple[float, float, int, int]:
    """P(a random positive scores above a random negative), ties = 0.5.
    SE by Hanley-McNeil. `pos` = real EPs, `neg` = rejects, both already sign-oriented so
    that HIGHER = 'more like a real EP' under the PRE-REGISTERED direction."""
    n1, n2 = len(pos), len(neg)
    if n1 == 0 or n2 == 0:
        return float("nan"), float("nan"), n1, n2
    s = sum(1.0 if a > b else 0.5 if a == b else 0.0 for a in pos for b in neg)
    a = s / (n1 * n2)
    q1 = a / (2 - a)
    q2 = 2 * a * a / (1 + a)
    se = math.sqrt(max(0.0, (a * (1 - a) + (n1 - 1) * (q1 - a * a) + (n2 - 1) * (q2 - a * a)) / (n1 * n2)))
    return a, se, n1, n2


def med(v):
    v = sorted(v)
    return None if not v else (v[len(v) // 2] if len(v) % 2 else (v[len(v) // 2 - 1] + v[len(v) // 2]) / 2)


# direction pre-registered BEFORE computing, from structure_model.md §4c + the axis's own semantics
PREREG = [
    ("extension_ratio", -1, "less extended above the 10-day = more like a real EP (structure_model §4c)"),
    ("rmv_15",          -1, "tighter base (lower RMV-15) = more like a real EP (axis component b)"),
    ("near_high_frac",  +1, "closer to the trailing high = more like a real EP (axis component a's own term)"),
    ("stage2_num",      +1, "Stage-2 present = more like a real EP (axis component a)"),
    ("credit_steps",    +1, "the axis's own boost = more like a real EP (the whole point)"),
]
for r in REJ + FIX:
    r["near_high_frac"] = (r["prior_close"] / r["trailing_high"]
                           if r["prior_close"] and r["trailing_high"] else None)
    r["stage2_num"] = None if r["stage2"] is None else (1.0 if r["stage2"] else 0.0)
    r["credit_steps"] = float(r["credit_steps"])

emit("=" * 96)
emit("STEP 4 — SEPARATION (AUC, direction PRE-REGISTERED, ties credited 0.5)")
emit("=" * 96)
emit(f"{'field':<18}{'AUC':>7}{'95% CI':>18}{'nEP':>6}{'nRej':>6}  {'medEP':>10}{'medRej':>10}")
results = {}
for k, sign, why in PREREG:
    pos = [sign * r[k] for r in FIX if r.get(k) is not None]
    neg = [sign * r[k] for r in REJ if r.get(k) is not None]
    a, se, n1, n2 = auc(pos, neg)
    lo, hi = a - 1.96 * se, a + 1.96 * se
    rp, rn = [r[k] for r in FIX if r.get(k) is not None], [r[k] for r in REJ if r.get(k) is not None]
    results[k] = (a, se, n1, n2)
    emit(f"{k:<18}{a:>7.3f}  [{max(0,lo):>5.3f}, {min(1,hi):>5.3f}]{n1:>6}{n2:>6}  "
         f"{(med(rp) or 0):>10.3f}{(med(rn) or 0):>10.3f}")
emit()
for k, sign, why in PREREG:
    emit(f"  direction for {k}: {why}")
emit()

# 2x2 for the binaries — an AUC on a 0/1 predictor is a contingency table wearing a curve
emit("2x2 contingency for the binary fields (the honest form for a 0/1 predictor):")
for k in ["stage2", "rmv_tight"]:
    emit(f"  {k}:")
    for nm, pop in (("real EPs", FIX), ("rejects", REJ)):
        t = sum(1 for r in pop if r[k] is True)
        fa = sum(1 for r in pop if r[k] is False)
        u = sum(1 for r in pop if r[k] is None)
        emit(f"    {nm:<10} True={t:<4} False={fa:<4} not-computable={u}")
emit()

# ── STEP 5 — CAPR, the worked example ────────────────────────────────────────────────────
emit("=" * 96)
emit("STEP 5 — CAPR, THE WORKED EXAMPLE")
emit("=" * 96)
for d in ("2026-08-24", "2026-08-25"):
    r = axis("CAPR", _d(d))
    emit(f"  CAPR {d}: bars={r['n_bars']}  prior_close={r['prior_close']}  "
         f"sma_200={r['sma_200'] and round(r['sma_200'],2)}  trailing_high={r['trailing_high']}")
    emit(f"    stage2={r['stage2']}  rmv_15={r['rmv_15'] and round(r['rmv_15'],1)} "
         f"(tight<= {_TIGHT_RMV_MAX:.0f} -> {r['rmv_tight']})  "
         f"extension_ratio={r['extension_ratio'] and round(r['extension_ratio'],3)}  "
         f"sma_10={r['sma_10'] and round(r['sma_10'],2)}")
    emit(f"    marker={r['marker']}  credit_steps={int(r['credit_steps'])}")
emit()
emit("  CAPR daily bars around the operator's July 27 reference (the supply he is pointing at):")
for b in BARS.get("CAPR", []):
    if date(2026, 7, 22) <= b["trade_date"] <= date(2026, 8, 24):
        emit(f"    {b['trade_date']}  O {b['open_price']:>7.2f}  H {b['high_price']:>7.2f}  "
             f"L {b['low_price']:>7.2f}  C {b['close']:>7.2f}  V {b['volume']:>12,.0f}")
emit()

# ── STEP 6 — per-name dumps ──────────────────────────────────────────────────────────────
emit("=" * 96)
emit("STEP 6 — EVERY NAME, EVERY AXIS OUTPUT")
emit("=" * 96)
for nm, pop in (("REAL EPs (labelled)", FIX), ("REJECTS (08-24 / 08-25)", REJ)):
    emit(f"-- {nm} " + "-" * (92 - len(nm)))
    emit(f"{'ticker':<8}{'date':<12}{'bars':>5}{'stage2':>8}{'rmv15':>8}{'tight':>7}"
         f"{'ext':>8}{'p/high':>8}  marker")
    for r in sorted(pop, key=lambda r: (r["alert_date"], r["ticker"])):
        emit(f"{r['ticker']:<8}{str(r['alert_date']):<12}{r['n_bars']:>5}"
             f"{str(r['stage2']):>8}"
             f"{('%.1f' % r['rmv_15']) if r['rmv_15'] is not None else '-':>8}"
             f"{str(r['rmv_tight']):>7}"
             f"{('%.3f' % r['extension_ratio']) if r['extension_ratio'] is not None else '-':>8}"
             f"{('%.3f' % r['near_high_frac']) if r['near_high_frac'] is not None else '-':>8}"
             f"  {r['marker']}")
    emit()

(HERE / "_structax_replay_out.txt").write_text("\n".join(OUT) + "\n")

# ── STEP 7 — multiplicity + the clustering that dominates this design ────────────────────
OUT2 = []


def emit2(s=""):
    print(s)
    OUT2.append(s)


def _norm_sf(z):
    return 0.5 * math.erfc(z / math.sqrt(2))


emit2("=" * 96)
emit2("STEP 7 — MULTIPLICITY (5 pre-registered comparisons) AND DATE CLUSTERING")
emit2("=" * 96)
ps = []
for k, sign, _ in PREREG:
    a, se, n1, n2 = results[k]
    z = abs(a - 0.5) / se if se and se > 0 else 0.0
    p = 2 * _norm_sf(z)
    ps.append((k, a, z, p))
for k, a, z, p in ps:
    emit2(f"  {k:<18} AUC {a:.3f}  z {z:>5.2f}  raw p {p:.4f}")
# Holm-Bonferroni at family alpha 0.05 over the 5 pre-registered tests
order = sorted(ps, key=lambda x: x[3])
m = len(order)
survived = []
for i, (k, a, z, p) in enumerate(order):
    thr = 0.05 / (m - i)
    ok = p <= thr and (not survived or True)
    emit2(f"  Holm step {i+1}: {k:<18} p {p:.4f} vs {thr:.4f} -> {'PASS' if ok else 'fail'}")
    if not ok:
        break
    survived.append(k)
emit2(f"  survive Holm-Bonferroni at family alpha 0.05: {survived if survived else 'NONE'}")
emit2()

emit2("DATE CLUSTERING — these are not 26 vs 27 independent observations:")
dsF = defaultdict(list)
dsR = defaultdict(list)
for r in FIX:
    dsF[r["alert_date"]].append(r)
for r in REJ:
    dsR[r["alert_date"]].append(r)
emit2(f"  real EPs: {len(FIX)} name-days on {len(dsF)} distinct market days")
for d in sorted(dsF):
    emit2(f"     {d}  n={len(dsF[d]):<3} {[r['ticker'] for r in dsF[d]]}")
emit2(f"  rejects:  {len(REJ)} name-days on {len(dsR)} distinct market days")
for d in sorted(dsR):
    emit2(f"     {d}  n={len(dsR[d])}")
emit2()

emit2("SENSITIVITY on the one field whose CI cleared 0.5 (rmv_15, lower = tighter):")
sub = [r for r in FIX if r["alert_date"] != date(2026, 4, 8)]
a, se, n1, n2 = auc([-r["rmv_15"] for r in sub], [-r["rmv_15"] for r in REJ])
emit2(f"  drop the 13 members that all share 2026-04-08: AUC {a:.3f} "
      f"[{max(0,a-1.96*se):.3f}, {min(1,a+1.96*se):.3f}]  nEP {n1}  nRej {n2}")
mF = [med([r["rmv_15"] for r in v]) for v in dsF.values()]
mR = [med([r["rmv_15"] for r in v]) for v in dsR.values()]
a2, se2, k1, k2 = auc([-x for x in mF], [-x for x in mR])
emit2(f"  one observation per market day ({len(dsF)} EP days vs {len(dsR)} reject days): AUC {a2:.3f}  "
      f"[{max(0,a2-1.96*se2):.3f}, {min(1,a2+1.96*se2):.3f}]  -- 2 days on one side is not a test")
emit2(f"  per-day median RMV-15, real EP days: "
      f"{[f'{d}:{med([r[chr(114)+chr(109)+chr(118)+chr(95)+chr(49)+chr(53)] for r in dsF[d]]):.0f}' for d in sorted(dsF)]}")
emit2(f"  per-day median RMV-15, reject days:  "
      f"{[f'{d}:{med([r[chr(114)+chr(109)+chr(118)+chr(95)+chr(49)+chr(53)] for r in dsR[d]]):.0f}' for d in sorted(dsR)]}")
emit2()
emit2("RMV-15 saturation (a ceiling value, not a measurement of tightness):")
for nm, pop in (("real EPs", FIX), ("rejects", REJ)):
    emit2(f"  {nm:<10} rmv_15 == 100.0 (clamped ceiling): "
          f"{sum(1 for r in pop if r['rmv_15'] == 100.0)}/{len(pop)}   "
          f"rmv_15 == 0.0 (clamped floor): {sum(1 for r in pop if r['rmv_15'] == 0.0)}/{len(pop)}")
emit2()
emit2("HOW THE AXIS TREATS CAPR vs THE OPERATOR'S OWN TEXTBOOK EP:")
for t, d in (("CAPR", date(2026, 8, 25)), ("MRNA", date(2026, 8, 19)), ("SNOW", date(2026, 5, 7))):
    r = axis(t, d)
    emit2(f"  {t} {d}: marker={r['marker']:<24} credit_steps={r['credit_steps']}  "
          f"stage2={r['stage2']}  rmv_tight={r['rmv_tight']}")

p = HERE / "_structax_replay_out.txt"
p.write_text(p.read_text() + "\n".join(OUT2) + "\n")

# ── STEP 8 — the liquidity confound, made concrete ───────────────────────────────────────
OUT3 = []


def emit3(s=""):
    print(s)
    OUT3.append(s)


def adv20(ticker, alert_date):
    b = bars_asof(ticker, alert_date)[-20:]
    if len(b) < 5:
        return None
    return med([x["close"] * x["volume"] for x in b])


for r in FIX + REJ:
    r["adv20"] = adv20(r["ticker"], r["alert_date"])


def spearman(xs, ys):
    n = len(xs)
    if n < 3:
        return float("nan")

    def rank(v):
        s = sorted(range(len(v)), key=lambda i: v[i])
        rk = [0.0] * len(v)
        i = 0
        while i < len(s):
            j = i
            while j + 1 < len(s) and v[s[j + 1]] == v[s[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                rk[s[k]] = avg
            i = j + 1
        return rk
    rx, ry = rank(xs), rank(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else float("nan")


emit3("=" * 96)
emit3("STEP 8 — THE LIQUIDITY CONFOUND (the two arms are not matched on anything)")
emit3("=" * 96)
for nm, pop in (("real EPs", FIX), ("rejects", REJ)):
    v = sorted(r["adv20"] for r in pop if r["adv20"])
    emit3(f"  {nm:<10} 20-day median dollar volume: min ${v[0]/1e6:>9,.1f}M  "
          f"median ${med(v)/1e6:>9,.1f}M  max ${v[-1]/1e6:>9,.1f}M")
pool = [r for r in FIX + REJ if r["adv20"] and r["rmv_15"] is not None]
emit3(f"  Spearman rho, rmv_15 vs 20-day dollar volume, pooled n={len(pool)}: "
      f"{spearman([r['adv20'] for r in pool], [r['rmv_15'] for r in pool]):.3f}   "
      f"(negative = thinner names read as 'less tight')")
emit3(f"  Spearman rho, near_high_frac vs dollar volume: "
      f"{spearman([r['adv20'] for r in pool], [r['near_high_frac'] for r in pool]):.3f}")
FLOOR = 38.9e6  # thinnest labelled real EP (QURE), per docs/analysis/silent_days_verify_2026-08-25.md
inband = [r for r in REJ if r["adv20"] and r["adv20"] >= FLOOR]
emit3(f"  rejects inside the labelled real-EP liquidity band (>= ${FLOOR/1e6:.1f}M/day): "
      f"{[r['ticker'] + ' ' + str(r['alert_date']) for r in inband]}")
if inband:
    a3, se3, n1, n2 = auc([-r["rmv_15"] for r in FIX], [-r["rmv_15"] for r in inband])
    emit3(f"  rmv_15 AUC against ONLY those liquidity-comparable rejects: {a3:.3f} "
          f"[{max(0,a3-1.96*se3):.3f}, {min(1,a3+1.96*se3):.3f}]  nEP {n1}  nRej {n2}  "
          f"-- n={n2} on one side, descriptive only")
    emit3(f"     their rmv_15: {[(r['ticker'], round(r['rmv_15'],1)) for r in inband]}")
emit3()

p = HERE / "_structax_replay_out.txt"
p.write_text(p.read_text() + "\n".join(OUT3) + "\n")

# ── STEP 9 — SUPPLEMENTARY: the same axis on history the 400-day purge has eaten ─────────
# mi_daily_closes is purged at 400 calendar days (db.purge_old_data), so replaying a
# 2026-04-08 alert TODAY leaves only ~180 bars and the 200-day SMA cannot be formed — a
# REPLAY artifact, not what the live axis saw in April. Re-pulled from Polygon (adjusted,
# the same source mi_daily_closes is built from) through the prod container, read-only,
# $0 marginal — capture: _structax_bars_polygon.psv. Prod remains the PRIMARY read above.
OUT4 = []


def emit4(s=""):
    print(s)
    OUT4.append(s)


PB: dict[tuple[str, date], list[dict]] = defaultdict(list)
for ln in (HERE / "_structax_bars_polygon.psv").read_text().splitlines():
    p = ln.split("|")
    if len(p) < 8 or p[0].startswith("#"):
        continue
    PB[(p[0], _d(p[1]))].append({
        "trade_date": _d(p[2]), "open_price": f(p[3]), "high_price": f(p[4]),
        "low_price": f(p[5]), "close": f(p[6]), "volume": f(p[7]),
    })
for k in PB:
    PB[k].sort(key=lambda r: r["trade_date"])


def axis_poly(ticker: str, alert_date: date) -> dict:
    lo = alert_date - timedelta(days=380)
    bars = [b for b in PB.get((ticker, alert_date), [])
            if lo <= b["trade_date"] < alert_date
            and b["high_price"] is not None and b["low_price"] is not None]
    feats = compute_structure_features(bars, alert_date)
    credit = structure_axis_credit(feats)
    return {"ticker": ticker, "alert_date": alert_date, "n_bars": len(bars), **feats, **credit}


emit4("=" * 96)
emit4("STEP 9 — SUPPLEMENTARY: same axis, history restored past the 400-day purge")
emit4("=" * 96)
# (a) validate the alternate source against prod on the overlapping dates
diffs, tot = 0, 0
for r in FIX + REJ:
    prod = {b["trade_date"]: b["close"] for b in bars_asof(r["ticker"], r["alert_date"])}
    for b in PB.get((r["ticker"], r["alert_date"]), []):
        if b["trade_date"] in prod and prod[b["trade_date"]]:
            tot += 1
            if abs(b["close"] - prod[b["trade_date"]]) > 0.01 * max(1.0, prod[b["trade_date"]]):
                diffs += 1
emit4(f"  source agreement on overlapping dates: {tot-diffs}/{tot} closes within 1% of mi_daily_closes")

FIXP = [axis_poly(t, d) for t, d in fix_days]
REJP = [axis_poly(t, d) for t, d in rej_days]
for r in FIXP + REJP:
    r["near_high_frac"] = (r["prior_close"] / r["trailing_high"]
                           if r["prior_close"] and r["trailing_high"] else None)
    r["stage2_num"] = None if r["stage2"] is None else (1.0 if r["stage2"] else 0.0)
    r["credit_steps"] = float(r["credit_steps"])
emit4()
emit4("  coverage now:")
for k in ["sma_200", "stage2", "rmv_15"]:
    a = sum(1 for r in FIXP if r[k] is not None)
    b = sum(1 for r in REJP if r[k] is not None)
    emit4(f"    {k:<16} real EPs {a}/{len(FIXP)}    rejects {b}/{len(REJP)}")
emit4(f"    still not computable on the EP side: "
      f"{[(r['ticker'], str(r['alert_date']), r['n_bars']) for r in FIXP if r['stage2'] is None]}")
emit4(f"    still not computable on the reject side: "
      f"{[(r['ticker'], str(r['alert_date']), r['n_bars']) for r in REJP if r['stage2'] is None]}")
emit4()
emit4("  what the axis says now:")
for nm, pop in (("real EPs", FIXP), ("rejects", REJP)):
    c = defaultdict(int)
    for r in pop:
        c[r["marker"]] += 1
    emit4(f"    {nm:<10} " + "  ".join(f"{k}={v}" for k, v in sorted(c.items()))
          + f"   |  credited (+1): {sum(1 for r in pop if r['credit_steps'] == 1)}/{len(pop)}")
emit4()
emit4("  separation, same PRE-REGISTERED directions:")
emit4(f"    {'field':<18}{'AUC':>7}{'95% CI':>18}{'nEP':>6}{'nRej':>6}{'medEP':>10}{'medRej':>10}")
ps2 = []
for k, sign, _ in PREREG:
    pos = [sign * r[k] for r in FIXP if r.get(k) is not None]
    neg = [sign * r[k] for r in REJP if r.get(k) is not None]
    a, se, n1, n2 = auc(pos, neg)
    rp = [r[k] for r in FIXP if r.get(k) is not None]
    rn = [r[k] for r in REJP if r.get(k) is not None]
    z = abs(a - 0.5) / se if se else 0.0
    ps2.append((k, a, 2 * _norm_sf(z)))
    emit4(f"    {k:<18}{a:>7.3f}  [{max(0,a-1.96*se):>5.3f}, {min(1,a+1.96*se):>5.3f}]"
          f"{n1:>6}{n2:>6}{(med(rp) or 0):>10.3f}{(med(rn) or 0):>10.3f}")
emit4()
order2 = sorted(ps2, key=lambda x: x[2])
surv2 = []
for i, (k, a, p) in enumerate(order2):
    thr = 0.05 / (len(order2) - i)
    if p > thr:
        break
    surv2.append(k)
emit4(f"  survive Holm-Bonferroni at family alpha 0.05: {surv2 if surv2 else 'NONE'}")
emit4(f"  raw p-values: " + "  ".join(f"{k}={p:.4f}" for k, a, p in ps2))
emit4()
emit4("  2x2 for stage2 with history restored:")
for nm, pop in (("real EPs", FIXP), ("rejects", REJP)):
    emit4(f"    {nm:<10} True={sum(1 for r in pop if r['stage2'] is True):<4}"
          f"False={sum(1 for r in pop if r['stage2'] is False):<4}"
          f"not-computable={sum(1 for r in pop if r['stage2'] is None)}")
emit4()
emit4("  per-name (restored history):")
for nm, pop in (("REAL EPs", FIXP), ("REJECTS", REJP)):
    emit4(f"  -- {nm}")
    for r in sorted(pop, key=lambda r: (r["alert_date"], r["ticker"])):
        emit4(f"    {r['ticker']:<7}{str(r['alert_date']):<12}bars={r['n_bars']:<5}"
              f"stage2={str(r['stage2']):<6}"
              f"rmv15={('%.1f' % r['rmv_15']) if r['rmv_15'] is not None else '-':<7}"
              f"ext={('%.3f' % r['extension_ratio']) if r['extension_ratio'] is not None else '-':<8}"
              f"p/high={('%.3f' % r['near_high_frac']) if r['near_high_frac'] is not None else '-':<8}"
              f"{r['marker']}")
emit4()
emit4("  CAPR with restored history:")
for d in ("2026-08-24", "2026-08-25"):
    r = axis_poly("CAPR", _d(d))
    emit4(f"    CAPR {d}: bars={r['n_bars']} stage2={r['stage2']} sma_200="
          f"{r['sma_200'] and round(r['sma_200'],2)} trailing_high={r['trailing_high']} "
          f"rmv_15={r['rmv_15'] and round(r['rmv_15'],1)} ext={r['extension_ratio'] and round(r['extension_ratio'],3)} "
          f"marker={r['marker']} credit={int(r['credit_steps'])}")

p = HERE / "_structax_replay_out.txt"
p.write_text(p.read_text() + "\n".join(OUT4) + "\n")

# ── STEP 10 — is the tightness separation a ceiling artifact? ────────────────────────────
OUT5 = []


def emit5(s):
    print(s)
    OUT5.append(s)


emit5("=" * 96)
emit5("STEP 10 — RMV-15 SATURATION SENSITIVITY (the one field that survived Holm)")
emit5("=" * 96)
cap = [r for r in REJ if r["rmv_15"] == 100.0]
emit5(f"  rejects pinned at the clamped 100 ceiling: {len(cap)}/{len(REJ)}  "
      f"{[r['ticker'] for r in cap]}")
emit5(f"  highest RMV-15 among the 26 real EPs: {max(r['rmv_15'] for r in FIX):.1f} "
      f"-- so every ceiling-pinned reject loses to EVERY real EP by construction")
emit5(f"  those pairs are {len(cap)*len(FIX)} of the {len(FIX)*len(REJ)} comparisons the AUC is built from")
sub = [r for r in REJ if r["rmv_15"] != 100.0]
a, se, n1, n2 = auc([-r["rmv_15"] for r in FIX], [-r["rmv_15"] for r in sub])
z = abs(a - 0.5) / se if se else 0.0
emit5(f"  rmv_15 AUC with the ceiling-pinned rejects dropped: {a:.3f} "
      f"[{max(0,a-1.96*se):.3f}, {min(1,a+1.96*se):.3f}]  nEP {n1}  nRej {n2}  "
      f"raw p {2*_norm_sf(z):.3f}")
emit5("  -> the separation is saturation, not a tightness gradient.")
p = HERE / "_structax_replay_out.txt"
p.write_text(p.read_text() + "\n".join(OUT5) + "\n")
