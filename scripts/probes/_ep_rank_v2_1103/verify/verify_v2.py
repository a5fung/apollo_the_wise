#!/usr/bin/env python3
"""BLIND verifier — EP ranking v2 (pre-registration docs/analysis/ep_rank_v2_prereg_2026-11-03.md).

Independent recompute, written BEFORE reading build/rank_v2.py. $0, local files only.
Zones: imports scripts/probes/_533_nbis_structure_encoder.py and calls encode(..., preopen=True)
UNCHANGED (the supply-ladder probe consumes exactly n_cleared / n_uncleared from that call).

Definitional choices the pre-registration leaves open (stated, not hidden):
  * 5-year window: bars with trade_date >= D minus 5 calendar years (data starts 2021-09-27,
    so this only trims for D after 2026-09-27). A full-history variant is also run.
  * swing low = mirror of pivot_levels' pivot high: low[i] <= min(low[i-2:i]) and
    low[i] < min(low[i+1:i+3]), i in the 40 sessions before D, wings from bars <= D only.
  * ADR20 in price = encoder adr20_pct(days, ia)/100 * base_high.
  * held = both of the 2 lowest swing lows >= base_high - 1 ADR ("within 1 ADR ... or above").
  * pullbacks scored both as the binary held flag and as the continuous min distance (ADR).
"""
from __future__ import annotations

import bisect
import csv
import gzip
import json
import random
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path("/Users/alvinfung/apollo_the_wise")
HERE = ROOT / "scripts/probes/_ep_rank_v2_1103"
OUT = HERE / "verify"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts/probes"))
import _533_nbis_structure_encoder as nbis  # noqa: E402  (encode() reused unchanged)
from scripts.alert_rank_shadow_running_read import CohortRead, score_both_directions  # noqa: E402

LOG = []


def P(*a):
    s = " ".join(str(x) for x in a)
    LOG.append(s)
    print(s)


# ───────────────────────── data ─────────────────────────
pairs = []
with open(HERE / "pairs.tsv") as f:
    for r in csv.DictReader(f, delimiter="\t"):
        pairs.append(r)

daily_full: dict[str, list] = defaultdict(list)
with gzip.open(HERE / "bars.csv.gz", "rt") as f:
    for r in csv.DictReader(f):
        try:
            o, h, l, c = (float(r[k]) for k in ("open_price", "high_price", "low_price", "close"))
        except (TypeError, ValueError):
            continue
        if c <= 0 or h <= 0:
            continue
        v = float(r["volume"]) if r["volume"] not in ("", None) else 0.0
        daily_full[r["ticker"]].append((r["trade_date"], o, h, l, c, v))
for t in daily_full:
    daily_full[t].sort()
daily_full = dict(daily_full)

alerts_by_day: dict[str, set] = defaultdict(set)
with open(HERE / "ep_alerts.csv") as f:
    for r in csv.DictReader(f):
        alerts_by_day[r["alert_date"]].add(r["ticker"])

shadow = {}
dups = 0
with open(HERE / "shadow_rows.csv") as f:
    for r in csv.DictReader(f):
        k = (r["ticker"], r["alert_date"])
        if k in shadow:
            dups += 1
            continue
        shadow[k] = r


def fnum(x):
    try:
        return None if x in ("", None) else float(x)
    except ValueError:
        return None


# C outcomes — parsed exactly as _rank_shadow_running_read_1103/score.py does
crow = []
for r in csv.reader(open(ROOT / "scripts/probes/_rank_shadow_running_read_1103/rows.psv"), delimiter="|"):
    F = lambda s: None if s == "" else float(s)
    d = dict(tk=r[0], date=r[1], adr=F(r[2]), high=r[3] == "t", filled=r[4] == "t", tier=r[5],
             c_eod=F(r[6]), pool_eod=int(r[7]), c_945=F(r[8]), pool_945=int(r[9]),
             open0=F(r[10]), low0=F(r[11]), sess=int(r[12]),
             mh5=F(r[13]), mh20=F(r[14]), r5=F(r[15]), r20=F(r[16]), minlow=F(r[17]))
    d["x5"] = None if (d["mh5"] is None or not d["adr"]) else d["mh5"] / d["adr"]
    d["x20"] = None if (d["mh20"] is None or not d["adr"]) else d["mh20"] / d["adr"]
    d["loser"] = (d["minlow"] is not None and d["low0"] is not None and d["minlow"] < d["low0"])
    crow.append(d)

