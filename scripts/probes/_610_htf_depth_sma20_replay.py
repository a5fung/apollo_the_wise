#!/usr/bin/env python3
"""#610 — the two knobs the $MRNA label exposed, replayed from RAW BARS, both directions.

  (a) FLAG DEPTH one-bar allowance   — the shipped gate rejects on the flag's single deepest
      intraday low (`base_low < 0.75 × pivot_high`). The trader (Leif Soreide, 2026-09-17)
      took MRNA at "~26%" because the breach was "mostly one stretch day (~1% over)". The
      variant excuses exactly ONE breaching bar: the gate reads the SECOND-lowest low.
      `depth_max_breach` optionally bounds how deep the excused bar may go.
  (b) SMA20 INVALIDATION margin      — the shipped check is `close < sma_20` → INVALIDATED
      (MRNA 2026-09-16: 145.62 vs 145.67, a 0.03% margin, the session before his breakout).
      The variant is `close < sma_20 × (1 − m)` for a small stated set of m.

NOTHING in flag_detector is changed. Each variant is the SHIPPED `compute_flag_metrics`
SOURCE with exactly two asserted single-line edits, compiled into a COPY of the module's
namespace (the live module object is untouched). Why not a monkeypatch: neither knob is a
constant, and patching `_sma` would contaminate the MA-stack and COILED gates that also read
`sma_20`. Why not a hand copy: the #416 lesson — a lookalike is not evidence. The patched
function at shipped settings (0 excused bars, 0 margin) is ASSERTED byte-equal in
stage+reason to `fd.compute_flag_metrics` on every pair, and reconciled against prod's
stored stages on 2026-06-29+ (the only span whose stored stages are under today's criteria).

Inputs (pulled ONCE from prod on 2026-09-18, read-only; scratchpad — 35 MB, not for the repo):
  replay_pairs.psv  ticker|scan_date|stage|reason|pivot_high_date|pivot_high_price|runup_pct|base_age|held_from_stage
      SELECT ... FROM mi_flag_candidates WHERE scan_date >= '2026-05-04' ORDER BY ticker, scan_date;
      -- 56,657 rows / 2,749 tickers / 98 scan days (05-04 → 09-17)
  replay_bars.psv   ticker|trade_date|open|high|low|close|volume
      WITH t AS (SELECT DISTINCT ticker FROM mi_flag_candidates WHERE scan_date >= '2026-05-04')
      SELECT d.ticker, d.trade_date, d.open_price, d.high_price, d.low_price, d.close, d.volume
      FROM mi_daily_closes d JOIN t USING (ticker) WHERE d.trade_date >= '2025-04-01'
      ORDER BY d.ticker, d.trade_date;                         -- 747,175 rows

Universe = the stored (ticker, scan_date) pairs — what prod actually scanned; `get_flag_universe`
is RS / dollar-volume / burst / stage-carryforward gated (the carryforward path was added
2026-05-19, an expansion), never threshold gated, so the same pairs are fair to every variant.
The stored STAGE is used ONLY for the fidelity check (06-29+); every verdict below is recomputed
from raw bars. Seed = 05-04 → 05-17 (state threading only); report window = 05-18 → 09-17.

History per pair = the last `fd._HISTORY_DAYS` (262) TRADING rows ending at the scan date — a
ROW-COUNT slice, matching `get_recent_daily_history` since 2026-09-05 (the older grid probe's
calendar slice is documented stale in docs/setups/htf.md). State threading per variant mirrors
prod's three 5-calendar-day lookback queries from the variant's OWN prior outputs.

Usage:
  python scripts/probes/_610_htf_depth_sma20_replay.py --data-dir <scratchpad> --mrna-check
  python scripts/probes/_610_htf_depth_sma20_replay.py --data-dir <scratchpad> --only-base
  python scripts/probes/_610_htf_depth_sma20_replay.py --data-dir <scratchpad>
"""
from __future__ import annotations

import argparse
import bisect
import csv
import inspect
import pathlib
import random
import statistics
import sys
import time
from collections import Counter, defaultdict
from datetime import date, timedelta

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from agents.market_intelligence import flag_detector as fd  # noqa: E402

ACTIONABLE = ("WATCH", "TIGHTENING", "COILED", "TRIGGERED")
BASELINE_MATCH_FLOOR = 0.95
SEED_START = date(2026, 5, 4)
WINDOW_START = date(2026, 5, 18)        # report from here; earlier rows thread state only
RECONCILE_START = date(2026, 6, 29)     # stored stages under today's criteria begin here
STATE_WINDOW_DAYS = 5
CORPUS_REPLAY_FROM = date(2026, 6, 15)  # same as tests/test_htf_labelled_corpus.py

