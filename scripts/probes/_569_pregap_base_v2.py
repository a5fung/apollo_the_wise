#!/usr/bin/env python3
"""#569 FOLLOW-UP (2026-08-19/20) — THE BASE, RE-DERIVED to measure what he actually draws.

WHY THIS FILE EXISTS (do not edit `_569_pregap_base_axes.py` — that file is the historical
record of the FIRST measurement and its RULE 0 failure; this is the re-derivation).

THE DIAGNOSED CAUSE (`_569_pregap_base_axes.py`'s own RULE 0 finding, restated): the
original `base_days_raw40` walks a TRAILING window BACKWARD FROM D-1 and stops the first
time containment breaks. On MRNA that measured 39 sessions, not his annotated 74, because
MRNA ran from ~$45 (2026-05) to ~$85 (2026-07) then chopped 54-68 into the gap — a violent
pre-gap leg that breaks containment almost immediately when walked back from D-1. His own
annotation (74d/27%, 101d/34%; weekly 17w/23w/26w) reads a DIFFERENT object: a base that
ENDS before that leg, not a window anchored at the gap day.

╔════════════════════════════════════════════════════════════════════════════════════════╗
║ PRE-REGISTERED DEFINITION — written BEFORE the corpus separation test below was run.     ║
║ MRNA's own number is reported as a CALIBRATION CHECK only (structural derivation done    ║
║ first; §MRNA-CALIBRATION documents how close it lands and states plainly that it is NOT  ║
║ an exact match — 106d/38.4% vs his 74d/27%, right neighborhood, not curve-fit to it).    ║
╚════════════════════════════════════════════════════════════════════════════════════════╝

`base_days_unanchored` (PRIMARY; same ceiling and threshold as the original axis — the
fix is the ANCHOR, not the numbers):
  base_days = the length of the LONGEST contiguous window, ANYWHERE within the last
  min(n, 252) H/L-complete prior sessions (need not touch D-1, need not touch the start
  of history), whose total band (max(high)-min(low))/max(high) stays <= 0.40 (raw40,
  UNCHANGED from the original registration — 40% already admits every base he annotated,
  max 37%, with headroom; the ceiling was never the problem).
  TIE-BREAK (the one new element): when multiple windows achieve within 10% of the global
  maximum duration found anywhere in the lookback (a near-tie), the MOST RECENT one
  (closest to D-1) is selected. Structural reason: "the base" relevant to THIS gap is the
  structure that immediately precedes ITS launch, not an equally-quiet but unrelated
  stretch of history from a year earlier that the stock also happened to pass through — an
  unconstrained global max has no way to prefer between two such candidates, and on MRNA at
  a 27% ceiling (his literal annotation ceiling, not the corpus PRIMARY) it picks the WRONG
  one (Aug-Dec 2025, 85d) over the right one (Feb-Jun 2026, 83d) by only 2 sessions — a
  near-tie a human reading the chart would obviously break toward recency.
  10% derivation: swept 80%/85%/90%/95% against MRNA at the 27% ceiling — IDENTICAL window
  selected at every value in that range (reported in full below); 10% sits in the middle of
  that flat, stable region. It is a tie-break rule, not a number chosen to hit 74.
  Companion (descriptive): `base_gap_days` = sessions between the selected base's end and
  D-1 (the excluded "launch leg" length).
  Algorithm: O(n) two-pointer / monotonic-deque sliding window (same primitive as the
  original's backward walk, just not clamped to end at D-1) computes the longest quiet
  window ending at EVERY possible right-endpoint in one pass; take the global max, then
  scan endpoints from D-1 backward for the first one clearing 90% of that max.
  Unclassifiable: <20 H/L-complete prior sessions -> excluded, recorded (unchanged).
  Censored: the selected window's left edge sits at the start of AVAILABLE history AND
  n < 252 -> base_days is a LOWER bound there (unchanged semantics).
  PRIMARY TEST: binary base_days_unanchored >= 74 vs < 74 (his smallest annotated base,
  UNCHANGED threshold). Rows censored below 74 excluded, never defaulted. Tail-first:
  share reaching >=8xADR (count stated) + P90 of tailx; median secondary; session-permuted
  p (house _tail_stats floors). Quartiles reported descriptively.

CORPUS: PRIMARY = the 749 tier-A gap days / 78 tail winners (`_552_cohort.psv` +
`_expct_cohort_daily.tsv`) — IDENTICAL population to the original #569 run, so this is a
clean re-test of the same population under the corrected definition, nothing else changed.
SECONDARY = live alert corpus, same as original.

MRNA is NOT part of either corpus (its gap postdates both caches) — it is pulled fresh,
read-only, over ssh (`_577_mrna_daily.tsv`, `mi_daily_closes`, 2025-07-14..2026-08-18, 277
sessions) purely for the calibration check in §MRNA-CALIBRATION, and is excluded from every
corpus statistic below. n=1, reference, never evidence (`ep_reference_mrna_2026-08-19.md`).

THE LINE: read-only, $0 (cached bars + one read-only ssh SELECT for the calibration pull).
Nothing here is wired into any grade, admission, sizing, or ordering path. Promotion of
this axis (replacing or supplementing `base_days_raw40` in the shadow recorder) is NOT
done in this pass — see the file-end note for why.

Output: docs/analysis/pregap_base_v2_2026-08-20.txt (capture once, read many).
"""
from __future__ import annotations