# ───────────────────────── population checks ─────────────────────────
P("=" * 96)
P("POPULATION CHECKS")
import tests.fixtures.must_not_trade_charts as mntc  # noqa: E402
import tests.fixtures.must_not_miss_eps as mnme  # noqa: E402

fixA = {(r.ticker, r.alert_date): r.verdict for r in mntc.CHART_RULINGS}
pA = {(r["ticker"], r["date"]): r["label"] for r in pairs if r["source"] == "A"}
P(f"A: fixture rulings={len(fixA)} pairs.tsv A rows={len(pA)} "
  f"exact (ticker,date,verdict) match={fixA == pA}")
if fixA != pA:
    P("  only-in-fixture:", sorted(set(fixA.items()) - set(pA.items())))
    P("  only-in-pairs  :", sorted(set(pA.items()) - set(fixA.items())))
yesA = {k for k, v in pA.items() if v in ("GOOD_CHART", "OKISH_CHART")}
noA = {k for k, v in pA.items() if v == "BAD_CHART"}
P(f"A yes(GOOD+OKISH)={len(yesA)} no(BAD)={len(noA)} excluded other verdicts={len(pA)-len(yesA)-len(noA)}")

fixB = {(m.ticker, m.alert_date): m.label_source for m in mnme.MUST_NOT_MISS}
pB = {(r["ticker"], r["date"]): r["label"] for r in pairs if r["source"] == "B"}
P(f"B: fixture members={len(fixB)} pairs.tsv B rows={len(pB)} exact match={fixB == pB}")
B_op = sorted(k for k, v in pB.items() if v == "operator")
B2 = sorted(k for k, v in pB.items() if v != "operator")
DOC_OP = {("BFLY", "2026-06-18"), ("ABNB", "2026-08-07"), ("PLTR", "2026-08-04"), ("TEAM", "2026-08-07"),
          ("HTFL", "2026-08-14"), ("MRNA", "2026-08-19"), ("CHPT", "2026-09-03"), ("PENG", "2026-10-07")}
P(f"B operator rows={len(B_op)} == operator_labelled_eps.md table (8): {set(B_op) == DOC_OP}")
P(f"B2 (R-picked evidence rows, NOT his labels)={len(B2)} labels={sorted(set(pB[k] for k in B2))}")
pC = {(r["ticker"], r["date"]) for r in pairs if r["source"] == "C"}
cC = {(r["tk"], r["date"]) for r in crow}
P(f"C: pairs.tsv C={len(pC)} rows.psv={len(cC)} same set={pC == cC}; sessions={len({d for _, d in cC})}; "
  f"min date={min(d for _, d in cC)}")
P(f"shadow_rows duplicates dropped (first kept)={dups}")
P(f"ep_alerts: first date={min(alerts_by_day)} last={max(alerts_by_day)} days={len(alerts_by_day)} "
  f"distinct (date,ticker)={sum(len(v) for v in alerts_by_day.values())}")
# C pools: ep_alerts distinct tickers per day == rows.psv day members == pool_size_eod
cpool = defaultdict(list)
for r in crow:
    cpool[r["date"]].append(r)
mism = [d for d, v in cpool.items() if not (len(v) == v[0]["pool_eod"] == len(alerts_by_day.get(d, ())))]
P(f"C pool check (rows.psv day count == pool_size_eod == ep_alerts count): mismatching days={len(mism)}")


# ───────────────────────── features ─────────────────────────
def window(t: str, d: str, five_year: bool = True):
    days = daily_full.get(t)
    if not days:
        return None
    if five_year:
        y, m, dd = (int(x) for x in d.split("-"))
        try:
            lo = date(y - 5, m, dd).isoformat()
        except ValueError:
            lo = date(y - 5, m, 28).isoformat()
        days = [r for r in days if r[0] >= lo]
    return days


