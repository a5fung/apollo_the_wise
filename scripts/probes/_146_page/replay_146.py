"""#146 detection page (2026-10-11) — replay the SHIPPED `flag_detector.compute_flag_metrics` over raw daily bars,
four arms that differ in exactly ONE conjunct of the TRIGGERED test. READ-ONLY: no DB, no network, nothing in
flag_detector is patched or changed. $0.

Population: scripts/probes/_146_page/q2_bars.tsv.gz — every ticker q1_candidates.sql admitted (a SQL superset of
the detector's own pole gate; leak_check.out: 0 of 649 stored WATCH-or-better rows since 06-29 belong to a ticker
it lost) plus the corpus tickers, bars 2023-12-01 → 2026-10-09. Every ticker is scored on EVERY trading day it has
a bar and >= 60 rows of history (the live scan's own floor), from 2024-11-01 (warm-up) and REPORTED from
2025-01-02 (WINDOW_START). State is threaded per arm from the arm's OWN prior outputs, mirroring the live
queries exactly:
    yesterday stage + was-it-a-hold   most recent prior output within 5 CALENDAR days  (db.get_yesterday_flag_state)
    recent_stages                     prior outputs within 5 CALENDAR days, ascending   (db.get_recent_flag_stages)
    prior pivot                       most recent prior output with a pivot within 40 CALENDAR days
                                      (db.get_yesterday_flag_pivots, carry_days=_PIVOT_CARRY_DAYS)
    history                           the last 262 rows ending on the scan day             (get_recent_daily_history)
    prior_failure                     None — telemetry only, never reaches `stage`
Unlike prod, a row exists for every scored day (no universe gaps): this measures the RULE on a continuous chain;
board membership is tagged afterwards (report_146.py), not re-imposed.

The arms. `recent_stages` is read at exactly ONE place in compute_flag_metrics (the `was_coiled_recent` term of the
TRIGGERED test, ~L1292-1294), so appending "COILED" to the arm's real recent_stages list when a licence holds
changes the function's behaviour in that one conjunct and nowhere else:
    A  shipped       recent_stages as threaded (TRIGGERED needs COILED today or a stored COILED in the window)
    B  D2-stored     + "COILED" when a STORED label in the 5-day window is TIGHTENING / COILED / TRIGGERED
                     (held labels count — the one-token analogue of the shipped COILED licence)
    C  D2-raw        + "COILED" when a RAW read in the window (held_from_stage when the row is a hold, else stage)
                     is TIGHTENING / COILED / TRIGGERED (held labels do NOT count)
    D  no licence    + "COILED" always (the 07-12 harness's "conjunct neutralised": every qualifying close over the
                     base's highest close on >= 1.5x volume reads TRIGGERED, from WATCH too) — context only
Each arm threads its own chain, so a B-only TRIGGERED read changes B's next-night hold and licence as it would live.

Outputs (scripts/probes/_146_page/):
    arm_rows.tsv.gz      every row whose stage OR raw read is WATCH-or-better or INVALIDATED, all four arms,
                         plus EVERY row for the corpus tickers (any stage) with ATR-14 and recomputed tightness ratios
    triggered_reads.tsv  every raw TRIGGERED read (held_from_stage NULL) per arm with its forward 10 closes,
                         the base levels, the licence windows and the bar-computable universe gates
Run from the repo root (background, ~10-40 min):
    PYTHONPATH=. python scripts/probes/_146_page/replay_146.py > scripts/probes/_146_page/replay_146.log 2>&1
"""
from __future__ import annotations

import bisect
import gzip
import multiprocessing as mp
import os
import re
import sys
import time
from collections import defaultdict
from datetime import date, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from agents.market_intelligence import flag_detector as fd  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
WARMUP_START = date(2024, 11, 1)
WINDOW_START = date(2025, 1, 2)
ACTIONABLE = ("WATCH", "TIGHTENING", "COILED", "TRIGGERED")
TPLUS = ("TIGHTENING", "COILED", "TRIGGERED")
KEEP_STAGES = ACTIONABLE + ("INVALIDATED",)
CORPUS = ("CDNA", "HNGE", "MRNA", "NCI", "ATAI", "OUST", "SHAZ", "REPL", "GH", "HPE")
ARMS = ("A", "B", "C", "D")
STATE_DAYS = 5                       # db.get_yesterday_flag_state / get_recent_flag_stages — calendar days
PIVOT_DAYS = fd._PIVOT_CARRY_DAYS    # db.get_yesterday_flag_pivots carry — 40 calendar days
HIST = fd._HISTORY_DAYS              # 262 rows
MIN_ROWS = 60                        # run_flag_scan: `if not history or len(history) < 60: return None`
FWD = 10
_REASON_RE = re.compile(r"close_([\d.]+)>base_high_close_([\d.]+)\s+vol_([\d.]+)x")

BARS: dict[str, list[dict]] = {}


