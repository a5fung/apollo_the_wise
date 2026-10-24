#!/usr/bin/env python3
"""#705 — HIS EXITS 01: where he sold, and which exit rule reproduces it (docs/analysis/cb_his_exits_study_2026-10-24.md).

The frozen holdings replay (`scripts/probes/_705_holdings_1024/02_replay.py`, sha pinned below) is IMPORTED read-only, and through it the
frozen second and first reads, the runner and the cb module. Nothing in them is edited. This module reuses its loaders (`load_all`,
`event_facts`), its panel-exit trade (`panel_trades_of`), its market comparison (`curve_on_window`, `market_stats`, `bar_verdict`) and the
first replay's `Trade` / `make_trade` / `simulate` (the holdings sizing `cap_30`: 1% risk, 30% cap, 30% per stock, no margin). The walk
loop is a copy of the holdings replay's (`walk_all`) with its own `walk_entry`: the same ORH5 entry and low-of-day stop for EVERY rule, so
the comparison isolates the EXIT; the rules go through `cb.walk_his_arms` (the `Arm` dataclass: partials, +R targets, trails, the stall
cut, a fixed-session time stop) and, for the two shapes `Arm` cannot express (selling into strength / on a gap-down), through `walk_x`, a
daily step parity-tested against `cb.walk_exit` on the rule they share (the plain 20-day trail).

STAGES (the time split: 2020 buys fit, 2021-22 buys check; the registration's order):
  --describe-2020   DESCRIBE his exits on the 2020 deciding buys (E in 2020-01-27..2020-12-31): days held to his exit window, the R at his
                    exit as a RANGE over the window [exit_lo, exit_hi], each marker (the 10- and 20-day first close below, +2R / +3R,
                    a gap-down day, a big up day, the stall, a close below the level, the 3-5 day count) before / within / after his
                    window, our speed-trail exit before / inside / after it, the top tail of his R minus ours. Reads 2020 only.
  --fit             the 2020 accounts: every candidate rule, the speed trail (DECIDING of the holdings replay), his panel exits, through
                    the frozen `simulate` (cap_30) from 2020-01-27; the market comparison over 2020-01-27..2020-12-31; the share of the
                    panel-exit result each rule recovers. Writes once. Prints the choice by the registered criterion.
  --pins            the pins (sha256) to paste under the doc's freeze marker line AFTER the `CHOSEN:` line is written above it.
  --check           the 2021-22 accounts (E in 2021-01-04..2022-06-14), the same table, ONCE: refuses unless every pin incl. the doc body
                    sits under the marker, the fit printout exists, a `CHOSEN:` line exists above the marker, and its own printout does not.
                    Then the description of ALL deciding buys (the 2021-22 rows for the first time) and the beside sets.

No subagent, no DB, no network. Read-only on every input. Nothing dated after 2024-12-31 is kept from any era-B file (the holdings
loader's cut). Outputs: this folder's printouts; data under `holdings_1024/his_exits/`.
"""
from __future__ import annotations

import argparse
import bisect
import hashlib
import importlib.util
import math
import os
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, replace as dc_replace
from datetime import date
from typing import Optional

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
H_PATH = os.path.join(REPO, "scripts", "probes", "_705_holdings_1024", "02_replay.py")
H_TESTS = os.path.join(REPO, "scripts", "probes", "_705_holdings_1024", "test_02_replay.py")
H_SHA = "4275d72f82aaf66c7c24372afe48e0b503dedb51e2c7715d8fbd26c4372e9ce9"        # the holdings replay's freeze record (holdings_module)
H_TESTS_SHA = "eee66bf08ef8f70c5da66b4aeec0f626f592ca327dcfc7c6c0c6fd1943a0b75f"  # holdings_tests


def sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_holdings():
    got = sha(H_PATH)
    if got != H_SHA:
        raise SystemExit(f"REFUSED: the holdings replay module is not the frozen one ({got} vs {H_SHA})")
    spec = importlib.util.spec_from_file_location("_705_holdings02_frozen_x", H_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_705_holdings02_frozen_x"] = mod
    spec.loader.exec_module(mod)
    return mod


H = _load_holdings()
ex, rp, R, cb = H.ex, H.rp, H.R, H.cb

# ═════════════════════════════════════════════════════════════════════════════════════════════
# paths, windows, constants (every number here is fixed before the stage that reads it)
# ═════════════════════════════════════════════════════════════════════════════════════════════
OUT_DIR = f"{H.H_DIR}/his_exits"
DOC = os.path.join(REPO, "docs", "analysis", "cb_his_exits_study_2026-10-24.md")
P_DESC_2020 = os.path.join(HERE, "01_describe_2020.txt")
P_FIT = os.path.join(HERE, "01_fit.txt")
P_CHECK = os.path.join(HERE, "01_check.txt")
P_DESC_ALL = os.path.join(HERE, "01_describe_all.txt")
STOPPED = os.path.join(HERE, "01_check.STOPPED.txt")
FREEZE_MARKER = H.FREEZE_MARKER                   # the one line the doc-body hash stops at
TRADES_FROZEN = os.path.join(H.OUT_DIR, "trades.tsv.gz")   # the holdings replay's walk (parity on 2020 only before the check)

HORIZON = H.HORIZON
CAP30 = H.CAP30
SPEED_ARM = H.SPEED_ARM                           # d3_p33_tspd: the holdings replay's DECIDING exit = "ours"
PRIMARY_ARM = H.PRIMARY_ARM                       # p33_s3_t10: beside
FIT_WINDOW = ("2020-01-27", "2020-12-31")         # buys with E inside; the account and the market comparison over these sessions
CHECK_WINDOW = ("2021-01-04", "2022-06-14")       # the holdings deciding window's remainder (first 2021 session .. the last stream before the gap)
EXIT_SLIPS = rp.EXIT_SLIPS
# the description's markers, in ADR20 units (the module's unit: ADR20 x the price)
GAP_X = 0.5                                       # a gap-down day: open <= prior close x (1 - GAP_X x ADR20)
UP_X = 1.5                                        # a big up day: close >= prior close x (1 + UP_X x ADR20)
EXT_X = 2.0                                       # an extension: close >= SMA10 x (1 + EXT_X x ADR20)
STALL_S, STALL_R = cb.STALL_CUT_SESSION, cb.STALL_CUT_R   # 3, 1.0: no high at fill + 1R by the close of session 3
DAY_BUCKETS = ((0, 0, "0 (E itself)"), (1, 2, "1-2"), (3, 5, "3-5"), (6, 10, "6-10"), (11, 20, "11-20"), (21, 10**6, ">20"))
TOP_TAIL = 0.10                                   # the top decile of (his R at exit_hi - ours)
RECOVERY_BAR = 0.25                               # the check's bar: the chosen rule recovers >= 25% of the ln-gap speed -> panel, and beats the speed trail
DROP_TOP = 3                                      # beside: every account without the 3 entries with the highest panel R
TIME_N = 5                                        # B1 / B2: the time stop's session (fixed from the 2020 description, §4 of the doc)
TIME_UNLESS_R = 2.0                               # B2: a trade that has reached +2R by then is kept for the trail


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the candidate rules — fixed in the registration before the fit (S = his words, B = from the 2020 description)
# ═════════════════════════════════════════════════════════════════════════════════════════════
@dataclass(frozen=True)
class XRule:
    """A daily exit rule `cb.Arm` cannot express. No partial. Per session j >= 1, in order: (1) the stop in force (open <= stop at the
    open, else low <= stop at the stop); (2) `gap_x`: a session that OPENS at or under prior close x (1 - gap_x x ADR20) sells all at
    that open; (3) `be_after_r`: once a high reaches fill + be_after_r x R the stop rests at the fill from the next session;
    (4) `up_x` / `ext_x`: a session whose close >= prior close x (1 + up_x x ADR20), or >= SMA10 x (1 + ext_x x ADR20), sells all at
    that close; (5) `below_fill_n`: a close under the fill on a session <= below_fill_n sells all at that close; (6) `time_n`: session
    time_n sells all at its close — unless `time_unless_r` is set and the trade has by then reached fill + time_unless_r x R (the
    day-0 peak after the fill, or any session high through time_n): then it is kept and the trail takes it; (7) `trail_n`: a close
    under the SMA(trail_n) sells all at the NEXT open (cb's trail); (8) the horizon marks. Day 0 is the entry's own minute walk (a
    day-0 stop-out, as every arm)."""
    name: str
    trail_n: Optional[int] = None
    time_n: Optional[int] = None
    up_x: Optional[float] = None
    ext_x: Optional[float] = None
    gap_x: Optional[float] = None
    below_fill_n: Optional[int] = None
    be_after_r: Optional[float] = None
    time_unless_r: Optional[float] = None


def _arm(name: str, **kw) -> "cb.Arm":
    return cb.Arm(name, **kw)


# S rules (his words; the line numbers are docs/methodology/operator_shared_notes.md)
S_RULES = {
    # l.2046-2047 (his 10-18 correction): "sell 1/3 at 2R then move to break even stop then trail rest at break of 10 or 20d ... 10d for
    # faster stocks and 20d for slower stocks" -> the +2R third (day 0 on the minutes), breakeven, the speed trail (10-day when ADR20 at
    # D > 4.79%, else 20-day), first close below, sold at the next open
    "S1_r2_p33_tspd": cb.HIS_EXIT_ARMS["r2_p33_tspd"],
    # l.1946-1947 (the article): "trailed with the 10- or the 20-day moving average... You wait for the first CLOSE below" — the WHOLE
    # position to the first close below the 20-day, no partial (the brief's example)
    "S2_hold_t20": _arm("S2_hold_t20", kind="qm", partial_frac=0.0, partial_session=None, trail_sma=20),
    # l.2070-2079 (the stall cut, confirmed 10-19) on top of l.2061-2062 ("the partial may be a combination of the two (+2R or a number of
    # days)"): 1/3 at +2R or at the session-3 close, whichever first; breakeven; the speed trail; no +1R by the close of session 3 -> all
    # sold at that close
    "S3_c3_p33_tspd_cut3": dc_replace(cb.HIS_EXIT_ARMS["c3_p33_tspd"], name="S3_c3_p33_tspd_cut3",
                                      stall_cut_session=STALL_S, stall_cut_r=STALL_R),
    # l.2126-2132 (his 10-19 ruling): "the day-based third is sold only when the trade is in profit" -> the session-3 third only on a
    # close above the fill, breakeven after it, the speed trail from session 4
    "S4_d3profit_p33_tspd": _arm("S4_d3profit_p33_tspd", kind="qm", partial_frac=1 / 3, partial_session=3, trail_sma=None,
                                 partial_if_profit=True, trail_mode="speed"),
}
# B rules (from the 2020 description; written into the registration BEFORE the fit — see the doc §4; `B_RULES` is filled there)
B_RULES = {
    # B1 time stop (from the 2020 description: 62% of his exit windows end by session 5, median 3; a red close precedes or meets 80% of
    # them; the article's "3-5 days"): the whole position at the close of session 5, the low-of-day stop until then
    "B1_time5": _arm("B1_time5", kind="fixed", target_r=1e9, max_sessions=TIME_N),
    # B2 the time stop that spares a trade already working (his >= 5R exits were held a median 11 sessions and had reached +2R by then):
    # no +2R by the close of session 5 -> all sold at that close; else held to the first close below the 10-day (sold at the next open)
    "B2_time5_unless2R_t10": XRule("B2_time5_unless2R_t10", trail_n=10, time_n=TIME_N, time_unless_r=TIME_UNLESS_R),
}
RULES: dict = {**S_RULES, **B_RULES}
BASELINES = {SPEED_ARM: cb.HIS_EXIT_ARMS[SPEED_ARM], PRIMARY_ARM: cb.ARMS[PRIMARY_ARM]}
ALL_ARMS = {**BASELINES, **{k: v for k, v in RULES.items() if isinstance(v, cb.Arm)}}
X_RULES = {k: v for k, v in RULES.items() if isinstance(v, XRule)}
RULE_TAG = {k: ("S" if k.startswith("S") else "B") for k in RULES}
PANEL = "panel_exit"


class GuardStop(Exception):
    pass


# ═════════════════════════════════════════════════════════════════════════════════════════════
# walk_x — the daily step for the two shapes Arm cannot express (parity-tested on the plain trail)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def walk_x(entry: dict, *, closes_before, fwd: "cb.DailyBars", adr20: float, rule: XRule, horizon: int = HORIZON,
           day0_peak: Optional[float] = None) -> dict:
    """`cb.walk_exit`-shaped result {status, realized_r, pnl_adr, sessions_held, events} for one filled entry under an XRule. A day-0
    stop-out is `cb.day0_result_to_outcome` (as every arm). Sell legs use kinds in `rp.SELL_KINDS` only: `cut` (a sale at the close),
    `stop` / `stop_gap` (the stop, and the gap-down sale at the open), `trail` (the next-open trail), `mark`; a zero-fraction event
    `(j, "x_<reason>", px, 0.0)` names the custom reason beside the leg. Statuses: stopped | time_exit | trailed | censored | degraded."""
    if entry["day0"]["stopped"]:
        return cb.day0_result_to_outcome(entry, adr20)
    fill, stop0 = float(entry["fill"]), float(entry["stop"])
    risk = fill - stop0
    assert risk > 0
    cb_arr = np.asarray(closes_before, dtype=float)
    o, h, l, c = fwd.o, fwd.h, fwd.l, fwd.c
    n = len(c)
    events: list = []

    def out(status, px, j, kind, tag=None):
        if tag:
            events.append((j, f"x_{tag}", float(px), 0.0))
        events.append((j, kind, float(px), 1.0))
        pnl = (float(px) - fill)
        return {"status": status, "realized_r": pnl / risk, "pnl_adr": pnl / (fill * adr20), "sessions_held": int(j), "events": events}

    allc = np.concatenate((cb_arr, c))
    nb = len(cb_arr)                             # allc[nb - 1] = E's close; session j's close = allc[nb - 1 + j]

    def sma(j, k):
        hi = nb + j                              # exclusive
        return float(allc[hi - k:hi].mean()) if hi - k >= 0 else None

    stop_now = stop0
    reached = (rule.time_unless_r is not None and day0_peak is not None and float(day0_peak) >= fill + rule.time_unless_r * risk)
    for j in range(1, min(int(horizon), n) + 1):
        oj, hj, lj, cj = float(o[j - 1]), float(h[j - 1]), float(l[j - 1]), float(c[j - 1])
        prev_c = float(allc[nb - 1 + j - 1])
        if rule.time_unless_r is not None and hj >= fill + rule.time_unless_r * risk:
            reached = True
        stop_j = stop_now
        if oj <= stop_j or lj <= stop_j:
            px = oj if oj <= stop_j else stop_j
            return out("stopped", px, j, "stop_gap" if oj < stop_j else "stop")
        if rule.gap_x is not None and oj <= prev_c * (1.0 - rule.gap_x * adr20):
            return out("time_exit", oj, j, "stop_gap", "gapdown")          # kind stop_gap at the open price -> legs_of books it at the open
        if rule.be_after_r is not None and hj >= fill + rule.be_after_r * risk:
            stop_now = max(stop_now, fill)                                  # rests from the next session
        if rule.up_x is not None and cj >= prev_c * (1.0 + rule.up_x * adr20):
            return out("time_exit", cj, j, "cut", "upday")
        if rule.ext_x is not None:
            s10 = sma(j, 10)
            if s10 is not None and cj >= s10 * (1.0 + rule.ext_x * adr20):
                return out("time_exit", cj, j, "cut", "extension")
        if rule.below_fill_n is not None and j <= rule.below_fill_n and cj < fill:
            return out("time_exit", cj, j, "cut", "belowfill")
        if rule.time_n is not None and j == rule.time_n and not (rule.time_unless_r is not None and reached):
            return out("time_exit", cj, j, "cut", "time")
        if rule.trail_n is not None:
            s = sma(j, rule.trail_n)
            if s is not None and cj < s:
                if j < n:
                    return out("censored" if j == int(horizon) else "trailed", float(o[j]), j + 1, "trail")
                # no next open: fall through to the mark / degraded
        if j == int(horizon):
            return out("censored", cj, j, "mark")
    # fwd ran out before the horizon
    if n > 0:
        return out("degraded", float(c[n - 1]), n, "mark")
    return out("degraded", float(cb_arr[-1]), 0, "mark")


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the walk (the holdings replay's loop with this module's arms)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def walk_entry(ev, bars, cidx, e: int, mb, breaks) -> dict:
    assert bars.dates[e].isoformat() == ev.E, (ev.ticker, e, ev.E)
    assert e >= cb.MIN_HISTORY and int(cidx[e]) - int(cidx[e - cb.MIN_HISTORY]) == cb.MIN_HISTORY, (ev.ticker, ev.E)
    assert ev.setup != "undated"
    en = cb.entry_variants(mb, pivot=ev.pivot, adr20=ev.adr20, day_high=float(bars.h[e]), day_low=float(bars.l[e]))["orh5"]
    closes_before = bars.c[:e + 1]
    fwd, cut = cb.forward_window(bars, cidx, e, HORIZON)
    fwd, brk = rp.cut_at_break(fwd, bars.dates[e], breaks)
    out = {"n_fwd": len(fwd), "hole": bool(cut), "break_cut": brk, "entry": en, "arms": {}, "fwd": fwd, "closes_before": closes_before,
           "day0_peak": None}
    if en["status"] == "filled":
        out["arms"] = cb.walk_his_arms(en, closes_before=closes_before, fwd=fwd, adr20=ev.adr20, minutes=mb, horizon=HORIZON, arms=ALL_ARMS)
        if not en["day0"]["stopped"]:
            out["day0_peak"] = cb.day0_peak_high(mb, en["fill_minute"])
        for name, rule in X_RULES.items():
            out["arms"][name] = walk_x(en, closes_before=closes_before, fwd=fwd, adr20=ev.adr20, rule=rule, day0_peak=out["day0_peak"])
    return out