def swing_lows(days, ia, W):
    lows = [r[3] for r in days[: ia + 1]]          # bars <= D only (no look-ahead)
    out = []
    for i in range(max(2, ia - W), ia):
        if i + 2 > ia:                              # right wing would need a bar after D
            continue
        if lows[i] <= min(lows[i - 2:i]) and lows[i] < min(lows[i + 1:i + 3]):
            out.append(i)
    return out


def features(t, d, five_year=True, ADRK=1.0, VOLW=252, SW=40, BASE_END=250, wing_prior_only=False):
    days = window(t, d, five_year)
    f = dict(ticker=t, date=d)
    if days is None:
        f["err"] = "no_bars"
        return f
    idx = {r[0]: i for i, r in enumerate(days)}
    if d not in idx:
        f["err"] = "no_bar_on_D"
        return f
    ia = idx[d]
    enc = nbis.encode(t, d, {t: days}, {}, preopen=True)
    if enc.get("error"):
        f["err"] = enc["error"]
        return f
    f["history"] = ia
    f["zones_cleared"] = enc["n_cleared"]
    f["zones_remaining"] = enc["n_uncleared"]
    f["cleared_ath"] = int(enc["open"] > enc["hist_max"])
    o, h, l, c, v = days[ia][1:6]
    prior_v = [r[5] for r in days[:ia]]
    f["vol_ratio_252"] = (v / max(prior_v[ia - VOLW:ia])) if ia >= VOLW and max(prior_v[ia - VOLW:ia]) > 0 else None
    f["vol_highest_ever"] = int(v > max(prior_v)) if prior_v else None
    f["tightness_eod_bars"] = (h - l) / h * 100.0
    sk = shadow.get((t, d))
    f["tightness_eod"] = fnum(sk["tightness_pct_eod"]) if sk else f["tightness_eod_bars"]
    f["tightness_eod_shadow"] = fnum(sk["tightness_pct_eod"]) if sk else None
    f["tightness_asof0945"] = fnum(sk["tightness_pct_asof0945"]) if sk else None
    # pullbacks held an old base high
    if ia >= BASE_END:
        base_high = max(r[2] for r in days[ia - BASE_END: ia - SW])
        adr = nbis.adr20_pct(days, ia)
        if wing_prior_only:     # right wing may not use the gap day D either
            sl = [i for i in swing_lows(days, ia, SW) if i + 2 <= ia - 1]
        else:
            sl = swing_lows(days, ia, SW)
        two = sorted(sl, key=lambda i: days[i][3])[:2]
        f["n_swing_lows"] = len(sl)
        if two and adr:
            adr_px = adr / 100.0 * base_high
            dists = [(days[i][3] - base_high) / adr_px for i in two]
            f["pb_min_dist_adr"] = min(dists)
            f["pullbacks_held"] = int(all(x >= -ADRK for x in dists))
            f["pb_lows"] = [(days[i][0], days[i][3]) for i in two]
            f["base_high"] = base_high
        else:
            f["pb_min_dist_adr"] = None
            f["pullbacks_held"] = None
    else:
        f["pb_min_dist_adr"] = None
        f["pullbacks_held"] = None
        f["n_swing_lows"] = None
    return f


def auc(feat, rows_yes, rows_no):
    ys = [r[feat] for r in rows_yes if r.get(feat) is not None]
    ns = [r[feat] for r in rows_no if r.get(feat) is not None]
    if not ys or not ns:
        return None, len(ys), len(ns)
    g = sum((a > b) + 0.5 * (a == b) for a in ys for b in ns)
    return g / (len(ys) * len(ns)), len(ys), len(ns)


def pct_rank(sorted_vals, v):   # == alert_rank_shadow._pct_rank
    lo = bisect.bisect_left(sorted_vals, v)
    hi = bisect.bisect_right(sorted_vals, v)
    return (lo + (hi - lo) / 2) / len(sorted_vals)