def load_bars(path):
    bars = defaultdict(list)
    with gzip.open(path, "rt") as fh:
        hdr = None
        for ln in fh:
            p = ln.rstrip("\n").split("\t")
            if hdr is None:
                hdr = p
                continue
            if len(p) != 7 or p[0].startswith("("):
                continue
            t, d, o, h, l, c, v = p
            if "" in (o, h, l, c):
                continue
            bars[t].append({"trade_date": date.fromisoformat(d), "open_price": float(o), "high_price": float(h),
                            "low_price": float(l), "close": float(c), "volume": float(v) if v else 0.0})
    for t in bars:
        bars[t].sort(key=lambda r: r["trade_date"])
    return bars


def _tightness_recompute(rows, pivot_idx, today_idx):
    """The code's own first-5 vs last-5 range / volume ratios (compute_flag_metrics ~L1208-1233), recomputed for a
    row the code rejected BEFORE reaching that step (corpus rows only, for the G8 side table). Labelled as such."""
    base_rows = rows[pivot_idx + 1: today_idx]
    base_age = len(base_rows)
    if base_age < 1:
        return None, None
    win = min(fd._TIGHTNESS_WINDOW, base_age)
    early = base_rows[:win]
    recent = base_rows[-win:]

    def tr_pct(i):
        prev_close = float(rows[i - 1]["close"]) if i > 0 else None
        tr = fd._wilder_tr(rows[i], prev_close)
        c = float(rows[i]["close"])
        return (tr / c * 100.0) if c > 0 else 0.0

    e = [tr_pct(pivot_idx + 1 + i) for i in range(win)]
    r = [tr_pct(today_idx - win + i) for i in range(win)]
    em, rm = fd._median_stat(e), fd._median_stat(r)
    rr = (rm / em) if em > 0 else None
    ev = sum(float(x["volume"] or 0) for x in early) / max(1, len(early))
    rv = sum(float(x["volume"] or 0) for x in recent) / max(1, len(recent))
    vr = (rv / ev) if ev > 0 else None
    return rr, vr


def replay_ticker(ticker):
    bars = BARS[ticker]
    dates = [r["trade_date"] for r in bars]
    is_corpus = ticker in CORPUS
    # per-arm chain of compact prior outputs: (scan_date, stage, held_from_stage, pivot_date, pivot_price)
    chain = {a: [] for a in ARMS}
    out_rows = []
    trig = []
    for idx, d in enumerate(dates):
        if d < WARMUP_START:
            continue
        hi = idx + 1
        rows = bars[max(0, hi - HIST):hi]
        if len(rows) < MIN_ROWS:
            continue
        today_idx = len(rows) - 1
        cutoff = d - timedelta(days=STATE_DAYS)
        pcut = d - timedelta(days=PIVOT_DAYS)
        for arm in ARMS:
            ch = chain[arm]
            # prune anything older than the pivot carry (nothing reads further back)
            while ch and ch[0][0] < pcut:
                ch.pop(0)
            window = [x for x in ch if cutoff <= x[0] < d]
            y_stage = window[-1][1] if window else None
            y_held = (window[-1][2] is not None) if window else False
            recent = [x[1] for x in window]
            ppiv = next(((x[3], x[4]) for x in reversed(ch) if x[3] is not None and x[0] < d), None)
            lic_stored = any(s in TPLUS for s in recent)
            lic_raw = any((x[2] or x[1]) in TPLUS for x in window)
            if arm == "A":
                inject = False
            elif arm == "B":
                inject = lic_stored
            elif arm == "C":
                inject = lic_raw
            else:
                inject = True
            rs = recent + ["COILED"] if inject else recent
            m = fd.compute_flag_metrics(
                rows, ticker=ticker,
                yesterday_stage=y_stage, yesterday_was_held=y_held,
                recent_stages=rs,
                prior_pivot_date=ppiv[0] if ppiv else None,
                prior_pivot_high=ppiv[1] if ppiv else None,
                prior_failure=None,
            )
            stage, held = m["stage"], m["held_from_stage"]
            ch.append((d, stage, held, m["pivot_high_date"], m["pivot_high_price"]))
            if d < WINDOW_START:
                continue
            raw = held or stage
            keep = is_corpus or stage in KEEP_STAGES or raw in KEEP_STAGES
            if not keep:
                continue
            atr_any = rr2 = vr2 = None
            if is_corpus:
                atr_any = fd._atr_14(rows, today_idx)
                if m["pivot_high_date"] is not None and m["range_contraction_ratio"] is None:
                    pidx = next((i for i in range(today_idx) if rows[i]["trade_date"] == m["pivot_high_date"]), None)
                    if pidx is not None:
                        rr2, vr2 = _tightness_recompute(rows, pidx, today_idx)
            rec = {
                "arm": arm, "ticker": ticker, "scan_date": d.isoformat(), "stage": stage, "held_from_stage": held or "",
                "raw": raw, "reason": (m["reason"] or "").replace("\t", " "),
                "pivot_high_date": m["pivot_high_date"].isoformat() if m["pivot_high_date"] else "",
                "pivot_high_price": m["pivot_high_price"], "base_age": m["base_age"], "base_high": m["base_high"],
                "base_low": m["base_low"], "runup_pct": m["runup_pct"], "range_ratio": m["range_contraction_ratio"],
                "vol_ratio": m["vol_contraction_ratio"], "fresh_fires": int(bool(m["fresh_tight_fires"])),
                "fresh_2bar_tr_pct": m["fresh_2bar_tr_pct"], "atr14_pct": m["atr14_pct"], "atr_14": m["atr_14"],
                "rmv_5d": m["rmv_5d"], "rmv_15d": m["rmv_15d"], "breakout_close": m["breakout_close"],
                "breakout_volume_ratio": m["breakout_volume_ratio"],
                "lic_stored": int(lic_stored), "lic_raw": int(lic_raw),
                "stored_window": ",".join(f"{x[1]}{'*' if x[2] else ''}" for x in window),
                "raw_window": ",".join((x[2] or x[1]) for x in window),
                "atr14_any": atr_any, "rr_recomputed": rr2, "vr_recomputed": vr2,
                "close": float(rows[-1]["close"]),
            }
            out_rows.append(rec)
            if stage == "TRIGGERED" and held is None:
                mm = _REASON_RE.search(m["reason"] or "")
                fwd = bars[idx + 1: idx + 1 + FWD]
                liq = rows[-20:]
                dv20 = sum(float(r["close"]) * float(r["volume"] or 0) for r in liq) / len(liq)
                min10 = min(float(r["close"]) for r in rows[-10:])
                trig.append({
                    "arm": arm, "ticker": ticker, "scan_date": d.isoformat(),
                    "pivot_high_date": m["pivot_high_date"].isoformat(), "pivot_high_price": m["pivot_high_price"],
                    "base_age": m["base_age"], "base_high": m["base_high"], "base_low": m["base_low"],
                    "base_high_close": float(mm.group(2)) if mm else None,
                    "breakout_close": m["breakout_close"], "breakout_volume_ratio": m["breakout_volume_ratio"],
                    "runup_pct": m["runup_pct"], "range_ratio": m["range_contraction_ratio"],
                    "vol_ratio": m["vol_contraction_ratio"],
                    "lic_stored": int(lic_stored), "lic_raw": int(lic_raw),
                    "stored_window": ",".join(f"{x[1]}{'*' if x[2] else ''}" for x in window),
                    "raw_window": ",".join((x[2] or x[1]) for x in window),
                    "coiled_in_window": int("COILED" in recent),
                    "fwd_closes": ";".join(f"{float(r['close']):.4f}" for r in fwd),
                    "fwd_lows": ";".join(f"{float(r['low_price']):.4f}" for r in fwd),
                    "fwd_n": len(fwd),
                    "close": float(rows[-1]["close"]), "dv20": dv20, "mom25": (float(rows[-1]["close"]) / min10 - 1) if min10 > 0 else None,
                    "n_rows": len(rows),
                })
    return ticker, out_rows, trig