def walk_all(S: dict, evs: list, say, label: str) -> tuple:
    """The holdings replay's `walk_all`, with this module's `walk_entry` (one minute file read per (tree, date))."""
    res, tally = {}, Counter()
    by_key = defaultdict(list)
    for ev in evs:
        if ev.keep:
            by_key[(ev.era, ev.minutes_tree or ev.era, ev.E)].append(ev)
    cache = {}
    t0 = time.time()
    for n, ((era, tree, d), group) in enumerate(sorted(by_key.items())):
        D = S["Ds"][era]
        path = S["files"][tree].get(d)
        want = {x.ticker for x in group}
        blocks = R.read_minute_file(path, want=want)[0] if (path is not None and want) else {}
        done = {(d, x.ticker): x.minutes_state for x in group}
        for ev in group:
            mb, state = R.minutes_for(blocks, done, d, ev.ticker)
            tally[f"{label}_minutes_{state}"] += 1
            key = (era, ev.ticker)
            if key not in cache:
                cache[key] = R.bars_for(D, D.tid[ev.ticker])
            bars, cidx = cache[key]
            e = R.locate_breakout_index(D.cal, cidx, ev.E)
            w = walk_entry(ev, bars, cidx, e, mb, S["guards"][era].get(ev.ticker))
            w["bars"], w["cidx"], w["e"] = bars, cidx, e
            res[ev.eid] = w
            tally[f"{label}_entry_{w['entry']['status']}_{w['entry'].get('reason') or ''}".rstrip("_")] += 1
        if (n + 1) % 50 == 0:
            print(f"  {label}: {n + 1}/{len(by_key)} (era, tree, date) groups walked ({time.time() - t0:.0f}s)", flush=True)
    return res, tally


def trades_with_events(evs: list, res: dict, arm: str, map_b) -> list:
    out = []
    for ev in evs:
        w = res.get(ev.eid)
        if not w or w["entry"]["status"] != "filled" or arm not in w["arms"]:
            continue
        t = rp.make_trade(ev, w["entry"], w["arms"][arm], w["bars"], w["cidx"], w["e"], w["n_fwd"])
        out.append((ev, H.to_unified(t, map_b)))
    return out


def trades_of(evs, res, arm, map_b):
    return [t for _e, t in trades_with_events(evs, res, arm, map_b)]


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the description — per entry, outcome rows (his window as a RANGE; markers before / within / after)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def rel(first: Optional[int], s_lo: int, s_hi: int) -> str:
    if first is None:
        return "never"
    return "before" if first < s_lo else ("within" if first <= s_hi else "after")


def describe_rows(evs: list, res: dict, S: dict) -> list:
    """One row per walked deciding entry (filled: the ORH5 fill and stop; unfilled: the panel account's close-fill proxy, labelled)."""
    rows = []
    for ev in evs:
        w = res.get(ev.eid)
        if not w:
            continue
        cal = S["Ds"][ev.era].cal
        bars, cidx, e, fwd = w["bars"], w["cidx"], w["e"], w["fwd"]
        e_ci = int(cidx[e])
        en = w["entry"]
        filled = en["status"] == "filled"
        if filled:
            fill, stop = float(en["fill"]), float(en["stop"])
        else:                                       # the panel account's proxy: the buy day's close + slippage, one ADR20 wide
            fill = float(bars.c[e]) * (1.0 + cb.ENTRY_SLIPPAGE_PCT)
            stop = fill * (1.0 - float(ev.adr20))
        risk = fill - stop
        adr = float(ev.adr20)
        # his exit window in sessions from E (clamped at 0: a panel exit "before" the buy day is the buy day itself, as the replay does)
        def sess(d):
            if not d:
                return None
            ci = bisect.bisect_right(cal, date.fromisoformat(d)) - 1
            return max(0, ci - e_ci)
        s_lo, s_hi = sess(S["exit_lo"].get(ev.eid, "")), sess(ev.exit_hi)
        still = ev.still_held or s_hi is None
        n_avail = len(fwd)                           # sessions 1..n_avail have bars
        c_all = np.concatenate(([float(bars.c[e])], np.asarray(fwd.c, dtype=float)))     # index s
        h_all = np.concatenate(([float(bars.h[e])], np.asarray(fwd.h, dtype=float)))
        o_all = np.concatenate(([float(bars.o[e])], np.asarray(fwd.o, dtype=float)))
        closes_through = np.concatenate((np.asarray(w["closes_before"], dtype=float), np.asarray(fwd.c, dtype=float)))
        nb = len(w["closes_before"])                 # closes_through[nb - 1] = E's close

        def sma_at(s, k):
            hi = nb + s
            return float(closes_through[hi - k:hi].mean()) if hi - k >= 0 else None

        def r_close(s):
            if s is None:
                return None
            s2 = min(s, n_avail)
            return (c_all[s2] - fill) / risk

        truncated = (s_hi is not None and s_hi > n_avail)
        r_lo, r_hi = r_close(s_lo), r_close(s_hi)
        r_band = None
        if s_lo is not None and s_hi is not None:
            seg = c_all[min(s_lo, n_avail):min(s_hi, n_avail) + 1]
            r_band = ((seg.min() - fill) / risk, (seg.max() - fill) / risk)
        # markers (first session), all from the bars after E and the day-0 peak after the fill
        first = {}
        for k, lab in ((10, "sma10"), (20, "sma20")):
            f = None
            for s in range(1, n_avail + 1):
                m = sma_at(s, k)
                if m is not None and c_all[s] < m:
                    f = s
                    break
            first[lab] = f
        d0 = w["day0_peak"]
        for kr, lab in ((1.0, "r1"), (2.0, "r2"), (3.0, "r3")):
            f = None
            if filled and d0 is not None and d0 >= fill + kr * risk:
                f = 0
            else:
                for s in range(1, n_avail + 1):
                    if h_all[s] >= fill + kr * risk:
                        f = s
                        break
            first[lab] = f
        f = None
        for s in range(0, n_avail + 1):
            if c_all[s] < float(ev.pivot):
                f = s
                break
        first["below_level"] = f
        first["red_close"] = next((s for s in range(1, n_avail + 1) if c_all[s] < c_all[s - 1]), None)
        first["below_prev_low"] = next((s for s in range(1, n_avail + 1) if c_all[s] < float(np.concatenate(([float(bars.l[e])], np.asarray(fwd.l, dtype=float)))[s - 1])), None)
        first["sma5"] = next((s for s in range(1, n_avail + 1) if sma_at(s, 5) is not None and c_all[s] < sma_at(s, 5)), None)
        f = None
        for s in range(1, n_avail + 1):
            if o_all[s] <= c_all[s - 1] * (1.0 - GAP_X * adr):
                f = s
                break
        first["gapdown"] = f
        f = None
        for s in range(1, n_avail + 1):
            if c_all[s] >= c_all[s - 1] * (1.0 + UP_X * adr):
                f = s
                break
        first["upday"] = f
        f = None
        for s in range(1, n_avail + 1):
            m = sma_at(s, 10)
            if m is not None and c_all[s] >= m * (1.0 + EXT_X * adr):
                f = s
                break
        first["extension"] = f
        stalled = first["r1"] is None or first["r1"] > STALL_S
        # inside-window marker presence (any session of the window, sessions >= 1)
        def in_win(lab):
            if s_lo is None or s_hi is None:
                return None
            a, b = max(1, s_lo), min(s_hi, n_avail)
            if b < a:
                return False
            if lab == "gapdown":
                return any(o_all[s] <= c_all[s - 1] * (1.0 - GAP_X * adr) for s in range(a, b + 1))
            if lab == "upday":
                return any(c_all[s] >= c_all[s - 1] * (1.0 + UP_X * adr) for s in range(a, b + 1))
            if lab == "newhigh":
                return any(h_all[s] >= h_all[:s].max() for s in range(a, b + 1))
            if lab == "extension":
                return any((sma_at(s, 10) is not None) and c_all[s] >= sma_at(s, 10) * (1.0 + EXT_X * adr) for s in range(a, b + 1))
            raise KeyError(lab)
        # ours (the speed trail) and the primary, when filled
        ours = w["arms"].get(SPEED_ARM) if filled else None
        our_s = int(ours["sessions_held"]) if ours else None
        our_first_sell = min((int(s) for s, k, _p, f in ours["events"] if k in rp.SELL_KINDS and f > 0), default=None) if ours else None
        row = dict(eid=ev.eid, ticker=ev.ticker, E=ev.E, year=ev.year, setup=ev.setup, era=ev.era, flicker=ev.flicker, retrigger=ev.retrigger,
                   filled=filled, adr20=adr, fast=(adr > cb.TRAIL_SPEED_ADR_CUT), fill=fill, stop=stop, width=risk / fill,
                   s_lo=s_lo, s_hi=s_hi, still_held=still, truncated=truncated, n_avail=n_avail,
                   r_lo=r_lo, r_hi=r_hi, r_band_min=(r_band[0] if r_band else None), r_band_max=(r_band[1] if r_band else None),
                   max_r_to_hi=((h_all[:min(s_hi, n_avail) + 1].max() - fill) / risk if s_hi is not None else None),
                   stalled=stalled,
                   our_status=(ours["status"] if ours else ""), our_r=(float(ours["realized_r"]) if ours else None), our_s=our_s,
                   our_first_sell=our_first_sell,
                   our_vs_his=("" if (ours is None or s_lo is None) else ("before" if our_s < s_lo else ("inside" if our_s <= s_hi else "after"))),
                   delta_r=((r_hi - float(ours["realized_r"])) if (ours and r_hi is not None) else None))
        for lab in ("sma10", "sma20", "r1", "r2", "r3", "below_level", "gapdown", "upday", "extension", "red_close", "below_prev_low", "sma5"):
            row[f"first_{lab}"] = first[lab]
            row[f"rel_{lab}"] = rel(first[lab], s_lo, s_hi) if s_lo is not None else ""
        for lab in ("gapdown", "upday", "newhigh", "extension"):
            row[f"win_{lab}"] = in_win(lab)
        for name in RULES:
            raw = w["arms"].get(name) if filled else None
            row[f"r_{name}"] = float(raw["realized_r"]) if raw else None
            row[f"s_{name}"] = int(raw["sessions_held"]) if raw else None
        rows.append(row)
    return rows


