#!/usr/bin/env python3
"""STRUCTURE READ v2 — THE MEASUREMENT (READ-ONLY · $0 · SHADOW · nothing changed).

Runs `_structure_read_v2` over the same two populations
`docs/analysis/structure_axis_replay_2026-08-25.md` used, so the numbers are directly
comparable to the live axis's AUC 0.481:

  * 26 operator/evidence-labelled REAL EPs  — tests/fixtures/must_not_miss_eps.py
  * 27 REJECTS from 08-24 / 08-25           — re-derived from the mi_ep_scan_log capture

⚠ PRE-REGISTRATION — written before any number below was computed, and NOT revised after.
Directions come from `docs/methodology/structure_model.md` (his model), not from the data.

  PRIMARY (one test, threshold-free):
    overhead_vol_frac      LOWER = more like a real EP.  His supply argument taken
                           literally: the share of the name's own traded volume sitting
                           above the open.  0.0 = blue sky.

  SECONDARY (a declared family of three, Holm-corrected together):
    zones_cleared                     HIGHER = better  (§1 claim 4, the ladder count)
    base_range_adr                    LOWER  = better  (gap-robust base tightness)
    overhead_unfilled_gap_span_adr    LOWER  = better  (untraded air above the open)

  PRE-REGISTERED NOVELTY CHECK: Spearman(overhead_vol_frac, near_high_frac).  The live
  axis's trailing-high term already scores 0.662 on these two populations.  If |rho| >=
  0.90 the honest headline is "restates trailing-high distance, computed differently",
  NOT "a new measure".  Declared here so it cannot become an after-the-fact rationalisation.

  PRE-REGISTERED HARD CUT: MRNA opened 35% above every prior print, so ANY overhead
  measure returns blue sky for it — that tests "did it open above the trailing high",
  which the live axis already computes.  The non-trivial subgroup, applied symmetrically
  to both arms: name-days whose OPEN IS NOT ABOVE the prior trailing high (i.e. there is
  actually overhead to measure).

  EVERYTHING ELSE IS DESCRIPTIVE and explicitly outside the tested set: zones_remaining,
  adr_to_next_zone, inside_unfilled_gap, base_gap_* counts, rmv_15, the CLEAR_AIR /
  IFFY / INTO_SUPPLY label, the 60-day volume-profile variant.

NOT FITTED: no cutline is chosen, no threshold is swept for separation, no direction is
flipped after seeing a number.  A null reported clearly is the deliverable.

THE LINE: measurement only.  No rule, threshold, filter, toggle, cutline or trade state is
touched, and nothing here is a recommendation.
"""
from __future__ import annotations

import math
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))

import _structure_read_v2 as V2  # noqa: E402
from agents.market_intelligence.flag_detector import _ntr  # noqa: E402
from tests.fixtures.must_not_miss_eps import MUST_NOT_MISS  # noqa: E402

OUT: list[str] = []


def emit(s: str = "") -> None:
    print(s)
    OUT.append(s)


def _d(s: str) -> date:
    y, m, dd = s.split("-")
    return date(int(y), int(m), int(dd))


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


# ── captures (pulled ONCE by the 08-25 replay; re-read, never re-pulled) ───────────────
POLY: dict[tuple[str, date], list[dict]] = defaultdict(list)
for ln in (HERE / "_structax_bars_polygon.psv").read_text().splitlines():
    p = ln.split("|")
    if len(p) < 8 or p[0].startswith("#"):
        continue
    POLY[(p[0], _d(p[1]))].append({
        "trade_date": _d(p[2]), "open_price": _f(p[3]), "high_price": _f(p[4]),
        "low_price": _f(p[5]), "close": _f(p[6]), "volume": _f(p[7])})
for k in POLY:
    POLY[k].sort(key=lambda r: r["trade_date"])

PROD: dict[str, list[dict]] = defaultdict(list)
for ln in (HERE / "_structax_bars.psv").read_text().splitlines():
    p = ln.split("|")
    if len(p) < 7 or p[3] == "" or p[4] == "":
        continue
    PROD[p[0]].append({"trade_date": _d(p[1]), "open_price": _f(p[2]),
                       "high_price": _f(p[3]), "low_price": _f(p[4]),
                       "close": _f(p[5]), "volume": _f(p[6])})
for t in PROD:
    PROD[t].sort(key=lambda r: r["trade_date"])

rej_days: list[tuple[str, date]] = []
seen: set[tuple[str, str]] = set()
for ln in (HERE / "_structax_scanlog.psv").read_text().splitlines():
    p = ln.split("|")
    if len(p) < 7 or p[6].startswith("filter:universe_"):
        continue
    if (p[1], p[0]) in seen:
        continue
    seen.add((p[1], p[0]))
    rej_days.append((p[1], _d(p[0])))
