#!/usr/bin/env python3
"""EP ALERT RANKING v2 — the pre-registered test, run as written.

Pre-registration: docs/analysis/ep_rank_v2_prereg_2026-11-03.md (fixed before any data was read).
Research only: $0, local files only, no network, no prod reads, nothing wired anywhere (THE LINE:
selection is his call). Data: ../pairs.tsv, ../bars.csv.gz, ../shadow_rows.csv, ../ep_alerts.csv,
../../_rank_shadow_running_read_1103/rows.psv (C's outcomes).

READINGS (decided before any outcome or label was scored; written here so they cannot drift):
 R1  "4 features" = one composite-eligible term per feature: zones_cleared (F1), vol_ratio_252 (F2),
     pullbacks_held (F3), tightness_eod (F4). The other named measures (zones_remaining, cleared_ath,
     vol_highest_ever, tightness_asof0945) are scored on A as SUB-READS and are NOT composite-eligible.
 R2  Feature 1 = the fixture-gated encoder's own preopen pass, CALLED unchanged
     (_533_nbis_structure_encoder.encode(..., preopen=True)), the same three fields the supply-ladder
     probe reads: n_cleared, n_uncleared, cls.startswith('BLUE_SKY'). Daily bars sliced to the 5
     calendar years before D (data starts 2021-09-27, so most names have ~4.5-5y).
 R3  Feature 3 swing low = a local min over +-2 sessions (mirror of the encoder's PIVOT_WING pivot
     high), pivot inside the 40 sessions before D, both wings inside bars < D. "The 2 lowest swing
     lows" = the two lowest-priced. Base high = max high of sessions 41..250 before D (index ia-250 ..
     ia-41). "Held = both within 1 ADR above it or above it" is read as: each low >= base_high x
     (1 - 1.0 x ADR20%/100) — within 1 ADR of the old base high, or above it. ADR20 = the encoder's
     adr20_pct (shared with F1). NULL when < 2 swing lows or the base window is not fully in history.
 R4  vol_ratio_252 = gap-day volume / max volume of the 252 sessions before D; NULL when fewer than
     252 prior sessions exist (the window is not shrunk silently). vol_highest_ever = gap-day volume
     > every prior day in the 5-year slice (available history; flagged when < 5y).
 R5  Tightness EOD = (h-l)/h*100 on D from bars (the shadow's compute_tightness_pct); as-of-09:45
     only where shadow_rows has it.
 R6  A feature qualifies if max(auc, 1-auc) >= 0.65 on A, direction = the side A favours.
 R7  Composite orientation = the old composite's: per-feature _pct_rank ascending (the shadow's own
     function, copied), flipped (1-rank) where A says higher raw = yes, mean; LOW = GOOD; top quartile
     = composite <= 0.25; "top half" = composite < 0.5 (strict; exact-0.5 counted separately).
     NULL on any included feature -> the item leaves the day's pool (rank_day_pool's all-or-nothing).
 R8  Day pool = that day's ep_alerts tickers (deduped) + the pair itself when it was not an alert
     (inserted alone; non-alert pairs never enter each other's pools), restricted to tickers with
     bars. bars.csv.gz holds only the 140 pair tickers, so A/B pools are PARTIAL — always reported as
     alerts-that-day vs featured-here. A pool of one -> 0.5, unrankable.
 R9  Bar (iii): candidate = v2's top quartile, baseline = the OLD composite's top quartile, same
     matured rows, score_both_directions(candidate, baseline). PASS = more tail winners AND loser
     rate no higher (the pre-reg's parenthetical), each horizon (5 and 20 sessions) separately.
"""
from __future__ import annotations

import bisect
import csv
import gzip
import importlib.util
import random
import statistics as st
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE.parent
REPO = Path("/Users/alvinfung/apollo_the_wise")
RR = REPO / "scripts/probes/_rank_shadow_running_read_1103/rows.psv"

sys.path.insert(0, str(REPO))
from scripts.alert_rank_shadow_running_read import (  # noqa: E402
    CohortRead, score_both_directions, render_running_read, confidence_label)

_spec = importlib.util.spec_from_file_location(
    "nbis", REPO / "scripts/probes/_533_nbis_structure_encoder.py")
nbis = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(nbis)

TOL = 1e-9
QUAL = 0.65
BAR_I = 0.70
BAR_II = 0.80
TAIL = 8.0
STATED = dict(adr_mult=1.0, vol_win=252, pb_win=40, base_end=250)
PRIMARY = ["zones_cleared", "vol_ratio", "held", "tight_eod"]
SUBREADS = ["zones_remaining", "cleared_ath", "vol_highest_ever", "tight_0945"]
YES = {"GOOD_CHART", "OKISH_CHART"}
NO = {"BAD_CHART"}

OUT = []


def P(*a):
    s = " ".join(str(x) for x in a)
    print(s)
    OUT.append(s)


def pdate(s):
    y, m, d = (int(x) for x in s.split("-"))
    return date(y, m, d)


def five_years_before(d: date) -> str:
    try:
        return d.replace(year=d.year - 5).isoformat()
    except ValueError:          # Feb 29
        return d.replace(year=d.year - 5, day=28).isoformat()


# ── load ────────────────────────────────────────────────────────────────────────────────
daily: dict[str, list] = defaultdict(list)
with gzip.open(DATA / "bars.csv.gz", "rt") as f:
    for r in csv.DictReader(f):
        try:
            o, h, l, c = (float(r[k]) for k in ("open_price", "high_price", "low_price", "close"))
        except (TypeError, ValueError):
            continue
        if c <= 0 or h <= 0:
            continue
        v = float(r["volume"]) if r["volume"] not in ("", None) else 0.0
        daily[r["ticker"]].append((r["trade_date"], o, h, l, c, v))