def bucket(s) -> str:
    if s is None:
        return "still held"
    for a, b, lab in DAY_BUCKETS:
        if a <= s <= b:
            return lab
    return "?"


def q(v, p):
    v = [x for x in v if x is not None and math.isfinite(x)]
    return float(np.percentile(v, p)) if v else float("nan")


def f2(x, nd=2):
    return "-" if x is None or (isinstance(x, float) and not math.isfinite(x)) else f"{x:+.{nd}f}"


def describe_print(say, rows: list, label: str, rule_names: "list | None" = None) -> None:
    rule_names = list(RULES) if rule_names is None else rule_names
    say(f"\n## DESCRIPTION — {label}")
    n = len(rows)
    filled = [r for r in rows if r["filled"]]
    unf = [r for r in rows if not r["filled"]]
    say(f"- entries {n}: ORH5 filled {len(filled)} (the description's main set), unfilled {len(unf)} (beside, on the panel account's close-fill proxy: "
        f"the buy day's close + 0.1%, one ADR20 wide)")
    say("- PARTIALS ARE INVISIBLE: the panel shows presence only, so 'his exit' is the last share's exit and his R is the whole position at it; "
        "the window [exit_lo, exit_hi] is the last stream holding and the first not holding — every R below is a RANGE over it, never a point")
    for grp, sel in (("filled", filled), ("unfilled (close-fill proxy)", unf)):
        if not sel:
            continue
        say(f"\n### {grp}: n = {len(sel)}")
        # days held
        c_hi = Counter(bucket(r["s_hi"]) for r in sel)
        c_lo = Counter(bucket(r["s_lo"]) for r in sel)
        order = [lab_ for _a, _b, lab_ in DAY_BUCKETS] + ["still held"]
        say("- sessions held to his exit window's END (exit_hi): " + ", ".join(f"{k} {c_hi.get(k, 0)}" for k in order if c_hi.get(k))
            + f" | median {q([r['s_hi'] for r in sel], 50):.0f}, p25 {q([r['s_hi'] for r in sel], 25):.0f}, p75 {q([r['s_hi'] for r in sel], 75):.0f}")
        say("- sessions to the window's START (exit_lo): " + ", ".join(f"{k} {c_lo.get(k, 0)}" for k in order if c_lo.get(k))
            + f"; window length 0 sessions {sum(1 for r in sel if r['s_lo'] == r['s_hi'])}, 1: {sum(1 for r in sel if r['s_hi'] is not None and r['s_hi'] - r['s_lo'] == 1)}, "
            f">1: {sum(1 for r in sel if r['s_hi'] is not None and r['s_hi'] - r['s_lo'] > 1)}; truncated by the data {sum(1 for r in sel if r['truncated'])}")
        # R at his exit: a range (a name still held at the last stream has no exit window: left out of these lines, counted above)
        sel_all, sel = sel, [r for r in sel if r["r_lo"] is not None and r["r_hi"] is not None]
        say(f"- R at his exit (RANGE): at the close of exit_lo median {f2(q([r['r_lo'] for r in sel], 50))} [p25 {f2(q([r['r_lo'] for r in sel], 25))}, p75 {f2(q([r['r_lo'] for r in sel], 75))}]; "
            f"at the close of exit_hi median {f2(q([r['r_hi'] for r in sel], 50))} [p25 {f2(q([r['r_hi'] for r in sel], 25))}, p75 {f2(q([r['r_hi'] for r in sel], 75))}]; "
            f"mean {f2(float(np.mean([r['r_lo'] for r in sel])))} .. {f2(float(np.mean([r['r_hi'] for r in sel])))}; sum {f2(sum(r['r_lo'] for r in sel), 1)} .. {f2(sum(r['r_hi'] for r in sel), 1)}")
        say(f"    the band of closes inside the window: min median {f2(q([r['r_band_min'] for r in sel], 50))}, max median {f2(q([r['r_band_max'] for r in sel], 50))}; "
            f"share of windows whose band straddles 0: {100 * np.mean([(r['r_band_min'] is not None and r['r_band_min'] < 0 < r['r_band_max']) for r in sel]):.0f}%")
        say(f"    his exits with R(exit_hi) <= -1 (a stop would have done it): {sum(1 for r in sel if r['r_hi'] is not None and r['r_hi'] <= -1)}; in (-1, 0): "
            f"{sum(1 for r in sel if r['r_hi'] is not None and -1 < r['r_hi'] < 0)}; [0, 2): {sum(1 for r in sel if r['r_hi'] is not None and 0 <= r['r_hi'] < 2)}; "
            f"[2, 5): {sum(1 for r in sel if r['r_hi'] is not None and 2 <= r['r_hi'] < 5)}; >= 5: {sum(1 for r in sel if r['r_hi'] is not None and r['r_hi'] >= 5)}; "
            f">= 10: {sum(1 for r in sel if r['r_hi'] is not None and r['r_hi'] >= 10)}")
        sel = sel_all
        # markers
        say("- markers vs his window (first occurrence: before / within / after / never):")
        for lab, words in (("sma10", "first close below the 10-day"), ("sma20", "first close below the 20-day"), ("sma5", "first close below the 5-day"),
                           ("red_close", "first red close (close below the prior close)"), ("below_prev_low", "first close below the prior session's low"),
                           ("r2", "+2R first reached (high)"),
                           ("r3", "+3R first reached"), ("below_level", "first close below the breakout level"),
                           ("gapdown", f"first gap-down day (open <= prior close - {GAP_X} ADR20)"), ("upday", f"first big up day (close >= prior close + {UP_X} ADR20)"),
                           ("extension", f"first extension (close >= 10-day x (1 + {EXT_X} ADR20))")):
            c = Counter(r[f"rel_{lab}"] for r in sel)
            say(f"    {words:62s}: before {c.get('before', 0):3d} | within {c.get('within', 0):3d} | after {c.get('after', 0):3d} | never {c.get('never', 0):3d}")
        say("- inside his window (any session of it, sessions >= 1): " + ", ".join(
            f"{lab} {sum(1 for r in sel if r[f'win_{lab}'])} of {sum(1 for r in sel if r[f'win_{lab}'] is not None)}"
            for lab in ("gapdown", "upday", "newhigh", "extension")) + f" | windows that are E itself only (no session >= 1): {sum(1 for r in sel if r['s_hi'] == 0)}")
        st = [r for r in sel if r["stalled"]]
        say(f"- the stall (no +1R by the close of session {STALL_S}): {len(st)} of {len(sel)}; of those his exit_hi <= 3: {sum(1 for r in st if r['s_hi'] is not None and r['s_hi'] <= 3)}, "
            f"4-5: {sum(1 for r in st if r['s_hi'] is not None and 4 <= r['s_hi'] <= 5)}, > 5: {sum(1 for r in st if r['s_hi'] is not None and r['s_hi'] > 5)}; "
            f"their R(exit_hi) median {f2(q([r['r_hi'] for r in st], 50))}; the not-stalled: n {len(sel) - len(st)}, exit_hi median {q([r['s_hi'] for r in sel if not r['stalled']], 50):.0f}, R(exit_hi) median {f2(q([r['r_hi'] for r in sel if not r['stalled']], 50))}")
        say(f"- the 3-5 day count: exit_hi in 3-5: {sum(1 for r in sel if r['s_hi'] is not None and 3 <= r['s_hi'] <= 5)}; the window overlaps 3-5: "
            f"{sum(1 for r in sel if r['s_hi'] is not None and r['s_lo'] <= 5 and r['s_hi'] >= 3)}; exit_hi > 5 {sum(1 for r in sel if r['s_hi'] is not None and r['s_hi'] > 5)}; "
            f"of those with exit_hi > 5, R(exit_hi) median {f2(q([r['r_hi'] for r in sel if r['s_hi'] is not None and r['s_hi'] > 5], 50))}, >= 5R {sum(1 for r in sel if r['s_hi'] is not None and r['s_hi'] > 5 and r['r_hi'] is not None and r['r_hi'] >= 5)}")
        say(f"- the fast / slow split (ADR20 at D above {100 * cb.TRAIL_SPEED_ADR_CUT:.2f}% -> the 10-day): fast {sum(1 for r in sel if r['fast'])}, exit_hi median fast "
            f"{q([r['s_hi'] for r in sel if r['fast']], 50):.0f} / slow {q([r['s_hi'] for r in sel if not r['fast']], 50):.0f}")
        if grp == "filled":
            c = Counter(r["our_vs_his"] for r in sel)
            say(f"- OUR deciding exit (the speed trail, last leg) vs his window: before {c.get('before', 0)} | inside {c.get('inside', 0)} | after {c.get('after', 0)}")
            for pos in ("before", "inside", "after"):
                g = [r for r in sel if r["our_vs_his"] == pos]
                if not g:
                    continue
                cs = Counter(r["our_status"] for r in g)
                say(f"    {pos:6s} n {len(g):3d}: ours by status {dict(cs)}; our sessions median {q([r['our_s'] for r in g], 50):.0f}; his exit_hi median {q([r['s_hi'] for r in g], 50):.0f}; "
                    f"our R mean {f2(float(np.mean([r['our_r'] for r in g])))} vs his R(exit_hi) mean {f2(float(np.mean([r['r_hi'] for r in g])))} (R(exit_lo) {f2(float(np.mean([r['r_lo'] for r in g])))})")
            bef = [r for r in sel if r["our_vs_his"] == "before"]
            say(f"    ours out while his book still held it: {len(bef)} — our stop did it {sum(1 for r in bef if r['our_status'] in ('stopped', 'stopped_day0'))} "
                f"(day 0: {sum(1 for r in bef if r['our_status'] == 'stopped_day0')}), our trail {sum(1 for r in bef if r['our_status'] == 'trailed')}; "
                f"our day-3 third before his window: {sum(1 for r in sel if r['our_first_sell'] is not None and r['s_lo'] is not None and r['our_first_sell'] < r['s_lo'])}")
            # the top tail of his R - ours
            d = [r for r in sel if r["delta_r"] is not None]
            d.sort(key=lambda r: -r["delta_r"])
            k = max(1, int(round(TOP_TAIL * len(d))))
            top, rest = d[:k], d[k:]
            say(f"- TOP TAIL: the {k} trades where his exit beats ours most (his R(exit_hi) - our R; sum of the gap {f2(sum(r['delta_r'] for r in top), 1)} of the whole set's {f2(sum(r['delta_r'] for r in d), 1)}):")
            say("    " + "; ".join(f"{r['ticker']} {r['E']} his [{f2(r['r_lo'], 1)}..{f2(r['r_hi'], 1)}]R in {r['s_lo']}-{r['s_hi']}s vs ours {f2(r['our_r'], 1)}R@{r['our_s']}s {r['our_status']}" for r in top))

            def med(g, key):
                return q([r[key] for r in g], 50)
            say(f"    top vs rest — his exit_hi median {med(top, 's_hi'):.0f} vs {med(rest, 's_hi'):.0f}; our exit session {med(top, 'our_s'):.0f} vs {med(rest, 'our_s'):.0f}; "
                f"ours stopped {100 * np.mean([r['our_status'] in ('stopped', 'stopped_day0') for r in top]):.0f}% vs {100 * np.mean([r['our_status'] in ('stopped', 'stopped_day0') for r in rest]):.0f}%; "
                f"ours trailed {100 * np.mean([r['our_status'] == 'trailed' for r in top]):.0f}% vs {100 * np.mean([r['our_status'] == 'trailed' for r in rest]):.0f}%; "
                f"max R reached by exit_hi {f2(med(top, 'max_r_to_hi'))} vs {f2(med(rest, 'max_r_to_hi'))}; ADR20 {100 * med(top, 'adr20'):.1f}% vs {100 * med(rest, 'adr20'):.1f}%; "
                f"fast {100 * np.mean([r['fast'] for r in top]):.0f}% vs {100 * np.mean([r['fast'] for r in rest]):.0f}%; flicker {100 * np.mean([r['flicker'] for r in top]):.0f}% vs {100 * np.mean([r['flicker'] for r in rest]):.0f}%; "
                f"retrigger {100 * np.mean([r['retrigger'] == 1 for r in top]):.0f}% vs {100 * np.mean([r['retrigger'] == 1 for r in rest]):.0f}%; EP {100 * np.mean([r['setup'] == 'EP' for r in top]):.0f}% vs {100 * np.mean([r['setup'] == 'EP' for r in rest]):.0f}%; "
                f"first close below the 10-day AFTER his window {100 * np.mean([r['rel_sma10'] in ('after', 'never') for r in top]):.0f}% vs {100 * np.mean([r['rel_sma10'] in ('after', 'never') for r in rest]):.0f}%; "
                f"stalled {100 * np.mean([r['stalled'] for r in top]):.0f}% vs {100 * np.mean([r['stalled'] for r in rest]):.0f}%")
            say(f"    the bottom tail (ours beats his most, {k}): " + "; ".join(
                f"{r['ticker']} {r['E']} his [{f2(r['r_lo'], 1)}..{f2(r['r_hi'], 1)}]R in {r['s_lo']}-{r['s_hi']}s vs ours {f2(r['our_r'], 1)}R@{r['our_s']}s" for r in d[-k:]))
            # per-rule per-trade R on this set (the fit's per-trade view; the account decides)
            say("- per trade on this set, every rule (filled, all statuses; R at 0 slippage): name | tag | n | mean R | sum R | win | >=5R | median sessions | exits inside his window")
            for name in [SPEED_ARM] + rule_names:
                key_r = "our_r" if name == SPEED_ARM else f"r_{name}"
                key_s = "our_s" if name == SPEED_ARM else f"s_{name}"
                v = [r[key_r] for r in sel if r.get(key_r) is not None]
                ss = [r[key_s] for r in sel if r.get(key_s) is not None]
                inside = sum(1 for r in sel if r.get(key_s) is not None and r["s_lo"] is not None and r["s_lo"] <= r[key_s] <= r["s_hi"])
                say(f"    {name:26s} | {RULE_TAG.get(name, 'base'):4s} | {len(v):3d} | {f2(float(np.mean(v)), 3)} | {f2(sum(v), 1)} | {100 * np.mean([x > 0 for x in v]):.0f}% | "
                    f"{sum(1 for x in v if x >= 5):3d} | {q(ss, 50):.0f} | {inside}")
            hr = [r for r in sel if r["r_hi"] is not None]
            say(f"    {'his panel exit (R at exit_hi)':26s} | his  | {len(hr):3d} | {f2(float(np.mean([r['r_hi'] for r in hr])), 3)} | {f2(sum(r['r_hi'] for r in hr), 1)} | "
                f"{100 * np.mean([r['r_hi'] > 0 for r in hr]):.0f}% | {sum(1 for r in hr if r['r_hi'] >= 5):3d} | {q([r['s_hi'] for r in hr], 50):.0f} | -")


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the accounts (fit and check): every rule, the speed trail, the panel exits — same subset, same start
# ═════════════════════════════════════════════════════════════════════════════════════════════
def accounts(say, S: dict, sel: list, res: dict, window: tuple, label: str, last_asof: str, drop_eids: "set | None" = None) -> dict:
    cal_u, map_b, px = S["cal_u"], S["map_b"], S["px"]
    w0, w1 = (bisect.bisect_left(cal_u, date.fromisoformat(d)) for d in window)
    assert cal_u[w0].isoformat() == window[0] and cal_u[w1].isoformat() == window[1], window
    sel = [e for e in sel if not drop_eids or e.eid not in drop_eids]
    out = {}
    ptr, pc = H.panel_trades_of(sel, res, S, last_asof)
    names = [SPEED_ARM, PRIMARY_ARM] + list(RULES) + [PANEL]
    for name in names:
        tr = ptr if name == PANEL else trades_of(sel, res, name, map_b)
        sim = rp.simulate(tr, CAP30, cal_u, w0)
        st = H.market_stats(H.curve_on_window(sim, w0, w1), px["QQQ"][w0:w1 + 1], px["SPY"][w0:w1 + 1])
        mt = [t for t in tr if t.mature]
        out[name] = dict(sim=sim, st=st, n=len(tr), sum_r=float(sum(t.realized_r for t in mt)), mean_r=float(np.mean([t.realized_r for t in mt])) if mt else float("nan"),
                         ge5=sum(1 for t in mt if t.realized_r >= 5), win=float(np.mean([t.realized_r > 0 for t in mt])) if mt else float("nan"))
    sp, pn = out[SPEED_ARM], out[PANEL]
    gap = math.log(pn["sim"]["final"]) - math.log(sp["sim"]["final"])
    say(f"\n## ACCOUNTS — {label}: buys with E in {window[0]}..{window[1]} (n = {len(sel)}), cap_30 sizing from {window[0]}; the market comparison over the window's "
        f"{w1 - w0 + 1} sessions (open walks marked at its last close); recovery = (ln rule - ln speed) / (ln panel - ln speed) on the final equity")
    say(f"- speed -> panel ln-gap {gap:+.3f} (speed final {sp['sim']['final']:.3f}, panel final {pn['sim']['final']:.3f})")
    hdr = ["rule", "tag", "final", "recovery", "yearly", "max DD", "Sharpe", "alpha t", "total vs QQQ/SPY", "bar", "entered/skipped", "n", "sum R", "mean R", "win", ">=5R"]
    rows = []
    for name in names:
        o = out[name]
        s, st = o["sim"], o["st"]
        rec = (math.log(s["final"]) - math.log(sp["sim"]["final"])) / gap if abs(gap) > 1e-12 else float("nan")
        ok, _f = H.bar_verdict(st)
        rows.append([name, "ours" if name == SPEED_ARM else ("beside" if name == PRIMARY_ARM else ("his" if name == PANEL else RULE_TAG[name])),
                     f"{s['final']:.3f}", f"{rec:+.2f}" if name not in (SPEED_ARM, PANEL) else ("0" if name == SPEED_ARM else "1"),
                     " ".join(f"{y} {rp.pct(r)}" for y, r in sorted(s["yearly"].items())), rp.pct(s["max_dd"]), f"{st['sharpe']:.2f}", f"{st['alpha_t']:.2f}",
                     f"{100 * st['total']:+.0f}% vs {100 * st['qqq']:+.0f}%/{100 * st['spy']:+.0f}%", "met" if ok else "not", f"{s['counts']['entered']}/{s['counts']['skipped_no_room']}",
                     o["n"], f"{o['sum_r']:+.1f}", f"{o['mean_r']:+.3f}", rp.pct(o["win"], 0), o["ge5"]])
        out[name]["recovery"] = rec
    for ln in rp.table(hdr, rows):
        say(ln)
    return out


