#!/usr/bin/env python3
"""#610 — replay the SHIPPED HTF breakout-entry shadow over five years of stored daily bars,
under TODAY's rules, and settle every replayed breakout offline.

WHY: #397 (the HTF money gate) needs N>=10 settled winners from `mi_htf_breakout_shadow`; prod
holds 16 rows / 9 settled since 2026-06-29. `mi_daily_closes` holds 13.6M rows (2021-09-07 ->
2026-09-09, 20,041 tickers incl. delisted), so the same chain prod runs live can be replayed.

THE CHAIN, mirrored stage by stage (NOTHING in flag_detector is changed or monkeypatched —
every constant is read at its shipped value; this is a BASELINE-ONLY run, no variants):

  prod 17:25 ET scan   get_flag_universe(d) -> compute_flag_metrics(last 262 rows <= d, state
                       threaded from the ticker's rows in [d-5 calendar days, d)) -> a row.
  prod intraday scan   next session: candidates = latest scan's TIGHTENING/COILED/TRIGGERED rows
                       with close(d) <= base_high; a BREAK = price > base_high AND projected
                       full-day volume >= adv_20 (median of the 20 sessions ending at d).
  prod shadow row      prepare_htf_breakout_order(base_high, base_low, sma_10, sma_20) -> the
                       order shape (entry = base_high, stop = tightest of base_low/sma_10/sma_20
                       within 8%, would_reject_reason).
  prod settle job      _htf_settle_from_bars(bars, entry_idx, entry_price, stop, target_r=3).

REPLAY DELTAS (each measured, none hidden — see the analysis doc):
  * universe: prod's RS gate (rs_top200 / rs_1m>=80) only exists from 2025-12-26 in
    mi_stock_scores, so the full-history universe applies the REPRODUCIBLE organic gates
    (close >= $5, 20-session mean dollar volume >= $5M, >= 60 sessions in 90 calendar days,
    security_type in (CS, ADRC) or unknown — prod passes unknown too) and drops the RS/burst
    OR-block. The real RS gate is re-applied on 2025-12-26+ as a sensitivity (always runs).
  * break: a 5-minute tick check cannot be replayed from daily bars. The daily proxy is
    high(d+1) > base_high AND full-day volume(d+1) >= adv_20. Validated in isolation against
    mi_flag_breaks on prod's OWN stored parent rows (detector held constant).
  * a lossless pre-screen chooses which (ticker, day) pairs get compute_flag_metrics:
    max(high over the 25 sessions before d) / min(low over the 65 sessions before d) >= 1.9
    is IMPLIED by the detector's own pole gate (pivot within 25 sessions; pole = pivot_high /
    min(low over 40 sessions ending at the pivot)), so nothing actionable is skipped — asserted
    against the stored actionable rows, must be 0 misses.

Inputs (pulled ONCE from prod on 2026-09-10, read-only; kept in the session scratchpad — 265 MB
is too big for the repo; the exact statements are here so the pull is reproducible). All via
`ssh apollo@87.99.134.162 'docker exec -i apollo-postgres psql -U apollo -d apollo -tAX ...'`:

  daily_closes_all.csv.gz   (13,620,198 rows / 20,041 tickers)
      COPY (SELECT ticker, trade_date, open_price, high_price, low_price, close, volume
            FROM mi_daily_closes) TO STDOUT WITH (FORMAT csv)            -- | gzip -1
  small_pulls.psv           (psql -tAX -f -, '|'-delimited, one tag per row)
      SELECT 'sectype', ticker, security_type, exchange FROM mi_security_types;
      SELECT 'cand', ticker, scan_date, stage, coalesce(reason,''), coalesce(pivot_high_date::text,''),
             coalesce(pivot_high_price::text,''), coalesce(base_high::text,''), coalesce(base_low::text,''),
             coalesce(base_age::text,''), coalesce(sma_10::text,''), coalesce(sma_20::text,''),
             coalesce(held_from_stage,'') FROM mi_flag_candidates ORDER BY ticker, scan_date;
      SELECT 'brk', ticker, break_date, coalesce(parent_scan_date::text,''), coalesce(parent_stage,''),
             base_high, coalesce(base_low::text,''), coalesce(minutes_since_open::text,''),
             coalesce(today_volume::text,''), coalesce(adv_20::text,''), coalesce(volume_pct_of_adv::text,'')
             FROM mi_flag_breaks ORDER BY break_date, ticker;
  stock_scores.csv.gz       (508,840 rows, 2025-12-26+)
      COPY (SELECT ticker, score_date, rs_rank, rs_1m FROM mi_stock_scores) TO STDOUT WITH (FORMAT csv)

The RS-gate sensitivity (2025-12-26+) always runs; there is no flag for it.

Usage:
  python scripts/probes/_610_htf_replay.py --data-dir <scratchpad> [--workers 8]
"""
from __future__ import annotations

import argparse
import bisect
import csv
import gzip
import json
import multiprocessing as mp
import os
import pathlib
import statistics
import sys
import time
from collections import Counter, defaultdict
from datetime import date, timedelta

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from agents.market_intelligence import flag_detector as fd  # noqa: E402
from agents.market_intelligence.anticipation import db_rows_to_bars  # noqa: E402