for t in daily:
    daily[t].sort()
BAR_TICKERS = set(daily)
IDX = {t: {row[0]: i for i, row in enumerate(rows)} for t, rows in daily.items()}

pairs = list(csv.DictReader(open(DATA / "pairs.tsv"), delimiter="\t"))

alert_pool: dict[str, set] = defaultdict(set)
for r in csv.DictReader(open(DATA / "ep_alerts.csv")):
    alert_pool[r["alert_date"]].add(r["ticker"])
ALERT_MIN = min(alert_pool)

shadow: dict[tuple, dict] = {}
shadow_dups = 0
for r in csv.DictReader(open(DATA / "shadow_rows.csv")):
    k = (r["ticker"], r["alert_date"])
    if k in shadow:
        shadow_dups += 1
        continue
    shadow[k] = r

F = lambda s: None if s in ("", None) else float(s)  # noqa: E731
rows_c = []
for r in csv.reader(open(RR), delimiter="|"):      # score.py's own row load, verbatim
    rows_c.append(dict(
        tk=r[0], date=r[1], adr=F(r[2]), high=r[3] == "t", filled=r[4] == "t", tier=r[5],
        c_eod=F(r[6]), pool_eod=int(r[7]), c_945=F(r[8]), pool_945=int(r[9]),
        open0=F(r[10]), low0=F(r[11]), sess=int(r[12]),
        mh5=F(r[13]), mh20=F(r[14]), r5=F(r[15]), r20=F(r[16]), minlow=F(r[17])))


def adrx(v, adr):
    return None if (v is None or not adr) else v / adr


for r in rows_c:
    r["x5"], r["x20"] = adrx(r["mh5"], r["adr"]), adrx(r["mh20"], r["adr"])
    r["loser"] = (r["minlow"] is not None and r["low0"] is not None and r["minlow"] < r["low0"])


# ── features ────────────────────────────────────────────────────────────────────────────
_enc_cache: dict = {}


def slice5(t, d):
    rows = daily.get(t)
    if not rows or d not in IDX[t]:
        return None, None
    ia_full = IDX[t][d]
    lo = bisect.bisect_left([x[0] for x in rows], five_years_before(pdate(d)))
    sl = rows[lo:ia_full + 1]
    return sl, len(sl) - 1


def encode1(t, d):
    k = (t, d)
    if k not in _enc_cache:
        sl, ia = slice5(t, d)
        if sl is None:
            _enc_cache[k] = ({"error": "no_bar_on_D" if t in BAR_TICKERS else "no_bars_for_ticker"}, None, None)
        else:
            _enc_cache[k] = (nbis.encode(t, d, {t: sl}, {}, preopen=True), sl, ia)
    return _enc_cache[k]


def swing_lows(days, ia, win):
    w = nbis.PIVOT_WING
    lows = [x[3] for x in days[:ia]]
    out = []
    for i in range(max(w, ia - win), ia - w):
        if lows[i] <= min(lows[i - w:i]) and lows[i] < min(lows[i + 1:i + 1 + w]):
            out.append(lows[i])
    return out


_feat_cache: dict = {}


def features(t, d, prm=STATED):
    key = (t, d, tuple(sorted(prm.items())))
    if key in _feat_cache:
        return _feat_cache[key]
    enc, days, ia = encode1(t, d)
    f = {k: None for k in PRIMARY + SUBREADS}
    f.update(null=[], cls=None, adr20=None, history5y=None, base_high=None, pb_low1_adr=None,
             pb_low2_adr=None, n_swing_lows=None, short5y=None)
    if enc.get("error"):
        f["null"].append(f"F1-3:{enc['error']}")
        _feat_cache[key] = f
        return f
    f["cls"] = enc["cls"]
    f["history5y"] = ia
    f["short5y"] = ia < 1200
    # F1 — the supply-ladder fields, as _533_supply_ladder_probe.py reads them
    f["zones_cleared"] = enc["n_cleared"]
    f["zones_remaining"] = enc["n_uncleared"]
    f["cleared_ath"] = 1 if enc["cls"].startswith("BLUE_SKY") else 0
    adr = nbis.adr20_pct(days, ia)
    f["adr20"] = adr
    # F2 — volume against its own history
    v0 = days[ia][5]
    W = prm["vol_win"]
    if not v0:
        f["null"].append("F2:no_volume_on_D")
    else:
        if ia >= W:
            mx = max(x[5] for x in days[ia - W:ia])
            f["vol_ratio"] = v0 / mx if mx > 0 else None
            if mx <= 0:
                f["null"].append("F2:zero_prior_volume")
        else:
            f["null"].append(f"F2:history<{W}({ia})")
        f["vol_highest_ever"] = 1 if v0 > max(x[5] for x in days[:ia]) else 0
    # F3 — pullbacks held an old base high
    pw, be = prm["pb_win"], prm["base_end"]
    if ia < be:
        f["null"].append(f"F3:history<{be}({ia})")
    elif not adr:
        f["null"].append("F3:no_adr")
    else:
        sls = sorted(swing_lows(days, ia, pw))
        f["n_swing_lows"] = len(sls)
        base_high = max(x[2] for x in days[ia - be:ia - pw])
        f["base_high"] = base_high
        if len(sls) < 2:
            f["null"].append(f"F3:swing_lows={len(sls)}")
        else:
            d1, d2 = ((s / base_high - 1) * 100 / adr for s in sls[:2])
            f["pb_low1_adr"], f["pb_low2_adr"] = d1, d2
            f["held"] = 1 if (d1 >= -prm["adr_mult"] and d2 >= -prm["adr_mult"]) else 0
    # F4 — tightness
    h, l = days[ia][2], days[ia][3]
    f["tight_eod"] = (h - l) / h * 100.0 if h > 0 else None
    s = shadow.get((t, d))
    f["tight_0945"] = F(s["tightness_pct_asof0945"]) if s else None
    _feat_cache[key] = f
    return f