def choose(out: dict) -> tuple:
    """The registered criterion: the candidate with the highest recovery share, which must exceed the speed trail (recovery > 0);
    ties -> S over B, then fewer parameters (the shorter name). None when no candidate beats the speed trail."""
    cands = [(out[n]["recovery"], 0 if RULE_TAG[n] == "S" else 1, len(n), n) for n in RULES if math.isfinite(out[n]["recovery"])]
    cands.sort(key=lambda x: (-x[0], x[1], x[2]))
    return (cands[0][3], cands[0][0]) if cands and cands[0][0] > 0 else (None, cands[0][0] if cands else float("nan"))


def chosen_from_doc() -> "str | None":
    """The `CHOSEN:` line ABOVE the marker (exactly one), -> the rule name, or "none"."""
    txt = open(DOC).read()
    body = txt.split(FREEZE_MARKER, 1)[0]
    lines = [ln for ln in body.splitlines() if ln.strip().startswith("CHOSEN:")]
    if len(lines) != 1:
        return None
    return lines[0].split("CHOSEN:", 1)[1].strip().split()[0].strip("`*")


# ═════════════════════════════════════════════════════════════════════════════════════════════
# freeze lock
# ═════════════════════════════════════════════════════════════════════════════════════════════
def pins() -> dict:
    p = {"holdings_module": sha(H_PATH), "holdings_tests": sha(H_TESTS), "his_exits_module": sha(os.path.abspath(__file__)),
         "his_exits_tests": sha(os.path.join(HERE, "test_01_his_exits.py")),
         "entries": sha(H.FILES["entries"]), "exits": sha(H.FILES["exits"]), "snapshots": sha(H.FILES["snapshots"]),
         "trades_frozen": sha(TRADES_FROZEN), "describe_2020_printout": sha(P_DESC_2020), "fit_printout": sha(P_FIT),
         "doc_body": rp.doc_body_sha(DOC)}
    return p