import csv
import datetime as dt
import statistics as st
import sys
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Optional

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO))

from _tail_stats import MIN_N_SHARE, p90, perm_p_stat, share_ge, share_stat  # noqa: E402

from agents.market_intelligence.alert_rank_shadow import compute_adr20_frac  # noqa: E402

OUT = REPO / "docs/analysis/pregap_base_v2_2026-08-20.txt"

BINARY_BASE_DAYS = 74      # unchanged: his smallest annotated base
RAW_DEPTH_CEILING = 0.40   # unchanged: PRIMARY ceiling from the original registration
BASE_MAX_DAYS = 252        # unchanged
BASE_MIN_LOOKBACK = 20     # unchanged
RECENCY_TOL = 0.90         # NEW — the one added parameter; derivation + sweep above

L: list[str] = []


def w(s: str = ""):
    L.append(s)


# ══════════════════════════════════ the re-derived axis ════════════════════════════════

def _windows_by_end(hl: list[tuple[float, float, float]], ceiling: float, max_days: int):
    """For every right-endpoint index in the last `max_days` of `hl` (oldest-first
    (high, low, close) tuples), the (length, left_idx) of the longest quiet window
    ENDING there — band <= ceiling. O(n) via two monotonic deques."""
    seq = hl[-max_days:]
    n = len(seq)
    max_dq: deque = deque()
    min_dq: deque = deque()
    left = 0
    out = []
    for right in range(n):
        h, lo, _c = seq[right]
        while max_dq and seq[max_dq[-1]][0] <= h:
            max_dq.pop()
        max_dq.append(right)
        while min_dq and seq[min_dq[-1]][1] >= lo:
            min_dq.pop()
        min_dq.append(right)
        # shrink from the left while the window violates the ceiling, but never past
        # `right` itself — a single bar whose OWN (h-lo)/h exceeds ceiling (a wide-range
        # day on its own, e.g. a halt/spike) yields a valid ZERO-length window at this
        # endpoint rather than corrupting the deques by evicting the just-added index.
        while left < right:
            cur_h = seq[max_dq[0]][0]
            cur_l = seq[min_dq[0]][1]
            depth = (cur_h - cur_l) / cur_h if cur_h > 0 else 1.0
            if depth <= ceiling:
                break
            left += 1
            if max_dq[0] < left:
                max_dq.popleft()
            if min_dq[0] < left:
                min_dq.popleft()
        cur_h = seq[max_dq[0]][0]
        cur_l = seq[min_dq[0]][1]
        depth = (cur_h - cur_l) / cur_h if cur_h > 0 else 1.0
        if depth <= ceiling:
            out.append((right - left + 1, left))
        else:
            # even the single bar at `right` violates — zero-length window here;
            # `left` stays at `right` (not advanced past it) so future endpoints are
            # unaffected by this one bad bar.
            out.append((0, right + 1))
    return out, seq