ACTIONABLE = ("WATCH", "TIGHTENING", "COILED", "TRIGGERED")
BREAK_PARENT_STAGES = ("TIGHTENING", "COILED", "TRIGGERED")   # the intraday scan's candidate stages
OVERLAP_START = date(2026, 6, 29)     # first scan under the current pole/liquidity rules
RS_SCORES_START = date(2025, 12, 26)  # first mi_stock_scores row
STATE_WINDOW_DAYS = 5                 # prod's three state queries look back 5 CALENDAR days
WARMUP_SESSIONS = 60                  # detector runs this far before the first pre-screen hit
TAIL_SESSIONS = 5                     # ... and this far after the last one (hysteresis continuity)
PRESCREEN_HIGH_WIN = fd._PIVOT_LOOKBACK_DAYS                                  # 25
PRESCREEN_LOW_WIN = fd._PIVOT_LOOKBACK_DAYS + fd._RUNUP_LOOKBACK_DAYS         # 65 (>= 25 + 39)
PRESCREEN_RATIO = fd._RUNUP_MIN_RATIO                                         # 1.90
# prod get_flag_universe organic gates (db.py) — the reproducible ones
UNI_MIN_CLOSE = 5.0
UNI_MIN_DOLLAR_VOL_20 = 5_000_000.0
UNI_MIN_SESSIONS = 60
UNI_SESSION_SPAN_DAYS = 90
UNI_SECTYPES = ("CS", "ADRC")

_G: dict = {}   # fork-shared read-only globals for the worker pool


# ── loading ──────────────────────────────────────────────────────────────────

def load_bars(path: pathlib.Path):
    """csv.gz -> {ticker: dict(dates=list[date], o,h,l,c,v = np.ndarray)} sorted by date."""
    import pandas as pd
    t0 = time.time()
    # keep_default_na=False: a ticker literally named "NA" must stay a string, not become NaN
    df = pd.read_csv(path, header=None, names=["ticker", "d", "o", "h", "l", "c", "v"],
                     dtype={"ticker": str}, parse_dates=["d"], keep_default_na=False)
    df.sort_values(["ticker", "d"], inplace=True, kind="mergesort")
    out = {}
    for t, g in df.groupby("ticker", sort=False):
        out[t] = dict(
            dates=[x.date() for x in g["d"]],
            o=g["o"].to_numpy(float), h=g["h"].to_numpy(float), l=g["l"].to_numpy(float),
            c=g["c"].to_numpy(float), v=g["v"].to_numpy(float),
        )
    print(f"bars: {len(df):,} rows / {len(out):,} tickers ({time.time()-t0:.0f}s)", flush=True)
    return out


def load_small(path: pathlib.Path):
    sectype, cands, breaks = {}, defaultdict(list), {}
    with path.open() as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line or line.startswith("("):
                continue
            f = line.split("|")
            if f[0] == "sectype":
                sectype[f[1]] = f[2]
            elif f[0] == "cand":
                _, t, d, stage, reason, pd_, pp, bh, bl, ba, s10, s20, held = f
                cands[t].append(dict(
                    scan_date=date.fromisoformat(d), stage=stage, reason=reason,
                    pivot_high_date=date.fromisoformat(pd_) if pd_ else None,
                    pivot_high_price=float(pp) if pp else None,
                    base_high=float(bh) if bh else None, base_low=float(bl) if bl else None,
                    base_age=int(ba) if ba else None,
                    sma_10=float(s10) if s10 else None, sma_20=float(s20) if s20 else None,
                    held_from_stage=held or None))
            elif f[0] == "brk":
                _, t, d, psd, pstage, bh, _bl, _mso, _tv, adv, *_rest = f
                breaks[(t, date.fromisoformat(d))] = dict(
                    parent_scan_date=date.fromisoformat(psd) if psd else None,
                    parent_stage=pstage, base_high=float(bh), adv_20=float(adv) if adv else None)
    for t in cands:
        cands[t].sort(key=lambda r: r["scan_date"])
    return sectype, cands, breaks


def load_scores(path: pathlib.Path):
    """{ticker: {score_date: (rs_rank, rs_1m)}}"""
    out = defaultdict(dict)
    with gzip.open(path, "rt") as fh:
        for row in csv.reader(fh):
            t, d, rk, r1 = row
            out[t][date.fromisoformat(d)] = (int(rk) if rk else None, float(r1) if r1 else None)
    return out


# ── per-ticker masks (numpy, vectorised) ─────────────────────────────────────

def _trailing_max(a, win):
    """m[i] = max(a[i-win:i]) (the `win` bars BEFORE i, i excluded); nan where i == 0."""
    n = len(a)
    out = np.full(n, np.nan)
    if n < 2:
        return out
    from numpy.lib.stride_tricks import sliding_window_view as swv
    if n - 1 >= win:
        out[win:] = swv(a[:-1], win).max(axis=1)
    for i in range(1, min(win, n)):
        out[i] = a[:i].max()
    return out


def _trailing_min(a, win):
    n = len(a)
    out = np.full(n, np.nan)
    if n < 2:
        return out
    from numpy.lib.stride_tricks import sliding_window_view as swv
    if n - 1 >= win:
        out[win:] = swv(a[:-1], win).min(axis=1)
    for i in range(1, min(win, n)):
        out[i] = a[:i].min()
    return out


def ticker_masks(tb, sectype_ok: bool):
    """Returns (prescreen, universe) boolean arrays over the ticker's bars."""
    n = len(tb["c"])
    h, l, c, v = tb["h"], tb["l"], tb["c"], tb["v"]
    idx = np.arange(n)
    # pre-screen: a superset of the detector's pole gate
    H = _trailing_max(h, PRESCREEN_HIGH_WIN)
    L = _trailing_min(l, PRESCREEN_LOW_WIN)
    with np.errstate(invalid="ignore", divide="ignore"):
        pre = (L > 0) & (H / L >= PRESCREEN_RATIO)
    pre &= idx >= UNI_MIN_SESSIONS - 1          # prod: < 60 rows of history -> no row at all
    # universe (reproducible organic gates)
    dv = c * v
    cs = np.concatenate([[0.0], np.cumsum(dv)])
    win = np.minimum(idx + 1, 20)
    dv20 = (cs[idx + 1] - cs[idx + 1 - win]) / win
    uni = (c >= UNI_MIN_CLOSE) & (dv20 >= UNI_MIN_DOLLAR_VOL_20) & (idx >= UNI_MIN_SESSIONS - 1)
    if uni.any():
        dates = tb["dates"]
        # >= 60 sessions within the last 90 calendar days: the 60th-prior bar's date >= d - 90
        for i in np.flatnonzero(uni):
            if (dates[i] - dates[i - (UNI_MIN_SESSIONS - 1)]).days > UNI_SESSION_SPAN_DAYS:
                uni[i] = False
    if not sectype_ok:
        uni[:] = False
    return pre, uni