# ── scoring helpers ─────────────────────────────────────────────────────────────────────
def auc(yes_vals, no_vals):
    """P(yes > no) + 0.5 P(tie) — 'the chance a yes ranks above a no'."""
    if not yes_vals or not no_vals:
        return None
    s = 0.0
    for a in yes_vals:
        for b in no_vals:
            s += 1.0 if a > b else (0.5 if a == b else 0.0)
    return s / (len(yes_vals) * len(no_vals))


def boot_ci(yes_vals, no_vals, n=2000, seed=20261103):
    rng = random.Random(seed)
    if len(yes_vals) < 2 or len(no_vals) < 2:
        return None
    xs = []
    for _ in range(n):
        y = [rng.choice(yes_vals) for _ in yes_vals]
        z = [rng.choice(no_vals) for _ in no_vals]
        xs.append(auc(y, z))
    xs.sort()
    return xs[int(0.05 * n)], xs[int(0.95 * n)]


def _pct_rank(sorted_vals, v):
    """agents/market_intelligence/alert_rank_shadow.py::_pct_rank, copied verbatim."""
    lo = bisect.bisect_left(sorted_vals, v)
    hi = bisect.bisect_right(sorted_vals, v)
    return (lo + (hi - lo) / 2) / len(sorted_vals)


A = [p for p in pairs if p["source"] == "A"]
B_his = [p for p in pairs if p["source"] == "B" and p["label"] == "operator"]
B2 = [p for p in pairs if p["source"] == "B" and p["label"] != "operator"]
C = [p for p in pairs if p["source"] == "C"]
A_yes = [p for p in A if p["label"] in YES]
A_no = [p for p in A if p["label"] in NO]
A_excl = [p for p in A if p["label"] not in YES | NO]


def score_A(prm):
    res = {}
    for k in PRIMARY + SUBREADS:
        yv = [features(p["ticker"], p["date"], prm)[k] for p in A_yes]
        nv = [features(p["ticker"], p["date"], prm)[k] for p in A_no]
        yv = [x for x in yv if x is not None]
        nv = [x for x in nv if x is not None]
        a = auc(yv, nv)
        res[k] = dict(auc=a, ny=len(yv), nn=len(nv),
                      score=(None if a is None else max(a, 1 - a)),
                      direction=(None if a is None else ("higher=yes" if a >= 0.5 else "lower=yes")))
    return res


def context(p):
    """(pool tickers for this pair's ranking, alerts that day, pair_in_alerts)."""
    d, t = p["date"], p["ticker"]
    al = alert_pool.get(d, set())
    pool = set(al) | {t}
    return pool, len(al), t in al


def rank_pair(p, included, prm):
    """Within-day composite for pair p. Returns dict(comp, featured, pool_alerts, status)."""
    d, t = p["date"], p["ticker"]
    pool, n_alerts, in_al = context(p)
    with_bars = sorted(x for x in pool if x in BAR_TICKERS)
    feats = {x: features(x, d, prm) for x in with_bars}
    me = feats.get(t) or features(t, d, prm)
    out = dict(pool_alerts=n_alerts, in_alerts=in_al, with_bars=len(with_bars),
               comp=None, featured=0, status=None, ranks={})
    if not included:
        out["status"] = "no_feature_qualified"
        return out
    if any(me[k] is None for k, _ in included):
        out["status"] = "NULL_feature:" + ",".join(k for k, _ in included if me[k] is None)
        return out
    q = [x for x in with_bars if all(feats[x][k] is not None for k, _ in included)]
    out["featured"] = len(q)
    ranks = []
    for k, direction in included:
        vals = sorted(feats[x][k] for x in q)
        r = _pct_rank(vals, me[k])
        if direction == "higher=yes":
            r = 1.0 - r
        out["ranks"][k] = r
        ranks.append(r)
    out["comp"] = sum(ranks) / len(ranks)
    if n_alerts == 0:
        out["status"] = f"unrankable:no_alerts_in_ep_alerts_that_day(file starts {ALERT_MIN})" \
            if d < ALERT_MIN else "unrankable:no_alerts_that_day"
    elif len(q) == 1 and n_alerts + (0 if in_al else 1) == 1:
        out["status"] = "unrankable:one_alert_day"
    elif len(q) == 1 and len(with_bars) == 1:
        out["status"] = f"unrankable:bars_gap({n_alerts}_alerts,1_featured)"
    elif len(q) == 1:
        out["status"] = f"unrankable:null_feature_gap({len(with_bars)}_with_bars,1_featured)"
    else:
        out["status"] = "rankable"
    return out