# name -> (excused bars [-1 = the spec's LITERAL close-based depth, see below], max breach of the
#          excused bar as a fraction of the pole (None = unbounded), sma20 margin)
# "Dc" is OUTSIDE the brief's two knobs and is here because the premise check showed a one-bar
# allowance cannot reach MRNA (four bars breach; second-lowest low 73.6% of the pole) while the
# spec's literal `Close >= 0.75 x High` does (lowest close 75.5%). It measures the cost of the
# 6/27 "tightened to the low" deviation recorded in docs/setups/htf.md. Not a recommendation.
VARIANTS: list[tuple[str, int, float | None, float]] = [
    ("BASE",     0, None, 0.0),
    ("D1",       1, None, 0.0),      # one bar excused, any depth
    ("D1b3",     1, 0.03, 0.0),      # one bar excused only if its low >= 72% of the pole
    ("Dc",      -1, None, 0.0),      # depth on the lowest CLOSE (spec literal) — premise correction, see above
    ("S010",     0, None, 0.001),
    ("S025",     0, None, 0.0025),
    ("S050",     0, None, 0.005),
    ("S100",     0, None, 0.010),
    ("D1+S010",  1, None, 0.001),    # the brief's minimal pair for MRNA's 09-16 (it does not reach it — see the check)
    ("Dc+S010", -1, None, 0.001),    # what MRNA's 09-16 would actually need at the two gates named in the brief
]
SMA_BINS = [0.001, 0.0025, 0.005, 0.010]
DEPTH_BREACH_BINS = [0.01, 0.02, 0.03, 0.05]


# ── the variant machinery: shipped source + two asserted single-line edits ───

_DEPTH_LINE = "    if base_low < _FLAG_DEPTH_MIN * pivot_high:\n"
_SMA_LINE = "    if sma_20 is not None and close_today < sma_20:\n"
_DEPTH_PATCH = "    if _PROBE_DEPTH_LOW(base_rows, base_low, pivot_high) < _FLAG_DEPTH_MIN * pivot_high:\n"
_SMA_PATCH = "    if sma_20 is not None and close_today < sma_20 * (1.0 - _PROBE_SMA20_MARGIN):\n"


def _depth_low_factory(excused_bars: int, max_breach: float | None):
    """Return the low the depth gate should compare. 0 excused bars = shipped behaviour."""
    def depth_low(base_rows, base_low, pivot_high):
        if excused_bars < 0:                                 # spec literal: the flag's lowest CLOSE
            return min(float(r["close"]) for r in base_rows)
        if excused_bars == 0:
            return base_low
        floor = fd._FLAG_DEPTH_MIN * pivot_high
        if base_low >= floor:
            return base_low                              # nothing to excuse
        if max_breach is not None and base_low < (fd._FLAG_DEPTH_MIN - max_breach) * pivot_high:
            return base_low                              # the deepest bar is too deep to excuse
        lows = sorted(float(r["low_price"]) for r in base_rows)
        return lows[excused_bars] if len(lows) > excused_bars else base_low
    return depth_low


def build_variant(excused_bars: int, max_breach: float | None, sma20_margin: float):
    src = inspect.getsource(fd.compute_flag_metrics)
    assert src.count(_DEPTH_LINE) == 1, "shipped depth-gate line not found exactly once — detector changed, re-derive"
    assert src.count(_SMA_LINE) == 1, "shipped sma20 line not found exactly once — detector changed, re-derive"
    src = src.replace(_DEPTH_LINE, _DEPTH_PATCH).replace(_SMA_LINE, _SMA_PATCH)
    ns = dict(vars(fd))                                  # a COPY — the live module is not touched
    ns["_PROBE_DEPTH_LOW"] = _depth_low_factory(excused_bars, max_breach)
    ns["_PROBE_SMA20_MARGIN"] = float(sma20_margin)
    exec(compile(src, f"<variant excused={excused_bars} breach={max_breach} m={sma20_margin}>", "exec"), ns)
    return ns["compute_flag_metrics"]


# ── loading ──────────────────────────────────────────────────────────────────

def _f(x):
    return float(x) if x not in ("", None) else None


def load_bars(path: pathlib.Path):
    bars: dict[str, list[dict]] = defaultdict(list)
    with path.open() as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line:
                continue
            t, d, o, h, l, c, v = line.split("|")
            bars[t].append({"trade_date": date.fromisoformat(d), "open_price": _f(o), "high_price": _f(h),
                            "low_price": _f(l), "close": _f(c), "volume": _f(v)})
    for t in bars:
        bars[t].sort(key=lambda r: r["trade_date"])
    return bars


def load_pairs(path: pathlib.Path):
    pairs: dict[str, list[dict]] = defaultdict(list)
    with path.open() as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line:
                continue
            t, d, stage, reason, pd_, pp, ru, ba, held = line.split("|")
            pairs[t].append({"scan_date": date.fromisoformat(d), "stage": stage, "reason": reason,
                             "pivot_high_date": date.fromisoformat(pd_) if pd_ else None,
                             "pivot_high_price": _f(pp), "runup_pct": _f(ru),
                             "base_age": int(ba) if ba else None, "held_from_stage": held or None})
    for t in pairs:
        pairs[t].sort(key=lambda r: r["scan_date"])
    return pairs