def dilate(mask, before, after):
    out = np.zeros(len(mask), dtype=bool)
    for i in np.flatnonzero(mask):
        out[max(0, i - before): i + after + 1] = True
    return out


# ── the replay of one ticker (worker) ────────────────────────────────────────

def _row_dicts(tb, lo, hi):
    d, o, h, l, c, v = tb["dates"], tb["o"], tb["h"], tb["l"], tb["c"], tb["v"]
    return [{"trade_date": d[i], "open_price": float(o[i]), "high_price": float(h[i]),
             "low_price": float(l[i]), "close": float(c[i]), "volume": float(v[i])}
            for i in range(lo, hi)]


def _adv20_before(tb, i):
    """prod intraday-scan adv_20: median of the last 20 sessions BEFORE i with volume > 0,
    inside 40 calendar days of the break date (mi_daily_closes has no row for the break day yet)."""
    vals = []
    j = i - 1
    while j >= 0 and len(vals) < 20 and (tb["dates"][i] - tb["dates"][j]).days <= 40:
        if tb["v"][j] > 0:
            vals.append(float(tb["v"][j]))
        j -= 1
    return statistics.median(vals) if vals else 0.0


def replay_ticker(ticker):
    tb = _G["bars"][ticker]
    sectype = _G["sectype"].get(ticker)
    pre, uni = ticker_masks(tb, sectype_ok=(sectype is None or sectype in UNI_SECTYPES))
    scan = dilate(pre, WARMUP_SESSIONS, TAIL_SESSIONS) & uni
    if not scan.any():
        return None
    dates = tb["dates"]
    n = len(dates)
    rows_all = _row_dicts(tb, 0, n)
    bars_all = db_rows_to_bars(rows_all)
    prior: list[dict] = []
    stage_year = Counter()
    kept_rows = []      # compact rows: overlap window OR actionable
    breaks = []
    for i in np.flatnonzero(scan):
        d = dates[i]
        rows = rows_all[max(0, i - fd._HISTORY_DAYS + 1): i + 1]
        if len(rows) < 60:
            continue
        cutoff = d - timedelta(days=STATE_WINDOW_DAYS)
        window = [r for r in prior if cutoff <= r["scan_date"] < d]
        ystage = window[-1]["stage"] if window else None
        recent = [r["stage"] for r in window]
        ppiv = next(((r["pivot_high_date"], r["pivot_high_price"])
                     for r in reversed(window) if r["pivot_high_date"] is not None), None)
        m = fd.compute_flag_metrics(rows, ticker=ticker, yesterday_stage=ystage, recent_stages=recent,
                                    prior_pivot_date=ppiv[0] if ppiv else None,
                                    prior_pivot_high=ppiv[1] if ppiv else None)
        row = dict(scan_date=d, stage=m["stage"], reason=m["reason"],
                   pivot_high_date=m["pivot_high_date"], pivot_high_price=m["pivot_high_price"],
                   base_high=m["base_high"], base_low=m["base_low"], base_age=m["base_age"],
                   runup_pct=m["runup_pct"], sma_10=m["sma_10"], sma_20=m["sma_20"],
                   held_from_stage=m["held_from_stage"], idx=int(i))
        prior.append(row)
        if len(prior) > 40:
            prior = prior[-40:]
        stage_year[(d.year, m["stage"])] += 1
        if m["stage"] in ACTIONABLE or d >= OVERLAP_START:
            kept_rows.append(row)
        # ── the intraday break scan, on the NEXT session, from THIS row as parent
        if (m["stage"] in BREAK_PARENT_STAGES and m["base_high"] and m["base_high"] > 0
                and float(tb["c"][i]) <= m["base_high"] and i + 1 < n):
            j = i + 1
            base_high = float(m["base_high"])
            if float(tb["h"][j]) <= base_high:
                continue
            adv20 = _adv20_before(tb, j)
            vol_j = float(tb["v"][j])
            if adv20 <= 0 or vol_j <= 0 or vol_j < adv20:
                continue
            spec, wreject = fd.prepare_htf_breakout_order(
                base_high=base_high, base_low=m["base_low"], sma_10=m["sma_10"], sma_20=m["sma_20"],
                regime_record=None)
            res = fd._htf_settle_from_bars(bars_all, j, entry_price=spec["entry_price"],
                                           stop=spec["stop_loss_price"])
            entry, stop = spec["entry_price"], spec["stop_loss_price"]
            risk = entry - stop
            target = entry + fd._HTF_BREAKOUT_TARGET_R * risk
            oj, hj, lj, cj = (float(tb[k][j]) for k in ("o", "h", "l", "c"))
            def _fwd(k):
                return (float(tb["c"][j + k]) / entry - 1.0) if j + k < n else None
            # #396 sibling readout — the SOURCED management protocol (scale-out day 3-5 -> breakeven
            # -> 10/20 EMA trail), the shipped _htf_management_replay on the same entry spec. Bars
            # capped at 300 forward sessions (prod passes everything up to today; a trail exit that
            # has not fired in 300 sessions is reported as still open, not marked).
            mg = fd._htf_management_replay(bars_all[: j + 301], j, entry_price=entry, initial_stop=stop,
                                           shares=float(spec["shares"] or 0))
            mg_status = mg["status"] if mg else None
            mg_r = mg["realized_r"] if mg else None
            mg_exit = next((e["date"] for e in (mg["events"] if mg else []) if e["type"] in ("trail_exit", "hard_stop_exit")), None)
            mg_scaled = bool(mg and mg["partial_taken"])
            breaks.append(dict(
                ticker=ticker, break_date=dates[j], parent_scan_date=d, parent_stage=m["stage"],
                pivot_high_date=m["pivot_high_date"], pivot_high=m["pivot_high_price"],
                runup_pct=m["runup_pct"], base_age=m["base_age"], base_high=base_high,
                base_low=m["base_low"], sma_10=m["sma_10"], sma_20=m["sma_20"],
                entry=entry, limit=spec["limit_price"], stop=stop, stop_kind=spec["stop_kind"],
                max_loss_pct=spec["max_loss_pct"], would_reject=wreject, shares=spec["shares"],
                target=round(target, 4), adv20=adv20, break_vol=vol_j, vol_x_adv=vol_j / adv20,
                break_open=oj, break_high=hj, break_low=lj, break_close=cj,
                gap_through_limit=oj > spec["limit_price"],
                unfillable=(oj > spec["limit_price"] and lj > spec["limit_price"]),
                mgmt_status=mg_status, mgmt_r=mg_r, mgmt_exit_date=mg_exit, mgmt_scaled=mg_scaled,
                entry_bar_hit_target=hj >= target, entry_bar_hit_stop=lj <= stop,
                outcome=res["outcome"] if res else None,
                realized_r=res["realized_r"] if res else None,
                fwd_mfe_r=res["fwd_mfe_r"] if res else None,
                fwd5=_fwd(5), fwd10=_fwd(10), fwd20=_fwd(20),
                sectype=sectype or "UNKNOWN",
            ))
    return dict(ticker=ticker, rows=kept_rows, breaks=breaks, stage_year=stage_year,
                n_scanned=int(scan.sum()), n_pre=int(pre.sum()))