def run(prm, label, verbose):
    sa = score_A(prm)
    included = [(k, sa[k]["direction"]) for k in PRIMARY
                if sa[k]["score"] is not None and sa[k]["score"] >= QUAL - TOL]
    res = dict(label=label, sa=sa, included=included)
    ranked = {}
    for p in pairs:
        ranked[(p["ticker"], p["date"], p["source"])] = rank_pair(p, included, prm)
    res["ranked"] = ranked
    # bar (i)
    def comps(group, only_rankable):
        out = []
        for p in group:
            rk = ranked[(p["ticker"], p["date"], "A")]
            if rk["comp"] is None:
                continue
            if only_rankable and rk["status"] != "rankable":
                continue
            out.append(rk["comp"])
        return out
    # low composite = good, so the chance a yes ranks above a no = P(c_yes < c_no) + .5 ties
    def auc_low(y, n):
        a = auc([-x for x in y], [-x for x in n])
        return a
    yl, nl = comps(A_yes, False), comps(A_no, False)
    yr, nr = comps(A_yes, True), comps(A_no, True)
    res["i_all"] = (auc_low(yl, nl), len(yl), len(nl))
    res["i_rank"] = (auc_low(yr, nr), len(yr), len(nr))
    # bar (ii)
    b = []
    for p in B_his:
        rk = ranked[(p["ticker"], p["date"], "B")]
        b.append((p, rk))
    elig = [(p, rk) for p, rk in b if rk["status"] == "rankable"]
    top = [x for x in elig if x[1]["comp"] < 0.5 - TOL]
    mid = [x for x in elig if abs(x[1]["comp"] - 0.5) <= TOL]
    res["ii"] = dict(b=b, elig=len(elig), top=len(top), mid=len(mid),
                     share=(len(top) / len(elig) if elig else None))
    # bar (iii)
    v2c = {}
    for p in C:
        v2c[(p["ticker"], p["date"])] = ranked[(p["ticker"], p["date"], "C")]
    iii = {}
    for tag, matured, xkey in (("5d", 6, "x5"), ("20d", 21, "x20")):
        pop = [r for r in rows_c if r["sess"] >= matured and r[xkey] is not None]
        for oldkey in ("c_eod", "c_945"):
            vt = [r for r in pop if v2c[(r["tk"], r["date"])]["comp"] is not None
                  and v2c[(r["tk"], r["date"])]["comp"] <= 0.25 + TOL]
            ot = [r for r in pop if r[oldkey] is not None and r[oldkey] <= 0.25 + TOL]
            cand = CohortRead(len(vt), sum(1 for r in vt if r[xkey] >= TAIL), sum(1 for r in vt if r["loser"]))
            base = CohortRead(len(ot), sum(1 for r in ot if r[xkey] >= TAIL), sum(1 for r in ot if r["loser"]))
            verdict = score_both_directions(cand, base)
            passed = (cand.n > 0 and base.n > 0 and cand.winners_admitted > base.winners_admitted
                      and cand.losers_admitted / cand.n <= base.losers_admitted / base.n + TOL)
            # v2's own top-vs-rest (running-read shape)
            vrest = [r for r in pop if r not in vt]
            own = score_both_directions(
                cand, CohortRead(len(vrest), sum(1 for r in vrest if r[xkey] >= TAIL),
                                 sum(1 for r in vrest if r["loser"])))
            iii[(tag, oldkey)] = dict(pop=len(pop), cand=cand, base=base, verdict=verdict,
                                      passed=passed, own=own, vt=vt, ot=ot,
                                      tails=[r for r in pop if r[xkey] >= TAIL])
    res["iii"] = iii
    res["c_null"] = sum(1 for v in v2c.values() if v["comp"] is None)
    return res


def fmt(x, n=3):
    return "NULL" if x is None else (f"{x:.{n}f}" if isinstance(x, float) else str(x))


# ════════════════════════════════════════════════════════════════════════════════════════
P("=" * 100)
P("EP RANKING v2 — the pre-registered test (docs/analysis/ep_rank_v2_prereg_2026-11-03.md)")
P("=" * 100)
P("READINGS" + __doc__.split("READINGS")[1].rstrip())

# ── data sanity ──
P("\n[0] DATA")
P(f"  pairs: {len(pairs)} (A {len(A)} · B his {len(B_his)} · B2 R-picked {len(B2)} · C {len(C)})")
P(f"  A labels: yes (GOOD/OKISH) {len(A_yes)} · no (BAD) {len(A_no)} · other verdicts excluded "
  f"{len(A_excl)}: " + ", ".join(sorted({p['label'] for p in A_excl})) +
  " — " + " ".join(f"{p['ticker']} {p['date']} {p['label']}" for p in A_excl))
P(f"  bars: {len(BAR_TICKERS)} tickers, {sum(len(v) for v in daily.values())} rows; "
  f"ep_alerts: {sum(len(v) for v in alert_pool.values())} distinct (date,ticker) over "
  f"{len(alert_pool)} days, first {ALERT_MIN} (the task text said 2026-03-01 — the file starts later)")
P(f"  shadow_rows: {len(shadow)} distinct (ticker,date) ({shadow_dups} duplicate rows dropped, first kept)")
mm, nb = 0, 0
for (t, d), s in shadow.items():
    tb = F(s["tightness_pct_eod"])
    if t in IDX and d in IDX[t] and tb is not None:
        nb += 1
        _, o, h, l, c, v = daily[t][IDX[t][d]]
        if abs((h - l) / h * 100 - tb) > 0.01:
            mm += 1
P(f"  tightness cross-check: bars (h-l)/h*100 vs shadow tightness_pct_eod on {nb} shared rows -> "
  f"{mm} differ by > 0.01pp")

# ── step 1: coverage ──
P("\n[1] FEATURE COVERAGE (stated thresholds) — every pair")
nulls = defaultdict(lambda: defaultdict(list))
for p in pairs:
    f = features(p["ticker"], p["date"])
    grp = p["source"] if p["source"] != "B" else ("B" if p["label"] == "operator" else "B2")
    for k in PRIMARY + SUBREADS:
        if f[k] is None:
            if k == "tight_0945":
                why = "not_a_shadow_row" if (p["ticker"], p["date"]) not in shadow else "shadow_null"
            else:
                why = ";".join(f["null"]) or "?"
            nulls[k][grp].append(f"{p['ticker']} {p['date']} ({why})")