def load_corpus_bars(path: pathlib.Path):
    return load_bars(path)


# ── replay ───────────────────────────────────────────────────────────────────

def replay_ticker(fn, ticker: str, tb: list[dict], scan_dates: list[date]) -> tuple[list[dict], int, int]:
    """One variant over one ticker's scan dates, prod-style state threading from its own outputs."""
    tdates = [r["trade_date"] for r in tb]
    prior: list[dict] = []
    out: list[dict] = []
    stale = skipped = 0
    for d in scan_dates:
        hi = bisect.bisect_right(tdates, d)
        lo = max(0, hi - fd._HISTORY_DAYS)
        rows = tb[lo:hi]
        if not rows or len(rows) < 60:
            skipped += 1                      # prod: no row written
            continue
        if rows[-1]["trade_date"] != d:
            stale += 1                        # prod scored an older bar that day (no bar yet at 17:25 ET)
        cutoff = d - timedelta(days=STATE_WINDOW_DAYS)
        window = [r for r in prior if cutoff <= r["scan_date"] < d]
        ppiv = next(((r["pivot_high_date"], r["pivot_high_price"])
                     for r in reversed(window) if r["pivot_high_date"] is not None), None)
        m = fn(rows, ticker=ticker,
               yesterday_stage=window[-1]["stage"] if window else None,
               recent_stages=[r["stage"] for r in window],
               prior_pivot_date=ppiv[0] if ppiv else None,
               prior_pivot_high=ppiv[1] if ppiv else None)
        m["scan_date"] = d
        m["close_today"] = rows[-1]["close"]
        prior.append(m)
        out.append(m)
    return out, stale, skipped


def run_variant(fn, bars, pairs) -> tuple[dict[str, list[dict]], int, int]:
    res: dict[str, list[dict]] = {}
    stale = skipped = 0
    for ticker, plist in pairs.items():
        tb = bars.get(ticker)
        if not tb:
            skipped += len(plist)
            continue
        out, s, k = replay_ticker(fn, ticker, tb, [p["scan_date"] for p in plist])
        res[ticker] = out
        stale += s
        skipped += k
    return res, stale, skipped


# ── outcomes (raw bars) ──────────────────────────────────────────────────────

def _idx(dates_t, d):
    i = bisect.bisect_left(dates_t, d)
    return i if i < len(dates_t) and dates_t[i] == d else None


def fwd(tb, dates_t, d, k):
    i = _idx(dates_t, d)
    if i is None or i + k >= len(tb):
        return None
    c0 = tb[i]["close"]
    return tb[i + k]["close"] / c0 - 1.0 if c0 else None


def excursion(tb, dates_t, d, k):
    i = _idx(dates_t, d)
    if i is None or i + k >= len(tb):
        return None, None
    c0 = tb[i]["close"]
    seg = tb[i + 1:i + 1 + k]
    return max(r["high_price"] for r in seg) / c0 - 1.0, min(r["low_price"] for r in seg) / c0 - 1.0


def closes_above(tb, dates_t, d, level, k):
    """Any CLOSE above `level` within the next k sessions (None if the window is unmatured)."""
    i = _idx(dates_t, d)
    if i is None or level is None or i + k >= len(tb):
        return None
    return any(r["close"] > level for r in tb[i + 1:i + 1 + k])


def _pct(n, d):
    return f"{n}/{d} = {n / d:.0%}" if d else f"{n}/0"


def _stats(vals):
    vals = [v for v in vals if v is not None]
    if not vals:
        return "n=0"
    return (f"n={len(vals)} med={statistics.median(vals):+.1%} mean={statistics.fmean(vals):+.1%} "
            f">=+10%:{sum(v >= 0.10 for v in vals) / len(vals):.0%} "
            f">=+20%:{sum(v >= 0.20 for v in vals) / len(vals):.0%} "
            f"<0:{sum(v < 0 for v in vals) / len(vals):.0%}")


