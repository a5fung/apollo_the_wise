#!/usr/bin/env python3
"""#354 C1 — D3 cohort: undercut→INVALIDATED bases, reclaim + forward-R probe (read-only).

ADR 0026 §D3. The change under test (NOT implemented — this evidence gates it): close <
base_low_close routes to WATCH_UR (base retained, age clock running toward the 25d cap) instead
of INVALIDATED; WATCH_UR's trigger = base-low reclaim (close back above base_low_close) → U&R
entry, stop = undercut low.

Ship rule (ADR 0026:94-95): reclaim-cohort forward R positive at N>=10 AND false-revival rate
(reclaim → immediate re-undercut) < 40%.

CAUSE ISOLATION — no inference needed. mi_flag_candidates.reason records the exact invalidation
cause; the undercut branch (flag_detector.py:841-843) writes
`close_{c:.2f}_below_base_low_close_{blc:.2f}` (format stable since the detector's first commit,
7bfc1e8). Prod recon 2026-07-26: INVALIDATED rows collapse to exactly two reason shapes —
`close_#_below_base_low_close_#` (1,628 rows = undercut) and `close_#_below_sma#_#` (1,079 =
MA loss). The frozen base_low_close is parsed from the reason string (2dp precision) because the
column does not exist and the LIVE value is recomputed daily (see FREEZE HAZARD below).

METHODOLOGY (each choice sensitivity-checked in the report):
  * Event = first undercut-INVALIDATED row per (ticker, pivot_high_date); consecutive
    under-water rows for the same base are the same event (pivots carry forward regardless of
    stage — get_yesterday_flag_pivots has no stage filter — so a sunk base re-emits daily).
  * Episode dedup: under D3 a base in WATCH_UR stays ONE base — a same-ticker "new" event whose
    undercut day falls inside a prior event's still-open window only exists because INVALIDATED
    killed the base and the machine re-anchored; dropped (raw vs deduped N both reported).
  * Reclaim = first daily close STRICTLY ABOVE the FROZEN base_low_close, within the remaining
    age window W = 25 - base_age_at_undercut trading days (age clock uninterrupted per D3; the
    age-cap check at flag_detector.py:837 precedes the undercut branch, so it still kills).
  * FREEZE HAZARD (measured as a variant): the code recomputes base_low_close from base_rows
    daily; once the undercut day enters the base window the running min IS the undercut close,
    so a minimal-diff C3 would trigger "reclaim" on the first non-new-closing-low day. The
    RUNNING-min variant is reported to show how degenerate that is; C3 must freeze the level.
  * Stop = undercut low = min(intraday low) over undercut day → reclaim day INCLUSIVE (known at
    the reclaim close, no lookahead; the classic spring makes its low the day it reclaims).
    Variant B: undercut-day low only.
  * R horizon = 10 trading days, fixed stop, stop-first ('pess': any low <= stop → -1.0R), else
    R at the horizon close — IDENTICAL to _146_triggered_gate_backtest.py's settle(), the other
    C1 cohort ("both cohorts settled identically", ADR 0026 §C1). STRICT settlement (needs a
    stop-out or the full 10 bars; else censored) is primary; _146's lenient partial-window
    settle also reported.
  * "Immediate" re-undercut = close back below the frozen base_low_close within K=5 trading
    days of the reclaim (the family's 5-bar settlement window, anticipation.SETTLE_FORWARD_BARS
    — the horizon at which this family judges an entry event). Full K-curve {1,2,3,5,10}
    reported because the ship rule turns on this choice.

DATA (read-only pulls; ssh apollo@87.99.134.162, docker exec apollo-postgres psql -U apollo -d apollo):
  _354_undercut_events.tsv:
    COPY (SELECT DISTINCT ON (ticker, pivot_high_date) ticker, scan_date, pivot_high_date,
            pivot_high_price, base_age, base_high, base_low, sma_20, sma_10, reason
          FROM mi_flag_candidates
          WHERE stage='INVALIDATED' AND reason ~ '^close_[0-9.]+_below_base_low_close_[0-9.]+'
          ORDER BY ticker, pivot_high_date, scan_date)
    TO STDOUT WITH (FORMAT csv, DELIMITER E'\t', HEADER true, NULL '')
  _354_stage_history.tsv:
    COPY (SELECT ticker, scan_date, pivot_high_date, stage FROM mi_flag_candidates
          ORDER BY ticker, scan_date) TO STDOUT WITH (...)
  _354_daily_bars.tsv:
    COPY (SELECT d.ticker, d.trade_date, d.open_price, d.high_price, d.low_price, d.close,
                 d.volume
          FROM mi_daily_closes d
          WHERE d.ticker IN (SELECT DISTINCT ticker FROM mi_flag_candidates
                             WHERE stage='INVALIDATED'
                               AND reason ~ '^close_[0-9.]+_below_base_low_close_[0-9.]+')
          ORDER BY d.ticker, d.trade_date) TO STDOUT WITH (...)

Run:  python scripts/probes/_354_undercut_reclaim_probe.py
"""
from __future__ import annotations