for k in PRIMARY + SUBREADS:
    tag = "PRIMARY" if k in PRIMARY else "sub-read"
    tot = sum(len(v) for v in nulls[k].values())
    P(f"  {k:<17} [{tag}] NULL {tot}/{len(pairs)}" +
      ("" if not tot else " — " + " | ".join(f"{g}: {len(v)}" for g, v in sorted(nulls[k].items()))))
    for g, v in sorted(nulls[k].items()):
        if k != "tight_0945":
            P(f"      {g}: " + "; ".join(v))
P("  tight_0945 is NULL wherever the pair is not a shadow row (most A, all B2 pre-05-11) — by design.")
h5 = [features(p["ticker"], p["date"])["history5y"] for p in pairs]
h5 = [x for x in h5 if x is not None]
P(f"  5-year window: bars.csv.gz starts 2021-09-27, so every D before 2026-09-27 gets a window cut short by"
  f" the FILE ({sum(1 for x in h5 if x < 1200)} pairs < 1200 sessions); genuinely short listing history"
  f" (< 1000 sessions) = {sum(1 for x in h5 if x < 1000)} pairs, < 252 = {sum(1 for x in h5 if x < 252)}"
  f" (those are the F2/F3 NULLs above). cleared_ath / vol_highest_ever = 'above every bar in the window'.")

# ── step 2+3: the stated run ──
S = run(STATED, "stated", True)
P("\n[2] POPULATION A — each feature's chance a yes (GOOD/OKISH) ranks above a no (BAD); 0.5 = nothing")
P(f"  {'feature':<17} {'role':<9} {'P(yes>no)':>9} {'score':>6} {'direction':<11} {'n yes/no':>9}  90% boot CI (P(yes>no))")
for k in PRIMARY + SUBREADS:
    r = S["sa"][k]
    yv = [features(p["ticker"], p["date"])[k] for p in A_yes]
    nv = [features(p["ticker"], p["date"])[k] for p in A_no]
    ci = boot_ci([x for x in yv if x is not None], [x for x in nv if x is not None])
    flag = ""
    if r["score"] is not None and r["score"] >= QUAL - TOL:
        flag = "  QUALIFIES" if k in PRIMARY else "  (>=0.65 but sub-read: not composite-eligible by R1)"
    P(f"  {k:<17} {'PRIMARY' if k in PRIMARY else 'sub-read':<9} {fmt(r['auc']):>9} {fmt(r['score']):>6} "
      f"{(r['direction'] or ''):<11} {r['ny']:>4}/{r['nn']:<4}  "
      f"{'' if ci is None else f'[{ci[0]:.2f}, {ci[1]:.2f}]'}{flag}")
P("  descriptive (not eligible): F3's continuous lows — lower of the two pullback lows vs the base high, in ADR:")
yv = [min(f["pb_low1_adr"], f["pb_low2_adr"]) for f in (features(p["ticker"], p["date"]) for p in A_yes) if f["pb_low1_adr"] is not None]
nv = [min(f["pb_low1_adr"], f["pb_low2_adr"]) for f in (features(p["ticker"], p["date"]) for p in A_no) if f["pb_low1_adr"] is not None]
P(f"      yes median {fmt(st.median(yv) if yv else None,2)} ADR (n={len(yv)}) · no median "
  f"{fmt(st.median(nv) if nv else None,2)} ADR (n={len(nv)}) · P(yes>no)={fmt(auc(yv, nv))}")
P("\n  per-pair values (A):")
P(f"    {'ticker':<6} {'date':<10} {'label':<12} {'zc':>3} {'zr':>3} {'ath':>3} {'vol_r':>6} {'vhe':>3} "
  f"{'held':>4} {'low1':>6} {'low2':>6} {'t_eod':>6} {'t_945':>6}  cls")
for p in sorted(A, key=lambda p: (p["label"] not in YES, p["label"], p["date"])):
    f = features(p["ticker"], p["date"])
    P(f"    {p['ticker']:<6} {p['date']:<10} {p['label']:<12} {fmt(f['zones_cleared']):>3} "
      f"{fmt(f['zones_remaining']):>3} {fmt(f['cleared_ath']):>3} {fmt(f['vol_ratio'],2):>6} "
      f"{fmt(f['vol_highest_ever']):>3} {fmt(f['held']):>4} {fmt(f['pb_low1_adr'],1):>6} "
      f"{fmt(f['pb_low2_adr'],1):>6} {fmt(f['tight_eod'],1):>6} {fmt(f['tight_0945'],1):>6}  {f['cls']}")

P("\n[3] THE v2 COMPOSITE")
if S["included"]:
    P("  included (score >= 0.65 on A): " + ", ".join(f"{k} ({d})" for k, d in S["included"]))
else:
    P("  NO PRIMARY FEATURE scores >= 0.65 on A -> the composite is EMPTY. That is the result; bars (i)-(iii)")
    P("  cannot be computed on an empty composite.")


def pool_line(p, rk):
    return (f"alerts that day {rk['pool_alerts']}{'' if rk['in_alerts'] else ' (+ this pair, not an alert)'}"
            f" · with bars {rk['with_bars']} · featured {rk['featured']} · status {rk['status']}")