def outcome_block(items, bars, dates_index, *, label):
    """items = [(ticker, date, base_high)]. Prints the repo's standard yardsticks with matured n."""
    f10 = [fwd(bars[t], dates_index[t], d, 10) for t, d, _ in items]
    f20 = [fwd(bars[t], dates_index[t], d, 20) for t, d, _ in items]
    mfe10 = [excursion(bars[t], dates_index[t], d, 10)[0] for t, d, _ in items]
    mfe20 = [excursion(bars[t], dates_index[t], d, 20)[0] for t, d, _ in items]
    mae20 = [excursion(bars[t], dates_index[t], d, 20)[1] for t, d, _ in items]
    brk10 = [closes_above(bars[t], dates_index[t], d, bh, 10) for t, d, bh in items]
    n = len(items)
    m10 = [v for v in f10 if v is not None]
    m20 = [v for v in f20 if v is not None]
    e10 = [v for v in mfe10 if v is not None]
    b10 = [v for v in brk10 if v is not None]
    print(f"  {label}: n={n} (fwd10 matured {len(m10)}, fwd20 matured {len(m20)})")
    print(f"    fwd10 : {_stats(f10)}")
    print(f"    fwd20 : {_stats(f20)}")
    print(f"    MFE10 : {_stats(mfe10)}   [ran >=+20% within 10 sessions: {_pct(sum(v >= 0.20 for v in e10), len(e10))}]")
    print(f"    MFE20 : {_stats(mfe20)}   MAE20: {_stats(mae20)}")
    print(f"    closed above the flag high within 10 sessions: {_pct(sum(b10), len(b10))}")
    print(f"    down a month later (fwd20 < 0): {_pct(sum(v < 0 for v in m20), len(m20))}")
    return dict(n=n, f10=m10, f20=m20, mfe10=e10, brk10=b10)


def episodes(results_t):
    """Maximal runs of consecutive actionable rows sharing one pivot_high_date (the grid's definition)."""
    eps, cur = [], None
    for m in results_t:
        if m["scan_date"] < WINDOW_START:
            continue
        act = m["stage"] in ACTIONABLE
        key = m["pivot_high_date"]
        if act and cur is not None and cur["pivot"] == key:
            cur["rows"].append(m)
        elif act:
            cur = {"pivot": key, "rows": [m]}
            eps.append(cur)
        else:
            cur = None
    for e in eps:
        e["first"] = e["rows"][0]
        e["trig"] = next((r for r in e["rows"] if r["stage"] == "TRIGGERED"), None)
    return eps


def reason_family(r: str | None) -> str:
    r = r or "null"
    for pfx, fam in (("adr_", "adr"), ("adv_", "adv"), ("runup_", "runup"), ("base_age_", "base_age"),
                     ("flag_low", "flag_depth"), ("pole_", "not_stage2"), ("ma_stack", "ma_stack"),
                     ("flagpole", "flagpole_vol"), ("no_pivot", "no_pivot")):
        if r.startswith(pfx):
            return fam
    if "_below_sma20_" in r:
        return "inv_sma20"
    if "_below_sma50_" in r:
        return "inv_sma50"
    if "_below_sma200_" in r:
        return "inv_sma200"
    if "_below_base_low_close_" in r:
        return "inv_base_low_close"
    if "_over_" in r and r.startswith("base_age"):
        return "inv_base_age"
    return r.split("_")[0]


# ── ceilings from the BASELINE pass (what each knob could touch at most) ─────

def ceilings(base_res, bars, dates_index):
    print("\n== CEILINGS from the baseline pass (window rows only) ==")
    sma_rows, sma_tick, sma_bins = 0, set(), Counter()
    for t, rl in base_res.items():
        for m in rl:
            if m["scan_date"] < WINDOW_START or m["stage"] != "INVALIDATED" or "_below_sma20_" not in (m["reason"] or ""):
                continue
            sma_rows += 1
            sma_tick.add(t)
            margin = (m["sma_20"] - m["close_today"]) / m["sma_20"]
            b = next((f"<= {x:.2%}" for x in SMA_BINS if margin <= x), f"> {SMA_BINS[-1]:.1%}")
            sma_bins[b] += 1
    print(f"  SMA20 INVALIDATED rows: {sma_rows} rows / {len(sma_tick)} tickers; by how far the close sat under the SMA20:")
    cum = 0
    for x in SMA_BINS:
        cum += sma_bins[f"<= {x:.2%}"]
        print(f"    within {x:.2%}: {cum} rows (cumulative) = {cum / max(1, sma_rows):.0%} of SMA20 kills")
    print(f"    beyond {SMA_BINS[-1]:.1%}: {sma_bins[f'> {SMA_BINS[-1]:.1%}']} rows")

    dep_rows, dep_eps = 0, set()
    breach_bars = Counter()
    one_bar_breach = Counter()
    one_bar_eps = set()
    for t, rl in base_res.items():
        tb, td = bars[t], dates_index[t]
        for m in rl:
            if m["scan_date"] < WINDOW_START or not (m["reason"] or "").startswith("flag_low"):
                continue
            dep_rows += 1
            dep_eps.add((t, m["pivot_high_date"]))
            pi = _idx(td, m["pivot_high_date"])
            ti = _idx(td, m["scan_date"])
            if pi is None or ti is None:
                continue
            floor = fd._FLAG_DEPTH_MIN * m["pivot_high_price"]
            nb = sum(1 for r in tb[pi + 1:ti] if r["low_price"] < floor)
            breach_bars["1" if nb == 1 else "2" if nb == 2 else "3+"] += 1
            if nb == 1:
                breach = fd._FLAG_DEPTH_MIN - m["base_low"] / m["pivot_high_price"]
                one_bar_breach[next((f"<= {x:.0%}" for x in DEPTH_BREACH_BINS if breach <= x), f"> {DEPTH_BREACH_BINS[-1]:.0%}")] += 1
                one_bar_eps.add((t, m["pivot_high_date"]))
    print(f"  flag-depth rejects: {dep_rows} rows / {len(dep_eps)} (ticker, pole) episodes; bars breaching 75% of the pole per row: "
          f"{dict(breach_bars)}")
    print(f"    exactly ONE breaching bar: {breach_bars['1']} rows / {len(one_bar_eps)} episodes = the most a one-bar allowance can touch")
    print(f"    ...and how far that one bar breached (points of the pole below 75%): {dict(sorted(one_bar_breach.items()))}")