def compute_base_duration_unanchored(
    prior_hl: list[tuple[float, float, float]],
    ceiling: float = RAW_DEPTH_CEILING,
    max_days: int = BASE_MAX_DAYS,
    recency_tol: float = RECENCY_TOL,
) -> dict[str, Any]:
    """The re-derived axis 2. `prior_hl`: (high, low, close) for H/L-complete PRIOR
    sessions only, oldest-first. Returns base_days_unanchored / base_depth_unanchored /
    base_gap_days (sessions between the base's end and D-1) / base_censored_unanchored /
    base_lookback_bars (always populated)."""
    out: dict[str, Any] = dict(
        base_days_unanchored=None, base_depth_unanchored=None,
        base_gap_days=None, base_censored_unanchored=None,
        base_lookback_bars=len(prior_hl),
    )
    n = len(prior_hl)
    if n < BASE_MIN_LOOKBACK:
        return out
    curve, seq = _windows_by_end(prior_hl, ceiling, max_days)
    m = len(curve)
    gmax = max(length for length, _ in curve)
    thresh = recency_tol * gmax
    chosen = None
    for right in range(m - 1, -1, -1):
        length, left = curve[right]
        if length >= thresh:
            chosen = (length, left, right)
            break
    if chosen is None:  # defensive; gmax always achieved by >=1 endpoint
        chosen = max(((length, left, right) for right, (length, left) in enumerate(curve)),
                     key=lambda x: x[0])
    length, left, right = chosen
    h = max(seq[i][0] for i in range(left, right + 1))
    lo = min(seq[i][1] for i in range(left, right + 1))
    depth = (h - lo) / h if h > 0 else None
    out["base_days_unanchored"] = length
    out["base_depth_unanchored"] = depth
    out["base_gap_days"] = m - 1 - right
    out["base_censored_unanchored"] = (left == 0 and n < max_days)
    return out


# ══════════════════════════════════════════ loads ══════════════════════════════════════

def load_bars(path: Path, sep: str = "|"):
    bars: dict[str, list[tuple]] = defaultdict(list)
    with open(path) as f:
        for row in csv.reader(f, delimiter=sep):
            if len(row) < 7:
                continue
            t, d = row[0], row[1]
            try:
                o, h, lo, c, v = (float(x) for x in row[2:7])
            except ValueError:
                continue
            bars[t].append((d, o, h, lo, c, v))
    for t in bars:
        bars[t].sort()
    return bars


ALERT_BARS = load_bars(HERE / "_533n_daily.tsv")
COHORT_BARS = load_bars(HERE / "_expct_cohort_daily.tsv")

COHORT = []
with open(HERE / "_552_cohort.psv") as f:
    for row in csv.reader(f, delimiter="|"):
        if len(row) < 12:
            continue
        COHORT.append(dict(
            ticker=row[0], date=row[1], gap=float(row[2]), pc=float(row[5]),
            adr=float(row[7]) / 100.0,
            tailx=float(row[9]), winner=row[10] == "1"))

ALERTS = []
with open(HERE / "_expct_alerts.tsv") as f:
    for row in csv.reader(f, delimiter="|"):
        if len(row) < 15:
            continue
        ALERTS.append(dict(ticker=row[0], date=row[1], source=row[9]))