def report_bars(R, verbose=True):
    if not R["included"]:
        return
    a_all, ny, nn = R["i_all"]
    a_r, nyr, nnr = R["i_rank"]
    P(f"\n  BAR (i) — composite on A, chance a yes ranks above a no (needs >= {BAR_I})")
    P(f"    LITERAL (every A yes/no with a composite; unrankable at the middle 0.5): {fmt(a_all)} "
      f"(n yes {ny} / no {nn}) -> {'PASS' if a_all is not None and a_all >= BAR_I - TOL else 'FAIL'}")
    P(f"    RANKABLE-ONLY (pool of >= 2 featured here): {fmt(a_r)} (n yes {nyr} / no {nnr})"
      f" -> {'PASS' if a_r is not None and a_r >= BAR_I - TOL else 'FAIL'}")
    P("    ⚠ in-sample by construction: the features were selected on A, then the composite is scored on A.")
    if verbose:
        st_counts = defaultdict(int)
        for p in A_yes + A_no:
            st_counts[R["ranked"][(p["ticker"], p["date"], "A")]["status"].split("(")[0]] += 1
        P("    A yes/no pool status: " + " · ".join(f"{k}={v}" for k, v in sorted(st_counts.items())))
        for p in sorted(A_yes + A_no, key=lambda p: (p["label"] not in YES, p["date"])):
            rk = R["ranked"][(p["ticker"], p["date"], "A")]
            P(f"      {p['ticker']:<6} {p['date']} {p['label']:<12} composite {fmt(rk['comp'])}  "
              f"ranks {', '.join(f'{k}={v:.2f}' for k, v in rk['ranks'].items())}  | {pool_line(p, rk)}")
    ii = R["ii"]
    P(f"\n  BAR (ii) — his 8 labelled EPs in the top half of their day (needs >= {int(BAR_II*100)}% of the "
      f"rankable ones)")
    P(f"    rankable {ii['elig']} of {len(B_his)} · top half (composite < 0.5) {ii['top']} · exactly 0.5 "
      f"{ii['mid']} -> share {fmt(ii['share'],2)} -> "
      f"{'PASS' if ii['share'] is not None and ii['share'] >= BAR_II - TOL else 'FAIL'}")
    if verbose:
        for p, rk in ii["b"]:
            P(f"      {p['ticker']:<5} {p['date']} composite {fmt(rk['comp'])}  "
              f"ranks {', '.join(f'{k}={v:.2f}' for k, v in rk['ranks'].items())}  | {pool_line(p, rk)}")
    P(f"\n  BAR (iii) — C, v2 top quartile vs the OLD composite's top quartile, tail >= {TAIL}xADR, both "
      f"directions (v2 NULL composite on {R['c_null']} of {len(C)} C rows -> never in v2's top)")
    for (tag, oldkey), x in R["iii"].items():
        c, b = x["cand"], x["base"]
        P(f"    [{tag} · vs old {oldkey}] matured n={x['pop']} | v2 top n={c.n} winners {c.winners_admitted} "
          f"losers {c.losers_admitted}/{c.n} | old top n={b.n} winners {b.winners_admitted} losers "
          f"{b.losers_admitted}/{b.n}")
        P(f"        score_both_directions(v2_top, old_top): {x['verdict']}")
        P(f"        pre-reg bar (more tail winners AND loser rate no higher): {'PASS' if x['passed'] else 'FAIL'}")
        if verbose and oldkey == "c_eod":
            P(f"        v2's own top vs rest: {x['own']}")
            P("        v2 top members: " + ", ".join(
                f"{r['tk']} {r['date']}({r[('x5' if tag == '5d' else 'x20')]:.1f}x{' L' if r['loser'] else ''})"
                for r in x["vt"]))
            P("        tails: " + ", ".join(
                f"{r['tk']} {r['date']} {r[('x5' if tag == '5d' else 'x20')]:.2f}x v2={fmt(S_ranked_c(R, r))} "
                f"old={fmt(r['c_eod'])} pool={r['pool_eod']}" for r in x["tails"]))


def S_ranked_c(R, r):
    return R["ranked"][(r["tk"], r["date"], "C")]["comp"]


report_bars(S, True)


def verdict_of(R):
    if not R["included"]:
        return "EMPTY", None, None, None
    i_ok = R["i_all"][0] is not None and R["i_all"][0] >= BAR_I - TOL
    ii_ok = R["ii"]["share"] is not None and R["ii"]["share"] >= BAR_II - TOL
    iii_ok = all(R["iii"][(h, "c_eod")]["passed"] for h in ("5d", "20d"))
    return ("PASS" if (i_ok and ii_ok and iii_ok) else
            ("HIS EYE, NOT THE TAIL" if (i_ok and ii_ok) else "FAIL")), i_ok, ii_ok, iii_ok


# ── step 4: plateau ──
P("\n[4] PLATEAU — each pre-registered threshold at -50% / +50%, one at a time (others at stated)")
variants = [("adr_mult", 0.5), ("adr_mult", 1.5), ("vol_win", 126), ("vol_win", 378),
            ("pb_win", 20), ("pb_win", 60), ("base_end", 125), ("base_end", 375)]
P(f"  {'variant':<16} {'vol_ratio':>9} {'held':>6} {'n(held)':>8} | included | (i) literal / rankable | (ii) | "
  f"(iii) 5d / 20d vs old EOD")
rows_plat = [("stated", STATED, S)]
for k, v in variants:
    prm = dict(STATED)
    prm[k] = v
    rows_plat.append((f"{k}={v}", prm, run(prm, f"{k}={v}", False)))
for name, prm, R in rows_plat:
    sa = R["sa"]
    inc = "+".join(k for k, _ in R["included"]) or "EMPTY"
    if R["included"]:
        i_s = f"{fmt(R['i_all'][0],2)} / {fmt(R['i_rank'][0],2)}"
        ii_s = f"{R['ii']['top']}/{R['ii']['elig']}"
        iii_s = " / ".join(("PASS" if R["iii"][(h, 'c_eod')]["passed"] else "fail") +
                           f"({R['iii'][(h, 'c_eod')]['cand'].winners_admitted}w)" for h in ("5d", "20d"))
    else:
        i_s = ii_s = iii_s = "-"
    P(f"  {name:<16} {fmt(sa['vol_ratio']['score'],2):>9} {fmt(sa['held']['score'],2):>6} "
      f"{sa['held']['ny']:>3}/{sa['held']['nn']:<4} | {inc} | {i_s} | {ii_s} | {iii_s} | "
      f"verdict {verdict_of(R)[0]}")