FEATS = ["zones_cleared", "tightness_eod", "vol_ratio_252", "pullbacks_held", "pb_min_dist_adr",
         "zones_remaining", "cleared_ath", "vol_highest_ever", "tightness_asof0945"]
# headline column per pre-registered feature (1 zones, 2 volume, 3 pullbacks, 4 tightness EOD)
COMPOSITE_ELIGIBLE = ["zones_cleared", "vol_ratio_252", "pullbacks_held", "tightness_eod"]
# the letter of feature 4 names BOTH shadow tightness columns
LETTER_ELIGIBLE = COMPOSITE_ELIGIBLE + ["tightness_asof0945"]


def run(cfg: dict, label: str, verbose: bool = False, forced: list | None = None, eligible=None, const=False):
    eligible = eligible or COMPOSITE_ELIGIBLE
    cache: dict = {}

    def F(t, d):
        k = (t, d)
        if k not in cache:
            cache[k] = features(t, d, **cfg)
        return cache[k]

    A_yes = [F(*k) for k in sorted(yesA)]
    A_no = [F(*k) for k in sorted(noA)]
    scores = {}
    for ft in FEATS:
        a, ny, nn = auc(ft, A_yes, A_no)
        if a is None:
            scores[ft] = (None, None, ny, nn)
            continue
        direction = "more=yes" if a >= 0.5 else "less=yes"
        scores[ft] = (max(a, 1 - a), direction, ny, nn)
    if forced is None:
        qual = [ft for ft in eligible if scores[ft][0] is not None and scores[ft][0] >= 0.65]
    else:
        qual = forced

    def comp_for(t, d, pool_tickers):
        """Mean of oriented within-day pct ranks (low = yes-like). Pool = that day's alerts
        with bars, plus the pair itself. Members lacking any composite feature are dropped."""
        members = set(pool_tickers) | {t}
        rows = [F(x, d) for x in sorted(members)]
        rows = [r for r in rows if "err" not in r and all(r.get(q) is not None for q in qual)]
        me = next((r for r in rows if r["ticker"] == t), None)
        if me is None or not qual:
            return None, len(rows)
        if const:                      # null check: a ranking that knows nothing
            return 0.5, len(rows)
        tot = 0.0
        for q in qual:
            sv = sorted(r[q] for r in rows)
            pr = pct_rank(sv, me[q])
            tot += (1 - pr) if scores[q][1] == "more=yes" else pr
        return tot / len(qual), len(rows)

    # (i) composite on A
    resA = []
    for k in sorted(yesA | noA):
        t, d = k
        pool = [x for x in alerts_by_day.get(d, ()) if x in daily_full]
        c, n = comp_for(t, d, pool)
        resA.append(dict(t=t, d=d, y=k in yesA, comp=c, featured=n, alerts=len(alerts_by_day.get(d, ()))))
    rank_A = [r for r in resA if r["comp"] is not None and r["featured"] >= 2]
    ys = [r["comp"] for r in rank_A if r["y"]]
    ns = [r["comp"] for r in rank_A if not r["y"]]
    a_i = (sum((a < b) + 0.5 * (a == b) for a in ys for b in ns) / (len(ys) * len(ns))) if ys and ns else None
    # (ii) his labelled EPs
    resB = []
    for (t, d) in B_op:
        pool = [x for x in alerts_by_day.get(d, ()) if x in daily_full]
        c, n = comp_for(t, d, pool)
        resB.append(dict(t=t, d=d, comp=c, featured=n, alerts=len(alerts_by_day.get(d, ())),
                         in_alerts=t in alerts_by_day.get(d, ())))
    rankB = [r for r in resB if r["comp"] is not None and r["featured"] >= 2]
    topB_le = sum(1 for r in rankB if r["comp"] <= 0.5 + 1e-12)
    topB_lt = sum(1 for r in rankB if r["comp"] < 0.5 - 1e-12)
    # B2 reported separately
    resB2 = []
    for (t, d) in B2:
        pool = [x for x in alerts_by_day.get(d, ()) if x in daily_full]
        c, n = comp_for(t, d, pool)
        resB2.append(dict(t=t, d=d, comp=c, featured=n, alerts=len(alerts_by_day.get(d, ()))))
    # (iii) C
    for r in crow:
        c, n = comp_for(r["tk"], r["date"], [x["tk"] for x in cpool[r["date"]]])
        r["v2"] = c if (c is not None and n >= 2) else (0.5 if c is not None else None)
        r["v2_pool"] = n
    iii = {}
    for tag, mat, xk in (("5d", 6, "x5"), ("20d", 21, "x20")):
        pop = [r for r in crow if r["sess"] >= mat and r[xk] is not None]

        def cohort(key, top=True):
            c = [r for r in pop if r[key] is not None and ((r[key] <= 0.25 + 1e-9) == top)]
            return CohortRead(len(c), sum(1 for r in c if r[xk] >= 8.0), sum(1 for r in c if r["loser"])), c
        v2t, v2tc = cohort("v2")
        v2r, _ = cohort("v2", False)
        oldt, _ = cohort("c_eod")
        old945, _ = cohort("c_945")
        pass_iii = (v2t.winners_admitted > oldt.winners_admitted and v2t.n > 0 and oldt.n > 0
                    and v2t.losers_admitted / v2t.n <= oldt.losers_admitted / oldt.n)
        iii[tag] = dict(pop=len(pop), v2top=v2t, v2rest=v2r, oldtop=oldt, old945top=old945,
                        v2_vs_old=score_both_directions(v2t, oldt),
                        v2_vs_rest=score_both_directions(v2t, v2r), pass_=pass_iii,
                        v2top_names=[(r["tk"], r["date"], round(r[xk], 2)) for r in v2tc])
    ok_i = a_i is not None and a_i >= 0.70
    ok_ii = bool(rankB) and topB_le / len(rankB) >= 0.80
    ok_ii_strict = bool(rankB) and topB_lt / len(rankB) >= 0.80
    ok_iii = iii["5d"]["pass_"] and iii["20d"]["pass_"]
    return dict(label=label, scores=scores, qual=qual, a_i=a_i, nA_rank=(len(ys), len(ns)), resA=resA,
                resB=resB, rankB=len(rankB), topB_le=topB_le, topB_lt=topB_lt, resB2=resB2, iii=iii,
                ok=(ok_i, ok_ii, ok_iii), ok_ii_strict=ok_ii_strict, cache=cache)