import csv
import random
import re
import statistics
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent

AGE_CAP = 25                 # flag_detector._BASE_AGE_MAX
HORIZON = 10                 # trading days — matches _146_triggered_gate_backtest.HORIZON
REVIVAL_K = 5                # primary "immediate" window (family 5-bar settle window)
REVIVAL_CURVE = (1, 2, 3, 5, 10)
HTF_REGIME_START = date(2026, 6, 28)   # #356 HTF 90/40 universe flip (Gemini 6/27 guards)
QUALIFIED = {"WATCH", "TIGHTENING", "COILED", "TRIGGERED"}

_REASON_RE = re.compile(r"^close_([0-9.]+)_below_base_low_close_([0-9.]+)$")


def _d(s: str) -> date:
    return date.fromisoformat(s)


def load_tsv(name: str) -> list[dict]:
    with open(HERE / name, newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def sma(closes: list[float], idx: int, window: int):
    """Mean close over the `window` bars ending at idx inclusive; None if short (detector _sma)."""
    if idx + 1 < window:
        return None
    seg = closes[idx + 1 - window: idx + 1]
    return sum(seg) / window


def settle(fwd, entry: float, stop: float, strict: bool):
    """fwd = bars STRICTLY AFTER the reclaim day. Same geometry as _146's settle():
    stop-first over the first HORIZON bars, else R at the horizon close.
    strict=True → censored (None) unless a stop-out occurred or all HORIZON bars exist."""
    risk = entry - stop
    if risk <= 0 or not fwd:
        return None
    window = fwd[:HORIZON]
    for b in window:
        if b["low"] <= stop:
            fwd_max = (max(x["high"] for x in window) - entry) / risk
            return (-1.0, fwd_max, "stop")
    if strict and len(window) < HORIZON:
        return None
    fwd_max = (max(x["high"] for x in window) - entry) / risk
    return ((window[-1]["close"] - entry) / risk, fwd_max, "horizon")


def stats_line(rs: list[float]) -> str:
    if not rs:
        return "n=  0"
    winners = [r for r in rs if r > 0]
    return (f"n={len(rs):>3}  mean={statistics.mean(rs):+5.2f}R  "
            f"median={statistics.median(rs):+5.2f}R  total={sum(rs):+7.1f}R  "
            f"win={100 * len(winners) / len(rs):3.0f}%  "
            f"avg-winner={statistics.mean(winners) if winners else 0.0:+5.2f}R  "
            f"min={min(rs):+5.2f}R  max={max(rs):+5.2f}R")


def main() -> int:
    events_raw = load_tsv("_354_undercut_events.tsv")
    stage_hist = load_tsv("_354_stage_history.tsv")
    bars_raw = load_tsv("_354_daily_bars.tsv")

    bars: dict[str, list[dict]] = defaultdict(list)
    for r in bars_raw:
        bars[r["ticker"]].append({
            "date": _d(r["trade_date"]), "open": float(r["open_price"]),
            "high": float(r["high_price"]), "low": float(r["low_price"]),
            "close": float(r["close"]), "volume": float(r["volume"] or 0)})
    idx_of = {t: {b["date"]: i for i, b in enumerate(bs)} for t, bs in bars.items()}
    data_end = max(b[-1]["date"] for b in bars.values())

    # stage history keyed for prior-stage classification
    hist_by_ticker: dict[str, list[dict]] = defaultdict(list)
    for r in stage_hist:
        hist_by_ticker[r["ticker"]].append(r)

    # ── build events ────────────────────────────────────────────────────────
    events, skipped = [], defaultdict(int)
    for r in events_raw:
        m = _REASON_RE.match(r["reason"])
        if not m:
            skipped["reason_unparseable"] += 1
            continue
        t, sd = r["ticker"], _d(r["scan_date"])
        ui = idx_of.get(t, {}).get(sd)
        if ui is None:
            skipped["no_bar_on_undercut_day"] += 1
            continue
        base_age = int(r["base_age"])
        if base_age > AGE_CAP:       # cannot happen (age check precedes undercut check) — assert
            skipped["age_over_cap"] += 1
            continue
        # prior-stage context (rows strictly before the undercut scan)
        same_pivot = [h for h in hist_by_ticker[t]
                      if h["pivot_high_date"] == r["pivot_high_date"] and _d(h["scan_date"]) < sd]
        best_prior = max((h["stage"] for h in same_pivot if h["stage"] in QUALIFIED),
                         key=lambda s: ["WATCH", "TIGHTENING", "COILED", "TRIGGERED"].index(s),
                         default=None)
        recent_q = any(h["stage"] in QUALIFIED and sd > _d(h["scan_date"]) >= sd.fromordinal(sd.toordinal() - 14)
                       for h in hist_by_ticker[t])
        events.append({
            "ticker": t, "date": sd, "ui": ui, "base_age": base_age,
            "window": AGE_CAP - base_age,
            "undercut_close": float(m.group(1)), "frozen_blc": float(m.group(2)),
            "pivot_high": float(r["pivot_high_price"]),
            "pivot_date": r["pivot_high_date"],
            "best_prior": best_prior, "recent_qualified": recent_q,
            "post_htf": sd >= HTF_REGIME_START})
    events.sort(key=lambda e: (e["ticker"], e["date"]))

    # ── episode dedup: drop an event opening inside a prior same-ticker open window ─────────
    deduped, dropped_overlap = [], 0
    open_until: dict[str, int] = {}       # ticker → bar index the prior window runs to
    for e in events:
        if e["ticker"] in open_until and e["ui"] <= open_until[e["ticker"]]:
            dropped_overlap += 1
            continue
        open_until[e["ticker"]] = e["ui"] + e["window"]
        deduped.append(e)

    # ── measure each event ─────────────────────────────────────────────────
    for e in deduped:
        bs, ui, W = bars[e["ticker"]], e["ui"], e["window"]
        blc = e["frozen_blc"]
        avail = len(bs) - 1 - ui                      # observed forward bars
        e["reclaim_k"] = None
        e["outcome"] = None
        for k in range(1, min(W, avail) + 1):
            if bs[ui + k]["close"] > blc:
                e["reclaim_k"] = k
                break
        if e["reclaim_k"] is None:
            if W <= 0:
                e["outcome"] = "window_exhausted"     # undercut at age 25 — no room
            elif avail < W:
                e["outcome"] = "censored_window"      # too recent to observe full window
            else:
                e["outcome"] = "no_reclaim"
            continue
        k = e["reclaim_k"]
        ri = ui + k
        e["outcome"] = "reclaimed"
        e["entry"] = bs[ri]["close"]
        e["ul_a"] = min(b["low"] for b in bs[ui:ri + 1])       # primary stop
        e["ul_b"] = bs[ui]["low"]                               # variant: undercut-day low only
        fwd = bs[ri + 1:]
        e["settle_a"] = settle(fwd, e["entry"], e["ul_a"], strict=True)
        e["settle_a_len"] = settle(fwd, e["entry"], e["ul_a"], strict=False)
        e["settle_b"] = settle(fwd, e["entry"], e["ul_b"], strict=True)
        # false revival: close back below frozen blc within K of the reclaim
        e["reundercut_k"] = None
        for j in range(1, min(len(fwd), max(REVIVAL_CURVE)) + 1):
            if fwd[j - 1]["close"] < blc:
                e["reundercut_k"] = j
                break
        e["fwd_observed"] = len(fwd)
        # F2-faithfulness: would the reclaim day survive the OTHER invalidation gates?
        closes = [b["close"] for b in bs]
        s20, s50, s200 = sma(closes, ri, 20), sma(closes, ri, 50), sma(closes, ri, 200)
        c = e["entry"]
        e["sma_ok"] = all(s is None or c >= s for s in (s20, s50, s200))
        pi_idx = ui - e["base_age"] - 1               # pivot bar index (base_age bars between)
        run_low = min(b["low"] for b in bs[max(pi_idx + 1, 0):ri]) if ri > pi_idx + 1 else None
        e["depth_ok"] = run_low is not None and run_low >= 0.75 * e["pivot_high"]
        # RUNNING-min variant (the literal-code hazard): first non-new-closing-low day
        e["running_reclaim_k"] = None
        rmin = min(closes[max(pi_idx + 1, 0):ui + 1])          # includes the undercut close
        for k2 in range(1, min(W, avail) + 1):
            if bs[ui + k2]["close"] > rmin:
                e["running_reclaim_k"] = k2
                break
            rmin = min(rmin, bs[ui + k2]["close"])

    # ── report ─────────────────────────────────────────────────────────────
    P = print
    P("=" * 100)
    P("#354 C1 — D3 undercut→reclaim probe   (data through "
      f"{data_end}, events 2026-05-04..2026-07-24)")
    P("=" * 100)
    P(f"raw undercut-INVALIDATED events (1st per ticker+pivot): {len(events_raw)}  "
      f"| skipped: {dict(skipped) or 'none'}  | overlap-dropped (same episode): {dropped_overlap}")
    P(f"DEDUPED COHORT: {len(deduped)}   "
      f"(pre-HTF-regime {sum(1 for e in deduped if not e['post_htf'])} · "
      f"post-HTF (>= {HTF_REGIME_START}) {sum(1 for e in deduped if e['post_htf'])})")
    P()

    outc = defaultdict(int)
    for e in deduped:
        outc[e["outcome"]] += 1
    total_decided = outc["reclaimed"] + outc["no_reclaim"]
    P("── (i) Reclaim within the remaining age window (25d cap, frozen base_low_close) ──")
    P(f"  reclaimed: {outc['reclaimed']}   no-reclaim: {outc['no_reclaim']}   "
      f"censored (window still open at data edge): {outc['censored_window']}   "
      f"window-exhausted (undercut at age cap): {outc['window_exhausted']}")
    if total_decided:
        P(f"  RECLAIM RATE (decided only): {outc['reclaimed']}/{total_decided} "
          f"= {100 * outc['reclaimed'] / total_decided:.0f}%")
    rk = [e["reclaim_k"] for e in deduped if e["outcome"] == "reclaimed"]
    if rk:
        P(f"  days-to-reclaim: median {statistics.median(rk):.0f} · mean {statistics.mean(rk):.1f} "
          f"· p90 {sorted(rk)[int(0.9 * len(rk))]} · max {max(rk)}")
    P()

    rec = [e for e in deduped if e["outcome"] == "reclaimed"]

    def cohort(label, evs, key="settle_a"):
        rs = [e[key] for e in evs if e.get(key)]
        r_vals = [s[0] for s in rs]
        P(f"  {label:<58} {stats_line(r_vals)}")
        return r_vals

    P("── (ii) Forward R from the reclaim close (stop = undercut low, 10d fixed-stop settle) ──")
    prim = cohort("PRIMARY — all reclaimers, stop=excursion low, strict", rec)
    fm = [e["settle_a"][1] for e in rec if e.get("settle_a")]
    if fm:
        P(f"  {'':<58} fwd-max median {statistics.median(fm):+5.2f}R (perfect-exit upper bound)")
    cohort("  sens: lenient partial-window settle (_146 convention)", rec, key="settle_a_len")
    cohort("  sens: stop = undercut-DAY low only (variant B)", rec, key="settle_b")
    cohort("  slice: post-HTF regime only", [e for e in rec if e["post_htf"]])
    cohort("  slice: pre-HTF regime only", [e for e in rec if not e["post_htf"]])
    cohort("  slice: base ever WATCH+ (same pivot) pre-undercut",
           [e for e in rec if e["best_prior"]])
    cohort("  slice: ticker qualified <=14d pre-undercut (loose)",
           [e for e in rec if e["recent_qualified"]])
    cohort("  slice: reclaim day passes SMA20/50/200 gates (F2-live)",
           [e for e in rec if e["sma_ok"]])
    cohort("  slice: + passes 25%-depth gate too", [e for e in rec if e["sma_ok"] and e["depth_ok"]])
    P()

    P("── (iii) False-revival rate: reclaim → close back below frozen blc within K days ──")

    def frate(evs, K):
        den = [e for e in evs if (e["reundercut_k"] and e["reundercut_k"] <= K) or e["fwd_observed"] >= K]
        hits = sum(1 for e in den if e["reundercut_k"] and e["reundercut_k"] <= K)
        return hits, len(den)

    for K in REVIVAL_CURVE:
        h, d = frate(rec, K)
        hp, dp = frate([e for e in rec if e["post_htf"]], K)
        tag = "  <-- PRIMARY (family 5-bar settle window)" if K == REVIVAL_K else ""
        P(f"  K={K:>2}: {h:>3}/{d:>3} = {100 * h / d if d else 0:5.1f}%   "
          f"(post-HTF only: {hp:>2}/{dp:>2} = {100 * hp / dp if dp else 0:5.1f}%){tag}")
    P()

    P("── C3 FREEZE HAZARD — reclaim vs the RUNNING base_low_close (literal minimal-diff code) ──")
    rr = [e["running_reclaim_k"] for e in deduped if e.get("running_reclaim_k")]
    n_win = sum(1 for e in deduped if e["outcome"] in ("reclaimed", "no_reclaim"))
    if rr and n_win:
        P(f"  'reclaims' under the running-min definition: {len(rr)}/{n_win} "
          f"({100 * len(rr) / n_win:.0f}%), median k={statistics.median(rr):.0f} day(s) — "
          f"degenerate: the running min IS the undercut close, so nearly any non-new-low day fires.")
        P("  C3 must FREEZE base_low_close at the undercut, or the reclaim trigger is meaningless.")
    P()

    # ── ship rule ──────────────────────────────────────────────────────────
    P("=" * 100)
    P("SHIP RULE (ADR 0026:94-95) — reclaim-cohort forward R positive at N>=10 AND "
      "false-revival < 40%")
    n = len(prim)
    mean_r = statistics.mean(prim) if prim else float("nan")
    med_r = statistics.median(prim) if prim else float("nan")
    # seeded bootstrap 95% CI on the mean (the mean is the contested stat: +0.09R vs median -0.43R)
    rng = random.Random(354)
    boots = sorted(statistics.mean(rng.choices(prim, k=n)) for _ in range(10_000)) if prim else []
    lo, hi = (boots[249], boots[9749]) if boots else (float("nan"),) * 2
    h5, d5 = frate(rec, REVIVAL_K)
    fr = 100 * h5 / d5 if d5 else float("nan")
    P(f"  N settled          = {n}    (>=10: {n >= 10})")
    P(f"  forward R          = mean {mean_r:+.2f}R (bootstrap 95% CI [{lo:+.2f}, {hi:+.2f}]) / "
      f"median {med_r:+.2f}R    (positive: mean {mean_r > 0} / median {med_r > 0})")
    P(f"  false-revival K={REVIVAL_K}  = {fr:.1f}%    (<40%: {fr < 40})")
    cross = next((K for K in REVIVAL_CURVE if (lambda h, d: h / d if d else 0)(*frate(rec, K)) >= 0.40), None)
    P(f"  sensitivity: false-revival crosses 40% at K={cross} — the ship rule PASSES on this axis "
      f"only if 'immediate' means K<={cross - 1 if cross else max(REVIVAL_CURVE)}")
    verdict = ("SHIP" if n >= 10 and mean_r > 0 and med_r > 0 and fr < 40 else
               "NO-SHIP" if n >= 10 else "INSUFFICIENT-DATA")
    P(f"  VERDICT: {verdict}  (rec only — the operator rules the flip; CHANGE_PROCESS applies)")
    P("=" * 100)
    P()

    # ── operator cohort printouts ──────────────────────────────────────────
    P("── COHORT PRINTOUT 1: reclaimers (entry=reclaim close, stop=excursion low) ──")
    P(f"{'ticker':<7}{'undercut':<12}{'age':>4}{'k':>4}  {'prior':<11}{'blc':>9}{'entry':>9}"
      f"{'stop':>9}{'R(10d)':>8}{'fwdmaxR':>9}  {'exit':<8}{'re-uc':>6}  gates")
    for e in sorted(rec, key=lambda x: x["date"]):
        s = e.get("settle_a")
        gates = ("sma+" if e["sma_ok"] else "sma-") + ("dep+" if e["depth_ok"] else "dep-")
        P(f"{e['ticker']:<7}{e['date']!s:<12}{e['base_age']:>4}{e['reclaim_k']:>4}  "
          f"{e['best_prior'] or '-':<11}{e['frozen_blc']:>9.2f}{e['entry']:>9.2f}"
          f"{e['ul_a']:>9.2f}"
          + (f"{s[0]:>+8.2f}{s[1]:>+9.2f}  {s[2]:<8}" if s else f"{'cens':>8}{'':>9}  {'':<8}")
          + f"{e['reundercut_k'] or '-':>6}  {gates}"
          + ("  [postHTF]" if e["post_htf"] else ""))
    P()
    P("── COHORT PRINTOUT 2: non-reclaimers / censored ──")
    P(f"{'ticker':<7}{'undercut':<12}{'age':>4}{'win':>4}  {'prior':<11}{'outcome':<18}")
    for e in sorted((e for e in deduped if e["outcome"] != "reclaimed"), key=lambda x: x["date"]):
        P(f"{e['ticker']:<7}{e['date']!s:<12}{e['base_age']:>4}{e['window']:>4}  "
          f"{e['best_prior'] or '-':<11}{e['outcome']:<18}"
          + ("  [postHTF]" if e["post_htf"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