# ── corpus (N=8) under every variant ─────────────────────────────────────────

def corpus_replay(fn, ticker, tb, through):
    dates = [r["trade_date"] for r in tb]
    out, _, _ = replay_ticker(fn, ticker, tb, [d for d in dates if CORPUS_REPLAY_FROM <= d <= through])
    return {m["scan_date"]: m for m in out}


def corpus_block(variant_fns, corpus_bars):
    from tests.fixtures.htf_labelled import HTF_LABELLED
    print("\n== LABELLED CORPUS (N=8, one contested; direction only, never a rate) — verdict on each member's assert dates ==")
    print(f"  {'member':6} {'label':10} {'date':10} " + " ".join(f"{n:>12}" for n, *_ in VARIANTS))
    flips = []
    for mem in HTF_LABELLED:
        tb = corpus_bars.get(mem.ticker)
        if not tb:
            print(f"  {mem.ticker}: no fixture bars")
            continue
        per = {name: corpus_replay(fn, mem.ticker, tb, max(mem.assert_dates)) for name, fn in variant_fns.items()}
        kind = "POSITIVE" if mem.ticker in ("CDNA", "HNGE", "MRNA") else "negative"
        for d in mem.assert_dates:
            cells = []
            for name, *_ in VARIANTS:
                m = per[name].get(d)
                s = "n/a" if m is None else (m["stage"] if m["stage"] in ACTIONABLE else f"x:{reason_family(m['reason'])}")
                cells.append(f"{s:>12}")
                if m is not None and name != "BASE":
                    b = per["BASE"].get(d)
                    if b is not None and (b["stage"] in ACTIONABLE) != (m["stage"] in ACTIONABLE):
                        flips.append((mem.ticker, kind, d, name, b["stage"], b["reason"], m["stage"], m["reason"]))
            print(f"  {mem.ticker:6} {kind:10} {d.isoformat():10} " + " ".join(cells))
    print("  FLIPS vs BASE (actionable <-> not) on assert dates:")
    if not flips:
        print("    none")
    for f in flips:
        print(f"    {f[0]} ({f[1]}) {f[2]} under {f[3]}: {f[4]} [{f[5]}] -> {f[6]} [{f[7]}]")
    return flips


# ── MRNA day-by-day (the premise check) ──────────────────────────────────────