def show(R, full=True):
    P("-" * 96)
    P(f"[{R['label']}]")
    P("  feature A scores (P(yes ranks above no), ties half; max of the two directions):")
    for ft, (s, dirn, ny, nn) in R["scores"].items():
        tag = "  <- composite-eligible" if ft in COMPOSITE_ELIGIBLE else ""
        P(f"    {ft:20s} {('%.3f' % s) if s is not None else 'NA':>6s} {dirn or '':9s} n yes/no={ny}/{nn}{tag}")
    P(f"  qualifying (>=0.65): {R['qual']}")
    ai = R["a_i"]
    P(f"  (i)  composite on A (rankable: featured pool>=2): {('%.3f' % ai) if ai is not None else 'NA'} "
      f"n yes/no={R['nA_rank'][0]}/{R['nA_rank'][1]}  bar 0.70 -> {'PASS' if R['ok'][0] else 'FAIL'}")
    P(f"  (ii) his labelled EPs ranked (featured pool>=2): {R['rankB']}; top half (<=0.5): {R['topB_le']}; "
      f"strictly above middle (<0.5): {R['topB_lt']}  bar 80% -> inclusive {'PASS' if R['ok'][1] else 'FAIL'} / strict {'PASS' if R['ok_ii_strict'] else 'FAIL'}")
    if full:
        for r in R["resB"]:
            P(f"       {r['t']:5s} {r['d']} comp={('%.3f' % r['comp']) if r['comp'] is not None else 'NA':>5s} "
              f"featured={r['featured']} alerts_that_day={r['alerts']} pair_is_an_alert={r['in_alerts']}")
    for tag in ("5d", "20d"):
        x = R["iii"][tag]
        P(f"  (iii) {tag}: pop={x['pop']} v2 top={x['v2top']} | old EOD top={x['oldtop']} | old 09:45 top={x['old945top']}")
        P(f"         v2-top vs old-top: {x['v2_vs_old']}  -> prereg (more winners, loser rate no higher): "
          f"{'PASS' if x['pass_'] else 'FAIL'}")
        P(f"         v2-top vs v2-rest: {x['v2_vs_rest']}")
        if full:
            P(f"         v2 top-quartile members: {x['v2top_names']}")
    P(f"  VERDICT: (i) {R['ok'][0]} (ii) {R['ok'][1]} (iii) {R['ok'][2]} -> "
      f"{'PASS' if all(R['ok']) else ('HIS EYE, NOT THE TAIL' if R['ok'][0] and R['ok'][1] else 'FAIL')}")