def _init_worker(g):
    _G.update(g)


# ── validations ──────────────────────────────────────────────────────────────

def validate_prescreen(bars, cands):
    """Every stored actionable row (current era) must sit on a pre-screen-true day."""
    miss, tot, holiday = [], 0, 0
    for t, rl in cands.items():
        tb = bars.get(t)
        if tb is None:
            continue
        pre = None
        for r in rl:
            if r["scan_date"] < OVERLAP_START or r["stage"] not in ACTIONABLE:
                continue
            if pre is None:
                pre, _ = ticker_masks(tb, sectype_ok=True)
            # prod also scans on market holidays (2026-07-03, 2026-09-07 Labor Day): that row is
            # computed from the bars ending at the LAST session <= scan_date, so check there.
            i = bisect.bisect_right(tb["dates"], r["scan_date"]) - 1
            if i < 0:
                continue
            if tb["dates"][i] != r["scan_date"]:
                holiday += 1
            tot += 1
            if not pre[i]:
                miss.append((t, r["scan_date"], r["stage"], r["reason"]))
    return tot, miss, holiday


def validate_break_rule(bars, cands, prod_breaks):
    """The daily break proxy alone, on prod's OWN stored parent rows (detector held constant):
    parent = stored TIGHTENING/COILED/TRIGGERED row at d with close(d) <= base_high; proxy fires
    if high(next session) > base_high and volume(next) >= adv_20. Compared to mi_flag_breaks."""
    tp = fn = fp = 0
    fn_list, fp_list, adv_ratio = [], [], []
    parents = split_adjusted = 0
    first_prod_break = min(d for _, d in prod_breaks)
    for t, rl in cands.items():
        tb = bars.get(t)
        if tb is None:
            continue
        dates = tb["dates"]
        for r in rl:
            if r["stage"] not in BREAK_PARENT_STAGES or not r["base_high"] or r["base_high"] <= 0:
                continue
            i = bisect.bisect_left(dates, r["scan_date"])
            if i >= len(dates) or dates[i] != r["scan_date"] or i + 1 >= len(dates):
                continue
            if float(tb["c"][i]) > r["base_high"]:
                continue
            j = i + 1
            if dates[j] < first_prod_break:
                continue                       # mi_flag_breaks did not exist yet
            if float(tb["h"][j]) / r["base_high"] < 0.5 or float(tb["c"][i]) / r["base_high"] < 0.5:
                split_adjusted += 1            # bars re-adjusted for a split after the scan (CRWD 07-01)
                continue
            parents += 1
            adv20 = _adv20_before(tb, j)
            fires = (float(tb["h"][j]) > r["base_high"] and adv20 > 0 and tb["v"][j] > 0
                     and float(tb["v"][j]) >= adv20)
            prod = (t, dates[j]) in prod_breaks
            if fires and prod:
                tp += 1
                pa = prod_breaks[(t, dates[j])].get("adv_20")
                if pa:
                    adv_ratio.append(round(adv20 / pa, 3))
            elif fires and not prod:
                fp += 1
                fp_list.append((t, dates[j], round(float(tb["h"][j]) / r["base_high"] - 1, 4),
                                round(float(tb["v"][j]) / adv20, 2), round(float(tb["c"][j]) / r["base_high"] - 1, 4)))
            elif prod and not fires:
                fn += 1
                fn_list.append((t, dates[j], round(float(tb["h"][j]) / r["base_high"] - 1, 4),
                                round(float(tb["v"][j]) / adv20, 2) if adv20 else None))
    return dict(parents=parents, tp=tp, fp=fp, fn=fn, fn_list=fn_list, fp_list=fp_list,
                adv_ratio_vs_prod=sorted(adv_ratio), split_adjusted=split_adjusted,
                first_prod_break=first_prod_break)


# ── stats ────────────────────────────────────────────────────────────────────

def q(vals, p):
    vals = sorted(v for v in vals if v is not None)
    if not vals:
        return None
    k = (len(vals) - 1) * p
    f = int(k)
    c = min(f + 1, len(vals) - 1)
    return vals[f] + (vals[c] - vals[f]) * (k - f)