def marker_ok(txt: str) -> bool:
    """The marker is its own line, exactly once, and the literal appears nowhere else (prose says 'the freeze marker')."""
    return txt.count(FREEZE_MARKER) == 1 and sum(1 for ln in txt.splitlines() if ln == FREEZE_MARKER) == 1


def freeze_missing(p: dict) -> list:
    txt = open(DOC).read()
    if not marker_ok(txt):
        return ["(the doc has no single marker line)"] + list(p)
    tail = txt.split(FREEZE_MARKER, 1)[1]
    return [k for k, v in p.items() if v not in tail]


def check_pinned_inputs(say) -> None:
    """The holdings replay's own pins (exports, candidates, labels, guards, the frozen modules) must still hold."""
    paths = {**H.FILES, **H.CODE}
    drift = []
    for k, v in H.PINNED.items():
        if k in paths and os.path.exists(paths[k]) and sha(paths[k]) != v:
            drift.append(k)
    if sha(H_PATH) != H_SHA or sha(H_TESTS) != H_TESTS_SHA:
        drift.append("holdings_module/tests")
    if drift:
        raise GuardStop("a pinned input changed: " + ", ".join(drift))
    say("- the holdings replay's pins re-checked (exports, candidates, labels, guards, the frozen modules; the holdings module and tests = its freeze record): no drift")


# ═════════════════════════════════════════════════════════════════════════════════════════════
# stages
# ═════════════════════════════════════════════════════════════════════════════════════════════
class Quiet:
    def __init__(self):
        self.lines = []

    def __call__(self, msg: str = "") -> None:
        self.lines.append(msg)


def load(say) -> dict:
    t0 = time.time()
    qs = Quiet()
    S = H.load_all(qs)
    snaps = pd.read_csv(H.FILES["snapshots"], sep="\t", dtype=str, keep_default_na=False)
    S["last_asof"] = max(snaps["asof"])
    ent = pd.read_csv(H.FILES["entries"], sep="\t", dtype=str, keep_default_na=False)
    S["exit_lo"] = {int(r["eid"]): r["exit_lo"] for r in ent.to_dict("records")}      # HEvent carries exit_hi only; the window's start comes from the timeline
    win = [e for e in S["evs"] if e.in_window]
    say(f"- loaded in {time.time() - t0:.0f}s: entries {len(S['evs'])}, deciding account {len(win)} (the registration's 262, asserted by the holdings loader), "
        f"walkable {sum(1 for e in win if e.keep)}; last stream asof {S['last_asof']}")
    return S


def select(S: dict, window: tuple) -> list:
    return [e for e in S["evs"] if e.in_window and window[0] <= e.E <= window[1]]


def parity_against_frozen(say, sel: list, res: dict, max_E: str) -> None:
    """Our re-walk of the speed trail must equal the holdings replay's per entry (realized R, sessions). Only rows with E <= max_E are
    taken from the frozen file (the later years' outcomes stay unread before the check)."""
    t = pd.read_csv(TRADES_FROZEN, sep="\t", dtype=str, keep_default_na=False)
    t = t[(t["arm"] == SPEED_ARM) & (t["E"] <= max_E)]
    fr = {int(r["eid"]): (float(r["realized_r"]), int(r["sessions_held"])) for r in t.to_dict("records")}
    n, bad = 0, []
    for ev in sel:
        w = res.get(ev.eid)
        if not w or w["entry"]["status"] != "filled":
            continue
        raw = w["arms"][SPEED_ARM]
        n += 1
        if ev.eid not in fr:
            bad.append(f"{ev.ticker} {ev.E} not in the frozen file")
        elif abs(fr[ev.eid][0] - float(raw["realized_r"])) > 1e-9 or fr[ev.eid][1] != int(raw["sessions_held"]):
            bad.append(f"{ev.ticker} {ev.E}: {fr[ev.eid]} vs ({raw['realized_r']}, {raw['sessions_held']})")
    if bad:
        raise GuardStop(f"PARITY with the frozen replay failed on {len(bad)} of {n}: " + "; ".join(bad[:5]))
    say(f"- parity with the frozen holdings replay (speed trail, E <= {max_E}): {n} filled entries equal in realized R (1e-9) and sessions held")