# ───────────────────────── main run ─────────────────────────
BASE = dict(five_year=True, ADRK=1.0, VOLW=252, SW=40, BASE_END=250)
R0 = run(BASE, "PRIMARY (as pre-registered)")
show(R0)

# feature cross-checks
cache = R0["cache"]
allpairs = sorted({(r["ticker"], r["date"]) for r in pairs if r["source"] in "ABC"})
for k in allpairs:
    if k not in cache:
        cache[k] = features(*k, **BASE)
shared = [f for f in cache.values() if f.get("tightness_eod_shadow") is not None]
match = sum(1 for f in shared if abs(f["tightness_eod_shadow"] - f["tightness_eod_bars"]) < 1e-6)
P("-" * 96)
P(f"tightness EOD bars vs shadow (all featured (t,d) with a shadow row): {match}/{len(shared)} match")
pf = [cache[k] for k in allpairs]
P(f"pair features computed: {len(pf)}; errors: {sorted((f['ticker'], f['date'], f['err']) for f in pf if 'err' in f)}")
for ft in ("zones_cleared", "zones_remaining", "cleared_ath", "vol_highest_ever", "tightness_eod",
           "vol_ratio_252", "pullbacks_held", "tightness_asof0945"):
    nulls = [f"{f['ticker']} {f['date']}" for f in pf if "err" not in f and f.get(ft) is None]
    P(f"  NULL {ft:20s}: {len(nulls)}")
P(f"  pairs with < 2 swing lows: {[(f['ticker'], f['date'], f.get('n_swing_lows')) for f in pf if f.get('n_swing_lows') is not None and f['n_swing_lows'] < 2]}")

# A-pair rankability breakdown
P("-" * 96)
P("A yes/no rankability (primary):")
cnt = defaultdict(int)
for r in R0["resA"]:
    if r["alerts"] == 0:
        cnt["day has no alerts"] += 1
    elif r["featured"] < 2 and r["alerts"] >= 2:
        cnt["day had alerts but only the pair has bars"] += 1
    elif r["featured"] < 2:
        cnt["one-alert day"] += 1
    else:
        cnt["rankable"] += 1
P("  " + json.dumps(dict(cnt)))
P("  no-alert-day pairs: " + str([(r["t"], r["d"]) for r in R0["resA"] if r["alerts"] == 0]))

# B2 separately
P("-" * 96)
P("B2 (R-picked evidence rows, NOT his labels) under the primary composite:")
rb2 = [r for r in R0["resB2"] if r["comp"] is not None and r["featured"] >= 2]
P(f"  rankable {len(rb2)} of {len(R0['resB2'])}; top half {sum(1 for r in rb2 if r['comp'] <= 0.5)}; "
  f"no-alert-day {sum(1 for r in R0['resB2'] if r['alerts'] == 0)}")

# ───────────────────────── variants ─────────────────────────
P("=" * 96)
P("VARIANTS")
show(run(BASE, "FORCED: zones_cleared + tightness_eod (his 'keep tightness')",
         forced=["zones_cleared", "tightness_eod"]))