P("  (feature 1 zones and feature 4 tightness carry no pre-registered threshold; their scores do not move.)")

# ── step 5: B2 ──
P("\n[5] B2 — the 26 R-picked winners (evidence:winner_r_available...), NOT his labels; reported apart")
b2_stat = defaultdict(int)
for p in B2:
    f = features(p["ticker"], p["date"])
    rk = S["ranked"][(p["ticker"], p["date"], "B")]
    b2_stat[(rk["status"] or "").split("(")[0]] += 1
    P(f"    {p['ticker']:<5} {p['date']} zc={fmt(f['zones_cleared'])} zr={fmt(f['zones_remaining'])} "
      f"ath={fmt(f['cleared_ath'])} vol_r={fmt(f['vol_ratio'],2)} vhe={fmt(f['vol_highest_ever'])} "
      f"held={fmt(f['held'])} t_eod={fmt(f['tight_eod'],1)} | composite {fmt(rk['comp'])} {rk['status']}")
P("  B2 status: " + " · ".join(f"{k}={v}" for k, v in sorted(b2_stat.items())))
for k in PRIMARY:
    vals = [features(p["ticker"], p["date"])[k] for p in B2]
    vals = [x for x in vals if x is not None]
    yv = [features(p["ticker"], p["date"])[k] for p in A_yes]
    nv = [features(p["ticker"], p["date"])[k] for p in A_no]
    yv = [x for x in yv if x is not None]
    nv = [x for x in nv if x is not None]
    P(f"    {k:<14} B2 median {fmt(st.median(vals) if vals else None,2)} (n={len(vals)}) | A-yes median "
      f"{fmt(st.median(yv) if yv else None,2)} | A-no median {fmt(st.median(nv) if nv else None,2)}")

# ── step 6: verdict ──
v, i_ok, ii_ok, iii_ok = verdict_of(S)
P("\n[6] VERDICT (the pre-registration's own words)")
P(f"  composite: {', '.join(f'{k} ({d})' for k, d in S['included']) or 'EMPTY'}")
P(f"  (i) {('PASS' if i_ok else 'FAIL') if i_ok is not None else '-'} · (ii) "
  f"{('PASS' if ii_ok else 'FAIL') if ii_ok is not None else '-'} · (iii) "
  f"{('PASS' if iii_ok else 'FAIL') if iii_ok is not None else '-'} -> {v}")
fragile = []
for name, prm, R in rows_plat[1:]:
    if verdict_of(R)[0] != v:
        fragile.append(f"{name} -> {verdict_of(R)[0]}")
vr_s = [R["sa"]["vol_ratio"]["score"] for _, _, R in rows_plat]
hd_s = [R["sa"]["held"]["score"] for _, _, R in rows_plat]
P("  plateau: " + ("verdict unchanged at every +-50% variant — but VACUOUSLY: the four thresholds touch only"
                   f" F2 (vol_ratio {min(vr_s):.2f}-{max(vr_s):.2f}) and F3 (held {min(hd_s):.2f}-{max(hd_s):.2f}),"
                   " which never reach 0.65 at any setting, so the composite (zones_cleared alone) never moves."
                   if not fragile else
                   "verdict CHANGES at: " + "; ".join(fragile) + " -> FRAGILE"))

P("\n  READINGS THE PASS/FAIL LINES DO NOT CARRY")
P(f"  - (i) fails on feature strength, not the pool gap: raw zones_cleared is {S['sa']['zones_cleared']['score']:.3f}"
  f" on A — under 0.70 before any within-day ranking — so pulling the missing pool bars cannot lift (i) to 0.70.")
thin = [(p["ticker"], rk["featured"], rk["pool_alerts"] + (0 if rk["in_alerts"] else 1))
        for p, rk in S["ii"]["b"] if rk["status"] == "rankable"]
P("  - (ii) is thin: ranked against " + ", ".join(f"{t} {fe - 1} other(s) of {tot - 1}" for t, fe, tot in thin)
  + " — only the ones whose whole day has bars are ranked over the full day.")
x5 = S["iii"][("5d", "c_eod")]
P(f"  - (iii) mechanics: v2's top quartile holds {x5['cand'].n} rows vs the old's {x5['base'].n} at 5 sessions —"
  " a one-feature composite gives the better of any two-alert day exactly 0.25, so v2 admits more of"
  " everything. v2 moves MRNA 08-19 from 0.875 to 0.125 and VICR 09-17 from 0.25 to 0.75; KOD 09-28 is a"
  " one-alert day under both rankings and can never reach either top quartile.")
P("  - F3 never fires on his examples: the pre-registered base high (max high of sessions 41-250) on KOD is the"
  " 2026-04-22 $47.84 peak; KOD's September lows sat at $29.81-33, the Dec-Feb shelf he pointed at. All 8 of his"
  " labelled EPs read held=0; A-yes and A-no medians are both 0. Any new definition is a new pre-registration.")
P(f"  - tight_0945 (sub-read) scores {S['sa']['tight_0945']['score']:.2f} but with WIDER 09:45 range = yes, opposite"
  f" to EOD, on only {S['sa']['tight_0945']['ny']}/{S['sa']['tight_0945']['nn']} pairs.")

# ── NOT the pre-registered bar: his "keep tightness" read as forced inclusion ──
P("\n[7] NOT THE PRE-REGISTERED BAR — his 11-03 'keep tightness' read literally as forced inclusion")
P("  (the pre-registration admits tightness only if it scores >= 0.65 on A; it scored "
  f"{S['sa']['tight_eod']['score']:.3f}, tighter = yes, and missed. This section shows what forcing it in reads;"
  " it changes nothing above.)")