def _fmt(v):
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:.6g}"
    return str(v)


def main():
    global BARS
    t0 = time.time()
    BARS = load_bars(os.path.join(HERE, "q2_bars.tsv.gz"))
    tickers = sorted(BARS)
    only = os.environ.get("R146_ONLY")            # smoke test: R146_ONLY=CDNA,HNGE restricts the run; outputs go to *_smoke
    suffix = ""
    if only:
        tickers = [t for t in tickers if t in set(only.split(","))]
        suffix = "_smoke"
    print(f"bars loaded: {len(tickers)} tickers, {sum(len(v) for v in BARS.values())} rows in {time.time()-t0:.0f}s", flush=True)
    last = max(v[-1]["trade_date"] for v in BARS.values())
    print(f"last bar date {last}; window {WINDOW_START} -> {last}; warm-up from {WARMUP_START}", flush=True)
    ctx = mp.get_context("fork")
    rows_fh = gzip.open(os.path.join(HERE, f"arm_rows{suffix}.tsv.gz"), "wt")
    trig_fh = open(os.path.join(HERE, f"triggered_reads{suffix}.tsv"), "w")
    rows_hdr = trig_hdr = None
    n_rows = n_trig = done = 0
    with ctx.Pool(processes=max(1, os.cpu_count() - 1)) as pool:
        for ticker, out_rows, trig in pool.imap_unordered(replay_ticker, tickers, chunksize=8):
            done += 1
            for r in out_rows:
                if rows_hdr is None:
                    rows_hdr = list(r)
                    rows_fh.write("\t".join(rows_hdr) + "\n")
                rows_fh.write("\t".join(_fmt(r[k]) for k in rows_hdr) + "\n")
                n_rows += 1
            for r in trig:
                if trig_hdr is None:
                    trig_hdr = list(r)
                    trig_fh.write("\t".join(trig_hdr) + "\n")
                trig_fh.write("\t".join(_fmt(r[k]) for k in trig_hdr) + "\n")
                n_trig += 1
            if done % 100 == 0:
                print(f"  {done}/{len(tickers)} tickers, {n_rows} kept rows, {n_trig} TRIGGERED reads, {time.time()-t0:.0f}s", flush=True)
    rows_fh.close()
    trig_fh.close()
    print(f"done: {done} tickers, {n_rows} kept rows -> arm_rows.tsv.gz, {n_trig} TRIGGERED reads -> triggered_reads.tsv, {time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