def parity_x_vs_arm(say, sel: list, res: dict) -> None:
    """walk_x configured as the plain 20-day trail equals cb.walk_exit's Arm on every filled entry (1e-9)."""
    plain = XRule("x_t20", trail_n=20)
    n = 0
    for ev in sel:
        w = res.get(ev.eid)
        if not w or w["entry"]["status"] != "filled":
            continue
        a = w["arms"]["S2_hold_t20"]
        b = walk_x(w["entry"], closes_before=w["closes_before"], fwd=w["fwd"], adr20=ev.adr20, rule=plain)
        if abs(float(a["realized_r"]) - float(b["realized_r"])) > 1e-9 or int(a["sessions_held"]) != int(b["sessions_held"]) or a["status"] != b["status"]:
            raise GuardStop(f"walk_x parity failed on {ev.ticker} {ev.E}: arm {a['status']} {a['realized_r']} @{a['sessions_held']} vs x {b['status']} {b['realized_r']} @{b['sessions_held']}")
        n += 1
    say(f"- walk_x parity with cb.walk_exit on the plain 20-day trail: {n} filled entries equal (status, realized R to 1e-9, sessions)")


def write_rows(rows: list, name: str) -> str:
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, name)
    pd.DataFrame(rows).to_csv(path, sep="\t", index=False)
    return path


def write_trades(sel: list, res: dict, S: dict, name: str) -> str:
    rows = []
    for ev in sel:
        w = res.get(ev.eid)
        if not w:
            continue
        en = w["entry"]
        base = dict(eid=ev.eid, era=ev.era, ticker=ev.ticker, E=ev.E, setup=ev.setup, flicker=ev.flicker, retrigger=ev.retrigger, entry_status=en["status"],
                    entry_reason=en.get("reason") or "", fill=en.get("fill"), stop=en.get("stop"), fill_minute=en.get("fill_minute"), n_fwd=w["n_fwd"],
                    exit_lo=S["exit_lo"].get(ev.eid, ""), exit_hi=ev.exit_hi)
        for arm, raw in w["arms"].items():
            rows.append({**base, "arm": arm, "status": raw["status"], "realized_r": raw["realized_r"], "sessions_held": raw["sessions_held"],
                         "legs": ";".join(f"{s}:{k}:{px:.4f}:{f:.4f}" for s, k, px, f in raw["events"] if k in rp.SELL_KINDS or str(k).startswith("x_"))})
        if not w["arms"]:
            rows.append({**base, "arm": "", "status": "", "realized_r": "", "sessions_held": "", "legs": ""})
    return write_rows(rows, name)


def stage_describe_2020(say) -> int:
    if os.path.exists(P_DESC_2020):
        print(f"REFUSED: {P_DESC_2020} exists (the description of 2020 is written once; delete it by hand to redo)", file=sys.stderr)
        return 2
    say("# #705 HIS EXITS 01 — DESCRIBE 2020 (the fit years' deciding buys; the 2021-22 outcomes are not computed here)")
    say(f"# registration: {os.path.relpath(DOC, REPO)}")
    check_pinned_inputs(say)
    S = load(say)
    sel = select(S, FIT_WINDOW)
    by_year = Counter(e.year for e in sel)
    say(f"- selected: E in {FIT_WINDOW[0]}..{FIT_WINDOW[1]}: n = {len(sel)}; walked by year " + ", ".join(f"{y} {c}" for y, c in sorted(by_year.items()))
        + f" (2021: {sum(1 for e in S['evs'] if e.in_window and e.year == 2021)} and 2022: {sum(1 for e in S['evs'] if e.in_window and e.year == 2022)} deciding buys exist and are NOT walked)")
    assert all(e.year == 2020 for e in sel)
    res, tally = walk_all(S, sel, say, "fit")
    say("- the walk: " + ", ".join(f"{k} {v}" for k, v in sorted(tally.items())))
    parity_against_frozen(say, sel, res, FIT_WINDOW[1])
    parity_x_vs_arm(say, sel, res)
    rows = describe_rows(sel, res, S)
    p = write_rows(rows, "describe_rows_2020.tsv")
    # the per-rule table here shows the S rules only: the B rules are written from this description, after it
    describe_print(say, rows, f"2020 deciding buys (E in {FIT_WINDOW[0]}..{FIT_WINDOW[1]})", rule_names=list(S_RULES))
    say(f"\n## Outputs: {p}")
    return 0


def stage_fit(say) -> int:
    if os.path.exists(P_FIT):
        print(f"REFUSED: {P_FIT} exists (the fit runs once)", file=sys.stderr)
        return 2
    if not os.path.exists(P_DESC_2020):
        print("REFUSED: run --describe-2020 first (the B rules are written from it into the registration before the fit)", file=sys.stderr)
        return 2
    say("# #705 HIS EXITS 01 — FIT on the 2020 buys (the registered rules; the 2021-22 outcomes are not computed here)")
    say(f"# registration: {os.path.relpath(DOC, REPO)}")
    say("- rules: " + "; ".join(f"{k} [{RULE_TAG[k]}]" for k in RULES) + f"; baselines {SPEED_ARM} (ours, the holdings DECIDING), {PRIMARY_ARM} (beside); his panel exits")
    say(f"- markers (ADR20 units): gap-down {GAP_X}, big up day {UP_X}, extension {EXT_X}; stall session {STALL_S} / +{STALL_R}R; the choice = highest recovery > 0, ties S over B then the shorter name")
    check_pinned_inputs(say)
    S = load(say)
    sel = select(S, FIT_WINDOW)
    assert all(e.year == 2020 for e in sel)
    res, tally = walk_all(S, sel, say, "fit")
    say("- the walk: " + ", ".join(f"{k} {v}" for k, v in sorted(tally.items())))
    parity_against_frozen(say, sel, res, FIT_WINDOW[1])
    parity_x_vs_arm(say, sel, res)
    out = accounts(say, S, sel, res, FIT_WINDOW, "FIT 2020", S["last_asof"])
    name, rec = choose(out)
    say(f"\n## THE CHOICE (the registered criterion): {name or 'none'}" + (f" — recovery {rec:+.2f} on 2020" if name else f" — no candidate beats the speed trail (best recovery {rec:+.2f})"))
    say("- the main loop writes `CHOSEN: <name>` (or `CHOSEN: none`) ABOVE the doc's freeze marker line, then --pins, then pastes them under it, then --check")
    # beside: without the top-3 panel-R entries; by setup
    ptr, _c = H.panel_trades_of(sel, res, S, S["last_asof"])
    top3 = {t.key for t in sorted(ptr, key=lambda t: -t.realized_r)[:DROP_TOP]}
    drop = {e.eid for e in sel if (e.era, e.ticker, e.E) in top3}
    say(f"\n## BESIDE — without the {DROP_TOP} entries with the highest panel R: " + ", ".join(f"{k[1]} {k[2]}" for k in sorted(top3, key=lambda k: k[2])))
    accounts(say, S, sel, res, FIT_WINDOW, f"FIT 2020 without the top {DROP_TOP}", S["last_asof"], drop_eids=drop)
    bk = [e for e in sel if e.setup in ("breakout", "both")]
    say(f"\n## BESIDE — breakout-dated only (n = {len(bk)})")
    accounts(say, S, bk, res, FIT_WINDOW, "FIT 2020 breakout-dated", S["last_asof"])
    p = write_trades(sel, res, S, "trades_fit_2020.tsv")
    say(f"\n## Outputs: {p}")
    return 0


def stage_pins(say) -> int:
    for pth in (P_DESC_2020, P_FIT):
        if not os.path.exists(pth):
            print(f"REFUSED: {pth} missing — the pins are taken after the description and the fit", file=sys.stderr)
            return 2
    ch = chosen_from_doc()
    say(f"- CHOSEN line above the marker: {ch if ch else 'MISSING (write exactly one `CHOSEN: <rule>` line above the marker first)'}")
    p = pins()
    say("## Pins (sha256) — paste every line under the doc's freeze marker line, then run --check")
    for k, v in p.items():
        say(f"- {k}: {v}")
    miss = freeze_missing(p)
    say(f"- freeze record: {'complete' if not miss else 'NOT YET under the marker: ' + ', '.join(miss)}")
    return 0