FORCED = [("zones_cleared", S["sa"]["zones_cleared"]["direction"]), ("tight_eod", S["sa"]["tight_eod"]["direction"])]
_rf = {(p["ticker"], p["date"], p["source"]): rank_pair(p, FORCED, STATED) for p in pairs}


def _ca(g, only):
    out = []
    for p in g:
        rk = _rf[(p["ticker"], p["date"], "A")]
        if rk["comp"] is not None and (not only or rk["status"] == "rankable"):
            out.append(rk["comp"])
    return out


_al = auc([-x for x in _ca(A_yes, False)], [-x for x in _ca(A_no, False)])
_ar = auc([-x for x in _ca(A_yes, True)], [-x for x in _ca(A_no, True)])
P(f"  (i) literal {_al:.3f} · rankable-only {_ar:.3f} (needs 0.70) -> FAIL")
_be = [(p, _rf[(p["ticker"], p["date"], "B")]) for p in B_his]
_be = [(p, rk) for p, rk in _be if rk["status"] == "rankable"]
P(f"  (ii) {sum(1 for _, rk in _be if rk['comp'] < 0.5 - TOL)} of {len(_be)} rankable labelled EPs in the top half"
  " -> FAIL. Their gap-day ranges (tightness_eod, % of high): " + ", ".join(
      f"{p['ticker']} {features(p['ticker'], p['date'])['tight_eod']:.0f}% (pool rank {rk['ranks']['tight_eod']:.2f})"
      for p, rk in _be))
_wide = sum(1 for _, rk in _be if rk["ranks"]["tight_eod"] > 0.5 + TOL)
for tag, mat, xk in (("5d", 6, "x5"), ("20d", 21, "x20")):
    pop = [r for r in rows_c if r["sess"] >= mat and r[xk] is not None]
    vt = [r for r in pop if _rf[(r["tk"], r["date"], "C")]["comp"] is not None
          and _rf[(r["tk"], r["date"], "C")]["comp"] <= 0.25 + TOL]
    ot = [r for r in pop if r["c_eod"] is not None and r["c_eod"] <= 0.25 + TOL]
    c = CohortRead(len(vt), sum(1 for r in vt if r[xk] >= TAIL), sum(1 for r in vt if r["loser"]))
    b = CohortRead(len(ot), sum(1 for r in ot if r[xk] >= TAIL), sum(1 for r in ot if r["loser"]))
    P(f"  (iii) {tag}: forced top n={c.n} winners {c.winners_admitted} losers {c.losers_admitted}/{c.n} vs old top"
      f" n={b.n} winners {b.winners_admitted} losers {b.losers_admitted}/{b.n} -> {score_both_directions(c, b)}")
P(f"  READ: {_wide} of {len(_be)} of his rankable labelled EPs sit in the WIDER half of their day on gap-day range"
  " (pool rank > 0.5 = wider than the middle) — on the gap day, tightness runs against his own EPs, so forcing it"
  " in fails every bar.")

# ── features.tsv ──
cols = ["ticker", "date", "source", "label", "label_group",
        "zones_cleared", "zones_remaining", "cleared_ath", "cls_preopen", "adr20_pct",
        "vol_ratio_252", "vol_highest_ever", "pullbacks_held", "pb_low1_adr", "pb_low2_adr",
        "n_swing_lows", "base_high", "tightness_eod", "tightness_asof0945", "history_5y_sessions",
        "null_reasons"] + [f"rank_{k}" for k in PRIMARY] + [
        "v2_composite", "v2_status", "alerts_that_day", "pair_in_alerts", "pool_with_bars",
        "pool_featured", "old_composite_eod", "old_pool_eod", "old_composite_0945", "old_pool_0945"]
with open(HERE / "features.tsv", "w", newline="") as fh:
    w = csv.writer(fh, delimiter="\t")
    w.writerow(cols)
    for p in pairs:
        f = features(p["ticker"], p["date"])
        rk = S["ranked"][(p["ticker"], p["date"], p["source"])]
        s = shadow.get((p["ticker"], p["date"]), {})
        grp = {"A": ("yes" if p["label"] in YES else "no" if p["label"] in NO else "excluded"),
               "B": ("his_label" if p["label"] == "operator" else "B2_r_picked"), "C": "shadow"}[p["source"]]
        g = lambda x, n=4: "" if x is None else (f"{x:.{n}f}" if isinstance(x, float) else str(x))  # noqa: E731
        w.writerow([p["ticker"], p["date"], p["source"], p["label"], grp,
                    g(f["zones_cleared"]), g(f["zones_remaining"]), g(f["cleared_ath"]), f["cls"] or "",
                    g(f["adr20"]), g(f["vol_ratio"]), g(f["vol_highest_ever"]), g(f["held"]),
                    g(f["pb_low1_adr"]), g(f["pb_low2_adr"]), g(f["n_swing_lows"]), g(f["base_high"]),
                    g(f["tight_eod"]), g(f["tight_0945"]), g(f["history5y"]), ";".join(f["null"])]
                   + [g(rk["ranks"].get(k)) for k in PRIMARY]
                   + [g(rk["comp"]), rk["status"] or "", rk["pool_alerts"], int(rk["in_alerts"]),
                      rk["with_bars"], rk["featured"], s.get("composite_rank_eod", ""),
                      s.get("pool_size_eod", ""), s.get("composite_rank_asof0945", ""),
                      s.get("pool_size_asof0945", "")])
(HERE / "rank_v2.txt").write_text("\n".join(OUT) + "\n", encoding="utf-8")