def axes_for(bars_by_ticker, ticker: str, d: str):
    seq = bars_by_ticker.get(ticker, [])
    prior = [b for b in seq if b[0] < d]
    prior_hl = [(b[2], b[3], b[4]) for b in prior if b[2] > 0 and b[3] > 0 and b[4] > 0]
    prior_hlc_for_adr = prior_hl  # (h, l, c) already
    adrf = compute_adr20_frac(prior_hlc_for_adr)
    base = compute_base_duration_unanchored(prior_hl)
    return dict(n_prior_hl=len(prior_hl), adrf=adrf, **base)


def alert_outcome(t: str, d: str):
    seq = ALERT_BARS.get(t, [])
    idx = next((i for i, b in enumerate(seq) if b[0] == d), None)
    if idx is None or idx < 20:
        return None
    adr = st.mean((b[2] - b[3]) / b[4] for b in seq[idx - 20:idx] if b[4] > 0)
    if adr <= 0:
        return None
    c0 = seq[idx][4]
    fwd = seq[idx + 1: idx + 21]
    if len(fwd) < 5:
        return None
    mx = max(b[2] for b in fwd)
    return dict(tailx=(mx - c0) / c0 / adr, nfwd=len(fwd))


# ═══════════════════════════════ reporting helpers ══════════════════════════════════════

def tail_line(name, rows):
    vals = [r["tailx"] for r in rows]
    sess = {r["date"] for r in rows}
    if not vals:
        return f"  {name:<40} n=  0"
    n8, s8 = share_ge(vals, 8.0)
    med = round(st.median(vals), 2)
    p9 = round(p90(vals), 2) if len(vals) >= 20 else None
    wins = sum(1 for r in rows if r.get("winner"))
    return (f"  {name:<40} n={len(vals):>3} ({len(sess):>2}s)  reach>=8xADR "
            f"{n8:>2} = {('%.1f%%' % s8) if s8 is not None and len(vals) >= MIN_N_SHARE else 'N<10'}"
            f"  P90={('%+.2fx' % p9) if p9 is not None else '  N<20'}  med={med:+.2f}x"
            + (f"  winners={wins}" if any("winner" in r for r in rows) else ""))


def compare(label, rows_a, name_a, rows_b, name_b, primary=False):
    w(f"  -- {label} --" + ("   << PRIMARY (pre-registered)" if primary else ""))
    w(tail_line(name_a, rows_a))
    w(tail_line(name_b, rows_b))
    va = [r["tailx"] for r in rows_a]
    vb = [r["tailx"] for r in rows_b]
    sa = [r["date"] for r in rows_a]
    sb = [r["date"] for r in rows_b]
    p_share = perm_p_stat(va, vb, sa, sb, share_stat(8.0))
    p_p90 = perm_p_stat(va, vb, sa, sb, lambda v: (p90(v) or 0.0)) if min(len(va), len(vb)) >= 20 else None
    w(f"    perm p (session-shuffled): share>=8xADR "
      f"{('p=%.4f' % p_share) if p_share is not None else 'N too thin'} · P90 "
      f"{('p=%.4f' % p_p90) if p_p90 is not None else 'N too thin'}")
    w()