def summarize(brks, label):
    settled = [b for b in brks if b["outcome"] is not None]
    n = len(settled)
    if n == 0:
        return {"label": label, "n_breaks": len(brks), "n_settled": 0}
    rr = [b["realized_r"] for b in settled]
    mfe = [b["fwd_mfe_r"] for b in settled]
    oc = Counter(b["outcome"] for b in settled)
    wins = sum(1 for b in settled if b["realized_r"] > 0)
    return {
        "label": label, "n_breaks": len(brks), "n_settled": n,
        "n_takeable_settled": sum(1 for b in settled if b["would_reject"] is None),
        "capture": oc.get("capture", 0), "stop": oc.get("stop", 0), "open": oc.get("open", 0),
        "capture_rate": round(oc.get("capture", 0) / n, 3),
        "win_rate_r_gt_0": round(wins / n, 3),
        "mean_r": round(statistics.fmean(rr), 3), "median_r": round(statistics.median(rr), 3),
        "r_p10": round(q(rr, .10), 2), "r_p25": round(q(rr, .25), 2), "r_p75": round(q(rr, .75), 2),
        "r_p90": round(q(rr, .90), 2), "sum_r": round(sum(rr), 1),
        "mfe_median": round(statistics.median(mfe), 2), "mfe_p75": round(q(mfe, .75), 2),
        "mfe_p90": round(q(mfe, .90), 2), "mfe_ge_3r": round(sum(1 for x in mfe if x >= 3) / n, 3),
        "r_hist": dict(sorted(Counter(
            "capture(+3)" if b["outcome"] == "capture" else "stop(-1)" if b["outcome"] == "stop"
            else f"open[{np.floor(b['realized_r'] * 2) / 2:+.1f})" for b in settled).items())),
        "gap_through_limit": sum(1 for b in settled if b["gap_through_limit"]),
        "resolved_on_entry_bar": sum(1 for b in settled if b["entry_bar_hit_target"] or b["entry_bar_hit_stop"]),
        "unknown_sectype": sum(1 for b in settled if b["sectype"] == "UNKNOWN"),
    }


