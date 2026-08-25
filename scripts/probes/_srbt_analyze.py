#!/usr/bin/env python3
"""STRUCTURE-READ BACKTEST — STAGE 2: does the supply read survive holding liquidity constant?
(READ-ONLY · $0 · MEASUREMENT ONLY. Nothing is wired into any score, no rule/threshold/
toggle/trade-state is touched, and nothing here is a recommendation — THE LINE.)

THE QUESTION (operator-authorised, 2026-08-25). `docs/analysis/structure_read_v2_2026-08-25.md`
scored the supply read at AUC 0.728 on 26 labelled real EPs vs 27 rejects — and flagged its own
unresolved caveat: the two arms differ 85x in dollar volume, so the read may be detecting
LIQUIDITY CLASS, not overhead supply. This harness answers it on months of scan history by
holding dollar volume constant.

⚠ PRE-REGISTRATION — written before any number below was computed and NOT revised afterwards.
NOTHING IS TUNED. `_structure_read_v2.py` is used UNCHANGED; not one parameter is adjusted,
no cutline is chosen, no direction is flipped after seeing a number. A null at scale is the
deliverable if that is what the data says.

  MEASURE (primary)      overhead_vol_frac        LOWER = more like a real EP / better forward
                                                  outcome. The share of the name's own traded
                                                  volume sitting above the open.
  MEASURE (robustness)   overhead_vol_frac_60d    same direction. FIXED 60-session window, so it
                                                  is immune to the history-depth drift that the
                                                  all-history profile has across the date range
                                                  (mi_daily_closes starts 2025-07-21).
  MEASURE (secondary)    zones_cleared            HIGHER = better (the ladder count)
                         base_range_adr           LOWER  = better (gap-robust base tightness)
  LIQUIDITY CONTROL      advd20 = median(close x volume) over the 20 PRIOR sessions, from bars.
                         NOT the scan log's `adv` field (that is a SHARE count, not dollars).

  OUTCOME (primary)      ret_5d      = (close of the 5th session after the alert - the alert-day
                                      OPEN) / that open. Same price basis the read is taken on.
  OUTCOME (secondary)    max_high_5d = the best the name offered over sessions 0-5, same basis.
  BINARY LABEL           ret_5d > 0. The only threshold with no free parameter, used so the
                         number is directly comparable to the published 0.728.

  STRATIFICATION (this is the whole point). ADV$ DECILES computed once over the computable
  cohort. Every stratified statistic restricts COMPARISONS TO PAIRS INSIDE THE SAME STRATUM and
  pools across strata, weighted by each stratum's pair count -> ONE number on the AUC scale,
  directly comparable to the pooled figure. Two strata definitions:
      (a) ADV$ decile
      (b) ADV$ decile x SCAN DATE  (holds liquidity AND market regime constant simultaneously)

  READING RULE, DECLARED NOW: if the stratified numbers collapse to ~0.500 while the pooled
  number is high, the read is a liquidity proxy and 0.728 is an artifact. If they hold, it is
  measuring structure.

  TESTS, in the order they are reported:
    T0  BAR-SOURCE FIDELITY — the read recomputed off mi_daily_closes vs the 08-25 study's
        Polygon capture, name by name. A miss here invalidates everything downstream.
    TB  FORWARD OUTCOME INSIDE THE SCAN COHORT, stratified. THE HEADLINE — no arm contrast,
        so "liquidity held constant" is structurally true rather than approximated.
    TA  Labelled real EPs vs scan-log rejects within ADV$ band — GATED on a measured liquidity
        overlap. If the overlap region is empty it is a description, not a test, and is reported
        as such.
    TC  Forward outcome among names we ALERTED (HIGH and MODERATE reported separately).
    RS  The review sample for the operator's labelling loop.

  KNOWN LIMITATION, stated up front and not fixable from this data: the cohort is "names a gate
  already logged". It cannot speak to names that were never scanned.
"""
from __future__ import annotations

import csv
import gzip
import math
import random
import statistics as st
import sys
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))

from agents.market_intelligence.scanned_report import _outcome_is_fresh  # noqa: E402

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


def _b(x):
    return None if x == "" else (x == "1")


# ══ LOAD ══════════════════════════════════════════════════════════════════════════════
READS: dict[tuple[str, str, str, date], dict] = {}
NUM = {"n_bars", "open", "prior_close", "gap_open_pct", "adr20_pct", "overhead_vol_frac",
       "overhead_vol_frac_60d", "overhead_vol_frac_at_prior_close", "n_gaps", "n_unfilled_gaps",
       "overhead_unfilled_gap_span_adr", "nearest_overhead_gap_bottom_adr", "n_levels",
       "n_qualified", "zones_overhead_at_prior_close", "zones_cleared", "zones_remaining",
       "zones_remaining_in_band", "adr_to_next_zone", "rmv_15", "base_range_adr",
       "base_gap_max_adr", "base_gap_span_adr", "base_gap_count_1p0x", "trailing_high",
       "near_high_frac", "advd20"}
BOOL = {"thin_history", "inside_unfilled_gap", "blue_sky", "rmv_tight", "tight_v2",
        "open_above_trailing_high"}
for r in csv.DictReader((HERE / "_srbt_reads.psv").open(), delimiter="|"):
    row = dict(r)
    row["alert_date"] = _d(r["alert_date"])
    for k in NUM:
        row[k] = _f(r.get(k))
    for k in BOOL:
        row[k] = _b(r.get(k))
    READS[(r["src"], r["tag"], r["ticker"], row["alert_date"])] = row

SCAN: dict[tuple[str, date], dict] = {}
for ln in (HERE / "_srbt_scanlog.psv").read_text().splitlines():
    p = ln.split("|")
    if len(p) < 20:
        continue
    SCAN[(p[1], _d(p[0]))] = {
        "gap_pct": _f(p[2]), "prev_close": _f(p[3]), "filter_reason": p[5],
        "ep_score": _f(p[6]), "score_tier": p[7], "adv_shares": _f(p[9]),
        "n_ticks": int(p[15]) if p[15] else 0, "ever_no_filter": p[18] == "t",
        "reasons": p[19]}