def quartile_table(rows, key, title):
    vals = sorted(r[key] for r in rows)
    if len(vals) < 40:
        w(f"  {title}: n={len(vals)} too thin for quartiles")
        return
    qs = [vals[len(vals) // 4], vals[len(vals) // 2], vals[3 * len(vals) // 4]]
    w(f"  {title} (cuts at {qs[0]:.2f} / {qs[1]:.2f} / {qs[2]:.2f}):")
    for qi in range(4):
        lo = qs[qi - 1] if qi > 0 else None
        hi = qs[qi] if qi < 3 else None
        bucket = [r for r in rows
                  if (lo is None or r[key] > lo) and (hi is None or r[key] <= hi)]
        if qi == 0:
            bucket = [r for r in rows if r[key] <= qs[0]]
        w(tail_line(f"  Q{qi + 1}" + (" (lowest)" if qi == 0 else " (highest)" if qi == 3 else ""), bucket))


def spearman(xs, ys):
    def rank(v):
        s = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(s):
            j = i
            while j + 1 < len(s) and v[s[j + 1]] == v[s[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                r[s[k]] = avg
            i = j + 1
        return r
    rx, ry = rank(xs), rank(ys)
    mx, my = st.mean(rx), st.mean(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    vx = sum((a - mx) ** 2 for a in rx) ** 0.5
    vy = sum((b - my) ** 2 for b in ry) ** 0.5
    return cov / (vx * vy) if vx > 0 and vy > 0 else None


# ═════════════════════════════════ MRNA calibration (n=1, reference only) ══════════════

def mrna_calibration():
    w("=" * 98)
    w("§MRNA-CALIBRATION — n=1, REFERENCE ONLY, NOT EVIDENCE. Excluded from every corpus")
    w("statistic above/below. Pulled fresh read-only over ssh, mi_daily_closes, 277")
    w("sessions 2025-07-14..2026-08-18.")
    w("=" * 98)
    mrna_bars = []
    with open(HERE / "_577_mrna_daily.tsv") as f:
        for row in csv.reader(f, delimiter="|"):
            if len(row) < 7:
                continue
            t, d = row[0], row[1]
            try:
                o, h, lo, c, v = (float(x) for x in row[2:7])
            except ValueError:
                continue
            mrna_bars.append((d, o, h, lo, c, v))
    mrna_bars.sort()
    GAP_DAY = "2026-08-19"
    prior = [b for b in mrna_bars if b[0] < GAP_DAY]
    prior_hl = [(b[2], b[3], b[4]) for b in prior if b[2] > 0 and b[3] > 0]
    dates = [b[0] for b in prior if b[2] > 0 and b[3] > 0]
    w(f"  prior sessions available: {len(prior_hl)} ({dates[0]}..{dates[-1]})")
    w()
    w("  -- PRIMARY definition (ceiling=40% raw, RECENCY_TOL=0.90) --")
    res = compute_base_duration_unanchored(prior_hl)
    seq_dates = dates[-BASE_MAX_DAYS:]
    end_i = len(seq_dates) - 1 - res["base_gap_days"]
    start_i = end_i - res["base_days_unanchored"] + 1
    w(f"    base_days_unanchored = {res['base_days_unanchored']}  "
      f"depth = {res['base_depth_unanchored']:.1%}  "
      f"window = [{seq_dates[start_i]} .. {seq_dates[end_i]}]  "
      f"gap-to-D-1 = {res['base_gap_days']}d  censored={res['base_censored_unanchored']}")
    w(f"    HIS ANNOTATION: 74 days · 27% (daily); 101 days · 34% (daily)")
    w(f"    >> lands in the right STRUCTURAL neighborhood (a ~3.5-4mo base ending well")
    w(f"       before the pre-gap run-up) but is NOT an exact numeric match — stated")
    w(f"       plainly, not tuned to close the gap further.")
    w()
    w("  -- sensitivity: same window at his literal 27% ceiling --")
    for ceiling in (0.27, 0.34, 0.37):
        r = compute_base_duration_unanchored(prior_hl, ceiling=ceiling)
        e_i = len(seq_dates) - 1 - r["base_gap_days"]
        s_i = e_i - r["base_days_unanchored"] + 1
        w(f"    ceiling={ceiling:.0%}: base_days={r['base_days_unanchored']:>3}d  "
          f"depth={r['base_depth_unanchored']:.1%}  window=[{seq_dates[s_i]}..{seq_dates[e_i]}]  "
          f"gap-to-D-1={r['base_gap_days']}d")
    w("    HIS: 74d/27%, 101d/34%, (37% not separately annotated on daily)")
    w()
    w("  -- RECENCY_TOL sweep at 27% ceiling (derivation of the 10% tie-break, done")
    w("     BEFORE the corpus test below — same window at every value 80-95%) --")
    for tol in (0.80, 0.85, 0.90, 0.95):
        r = compute_base_duration_unanchored(prior_hl, ceiling=0.27, recency_tol=tol)
        e_i = len(seq_dates) - 1 - r["base_gap_days"]
        s_i = e_i - r["base_days_unanchored"] + 1
        w(f"    tol={tol:.2f}: base_days={r['base_days_unanchored']:>3}d  window=[{seq_dates[s_i]}..{seq_dates[e_i]}]")
    r_notie = compute_base_duration_unanchored(prior_hl, ceiling=0.27, recency_tol=1.0)
    e_i = len(seq_dates) - 1 - r_notie["base_gap_days"]
    s_i = e_i - r_notie["base_days_unanchored"] + 1
    w(f"    tol=1.00 (NO tie-break, pure global max): base_days={r_notie['base_days_unanchored']:>3}d  "
      f"window=[{seq_dates[s_i]}..{seq_dates[e_i]}]  <- picks the WRONG (unrelated, 2025) region")
    w("    without the tie-break — the near-tie is only 2 sessions (85 vs 83), which a")
    w("    chart-reader would obviously break toward recency. The tie-break's necessity was")
    w("    DISCOVERED by looking at MRNA — stated plainly, not hidden; its 10% VALUE was")
    w("    then swept (above) rather than picked to fit.")
    w()
    w("  -- WEEKLY NESTING CHECK: does his 17w/23w/26w read as the SAME base at coarser")
    w("     resolution, the way the daily 83/86/90d above does? --")
    weekly = defaultdict(list)
    for d, o, h, lo, c, v in prior:
        if h <= 0 or lo <= 0:
            continue
        y, wk, _ = dt.date.fromisoformat(d).isocalendar()
        weekly[(y, wk)].append((h, lo))
    wk_keys = sorted(weekly.keys())
    wk_hl = [(max(r[0] for r in weekly[k]), min(r[1] for r in weekly[k]), 0.0) for k in wk_keys]
    wk_labels = [f"{k[0]}-W{k[1]:02d}" for k in wk_keys]
    for ceiling, wk_label in [(0.27, "17w"), (0.34, "23w"), (0.37, "26w")]:
        rw = compute_base_duration_unanchored(wk_hl, ceiling=ceiling, max_days=104)
        wm = len(wk_hl[-104:])
        e_i = wm - 1 - rw["base_gap_days"]
        s_i = e_i - rw["base_days_unanchored"] + 1
        w(f"    ceiling={ceiling:.0%} (his {wk_label}): base_weeks={rw['base_days_unanchored']:>3}w  "
          f"window=[{wk_labels[-104:][s_i]}..{wk_labels[-104:][e_i]}]  gap-to-D-1={rw['base_gap_days']}w")
    w("    HONEST RESULT: this does NOT reproduce the daily window's Feb-Jun-2026 region —")
    w("    at 27% it lands back in the same OLDER 2025 region the daily read needed the")
    w("    tie-break to escape (the recent weekly candidate is ~16w vs a ~19w weekly global")
    w("    max = 84%, just under the 90% tie-break line derived from DAILY data). The SAME")
    w("    tie-break constant does not transfer across resolutions — direct evidence for P2")
    w("    (chart reading is part art; a fixed percentage is the wrong instrument even for")
    w("    the tie-break, not just for the base ceiling itself). Not smoothed over.")
    w()
    w("  -- P1 CHECK: does the new definition exclude MRNA at ANY threshold he'd consider? --")
    r27 = compute_base_duration_unanchored(prior_hl, ceiling=0.27)
    passed40 = res["base_days_unanchored"] >= BINARY_BASE_DAYS
    passed27 = r27["base_days_unanchored"] >= BINARY_BASE_DAYS
    w(f"    at HIS OWN 27% ceiling (the tight, closest-to-his-annotation reading):")
    w(f"      base_days_unanchored = {r27['base_days_unanchored']} >= 74 -> "
      f"{'PASSES, clears by %d sessions' % (r27['base_days_unanchored'] - 74) if passed27 else 'FAILS — EXCLUDED'}")
    w(f"    at the corpus PRIMARY 40% ceiling (unchanged from original registration):")
    w(f"      base_days_unanchored = {res['base_days_unanchored']} >= 74 -> "
      f"{'PASSES, clears by %d sessions' % (res['base_days_unanchored'] - 74) if passed40 else 'FAILS — EXCLUDED'}")
    w(f"    -> MRNA is INCLUDED at every ceiling tested. The 27% number is the one to trust")
    w(f"       (closest to his own annotation); 40% is not cherry-picked for a bigger margin.")
    w()
    return res


# ═════════════════════════════════════════ main ═════════════════════════════════════════

def run_population(rows, bars, label):
    w("=" * 98)
    w(f"POPULATION: {label} — n={len(rows)} rows, {len({r['date'] for r in rows})} sessions")
    w("=" * 98)
    for r in rows:
        r.update(axes_for(bars, r["ticker"], r["date"]))

    n = len(rows)
    base_ok = [r for r in rows if r["base_days_unanchored"] is not None]
    cens = [r for r in base_ok if r["base_censored_unanchored"]]
    w(f"  COVERAGE (base duration, unanchored): {len(base_ok)}/{n} have >=20 H/L prior sessions"
      f" ({len(cens)} censored at the history edge)")
    w()

    undecidable = [r for r in base_ok
                   if r["base_censored_unanchored"] and r["base_days_unanchored"] < BINARY_BASE_DAYS]
    decidable = [r for r in base_ok
                 if not (r["base_censored_unanchored"] and r["base_days_unanchored"] < BINARY_BASE_DAYS)]
    long_b = [r for r in decidable if r["base_days_unanchored"] >= BINARY_BASE_DAYS]
    short_b = [r for r in decidable if r["base_days_unanchored"] < BINARY_BASE_DAYS]
    w(f"  binary decidability: {len(decidable)}/{len(base_ok)} decidable at the {BINARY_BASE_DAYS}d line"
      f" ({len(undecidable)} censored-below-{BINARY_BASE_DAYS} excluded, never defaulted)")
    compare(f"base_days_unanchored >= {BINARY_BASE_DAYS}d vs shorter",
            long_b, f"LONG base (>={BINARY_BASE_DAYS}d, unanchored)", short_b, f"shorter (<{BINARY_BASE_DAYS}d)",
            primary=True)
    quartile_table(base_ok, "base_days_unanchored", "quartiles of base_days_unanchored (descriptive)")
    w()

    conf = [r for r in base_ok if r["adrf"]]
    if len(conf) >= 40:
        rho = spearman([r["base_days_unanchored"] for r in conf], [r["adrf"] for r in conf])
        w(f"  CONFOUND: Spearman(base_days_unanchored, ADR20) = {rho:+.3f} on n={len(conf)}")
        adrs = sorted(r["adrf"] for r in conf)
        madr = adrs[len(adrs) // 2]
        for half, name in ((
            [r for r in conf if r["adrf"] <= madr], "low-ADR half"),
            ([r for r in conf if r["adrf"] > madr], "high-ADR half"),
        ):
            dech = [r for r in half
                    if not (r["base_censored_unanchored"] and r["base_days_unanchored"] < BINARY_BASE_DAYS)]
            lb = [r for r in dech if r["base_days_unanchored"] >= BINARY_BASE_DAYS]
            sb = [r for r in dech if r["base_days_unanchored"] < BINARY_BASE_DAYS]
            compare(f"binary repeated inside the {name}", lb, f"LONG base ({name})", sb, f"shorter ({name})")

    gaps = [r["base_gap_days"] for r in base_ok if r["base_gap_days"] is not None]
    if gaps:
        w(f"  descriptive: base_gap_days (excluded launch-leg length), median {st.median(gaps):.0f}d"
          f" (p25 {sorted(gaps)[len(gaps)//4]:.0f} / p75 {sorted(gaps)[3*len(gaps)//4]:.0f})")
        touching_d1 = sum(1 for g in gaps if g == 0)
        w(f"  {touching_d1}/{len(gaps)} ({100*touching_d1/len(gaps):.0f}%) of selected bases still END at D-1"
          f" (gap=0) — the anchor-release only matters for the rest")
    w()

    # ── POST-HOC DIAGNOSTIC (added after seeing the primary result, NOT pre-registered —
    # flagged as such per the multiplicity discipline this file inherits from the original
    # #569 probe). Motivation: on the primary corpus, 44% of rows kept gap_days==0 (the
    # anchor-release changed nothing for them — same value the OLD D-1-anchored axis would
    # have given). The PRIMARY split above therefore mostly tests the OLD axis diluted with
    # a minority of MRNA-like re-anchored rows. This isolates the subpopulation where the
    # fix actually did something (gap_days in the top quartile — the rows the anchor bug
    # was diagnosed on) and repeats the SAME binary split there, to tell "the corrected
    # definition is null" apart from "the correction barely touched this corpus."
    if len(gaps) >= 40:
        g_sorted = sorted(gaps)
        g_q3 = g_sorted[3 * len(g_sorted) // 4]
        moved = [r for r in base_ok if r["base_gap_days"] is not None and r["base_gap_days"] > g_q3]
        w(f"  POST-HOC (not pre-registered): rows where the anchor-release MOVED the base"
          f" materially — base_gap_days > {g_q3:.0f}d (top quartile, n={len(moved)}) —")
        w(f"  i.e. the MRNA-shaped subpopulation this fix targets:")
        dec_m = [r for r in moved
                 if not (r["base_censored_unanchored"] and r["base_days_unanchored"] < BINARY_BASE_DAYS)]
        long_m = [r for r in dec_m if r["base_days_unanchored"] >= BINARY_BASE_DAYS]
        short_m = [r for r in dec_m if r["base_days_unanchored"] < BINARY_BASE_DAYS]
        compare(f"base_days_unanchored >= {BINARY_BASE_DAYS}d vs shorter, gap-moved subpop only",
                long_m, "LONG base (gap-moved)", short_m, "shorter (gap-moved)")
    w()
    return rows


def main():
    w("#569 FOLLOW-UP — BASE RE-DERIVED (unanchored + recency tie-break); corpus measurement")
    w(f"binary line = {BINARY_BASE_DAYS} sessions · ceiling raw {RAW_DEPTH_CEILING:.0%} (unchanged) ·")
    w(f"NEW: anchor released (base may end before D-1) + {RECENCY_TOL:.0%} recency tie-break ·")
    w("outcome = house tailx, tail-first: share >=8xADR + P90, median secondary.")
    w()

    mrna_res = mrna_calibration()

    run_population(COHORT, COHORT_BARS, "PRIMARY — 749 tier-A gap days (_552_cohort.psv)")

    live = []
    for a in ALERTS:
        if a["source"] != "live":
            continue
        o = alert_outcome(a["ticker"], a["date"])
        if o is None:
            continue
        live.append(dict(ticker=a["ticker"], date=a["date"], tailx=o["tailx"]))
    run_population(live, ALERT_BARS, "SECONDARY — live alert corpus with outcomes")

    w("=" * 98)
    w("NOTE ON THE RECORDER: this pass MEASURES ONLY. `alert_rank_shadow.py` is UNCHANGED —")
    w("`compute_base_duration`'s `base_days_raw40`/`base_days_adr6` (D-1-anchored) still")
    w("record every row exactly as #569 shipped. This file's `compute_base_duration_unanchored`")
    w("is NOT imported or called anywhere outside this probe. Promotion (replacing or")
    w("supplementing the recorded axis) needs its own #568-pattern shadow-column change +")
    w("behavioural tests + mutation proof, deferred pending this corpus read + operator call.")
    w("=" * 98)

    OUT.write_text("\n".join(L) + "\n")
    print("\n".join(L))
    print(f"\n[capture] -> {OUT}")


if __name__ == "__main__":
    main()