def fmt(s):
    if s.get("n_settled", 0) == 0:
        return f"{s['label']:40} breaks={s['n_breaks']} settled=0"
    return (f"{s['label']:40} breaks={s['n_breaks']:4d} settled={s['n_settled']:4d} "
            f"takeable={s['n_takeable_settled']:4d} | cap/stop/open={s['capture']}/{s['stop']}/{s['open']} "
            f"capRate={s['capture_rate']:.1%} win(R>0)={s['win_rate_r_gt_0']:.1%} | "
            f"meanR={s['mean_r']:+.2f} medR={s['median_r']:+.2f} p10/p25/p75/p90="
            f"{s['r_p10']:+.1f}/{s['r_p25']:+.1f}/{s['r_p75']:+.1f}/{s['r_p90']:+.1f} sumR={s['sum_r']:+.1f} | "
            f"MFE med/p75/p90={s['mfe_median']:.2f}/{s['mfe_p75']:.2f}/{s['mfe_p90']:.2f} >=3R:{s['mfe_ge_3r']:.0%}")


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--limit-tickers", type=int, default=0, help="debug: only the first N tickers")
    args = ap.parse_args()
    dd = pathlib.Path(args.data_dir)
    out_dir = pathlib.Path(args.out) if args.out else dd / "replay_out"
    out_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    # shipped constants, echoed so the run is self-describing (and asserted unmodified)
    consts = dict(RUNUP_MIN_RATIO=fd._RUNUP_MIN_RATIO, RUNUP_LOOKBACK_DAYS=fd._RUNUP_LOOKBACK_DAYS,
                  HTF_MIN_ADV_SHARES=fd._HTF_MIN_ADV_SHARES, HTF_MIN_ADR_PCT=fd._HTF_MIN_ADR_PCT,
                  HTF_BREAKOUT_TARGET_R=fd._HTF_BREAKOUT_TARGET_R, HTF_SETTLE_WINDOW=fd._HTF_SETTLE_WINDOW,
                  HTF_MAX_LOSS_PCT=fd._HTF_MAX_LOSS_PCT, HISTORY_DAYS=fd._HISTORY_DAYS,
                  BREAKOUT_VOL_RATIO=fd._BREAKOUT_VOL_RATIO, FLAG_DEPTH_MIN=fd._FLAG_DEPTH_MIN)
    print("shipped constants:", json.dumps(consts))
    assert consts["RUNUP_MIN_RATIO"] == 1.90 and consts["HTF_MIN_ADR_PCT"] == 0.04 \
        and consts["HTF_MIN_ADV_SHARES"] == 500_000, "constants are not the shipped values — void"

    bars = load_bars(dd / "daily_closes_all.csv.gz")
    sectype, cands, prod_breaks = load_small(dd / "small_pulls.psv")
    scores = load_scores(dd / "stock_scores.csv.gz")
    print(f"sectypes {len(sectype):,} | stored candidate rows {sum(len(v) for v in cands.values()):,} "
          f"| prod breaks {len(prod_breaks)} | score rows {sum(len(v) for v in scores.values()):,}")

    # ── validation 1: the pre-screen is lossless on the stored actionable rows
    tot, miss, holiday = validate_prescreen(bars, cands)
    print(f"\nPRESCREEN LOSSLESS CHECK: {tot} stored actionable rows since {OVERLAP_START} "
          f"({holiday} of them prod scans on a market holiday, checked at the last session); "
          f"excluded by the pre-screen = {len(miss)}")
    for x in miss[:10]:
        print("   MISS", x)
    if miss:
        raise SystemExit("pre-screen drops stored actionable rows — the run is VOID")

    # ── validation 2: the daily break proxy alone, against mi_flag_breaks
    bv = validate_break_rule(bars, cands, prod_breaks)
    print(f"BREAK-RULE CHECK on prod's stored parents (next session >= {bv['first_prod_break']}, "
          f"{bv['split_adjusted']} split-adjusted parents excluded): parents={bv['parents']} "
          f"prod-and-proxy={bv['tp']} proxy-only={bv['fp']} prod-only={bv['fn']}  "
          f"-> proxy recall {bv['tp']/max(1, bv['tp']+bv['fn']):.0%}, precision {bv['tp']/max(1, bv['tp']+bv['fp']):.0%}")
    by_date = Counter(d for _, d, *_ in bv["fp_list"])
    print("   proxy-only by date (a cluster = a prod scan outage, not a rule gap):",
          sorted(by_date.items(), key=lambda x: -x[1])[:15])
    wick_only = sum(1 for x in bv["fp_list"] if x[4] < 0)
    tiny = sum(1 for x in bv["fp_list"] if x[2] <= 0.005)
    print(f"   proxy-only: {wick_only} closed back UNDER base_high (wick), {tiny} poked <=0.5% above it")
    ar = bv["adv_ratio_vs_prod"]
    print(f"   my adv20 / prod's stored adv_20 on the shared breaks: n={len(ar)} min={ar[0] if ar else None} "
          f"median={statistics.median(ar) if ar else None} max={ar[-1] if ar else None}")
    print("   prod-only (proxy missed) [ticker, date, high/base_high-1, vol/adv20]:", bv["fn_list"][:20])
    print("   proxy-only (prod missed) [ticker, date, high/base_high-1, vol/adv20, close/base_high-1]:",
          bv["fp_list"][:30])

    # ── the replay
    tickers = sorted(bars.keys())
    if args.limit_tickers:
        tickers = tickers[:args.limit_tickers]
    _G.update(bars=bars, sectype=sectype)
    results = []
    t1 = time.time()
    ctx = mp.get_context("fork")
    with ctx.Pool(args.workers, initializer=_init_worker, initargs=(_G,)) as pool:
        for k, r in enumerate(pool.imap_unordered(replay_ticker, tickers, chunksize=25)):
            if r is not None:
                results.append(r)
            if (k + 1) % 2000 == 0:
                print(f"  ... {k+1:,}/{len(tickers):,} tickers ({time.time()-t1:.0f}s)", flush=True)
    print(f"replay: {len(results):,} tickers had scan days ({time.time()-t1:.0f}s)")

    all_breaks = [b for r in results for b in r["breaks"]]
    all_breaks.sort(key=lambda b: (b["break_date"], b["ticker"]))
    stage_year = Counter()
    n_scanned = n_pre = 0
    for r in results:
        stage_year.update(r["stage_year"])
        n_scanned += r["n_scanned"]
        n_pre += r["n_pre"]
    print(f"pairs pre-screened {n_pre:,}; detector calls {n_scanned:,}")

    # ── validation 3: stage reconciliation on the stored overlap pairs
    mine = {}
    for r in results:
        for row in r["rows"]:
            if row["scan_date"] >= OVERLAP_START:
                mine[(r["ticker"], row["scan_date"])] = row
    match = mism = 0
    kinds = Counter()
    examples = []
    mism_rows = []
    prod_only_act = 0
    holiday_rows = 0
    prod_only_reasons = Counter()
    for t, rl in cands.items():
        for s in rl:
            if s["scan_date"] < OVERLAP_START:
                continue
            m = mine.get((t, s["scan_date"]))
            if m is None:
                tbd = bars[t]["dates"] if t in bars else []
                k = bisect.bisect_left(tbd, s["scan_date"])
                if k >= len(tbd) or tbd[k] != s["scan_date"]:
                    holiday_rows += 1          # prod scanned on a market holiday; no bar, no replay row
                elif s["stage"] in ACTIONABLE:
                    prod_only_act += 1
                    tb = bars[t]
                    c_ = float(tb["c"][k]); dv_ = float((tb["c"][max(0, k-19):k+1] * tb["v"][max(0, k-19):k+1]).mean())
                    why = ("close<$5" if c_ < UNI_MIN_CLOSE else "dollar_vol<$5M" if dv_ < UNI_MIN_DOLLAR_VOL_20
                           else "sectype" if sectype.get(t) not in (None,) + UNI_SECTYPES else "<60 sessions/90d" if k < 59
                           else "other")
                    prod_only_reasons[why] += 1
                continue
            if s["stage"] == m["stage"]:
                match += 1
            else:
                mism += 1
                kind = ("mna_filter" if (s["reason"] or "").startswith("mna_filter") else f"{s['stage']}->{m['stage']}")
                kinds[kind] += 1
                mism_rows.append((t, s["scan_date"].isoformat(), s["stage"], (s["reason"] or "")[:60], m["stage"], (m["reason"] or "")[:60]))
                if len(examples) < 15:
                    examples.append(mism_rows[-1])
    stored_keys = {(t, s["scan_date"]) for t, rl in cands.items() for s in rl if s["scan_date"] >= OVERLAP_START}
    mine_only_act = [(t, d) for (t, d), row in mine.items() if row["stage"] in ACTIONABLE and (t, d) not in stored_keys]
    print(f"\nSTAGE RECONCILIATION (overlap {OVERLAP_START} -> end, on pairs both sides scanned): "
          f"{match:,} match / {mism:,} mismatch = {match/max(1, match+mism):.2%}")
    print("   mismatch kinds:", dict(kinds.most_common(12)))
    for ex in examples:
        print("   ", ex)
    print(f"   stored rows on market holidays (no bar; prod re-scans the last session): {holiday_rows}")
    print(f"   stored ACTIONABLE rows my universe did not scan (prod carry-forward / RS paths): {prod_only_act} {dict(prod_only_reasons)}")
    print(f"   my ACTIONABLE rows on pairs prod never scanned (the universe gap, RS gate absent here): "
          f"{len(mine_only_act)} rows / {len({t for t, _ in mine_only_act})} tickers")

    with (out_dir / "stage_mismatches.csv").open("w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["ticker", "scan_date", "prod_stage", "prod_reason", "replay_stage", "replay_reason"]); w.writerows(mism_rows)
    with (out_dir / "universe_gap_actionable.csv").open("w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["ticker", "scan_date", "stage"])
        w.writerows((t, d.isoformat(), mine[(t, d)]["stage"]) for t, d in sorted(mine_only_act))

    # ── validation 4: replayed breaks vs the 16 prod shadow rows
    ov = [b for b in all_breaks if b["break_date"] >= OVERLAP_START]
    ov_keys = {(b["ticker"], b["break_date"]) for b in ov}
    prod_ov = {k for k in prod_breaks if k[1] >= OVERLAP_START}
    print(f"\nSHADOW RECONCILIATION (overlap): replayed breaks {len(ov)} | prod shadow rows {len(prod_ov)} | "
          f"both {len(ov_keys & prod_ov)} | replay-only {len(ov_keys - prod_ov)} | prod-only {len(prod_ov - ov_keys)}")
    print("   prod-only:", sorted(prod_ov - ov_keys))
    print("   replay-only:", sorted(ov_keys - prod_ov))
    for b in ov:
        if (b["ticker"], b["break_date"]) in prod_ov:
            print(f"   both: {b['ticker']} {b['break_date']} entry {b['entry']} stop {b['stop']} {b['stop_kind']} "
                  f"reject={b['would_reject']} -> {b['outcome']} R={b['realized_r']} mfe={b['fwd_mfe_r']}")

    # ── board volume by year (context: prod WATCH+ rows/month ~130 since 07)
    years = sorted({y for y, _ in stage_year})
    print("\nROWS BY YEAR (stage counts from the replay; the universe here has no RS gate):")
    for y in years:
        print(f"   {y}: " + "  ".join(f"{s}={stage_year[(y, s)]:,}" for s in ("WATCH", "TIGHTENING", "COILED", "TRIGGERED", "INVALIDATED", "unqualified")))

    # ── outcomes
    print("\n== OUTCOMES (settled = the shipped settler returned a verdict; window 12 sessions) ==")
    sums = {}
    def add(label, brks):
        s = summarize(brks, label)
        sums[label] = s
        print(fmt(s))
        return s
    add("ALL break-rows", all_breaks)
    add("  takeable (would_reject IS NULL)", [b for b in all_breaks if b["would_reject"] is None])
    add("  would-reject: stop>8%", [b for b in all_breaks if b["would_reject"] == "stop_distance_gt_8pct"])
    add("  other would-reject", [b for b in all_breaks if b["would_reject"] not in (None, "stop_distance_gt_8pct")])
    # first break per episode (ticker + pivot date)
    seen = set()
    first = []
    for b in all_breaks:
        k = (b["ticker"], b["pivot_high_date"])
        if k in seen:
            continue
        seen.add(k)
        first.append(b)
    add("FIRST break per episode (ticker+pivot)", first)
    add("  first, takeable", [b for b in first if b["would_reject"] is None])
    add("  first, takeable, known sectype (CS/ADRC)", [b for b in first if b["would_reject"] is None and b["sectype"] != "UNKNOWN"])
    add("  first, takeable, UNKNOWN sectype", [b for b in first if b["would_reject"] is None and b["sectype"] == "UNKNOWN"])
    add("  first, takeable, NOT gap-through-limit", [b for b in first if b["would_reject"] is None and not b["gap_through_limit"]])
    add("  first, takeable, gap-through-limit only", [b for b in first if b["would_reject"] is None and b["gap_through_limit"]])
    add("  first, takeable, UNFILLABLE (open>limit, low never touched it)", [b for b in first if b["would_reject"] is None and b["unfillable"]])
    add("  first, takeable, excluding UNFILLABLE", [b for b in first if b["would_reject"] is None and not b["unfillable"]])
    add("  first, takeable, not resolved on entry bar", [b for b in first if b["would_reject"] is None and not (b["entry_bar_hit_target"] or b["entry_bar_hit_stop"])])
    add("  first, takeable, break day CLOSED above base_high", [b for b in first if b["would_reject"] is None and b["break_close"] > b["base_high"]])
    add("  first, takeable, break day closed back UNDER (wick)", [b for b in first if b["would_reject"] is None and b["break_close"] <= b["base_high"]])
    add("  first, takeable, poke <=0.5% above base_high", [b for b in first if b["would_reject"] is None and b["break_high"] / b["base_high"] - 1 <= 0.005])
    print("\n-- first break per episode, takeable, by YEAR of break --")
    for y in years:
        add(f"  {y}", [b for b in first if b["would_reject"] is None and b["break_date"].year == y])
    print("\n-- first break per episode, takeable, by parent stage --")
    for st in BREAK_PARENT_STAGES:
        add(f"  parent={st}", [b for b in first if b["would_reject"] is None and b["parent_stage"] == st])
    print("\n-- first break per episode, takeable, by stop kind --")
    for sk in ("base_low", "sma_10", "sma_20"):
        add(f"  stop={sk}", [b for b in first if b["would_reject"] is None and b["stop_kind"] == sk])
    print("\n-- first break per episode, takeable, by break-day volume multiple --")
    for lo, hi in ((1.0, 1.5), (1.5, 2.0), (2.0, 3.0), (3.0, 1e9)):
        add(f"  vol {lo}-{hi if hi < 1e8 else 'inf'}x adv20", [b for b in first if b["would_reject"] is None and lo <= b["vol_x_adv"] < hi])

    # ── #396 management readout (the sibling shipped protocol) on the same breaks
    def mg_stats(label, brks):
        closed = [b for b in brks if b["mgmt_status"] in ("closed_trail_exit", "closed_hard_stop") and b["mgmt_r"] is not None]
        still_open = sum(1 for b in brks if b["mgmt_status"] == "open")
        if not closed:
            print(f"{label:40} closed=0 open={still_open}")
            return
        rr = [b["mgmt_r"] for b in closed]
        trail = sum(1 for b in closed if b["mgmt_status"] == "closed_trail_exit")
        print(f"{label:40} closed={len(closed):4d} (trail {trail} / hard-stop {len(closed)-trail}) open={still_open} | "
              f"meanR={statistics.fmean(rr):+.2f} medR={statistics.median(rr):+.2f} p10/p25/p75/p90="
              f"{q(rr,.1):+.1f}/{q(rr,.25):+.1f}/{q(rr,.75):+.1f}/{q(rr,.9):+.1f} sumR={sum(rr):+.1f} "
              f"win(R>0)={sum(1 for x in rr if x > 0)/len(rr):.0%} >=+3R:{sum(1 for x in rr if x >= 3)/len(rr):.0%} "
              f"max={max(rr):+.1f} scaled-out={sum(1 for b in closed if b['mgmt_scaled'])}")
        sums[f"mgmt::{label.strip()}"] = dict(n_closed=len(closed), trail=trail, open=still_open,
                                              mean_r=round(statistics.fmean(rr), 3), median_r=round(statistics.median(rr), 3),
                                              p10=q(rr, .1), p25=q(rr, .25), p75=q(rr, .75), p90=q(rr, .9), sum_r=round(sum(rr), 1),
                                              win=round(sum(1 for x in rr if x > 0) / len(rr), 3), max_r=max(rr))
    print("\n== #396 MANAGEMENT READOUT (shipped _htf_management_replay: scale 40% day 3-5 -> breakeven -> 10/20 EMA trail; same entries) ==")
    mg_stats("ALL break-rows", all_breaks)
    mg_stats("first, takeable", [b for b in first if b["would_reject"] is None])
    mg_stats("first, takeable, excluding UNFILLABLE", [b for b in first if b["would_reject"] is None and not b["unfillable"]])
    mg_stats("first, would-reject stop>8%", [b for b in first if b["would_reject"] == "stop_distance_gt_8pct"])
    for y in years:
        mg_stats(f"  first, takeable, {y}", [b for b in first if b["would_reject"] is None and b["break_date"].year == y])

    # ── RS-gate sensitivity (2025-12-26+): re-apply prod's organic RS/burst OR-block at the parent
    def rs_pass(t, d, tb_i):
        sc = scores.get(t, {})
        sd = None
        for k in range(0, 6):
            if (d - timedelta(days=k)) in sc:
                sd = d - timedelta(days=k)
                break
        tb = bars[t]
        i = tb_i
        c10 = tb["c"][max(0, i - 9): i + 1].min()
        mom = c10 > 0 and (tb["c"][i] / c10 - 1.0) >= 0.25
        if sd is None:
            return mom, False
        rk, r1 = sc[sd]
        return ((rk is not None and rk <= 200) or (r1 is not None and r1 >= 80) or mom), True
    rs_window = [b for b in first if b["would_reject"] is None and b["parent_scan_date"] >= RS_SCORES_START]
    rs_in, rs_out, rs_nodata = [], [], 0
    for b in rs_window:
        tb = bars[b["ticker"]]
        i = bisect.bisect_left(tb["dates"], b["parent_scan_date"])
        ok, had = rs_pass(b["ticker"], b["parent_scan_date"], i)
        if not had:
            rs_nodata += 1
        (rs_in if ok else rs_out).append(b)
    print(f"\n-- RS-GATE SENSITIVITY ({RS_SCORES_START}+, first/takeable; prod's rs_top200 OR rs_1m>=80 OR +25% off 10-session min close at the parent date; no score row for {rs_nodata}) --")
    add("  window, no RS gate", rs_window)
    add("  window, RS gate PASSED", rs_in)
    add("  window, RS gate FAILED (prod would not have scanned)", rs_out)

    # ── per-break CSV + summary json
    fn = out_dir / "htf_replay_breaks.csv"
    cols = ["ticker", "break_date", "parent_scan_date", "parent_stage", "pivot_high_date", "pivot_high",
            "runup_pct", "base_age", "base_high", "base_low", "sma_10", "sma_20", "entry", "limit", "stop",
            "stop_kind", "max_loss_pct", "would_reject", "shares", "target", "adv20", "break_vol", "vol_x_adv",
            "break_open", "break_high", "break_low", "break_close", "gap_through_limit",
            "entry_bar_hit_target", "entry_bar_hit_stop", "outcome", "realized_r", "fwd_mfe_r",
            "fwd5", "fwd10", "fwd20", "sectype", "unfillable", "mgmt_status", "mgmt_r", "mgmt_exit_date", "mgmt_scaled"]
    with fn.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for b in all_breaks:
            w.writerow({k: (round(v, 4) if isinstance(v, float) else v) for k, v in b.items() if k in cols})
    with (out_dir / "htf_replay_summary.json").open("w") as fh:
        json.dump(dict(constants=consts, prescreen_check=dict(stored_actionable=tot, missed=len(miss)),
                       break_rule_check={k: v for k, v in bv.items() if not k.endswith("_list")},
                       stage_reconciliation=dict(match=match, mismatch=mism, kinds=dict(kinds),
                                                 prod_only_actionable=prod_only_act,
                                                 mine_only_actionable=len(mine_only_act)),
                       shadow_reconciliation=dict(replayed=len(ov), prod=len(prod_ov), both=len(ov_keys & prod_ov)),
                       rows_by_year={f"{y}": {s: stage_year[(y, s)] for s in ("WATCH", "TIGHTENING", "COILED", "TRIGGERED", "INVALIDATED", "unqualified")} for y in years},
                       summaries=sums), fh, indent=1, default=str)
    print(f"\ntotal {time.time()-t0:.0f}s; per-break CSV {fn}; summary {out_dir/'htf_replay_summary.json'}")


if __name__ == "__main__":
    main()