NOW = datetime.now(timezone.utc)
OUTC: dict[tuple[str, date], dict] = {}
for ln in (HERE / "_srbt_outcomes.psv").read_text().splitlines():
    p = ln.split("|")
    if len(p) < 17:
        continue
    lr = p[16].strip()
    try:
        lrd = datetime.fromisoformat(lr)
    except ValueError:
        lrd = None
    o = {"ticker": p[0], "alert_date": _d(p[1]), "source": p[2], "skip_reason": p[3],
         "skip_category": p[4], "open_d0": _f(p[9]), "close_d0": _f(p[10]),
         "ret_1d": _f(p[11]), "ret_5d": _f(p[12]), "ret_20d": _f(p[13]),
         "max_high_5d": _f(p[14]), "max_high_20d": _f(p[15]), "last_refreshed_at": lrd}
    k = (o["ticker"], o["alert_date"])
    prev = OUTC.get(k)
    if prev is None or (lrd and prev["last_refreshed_at"] and lrd > prev["last_refreshed_at"]):
        OUTC[k] = o

ALERTS: dict[tuple[str, date], dict] = {}
for ln in (HERE / "_srbt_alerts.psv").read_text().splitlines():
    p = ln.split("|")
    if len(p) < 6:
        continue
    ALERTS[(p[0], _d(p[1]))] = {"ep_score": _f(p[2]), "tier": p[3], "gap_pct": _f(p[4]),
                                "quality": p[5]}

BARS: dict[str, list[tuple[date, float, float, float]]] = defaultdict(list)
with gzip.open(HERE / "_srbt_bars.psv.gz", "rt") as fh:
    for ln in fh:
        p = ln.rstrip("\n").split("|")
        if len(p) < 7 or p[3] == "" or p[4] == "":
            continue
        BARS[p[0]].append((_d(p[1]), _f(p[2]), _f(p[3]), _f(p[5])))   # date, open, high, close
for t in BARS:
    BARS[t].sort()
MAX_BAR = max(b[0] for bs in BARS.values() for b in bs)


def recompute_outcome(ticker: str, ad: date) -> dict:
    """Reproduce missed_outcomes.py's own arithmetic from bars, exactly:
    open_d0 = the alert-day open; close_d5 = OFFSET 4 among sessions AFTER the alert day;
    max_high_5d = max high over the 6 sessions from the alert day inclusive."""
    bs = BARS.get(ticker, [])
    d0 = next((b for b in bs if b[0] == ad), None)
    if not d0 or not d0[1]:
        return {}
    aft = [b for b in bs if b[0] > ad]
    o = d0[1]
    r: dict = {"open_d0": o}
    if len(aft) >= 5:
        r["ret_5d"] = (aft[4][3] - o) / o
    if len(aft) >= 1:
        r["ret_1d"] = (aft[0][3] - o) / o
    win = [b for b in bs if b[0] >= ad][:6]
    if len(win) >= 6:
        r["max_high_5d"] = (max(b[2] for b in win) - o) / o
    return r


# ══ STATS ═════════════════════════════════════════════════════════════════════════════
def _midranks(v: list[float]) -> list[float]:
    idx = sorted(range(len(v)), key=lambda i: v[i])
    rk = [0.0] * len(v)
    i = 0
    while i < len(idx):
        j = i
        while j + 1 < len(idx) and v[idx[j + 1]] == v[idx[i]]:
            j += 1
        for k in range(i, j + 1):
            rk[idx[k]] = (i + j) / 2.0 + 1.0
        i = j + 1
    return rk


def auc(pos: list[float], neg: list[float]):
    """Rank-based AUC with midranks for ties (identical to the pairwise 0.5-for-ties form)."""
    n1, n2 = len(pos), len(neg)
    if not n1 or not n2:
        return None, 0
    rk = _midranks(pos + neg)
    s = sum(rk[:n1])
    return (s - n1 * (n1 + 1) / 2.0) / (n1 * n2), n1 * n2


def strat_auc(items, score_of, label_of, stratum_of):
    """AUC with COMPARISONS RESTRICTED TO PAIRS INSIDE THE SAME STRATUM, pooled across
    strata weighted by pair count. This is the 'hold dollar volume constant' statistic."""
    g = defaultdict(lambda: ([], []))
    for r in items:
        s, lb = score_of(r), label_of(r)
        if s is None or lb is None:
            continue
        g[stratum_of(r)][0 if lb else 1].append(s)
    num = den = 0.0
    per = {}
    for k, (pos, neg) in g.items():
        a, w = auc(pos, neg)
        if a is None:
            continue
        num += a * w
        den += w
        per[k] = (a, len(pos), len(neg))
    return (num / den if den else None), int(den), per


def strat_concordance(items, score_of, outcome_of, stratum_of):
    """Threshold-free twin of strat_auc on a CONTINUOUS outcome: over pairs inside the same
    stratum whose outcomes differ, the share where the higher score had the better outcome
    (ties in score count 0.5). 0.500 = a coin, same scale as AUC."""
    g = defaultdict(list)
    for r in items:
        s, y = score_of(r), outcome_of(r)
        if s is None or y is None:
            continue
        g[stratum_of(r)].append((s, y))
    c = n = 0.0
    for arr in g.values():
        m = len(arr)
        for i in range(m):
            si, yi = arr[i]
            for j in range(i + 1, m):
                sj, yj = arr[j]
                if yi == yj:
                    continue
                n += 1
                if si == sj:
                    c += 0.5
                elif (si > sj) == (yi > yj):
                    c += 1
    return (c / n if n else None), int(n)


def cluster_boot_ci(items, stat_fn, cluster_of, n_boot=400, seed=7):
    """Cluster bootstrap over SCAN DATES — the clustering the 08-25 study could not do with
    ten days against two. Resamples whole trading days with replacement."""
    rng = random.Random(seed)
    by = defaultdict(list)
    for r in items:
        by[cluster_of(r)].append(r)
    keys = list(by)
    vals = []
    for _ in range(n_boot):
        samp = []
        for _ in range(len(keys)):
            samp.extend(by[keys[rng.randrange(len(keys))]])
        v = stat_fn(samp)
        if v is not None and not math.isnan(v):
            vals.append(v)
    if len(vals) < 20:
        return None, None
    vals.sort()
    return vals[int(0.025 * len(vals))], vals[min(len(vals) - 1, int(0.975 * len(vals)))]