R945 = run(BASE, "LETTER: every feature-4 column eligible (adds tightness_asof0945)", eligible=LETTER_ELIGIBLE)
show(R945)
show(run(BASE, "zones_cleared + tightness_asof0945 + tightness_eod",
         forced=["zones_cleared", "tightness_asof0945", "tightness_eod"]), full=False)
show(run(dict(BASE, five_year=False), "FULL HISTORY (no 5-year trim)"), full=False)

Rc = run(BASE, "NULL CHECK: a constant ranking (every member 0.5) on bar (ii)", const=True)
P("-" * 96)
P(f"NULL CHECK (ii): a ranking that knows nothing puts {Rc['topB_le']}/{Rc['rankB']} of his EPs at <=0.5 "
  f"(inclusive reading) and {Rc['topB_lt']}/{Rc['rankB']} at <0.5 (strict reading)")
show(run(BASE, "pullbacks scored CONTINUOUS (min distance) instead of the binary held flag",
         eligible=["zones_cleared", "vol_ratio_252", "pb_min_dist_adr", "tightness_eod"]), full=False)
# pullbacks scored continuous instead of binary (definitional sensitivity)
P("-" * 96)
P(f"pullbacks continuous (pb_min_dist_adr) A score: {R0['scores']['pb_min_dist_adr']}")

# ───────────────────────── plateau ─────────────────────────
P("=" * 96)
P("PLATEAU (+-50% on 1 ADR, 252 sessions, 40 / 41-250 windows)")
plateau = []
for name, cfg in [
    ("ADR 0.5", dict(BASE, ADRK=0.5)), ("ADR 1.5", dict(BASE, ADRK=1.5)),
    ("VOL 126", dict(BASE, VOLW=126)), ("VOL 378", dict(BASE, VOLW=378)),
    ("SW 20 / base 21-250", dict(BASE, SW=20)), ("SW 60 / base 61-250", dict(BASE, SW=60)),
    ("base end 125", dict(BASE, BASE_END=125)), ("base end 375", dict(BASE, BASE_END=375)),
]:
    R = run(cfg, name)
    s = R["scores"]
    line = (f"  {name:22s} zones={s['zones_cleared'][0]:.3f} vol={s['vol_ratio_252'][0]:.3f}({s['vol_ratio_252'][2]}/{s['vol_ratio_252'][3]}) "
            f"pb={s['pullbacks_held'][0]:.3f}({s['pullbacks_held'][2]}/{s['pullbacks_held'][3]}) pbcont={s['pb_min_dist_adr'][0]:.3f} qual={R['qual']} "
            f"(i)={R['a_i']:.3f} (ii)={R['topB_le']}(<{R['topB_lt']})/{R['rankB']} (iii)5d={R['iii']['5d']['pass_']} 20d={R['iii']['20d']['pass_']} "
            f"-> {'PASS' if all(R['ok']) else 'FAIL'}")
    P(line)
    plateau.append(line)

# ───────────────────────── 25-pair sample ─────────────────────────
P("=" * 96)
yes_keys = sorted(yesA)
rest = sorted(k for k in allpairs if k not in yesA)
rng = random.Random(1103)
samp = yes_keys + sorted(rng.sample(rest, 8))
P(f"SAMPLE: 17 A-yes + random.Random(1103).sample(sorted(rest of {len(rest)} distinct pairs), 8) = {len(samp)}")
with open(OUT / "verify_features.tsv", "w") as f:
    cols = ["ticker", "date", "history", "zones_cleared", "zones_remaining", "cleared_ath", "vol_ratio_252",
            "vol_highest_ever", "tightness_eod", "tightness_asof0945", "pullbacks_held", "pb_min_dist_adr",
            "n_swing_lows", "base_high", "pb_lows", "err"]
    f.write("\t".join(cols + ["in_sample"]) + "\n")
    for k in allpairs:
        r = cache[k]
        f.write("\t".join(str(r.get(c, "")) for c in cols) + "\t" + str(int(k in samp)) + "\n")
P("sample keys: " + ", ".join(f"{t} {d}" for t, d in samp))

(OUT / "verify_v2.txt").write_text("\n".join(LOG) + "\n")