def mrna_check(bars, pairs, variant_fns):
    t = "MRNA"
    tb = bars[t]
    td = [r["trade_date"] for r in tb]
    pole_date, pole = None, None
    print("\n== MRNA — bars inside the flag vs the 75% floor ==")
    # locate the flag from the stored pole (prod: pivot 176.66)
    stored = [p for p in pairs[t] if p["pivot_high_price"] and abs(p["pivot_high_price"] - 176.66) < 0.01]
    if stored:
        pole_date, pole = stored[0]["pivot_high_date"], stored[0]["pivot_high_price"]
    pi = _idx(td, pole_date) if pole_date else None
    if pi is not None:
        floor = fd._FLAG_DEPTH_MIN * pole
        seg = tb[pi + 1:]
        lows = sorted((r["low_price"], r["trade_date"]) for r in seg if r["trade_date"] <= date(2026, 9, 16))
        breaching = [(l, d) for l, d in lows if l < floor]
        print(f"  pole {pole_date} {pole:.2f}; 75% floor = {floor:.2f}; bars in the flag through 09-16 = {len(lows)}")
        print(f"  bars with low < floor: {len(breaching)} -> {[(d.isoformat(), l) for l, d in breaching]}")
        print(f"  three lowest lows: {[(d.isoformat(), l) for l, d in lows[:3]]}; second-lowest / pole = {lows[1][0] / pole:.4f}")
        print(f"  lowest CLOSE in the flag / pole = {min(r['close'] for r in seg if r['trade_date'] <= date(2026, 9, 16)) / pole:.4f}"
              f"  (the spec's literal form is Close >= 0.75 x High)")
    print("\n== MRNA — day by day, 08-19 -> 09-17, per variant (stage [reason family]) ==")
    scan_dates = [p["scan_date"] for p in pairs[t]]
    per = {name: {m["scan_date"]: m for m in replay_ticker(fn, t, tb, scan_dates)[0]} for name, fn in variant_fns.items()}
    names = [n for n, *_ in VARIANTS]
    print(f"  {'date':10} {'close':>7} {'sma20':>7} " + " ".join(f"{n:>14}" for n in names))
    for d in scan_dates:
        if d < date(2026, 8, 19):
            continue
        b = per["BASE"].get(d)
        if b is None:
            continue
        cells = []
        for n in names:
            m = per[n].get(d)
            s = "n/a" if m is None else (m["stage"] if m["stage"] in ACTIONABLE else
                                          ("INV:" if m["stage"] == "INVALIDATED" else "x:") + reason_family(m["reason"]))
            cells.append(f"{s:>14}")
        sma = f"{b['sma_20']:.2f}" if b.get("sma_20") else "-"
        print(f"  {d.isoformat():10} {b['close_today']:7.2f} {sma:>7} " + " ".join(cells))
    for n in names:
        m = per[n].get(date(2026, 9, 17))
        if m:
            print(f"  09-17 full reason under {n}: stage={m['stage']} reason={m['reason']} sma10={m.get('sma_10')} sma20={m.get('sma_20')}")


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--only-base", action="store_true")
    ap.add_argument("--mrna-check", action="store_true", help="premise checks on MRNA only, then exit")
    ap.add_argument("--corpus-bars", default="tests/fixtures/htf_labelled_bars.psv")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    dd = pathlib.Path(args.data_dir)
    out_dir = pathlib.Path(args.out) if args.out else dd / "out"
    out_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    bars = load_bars(dd / "replay_bars.psv")
    pairs = load_pairs(dd / "replay_pairs.psv")
    dates_index = {t: [r["trade_date"] for r in tb] for t, tb in bars.items()}
    n_pairs = sum(len(v) for v in pairs.values())
    if n_pairs < 50000 or len(bars) < 2500:
        raise SystemExit(f"input looks truncated: {n_pairs} pairs / {len(bars)} tickers")
    scan_dates_all = sorted({p["scan_date"] for pl in pairs.values() for p in pl})
    window_days = [d for d in scan_dates_all if d >= WINDOW_START]
    print(f"loaded {sum(len(v) for v in bars.values()):,} bars / {len(bars):,} tickers; {n_pairs:,} pairs over "
          f"{len(scan_dates_all)} scan days ({scan_dates_all[0]} -> {scan_dates_all[-1]}); report window {WINDOW_START} -> "
          f"{scan_dates_all[-1]} = {len(window_days)} scan days; last bar {max(max(td) for td in dates_index.values())}  ({time.time() - t0:.0f}s)")

    variant_fns = {name: build_variant(k, mb, m) for name, k, mb, m in VARIANTS}

    # ── equivalence: the patched function at shipped settings == the shipped function
    rng = random.Random(610)
    sample = rng.sample([(t, p["scan_date"]) for t, pl in pairs.items() for p in pl], 1500)
    diffs = 0
    for t, d in sample:
        tb = bars.get(t)
        if not tb:
            continue
        a = replay_ticker(fd.compute_flag_metrics, t, tb, [d])[0]
        b = replay_ticker(variant_fns["BASE"], t, tb, [d])[0]
        if [(m["stage"], m["reason"]) for m in a] != [(m["stage"], m["reason"]) for m in b]:
            diffs += 1
    assert diffs == 0, f"patched-at-shipped-settings differs from fd.compute_flag_metrics on {diffs} sampled pairs"
    print(f"equivalence: patched function at shipped settings == fd.compute_flag_metrics on {len(sample)} sampled pairs (0 diffs)")

    if args.mrna_check:
        mrna_check(bars, pairs, variant_fns)
        return

    stored = {(t, p["scan_date"]): p for t, pl in pairs.items() for p in pl}
    results: dict[str, dict[str, list[dict]]] = {}
    summaries: dict[str, dict] = {}
    for name, k, mb, m in (VARIANTS[:1] if args.only_base else VARIANTS):
        t1 = time.time()
        res, stale, skipped = run_variant(variant_fns[name], bars, pairs)
        results[name] = res
        # per-pair CSV (window only)
        with (out_dir / f"{name}.csv").open("w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["ticker", "scan_date", "stage", "reason", "pivot_date", "pivot_price", "runup", "base_age",
                        "base_high", "base_low", "close", "sma_20", "fwd10", "fwd20", "mfe10", "mfe20", "mae20", "brk10"])
            for t, rl in res.items():
                tb, td = bars[t], dates_index[t]
                for r in rl:
                    if r["scan_date"] < WINDOW_START:
                        continue
                    d = r["scan_date"]
                    mfe10 = excursion(tb, td, d, 10)[0]
                    mfe20, mae20 = excursion(tb, td, d, 20)
                    w.writerow([t, d, r["stage"], r["reason"], r["pivot_high_date"], r["pivot_high_price"],
                                None if r["runup_pct"] is None else round(r["runup_pct"], 4), r["base_age"],
                                r["base_high"], r["base_low"], r["close_today"], r["sma_20"],
                                *(None if v is None else round(v, 4) for v in (fwd(tb, td, d, 10), fwd(tb, td, d, 20), mfe10, mfe20, mae20)),
                                closes_above(tb, td, d, r["base_high"], 10)])
        if name == "BASE":
            match = mism = 0
            kinds = Counter()
            for t, rl in res.items():
                for r in rl:
                    if r["scan_date"] < RECONCILE_START:
                        continue
                    s = stored.get((t, r["scan_date"]))
                    if s is None:
                        continue
                    if s["stage"] == r["stage"]:
                        match += 1
                    else:
                        mism += 1
                        kinds["mna_filter" if (s["reason"] or "").startswith("mna_filter") else f"{s['stage']}->{r['stage']}"] += 1
            rate = match / max(1, match + mism)
            print(f"\nBASELINE RECONCILIATION vs prod's stored stages, {RECONCILE_START}+ only: {match:,} match / {mism:,} mismatch = {rate:.2%} "
                  f"(stale-last-bar pairs {stale}, skipped<60rows {skipped}); mismatch kinds {dict(kinds.most_common(8))}")
            if rate < BASELINE_MATCH_FLOOR:
                raise SystemExit(f"baseline match {rate:.2%} < floor {BASELINE_MATCH_FLOOR:.0%} — do NOT read the variants")
            ceilings(res, bars, dates_index)

        stage_rows = Counter()
        act_tickers = set()
        ep_list = []
        for t, rl in res.items():
            for r in rl:
                if r["scan_date"] >= WINDOW_START:
                    stage_rows[r["stage"]] += 1
                    if r["stage"] in ACTIONABLE:
                        act_tickers.add(t)
            for e in episodes(rl):
                e["ticker"] = t
                ep_list.append(e)
        act_rows = sum(stage_rows[s] for s in ACTIONABLE)
        trig = [(e["ticker"], e["trig"]["scan_date"]) for e in ep_list if e["trig"] is not None]
        summaries[name] = dict(act_rows=act_rows, act_per_day=act_rows / len(window_days), act_tickers=len(act_tickers),
                               episodes=ep_list, ep_keys={(e["ticker"], e["pivot"]) for e in ep_list}, trig=trig,
                               stage_rows=dict(stage_rows))
        print(f"\n== {name}  ({time.time() - t1:.0f}s) == rows by stage {dict(stage_rows)}; actionable {act_rows:,} "
              f"({act_rows / len(window_days):.1f}/day) | tickers {len(act_tickers)} | episodes {len(ep_list)} | TRIGGERED {len(trig)}")

    if args.only_base:
        print(f"\ntotal {time.time() - t0:.0f}s")
        return

    # ── both directions vs BASE
    b = summaries["BASE"]
    base_rows = {(t, r["scan_date"]): r for t, rl in results["BASE"].items() for r in rl if r["scan_date"] >= WINDOW_START}
    print("\n== THE BASELINE'S OWN ADMITTED POPULATION (the comparison every admitted row must be read against) ==")
    base_first = [(e["ticker"], e["first"]["scan_date"], e["first"]["base_high"]) for e in b["episodes"]]
    outcome_block(base_first, bars, dates_index, label="BASE episodes, from the first actionable day")
    outcome_block([(t, d, base_rows[(t, d)]["base_high"]) for t, d in b["trig"]], bars, dates_index, label="BASE TRIGGERED events")

    for name, k, mb, m in VARIANTS[1:]:
        s = summaries[name]
        vres = results[name]
        vrows = {(t, r["scan_date"]): r for t, rl in vres.items() for r in rl if r["scan_date"] >= WINDOW_START}
        newly = [(key, base_rows[key]) for key, r in vrows.items()
                 if r["stage"] in ACTIONABLE and key in base_rows and base_rows[key]["stage"] not in ACTIONABLE]
        lost = [key for key, r in vrows.items() if r["stage"] not in ACTIONABLE and key in base_rows and base_rows[key]["stage"] in ACTIONABLE]
        fam = Counter(reason_family(br["reason"]) + ("" if br["stage"] != "INVALIDATED" else "") for _, br in newly)
        print(f"\n==== {name}: excused bars={k} max_breach={mb} sma20_margin={m:.2%} ====")
        print(f"  actionable {s['act_rows']:,} ({s['act_per_day']:.1f}/day vs {b['act_per_day']:.1f}) | tickers {s['act_tickers']} (vs {b['act_tickers']}) | "
              f"episodes {len(s['episodes'])} (vs {len(b['episodes'])}) | TRIGGERED {len(s['trig'])} (vs {len(b['trig'])})")
        print(f"  rows newly actionable: {len(newly)} / {len({t for (t, _), _ in newly})} tickers — by what BASE said on that row: {dict(fam.most_common())}")
        print(f"  rows no longer actionable (knock-on): {len(lost)} / {len({t for t, _ in lost})} tickers")
        # new episodes (never on the board under BASE)
        new_eps = [e for e in s["episodes"] if (e["ticker"], e["pivot"]) not in b["ep_keys"]]
        lost_eps = [e for e in b["episodes"] if (e["ticker"], e["pivot"]) not in s["ep_keys"]]
        print(f"  NEW episodes (ticker+pole never actionable under BASE): {len(new_eps)} / {len({e['ticker'] for e in new_eps})} tickers; "
              f"lost episodes: {len(lost_eps)}")
        if new_eps:
            outcome_block([(e["ticker"], e["first"]["scan_date"], e["first"]["base_high"]) for e in new_eps], bars, dates_index,
                          label="NEW episodes, from their first actionable day")
            reached = Counter(max(e["rows"], key=lambda r: ACTIONABLE.index(r["stage"]))["stage"] for e in new_eps)
            print(f"    highest stage reached by the new episodes: {dict(reached)}")
            print("    new episodes (ticker first-day rows highest fwd10/fwd20/MFE20):")
            for e in sorted(new_eps, key=lambda e: e["first"]["scan_date"]):
                t, d = e["ticker"], e["first"]["scan_date"]
                f10, f20 = fwd(bars[t], dates_index[t], d, 10), fwd(bars[t], dates_index[t], d, 20)
                mfe = excursion(bars[t], dates_index[t], d, 20)[0]
                hs = max(e["rows"], key=lambda r: ACTIONABLE.index(r["stage"]))["stage"]
                fmt = lambda v: "unmatured" if v is None else f"{v:+.0%}"
                print(f"      {t:6} {d.isoformat()[5:]} {len(e['rows']):3d}d {hs:10} {fmt(f10)}/{fmt(f20)}/{fmt(mfe)}")
        # retained rows (the SMA20 knob's effect): BASE INVALIDATED on sma20 -> variant actionable
        retained = [(key, br) for key, br in newly if reason_family(br["reason"]) == "inv_sma20"]
        if retained:
            items = [(t, d, vrows[(t, d)]["base_high"]) for (t, d), _ in retained]
            outcome_block(items, bars, dates_index, label="RETAINED rows (BASE killed on SMA20, variant kept), from the retained day")
            # what the variant itself did next within 5 sessions
            later_inv = later_trig = 0
            for (t, d), _ in retained:
                nxt = [r for r in vres[t] if d < r["scan_date"] <= d + timedelta(days=7)]
                if any(r["stage"] == "INVALIDATED" for r in nxt):
                    later_inv += 1
                if any(r["stage"] == "TRIGGERED" for r in nxt):
                    later_trig += 1
            print(f"    of those {len(retained)} retained rows: the variant itself INVALIDATED within 5 sessions anyway {later_inv}; "
                  f"TRIGGERED within 5 sessions {later_trig}")
        # TRIGGERED delta
        new_trig = sorted(set(s["trig"]) - set(b["trig"]))
        lost_trig = sorted(set(b["trig"]) - set(s["trig"]))
        print(f"  TRIGGERED events: +{len(new_trig)} new, -{len(lost_trig)} lost")
        for t, d in new_trig:
            f10, f20 = fwd(bars[t], dates_index[t], d, 10), fwd(bars[t], dates_index[t], d, 20)
            mfe = excursion(bars[t], dates_index[t], d, 20)[0]
            fmt = lambda v: "unmatured" if v is None else f"{v:+.0%}"
            print(f"    + {t} {d} fwd10 {fmt(f10)} fwd20 {fmt(f20)} MFE20 {fmt(mfe)}   [BASE that day: {base_rows[(t, d)]['stage']} {base_rows[(t, d)]['reason']}]")
        for t, d in lost_trig:
            print(f"    - {t} {d}   [variant that day: {vrows[(t, d)]['stage']} {vrows[(t, d)]['reason']}]")

    corpus_bars = load_corpus_bars(pathlib.Path(args.corpus_bars))
    corpus_block(variant_fns, corpus_bars)
    mrna_check(bars, pairs, variant_fns)
    print(f"\ntotal {time.time() - t0:.0f}s; per-pair CSVs in {out_dir}")


if __name__ == "__main__":
    main()