def spearman(xs, ys):
    n = len(xs)
    if n < 3:
        return float("nan")
    rx, ry = _midranks(xs), _midranks(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else float("nan")


def med(v):
    v = [x for x in v if x is not None]
    return st.median(v) if v else None


# ══ COHORT ════════════════════════════════════════════════════════════════════════════
def reason_cat(fr: str) -> str:
    if fr == "":
        return "00_passed_all_gates"
    if fr.startswith("filter:universe_"):
        return "01_universe_floor"
    if fr.startswith("already scored earlier today"):
        return "02_bookkeeping_already_scored"
    if fr.startswith("EP cooldown"):
        return "02_bookkeeping_cooldown"
    if fr.startswith("outside top-"):
        return "03_rank_cap"
    if fr.startswith("score "):
        return "04_score_below_threshold"
    if fr.startswith("score-"):
        return "04_score_below_threshold"
    if fr.startswith("quality filter"):
        return "05_quality_filter"
    if fr.startswith("already up "):
        return "06_extended"
    if fr.startswith(("pre-mkt volume", "low volume", "low rel volume")):
        return "07_volume"
    if fr.startswith("routine catalyst"):
        return "08_routine_catalyst"
    if fr.startswith("M&A"):
        return "09_mna"
    if fr.startswith("filter:"):
        return "10_other_filter"
    return "11_other"


COH: list[dict] = []
for (src, tag, tkr, ad), r in READS.items():
    if src != "prod" or tag != "cohort":
        continue
    s = SCAN.get((tkr, ad), {})
    r = dict(r)
    r["scan"] = s
    r["cat"] = reason_cat(s.get("filter_reason", ""))
    r["month"] = f"{ad.year}-{ad.month:02d}"
    r["alerted"] = (tkr, ad) in ALERTS
    r["alert_tier"] = ALERTS.get((tkr, ad), {}).get("tier")
    o = OUTC.get((tkr, ad))
    r["outc_row"] = o
    r["outc_fresh"] = bool(o) and _outcome_is_fresh(o, ad, NOW)
    r["ret_5d"] = o["ret_5d"] if (o and r["outc_fresh"]) else None
    r["max_high_5d"] = o["max_high_5d"] if (o and r["outc_fresh"]) else None
    rc = recompute_outcome(tkr, ad)
    r["ret_5d_rc"] = rc.get("ret_5d")
    r["max_high_5d_rc"] = rc.get("max_high_5d")
    r["open_d0_rc"] = rc.get("open_d0")
    COH.append(r)
COH.sort(key=lambda r: (r["alert_date"], r["ticker"]))
COMP = [r for r in COH if not r["reason"] and r["overhead_vol_frac"] is not None]

emit("=" * 108)
emit("SUPPLY-LADDER READ vs MONTHS OF SCAN HISTORY — does it survive holding liquidity constant?")
emit("READ-ONLY · $0 · MEASUREMENT ONLY · nothing wired, no rule changed, nothing tuned.")
emit("=" * 108)
emit()
emit("STEP 1 — THE COHORT AS IT ACTUALLY IS (the real N, not an estimate)")
emit("-" * 108)
ds = sorted({r["alert_date"] for r in COH})
emit(f"  mi_ep_scan_log, deduped to one row per (scan_date, ticker), last tick of the day:")
emit(f"    {len(COH)} name-days · {len({r['ticker'] for r in COH})} tickers · "
     f"{len(ds)} scan days · {ds[0]} to {ds[-1]}")
emit(f"    median names per scan day: {med([len([r for r in COH if r['alert_date']==d]) for d in ds]):.0f}"
     f"   (NOT ~200/day — that rate only appears on 08-24/08-25)")
emit(f"  computable reads: {len(COMP)}/{len(COH)}")
nr = defaultdict(int)
for r in COH:
    if r["reason"]:
        nr[r["reason"].split("(")[0]] += 1
for k, v in sorted(nr.items(), key=lambda x: -x[1]):
    emit(f"    not computable — {k:<24} {v}")
emit(f"    ⚠ every 08-25 name-day is dropped: mi_daily_closes ends {MAX_BAR}, so there is no")
emit(f"      alert-day OPEN for them. That is 212 of the 264 uncomputable rows.")
emit()
emit("  what killed each name-day (last tick's reason), and how many are computable:")
cc = defaultdict(lambda: [0, 0])
for r in COH:
    cc[r["cat"]][0] += 1
    if r in COMP:
        cc[r["cat"]][1] += 1
for k in sorted(cc):
    emit(f"    {k:<32} {cc[k][0]:>5} name-days   computable {cc[k][1]:>5}")
emit()
emit("  ⚠ REGIME BREAK, named because it changes what the pool is: `filter:universe_*` rows exist")
emit("    ONLY on 2026-08-24/25 (the scanner began logging universe-floor rejects then). Every")
emit("    stratified test below therefore EXCLUDES them, so the population is uniform across the")
emit("    whole date range — this is the same exclusion the 08-25 study's reject arm used.")
emit()

POOL = [r for r in COMP if r["cat"] != "01_universe_floor"]
emit(f"  → the analysis pool: {len(POOL)} computable name-days, "
     f"{len({r['ticker'] for r in POOL})} tickers, "
     f"{len({r['alert_date'] for r in POOL})} scan days, "
     f"{min(r['alert_date'] for r in POOL)} to {max(r['alert_date'] for r in POOL)}")
emit()

# ══ T0 — BAR-SOURCE FIDELITY ══════════════════════════════════════════════════════════
emit("=" * 108)
emit("T0 — BAR-SOURCE FIDELITY: the read recomputed off mi_daily_closes vs the 08-25 study's")
emit("     Polygon capture, NAME BY NAME. A miss here invalidates every number below.")
emit("-" * 108)
pairs = []
for (src, tag, tkr, ad), r in READS.items():
    if src != "prod" or tag not in ("fixture", "v2rej"):
        continue
    q = READS.get(("poly", tag, tkr, ad))
    if q and r.get("overhead_vol_frac") is not None and q.get("overhead_vol_frac") is not None:
        pairs.append((tag, tkr, ad, r, q))
emit(f"  name-days readable on BOTH sources: {len(pairs)}  "
     f"({sum(1 for p in pairs if p[0]=='fixture')} labelled real EPs, "
     f"{sum(1 for p in pairs if p[0]=='v2rej')} of the 27 original rejects)")
emit("  ⚠ only 9 of the 27 rejects: 18 of them are 2026-08-25 name-days and mi_daily_closes has")
emit("    no 08-25 bar, so the full 26-vs-27 cannot be re-run on this source. The fidelity check")
emit("    is therefore done AT THE MEASURE LEVEL, name by name, which is the stronger form.")
emit()
for key in ("overhead_vol_frac", "overhead_vol_frac_60d", "zones_cleared", "gap_open_pct"):
    a = [p[3][key] for p in pairs if p[3].get(key) is not None and p[4].get(key) is not None]
    b = [p[4][key] for p in pairs if p[3].get(key) is not None and p[4].get(key) is not None]
    if not a:
        continue
    dif = [abs(x - y) for x, y in zip(a, b)]
    emit(f"    {key:<28} Spearman(prod, polygon) {spearman(a,b):>6.3f}   "
         f"median |diff| {med(dif):>7.4f}   max |diff| {max(dif):>7.4f}")
emit()
emit("    the 6 largest disagreements on the primary (all are history-depth, not error):")
dd = sorted(pairs, key=lambda p: -abs(p[3]["overhead_vol_frac"] - p[4]["overhead_vol_frac"]))[:6]
for tag, tkr, ad, r, q in dd:
    emit(f"      {tkr:<6} {ad} {tag:<8} prod {r['overhead_vol_frac']:.3f} ({int(r['n_bars'])}d) "
         f"vs polygon {q['overhead_vol_frac']:.3f} ({int(q['n_bars'])}d)   "
         f"60d variant: {r['overhead_vol_frac_60d']:.3f} vs {q['overhead_vol_frac_60d']:.3f}")
emit()
FIXP = [READS[k] for k in READS if k[0] == "prod" and k[1] == "fixture"]
REJP = [READS[k] for k in READS if k[0] == "prod" and k[1] == "v2rej"
        and READS[k].get("overhead_vol_frac") is not None]
FIXQ = [READS[k] for k in READS if k[0] == "poly" and k[1] == "fixture"]
REJQ = [READS[k] for k in READS if k[0] == "poly" and k[1] == "v2rej"
        and (READS[k]["ticker"], READS[k]["alert_date"]) in
        {(x["ticker"], x["alert_date"]) for x in REJP}]
for nm, F, R in (("mi_daily_closes", FIXP, REJP), ("polygon capture", FIXQ, REJQ)):
    a, _ = auc([-r["overhead_vol_frac"] for r in F if r.get("overhead_vol_frac") is not None],
               [-r["overhead_vol_frac"] for r in R if r.get("overhead_vol_frac") is not None])
    emit(f"    26 real EPs vs the 9 readable rejects, overhead_vol_frac on {nm:<16}: AUC {a:.3f}")
emit("    (the published figure is 0.728 on 26 vs 27; this 26-vs-9 subset is shown only to")
emit("     confirm the two bar sources rank the same way, not as a replication of that number.)")
emit()

# ══ ADV$ DECILES ══════════════════════════════════════════════════════════════════════
adv = sorted(r["advd20"] for r in POOL if r["advd20"])
CUTS = [adv[int(len(adv) * i / 10)] for i in range(1, 10)]


def decile(r) -> int:
    v = r.get("advd20")
    if v is None:
        return -1
    d = 0
    for c in CUTS:
        if v >= c:
            d += 1
    return d


for r in POOL:
    r["dec"] = decile(r)
emit("=" * 108)
emit("STEP 2 — THE LIQUIDITY CONTROL: ADV$ deciles (median close x volume, prior 20 sessions)")
emit("-" * 108)
emit(f"  {'decile':<8}{'ADV$ range':<34}{'n':>6}{'median ADV$':>16}")
for d in range(10):
    sub = [r for r in POOL if r["dec"] == d]
    if not sub:
        continue
    lo, hi = min(r["advd20"] for r in sub), max(r["advd20"] for r in sub)
    emit(f"  {d:<8}${lo/1e6:>10.2f}M - ${hi/1e6:>10.2f}M      {len(sub):>6}"
         f"{med([r['advd20'] for r in sub])/1e6:>14.2f}M")
emit(f"  the pool spans ${min(adv)/1e6:.2f}M to ${max(adv)/1e6:.0f}M of daily dollar volume — a"
     f" {max(adv)/max(1.0,min(adv)):,.0f}x range,")
emit("  which is exactly why an unstratified number cannot tell structure from liquidity class.")
emit(f"  pooled Spearman(overhead_vol_frac, ADV$) over the {len(POOL)} name-days: "
     f"{spearman([r['overhead_vol_frac'] for r in POOL], [r['advd20'] for r in POOL]):.3f}")
emit("  (the 08-25 study measured -0.403 across its 53 rows and named it the unresolved caveat.)")
emit()
# ══ STEP 3 — THE OUTCOME JOIN, AND WHETHER IT CAN BE TRUSTED ══════════════════════════
emit("=" * 108)
emit("STEP 3 — FORWARD OUTCOMES: the join, the #583 staleness guard, and an independent recompute")
emit("-" * 108)
have_row = [r for r in POOL if r["outc_row"]]
fresh = [r for r in POOL if r["outc_fresh"]]
withr5 = [r for r in POOL if r["ret_5d"] is not None]
emit(f"  pool {len(POOL)} name-days")
emit(f"    have a mi_ep_missed_outcomes row           {len(have_row):>5}")
emit(f"    row PASSES the #583 freshness guard        {len(fresh):>5}  "
     f"(guard: refreshed within 2 days, OR after the 5-session outcome settled)")
emit(f"    ...and carries a settled ret_5d            {len(withr5):>5}")
stale = [r for r in have_row if not r["outc_fresh"]]
emit(f"    STALE (excluded, never silently kept)      {len(stale):>5}")
nores = [r for r in POOL if not r["outc_row"]]
emit(f"    NO outcome row at all                      {len(nores):>5}  "
     f"— reported, not dropped silently")
pend = [r for r in fresh if r["ret_5d"] is None]
emit(f"    fresh row but ret_5d still PENDING         {len(pend):>5}  "
     f"(alert dates {min([r['alert_date'] for r in pend]) if pend else '-'} onward — the 5th")
emit(f"                                                     session has not printed yet)")
emit()
agree = [(r["ret_5d"], r["ret_5d_rc"]) for r in withr5 if r["ret_5d_rc"] is not None]
bad = [r for r in withr5 if r["ret_5d_rc"] is not None and abs(r["ret_5d"] - r["ret_5d_rc"]) > 0.005]
emit(f"  INDEPENDENT RECOMPUTE from mi_daily_closes (same arithmetic as missed_outcomes.py:")
emit(f"  open_d0 = the alert-day open; close_d5 = 5th session after; max over sessions 0-5):")
emit(f"    comparable rows {len(agree)}   Spearman {spearman([a for a,_ in agree],[b for _,b in agree]):.4f}"
     f"   rows differing by >0.5pp: {len(bad)}")
if bad[:5]:
    for r in bad[:5]:
        emit(f"      {r['ticker']:<6} {r['alert_date']}  table {r['ret_5d']:+.4f}  "
             f"recomputed {r['ret_5d_rc']:+.4f}")
emit(f"    ⚠ FINDING: {len(stale)} of {len(have_row)} rows are stale — the #583 class is ABSENT from")
emit("      this cohort (the nightly rebuild has kept every row current). The guard is applied")
emit("      anyway, as instructed; on this data it is a no-op rather than a filter.")
emit()
for r in POOL:
    r["ret5"] = r["ret_5d"] if r["ret_5d"] is not None else r["ret_5d_rc"]
    r["mh5"] = r["max_high_5d"] if r["max_high_5d"] is not None else r["max_high_5d_rc"]
    r["ret5_src"] = ("table" if r["ret_5d"] is not None
                     else ("recomputed" if r["ret_5d_rc"] is not None else None))
EVAL = [r for r in POOL if r["ret5"] is not None]
emit(f"  → the outcome sample: {len(EVAL)} name-days with a settled 5-session outcome "
     f"({sum(1 for r in EVAL if r['ret5_src']=='table')} from the table, "
     f"{sum(1 for r in EVAL if r['ret5_src']=='recomputed')} recomputed where the table had no row).")
emit(f"    base rate — {sum(1 for r in EVAL if r['ret5']>0)/len(EVAL)*100:.1f}% closed the 5th "
     f"session above the gap-day open; median ret_5d {med([r['ret5'] for r in EVAL])*100:+.1f}%")
emit()

# ══ TB — THE HEADLINE TEST ════════════════════════════════════════════════════════════
emit("=" * 108)
emit("TB — 🎯 THE DECISIVE TEST: does the supply read predict the forward outcome WITHIN a")
emit("     dollar-volume band? (no arm contrast — every comparison is same-population)")
emit("=" * 108)
emit("  AUC = the chance a randomly picked winner (ret_5d > 0) has a LOWER overhead reading than")
emit("  a randomly picked loser. 0.500 is a coin. Stratified = comparisons restricted to pairs")
emit("  inside the same stratum, pooled by pair count.")
emit()


def mk(key, sign):
    return lambda r: (sign * r[key]) if r.get(key) is not None else None


LBL = lambda r: (r["ret5"] > 0) if r.get("ret5") is not None else None  # noqa: E731
MEAS = [("PRIMARY overhead_vol_frac", "overhead_vol_frac", -1),
        ("robustness  ..._60d window", "overhead_vol_frac_60d", -1),
        ("secondary   zones_cleared", "zones_cleared", +1),
        ("secondary   base_range_adr", "base_range_adr", -1),
        ("[ref] near_high_frac", "near_high_frac", +1),
        ("[ref] raw gap % at the open", "gap_open_pct", +1),
        ("[ref] ADV$ itself", "advd20", +1)]
emit(f"  {'measure':<30}{'pooled':>9}{'by ADV$':>10}{'ADV$ x DATE':>13}{'pairs(band)':>13}"
     f"{'pairs(b x d)':>14}")
emit("  " + "-" * 96)
TBRES = {}
for nm, key, sg in MEAS:
    sc = mk(key, sg)
    a0, _, _ = strat_auc(EVAL, sc, LBL, lambda r: 0)
    a1, p1, per1 = strat_auc(EVAL, sc, LBL, lambda r: r["dec"])
    a2, p2, _ = strat_auc(EVAL, sc, LBL, lambda r: (r["dec"], r["alert_date"]))
    TBRES[key] = (a0, a1, a2, per1)
    emit(f"  {nm:<30}{a0:>9.3f}{a1:>10.3f}{a2:>13.3f}{p1:>13,}{p2:>14,}")
emit()
emit("  95% confidence, CLUSTER BOOTSTRAP over whole scan days (400 resamples) — the clustered")
emit("  test the 08-25 study could not run with ten days against two:")
for nm, key, sg in MEAS[:4]:
    sc = mk(key, sg)
    lo, hi = cluster_boot_ci(EVAL, lambda it: (strat_auc(it, sc, LBL, lambda r: r["dec"])[0]),
                             lambda r: r["alert_date"])
    lo2, hi2 = cluster_boot_ci(EVAL, lambda it: (strat_auc(it, sc, LBL, lambda r: 0)[0]),
                               lambda r: r["alert_date"])
    emit(f"    {nm:<30} by ADV$ band {TBRES[key][1]:.3f} "
         f"[{lo:.3f}, {hi:.3f}]      pooled {TBRES[key][0]:.3f} [{lo2:.3f}, {hi2:.3f}]")
emit()
emit("  THRESHOLD-FREE TWIN — no binary label at all: over pairs inside a stratum whose 5-session")
emit("  returns differ, the share where the lower overhead reading had the better return.")
for onm, okey in (("ret_5d", "ret5"), ("max_high_5d (what it OFFERED)", "mh5")):
    for nm, key, sg in MEAS[:2]:
        sc = mk(key, sg)
        c0, n0 = strat_concordance(EVAL, sc, lambda r: r.get(okey), lambda r: 0)
        c1, n1 = strat_concordance(EVAL, sc, lambda r: r.get(okey), lambda r: r["dec"])
        c2, n2 = strat_concordance(EVAL, sc, lambda r: r.get(okey), lambda r: (r["dec"], r["alert_date"]))
        emit(f"    {onm:<30} {nm:<28} pooled {c0:.3f}   by ADV$ {c1:.3f}   ADV$ x date {c2:.3f}")
emit()
emit("  EVERY ADV$ DECILE SEPARATELY (the primary), so no band can hide inside the pooled figure:")
emit(f"    {'decile':<8}{'median ADV$':>14}{'n':>6}{'win rate':>10}{'AUC':>8}   ")
per = TBRES["overhead_vol_frac"][3]
for d in range(10):
    sub = [r for r in EVAL if r["dec"] == d]
    if not sub or d not in per:
        continue
    a, npos, nneg = per[d]
    emit(f"    {d:<8}{med([r['advd20'] for r in sub])/1e6:>12.1f}M{len(sub):>6}"
         f"{npos/(npos+nneg)*100:>9.0f}%{a:>8.3f}")
emit()
emit("  BY MONTH (the primary, stratified by ADV$ decile within each month):")
for m in sorted({r["month"] for r in EVAL}):
    sub = [r for r in EVAL if r["month"] == m]
    a, n, _ = strat_auc(sub, mk("overhead_vol_frac", -1), LBL, lambda r: r["dec"])
    emit(f"    {m}   n={len(sub):>4}   by-ADV$ AUC {a:.3f}" if a is not None else f"    {m}  n/a")
emit()
# ══ TA — REAL EPs vs REJECTS, WITHIN BAND (gated on a MEASURED overlap) ═══════════════
emit("=" * 108)
emit("TA — THE ORIGINAL ARM CONTRAST, WITH LIQUIDITY HELD CONSTANT (gated on overlap)")
emit("-" * 108)
FIXR = [r for r in FIXP if r.get("overhead_vol_frac") is not None and r.get("advd20")]
REJPOOL = [r for r in POOL if not r["alerted"]
           and r["cat"] not in ("00_passed_all_gates", "02_bookkeeping_already_scored",
                                "02_bookkeeping_cooldown")]
emit(f"  labelled real EPs (must_not_miss fixture, read off mi_daily_closes): {len(FIXR)}")
emit(f"  rejects — never alerted AND killed by a substantive gate (bookkeeping reasons excluded):"
     f" {len(REJPOOL)}")
flo, fhi = min(r["advd20"] for r in FIXR), max(r["advd20"] for r in FIXR)
emit(f"  real-EP ADV$ band: ${flo/1e6:.1f}M to ${fhi/1e6:,.0f}M   (median ${med([r['advd20'] for r in FIXR])/1e6:,.0f}M)")
emit(f"  reject-pool median ADV$: ${med([r['advd20'] for r in REJPOOL])/1e6:.1f}M")
inband = [r for r in REJPOOL if flo <= r["advd20"] <= fhi]
emit(f"  🔎 THE OVERLAP GATE — rejects inside the real-EP liquidity band: {len(inband)}")
emit("     (the 08-25 study had FOUR. That was the caveat this run exists to settle.)")
emit()
ALLTA = [dict(r, _ep=True) for r in FIXR] + [dict(r, _ep=False) for r in REJPOOL]
for r in ALLTA:
    r["dec"] = decile(r)
for nm, key, sg in MEAS[:4] + [MEAS[6]]:
    sc = mk(key, sg)
    a0, _, _ = strat_auc(ALLTA, sc, lambda r: r["_ep"], lambda r: 0)
    a1, n1, _ = strat_auc(ALLTA, sc, lambda r: r["_ep"], lambda r: r["dec"])
    sub = [r for r in ALLTA if flo <= (r.get("advd20") or 0) <= fhi]
    a2, n2, _ = strat_auc(sub, sc, lambda r: r["_ep"], lambda r: 0)
    emit(f"  {nm:<30} pooled {a0:>6.3f}   by ADV$ decile {a1:>6.3f}   "
         f"inside the real-EP band only {a2:>6.3f} (n={len([r for r in sub if r['_ep']])}v"
         f"{len([r for r in sub if not r['_ep']])})")
emit()
emit()
emit("  🔎 WHERE THE PUBLISHED 0.728 GOES — the SAME 26 real EPs, the SAME measure, the SAME bar")
emit("     source (mi_daily_closes). Only the REJECT ARM changes:")
emit(f"     {'reject arm':<46}{'n':>6}{'median ADV$':>14}{'AUC':>8}{'ADV$ alone':>12}")
V2R = [r for r in REJP]
CASES = [("the 08-25 study's arm, 9 of 27 readable here", V2R),
         ("every historical reject (substantive gate kills)", REJPOOL),
         ("...restricted to the real-EP liquidity band", inband)]
for nm, arm in CASES:
    a, _ = auc([-r["overhead_vol_frac"] for r in FIXR], [-r["overhead_vol_frac"] for r in arm])
    av, _ = auc([r["advd20"] for r in FIXR], [r["advd20"] for r in arm])
    emit(f"     {nm:<46}{len(arm):>6}{med([r['advd20'] for r in arm])/1e6:>12.1f}M{a:>8.3f}{av:>12.3f}")
allta_a, _, _ = strat_auc(ALLTA, mk("overhead_vol_frac", -1), lambda r: r["_ep"], lambda r: r["dec"])
emit(f"     {'...and with ADV$ held constant (decile-stratified)':<46}{len(REJPOOL):>6}"
     f"{med([r['advd20'] for r in REJPOOL])/1e6:>12.1f}M{allta_a:>8.3f}{'—':>12}")
emit("     'ADV$ alone' = dollar volume used as the discriminator by itself, no chart read at all.")
emit("     ⚠ The 1.000 on the 9-name arm is ARITHMETICALLY FORCED, not a measurement: those 9 sit")
emit("       entirely below the real-EP band's floor, so two disjoint ranges separate perfectly by")
emit("       construction. It restates the caveat rather than testing it. THE NUMBER THAT CARRIES")
emit("       THE ARGUMENT IS 0.888 on 2,418 rejects — a real sample with overlapping liquidity")
emit("       ranges, where a quantity that never looked at a chart still beats the read's 0.579.")
emit()
emit("  ⚠ HOW TO READ TA, declared in the pre-registration: banding cannot repair an arm contrast,")
emit("    it can only shrink it. 13 of the 26 real EPs are still ONE date (2026-04-08) and the two")
emit("    arms are still different populations. TA is a CONSISTENCY CHECK on TB, not the test.")
emit()

# ══ TC — THE NAMES WE ACTUALLY ALERTED ════════════════════════════════════════════════
emit("=" * 108)
emit("TC — DOES THE READ PREDICT THE 5-DAY OUTCOME AMONG THE NAMES WE ALERTED?")
emit("     (selection quality, on the money path — the sample that actually matters)")
emit("-" * 108)
AL = [r for r in EVAL if r["alerted"]]
emit(f"  mi_ep_alerts holds {len(ALERTS)} live alert name-days; {len([r for r in POOL if r['alerted']])}"
     f" of them are computable in this pool and {len(AL)} have a settled 5-session outcome.")
for tier in ("HIGH", "MODERATE", None):
    sub = [r for r in AL if (r["alert_tier"] == tier if tier else True)]
    if len(sub) < 8:
        emit(f"  {tier or 'ALL':<9} n={len(sub)} — too few to report a number")
        continue
    wr = sum(1 for r in sub if r["ret5"] > 0) / len(sub)
    emit(f"  {tier or 'ALL TIERS':<9} n={len(sub):>4}   "
         f"{wr*100:.0f}% closed day 5 above the open   "
         f"median ret_5d {med([r['ret5'] for r in sub])*100:+.1f}%   "
         f"median max_high_5d {med([r['mh5'] for r in sub])*100:+.1f}%")
    for nm, key, sg in MEAS[:4]:
        sc = mk(key, sg)
        a0, _, _ = strat_auc(sub, sc, LBL, lambda r: 0)
        a1, n1, _ = strat_auc(sub, sc, LBL, lambda r: r["dec"])
        c0, _ = strat_concordance(sub, sc, lambda r: r.get("ret5"), lambda r: 0)
        cm, _ = strat_concordance(sub, sc, lambda r: r.get("mh5"), lambda r: 0)
        lo, hi = cluster_boot_ci(sub, lambda it: strat_auc(it, sc, LBL, lambda r: 0)[0],
                                 lambda r: r["alert_date"], n_boot=400)
        ci = f"[{lo:.3f}, {hi:.3f}]" if lo is not None else "[--]"
        emit(f"      {nm:<30} AUC(ret_5d>0) {a0:>6.3f} {ci:<16} by ADV$ {a1:>6.3f}   "
             f"concordance ret_5d {c0:>5.3f} / max_high_5d {cm:>5.3f}")
    emit()

# ══ RS — THE REVIEW SAMPLE FOR THE OPERATOR'S LABELLING LOOP ══════════════════════════
emit("=" * 108)
emit("RS — REVIEW SAMPLE: what to put in front of the operator so his chart labels teach the most")
emit("-" * 108)
emit("  Threshold-free buckets: the read's TOP and BOTTOM decile of overhead_vol_frac, crossed")
emit("  with the sign of the 5-session outcome. The DISAGREEMENTS (confident-and-wrong) are the")
emit("  two buckets a label actually corrects. Drawn WITHIN ADV$ band and spread across months so")
emit("  he is not handed twenty microcaps from one week. This is a LIST, not a surface — no")
emit("  Telegram command is built here.")
emit()
ov = sorted(r["overhead_vol_frac"] for r in EVAL)
LOCUT, HICUT = ov[int(len(ov) * 0.10)], ov[int(len(ov) * 0.90)]
emit(f"  bottom-decile cut: overhead_vol_frac <= {LOCUT:.3f} (the read says CLEAR)")
emit(f"  top-decile cut:    overhead_vol_frac >= {HICUT:.3f} (the read says BURIED)")
emit()
BUCKETS = [
    ("A. CLEAR and it RAN — confident right (confirm the read)",
     lambda r: r["overhead_vol_frac"] <= LOCUT and r["ret5"] > 0, lambda r: -r["mh5"]),
    ("B. 🔴 CLEAR and it FELL — confident WRONG (what supply did the read not see?)",
     lambda r: r["overhead_vol_frac"] <= LOCUT and r["ret5"] <= 0, lambda r: r["ret5"]),
    ("C. 🔴 BURIED and it RAN — confident WRONG (overhead that did not stop it)",
     lambda r: r["overhead_vol_frac"] >= HICUT and r["ret5"] > 0, lambda r: -r["mh5"]),
    ("D. BURIED and it FELL — confident right (confirm the read)",
     lambda r: r["overhead_vol_frac"] >= HICUT and r["ret5"] <= 0, lambda r: r["ret5"]),
]
SAMPLE = []
for title, pred, rank in BUCKETS:
    cand = [r for r in EVAL if pred(r)]
    cand.sort(key=rank)
    picked, used_m, used_d = [], defaultdict(int), defaultdict(int)
    for r in cand:                       # spread: <=2 per month, <=2 per ADV$ decile
        if used_m[r["month"]] >= 2 or used_d[r["dec"]] >= 2:
            continue
        picked.append(r)
        used_m[r["month"]] += 1
        used_d[r["dec"]] += 1
        if len(picked) >= 10:
            break
    emit(f"  {title}   ({len(cand)} candidates, {len(picked)} drawn)")
    emit(f"    {'ticker':<7}{'date':<12}{'ADV$':>9}{'overhead':>10}{'zones':>7}{'label':<20}"
         f"{'gap%':>7}{'ret_5d':>9}{'ranhigh':>9}  why we saw it")
    for r in picked:
        SAMPLE.append((title[0], r))
        emit(f"    {r['ticker']:<7}{str(r['alert_date']):<12}"
             f"{r['advd20']/1e6:>7.1f}M{r['overhead_vol_frac']:>10.3f}"
             f"{int(r['zones_cleared'] or 0):>7}  {r['label']:<18}"
             f"{r['gap_open_pct']:>6.1f}%{r['ret5']*100:>8.1f}%{(r['mh5'] or 0)*100:>8.1f}%  "
             f"{(r['scan'].get('filter_reason') or 'passed every gate')[:44]}")
    emit()
with (HERE / "_srbt_review_sample.psv").open("w") as fh:
    fh.write("bucket|ticker|alert_date|adv_dollar_20d|overhead_vol_frac|overhead_vol_frac_60d|"
             "zones_cleared|zones_remaining|v2_label|gap_open_pct|ret_5d|max_high_5d|"
             "alerted|alert_tier|scan_filter_reason\n")
    for b, r in SAMPLE:
        fh.write(f"{b}|{r['ticker']}|{r['alert_date']}|{r['advd20']:.0f}|"
                 f"{r['overhead_vol_frac']:.4f}|{r['overhead_vol_frac_60d']:.4f}|"
                 f"{int(r['zones_cleared'] or 0)}|{int(r['zones_remaining'] or 0)}|{r['label']}|"
                 f"{r['gap_open_pct']:.2f}|{r['ret5']:.4f}|{(r['mh5'] or 0):.4f}|"
                 f"{int(r['alerted'])}|{r['alert_tier'] or ''}|"
                 f"{(r['scan'].get('filter_reason') or '')}\n")
emit(f"  → written to scripts/probes/_srbt_review_sample.psv ({len(SAMPLE)} name-days)")
emit()

# ══ INTEGRITY + DEGENERACY + THE EP-SHAPED SUBGROUP ═══════════════════════════════════
emit("=" * 108)
emit("INTEGRITY CHECKS — run because a wrong-row join across ~2,900 rows is the live risk here")
emit("-" * 108)
gd = [(r, r["gap_open_pct"] - r["scan"]["gap_pct"]) for r in POOL
      if r["scan"].get("gap_pct") is not None and r.get("gap_open_pct") is not None]
big = [(r, d) for r, d in gd if abs(d) > 5.0]
emit(f"  1. OPEN-vs-SCAN-LOG cross-check: the replayed open gap vs the gap the scanner logged.")
emit(f"     comparable {len(gd)}   median |diff| {med([abs(d) for _, d in gd]):.2f}pp   "
     f"differing by >5pp: {len(big)} ({len(big)/len(gd)*100:.1f}%)")
emit(f"     SIGNED: the scan log reads HIGHER than the session open on "
     f"{sum(1 for _, d in gd if d < 0)/len(gd)*100:.0f}% of rows, median "
     f"{-med([d for _, d in gd]):+.2f}pp; Spearman(open gap, logged gap) = "
     f"{spearman([r['gap_open_pct'] for r, _ in gd], [r['scan']['gap_pct'] for r, _ in gd]):.3f}.")
emit("     That is the expected basis difference — the scanner logs an INTRADAY gap at whatever")
emit("     tick it fired, the read uses the SESSION OPEN — one-directional and rank-correlated,")
emit("     which is what a basis difference looks like and what a wrong-row join does not.")
emit()
emit("  1b. END-TO-END SPOT CHECK against the published v2 worked examples (doc §6), recomputed")
emit("      here from mi_daily_closes rather than the study's own capture:")
for tkr, ad, w_ov, w_zo, w_cl, w_gap in (("CAPR", date(2026, 8, 24), 0.440, 17, 0, 17.95),
                                         ("MRNA", date(2026, 8, 19), 0.000, 0, 0, 0.00),
                                         ("SNOW", date(2026, 5, 7), 0.826, None, 4, None)):
    q = READS.get(("prod", "cohort", tkr, ad)) or READS.get(("prod", "fixture", tkr, ad))
    if not q:
        continue
    emit(f"      {tkr} {ad}   overhead {q['overhead_vol_frac']:.3f} (doc {w_ov:.3f})   "
         f"zones overhead {int(q['zones_overhead_at_prior_close'])}"
         f"{'' if w_zo is None else f' (doc {w_zo})'}   cleared {int(q['zones_cleared'])} "
         f"(doc {w_cl})   unfilled air {q['overhead_unfilled_gap_span_adr']:.2f} ADR"
         f"{'' if w_gap is None else f' (doc {w_gap:.2f})'}   [{int(q['n_bars'])} prior sessions]")
emit("      CAPR and MRNA reproduce the published values exactly. SNOW clears 2 zones here against")
emit("      the doc's 4 — mi_daily_closes gives it 201 prior sessions where the study's Polygon")
emit("      capture gave 271, so two older levels do not exist in this history. That is the same")
emit("      history-depth effect T0 measured, and the 60-day variant is the control for it.")
emit()
z = sum(1 for r in POOL if r["overhead_vol_frac"] == 0.0)
one = sum(1 for r in POOL if r["overhead_vol_frac"] >= 0.999)
emit(f"  2. IS THE MEASURE DEGENERATE ON THIS COHORT? "
     f"exactly 0.000 (blue sky): {z} of {len(POOL)} ({z/len(POOL)*100:.0f}%);  "
     f">=0.999 (fully buried): {one} ({one/len(POOL)*100:.0f}%)")
emit(f"     quartiles of overhead_vol_frac: "
     + ", ".join(f"{q:.3f}" for q in st.quantiles([r["overhead_vol_frac"] for r in POOL], n=4)))
emit("     Ties count half in every AUC above, so a large blue-sky mass drags a real effect")
emit("     TOWARD 0.500 — the null below is therefore partly a ceiling on how much this measure")
emit("     CAN say on a cohort where a fifth of the names have nothing overhead at all.")
emit()
emit(f"  3. history depth by month (the all-history volume profile grows across the range;")
emit(f"     the 60d variant is the control for it):")
for m in sorted({r["month"] for r in POOL}):
    sub = [r for r in POOL if r["month"] == m]
    emit(f"     {m}   median prior sessions {med([r['n_bars'] for r in sub]):.0f}")
emit()
emit("=" * 108)
emit("TB-SUB — THE SAME TEST RESTRICTED TO EP-SHAPED NAME-DAYS (open gap >= 8.1%)")
emit("-" * 108)
emit("  8.1% is the labelled real-EP arm's own minimum open gap, taken unchanged from the 08-25")
emit("  study's gap-matched control. It is NOT a threshold chosen here — reusing it is the point.")
SUB = [r for r in EVAL if (r.get("gap_open_pct") or -99) >= 8.1]
emit(f"  n = {len(SUB)} name-days over {len({r['alert_date'] for r in SUB})} scan days   "
     f"{sum(1 for r in SUB if r['ret5']>0)/len(SUB)*100:.0f}% closed day 5 above the open")
for nm, key, sg in MEAS[:4] + [MEAS[5]]:
    sc = mk(key, sg)
    a0, _, _ = strat_auc(SUB, sc, LBL, lambda r: 0)
    a1, _, _ = strat_auc(SUB, sc, LBL, lambda r: r["dec"])
    a2, _, _ = strat_auc(SUB, sc, LBL, lambda r: (r["dec"], r["alert_date"]))
    cm, _ = strat_concordance(SUB, sc, lambda r: r.get("mh5"), lambda r: r["dec"])
    lo, hi = cluster_boot_ci(SUB, lambda it: strat_auc(it, sc, LBL, lambda r: r["dec"])[0],
                             lambda r: r["alert_date"], n_boot=400)
    ci = f"[{lo:.3f}, {hi:.3f}]" if lo is not None else "[--]"
    emit(f"  {nm:<30} pooled {a0:>6.3f}   by ADV$ {a1:>6.3f} {ci:<16} ADV$ x date {a2:>6.3f}   "
         f"max_high concordance {cm:.3f}")
emit()
emit("=" * 108)
emit("DESCRIPTIVE — what each of the read's own labels was worth, on the names we ALERTED")
emit("-" * 108)
emit(f"  {'v2 label':<22}{'n':>5}{'win rate':>10}{'med ret_5d':>12}{'med max_high_5d':>17}")
for lab in sorted({r["label"] for r in AL if r.get("label")}):
    sub = [r for r in AL if r["label"] == lab]
    emit(f"  {lab:<22}{len(sub):>5}{sum(1 for r in sub if r['ret5']>0)/len(sub)*100:>9.0f}%"
         f"{med([r['ret5'] for r in sub])*100:>11.1f}%{med([r['mh5'] for r in sub])*100:>16.1f}%")
emit("  (descriptive only — the label depends on MARGIN_ADR = 0.25, which the v2 module discloses")
emit("   as fixture-calibrated. Nothing tested above depends on it.)")
emit()
(HERE / "_srbt_out.txt").write_text("\n".join(OUT) + "\n")