def stage_check(say) -> int:
    if os.path.exists(P_CHECK) or os.path.exists(STOPPED):
        print(f"REFUSED: {P_CHECK} or a STOPPED file exists (the check runs once)", file=sys.stderr)
        return 2
    for pth in (P_DESC_2020, P_FIT):
        if not os.path.exists(pth):
            print(f"REFUSED: {pth} missing", file=sys.stderr)
            return 2
    ch = chosen_from_doc()
    if ch is None:
        print("REFUSED: no single `CHOSEN:` line above the marker", file=sys.stderr)
        return 2
    if ch != "none" and ch not in RULES:
        print(f"REFUSED: CHOSEN names {ch!r}, not a registered rule", file=sys.stderr)
        return 2
    p = pins()
    miss = freeze_missing(p)
    if miss:
        print("REFUSED: pins not under the marker: " + ", ".join(miss), file=sys.stderr)
        return 2
    say("# #705 HIS EXITS 01 — CHECK on the 2021-22 buys (ONE run; the chosen rule decides, every other rule beside)")
    say(f"# registration: {os.path.relpath(DOC, REPO)}")
    say(f"- freeze: every pin incl. doc_body {p['doc_body'][:12]}… sits under the marker line; CHOSEN: {ch}")
    try:
        check_pinned_inputs(say)
        S = load(say)
        sel = select(S, CHECK_WINDOW)
        say(f"- selected: E in {CHECK_WINDOW[0]}..{CHECK_WINDOW[1]}: n = {len(sel)}; by year " + ", ".join(f"{y} {c}" for y, c in sorted(Counter(e.year for e in sel).items())))
        assert all(e.year in (2021, 2022) for e in sel)
        res, tally = walk_all(S, sel, say, "check")
        say("- the walk: " + ", ".join(f"{k} {v}" for k, v in sorted(tally.items())))
        parity_against_frozen(say, sel, res, CHECK_WINDOW[1])
        parity_x_vs_arm(say, sel, res)
        out = accounts(say, S, sel, res, CHECK_WINDOW, "CHECK 2021-22", S["last_asof"])
        say("\n## THE CHECK READOUT")
        if ch == "none":
            say("- CHOSEN: none on 2020 — the check is DESCRIPTIVE: no rule decides; the table above is read as is")
        else:
            o, sp = out[ch], out[SPEED_ARM]
            beats = o["sim"]["final"] > sp["sim"]["final"]
            ok = beats and o["recovery"] >= RECOVERY_BAR
            say(f"- CHOSEN {ch} [{RULE_TAG[ch]}]: final {o['sim']['final']:.3f} vs the speed trail {sp['sim']['final']:.3f} vs his panel exits {out[PANEL]['sim']['final']:.3f}; "
                f"recovery {o['recovery']:+.2f} (bar >= {RECOVERY_BAR:.2f} and beats the speed trail) -> **{'PASS' if ok else 'FAIL'}**")
            say(f"    market: {H.fmt_stats(o['st'])} -> his bar {'met' if H.bar_verdict(o['st'])[0] else 'not met'} (beside; the window is 2021-22, not the registered one)")
            say(f"    speed: {H.fmt_stats(sp['st'])}; panel: {H.fmt_stats(out[PANEL]['st'])}")
            say(f"    per trade: chosen mean R {o['mean_r']:+.3f} (sum {o['sum_r']:+.1f}) vs speed {sp['mean_r']:+.3f} ({sp['sum_r']:+.1f}) vs panel {out[PANEL]['mean_r']:+.3f} ({out[PANEL]['sum_r']:+.1f})")
        best = max((n for n in RULES), key=lambda n: out[n]["recovery"] if math.isfinite(out[n]["recovery"]) else -1e9)
        say(f"- beside: the best rule on 2021-22 by recovery is {best} ({out[best]['recovery']:+.2f}) — a post-hoc reading, it decides nothing")
        ptr, _c = H.panel_trades_of(sel, res, S, S["last_asof"])
        top3 = {t.key for t in sorted(ptr, key=lambda t: -t.realized_r)[:DROP_TOP]}
        drop = {e.eid for e in sel if (e.era, e.ticker, e.E) in top3}
        say(f"\n## BESIDE — without the {DROP_TOP} entries with the highest panel R: " + ", ".join(f"{k[1]} {k[2]}" for k in sorted(top3, key=lambda k: k[2])))
        accounts(say, S, sel, res, CHECK_WINDOW, f"CHECK without the top {DROP_TOP}", S["last_asof"], drop_eids=drop)
        bk = [e for e in sel if e.setup in ("breakout", "both")]
        say(f"\n## BESIDE — breakout-dated only (n = {len(bk)})")
        accounts(say, S, bk, res, CHECK_WINDOW, "CHECK breakout-dated", S["last_asof"])
        for y, win in ((2021, ("2021-01-04", "2021-12-31")), (2022, ("2022-01-03", "2022-06-14"))):
            yy = [e for e in sel if e.year == y]
            if len(yy) >= 5:
                say(f"\n## BESIDE — {y} alone (n = {len(yy)})")
                accounts(say, S, yy, res, win, f"CHECK {y}", S["last_asof"])
        rows = describe_rows(sel, res, S)
        write_rows(rows, "describe_rows_2021_22.tsv")
        describe_print(say, rows, f"2021-22 deciding buys (E in {CHECK_WINDOW[0]}..{CHECK_WINDOW[1]}) — read for the first time here")
        p2 = write_trades(sel, res, S, "trades_check_2021_22.tsv")
        say(f"\n## Outputs: {p2}, describe_rows_2021_22.tsv")
    except GuardStop as g:
        say(f"STOPPED: {g}")
        say.write(STOPPED)
        return 3
    except Exception:
        import traceback
        say("STOPPED (crash):\n" + traceback.format_exc())
        say.write(STOPPED)
        return 4
    return 0


def stage_describe_all(say) -> int:
    """After the check: the description of ALL deciding buys in the window (262) and, beside, the deciding buys of the other years and the
    dated-but-wider-than-the-cap entries. Needs the check printout (so the order of reading is kept)."""
    if not os.path.exists(P_CHECK):
        print("REFUSED: run --check first", file=sys.stderr)
        return 2
    say("# #705 HIS EXITS 01 — DESCRIBE ALL (after the check): the 262 deciding buys, then the beside sets")
    check_pinned_inputs(say)
    S = load(say)
    win = [e for e in S["evs"] if e.in_window]
    res, tally = walk_all(S, win, say, "all")
    say("- the walk: " + ", ".join(f"{k} {v}" for k, v in sorted(tally.items())))
    parity_against_frozen(say, win, res, "2022-06-14")
    rows = describe_rows(win, res, S)
    write_rows(rows, "describe_rows_all_262.tsv")
    describe_print(say, rows, "ALL 262 deciding buys (2020-01-27..2022-06-14)")
    for y in (2020, 2021, 2022):
        describe_print(say, [r for r in rows if r["year"] == y], f"{y} alone")
    beside = [e for e in S["evs"] if e.setup in H.SETUPS and not e.in_window and not e.same_day_rebuy and e.keep]
    res2, _t = walk_all(S, beside, say, "beside")
    rows2 = describe_rows(beside, res2, S)
    write_rows(rows2, "describe_rows_beside_dated.tsv")
    describe_print(say, rows2, f"BESIDE — dated buys outside the account (other years' deciding + wider-than-cap windows; n = {len(rows2)})")
    return 0


def main(argv=None) -> int:
    ap_ = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap_.add_mutually_exclusive_group(required=True)
    g.add_argument("--describe-2020", action="store_true")
    g.add_argument("--fit", action="store_true")
    g.add_argument("--pins", action="store_true")
    g.add_argument("--check", action="store_true")
    g.add_argument("--describe-all", action="store_true")
    args = ap_.parse_args(argv)
    say = rp.Say()
    try:
        if args.describe_2020:
            rc = stage_describe_2020(say)
            if rc == 0:
                say.write(P_DESC_2020)
            return rc
        if args.fit:
            rc = stage_fit(say)
            if rc == 0:
                say.write(P_FIT)
            return rc
        if args.pins:
            return stage_pins(say)
        if args.check:
            rc = stage_check(say)
            if rc == 0:
                say.write(P_CHECK)
            return rc
        if args.describe_all:
            rc = stage_describe_all(say)
            if rc == 0:
                say.write(P_DESC_ALL)
            return rc
    except GuardStop as g:
        print(f"STOPPED: {g}", file=sys.stderr)
        return 3
    return 1


if __name__ == "__main__":
    sys.exit(main())