rej_days.sort(key=lambda x: (x[1], x[0]))

FIXMAP = {(m.ticker, m.alert_date): m for m in MUST_NOT_MISS if not m.excluded}
fix_days = [(t, _d(ds)) for (t, ds) in FIXMAP]


# ── read one name-day ─────────────────────────────────────────────────────────────────
def read(ticker: str, ad: date) -> dict:
    allbars = POLY.get((ticker, ad), [])
    prior = [b for b in allbars if b["trade_date"] < ad]
    same = [b for b in allbars if b["trade_date"] == ad]
    r: dict = {"ticker": ticker, "alert_date": ad, "n_prior": len(prior)}
    if not same or not prior:
        r["reason"] = "no_alert_day_bar" if not same else "no_prior_bars"
        return r
    open_px = float(same[0]["open_price"])
    r.update(V2.structure_read_v2(prior, ad, open_px))
    highs = [b["high_price"] for b in prior if b["high_price"] is not None]
    r["trailing_high"] = max(highs) if highs else None
    r["near_high_frac"] = (r["prior_close"] / r["trailing_high"]
                           if r.get("prior_close") and r["trailing_high"] else None)
    r["open_above_trailing_high"] = (open_px > r["trailing_high"]) if r["trailing_high"] else None
    b20 = prior[-20:]
    r["adv20"] = (sorted(b["close"] * (b["volume"] or 0) for b in b20)[len(b20) // 2]
                  if len(b20) >= 5 else None)
    return r


# ── stats (same shapes as the 08-25 replay, so the numbers are comparable) ────────────
def auc(pos: list[float], neg: list[float]):
    n1, n2 = len(pos), len(neg)
    if not n1 or not n2:
        return float("nan"), float("nan"), n1, n2
    s = sum(1.0 if a > b else 0.5 if a == b else 0.0 for a in pos for b in neg)
    a = s / (n1 * n2)
    q1, q2 = a / (2 - a), 2 * a * a / (1 + a)
    se = math.sqrt(max(0.0, (a * (1 - a) + (n1 - 1) * (q1 - a * a)
                            + (n2 - 1) * (q2 - a * a)) / (n1 * n2)))
    return a, se, n1, n2


def _norm_sf(z):
    return 0.5 * math.erfc(z / math.sqrt(2))


def pval(a, se):
    return 2 * _norm_sf(abs(a - 0.5) / se) if se and se > 0 else float("nan")


def med(v):
    v = sorted(x for x in v if x is not None)
    if not v:
        return None
    return v[len(v) // 2] if len(v) % 2 else (v[len(v) // 2 - 1] + v[len(v) // 2]) / 2


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
            for k in range(i, j + 1):
                rk[s[k]] = (i + j) / 2 + 1
            i = j + 1
        return rk
    rx, ry = rank(xs), rank(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else float("nan")


def report(name: str, key: str, sign: int, FIX: list[dict], REJ: list[dict],
           note: str = "") -> tuple[float, float, float]:
    pos = [sign * r[key] for r in FIX if r.get(key) is not None]
    neg = [sign * r[key] for r in REJ if r.get(key) is not None]
    a, se, n1, n2 = auc(pos, neg)
    p = pval(a, se)
    emit(f"  {name:<34}{a:>7.3f}  [{max(0,a-1.96*se):>5.3f}, {min(1,a+1.96*se):>5.3f}]"
         f"{n1:>5}{n2:>5}{(med([r.get(key) for r in FIX]) or 0):>10.3f}"
         f"{(med([r.get(key) for r in REJ]) or 0):>10.3f}{p:>9.4f}  {note}")
    return a, se, p


# ══════════════════════════════════════════════════════════════════════════════════════
emit("=" * 112)
emit("STRUCTURE READ v2 — SUPPLY-LADDER MEASUREMENT (shadow, read-only, $0, nothing changed)")
emit("=" * 112)
emit()
emit("STEP 0 — PARITY: the REUSED level derivation, through this module's adapter,")
emit("         against the four level values structure_model.md §4 documents.")
prow = V2.parity_check(verbose=False)
emit("  " + "\n  ".join(f"{'OK ' if ok else 'XX '} {nm:<18} want {want:>8.2f}  "
                        f"got {('%.2f' % got) if got is not None else 'none':>8}"
                        for nm, ok, got, want in prow))
emit(f"  -> {sum(1 for _, ok, _, _ in prow if ok)}/{len(prow)} reproduced. "
     "Any miss here invalidates every ladder number below.")
emit()

FIX = [read(t, d) for t, d in fix_days]
REJ = [read(t, d) for t, d in rej_days]

emit("=" * 112)
emit("STEP 1 — POPULATIONS, COVERAGE, AND THE NO-LOOKAHEAD GUARD")
emit("=" * 112)
emit(f"  real EPs: {len(FIX)} name-days   rejects: {len(REJ)} name-days   "
     f"(the same 26 / 27 the 08-25 replay used)")
for nm, pop in (("real EPs", FIX), ("rejects", REJ)):
    bad = [r for r in pop if r.get("reason")]
    emit(f"  {nm:<10} computable: {len(pop)-len(bad)}/{len(pop)}"
         + (f"   not computable: {[(r['ticker'], str(r['alert_date']), r['reason']) for r in bad]}"
            if bad else ""))
emit("  the alert-day bar is never read beyond its OPEN; structure_read_v2 asserts no bar")
emit("  dated >= the alert date reaches any computation (the 08-25 capture rows are partial).")
emit()
emit("  OPEN cross-check against the fixture's own gap_pct / prev_close (catches wrong-row bugs):")
bigdiff = []
for r in FIX:
    m = FIXMAP.get((r["ticker"], str(r["alert_date"])))
    if not m or m.gap_pct is None or not r.get("gap_open_pct"):
        continue
    d = r["gap_open_pct"] - m.gap_pct
    if abs(d) > 1.0:
        bigdiff.append((r["ticker"], str(r["alert_date"]), round(m.gap_pct, 2),
                        round(r["gap_open_pct"], 2)))
emit(f"    members whose replayed open-gap differs from the fixture by > 1pp: "
     f"{len(bigdiff)}/{len(FIX)}  {bigdiff if bigdiff else ''}")
emit("    (a difference here is a split adjustment, not an error — every v2 output is a ratio,")
emit("     an ADR-normalised distance or a volume FRACTION, all of which cancel a uniform split.)")
emit()

# ── STEP 2 — THE RMV DEFECT, at N=1, on the name he objected to ───────────────────────
emit("=" * 112)
emit("STEP 2 — THE OPERATOR'S SECOND OBJECTION, MECHANICALLY: why CAPR reads as a tight base")
emit("=" * 112)
emit('  "how can CAPR have a tight base when there are two large gap downs?"')
emit()
emit("  RMV-15 = mean(gap-aware true range, last 3 bars) / mean(the same, last 15), mapped to")
emit("  0-100. A large bar INSIDE the 15-bar baseline inflates the DENOMINATOR, so the name")
emit("  reads TIGHTER. A large gap OUTSIDE that window is invisible to it entirely.")
emit()
for ad in (date(2026, 8, 24), date(2026, 8, 25)):
    prior = [b for b in POLY[("CAPR", ad)] if b["trade_date"] < ad]
    win = prior[-15:]
    ntrs = []
    for i, b in enumerate(win):
        gi = len(prior) - 15 + i
        ntrs.append((b["trade_date"], _ntr(b, prior[gi - 1]["close"] if gi > 0 else None)))
    base = sum(v for _, v in ntrs) / len(ntrs)
    recent = sum(v for _, v in ntrs[-3:]) / 3
    rr = read("CAPR", ad)
    emit(f"  CAPR {ad} — the 15 bars behind RMV-15 = {rr['rmv_15']:.1f} "
         f"(the live 'tight' cutline is 30):")
    for dt, v in ntrs:
        emit(f"      {dt}  daily true range {v:>6.2f}% of close"
             + ("   <- the last-3 window" if (dt, v) in ntrs[-3:] else ""))
    emit(f"      baseline mean {base:.2f}%  vs last-3 mean {recent:.2f}%  "
         f"-> ratio {recent/base:.3f}  -> RMV {rr['rmv_15']:.1f}")
    emit(f"      gap-robust alternative: base close-to-close span / ADR20 = "
         f"{rr['base_range_adr']:.2f} ADR   "
         f"(gaps inflate the span; ADR20 is a mean of INTRADAY ranges, which gaps do not)")
    emit(f"      true vacuums inside the 15-bar base: {rr['base_gap_count_1p0x']} at >=1 ADR "
         f"(largest {rr['base_gap_max_adr']:.2f} ADR)  -> tight_v2 = {rr['tight_v2']}")
    emit()
z = [g for g in V2.gap_zones([b for b in POLY[("CAPR", date(2026, 8, 25))]
                              if b["trade_date"] < date(2026, 8, 25)])
     if g["unfilled_span"] > 0]
emit("  every UNFILLED vacuum in CAPR's prior history (his 'huge gap down from July 27'):")
for g in sorted(z, key=lambda x: -x["unfilled_span"])[:8]:
    emit(f"      {g['date']}  {g['direction']:<4} {g['bottom']:.2f} -> {g['top']:.2f}  "
         f"span {g['span_pct']:.1f}% of the prior close  "
         f"unfilled {g['unfilled_span']:.2f} of {g['top']-g['bottom']:.2f}")
emit()

# ── STEP 3 — THE PRE-REGISTERED TESTS ─────────────────────────────────────────────────
emit("=" * 112)
emit("STEP 3 — THE PRE-REGISTERED TESTS (directions fixed before computing; ties count 0.5)")
emit("=" * 112)
emit("  AUC = chance a randomly picked real EP scores better than a randomly picked reject.")
emit("  0.500 = a coin.  The live structure axis scores 0.481 here; the selection score 0.63-0.70.")
emit()
emit(f"  {'measure':<34}{'AUC':>7}{'95% CI':>16}{'nEP':>5}{'nRj':>5}{'medEP':>10}{'medRej':>10}{'raw p':>9}")
emit("  " + "-" * 108)
a_prim, se_prim, p_prim = report("PRIMARY overhead_vol_frac", "overhead_vol_frac", -1, FIX, REJ,
                                 "lower = less supply overhead")
emit("  " + "-" * 108)
SEC = [("zones_cleared", "zones_cleared", +1, "more congestion zones cleared"),
       ("base_range_adr", "base_range_adr", -1, "gap-robust base tightness"),
       ("overhead_unfilled_gap_span_adr", "overhead_unfilled_gap_span_adr", -1,
        "untraded air above the open")]
sec_ps = []
for nm, k, sg, note in SEC:
    a, se, p = report("SECONDARY " + nm, k, sg, FIX, REJ, note)
    sec_ps.append((nm, a, p))
emit()
emit("  Holm-Bonferroni over the 3-member SECONDARY family at family alpha 0.05:")
order = sorted(sec_ps, key=lambda x: x[2])
surv = []
for i, (nm, a, p) in enumerate(order):
    thr = 0.05 / (len(order) - i)
    ok = p <= thr
    emit(f"    step {i+1}: {nm:<34} p {p:.4f} vs {thr:.4f} -> {'PASS' if ok else 'fail'}")
    if not ok:
        break
    surv.append(nm)
emit(f"    survive: {surv if surv else 'NONE'}")
emit(f"  the PRIMARY is a single pre-registered test and carries no correction: p = {p_prim:.4f}")
emit()

# ── STEP 4 — the pre-registered novelty check ─────────────────────────────────────────
emit("=" * 112)
emit("STEP 4 — IS THE PRIMARY NEW INFORMATION, OR TRAILING-HIGH DISTANCE IN DISGUISE?")
emit("=" * 112)
pool = [r for r in FIX + REJ if r.get("overhead_vol_frac") is not None
        and r.get("near_high_frac") is not None]
rho = spearman([r["overhead_vol_frac"] for r in pool], [r["near_high_frac"] for r in pool])
emit(f"  Spearman(overhead_vol_frac, near_high_frac), pooled n={len(pool)}: {rho:.3f}")
emit("  PRE-REGISTERED reading: |rho| >= 0.90 means it restates the live axis's own trailing-high")
emit("  term computed a different way, NOT a new measure.")
emit(f"  -> {'RESTATES IT' if abs(rho) >= 0.90 else 'adds information beyond it'}")
a_nh, se_nh, _, _ = auc([r["near_high_frac"] for r in FIX if r.get("near_high_frac") is not None],
                        [r["near_high_frac"] for r in REJ if r.get("near_high_frac") is not None])
emit(f"  for reference, near_high_frac on the SAME populations here: AUC {a_nh:.3f} "
     f"(the 08-25 replay reported 0.662 on prod-sourced bars)")
emit()

# ── STEP 5 — the hard cut ─────────────────────────────────────────────────────────────
emit("=" * 112)
emit("STEP 5 — THE HARD CUT: drop every name that opened above its own trailing high")
emit("=" * 112)
emit("  MRNA opened 35% above every prior print, so ANY overhead measure returns blue sky for it.")
emit("  That separation tests 'did it open at a new high', which the live axis already computes.")
emit("  This subgroup keeps ONLY name-days with real overhead to measure, both arms alike.")
F2 = [r for r in FIX if r.get("open_above_trailing_high") is False]
R2 = [r for r in REJ if r.get("open_above_trailing_high") is False]
emit(f"  real EPs kept: {len(F2)}/{len(FIX)}   rejects kept: {len(R2)}/{len(REJ)}")
emit(f"  dropped real EPs (opened at a new high): "
     f"{[r['ticker'] for r in FIX if r.get('open_above_trailing_high')]}")
emit(f"  dropped rejects (opened at a new high):  "
     f"{[r['ticker'] for r in REJ if r.get('open_above_trailing_high')]}")
emit()
emit(f"  {'measure':<34}{'AUC':>7}{'95% CI':>16}{'nEP':>5}{'nRj':>5}{'medEP':>10}{'medRej':>10}{'raw p':>9}")
emit("  " + "-" * 108)
report("PRIMARY overhead_vol_frac", "overhead_vol_frac", -1, F2, R2)
for nm, k, sg, note in SEC:
    report(nm, k, sg, F2, R2)
report("[ref] near_high_frac", "near_high_frac", +1, F2, R2, "the live axis's own term")
emit()

# ── STEP 5b — the two confounds that could manufacture this separation ────────────────
emit("=" * 112)
emit("STEP 5b — IS THIS JUST GAP SIZE, OR JUST 'THE NAME HAD ZONES AT ALL'? (two controls)")
emit("=" * 112)
emit("  CONTROL 1 — raw gap % at the OPEN. Every labelled real EP gapped >= 8.1% at the open by")
emit("  construction (the fixture's own admission basis); many rejects were logged on an INTRADAY")
emit("  gap and barely moved at the open. So a measure keyed off the open can separate the arms")
emit("  simply by separating gap size. structure_model.md §1 claim 4 makes this the decisive test:")
emit("  zones-consumed vs raw gap %, AT COMPARABLE GAP SIZE.")
emit()
gp = [(r["gap_open_pct"], r) for r in FIX + REJ if r.get("gap_open_pct") is not None]
for k, sg, nm in (("overhead_vol_frac", -1, "overhead_vol_frac"),
                  ("zones_cleared", +1, "zones_cleared")):
    sub = [(g, r) for g, r in gp if r.get(k) is not None]
    emit(f"    Spearman(open gap %, {nm}) pooled n={len(sub)}: "
         f"{spearman([g for g, _ in sub], [r[k] for _, r in sub]):.3f}")
a_gap, se_gap, _, _ = auc([r["gap_open_pct"] for r in FIX if r.get("gap_open_pct") is not None],
                          [r["gap_open_pct"] for r in REJ if r.get("gap_open_pct") is not None])
emit(f"    raw gap % ITSELF as a discriminator (bigger = 'more like a real EP'): AUC {a_gap:.3f} "
     f"[{max(0,a_gap-1.96*se_gap):.3f}, {min(1,a_gap+1.96*se_gap):.3f}]  "
     "— reported as a CONTROL, not a claim; its direction was not pre-registered.")
emit()
FLOOR_GAP = min(r["gap_open_pct"] for r in FIX if r.get("gap_open_pct") is not None)
F4 = [r for r in FIX if (r.get("gap_open_pct") or -99) >= FLOOR_GAP]
R4 = [r for r in REJ if (r.get("gap_open_pct") or -99) >= FLOOR_GAP]
emit(f"  MATCHED ON GAP SIZE — both arms restricted to an open gap >= {FLOOR_GAP:.1f}% (the labelled")
emit(f"  real-EP arm's own minimum, so the floor is taken from the data's definition, not chosen):")
emit(f"    real EPs {len(F4)}/{len(FIX)}   rejects {len(R4)}/{len(REJ)}   "
     f"median open gap now {med([r['gap_open_pct'] for r in F4]):.1f}% vs "
     f"{med([r['gap_open_pct'] for r in R4]):.1f}%")
emit(f"  {'measure':<34}{'AUC':>7}{'95% CI':>16}{'nEP':>5}{'nRj':>5}{'medEP':>10}{'medRej':>10}{'raw p':>9}")
emit("  " + "-" * 108)
report("PRIMARY overhead_vol_frac", "overhead_vol_frac", -1, F4, R4)
for nm, k, sg, note in SEC:
    report(nm, k, sg, F4, R4)
report("[control] raw gap %", "gap_open_pct", +1, F4, R4, "should now be ~0.5 if matched")
emit()
emit("  BEST-ADMISSION-PRICE SENSITIVITY — the fairest possible version for the rejects. Instead of")
emit("  the open, each reject is re-read at the HIGHEST price its own scan log ever showed that day")
emit("  (prior close x (1 + its max logged gap)), i.e. the most favourable moment admission could")
emit("  have fired. Every reject reached at least a 9.2% gap at some tick. Real EPs keep their opens.")
maxgap: dict[tuple[str, str], float] = {}
for ln in (HERE / "_structax_scanlog.psv").read_text().splitlines():
    p = ln.split("|")
    if len(p) < 7 or p[6].startswith("filter:universe_"):
        continue
    g = _f(p[2])
    if g is not None:
        k2 = (p[1], p[0])
        maxgap[k2] = max(maxgap.get(k2, -1e9), g)
RBEST = []
for t, d in rej_days:
    allb = POLY.get((t, d), [])
    prior = [b for b in allb if b["trade_date"] < d]
    g = maxgap.get((t, str(d)))
    if not prior or g is None:
        continue
    px = float(prior[-1]["close"]) * (1 + g / 100.0)
    rr = {"ticker": t, "alert_date": d, "n_prior": len(prior)}
    rr.update(V2.structure_read_v2(prior, d, px))
    RBEST.append(rr)
emit(f"  {'measure':<34}{'AUC':>7}{'95% CI':>16}{'nEP':>5}{'nRj':>5}{'medEP':>10}{'medRej':>10}{'raw p':>9}")
emit("  " + "-" * 108)
report("PRIMARY overhead_vol_frac", "overhead_vol_frac", -1, FIX, RBEST)
for nm, k, sg, note in SEC:
    report(nm, k, sg, FIX, RBEST)
emit()
emit("  CONTROL 2 — does zones_cleared measure CLEARING, or just 'this name has qualified zones'?")
emit("  A level needs >=2 failed test EPISODES to qualify, so a name that collapsed and never")
emit("  retested has NO qualified levels and scores 0 cleared for the wrong reason.")
for nm, pop in (("real EPs", FIX), ("rejects", REJ)):
    haz = [r for r in pop if (r.get("zones_overhead_at_prior_close") or 0) > 0]
    emit(f"    {nm:<10} have >=1 qualified overhead zone: {len(haz)}/{len(pop)}   "
         f"median zones overhead {med([r['zones_overhead_at_prior_close'] for r in pop]):.0f}")
for r in FIX + REJ:
    z = r.get("zones_overhead_at_prior_close")
    r["cleared_frac"] = (r["zones_cleared"] / z) if z else None
emit(f"  {'measure':<34}{'AUC':>7}{'95% CI':>16}{'nEP':>5}{'nRj':>5}{'medEP':>10}{'medRej':>10}{'raw p':>9}")
emit("  " + "-" * 108)
report("[post-hoc] cleared_frac", "cleared_frac", +1, FIX, REJ,
       "share of overhead zones cleared, names WITH zones only")
emit("  ⚠ POST-HOC — not in the pre-registered family; run as a confound check, not as a finding.")
emit()

# ── STEP 6 — young names ──────────────────────────────────────────────────────────────
emit("=" * 112)
emit("STEP 6 — YOUNG NAMES (the live axis returns 'unknown' and zero credit for these)")
emit("=" * 112)
emit("  v2 needs no 200-session average: it reads whatever history exists, and says how much.")
young = [r for r in FIX + REJ if r.get("n_prior") is not None and r["n_prior"] < 200]
emit(f"  name-days with under 200 prior sessions: {len(young)}")
emit(f"  {'ticker':<7}{'date':<12}{'arm':<9}{'bars':>5}{'v1 axis':>10}"
     f"{'ovh_vol':>9}{'cleared':>8}{'baseADR':>9}{'gapADR':>8}  label")
fixkeys = {(r["ticker"], r["alert_date"]) for r in FIX}
for r in sorted(young, key=lambda x: x["n_prior"]):
    arm = "real EP" if (r["ticker"], r["alert_date"]) in fixkeys else "reject"
    emit(f"  {r['ticker']:<7}{str(r['alert_date']):<12}{arm:<9}{r['n_prior']:>5}"
         f"{'unknown':>10}"
         f"{(('%.3f' % r['overhead_vol_frac']) if r.get('overhead_vol_frac') is not None else '-'):>9}"
         f"{(str(r.get('zones_cleared')) if r.get('zones_cleared') is not None else '-'):>8}"
         f"{(('%.2f' % r['base_range_adr']) if r.get('base_range_adr') is not None else '-'):>9}"
         f"{(('%.2f' % r['overhead_unfilled_gap_span_adr']) if r.get('overhead_unfilled_gap_span_adr') is not None else '-'):>8}"
         f"  {r.get('label', r.get('reason'))}")
emit()
emit("  SENSITIVITY (the headline above KEEPS them — short history means little overhead by")
emit("  construction, so the 7 young rejects bias the primary AGAINST separating):")
F3 = [r for r in FIX if (r.get("n_prior") or 0) >= 200]
R3 = [r for r in REJ if (r.get("n_prior") or 0) >= 200]
emit(f"  {'measure':<34}{'AUC':>7}{'95% CI':>16}{'nEP':>5}{'nRj':>5}{'medEP':>10}{'medRej':>10}{'raw p':>9}")
emit("  " + "-" * 108)
report("PRIMARY overhead_vol_frac", "overhead_vol_frac", -1, F3, R3)
for nm, k, sg, note in SEC:
    report(nm, k, sg, F3, R3)
emit()

# ── STEP 7 — CAPR vs MRNA, the worked examples ────────────────────────────────────────
emit("=" * 112)
emit("STEP 7 — CAPR vs MRNA (if a measure cannot separate these two it has not solved his problem)")
emit("=" * 112)
WORKED = [("CAPR", date(2026, 8, 24)), ("CAPR", date(2026, 8, 25)),
          ("MRNA", date(2026, 8, 19)), ("SNOW", date(2026, 5, 7)),
          ("QURE", date(2026, 5, 29)), ("OESX", date(2026, 8, 25))]
emit(f"  {'name':<16}{'open':>9}{'ovh_vol':>9}{'zones':>7}{'clr':>5}{'rem':>5}"
     f"{'nextADR':>9}{'ovhGapADR':>11}{'inGap':>7}{'rmv15':>8}{'baseADR':>9}  label")
for t, d in WORKED:
    r = read(t, d)
    if r.get("reason"):
        emit(f"  {t+' '+str(d):<16}  {r['reason']}")
        continue
    emit(f"  {t+' '+str(d):<16}{r['open']:>9.2f}{r['overhead_vol_frac']:>9.3f}"
         f"{r['zones_overhead_at_prior_close']:>7}{r['zones_cleared']:>5}{r['zones_remaining']:>5}"
         f"{(('%.2f' % r['adr_to_next_zone']) if r['adr_to_next_zone'] is not None else 'blue'):>9}"
         f"{r['overhead_unfilled_gap_span_adr']:>11.2f}"
         f"{str(r['inside_unfilled_gap']):>7}{r['rmv_15']:>8.1f}{r['base_range_adr']:>9.2f}"
         f"  {r['label']}")
emit()
emit("  the live structure axis gives every one of these the identical verdict: no_stage2, credit 0.")
emit()

# ── STEP 8 — confounds and the label distribution ─────────────────────────────────────
emit("=" * 112)
emit("STEP 8 — CONFOUNDS, SENSITIVITIES, AND WHAT THE LABEL SAYS")
emit("=" * 112)
poolL = [r for r in FIX + REJ if r.get("adv20") and r.get("overhead_vol_frac") is not None]
emit(f"  Spearman(overhead_vol_frac, 20-day dollar volume), pooled n={len(poolL)}: "
     f"{spearman([r['adv20'] for r in poolL], [r['overhead_vol_frac'] for r in poolL]):.3f}")
emit(f"  Spearman(base_range_adr,  20-day dollar volume): "
     f"{spearman([r['adv20'] for r in poolL if r.get('base_range_adr') is not None], [r['base_range_adr'] for r in poolL if r.get('base_range_adr') is not None]):.3f}")
emit(f"  Spearman(rmv_15,          20-day dollar volume): "
     f"{spearman([r['adv20'] for r in poolL if r.get('rmv_15') is not None], [r['rmv_15'] for r in poolL if r.get('rmv_15') is not None]):.3f}"
     "   (the 08-25 replay measured -0.32 for this one)")
emit("  the same correlation computed WITHIN each arm (if it only exists across the arms, it is")
emit("  the between-group liquidity gap doing the work, not a within-name relationship):")
for nm, pop in (("real EPs", FIX), ("rejects", REJ)):
    sub = [r for r in pop if r.get("adv20") and r.get("overhead_vol_frac") is not None]
    emit(f"    {nm:<10} n={len(sub):<3} rho(overhead_vol_frac, dollar volume) = "
         f"{spearman([r['adv20'] for r in sub], [r['overhead_vol_frac'] for r in sub]):.3f}")
FLOOR = 38.9e6   # the thinnest labelled real EP (QURE), per silent_days_verify_2026-08-25.md
inband = [r for r in REJ if r.get("adv20") and r["adv20"] >= FLOOR]
emit(f"  rejects inside the labelled real-EP liquidity band (>= ${FLOOR/1e6:.1f}M/day): "
     f"{[r['ticker'] + ' ' + str(r['alert_date']) for r in inband]}")
if inband:
    a, se, _, _ = auc([-r["overhead_vol_frac"] for r in FIX if r.get("overhead_vol_frac") is not None],
                      [-r["overhead_vol_frac"] for r in inband])
    emit(f"  primary against ONLY those liquidity-comparable rejects: AUC {a:.3f} "
         f"[{max(0,a-1.96*se):.3f}, {min(1,a+1.96*se):.3f}]  n={len(inband)} on one side — "
         "a description, not a test")
emit()
emit("  DATE CLUSTERING — these are not 26 vs 27 independent observations:")
dF, dR = defaultdict(int), defaultdict(int)
for r in FIX:
    dF[r["alert_date"]] += 1
for r in REJ:
    dR[r["alert_date"]] += 1
emit(f"    real EPs: {len(FIX)} name-days on {len(dF)} market days "
     f"(largest single day n={max(dF.values())}, 2026-04-08)")
emit(f"    rejects:  {len(REJ)} name-days on {len(dR)} market days")
sub = [r for r in FIX if r["alert_date"] != date(2026, 4, 8)]
a, se, n1, n2 = auc([-r["overhead_vol_frac"] for r in sub if r.get("overhead_vol_frac") is not None],
                    [-r["overhead_vol_frac"] for r in REJ if r.get("overhead_vol_frac") is not None])
emit(f"    primary with the 13 members that all share 2026-04-08 dropped: AUC {a:.3f} "
     f"[{max(0,a-1.96*se):.3f}, {min(1,a+1.96*se):.3f}]  nEP {n1}")
emit()
emit("  SENSITIVITY on the one inherited size constant (LARGE_GAP_ADR = 1.0, the encoder's")
emit("  REJECT_ADR) — 'a base with a large vacuum in it is not tight' at three sizes:")
for k, lbl in (("base_gap_count_0p5x", "0.5 ADR"), ("base_gap_count_1p0x", "1.0 ADR"),
               ("base_gap_count_2p0x", "2.0 ADR")):
    fe = sum(1 for r in FIX if (r.get(k) or 0) > 0)
    re_ = sum(1 for r in REJ if (r.get(k) or 0) > 0)
    emit(f"    gap >= {lbl} inside the 15-bar base: real EPs {fe}/{len(FIX)}   "
         f"rejects {re_}/{len(REJ)}")
emit("    ⚠ the 2.0-ADR row is a one-sided screen (0/26 vs 6/27), and it comes out of a")
emit("      three-point sensitivity sweep — descriptive, not a pre-registered test.")
emit(f"      the 6 rejects carrying a >=2 ADR vacuum inside their base: "
     f"{[r['ticker'] + ' ' + str(r['alert_date']) for r in REJ if (r.get('base_gap_count_2p0x') or 0) > 0]}")
emit()
emit("  v1 vs v2 tightness, side by side (the live cutline is rmv_15 <= 30):")
for nm, pop in (("real EPs", FIX), ("rejects", REJ)):
    t1 = sum(1 for r in pop if r.get("rmv_tight") is True)
    t2 = sum(1 for r in pop if r.get("tight_v2") is True)
    emit(f"    {nm:<10} rmv_tight (live): {t1}/{len(pop)}    tight_v2 (gap-aware): {t2}/{len(pop)}")
emit()
emit("  DESCRIPTIVE label distribution (outside the tested set):")
for nm, pop in (("real EPs", FIX), ("rejects", REJ)):
    c = defaultdict(int)
    for r in pop:
        c[r.get("label", r.get("reason", "?"))] += 1
    emit(f"    {nm:<10} " + "  ".join(f"{k}={v}" for k, v in sorted(c.items())))
emit()

# ── STEP 9 — every name ───────────────────────────────────────────────────────────────
emit("=" * 112)
emit("STEP 9 — EVERY NAME, EVERY v2 OUTPUT")
emit("=" * 112)
for nm, pop in (("REAL EPs (labelled)", FIX), ("REJECTS (08-24 / 08-25)", REJ)):
    emit(f"-- {nm} " + "-" * (100 - len(nm)))
    emit(f"  {'ticker':<7}{'date':<12}{'bars':>5}{'gap%':>7}{'ovh_vol':>9}{'ovh60d':>8}"
         f"{'zOvh':>5}{'clr':>4}{'rem':>4}{'nextADR':>9}{'ovhGapADR':>10}{'inGap':>6}"
         f"{'rmv15':>7}{'baseADR':>8}{'bGapADR':>8}  label")
    for r in sorted(pop, key=lambda x: (x["alert_date"], x["ticker"])):
        if r.get("reason"):
            emit(f"  {r['ticker']:<7}{str(r['alert_date']):<12}{r.get('n_prior', 0):>5}"
                 f"   {r['reason']}")
            continue
        def g(k, fmt="%.2f", alt="-"):
            v = r.get(k)
            return (fmt % v) if v is not None else alt
        emit(f"  {r['ticker']:<7}{str(r['alert_date']):<12}{r['n_prior']:>5}"
             f"{g('gap_open_pct','%.1f'):>7}{g('overhead_vol_frac','%.3f'):>9}"
             f"{g('overhead_vol_frac_60d','%.3f'):>8}"
             f"{r['zones_overhead_at_prior_close']:>5}{r['zones_cleared']:>4}"
             f"{r['zones_remaining']:>4}{g('adr_to_next_zone','%.2f','blue'):>9}"
             f"{g('overhead_unfilled_gap_span_adr'):>10}{str(r['inside_unfilled_gap'])[:5]:>6}"
             f"{g('rmv_15','%.1f'):>7}{g('base_range_adr'):>8}{g('base_gap_max_adr'):>8}"
             f"  {r['label']}")
    emit()

(HERE / "_structure_read_v2_out.txt").write_text("\n".join(OUT) + "\n")
print(f"\n[captured -> {HERE / '_structure_read_v2_out.txt'}]")
