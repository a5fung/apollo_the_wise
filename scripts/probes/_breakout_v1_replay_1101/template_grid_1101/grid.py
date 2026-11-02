#!/usr/bin/env python3
"""Breakout v1 — the TEMPLATE GRID on the frozen 2017-2024 paper replay (registration
docs/analysis/breakout_v1_template_grid_prereg_2026-11-01.md, written before any outcome).

Four steps, one variable each, the pick made on 2017-21 ONLY and judged ONCE on 2022-24, each step carrying the previous
step's 2017-21 pick:
  1. EXITS on today's list and entry: A = today's pp exit (the live code, `v1_replay.exit_one`); B = no partial, the 20-day
     trail with a quick reclaim forgiven (the 10-22 grid's cell A20_X3_P0); C = the speed trail, no partial (10-day when
     ADR20 at D > cb.TRAIL_SPEED_ADR_CUT, else 20-day; first close below -> the next open; the round-3 cut); D = a third
     sold at the first close of session 3, 4 or 5 above the fill, then the stop at the fill and the 20-day close-below trail.
  2. the 15-cent MINIMUM STOP (the follow-up's floor; re-confirmed on top of step 1's pick, never re-selected).
  3. SELECTION: the strength gate at 98 (live) vs 95 vs 90 — the list rebuilt by `v1_replay.run_population` with
     `breakout_v1.RS_MIN` set from here (never edited), the new names walked through the SAME entry code; both directions
     counted (real big breakouts gained, losing trades added).
  4. SLOTS: 5 (live) vs 8 vs 10 — information for him; the 30-of-31 refused big winners reported under each.

`v1_replay` (V) is IMPORTED and never copy-edited: its books (`apply_book`), stats, bootstrap, minute readers, stores,
entry simulation, the pp stepper and the pin helpers are called. Exits B, C, D are re-implemented HERE (the live code has
only A), pinned to their source definitions and hand-tested in `dryrun`. Offline research; $0; nothing live changes; no
date >= 2025-01-01 is read (V.assert_sealed on every E and forward bar); the walk refuses on a changed pin, on an
incomplete minute pull, or when its outputs exist. Any rule change is the operator's call (THE LINE).

Stages: parity | population | request | coverage | dryrun | pins | walk
Scratch: $TGRID_SCRATCH (default scratchpad/Tgrid/<phase>/).
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import os
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Optional

import numpy as np

HERE = Path(__file__).resolve().parent
PROBE = HERE.parent                                   # scripts/probes/_breakout_v1_replay_1101
REPO = HERE.parents[3]                                # the repo root (template_grid_1101 -> _breakout_v1_replay_1101 -> probes -> scripts -> repo)
assert (REPO / "agents" / "market_intelligence").is_dir(), REPO
TG_SCRATCH = Path(os.environ.get("TGRID_SCRATCH", "/private/tmp/claude-501/-Users-alvinfung-apollo-the-wise/"
                                 "d30e3944-e07e-4b44-97de-010acba78d0b/scratchpad/Tgrid"))
os.environ.setdefault("BV1_SCRATCH", str(TG_SCRATCH / "pop"))   # V's sealed daily copy lands in THIS task's scratch
if str(PROBE) not in sys.path:
    sys.path.insert(0, str(PROBE))
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
import v1_replay as V  # noqa: E402  (the frozen replay module, imported; read-only)

cb, ppr, bv, runner = V.cb, V.ppr, V.bv, V.runner

# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 0. Paths, constants, the bar
# ═══════════════════════════════════════════════════════════════════════════════════════════════
DOC = REPO / "docs" / "analysis" / "breakout_v1_template_grid_prereg_2026-11-01.md"
BASE_DOC = V.DOC                                      # the frozen paper-baseline registration (its pins must still hold)
TRADES = V.OUT / "trades.tsv.gz"                      # the frozen outcomes (every list name-day, the A exit)
TICK = PROBE / "followup_tests_1101" / "tick_facts.tsv.gz"   # width at placement (level - day-low stop) in raw cents
WINNERS = PROBE / "big_winners_1101" / "big_winners_2017_2024.tsv"
TRAIL_LIB = REPO / "scripts" / "probes" / "_702_trail_variants_1023" / "trail_lib.py"   # B's source definition (X3 / P0)
CB_MODULE = REPO / "agents" / "market_intelligence" / "consolidation_breakout.py"        # C's cut (TRAIL_SPEED_ADR_CUT)
LIST90 = HERE / "list90"                              # the list at rs >= 90 (98 and 95 are subsets)
REQUEST = HERE / "minute_request.tsv"
RAW_REQUEST = HERE / "raw_close_request.tsv"
OUT = HERE / "out"
TG_MINUTE_DIR = V.CB / "minutes_tgrid_1101"           # where the main loop's pull for the new names lands
TG_RAW_PULL = V.CB / "raw_close_tgrid_1101.csv.gz"    # the raw closes of the new raw_src=2 tickers (optional; see request)
TG_RAW_META = V.CB / "raw_close_tgrid_1101.meta.json"
RS_LEVELS = (98.0, 95.0, 90.0)
SLOT_COUNTS = (5, 8, 10)
EXITS = ("A", "B", "C", "D")
EXIT_WORDS = {"A": "A today's exit: a third at +2R or at the session-3 close, stop to cost, 20-day close-below trail, stall cut",
              "B": "B no partial: 20-day trail, a quick reclaim forgiven (two sessions), stall cut",
              "C": "C no partial: the speed trail (10-day when ADR20 at D > 4.79%, else 20-day), first close below, stall cut",
              "D": "D a third at the first close of session 3-5 above the fill, stop to cost, 20-day close-below trail, stall cut"}
FLOOR_CENTS = 15.0                                    # step 2: the planned risk at placement under 15 raw cents -> never placed
ERA_A, ERA_B = "2017-21", "2022-24"
PRIMARY_COST = V.PRIMARY_COST                         # 2 cents a share each way (the primary row's cost)
PICK_TIE = 0.02                                       # means within 0.02R are a tie -> the higher 10R+ per 100 wins
X3_GRACE = 2                                          # B: a reclaim at sj+1 or sj+2 cancels the watch; else sold at the open of sj+3
D_THIRD_SESSIONS = (3, 4, 5)                          # D: the first close of session 3, 4 or 5 above the fill sells a third
# the bar (registration §5): TEMPLATE / FAIL / CAN'T TELL on the primary row (capped book, 2c, decisive trades)
N_FLOOR = V.N_FLOOR                                   # 100
TAIL_PER100 = 2.0                                     # >= 2 trades per 100 at >= 10R (his 2.9)
FAIL_MEAN_REF = V.FAIL_MEAN_REF                       # the whole interval under +0.25R
BENCH = {"name": "his 205 holdings trades under our rules (cb_holdings_replay_prereg_2026-10-24.md §RESULT)",
         "n": 205, "mean_r": 1.06, "win_rate": 0.37, "median_r": -1.0, "ge10_per100": 2.9}
TEMPLATE = "TEMPLATE"
CANT = "CAN'T TELL"


def sha(p: Path) -> str:
    return V.sha(p)


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 1. The frozen rows
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def _none(x):
    if x is None:
        return None
    if isinstance(x, float) and math.isnan(x):
        return None
    if isinstance(x, str) and x.strip() == "":
        return None
    return x


def _bool(x) -> bool:
    return str(x) == "True"


def _f(x) -> Optional[float]:
    x = _none(x)
    return None if x is None else float(x)


def _i(x) -> Optional[int]:
    x = _none(x)
    return None if x is None else int(float(x))


def load_frozen() -> list:
    """Every frozen row as a dict (the entry side is reused as it is; the exit side is re-walked per rule)."""
    import pandas as pd
    df = pd.read_csv(TRADES, sep="\t", low_memory=False)
    rows = []
    for r in df.to_dict("records"):
        rows.append({
            "key": r["key"], "E": r["E"], "D": r["D"], "ticker": r["ticker"], "list_rank": int(r["list_rank"]),
            "era_store": r["era_store"], "fwd_store": _none(r["fwd_store"]), "era": r["era"], "month": r["month"], "year": int(r["year"]),
            "placed_m": _i(r["placed_m"]), "cancel_m": _i(r["cancel_m"]), "filled": _bool(r["filled"]),
            "fill": _f(r["fill"]), "stop": _f(r["stop"]), "fill_minute": _i(r["fill_minute"]), "placed_stop": _f(r["placed_stop"]),
            "adr20": _f(r["adr20"]), "rs_best": _f(r["rs_best"]), "raw_factor": float(r["raw_factor"]), "raw_src": int(r["raw_src"]),
            "level": _f(r["level"]), "list_level": _f(r["list_level"]), "vol_bar": _f(r["vol_bar"]), "orh5": _f(r["orh5"]),
            "outcome": _none(r["outcome"]), "status": _none(r["status"]), "after_cutoff": _bool(r["after_cutoff"]),
            "decisive": _bool(r["decisive"]), "mature": _bool(r.get("mature")), "free_date": _none(r["free_date"]),
            "free_minute": _i(r["free_minute"]), "exit_at_open": _bool(r["exit_at_open"]),
            "events": (json.loads(r["events"]) if isinstance(r["events"], str) else None),
            "legs": (json.loads(r["legs"]) if isinstance(r["legs"], str) else []),
            "f_risk": _f(r["f_risk"]) or 0.0, "total_r": _f(r["total_r"]) or 0.0, "r_2c": _f(r["r_2c"]),
            "adm_cap": _none(r["adm_cap"]), "adm_guard": _none(r["adm_guard"]), "why_cap": _none(r["why_cap"]),
            "day0_third": _f(r["day0_third"]), "day0_stopped": (None if _none(r["day0_stopped"]) is None else _bool(r["day0_stopped"])),
            "day0_peak": _f(r["day0_peak"]), "stop_check": _none(r["stop_check"]), "qqq_phase": _none(r.get("qqq_phase")),
        })
    return rows


def load_tick() -> dict:
    import pandas as pd
    df = pd.read_csv(TICK, sep="\t")
    return {r["key"]: r for r in df.to_dict("records")}


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 2. The minute index (the baseline's stores + the pull for the new names) and the forward bars
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def minute_index() -> list:
    index = V.minute_index()
    d = TG_MINUTE_DIR
    if d.is_dir():
        done = runner.load_done_pairs(d) or {}
        seal = V.SEAL.isoformat()
        done = {k: v for k, v in done.items() if k[0] < seal}
        files = runner.minute_date_files(d)
        files = {k: v for k, v in files.items() if date.fromisoformat(k) < V.SEAL}
        index.append((d, done, files))
    return index


def minute_blocks(index: list, e: str, tickers: list) -> dict:
    """{ticker: (MinuteBars | None, state)} for one breakout day, read exactly as the walk reads them."""
    src: dict = {}
    for t in tickers:
        src.setdefault(V.held_in(index, e, t), []).append(t)
    blocks = {}
    for d, want in src.items():
        if d is None:
            continue
        files = next(f for dd, _, f in index if dd == d)
        done = next(dn for dd, dn, _ in index if dd == d)
        b, _info = runner.read_minute_file(files[e], set(want))
        for t in want:
            blocks[t] = runner.minutes_for(b, done, e, t)
    return blocks


class Stores:
    def __init__(self):
        self._s: dict = {}

    def get(self, era: str) -> V.Store:
        if era not in self._s:
            S = V.load_store(era)
            S.cal_pos = {dd: i for i, dd in enumerate(S.D.cal)}
            self._s[era] = S
        return self._s[era]


def forward_inputs(stores: Stores, row: dict) -> tuple:
    """(bars, cidx, e_i, fwd_store) via V.walk_inputs — the SAME store choice the baseline made (the Q1-2022 seam)."""
    ed = date.fromisoformat(row["E"])
    lr = {"ticker": row["ticker"], "era_store": row["era_store"]}
    bars, cidx, e_i, chosen = V.walk_inputs(stores._s, stores.get, lr, ed)
    return bars, cidx, e_i, chosen


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 3. The exits — A called, B / C / D re-implemented (pinned to their sources; hand-tested in `dryrun`)
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def sma_n_at(closes_before, fwd_closes: list, n: int) -> Optional[float]:
    """The n-day simple average of the closes ending at the last forward close, computed as `ppr.sma_at_last` computes
    the 20-day (the last n closes before the entry incl. E's, then the forward closes; prefix sums; / n) so that for
    n = 20 the comparison is bit-for-bit the live trail's. None with fewer than n closes."""
    tail = [float(x) for x in list(closes_before)[-n:]]
    seq = tail + [float(c) for c in fwd_closes]
    pos = len(seq)
    if pos - n < 0:
        return None
    cs = [0.0]
    acc = 0.0
    for i, x in enumerate(seq):
        acc = x if i == 0 else acc + x
        cs.append(acc)
    return (cs[pos] - cs[pos - n]) / n


def day0_no_partial(minutes: "cb.MinuteBars", *, fill: float, stop: float, fill_minute: int) -> dict:
    """Day 0 under an exit with NO +2R sale (B, C, D): the minutes after the fill minute against the day-low stop only
    (`cb.day0_walk`, the live stop-only walk), the highest high after the fill (`cb.day0_peak_high`) and whether that
    high reached +2R (`hit2r`: B / C rest the breakeven stop from SESSION 1, never inside day 0 — the 10-22 grid's P0
    reading, 'from the session after +2R was first reached'). The fill minute's own low is not read (cb's convention)."""
    d0 = cb.day0_walk(minutes, fill_minute=int(fill_minute), stop=float(stop))
    peak = cb.day0_peak_high(minutes, int(fill_minute))
    target = ppr.target_price(fill, stop)
    return {"stopped": bool(d0["stopped"]), "exit_price": d0.get("exit_price"), "exit_minute": d0.get("exit_minute"),
            "peak": (None if not math.isfinite(peak) else float(peak)), "hit2r": bool(math.isfinite(peak) and peak >= target),
            "partial_price": None, "partial_minute": None}


def trail_n_for(rule: str, adr20: float) -> int:
    """C: the round-3 speed cut — the 10-day when ADR20 at D is ABOVE `cb.TRAIL_SPEED_ADR_CUT` (4.79%), else the 20-day
    (`consolidation_breakout.walk_exit`, trail_mode 'speed': `SMA_SHORT if adr20 > TRAIL_SPEED_ADR_CUT else SMA_MID`).
    B and D: the 20-day (`ppr.TRAIL_SMA`)."""
    if rule == "C":
        return int(cb.SMA_SHORT) if float(adr20) > float(cb.TRAIL_SPEED_ADR_CUT) else int(cb.SMA_MID)
    return int(ppr.TRAIL_SMA)


def step_rule(rule: str, *, fill: float, stop: float, d0: dict, closes_before, fwd: "cb.DailyBars", adr20: float,
              horizon: int = V.HORIZON) -> dict:
    """Sessions 1.. on the daily bars for exits B, C, D, in `walk_pp`'s shape (status, realized_r, sessions_held, events;
    the event vocabulary of `v1_replay.step_pp` so `leg_rows` / `r_at_cost` / `free_point` read it unchanged; a frac-0
    event is informational). Per session, in the live order: (1) the broker's stop leg (a gap under it books the open);
    (1b) B / C: +2R first reached (a high at the target, or an open above it) -> breakeven from the NEXT session, no sale;
    (1c) the stall cut's reach test (sessions 1..3), the cut at session 3's close when fill + 1R was never reached;
    (2) D: the third at the close of the first of sessions 3 / 4 / 5 that closes ABOVE the fill (`stop_after_third`
    from the next session); (3) the trail on the settled close — live once +2R was reached (B / C) / from session 3
    (all): C / D sell everything at the NEXT open after the first close under the average (X1); B opens a WATCH at the
    first close under the 20-day (sj), a close at or above it on sj+1 or sj+2 cancels the watch (a later close under
    opens a fresh one), no reclaim by sj+2's close -> everything sold at the open of sj+3 (X3, grace 2; the stop and
    the cut keep running inside the window); (4) the horizon mark. `d0` = `day0_no_partial` of the breakout day."""
    if rule not in ("B", "C", "D"):
        raise ValueError(rule)
    risk = float(fill) - float(stop)
    if not risk > 0:
        raise ValueError("step_rule: stop must be below the fill")
    adr20 = cb._check_adr(adr20)
    fill, stop = float(fill), float(stop)
    o, h, l, c = fwd.o, fwd.h, fwd.l, fwd.c
    n = len(c)
    frac = ppr.PARTIAL_FRAC
    target = ppr.target_price(fill, stop)
    cut_lvl = ppr.cut_level(fill, stop)
    sma_n = trail_n_for(rule, adr20)
    events: list = []
    if rule == "C":
        events.append((0, "trail_n", float(sma_n), 0.0))
    pnl = 0.0
    remaining = 1.0
    stop_now = stop
    partial_taken = False
    no_partial = rule in ("B", "C")
    hit2r = bool(no_partial and d0.get("hit2r"))
    reached = bool(d0.get("peak") is not None and float(d0["peak"]) >= cut_lvl)
    if hit2r:                                          # +2R reached on day 0 after the fill: breakeven rests from session 1
        events.append((0, "reach_2r", float(d0["peak"]), 0.0))
        stop_now = ppr.stop_after_third(stop_now, fill)
        events.append((0, "stop_to", stop_now, 0.0))
    watch: Optional[int] = None
    cb_list = [float(x) for x in closes_before]
    fwd_closes: list = []
    for j in range(1, min(int(horizon), n) + 1):
        oj, hj, lj, cj = float(o[j - 1]), float(h[j - 1]), float(l[j - 1]), float(c[j - 1])
        fwd_closes.append(cj)
        stop_j = stop_now
        gap2r = bool(no_partial and not hit2r and oj >= target)
        # 1. the broker's stop leg
        if oj <= stop_j or lj <= stop_j:
            if gap2r:
                events.append((j, "reach_2r", oj, 0.0))
            px = oj if oj <= stop_j else stop_j
            events.append((j, "stop_gap" if oj < stop_j else "stop", px, remaining))
            pnl += (px - fill) * remaining
            return cb._outcome("stopped", pnl, risk, fill, adr20, j, events)
        # 1b. B / C: +2R first reached -> breakeven from the next session (no sale)
        if no_partial and not hit2r and (gap2r or hj >= target):
            hit2r = True
            events.append((j, "reach_2r", oj if gap2r else target, 0.0))
            stop_now = ppr.stop_after_third(stop_now, fill)
            events.append((j, "stop_to", stop_now, 0.0))
            if stop_now > cj:
                events.append((j, "be_above_close", cj, 0.0))
        # 1c. the stall cut: the reach test (sessions 1..3), the cut at session 3's close
        if j <= ppr.STALL_CUT_SESSION:
            if hj >= cut_lvl:
                reached = True
            if j == ppr.STALL_CUT_SESSION and not reached:
                events.append((j, "cut", cj, remaining))
                pnl += (cj - fill) * remaining
                return cb._outcome("time_exit", pnl, risk, fill, adr20, j, events)
        # 2. D: the third at the first close of session 3 / 4 / 5 above the fill
        if rule == "D" and not partial_taken and j in D_THIRD_SESSIONS and cj > fill:
            events.append((j, "partial", cj, frac))
            pnl += (cj - fill) * frac
            remaining -= frac
            partial_taken = True
            stop_now = ppr.stop_after_third(stop_now, fill)
            events.append((j, "stop_to", stop_now, 0.0))
            if stop_now > cj:
                events.append((j, "be_above_close", cj, 0.0))
        # 3. the trail on the settled close
        live = (hit2r if no_partial else partial_taken) or j >= ppr.LEG_SESSION
        sma = sma_n_at(cb_list, fwd_closes, sma_n)
        under = sma is not None and cj < sma
        sell = False
        if rule == "B":
            if watch is not None:
                if sma is not None and cj >= sma:
                    events.append((j, "reclaim", sma, 0.0))
                    watch = None
                elif j == watch + X3_GRACE:
                    sell = True
            elif live and under:
                watch = j
                events.append((j, "watch", sma, 0.0))
        else:
            sell = bool(live and under)
        if sell and j < n:
            opx = float(o[j])
            events.append((j + 1, "trail", opx, remaining))
            pnl += (opx - fill) * remaining
            return cb._outcome("censored" if j == int(horizon) else "trailed", pnl, risk, fill, adr20, j + 1, events)
        # 4. the horizon
        if j == int(horizon):
            events.append((j, "mark", cj, remaining))
            pnl += (cj - fill) * remaining
            return cb._outcome("censored", pnl, risk, fill, adr20, j, events)
    return cb._degraded(c, n, remaining, pnl, fill, risk, adr20, events, cb_list[-1] if cb_list else None)


def exit_rule(rule: str, *, fill: float, stop: float, d0_pp: Optional[dict], d0_np: Optional[dict], closes_before,
              fwd: "cb.DailyBars", adr20: float, horizon: int = V.HORIZON) -> dict:
    """One filled trade under one exit. A: `V.exit_one` (the live pp decisions, asserted equal to `walk_pp`) on the pp
    day-0 facts; B / C / D: a day-0 stop-out under the stop-only walk is booked by `cb.day0_result_to_outcome`, else
    `step_rule` on the daily bars."""
    if rule == "A":
        return V.exit_one(fill=fill, stop=stop, day0=d0_pp, closes_before=closes_before, fwd=fwd, adr20=adr20, horizon=horizon)
    if d0_np.get("stopped"):
        return cb.day0_result_to_outcome({"status": "filled", "fill": fill, "stop": stop, "day0": d0_np}, adr20)
    return step_rule(rule, fill=fill, stop=stop, d0=d0_np, closes_before=closes_before, fwd=fwd, adr20=adr20, horizon=horizon)


def book_fields(rec: dict, res: dict, *, fwd, d0: dict, fm: Optional[int], date_at, ed: date) -> None:
    """The exit side of a trade for the books (free point, legs, costs), through V's helpers."""
    fill, stop = rec["fill"], rec["stop"]
    held = int(res["sessions_held"])
    exit_kind = res["events"][-1][1] if res["events"] else None
    mature = bool(cb.is_mature(res["status"], len(fwd)))
    free_date, free_minute = V.free_point(res["status"], held, fwd, d0, rec["E"], date_at)
    rec.update(status=res["status"], events=res["events"], sessions_held=held, mature=mature, open_mark=not mature,
               n_fwd=len(fwd), exit_kind=exit_kind, free_date=free_date, free_minute=free_minute,
               exit_at_open=(exit_kind == "trail"), realized_r=float(res["realized_r"]),
               decisive=bool(mature and not rec["after_cutoff"]))
    c_primary = PRIMARY_COST / 100.0 / rec["raw_factor"]
    rec["r_2c"] = V.r_at_cost(res["events"], fill, stop, c_primary)
    rec["r_0c"] = V.r_at_cost(res["events"], fill, stop, 0.0)
    rec["legs"] = V.leg_rows(res["events"], fill=fill, stop=stop, cost=c_primary, e_iso=rec["E"], dates_from_e=date_at,
                             day0=d0, fm=fm)
    rec["total_r"] = rec["r_2c"]
    rec["f_risk"] = V.risk_fraction(fill, stop)


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 4. Re-walking the frozen fills under every exit (the entry side untouched), and the new names end to end
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def rewalk_frozen(rows: list, stores: Stores, index: list, rules: tuple = EXITS, *, assert_a: bool = True,
                  log=print) -> dict:
    """{rule: {key: rec}} for every frozen FILLED row (incl. the 4 sold after the fill, identical under every exit).
    Under A the re-walk is ASSERTED equal to the frozen events on every fill (the proof that B / C / D read the same
    bars, day-0 minutes and ADR the baseline read). Rows the baseline excluded stay excluded (`sold_after_fill` kept)."""
    out = {r: {} for r in rules}
    by_e = defaultdict(list)
    for t in rows:
        if t["filled"]:
            by_e[t["E"]].append(t)
    n_bad = 0
    t0 = time.time()
    for n_e, e in enumerate(sorted(by_e)):
        ed = date.fromisoformat(e)
        V.assert_sealed(ed, "breakout day")
        names = by_e[e]
        blocks = minute_blocks(index, e, [t["ticker"] for t in names])
        for t in names:
            if t["outcome"] == "sold_after_fill":
                for r in rules:
                    out[r][t["key"]] = dict(t)
                continue
            mb, state = blocks.get(t["ticker"], (None, "pending"))
            if state != "ok" or mb is None or len(mb) == 0:
                raise SystemExit(f"re-walk: the minutes of a frozen fill are not held: {t['key']} ({state})")
            bars, cidx, e_i, chosen = forward_inputs(stores, t)
            if e_i is None or chosen != t["fwd_store"]:
                raise SystemExit(f"re-walk: the forward store differs from the frozen row: {t['key']} {chosen} vs {t['fwd_store']}")
            fill, stop, fm = t["fill"], t["stop"], t["fill_minute"]
            mins = V.minutes_to_dict(mb)
            d0_pp = ppr.day0_facts([(m, b["open"], b["high"], b["low"]) for m, b in sorted(mins.items())], fill=fill, stop=stop,
                                   fill_minute=fm)
            d0_np = day0_no_partial(mb, fill=fill, stop=stop, fill_minute=fm)
            fwd, _cut = cb.forward_window(bars, cidx, e_i, V.HORIZON)
            for d in fwd.dates:
                V.assert_sealed(d, "forward bar")
            date_at = (lambda j, _b=bars, _e=e_i: _b.dates[min(_e + j, len(_b) - 1)])
            for r in rules:
                res = exit_rule(r, fill=fill, stop=stop, d0_pp=d0_pp, d0_np=d0_np, closes_before=bars.c[:e_i + 1], fwd=fwd,
                                adr20=t["adr20"])
                rec = dict(t)
                book_fields(rec, res, fwd=fwd, d0=(d0_pp if r == "A" else d0_np), fm=fm, date_at=date_at, ed=ed)
                if r == "A" and assert_a:
                    same = (V.events_equal(rec["events"], t["events"]) and rec["status"] == t["status"]
                            and abs(rec["r_2c"] - t["r_2c"]) <= 1e-9 and rec["free_date"] == t["free_date"]
                            and rec["free_minute"] == t["free_minute"] and rec["decisive"] == t["decisive"])
                    if not same:
                        n_bad += 1
                        if n_bad <= 5:
                            log(f"  A re-walk differs: {t['key']} {rec['status']} {rec['events']} vs {t['status']} {t['events']}")
                out[r][t["key"]] = rec
        if n_e % 200 == 0:
            log(f"  re-walk day {n_e}/{len(by_e)} {e}: {sum(len(v) for v in out.values())} recs ({time.time() - t0:.0f}s)")
    if assert_a and n_bad:
        raise SystemExit(f"re-walk: the A exit differs from the frozen events on {n_bad} fills")
    log(f"  re-walk: {len(out[rules[0]]):,} fills x {len(rules)} exits; A == frozen on every fill ({time.time() - t0:.0f}s)")
    return out


def walk_new_rows(new_rows: list, stores: Stores, index: list, raw: dict, unfetchable: set, cutoff: date, rules: tuple,
                  log=print) -> tuple:
    """The NEW list names (rs in [90, 98)) end to end: the same entry (`V.simulate_entry` on the minutes, the same data
    abstains, the same raw-close re-judgement), then every exit rule. Returns ({rule: {key: rec}}, exclusions)."""
    out = {r: {} for r in rules}
    excl = Counter()
    by_e = defaultdict(list)
    for lr in new_rows:
        by_e[lr["E"]].append(lr)
    t0 = time.time()
    for n_e, e in enumerate(sorted(by_e)):
        ed = date.fromisoformat(e)
        V.assert_sealed(ed, "breakout day")
        names = by_e[e]
        blocks = minute_blocks(index, e, [lr["ticker"] for lr in names])
        for lr in names:
            t = lr["ticker"]
            raw_factor = float(lr["raw_factor_D"])
            if int(lr.get("raw_src") or 0) == 2:
                raw_d = raw.get((t, lr["scan_date"]))
                if raw_d is None:
                    excl["raw_close_missing"] += 1
                    continue
                if raw_d < bv.MIN_PRICE:
                    excl["below_floor_raw"] += 1
                    continue
                raw_factor = raw_d / float(lr["close"])
            mb, state = blocks.get(t, (None, "pending"))
            if state != "ok" or mb is None or len(mb) == 0:
                excl["minutes_unfetchable" if (e, t) in unfetchable else f"minutes_{state}"] += 1
                continue
            bars, cidx, e_i, fwd_store = V.walk_inputs(stores._s, stores.get, lr, ed)
            if e_i is None:
                excl["no_daily_bar_E"] += 1
                continue
            dh, dl = float(bars.h[e_i]), float(bars.l[e_i])
            if abs(float(mb.h.max()) - dh) / dh > V.MISMATCH_MAX or abs(float(mb.l.min()) - dl) / dl > V.MISMATCH_MAX:
                excl["minute_daily_mismatch"] += 1
                continue
            mins = V.minutes_to_dict(mb)
            tr = V.simulate_entry(mins, list_level=lr["level"], adr20=lr["adr20"], vol_bar=lr["vol_bar"])
            rec = {"key": f"{e}|{t}", "E": e, "D": lr["scan_date"], "ticker": t, "list_rank": lr["list_rank"], "era_store": lr["era_store"],
                   "fwd_store": fwd_store, "era": ERA_A if ed <= V.ERA_A_E_LAST else ERA_B, "year": ed.year, "month": e[:7],
                   "list_level": lr["level"], "adr20": lr["adr20"], "vol_bar": lr["vol_bar"], "rs_best": lr["rs_best"],
                   "raw_factor": raw_factor, "raw_src": int(lr.get("raw_src") or 0), "outcome": tr["outcome"], "reason": tr["reason"],
                   "placed_m": tr["placed_m"], "cancel_m": tr["cancel_m"], "level": tr["level"], "orh5": tr["orh5"],
                   "fill": tr["fill"], "fill_minute": tr["fill_minute"], "placed_stop": tr["placed_stop"], "stop": tr["stop"],
                   "stop_check": (tr["stop_check"] or {}).get("action"), "filled": tr["outcome"] in ("filled", "sold_after_fill"),
                   "after_cutoff": ed > cutoff, "decisive": False, "free_date": None, "free_minute": None, "exit_at_open": False,
                   "new_name": True}
            excl[f"entry_{tr['outcome']}"] += 1
            if tr["placed_m"] is not None:
                rec["width_raw_cents"] = placement_width_cents(mins, int(tr["placed_m"]), list_level=lr["level"], adr20=lr["adr20"],
                                                               vol_bar=lr["vol_bar"], raw_factor=raw_factor)
            if tr["outcome"] == "sold_after_fill":
                fill, stop, px, fm = tr["fill"], tr["stop"], tr["sold_after_fill_px"], tr["fill_minute"]
                rec.update(status="sold_after_fill", events=[(0, "sold_after_fill", px, 1.0)], sessions_held=0, mature=True,
                           free_date=e, free_minute=fm + 1, exit_kind="sold_after_fill", open_mark=False, decisive=not rec["after_cutoff"])
                c_primary = PRIMARY_COST / 100.0 / raw_factor
                rec["r_2c"] = V.r_at_cost(rec["events"], fill, stop, c_primary)
                rec["r_0c"] = V.r_at_cost(rec["events"], fill, stop, 0.0)
                rec["legs"] = V.leg_rows(rec["events"], fill=fill, stop=stop, cost=c_primary, e_iso=e, dates_from_e=lambda j: ed,
                                         day0={"partial_minute": None, "exit_minute": None}, fm=fm)
                rec["total_r"] = rec["r_2c"]
                rec["f_risk"] = V.risk_fraction(fill, stop)
                for r in rules:
                    out[r][rec["key"]] = dict(rec)
                continue
            if tr["outcome"] != "filled":
                for r in rules:
                    out[r][rec["key"]] = dict(rec)
                continue
            fill, stop, fm = tr["fill"], tr["stop"], tr["fill_minute"]
            if not stop < fill:
                excl["stop_at_or_above_fill"] += 1
                rec.update(outcome="abstain", reason="stop_at_or_above_fill", filled=False)
                for r in rules:
                    out[r][rec["key"]] = dict(rec)
                continue
            d0_pp = ppr.day0_facts([(m, b["open"], b["high"], b["low"]) for m, b in sorted(mins.items())], fill=fill, stop=stop,
                                   fill_minute=fm)
            d0_np = day0_no_partial(mb, fill=fill, stop=stop, fill_minute=fm)
            fwd, _cut = cb.forward_window(bars, cidx, e_i, V.HORIZON)
            for d in fwd.dates:
                V.assert_sealed(d, "forward bar")
            date_at = (lambda j, _b=bars, _e=e_i: _b.dates[min(_e + j, len(_b) - 1)])
            for r in rules:
                res = exit_rule(r, fill=fill, stop=stop, d0_pp=d0_pp, d0_np=d0_np, closes_before=bars.c[:e_i + 1], fwd=fwd,
                                adr20=lr["adr20"])
                rr = dict(rec)
                book_fields(rr, res, fwd=fwd, d0=(d0_pp if r == "A" else d0_np), fm=fm, date_at=date_at, ed=ed)
                out[r][rr["key"]] = rr
        if n_e % 200 == 0:
            log(f"  new-name day {n_e}/{len(by_e)} {e}: {len(out[rules[0]])} rows, {dict(excl)} ({time.time() - t0:.0f}s)")
    return out, excl


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 5. The book, the measures, the bar
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def book_rows(placed_frozen: list, recs: dict, new_placed: Optional[dict] = None, *, floor: bool = False,
              tick: Optional[dict] = None, rs_min: float = 98.0) -> list:
    """The placed rows the book sees under one cell: the frozen placed rows (their exit side from `recs` when filled),
    plus the new names' placed rows at rs >= rs_min, minus the rows under the 15c floor (never placed)."""
    rows = []
    for t in placed_frozen:
        rows.append(recs[t["key"]] if t["filled"] else t)
    if new_placed:
        for k, t in new_placed.items():
            if t.get("placed_m") is not None and float(t["rs_best"]) >= rs_min:
                rows.append(t)
    if floor:
        rows = [t for t in rows if width_cents(t, tick) >= FLOOR_CENTS]
    return rows


def placement_width_cents(mins: dict, placed_m: int, *, list_level: float, adr20, vol_bar: float, raw_factor: float) -> float:
    """The planned risk at the PLACEMENT tick in RAW cents, read exactly as the follow-up read it for every frozen placed
    row (`followup.run_tick`): the live `breakout_v1_entry.evaluate` on the minutes through placed_m - 1 -> (level - the
    day-low stop) x the raw factor x 100. Never the re-priced stop (a re-price lowers the stop and would widen the reading)."""
    st = V.bve.evaluate({k: v for k, v in mins.items() if k <= placed_m - 1}, list_level=float(list_level), adr20=adr20,
                        vol_bar=float(vol_bar), last_completed=placed_m - 1)
    return (float(st["level"]) - float(st["stop"])) * float(raw_factor) * 100.0


def width_cents(t: dict, tick: Optional[dict]) -> float:
    """The planned risk at placement in RAW cents: the follow-up's `width_raw_cents` for a frozen row; for a new name the
    SAME reading computed by `placement_width_cents` in the walk (`t["width_raw_cents"]`). A placed row with neither is
    a defect, not a pass."""
    if tick is not None and t["key"] in tick:
        return float(tick[t["key"]]["width_raw_cents"])
    if t.get("width_raw_cents") is None:
        raise ValueError(f"width_cents: no placement width for {t.get('key')}")
    return float(t["width_raw_cents"])


def run_book(rows: list, sessions: list, slots: Optional[int]) -> dict:
    return V.apply_book(rows, slots=slots, safeguards=False, sessions=sessions)


def scored(rows: list, adm: dict, era: Optional[str]) -> list:
    return [t for t in rows if adm["admitted"].get(t["key"]) and t["filled"] and t["decisive"] and (era is None or t["era"] == era)]


def measures(pop: list, key: str, rcol: str = "r_2c") -> dict:
    s = V.stats(np.array([t[rcol] for t in pop]), [t["month"] for t in pop], key=key)
    if s.get("n", 0):
        s["ge10_per100"] = 100.0 * s["share_ge10"]
        s["ge5_per100"] = 100.0 * s["share_ge5"]
        s["ge3_per100"] = 100.0 * s["share_ge3"]
        r = np.array([t[rcol] for t in pop])
        s["avg_win"] = float(r[r > 0].mean()) if (r > 0).any() else float("nan")
        s["avg_loss"] = float(r[r <= 0].mean()) if (r <= 0).any() else float("nan")
        s["losers"] = int((r <= 0).sum())
    return s


def verdict_template(s: dict) -> tuple:
    """TEMPLATE / FAIL / CAN'T TELL (registration §5): read on the primary row only."""
    if s.get("n", 0) < N_FLOOR:
        return CANT, f"n = {s.get('n', 0)} < {N_FLOOR}"
    tail = s["ge10_per100"] >= TAIL_PER100
    if s["ci_lo"] > 0 and tail:
        return TEMPLATE, f"interval lower end > 0 and >= {TAIL_PER100:.0f} per 100 at 10R+"
    if s["ci_hi"] < FAIL_MEAN_REF and not tail:
        return "FAIL", f"whole interval under +{FAIL_MEAN_REF}R and under {TAIL_PER100:.0f} per 100 at 10R+"
    if tail and s["ci_lo"] <= 0:
        return CANT, "tail present, mean not shown positive: the big winners are there, the rest gives it back"
    if not tail and s["ci_lo"] > 0:
        return CANT, "mean positive, tail thin: the big winners are not found or not held"
    return CANT, "interval spans the bar"


def fmt(name: str, s: dict, with_verdict: bool = False) -> str:
    if s.get("n", 0) == 0:
        return f"{name:46s} n 0"
    txt = (f"{name:46s} n {s['n']:5d}  mean {s['mean_r']:+.3f} [{s['ci_lo']:+.2f}, {s['ci_hi']:+.2f}]  win {s['win_rate']:5.1%}  "
           f"med {s['median_r']:+.2f}  avg win {s['avg_win']:+.2f} avg loss {s['avg_loss']:+.2f}  "
           f"10R+/100 {s['ge10_per100']:4.1f} ({s['n_ge10']})  5R+/100 {s['ge5_per100']:4.1f}  3R+ {s['share_ge3']:4.1%}  sum {s['sum_r']:+.0f}")
    if with_verdict:
        v, why = verdict_template(s)
        txt += f"   VERDICT {v} ({why})"
    return txt


def bench_line() -> str:
    b = BENCH
    return (f"{'BENCHMARK ' + 'his 205 trades under our rules':46s} n {b['n']:5d}  mean {b['mean_r']:+.3f}             "
            f"win {b['win_rate']:5.1%}  med {b['median_r']:+.2f}                              10R+/100 {b['ge10_per100']:4.1f}")


def pick(cands: dict, order: list) -> str:
    """The pick rule (§4): the highest 2017-21 mean R on the primary row; means within PICK_TIE -> the higher 10R+ per
    100; still tied -> the earlier in `order` (A / today's first)."""
    best = order[0]
    for c in order[1:]:
        a, b = cands[c], cands[best]
        if a.get("n", 0) < N_FLOOR:
            continue
        if b.get("n", 0) < N_FLOOR:
            best = c
            continue
        if a["mean_r"] > b["mean_r"] + PICK_TIE:
            best = c
        elif abs(a["mean_r"] - b["mean_r"]) <= PICK_TIE and a["ge10_per100"] > b["ge10_per100"] + 1e-9:
            best = c
    return best


def paired_diff(recs_x: dict, recs_a: dict, era: str, key: str) -> dict:
    """The 'beyond noise' yardstick for an exit: the per-trade difference X - A on the SAME filled decisive trades (the
    uncapped set, so the book's path dependence is out), month-block bootstrap of its mean."""
    keys = [k for k, t in recs_a.items() if t["filled"] and t.get("decisive") and t["era"] == era and k in recs_x
            and recs_x[k].get("decisive")]
    d = np.array([recs_x[k]["r_2c"] - recs_a[k]["r_2c"] for k in keys])
    if len(d) == 0:
        return {"n": 0}
    lo, hi = runner.block_bootstrap_ci(d, [recs_a[k]["month"] for k in keys], key=key)
    return {"n": len(d), "mean": float(d.mean()), "lo": lo, "hi": hi, "beyond_noise": bool(lo > 0 or hi < 0)}


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 6. The list at rs >= 90 (steps 3), the request, the coverage
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def run_population(era: str) -> dict:
    """`V.run_population` with `breakout_v1.RS_MIN` set to 90 for the call (the gate reads the module global at call time;
    the module file is not edited). The rows with rs_best >= 98 must equal the pinned list row for row (`parity`)."""
    LIST90.mkdir(parents=True, exist_ok=True)
    old = bv.RS_MIN
    try:
        bv.RS_MIN = float(min(RS_LEVELS))
        assert bv.v1_gates.__globals__["RS_MIN"] == bv.RS_MIN
        summary = V.run_population(era, LIST90)
    finally:
        bv.RS_MIN = old
    summary["rs_min_used"] = float(min(RS_LEVELS))
    (LIST90 / f"population_era{era}.json").write_text(json.dumps(summary, indent=1, default=str))
    return summary


def nesting_parity(log=print) -> list:
    """The 90-list restricted to rs_best >= 98 == the frozen 98-list, row for row (every column, the rank included)."""
    rows90 = V.read_list(LIST90)
    rows98 = V.read_list(V.OUT)
    sub = [r for r in rows90 if r["rs_best"] >= 98.0]
    k90 = {(r["scan_date"], r["ticker"]): r for r in sub}
    k98 = {(r["scan_date"], r["ticker"]): r for r in rows98}
    problems = []
    if set(k90) != set(k98):
        problems.append(f"nesting: {len(set(k98) - set(k90))} frozen rows missing from the 90-list, {len(set(k90) - set(k98))} extra")
    n_diff = 0
    for k, r in k98.items():
        q = k90.get(k)
        if q is None:
            continue
        for col in ("E", "list_rank", "level", "vol_bar", "adr20", "rs_best", "close", "raw_factor_D", "raw_src", "security_type",
                    "prior_move", "pole_date", "base_low", "era_store"):
            a, b = r.get(col), q.get(col)
            if isinstance(a, float) and isinstance(b, float):
                if abs(a - b) > 1e-9:
                    n_diff += 1
                    break
            elif str(a) != str(b):
                n_diff += 1
                break
    if n_diff:
        problems.append(f"nesting: {n_diff} rows differ on a column")
    L = [f"nesting parity: 90-list rows {len(rows90):,}, of which rs >= 98: {len(sub):,}; frozen 98-list rows {len(rows98):,}; "
         f"{'EQUAL row for row' if not problems else 'DIFFER: ' + '; '.join(problems)}"]
    for lvl in RS_LEVELS:
        n = sum(1 for r in rows90 if r["rs_best"] >= lvl)
        L.append(f"  list rows at rs >= {lvl:.0f}: {n:,} ({n / 2012:.1f} a night); new over 98: {n - len(sub):,}")
    for line in L:
        log(line)
    return problems


def new_list_rows() -> list:
    rows90 = V.read_list(LIST90)
    return [r for r in rows90 if r["rs_best"] < 98.0]


def e_bar_facts(stores: Stores, rows: list) -> tuple:
    """E's daily high and volume per (ticker, E) from the row's store (the request's `why` rule, as `V.run_request`)."""
    need = defaultdict(set)
    for r in rows:
        need[r["era_store"]].add((r["ticker"], r["E"]))
    high_e, vol_e = {}, {}
    for era, pairs in need.items():
        S = stores.get(era)
        D = S.D
        pos = {d.isoformat(): i for i, d in enumerate(D.cal)}
        for t, e in pairs:
            k = D.tid.get(t)
            if k is None or e not in pos:
                continue
            a, b = int(D.start[k]), int(D.stop[k])
            ci = pos[e]
            j = np.searchsorted(D.ci[a:b], ci)
            if j < b - a and D.ci[a + j] == ci:
                high_e[(t, e)] = float(D.h[a + j])
                vol_e[(t, e)] = float(D.v[a + j])
    return high_e, vol_e


def run_request(stores: Stores, log=print) -> dict:
    """`minute_request.tsv` (ticker, session_date, why) for the NEW names' breakout days the stores do not hold; the
    raw-close request for the new raw_src=2 tickers outside the baseline's pull. Written once; pinned."""
    if REQUEST.exists():
        raise SystemExit(f"REFUSED — {REQUEST} exists: the request is written once and pinned")
    rows = new_list_rows()
    if not rows:
        raise SystemExit("no new list rows: run `population A` and `population B` first")
    high_e, vol_e = e_bar_facts(stores, rows)
    index = minute_index()
    req, cov = [], Counter()
    per_level = {lvl: Counter() for lvl in RS_LEVELS if lvl < 98}
    for r in rows:
        key = (r["ticker"], r["E"])
        if key not in high_e:
            cov["no_daily_bar_E"] += 1
            r["minutes"] = "no_daily_bar_E"
            continue
        why = "fill_possible" if high_e[key] > r["level"] * (1.0 - V.MISMATCH_MAX) else "cap_occupancy_only"
        fired = bv.breakout_triggered({"h": high_e[key], "v": vol_e[key]}, {"ok": True, "level": r["level"], "vol_bar": r["vol_bar"]})
        r["fired"] = int(fired["fired"])
        cov["fired_E"] += int(fired["fired"])
        src = V.held_in(index, r["E"], r["ticker"])
        if src is not None:
            cov[f"held_{why}"] += 1
            r["minutes"] = f"held:{src.name}"
        else:
            cov[f"missing_{why}"] += 1
            r["minutes"] = "missing"
            req.append({"ticker": r["ticker"], "session_date": r["E"], "why": why, "rs_best": r["rs_best"]})
        for lvl in per_level:
            if r["rs_best"] >= lvl:
                per_level[lvl]["rows"] += 1
                per_level[lvl]["missing" if src is None else "held"] += 1
    req.sort(key=lambda x: (x["session_date"], x["ticker"]))
    for x in req:
        V.assert_sealed(date.fromisoformat(x["session_date"]), "requested minute session")
    with open(REQUEST, "w", newline="") as fh:
        w = csv.writer(fh, delimiter="\t")
        w.writerow(["ticker", "session_date", "why"])
        for x in req:
            w.writerow([x["ticker"], x["session_date"], x["why"]])
    # the raw closes: new raw_src=2 tickers / dates the baseline's pull does not cover
    raw, _meta = V.load_raw_pull()
    span: dict = {}
    n_raw2 = n_raw_covered = 0
    for r in rows:
        if int(r.get("raw_src") or 0) == 2:
            n_raw2 += 1
            if (r["ticker"], r["scan_date"]) in raw:
                n_raw_covered += 1
                continue
            t = r["ticker"]
            s = span.setdefault(t, [r["scan_date"], r["scan_date"], 0])
            s[0] = min(s[0], r["scan_date"]); s[1] = max(s[1], r["scan_date"]); s[2] += 1
    with open(RAW_REQUEST, "w", newline="") as fh:
        w = csv.writer(fh, delimiter="\t")
        w.writerow(["ticker", "first_date", "last_date", "n_list_rows"])
        for t in sorted(span):
            w.writerow([t, span[t][0], span[t][1], span[t][2]])
    summary = {"new_list_rows": len(rows), "request_rows": len(req), "request_sessions": len({x["session_date"] for x in req}),
               "request_fill_possible": sum(1 for x in req if x["why"] == "fill_possible"),
               "request_cap_occupancy_only": sum(1 for x in req if x["why"] == "cap_occupancy_only"),
               "request_rows_rs_ge95": sum(1 for x in req if x["rs_best"] >= 95.0),
               "request_rows_rs_90_95": sum(1 for x in req if x["rs_best"] < 95.0),
               "coverage": dict(cov), "per_level": {f"rs>={int(k)}": dict(v) for k, v in per_level.items()},
               "new_raw_src2_rows": n_raw2, "new_raw_src2_rows_covered_by_baseline_pull": n_raw_covered,
               "raw_close_request_tickers": len(span), "raw_close_request_list_rows": sum(s[2] for s in span.values()),
               "pull_dir": str(TG_MINUTE_DIR), "raw_pull_file": str(TG_RAW_PULL)}
    (HERE / "request_summary.json").write_text(json.dumps(summary, indent=1))
    V.write_tsv(HERE / "list_coverage_new.tsv", rows, ["scan_date", "E", "ticker", "list_rank", "rs_best", "level", "minutes", "fired"])
    log(json.dumps(summary, indent=1))
    return summary


def read_request() -> list:
    return V.read_request(REQUEST)


def coverage_problems() -> list:
    """The coverage rule (the baseline's, §7): every requested pair HELD or UNFETCHABLE, at most 2% unfetchable."""
    request = read_request()
    index = minute_index()
    failed = V.load_failed_pairs(TG_MINUTE_DIR) if TG_MINUTE_DIR.is_dir() else set()
    cov = V.coverage(index, request, failed=failed)
    problems = V.coverage_problems(cov, len(request))
    raw_req = V.read_request(RAW_REQUEST)
    if raw_req:
        if not TG_RAW_PULL.exists():
            problems.append(f"the raw-close pull for the {len(raw_req)} new raw_src=2 tickers is missing: {TG_RAW_PULL}")
        else:
            raw, _meta = load_raw_all()
            miss = [r["ticker"] for r in raw_req if not any((r["ticker"], d) in raw for d in (r["first_date"], r["last_date"]))]
            cov["raw_close_tickers_without_a_row_at_their_span_ends"] = len(miss)
            if len(miss) > V.UNFETCHABLE_MAX * len(raw_req):
                problems.append(f"{len(miss)} of {len(raw_req)} raw-close tickers have no pulled row at either end of their span (> {V.UNFETCHABLE_MAX:.0%})")
            # row level, the walk's own test, BEFORE any outcome: every new raw_src=2 list row needs a raw close on its D
            raw2 = [lr for lr in new_list_rows() if int(lr.get("raw_src") or 0) == 2]
            miss_rows = sum(1 for lr in raw2 if (lr["ticker"], lr["scan_date"]) not in raw)
            cov["raw_src2_new_rows"] = len(raw2)
            cov["raw_src2_new_rows_without_a_raw_close"] = miss_rows
            if raw2 and miss_rows > V.UNFETCHABLE_MAX * len(raw2):
                problems.append(f"{miss_rows:,} of {len(raw2):,} new raw_src=2 list rows have no raw close on D (> {V.UNFETCHABLE_MAX:.0%}; the walk's own bound)")
    return problems, cov


def load_raw_all() -> tuple:
    """The baseline's raw-close pull, plus this grid's (optional) pull for the new raw_src=2 tickers."""
    raw, meta = V.load_raw_pull()
    meta = {"baseline": meta}
    if TG_RAW_PULL.exists():
        raw2, meta2 = V.load_raw_pull(TG_RAW_PULL, TG_RAW_META, RAW_REQUEST)
        raw = dict(raw)
        raw.update(raw2)
        meta["tgrid"] = meta2
    return raw, meta


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 7. The big winners (step 3 recall, step 4's 31 refused catches)
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def load_winners() -> tuple:
    """(the 872 real big breakouts of the +100% set, the 31 refused >= 3R catches) from the winners table."""
    import pandas as pd
    w = pd.read_csv(WINNERS, sep="\t", low_memory=False)
    w1 = w[w["set"] == "+100%"]
    real = w1[w1["class"] == "measurable_breakout"]
    refused = w1[(w1.catch_r_2c >= 3) & (w1.catch_slot == 0)]
    return real.to_dict("records"), refused.to_dict("records")


def winner_recall(real: list, list_rows: list, recs: dict, adm_cap: dict, adm_guard: dict) -> dict:
    """The big-winners study's funnel on the 872 real big breakouts under one cell: LISTED = a list row (ticker, D) with
    trough <= D <= s50; FILLED = a listed night whose row filled (the uncapped walk); the CATCH = the first filled night;
    its R under the cell's exit; SLOT = the catch admitted by the capped book; made money / >= 3R / >= 10R on the catch."""
    by_t = defaultdict(list)
    for r in list_rows:
        by_t[r["ticker"]].append(r["scan_date"])
    recs_by = defaultdict(dict)
    for k, t in recs.items():
        if t.get("filled"):
            recs_by[t["ticker"]][t["D"]] = t
    c = Counter(n=len(real))
    for w in real:
        t, lo, hi = w["ticker"], w["trough_date"], w["s50_date"]
        nights = sorted(d for d in by_t.get(t, ()) if lo <= d <= hi)
        if not nights:
            continue
        c["listed"] += 1
        fills = [recs_by[t][d] for d in nights if d in recs_by[t]]
        if not fills:
            continue
        c["filled"] += 1
        catch = fills[0]
        if adm_guard["admitted"].get(catch["key"]):
            pass
        if adm_cap["admitted"].get(catch["key"]):
            c["slot"] += 1
        if catch["r_2c"] > 0:
            c["made_money"] += 1
        if catch["r_2c"] >= 3:
            c["ge3"] += 1
        if catch["r_2c"] >= 10:
            c["ge10"] += 1
        if any(adm_cap["admitted"].get(f["key"]) for f in fills):
            c["any_fill_slot"] += 1
    return dict(c)


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 8. The pins and the freeze
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def pin_map() -> dict:
    m = {"grid.py": HERE / "grid.py", "v1_replay.py": PROBE / "v1_replay.py", "trades.tsv.gz": TRADES,
         "tick_facts.tsv.gz": TICK, "big_winners_2017_2024.tsv": WINNERS, "trail_lib.py": TRAIL_LIB,
         "consolidation_breakout.py": CB_MODULE, "breakout_pp_rules.py": V.LIVE_PINS.get("breakout_pp_rules.py", REPO / "agents/market_intelligence/broker/breakout_pp_rules.py"),
         "list90/list_eraA.tsv.gz": LIST90 / "list_eraA.tsv.gz", "list90/list_eraB.tsv.gz": LIST90 / "list_eraB.tsv.gz",
         "list90/nights_eraA.tsv": LIST90 / "nights_eraA.tsv", "list90/nights_eraB.tsv": LIST90 / "nights_eraB.tsv",
         "minute_request.tsv": REQUEST, "raw_close_request.tsv": RAW_REQUEST, "dryrun.txt": OUT / "dryrun.txt",
         "calibration.txt": OUT / "calibration.txt", "parity.txt": OUT / "parity.txt",
         "empirical_pp_c0_r.npy": PROBE / "empirical_pp_c0_r.npy", "empirical_pp_c0_months.npy": PROBE / "empirical_pp_c0_months.npy"}
    return m


def pins() -> list:
    return [f"| {k} | `{sha(p) if Path(p).is_file() else 'MISSING'}` |" for k, p in pin_map().items()]


def doc_body_sha(text: str) -> str:
    return runner.doc_body_sha(text)


def freeze_problems() -> list:
    """The walk's freeze: every pin of THIS registration matches the disk; the doc carries the FREEZE marker and a footer
    with `doc_body` equal to the body's sha; the BASELINE registration's body pins still match its artefacts (its own
    table, read through V's helpers — `V.freeze_problems` is not called because the baseline's outputs now exist)."""
    problems = []
    if not DOC.is_file():
        return [f"registration doc missing: {DOC}"]
    text = DOC.read_text(encoding="utf-8")
    if text.count(V.FREEZE_MARK) != 1:
        return [f"the doc must carry the {V.FREEZE_MARK} marker exactly once"]
    body, footer = text.split(V.FREEZE_MARK, 1)
    for k, p in pin_map().items():
        want = V._pin_in(body, k)
        if want is None:
            problems.append(f"body pin missing from the doc: {k}")
        elif not Path(p).is_file():
            problems.append(f"pinned file missing on disk: {k}")
        elif sha(p) != want:
            problems.append(f"pin differs: {k} (doc {want[:12]}.. disk {sha(p)[:12]}..)")
    fb = V._pin_in(footer, "doc_body")
    if fb is None:
        problems.append("footer carries no doc_body")
    elif fb != doc_body_sha(text):
        problems.append("doc_body differs from the body on disk (the body was edited after the freeze)")
    if V._pin_in(footer, "freeze_commit") is None and not re.search(r"freeze_commit\s*=\s*[0-9a-f]{7,40}", footer):
        problems.append("footer carries no freeze_commit")
    # the baseline's body pins (its artefacts, incl. the live rule modules and the stores) must still hold
    base_text = BASE_DOC.read_text(encoding="utf-8")
    base_body = base_text.split(V.FREEZE_MARK, 1)[0]
    for k, h in V.hashes_of(V.body_pin_map(V.OUT)).items():
        want = V._pin_in(base_body, k)
        if want is None or h != want:
            problems.append(f"the BASELINE's pin no longer holds: {k}")
    return problems


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 9. The calibration of the bar (synthetic populations on the real fill months)
# ═══════════════════════════════════════════════════════════════════════════════════════════════
CAL_NS = (100, 300, 520, 581, 700, 1000, 1058, 2000)
W_MEANS = (0.30, 0.50, 0.75, 1.05)


def q_profile(emp: np.ndarray, months: np.ndarray, win_rate: float = 0.25, mean: float = 1.06) -> tuple:
    """Qullamaggie's profile: the anchor's losers as they are; the smallest winners DROPPED until the win rate is
    `win_rate`; the remaining winners scaled by one factor so the mean lands on `mean`. Returns (r, months)."""
    win = emp > 0
    L = int((~win).sum())
    keep_w = int(round(L * win_rate / (1.0 - win_rate)))
    w_idx = np.flatnonzero(win)
    order = w_idx[np.argsort(emp[w_idx])]
    drop = set(order[:max(0, len(w_idx) - keep_w)].tolist())
    keep = np.array([i for i in range(len(emp)) if i not in drop])
    r, mo = emp[keep].copy(), months[keep]
    w2 = r > 0
    s = (mean * len(r) - r[~w2].sum()) / r[w2].sum()
    r = np.where(w2, r * s, r)
    return r, mo, float(s)


def q_tail_profile(emp: np.ndarray, months: np.ndarray, win_rate: float = 0.25, ge10_per100: float = 2.9) -> tuple:
    """His TAIL: the anchor thinned to `win_rate` as `q_profile`, the winners scaled so that exactly `ge10_per100` of
    every 100 trades reach 10R (the mean then falls where it falls — reported, not set)."""
    win = emp > 0
    L = int((~win).sum())
    keep_w = int(round(L * win_rate / (1.0 - win_rate)))
    w_idx = np.flatnonzero(win)
    order = w_idx[np.argsort(emp[w_idx])]
    drop = set(order[:max(0, len(w_idx) - keep_w)].tolist())
    keep = np.array([i for i in range(len(emp)) if i not in drop])
    r, mo = emp[keep].copy(), months[keep]
    q = float(np.quantile(r, 1.0 - ge10_per100 / 100.0))
    s = 10.0 / q
    r = np.where(r > 0, r * s, r)
    return r, mo, float(s)


def h_profile(emp: np.ndarray, months: np.ndarray, mean: float = 1.06, ge10_per100: float = 2.9) -> tuple:
    """His BENCHMARK on both counts (the review's population H, 11-01): the anchor's trades as they are (win 35%, his 37%),
    each winner raised to one power b and scaled by one factor a so that exactly `ge10_per100` of every 100 trades reach
    10R AND the mean lands on `mean` (b found by bisection). Returns (r, months, b)."""
    w = emp > 0
    k = int(round(ge10_per100 / 100.0 * len(emp)))

    def build(b: float) -> np.ndarray:
        rw = emp[w] ** b
        a = 10.0 / np.sort(rw)[::-1][k - 1]
        r = emp.copy()
        r[w] = a * rw
        return r
    lo, hi = 0.3, 3.0
    f_lo = build(lo).mean() - mean
    for _ in range(80):
        mid = (lo + hi) / 2.0
        f_mid = build(mid).mean() - mean
        if (f_mid > 0) == (f_lo > 0):
            lo, f_lo = mid, f_mid
        else:
            hi = mid
    b = (lo + hi) / 2.0
    return build(b), months, float(b)


def calibration(out_path: Path, reps: int = 300, seed: int = 702) -> list:
    emp, months = V.load_anchor()
    rng = np.random.default_rng(seed)
    win = emp > 0
    sum_w, sum_l, N = float(emp[win].sum()), float(emp[~win].sum()), len(emp)
    scales = {mu: (mu * N - sum_l) / sum_w for mu in W_MEANS}
    q_r, q_m, q_scale = q_profile(emp, months)
    t_r, t_m, t_scale = q_tail_profile(emp, months)
    h_r, h_m, h_b = h_profile(emp, months)

    def draw(n: int, kind: str, mu: float = 1.05):
        if kind == "Q":
            idx = rng.integers(0, len(q_r), size=n)
            return q_r[idx].copy(), [str(x) for x in q_m[idx]]
        if kind == "T":
            idx = rng.integers(0, len(t_r), size=n)
            return t_r[idx].copy(), [str(x) for x in t_m[idx]]
        if kind == "H":
            idx = rng.integers(0, len(h_r), size=n)
            return h_r[idx].copy(), [str(x) for x in h_m[idx]]
        idx = rng.integers(0, N, size=n)
        r = emp[idx].copy()
        mo = months[idx]
        if kind == "W":
            r = np.where(r > 0, r * scales[mu], r)
        elif kind == "M":
            w = (rng.random(n) < 0.12) & (r > 0)
            r = np.where(w, r * scales[1.05], r)
        return r, [str(x) for x in mo]

    def profile(r):
        return {"mean": float(r.mean()), "win": float((r > 0).mean()), "ge3": float((r >= 3).mean()),
                "ge10_per100": 100.0 * float((r >= 10).mean()), "avg_win": float(r[r > 0].mean()), "avg_loss": float(r[r <= 0].mean())}
    anchors = {"N": {**profile(emp), "n": int(N)}}
    for mu in W_MEANS:
        anchors[f"W{mu:.2f}"] = {**profile(np.where(emp > 0, emp * scales[mu], emp)), "scale": float(scales[mu])}
    bigm, _ = draw(200_000, "M")
    anchors["M"] = profile(bigm)
    anchors["Q"] = {**profile(q_r), "n": int(len(q_r)), "scale": q_scale}
    anchors["T"] = {**profile(t_r), "n": int(len(t_r)), "scale": t_scale}
    anchors["H"] = {**profile(h_r), "n": int(len(h_r)), "power": h_b}
    pops = [("N (every structural breakout, pp; the null)", "N", None)] + \
           [(f"W {mu:+.2f}R (winners x {scales[mu]:.2f}; win 35%)", "W", mu) for mu in W_MEANS] + \
           [("M (12% W+1.05 + 88% N)", "M", None), (f"Q (his profile: win 25%, mean +1.06; winners x {q_scale:.2f})", "Q", None),
            (f"T (his tail: win 25%, 2.9 per 100 at 10R+, mean {anchors['T']['mean']:+.2f}; winners x {t_scale:.2f})", "T", None),
            (f"H (his benchmark: win {anchors['H']['win']:.0%}, mean +1.06, 2.9 per 100 at 10R+; winners ^{h_b:.2f})", "H", None)]   # LAST: the earlier rows' draws unchanged
    rows = []
    for name, kind, mu in pops:
        for n in CAL_NS:
            vs = Counter()
            for r_i in range(reps):
                r, mo = draw(n, kind, mu or 1.05)
                s = measures([{"r_2c": float(x), "month": m} for x, m in zip(r, mo)], key=f"tgrid|{name}|{n}|{r_i}")
                vs[verdict_template(s)[0]] += 1
            rows.append({"population": name, "kind": kind, "mu": mu, "n": n, **{k: v / reps for k, v in vs.items()}})
    L = [f"CALIBRATION of the TEMPLATE bar (TEMPLATE: n >= {N_FLOOR}, interval lower end > 0, >= {TAIL_PER100:.0f} per 100 at >= 10R; "
         f"FAIL: n >= {N_FLOOR}, interval upper end < +{FAIL_MEAN_REF}R, under {TAIL_PER100:.0f} per 100 at 10R+; else CAN'T TELL); "
         f"{reps} replicates each; months = each drawn trade's REAL fill month (the block bootstrap's blocks)"]
    for k, v in anchors.items():
        L.append(f"{k} anchor: " + ", ".join(f"{a} {b:.4g}" if isinstance(b, float) else f"{a} {b}" for a, b in v.items()))
    L.append(f"{'population':58s} {'n':>5s}  {'TEMPLATE':>9s} {'FAIL':>6s} {'CANT':>6s}")
    for r in rows:
        L.append(f"{r['population']:58s} {r['n']:5d}  {r.get(TEMPLATE, 0):9.1%} {r.get('FAIL', 0):6.1%} {r.get(CANT, 0):6.1%}")
    L.append("")
    L.append("the smallest W mean that reads TEMPLATE more than 80% of the time, per n:")
    for n in CAL_NS:
        ok = [r["mu"] for r in rows if r["kind"] == "W" and r["n"] == n and r.get(TEMPLATE, 0) > 0.80]
        L.append(f"  n {n:5d}: {('+%.2fR' % min(ok)) if ok else 'none of ' + ', '.join('%+.2f' % m for m in W_MEANS)}")
    L.append("Q (his profile) reads TEMPLATE: " + ", ".join(f"n {r['n']} {r.get(TEMPLATE, 0):.0%}" for r in rows if r["kind"] == "Q"))
    L.append("T (his tail) reads TEMPLATE: " + ", ".join(f"n {r['n']} {r.get(TEMPLATE, 0):.0%}" for r in rows if r["kind"] == "T"))
    L.append("H (his benchmark, both counts) reads TEMPLATE: " + ", ".join(f"n {r['n']} {r.get(TEMPLATE, 0):.0%}" for r in rows if r["kind"] == "H"))
    L.append("N (the null) reads TEMPLATE: " + ", ".join(f"n {r['n']} {r.get(TEMPLATE, 0):.1%}" for r in rows if r["kind"] == "N")
             + "; FAIL: " + ", ".join(f"n {r['n']} {r.get('FAIL', 0):.0%}" for r in rows if r["kind"] == "N"))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(L) + "\n")
    print("\n".join(L), flush=True)
    return rows


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 10. The dry run: hand-computed cases for B / C / D, the SMA parity, the fuzz invariants
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def _bars(rows: list) -> "cb.DailyBars":
    """DailyBars from [(o, h, l, c)] dated from 2018-01-02 on (synthetic sessions)."""
    o = np.array([r[0] for r in rows], float); h = np.array([r[1] for r in rows], float)
    l = np.array([r[2] for r in rows], float); c = np.array([r[3] for r in rows], float)
    dates = [date(2018, 1, 2) + __import__("datetime").timedelta(days=i) for i in range(len(rows))]
    v = np.ones(len(rows))
    return cb.DailyBars(dates, o, h, l, c, v)


def _mins(rows: list) -> "cb.MinuteBars":
    """MinuteBars from [(minute, o, h, l, c)]."""
    return cb.minute_bars_from_lists([r[0] for r in rows], [r[1] for r in rows], [r[2] for r in rows], [r[3] for r in rows],
                                     [r[4] for r in rows], [1.0] * len(rows))


def dry_cases() -> list:
    out = []

    def chk(name, cond, detail=""):
        out.append((name, bool(cond), detail))

    def R(res):
        return float(res["realized_r"])

    def last(res):
        return res["events"][-1][1], res["events"][-1][0]

    # 0. the SMA arithmetic equals the live 20-day on random paths
    rng = np.random.default_rng(11)
    ok = True
    for _ in range(50):
        cbf = list(rng.uniform(5, 15, size=int(rng.integers(20, 60))))
        fwd = [{"c": float(x)} for x in rng.uniform(5, 15, size=int(rng.integers(1, 30)))]
        a = sma_n_at(cbf, [b["c"] for b in fwd], 20)
        b = ppr.sma_at_last(cbf, fwd)
        if a is None or b is None or abs(a - b) > 1e-12:
            ok = False
    chk("SMA20 arithmetic == ppr.sma_at_last on 50 random paths", ok)

    # the no-partial day-0 facts (no stop on day 0): hit2r False, peak 10.4 — shared by the daily cases
    d0_flat = {"stopped": False, "exit_price": None, "exit_minute": None, "peak": 10.4, "hit2r": False, "partial_price": None, "partial_minute": None}
    cb20 = [10.0] * 20                        # SMA20 before = 10.0
    fill, stop = 10.0, 9.0                    # risk 1; target 12; cut level 11

    # 1. B: a watch at session 3, RECLAIMED at session 4 (forgiven); a fresh watch at 6, no reclaim by 8 -> sold at the open of 9
    path = [(10.2, 11.5, 10.1, 11.0), (11.0, 11.4, 10.8, 11.2), (11.0, 11.2, 9.9, 9.95), (10.0, 10.6, 9.9, 10.5),
            (10.4, 10.9, 10.3, 10.8), (10.7, 10.8, 9.8, 9.9), (9.9, 10.1, 9.6, 9.7), (9.7, 10.0, 9.5, 9.6),
            (9.65, 10.0, 9.5, 9.8), (9.8, 10.0, 9.6, 9.9)]
    resB = step_rule("B", fill=fill, stop=stop, d0=d0_flat, closes_before=cb20, fwd=_bars(path), adr20=0.03)
    kinds = [e[1] for e in resB["events"]]
    chk("B reclaim forgiven: watch at 3, reclaim at 4, watch at 6, expiry at 8 -> trail at the open of 9 (-0.350R)",
        resB["status"] == "trailed" and last(resB) == ("trail", 9) and abs(R(resB) + 0.35) < 1e-9
        and kinds == ["watch", "reclaim", "watch", "trail"] and resB["sessions_held"] == 9, f"{resB}")
    resC = step_rule("C", fill=fill, stop=stop, d0=d0_flat, closes_before=cb20, fwd=_bars(path), adr20=0.03)
    chk("C (slow, 20-day) on the same path: the first close under at 3 -> sold at the open of 4 (0.000R)",
        resC["status"] == "trailed" and last(resC) == ("trail", 4) and abs(R(resC)) < 1e-9 and resC["events"][0] == (0, "trail_n", 20.0, 0.0), f"{resC}")
    resD = step_rule("D", fill=fill, stop=stop, d0=d0_flat, closes_before=cb20, fwd=_bars(path), adr20=0.03)
    chk("D on the same path: session 3 closes under the fill (no third) and under the 20-day -> everything at the open of 4 (0.000R)",
        resD["status"] == "trailed" and last(resD) == ("trail", 4) and abs(R(resD)) < 1e-9 and "partial" not in [e[1] for e in resD["events"]], f"{resD}")
    # 1b. B NOT reclaimed: closes under at 3, 4 and 5 -> sold at the open of 6
    path2 = [(10.2, 11.5, 10.1, 11.0), (11.0, 11.4, 10.8, 11.2), (11.0, 11.2, 9.9, 9.95), (10.0, 10.3, 9.9, 10.1),
             (10.1, 10.3, 9.9, 10.1), (10.7, 10.8, 10.2, 10.6), (10.6, 10.7, 10.3, 10.5)]
    resB2 = step_rule("B", fill=fill, stop=stop, d0=d0_flat, closes_before=cb20, fwd=_bars(path2), adr20=0.03)
    chk("B not reclaimed: under at 3, 4 (10.1 < 10.1125), 5 (10.1 < 10.1175) -> sold at the open of 6 (+0.700R)",
        resB2["status"] == "trailed" and last(resB2) == ("trail", 6) and abs(R(resB2) - 0.7) < 1e-9
        and [e[1] for e in resB2["events"]] == ["watch", "trail"], f"{resB2}")
    # 1c. B: the stop fires inside the watch window
    path3 = [(10.2, 11.5, 10.1, 11.0), (11.0, 11.4, 10.8, 11.2), (11.0, 11.2, 9.9, 9.95), (9.9, 10.0, 8.9, 9.0)]
    resB3 = step_rule("B", fill=fill, stop=stop, d0=d0_flat, closes_before=cb20, fwd=_bars(path3), adr20=0.03)
    chk("B: the stop keeps running inside the watch window -> stopped at session 4 (-1.000R)",
        resB3["status"] == "stopped" and last(resB3) == ("stop", 4) and abs(R(resB3) + 1.0) < 1e-9, f"{resB3}")

    # 2. C: the speed switch — ADR20 4.79% exactly -> 20-day; 4.80% -> 10-day; a close under the 10-day but above the 20-day
    cb_mix = [9.0] * 10 + [11.0] * 10         # SMA20 before 10.0, SMA10 before 11.0
    f2, s2 = 10.5, 9.5                        # target 12.5, cut 11.5
    path4 = [(10.6, 11.6, 10.5, 11.3), (11.2, 11.5, 11.0, 11.2), (11.1, 11.3, 10.6, 10.7), (10.8, 11.0, 10.7, 10.9),
             (10.9, 11.0, 9.4, 9.5), (9.6, 9.8, 9.4, 9.6)]
    d0b = dict(d0_flat, peak=10.9)
    res_fast = step_rule("C", fill=f2, stop=s2, d0=d0b, closes_before=cb_mix, fwd=_bars(path4), adr20=0.0480)
    res_slow = step_rule("C", fill=f2, stop=s2, d0=d0b, closes_before=cb_mix, fwd=_bars(path4), adr20=0.0479)
    chk("C fast (ADR 4.80% > cut): the 10-day; session 3 closes 10.7 < 11.02 -> sold at the open of 4 (+0.300R)",
        res_fast["events"][0] == (0, "trail_n", 10.0, 0.0) and res_fast["status"] == "trailed" and last(res_fast) == ("trail", 4)
        and abs(R(res_fast) - 0.3) < 1e-9, f"{res_fast}")
    chk("C slow (ADR 4.79%, not above the cut): the 20-day; 10.7 >= 10.31 holds; stopped at session 5 (-1.000R)",
        res_slow["events"][0] == (0, "trail_n", 20.0, 0.0) and res_slow["status"] == "stopped" and last(res_slow) == ("stop", 5)
        and abs(R(res_slow) + 1.0) < 1e-9, f"{res_slow}")
    chk("C's cut is the live constant (cb.TRAIL_SPEED_ADR_CUT == 0.0479) and the averages the live 10 / 20",
        abs(cb.TRAIL_SPEED_ADR_CUT - 0.0479) < 1e-12 and cb.SMA_SHORT == 10 and cb.SMA_MID == 20)

    # 3. D: the third at the first close of session 3 / 4 / 5 above the fill
    cb96 = [9.6] * 20
    path5 = [(10.1, 11.2, 10.0, 10.8), (10.8, 11.0, 10.5, 10.9), (10.9, 11.0, 9.9, 9.95), (10.0, 10.7, 9.9, 10.6),
             (10.5, 10.7, 9.95, 10.4), (10.4, 10.6, 10.2, 10.5)]
    resD5 = step_rule("D", fill=fill, stop=stop, d0=d0_flat, closes_before=cb96, fwd=_bars(path5), adr20=0.03)
    ev = resD5["events"]
    chk("D: session 3 closes under the fill, session 4 above -> the third at 4's close (10.6), the stop to 10 from 5, stopped at 5 (+0.200R)",
        resD5["status"] == "stopped" and (4, "partial", 10.6, ppr.PARTIAL_FRAC) in ev and (4, "stop_to", 10.0, 0.0) in ev
        and last(resD5) == ("stop", 5) and abs(R(resD5) - 0.2) < 1e-9, f"{resD5}")
    path6 = [(10.1, 11.2, 10.0, 10.8), (10.8, 11.0, 10.5, 10.9), (10.9, 11.0, 9.9, 9.95), (10.0, 10.3, 9.9, 9.9),
             (9.9, 10.2, 9.8, 9.95), (10.0, 11.0, 9.9, 10.9), (10.9, 11.0, 8.9, 9.1)]
    resD6 = step_rule("D", fill=fill, stop=stop, d0=d0_flat, closes_before=cb96, fwd=_bars(path6), adr20=0.03)
    chk("D: none of sessions 3 / 4 / 5 closes above the fill -> no third ever (6 is outside the window); stopped at 7 at the day-low stop (-1.000R)",
        resD6["status"] == "stopped" and "partial" not in [e[1] for e in resD6["events"]] and last(resD6) == ("stop", 7)
        and abs(R(resD6) + 1.0) < 1e-9, f"{resD6}")
    path7 = [(10.1, 11.2, 10.0, 10.8), (10.8, 11.0, 10.5, 10.9), (10.9, 11.0, 10.4, 10.5), (10.5, 10.8, 10.3, 10.7),
             (10.7, 10.9, 10.4, 10.8), (10.8, 10.9, 9.9, 10.0)]
    resD7 = step_rule("D", fill=fill, stop=stop, d0=d0_flat, closes_before=cb96, fwd=_bars(path7), adr20=0.03)
    chk("D: session 3 closes above the fill -> the third at 3's close (10.5); one third only (4 and 5 take none); stopped at cost at 6 (+0.167R)",
        (3, "partial", 10.5, ppr.PARTIAL_FRAC) in resD7["events"] and sum(1 for e in resD7["events"] if e[1] == "partial") == 1
        and last(resD7) == ("stop", 6) and abs(R(resD7) - 0.5 / 3) < 1e-9, f"{resD7}")
    path8 = [(10.1, 11.2, 10.0, 10.8), (10.8, 11.0, 10.5, 10.9), (10.9, 11.0, 9.9, 9.95), (10.0, 10.3, 9.9, 9.9),
             (9.9, 10.8, 9.8, 10.7), (10.6, 10.8, 9.9, 10.0)]
    resD8 = step_rule("D", fill=fill, stop=stop, d0=d0_flat, closes_before=cb96, fwd=_bars(path8), adr20=0.03)
    chk("D: sessions 3 and 4 close under the fill, session 5 above -> the third at 5's close (10.7), the stop to 10 from 6, stopped at cost at 6 (+0.233R)",
        resD8["status"] == "stopped" and (5, "partial", 10.7, ppr.PARTIAL_FRAC) in resD8["events"] and (5, "stop_to", 10.0, 0.0) in resD8["events"]
        and sum(1 for e in resD8["events"] if e[1] == "partial") == 1 and last(resD8) == ("stop", 6)
        and abs(R(resD8) - 0.7 / 3) < 1e-9, f"{resD8}")
    # 3b. D vs A on a path with no +2R touch and session 3 at or under the fill: identical (D = A minus the +2R leg)
    d0pp = {"v": 1, "stopped": False, "peak": 10.4, "exit_price": None, "exit_minute": None, "partial_price": None, "partial_minute": None, "stop_in_force": None}
    resA6 = V.exit_one(fill=fill, stop=stop, day0=d0pp, closes_before=cb96, fwd=_bars(path6), adr20=0.03)
    chk("D == A (the live pp) on a path with no +2R touch and sessions 3-5 at or under the fill", V.events_equal(resD6["events"], resA6["events"])
        and resD6["status"] == resA6["status"], f"{resD6['events']} vs {resA6['events']}")

    # 4. same-bar ties under P0: a bar touching both the stop and +2R books the STOP; a gap open above +2R then the stop -> -1R (A: +0.2R)
    path8 = [(10.5, 12.5, 8.9, 9.2), (9.2, 9.5, 9.0, 9.3)]
    resB8 = step_rule("B", fill=fill, stop=stop, d0=d0_flat, closes_before=cb20, fwd=_bars(path8), adr20=0.03)
    chk("P0 tie: session 1 touches +2R and the stop -> the stop (-1.000R), no reach event",
        resB8["status"] == "stopped" and abs(R(resB8) + 1.0) < 1e-9 and [e[1] for e in resB8["events"]] == ["stop"], f"{resB8}")
    path9 = [(12.6, 12.8, 8.9, 9.0), (9.0, 9.5, 8.8, 9.0)]
    resB9 = step_rule("B", fill=fill, stop=stop, d0=d0_flat, closes_before=cb20, fwd=_bars(path9), adr20=0.03)
    resA9 = V.exit_one(fill=fill, stop=stop, day0=d0pp, closes_before=cb20, fwd=_bars(path9), adr20=0.03)
    chk("P0 gap open above +2R, then the stop in the same bar: +2R reached (breakeven from the NEXT session), stopped at 9 (-1.000R); A takes the third at the open then the stop (+0.200R)",
        resB9["status"] == "stopped" and abs(R(resB9) + 1.0) < 1e-9 and [e[1] for e in resB9["events"]] == ["reach_2r", "stop"]
        and abs(R(resA9) - 0.2) < 1e-9, f"{resB9} / {resA9}")
    # 4b. +2R reached at session 1 (no stop) -> breakeven from session 2: a session-2 low at the fill stops at cost
    path10 = [(10.5, 12.1, 10.4, 11.9), (11.8, 12.0, 9.99, 11.0)]
    resB10 = step_rule("B", fill=fill, stop=stop, d0=d0_flat, closes_before=cb20, fwd=_bars(path10), adr20=0.03)
    chk("P0: +2R reached at session 1 -> the stop at the fill from session 2; stopped at cost at 2 (0.000R)",
        resB10["status"] == "stopped" and abs(R(resB10)) < 1e-9 and (1, "stop_to", 10.0, 0.0) in resB10["events"] and last(resB10) == ("stop", 2), f"{resB10}")

    # 5. the stall cut under P0: no high at +1R by session 3's close -> everything at that close
    path11 = [(10.1, 10.5, 9.9, 10.2), (10.2, 10.6, 10.0, 10.3), (10.3, 10.9, 10.1, 10.4), (10.4, 11.5, 10.3, 11.2)]
    resC11 = step_rule("C", fill=fill, stop=stop, d0=d0_flat, closes_before=cb20, fwd=_bars(path11), adr20=0.03)
    chk("P0 stall cut: no high at 11 by session 3 -> cut at 3's close 10.4 (+0.400R)", resC11["status"] == "time_exit"
        and last(resC11) == ("cut", 3) and abs(R(resC11) - 0.4) < 1e-9, f"{resC11}")
    d0r = dict(d0_flat, peak=11.0)
    resC11b = step_rule("C", fill=fill, stop=stop, d0=d0r, closes_before=cb20, fwd=_bars(path11), adr20=0.03)
    chk("P0 stall cut: +1R reached on day 0 (peak 11.0) -> no cut; the trail then holds (censored at the path's end = degraded here)",
        resC11b["status"] == "degraded", f"{resC11b}")

    # 6. day 0 under A vs the no-partial walk: the +2R touch after the fill
    mins = [(m, 10.0, 10.05, 9.95, 10.0) for m in range(0, 10)] + [(10, 10.0, 10.1, 9.98, 10.05)] + \
           [(m, 10.0 + 0.5 * (m - 10), 10.1 + 0.5 * (m - 10), 9.95 + 0.5 * (m - 10), 10.05 + 0.5 * (m - 10)) for m in range(11, 15)] + \
           [(15, 12.0, 12.1, 11.9, 12.0)] + [(m, 11.0, 11.1, 10.5, 10.8) for m in range(16, 20)] + [(20, 10.3, 10.4, 9.8, 9.9)] + \
           [(m, 9.9, 10.0, 9.85, 9.9) for m in range(21, 30)]
    mb = _mins(mins)
    d0a = ppr.day0_facts([(m, o, h, l) for m, o, h, l, _c in mins], fill=10.0, stop=9.0, fill_minute=10)
    d0n = day0_no_partial(mb, fill=10.0, stop=9.0, fill_minute=10)
    chk("A's day 0: the third at 12.0 (minute 14, high 12.1 >= 12), the breakeven stop then hit at minute 20 -> stopped",
        d0a["partial_price"] == 12.0 and d0a["partial_minute"] == 14 and d0a["stopped"] and d0a["exit_price"] == 10.0 and d0a["exit_minute"] == 20, f"{d0a}")
    chk("the no-partial day 0: not stopped (the low 9.8 is above 9.0), +2R reached (hit2r), peak 12.1",
        not d0n["stopped"] and d0n["hit2r"] and abs(d0n["peak"] - 12.1) < 1e-9, f"{d0n}")
    resA0 = V.exit_one(fill=10.0, stop=9.0, day0=d0a, closes_before=cb20, fwd=_bars(path10), adr20=0.03)
    pathg = [(9.9, 10.2, 9.7, 10.1), (10.1, 10.3, 10.0, 10.2)]
    resB0 = exit_rule("B", fill=10.0, stop=9.0, d0_pp=d0a, d0_np=d0n, closes_before=cb20, fwd=_bars(pathg), adr20=0.03)
    chk("A books day 0: +0.667R (a third at +2R, the rest at cost); B on the same day 0 rests the breakeven from session 1 and is gapped out at 9.9 (-0.100R)",
        resA0["status"] == "stopped_day0" and abs(R(resA0) - 2.0 / 3) < 1e-9 and resB0["status"] == "stopped"
        and last(resB0) == ("stop_gap", 1) and abs(R(resB0) + 0.1) < 1e-9 and (0, "stop_to", 10.0, 0.0) in resB0["events"], f"{resA0} / {resB0}")
    # 6b. a day-0 stop under the stop-only walk is booked by the live day0_result_to_outcome
    mins2 = [(m, 10.0, 10.05, 9.95, 10.0) for m in range(0, 11)] + [(11, 9.95, 10.0, 8.95, 9.0)] + [(m, 9.0, 9.1, 8.9, 9.0) for m in range(12, 20)]
    d0n2 = day0_no_partial(_mins(mins2), fill=10.0, stop=9.0, fill_minute=10)
    resB02 = exit_rule("B", fill=10.0, stop=9.0, d0_pp=None, d0_np=d0n2, closes_before=cb20, fwd=_bars(pathg), adr20=0.03)
    chk("a day-0 stop under the no-partial walk: stopped_day0 at 9.0 (-1.000R), minute 11", resB02["status"] == "stopped_day0"
        and abs(R(resB02) + 1.0) < 1e-9 and d0n2["exit_minute"] == 11 and resB02["events"] == [(0, "day0_stop", 9.0, 1.0)], f"{resB02}")

    # 7. the free point and the legs read the new events (the book's inputs)
    rec = {"fill": 10.0, "stop": 9.0, "E": "2018-01-01", "raw_factor": 1.0, "after_cutoff": False}
    date_at = lambda j: date(2018, 1, 1) + __import__("datetime").timedelta(days=j)
    book_fields(rec, resB, fwd=_bars(path), d0=d0_flat, fm=10, date_at=date_at, ed=date(2018, 1, 1))
    chk("book fields on B's trail sale: freed at the open of session 9 (exit_at_open), one leg at 2c, R -0.350 -> -0.390 at 2c",
        rec["free_date"] == "2018-01-10" and rec["exit_at_open"] and len(rec["legs"]) == 1 and abs(rec["r_2c"] + 0.39) < 1e-9
        and rec["decisive"] and rec["mature"], f"{rec}")

    # 8. the verdict words
    chk("verdict: lower end > 0 and 2.0 per 100 at 10R+ -> TEMPLATE", verdict_template({"n": 500, "ci_lo": 0.01, "ci_hi": 0.5, "ge10_per100": 2.0})[0] == TEMPLATE)
    chk("verdict: upper end < +0.25 and 1.9 per 100 -> FAIL", verdict_template({"n": 500, "ci_lo": -0.5, "ci_hi": 0.2, "ge10_per100": 1.9})[0] == "FAIL")
    chk("verdict: tail present, lower end <= 0 -> CAN'T TELL (tail present)", verdict_template({"n": 500, "ci_lo": -0.1, "ci_hi": 0.5, "ge10_per100": 3.0})[1].startswith("tail present"))
    chk("verdict: n 99 -> CAN'T TELL (n)", verdict_template({"n": 99, "ci_lo": 0.5, "ci_hi": 0.9, "ge10_per100": 5.0})[1].startswith("n ="))
    chk("pick: within 0.02R the higher 10R+ wins; beyond it the mean wins; A first on a full tie",
        pick({"A": {"n": 500, "mean_r": 0.10, "ge10_per100": 1.0}, "B": {"n": 500, "mean_r": 0.11, "ge10_per100": 2.0}}, ["A", "B"]) == "B"
        and pick({"A": {"n": 500, "mean_r": 0.10, "ge10_per100": 3.0}, "B": {"n": 500, "mean_r": 0.15, "ge10_per100": 1.0}}, ["A", "B"]) == "B"
        and pick({"A": {"n": 500, "mean_r": 0.10, "ge10_per100": 2.0}, "B": {"n": 500, "mean_r": 0.10, "ge10_per100": 2.0}}, ["A", "B"]) == "A")
    chk("the floor reads the planned width at the placement tick (raw cents): 14.9c refused, 15.0c kept; a placed row without one is a defect",
        width_cents({"key": "k", "width_raw_cents": 14.9}, None) < FLOOR_CENTS
        and width_cents({"key": "k", "width_raw_cents": 15.0}, None) >= FLOOR_CENTS - 1e-9)
    try:
        width_cents({"key": "k"}, None)
        chk("a placed row without a placement width raises", False)
    except ValueError:
        chk("a placed row without a placement width raises", True)
    return out


def fuzz(n: int = 400, seed: int = 1101, survive: bool = False) -> dict:
    """Random day-0 + daily paths through every rule: the invariants (status vocabulary; the fractions sold sum to 1 on a
    terminal exit; R equals the events' own arithmetic; D == A where neither takes a third; B == C(20-day) when C's exit
    is not a trail sale; C(ADR <= cut) == a 20-day X1 walk). `survive`: the day-0 path is redrawn (calmer minutes) until
    NEITHER day-0 walk stops out, so every path reaches the daily rules (the review's 11-01 point: most unbiased paths die
    on day 0 and make D == A trivial); D's third is tallied by session."""
    rng = np.random.default_rng(seed)
    kinds = Counter()
    for _ in range(n):
        fill, stop = 20.0, 20.0 * (1 - rng.uniform(0.02, 0.08))
        fm = int(rng.integers(5, 300))
        for _try in range(200 if survive else 1):
            mins = []
            p = fill
            sd_o, sd_hl = (0.0008, 0.002) if survive else (0.003, 0.01)
            for m in range(0, 390):
                o = p * (1 + rng.normal(0, sd_o)); h = o * (1 + abs(rng.normal(0, sd_hl))); l = o * (1 - abs(rng.normal(0, sd_hl)))
                c = float(rng.uniform(l, h)); mins.append((m, o, h, l, c)); p = c
            mb = _mins(mins)
            d0a = ppr.day0_facts([(m, o, h, l) for m, o, h, l, _c in mins], fill=fill, stop=stop, fill_minute=fm)
            d0n = day0_no_partial(mb, fill=fill, stop=stop, fill_minute=fm)
            if not survive or (not d0n["stopped"] and not d0a["stopped"]):
                break
        if survive and (d0n["stopped"] or d0a["stopped"]):
            kinds["survive_redraw_exhausted"] += 1
            continue
        cbf = list(p * (1 + rng.normal(0, 0.01, size=40)).cumprod() * 0.0 + rng.uniform(15, 25, size=40))
        nfwd = int(rng.integers(1, 130))
        rows = []
        q = float(mins[-1][4])
        for _j in range(nfwd):
            o = q * (1 + rng.normal(0, 0.02)); h = o * (1 + abs(rng.normal(0, 0.03))); l = o * (1 - abs(rng.normal(0, 0.03)))
            c = float(rng.uniform(l, h)); rows.append((o, h, l, c)); q = c
        fwd = _bars(rows)
        adr = float(rng.choice([0.03, 0.06]))
        res = {}
        for r in EXITS:
            res[r] = exit_rule(r, fill=fill, stop=stop, d0_pp=d0a, d0_np=d0n, closes_before=cbf, fwd=fwd, adr20=adr)
            assert res[r]["status"] in ("stopped", "stopped_day0", "trailed", "time_exit", "censored", "degraded"), res[r]
            sold = sum(e[3] for e in res[r]["events"] if e[3] > 0)
            assert abs(sold - 1.0) < 1e-9, (r, res[r])
            pnl = sum((e[2] - fill) * e[3] for e in res[r]["events"] if e[3] > 0 and e[1] not in ("stop_to", "be_above_close"))
            assert abs(pnl / (fill - stop) - res[r]["realized_r"]) < 1e-9, (r, res[r])
            kinds[(r, res[r]["status"])] += 1
        for e in res["D"]["events"]:
            if e[1] == "partial":
                kinds[f"D_third_s{e[0]}"] += 1
        # D == A when A never takes a third (no +2R touch on day 0 or later before the exit, session 3 at or under the fill)
        if not any(e[1] in ("partial", "partial_r") for e in res["A"]["events"]) and not any(e[1] == "partial" for e in res["D"]["events"]):
            assert V.events_equal(res["A"]["events"], res["D"]["events"]), (res["A"], res["D"])
            kinds["D==A"] += 1
        # B == C(20) when C did not sell on the trail (the watch never had to decide) and the ADR picks the 20-day
        if adr <= cb.TRAIL_SPEED_ADR_CUT and res["C"]["status"] != "trailed" and not any(e[1] == "trail" for e in res["C"]["events"]):
            ev_c = [e for e in res["C"]["events"] if e[1] != "trail_n"]
            ev_b = [e for e in res["B"]["events"] if e[1] not in ("watch", "reclaim")]
            assert V.events_equal(ev_b, ev_c) and res["B"]["status"] == res["C"]["status"], (res["B"], res["C"])
            kinds["B==C20"] += 1
    return dict(kinds)


def run_dryrun() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    L = []
    cases = dry_cases()
    for name, ok, detail in cases:
        L.append(f"[{'ok' if ok else 'FAIL'}] {name}" + ("" if ok else f"\n      {detail}"))
    kinds = fuzz()
    L.append(f"[ok] fuzz: 400 random day-0 + daily paths through A / B / C / D — statuses in the vocabulary, every share sold once, "
             f"R == the events' arithmetic; D == A on {kinds.get('D==A', 0)} paths where neither takes a third; "
             f"B == C(20-day) on {kinds.get('B==C20', 0)} paths where C's exit is not a trail sale; "
             f"{ {k: v for k, v in kinds.items() if isinstance(k, tuple)} }")
    kinds2 = fuzz(400, seed=1102, survive=True)
    n_surv = 400 - kinds2.get("survive_redraw_exhausted", 0)
    L.append(f"[ok] fuzz, day-0 survivors: {n_surv} of 400 paths that neither day-0 walk stops out — the same invariants; "
             f"D == A on {kinds2.get('D==A', 0)} paths where neither takes a third; B == C(20-day) on {kinds2.get('B==C20', 0)}; "
             f"D's third at session 3 / 4 / 5 on {kinds2.get('D_third_s3', 0)} / {kinds2.get('D_third_s4', 0)} / {kinds2.get('D_third_s5', 0)} paths; "
             f"{ {k: v for k, v in kinds2.items() if isinstance(k, tuple)} }")
    if n_surv < 300:
        cases.append(("fuzz day-0 survivors: at least 300 of 400 paths survive day 0", False, f"{n_surv}"))
    calibration(OUT / "calibration.txt")
    L.append(f"[ok] calibration written: {OUT / 'calibration.txt'}")
    n_fail = sum(1 for _n, ok, _d in cases if not ok)
    L.append(f"DRY RUN {'COMPLETE' if not n_fail else 'FAILED'}: {len(cases)} hand-computed cases, {n_fail} failed")
    txt = "\n".join(L) + "\n"
    (OUT / "dryrun.txt").write_text(txt)
    print(txt, flush=True)
    return {"cases": len(cases), "failed": n_fail, "fuzz": kinds}


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 11. Parity (the re-walk of A on the real fills; the nesting of the 90-list)
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def run_parity() -> dict:
    """(1) The A exit re-walked on every frozen fill through THIS module's loader + V.exit_one equals the frozen events,
    R, free point and decisive flag (the proof that B / C / D are fed the baseline's bars); (2) the frozen book reproduced
    from the re-walked A rows (`apply_book` imported) on every placed row; (3) the nesting of the 90-list if present."""
    OUT.mkdir(parents=True, exist_ok=True)
    L = []
    rows = load_frozen()
    stores = Stores()
    index = minute_index()
    recs = rewalk_frozen(rows, stores, index, rules=("A",), assert_a=True, log=lambda s: (L.append(s), print(s, flush=True)))
    placed = [t for t in rows if t["placed_m"] is not None]
    sessions = sorted({t["E"] for t in rows})
    rows_a = book_rows(placed, recs["A"])
    adm = run_book(rows_a, sessions, V.CAP_SLOTS)
    diff = [t["key"] for t in placed if str(adm["admitted"].get(t["key"])) != str(t["adm_cap"])]
    L.append(f"book parity: the capped book re-run on the re-walked A rows differs from the frozen adm_cap on {len(diff)} of {len(placed):,} placed rows; "
             f"blocked {dict(adm['blocked'])} (frozen: max_positions 11,808 / ticker_open_position 1,260)")
    for era, want in ((ERA_A, (1058, -0.153)), (ERA_B, (581, -0.412))):
        pop = scored(rows_a, adm, era)
        s = measures(pop, key=f"tgrid|parity|{era}")
        L.append(f"book parity {era}: " + fmt("A re-walked, capped, 2c", s) + f"   (frozen n {want[0]} mean {want[1]:+.3f})")
        if s["n"] != want[0] or abs(s["mean_r"] - want[1]) > 0.0015:
            diff.append(f"era {era}")
    # the placement width (step 2's floor) read by the walk for a new name == the follow-up's on frozen rows: a sample of
    # 300 placed rows (filled, cancelled and re-priced ones among them), 0 differences required
    tick = load_tick()
    rng = np.random.default_rng(1101)
    sample = [placed[i] for i in rng.choice(len(placed), size=300, replace=False)]
    n_w_bad = 0
    by_e = defaultdict(list)
    for t in sample:
        by_e[t["E"]].append(t)
    for e, names in by_e.items():
        blocks = minute_blocks(index, e, [t["ticker"] for t in names])
        for t in names:
            mb, state = blocks.get(t["ticker"], (None, "pending"))
            w = placement_width_cents(V.minutes_to_dict(mb), int(t["placed_m"]), list_level=t["list_level"], adr20=t["adr20"],
                                      vol_bar=t["vol_bar"], raw_factor=t["raw_factor"])
            if abs(w - float(tick[t["key"]]["width_raw_cents"])) > 1e-6:
                n_w_bad += 1
    L.append(f"width parity: the walk's placement width == the follow-up's `width_raw_cents` on {300 - n_w_bad} of 300 sampled placed rows "
             f"({sum(1 for t in sample if t['filled'])} filled, {sum(1 for t in sample if not t['filled'])} cancelled)")
    if n_w_bad:
        diff.append(f"width parity: {n_w_bad} rows differ")
    if diff:
        L.append("PARITY FAILED: " + ", ".join(diff[:10]))
    else:
        L.append("PARITY COMPLETE: the A exit, the capped book and the placement width reproduce the frozen replay / follow-up on every row")
    if (LIST90 / "list_eraA.tsv.gz").exists() and (LIST90 / "list_eraB.tsv.gz").exists():
        probs = nesting_parity(log=lambda s: (L.append(s), print(s, flush=True)))
        if probs:
            L.append("NESTING FAILED: " + "; ".join(probs))
            diff.extend(probs)
        else:
            L.append("NESTING COMPLETE: the 90-list holds the frozen 98-list row for row")
    (OUT / "parity.txt").write_text("\n".join(L) + "\n")
    print("\n".join(L[-6:]), flush=True)
    return {"bad": diff}


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 12. The walk — once, after the freeze and the pull
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def run_walk(force: bool = False, limit_days: Optional[int] = None, smoke_from: Optional[str] = None) -> dict:
    """The registered run. `force` + `limit_days` = a SMOKE on the first N breakout days only: the code paths are
    exercised on real bars but NO R is printed or written — the tally (counts, statuses, exclusions, the cells' n) goes
    to scratch, the row shapes without any R column beside it (the baseline's smoke convention)."""
    smoke = bool(force and limit_days)
    if not force:
        probs = freeze_problems()
        if probs:
            raise SystemExit("REFUSED — the freeze does not hold:\n  " + "\n  ".join(probs))
        probs, cov = coverage_problems()
        if probs:
            raise SystemExit("REFUSED — the pull does not cover the pinned request:\n  " + "\n  ".join(probs))
        for name in ("results.txt", "cells.json", "trades_grid.tsv.gz"):
            if (OUT / name).exists():
                raise SystemExit(f"REFUSED — {OUT / name} exists: the walk runs once")
    else:
        cov = V.coverage(minute_index(), read_request(), failed=set())
    L = []

    def log(s=""):
        if smoke and not re.match(r"^(TEMPLATE GRID|  re-walk|  new-name day|new names walked|STEP|recall parity|JUDGED|-- |$)", str(s)):
            return                                   # a smoke prints no outcome: only the progress and the step headers
        L.append(str(s)); print(s, flush=True)

    log(f"TEMPLATE GRID — written {date.today().isoformat()} (registration {DOC.name}); the walk runs once" + (" [SMOKE]" if smoke else ""))
    rows = load_frozen()
    tick = load_tick()
    stores = Stores()
    index = minute_index()
    cutoff = V.e_cutoff(stores.get("B"))
    sessions = sorted({t["E"] for t in rows})
    if smoke:
        days = [d for d in sessions if d >= smoke_from] if smoke_from else sessions
        keep_days = set(days[:int(limit_days)])
        rows = [t for t in rows if t["E"] in keep_days]
    placed = [t for t in rows if t["placed_m"] is not None]
    recs = rewalk_frozen(rows, stores, index, rules=EXITS, assert_a=True, log=log)
    real, refused = load_winners()
    # the big-winners study's funnel on the 872 real big breakouts, reproduced under today's exit, no floor, 98, 5 slots
    rows_a = book_rows(placed, recs["A"])
    w0 = winner_recall(real, V.read_list(V.OUT), recs["A"], run_book(rows_a, sessions, V.CAP_SLOTS), run_book(rows_a, sessions, None))
    log(f"recall parity (today's exit, 98, 5 slots): real big breakouts listed {w0.get('listed')} / filled {w0.get('filled')} / took a slot {w0.get('slot')} "
        f"(the study: 380 / 231 / 63)" + (" [smoke: a few days, not comparable]" if smoke else ""))
    if (w0.get("listed"), w0.get("filled"), w0.get("slot")) != (380, 231, 63) and not smoke:
        raise SystemExit("REFUSED — the recall funnel does not reproduce the big-winners study at 98 under today's exit")
    cells: dict = {}

    def cell(name: str, rule: str, *, floor: bool, rs_min: float, slots: Optional[int], new: Optional[dict], with_verdict_era=None):
        rows_c = book_rows(placed, recs[rule], new[rule] if new else None, floor=floor, tick=tick, rs_min=rs_min)
        adm = run_book(rows_c, sessions, slots)
        adm_g = run_book(rows_c, sessions, None)
        out = {"name": name, "rule": rule, "floor": floor, "rs_min": rs_min, "slots": slots, "placed_rows": len(rows_c),
               "blocked": dict(adm["blocked"]), "blocked_guard": dict(adm_g["blocked"])}
        for era in (ERA_A, ERA_B, None):
            tag = era or "all"
            pop = scored(rows_c, adm, era)
            s = measures(pop, key=f"tgrid|{name}|cap|{tag}")
            out[f"cap_{tag}"] = s
            pop_g = scored(rows_c, adm_g, era)
            out[f"guard_{tag}"] = measures(pop_g, key=f"tgrid|{name}|guard|{tag}")
        out["admitted_fills"] = sum(1 for t in rows_c if adm["admitted"].get(t["key"]) and t["filled"])
        cells[name] = out
        return out, adm, adm_g, rows_c

    def show(out: dict, era: str, verdict: bool):
        if smoke:
            return
        log(fmt(f"{out['name']} capped 5-slot book, 2c, {era}" if out["slots"] == 5 else f"{out['name']} capped {out['slots']}-slot book, 2c, {era}",
                out[f"cap_{era}"], with_verdict=verdict))
        log(fmt(f"  beside: no slot limit (guard only), 2c, {era}", out[f"guard_{era}"]))

    # ── STEP 1: the exits on today's list, entry, floor-less, 5 slots ──
    log(""); log("STEP 1 — EXITS (today's list and entry, no floor, 5 slots). Pick on 2017-21 by the pick rule; judged once on 2022-24.")
    log(bench_line())
    s1 = {}
    for r in EXITS:
        s1[r], _adm, _g, _rows = cell(f"step1_{r}", r, floor=False, rs_min=98.0, slots=5, new=None)
    for r in EXITS:
        show(s1[r], ERA_A, verdict=False)
        pd_ = paired_diff(recs[r], recs["A"], ERA_A, key=f"tgrid|paired|{r}|{ERA_A}")
        if r != "A" and pd_.get("n"):
            log(f"  paired X - A on the same uncapped decisive trades, 2017-21: n {pd_['n']:,} mean {pd_['mean']:+.3f} [{pd_['lo']:+.2f}, {pd_['hi']:+.2f}]"
                f" -> {'beyond noise' if pd_['beyond_noise'] else 'not beyond noise'}")
            s1[r]["paired_A_2017_21"] = pd_
    pick1 = pick({r: s1[r][f"cap_{ERA_A}"] for r in EXITS}, list(EXITS))
    log(f"-> STEP 1 PICK on 2017-21: {pick1} ({EXIT_WORDS[pick1]})")
    log(f"JUDGED on 2022-24 (the pick; the other exits beside, deciding nothing):")
    for r in EXITS:
        show(s1[r], ERA_B, verdict=(r == pick1))
        pd_ = paired_diff(recs[r], recs["A"], ERA_B, key=f"tgrid|paired|{r}|{ERA_B}")
        if r != "A" and pd_.get("n"):
            log(f"  paired X - A, 2022-24: n {pd_['n']:,} mean {pd_['mean']:+.3f} [{pd_['lo']:+.2f}, {pd_['hi']:+.2f}]"
                f" -> {'beyond noise' if pd_['beyond_noise'] else 'not beyond noise'}")
            s1[r]["paired_A_2022_24"] = pd_
    # ── STEP 2: the 15c floor on the pick ──
    log(""); log(f"STEP 2 — the 15-cent MINIMUM STOP on top of {pick1} (re-confirmed, not re-selected; carried forward regardless).")
    s2, _adm2, _g2, _rows2 = cell(f"step2_{pick1}_floor15", pick1, floor=True, rs_min=98.0, slots=5, new=None)
    for era in (ERA_A, ERA_B):
        show(s1[pick1], era, verdict=False)
        show(s2, era, verdict=(era == ERA_B))
        a, b = s2[f"cap_{era}"].get("mean_r"), s1[pick1][f"cap_{era}"].get("mean_r")
        if a is None or b is None:
            log(f"  the floor's effect, {era}: no decisive trades on one side (n {s2[f'cap_{era}'].get('n', 0)} vs {s1[pick1][f'cap_{era}'].get('n', 0)})")
            continue
        d = a - b
        log(f"  the floor's effect, {era}: {d:+.3f}R a trade ({'helps' if d > 0 else 'hurts'}); placed rows removed by the floor {s1[pick1]['placed_rows'] - s2['placed_rows']:,}")
    # ── STEP 3: the strength gate 98 / 95 / 90 carrying steps 1-2 ──
    log(""); log(f"STEP 3 — the strength gate at 98 (live) / 95 / 90, carrying {pick1} + the 15c floor, 5 slots. Both directions counted.")
    raw, raw_meta = load_raw_all()
    unfetchable = cov.get("unfetchable_pairs", set()) if isinstance(cov, dict) else set()
    new_rows = new_list_rows()
    if smoke:
        new_rows = [lr for lr in new_rows if lr["E"] in keep_days]
    new_recs, new_excl = walk_new_rows(new_rows, stores, index, raw, unfetchable, cutoff, EXITS, log=log)
    n_raw2 = sum(1 for lr in new_rows if int(lr.get("raw_src") or 0) == 2)
    if n_raw2 and new_excl.get("raw_close_missing", 0) > V.UNFETCHABLE_MAX * n_raw2 and not smoke:
        raise SystemExit(f"REFUSED — {new_excl['raw_close_missing']:,} of {n_raw2:,} new raw_src=2 list rows have no raw close on D (> {V.UNFETCHABLE_MAX:.0%})")
    log(f"new names walked: {len(new_rows):,} list rows; exclusions {dict(new_excl)}")
    s3 = {}
    list90 = V.read_list(LIST90)
    for lvl in RS_LEVELS:
        s3[lvl], adm3, adm3g, rows3 = cell(f"step3_{pick1}_floor15_rs{int(lvl)}", pick1, floor=True, rs_min=lvl, slots=5, new=new_recs)
        lrows = [r for r in list90 if r["rs_best"] >= lvl]
        all_recs = dict(recs[pick1]); all_recs.update({k: t for k, t in new_recs[pick1].items() if float(t["rs_best"]) >= lvl})
        keys3 = {t["key"] for t in rows3}            # the funnel is counted AFTER the floor: a floored row is never placed, so never filled
        all_recs = {k: v for k, v in all_recs.items() if k in keys3}
        s3[lvl]["winners"] = winner_recall(real, lrows, all_recs, adm3, adm3g)
        s3[lvl]["list_rows"] = len(lrows)
    for era in (ERA_A, ERA_B):
        log(f"-- {era} --")
        for lvl in RS_LEVELS:
            show(s3[lvl], era, verdict=False)
    base = s3[98.0]
    for lvl in RS_LEVELS:
        w = s3[lvl]["winners"]
        log(f"rs >= {lvl:.0f}: list rows {s3[lvl]['list_rows']:,}; real big breakouts (872): listed {w.get('listed', 0)} / filled {w.get('filled', 0)} / "
            f"took a slot {w.get('slot', 0)} / made money {w.get('made_money', 0)} / 3R+ {w.get('ge3', 0)} / 10R+ {w.get('ge10', 0)}; "
            f"capped decisive trades all years {s3[lvl]['cap_all']['n']:,} (losers {s3[lvl]['cap_all'].get('losers', 0):,}, 10R+ {s3[lvl]['cap_all'].get('n_ge10', 0)}) "
            f"-> vs 98: trades {s3[lvl]['cap_all']['n'] - base['cap_all']['n']:+,}, losers {s3[lvl]['cap_all'].get('losers', 0) - base['cap_all'].get('losers', 0):+,}, "
            f"10R+ {s3[lvl]['cap_all'].get('n_ge10', 0) - base['cap_all'].get('n_ge10', 0):+}, real big breakouts filled {w.get('filled', 0) - base['winners'].get('filled', 0):+}")
    pick3 = pick({lvl: s3[lvl][f"cap_{ERA_A}"] for lvl in RS_LEVELS}, list(RS_LEVELS))
    log(f"-> STEP 3 PICK on 2017-21: rs >= {pick3:.0f}")
    log("JUDGED on 2022-24:")
    show(s3[pick3], ERA_B, verdict=True)
    # ── STEP 4: slots 5 / 8 / 10 carrying steps 1-3 ──
    log(""); log(f"STEP 4 — SLOTS 5 (live) / 8 / 10, carrying {pick1} + 15c floor + rs >= {pick3:.0f}. Information for him; no pick (the slot count is his).")
    s4 = {}
    for k in SLOT_COUNTS:
        s4[k], adm4, _g4, rows4 = cell(f"step4_{pick1}_floor15_rs{int(pick3)}_slots{k}", pick1, floor=True, rs_min=pick3, slots=k, new=new_recs)
        all_recs = dict(recs[pick1]); all_recs.update({kk: t for kk, t in new_recs[pick1].items() if float(t["rs_best"]) >= pick3})
        got = []
        for w in refused:
            key = f"{w['catch_E']}|{w['ticker']}"
            t = all_recs.get(key)
            got.append({"ticker": w["ticker"], "E": w["catch_E"], "r_A_frozen": float(w["catch_r_2c"]),
                        "in_book": bool(t is not None and any(x["key"] == key for x in rows4)),
                        "admitted": bool(t is not None and adm4["admitted"].get(key)),
                        "r_chain": (None if t is None else t.get("r_2c")), "decisive": bool(t is not None and t.get("decisive")),
                        "why": (None if t is None else adm4["reason"].get(key))})
        s4[k]["refused31"] = got
    for era in (ERA_A, ERA_B, "all"):
        log(f"-- {era} --")
        for k in SLOT_COUNTS:
            show(s4[k], era, verdict=(era == ERA_B))
    log("the 31 refused >= 3R catches of the baseline (30 on the full slots, 1 on the ticker guard) under each slot count:")
    for k in SLOT_COUNTS:
        g = s4[k]["refused31"]
        log(f"  {k} slots: admitted {sum(1 for x in g if x['admitted'])} of {len(g)} (in the chain's placed rows: {sum(1 for x in g if x['in_book'])}); "
            f"their R under the chain's exit, admitted decisive ones: " + ", ".join(f"{x['ticker']} {x['r_chain']:+.1f}" for x in g if x["admitted"] and x["decisive"] and x["r_chain"] is not None)
            + "; admitted but open at the seal, never scored: " + (", ".join(f"{x['ticker']} {x['E']}" for x in g if x["admitted"] and not x["decisive"]) or "none"))
    # ── write ──
    if smoke:
        sd = TG_SCRATCH / "walk" / "smoke"
        sd.mkdir(parents=True, exist_ok=True)
        tally = {"days": int(limit_days), "frozen_rows": len(rows), "placed": len(placed), "fills_per_exit": {r: sum(1 for t in recs[r].values() if t["filled"]) for r in EXITS},
                 "new_rows": len(new_rows), "new_excl": dict(new_excl),
                 "cells": {k: {"placed_rows": v["placed_rows"], "admitted_fills": v["admitted_fills"], "n_cap_all": v["cap_all"].get("n", 0), "blocked": v["blocked"]} for k, v in cells.items()},
                 "recall_parity_rows": {k: w0.get(k) for k in ("n", "listed", "filled", "slot")},
                 "refused31_in_book": {k: sum(1 for x in s4[k]["refused31"] if x["in_book"]) for k in SLOT_COUNTS},
                 "no_R_written": True, "no_pick_recorded": True}
        (sd / "smoke_tally.json").write_text(json.dumps(tally, indent=1, default=str))
        drop = {"realized_r", "events", "legs", "total_r", "r_2c", "r_0c", "status", "sessions_held", "exit_kind"} | {k for r in EXITS for t in recs[r].values() for k in t if k.startswith("r_")}
        shape_rows = [{k: v for k, v in t.items() if k not in drop} | {"rule": r} for r in EXITS for t in recs[r].values()]
        V.write_tsv(sd / "smoke_rows.tsv.gz", shape_rows, sorted({k for t in shape_rows for k in t}))
        print(json.dumps(tally, indent=1, default=str), flush=True)
        return tally
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "results.txt").write_text("\n".join(L) + "\n")
    (OUT / "cells.json").write_text(json.dumps({"cells": cells, "pick1": pick1, "pick3": pick3, "new_excl": dict(new_excl),
                                                "raw_meta": raw_meta, "cutoff": cutoff.isoformat()}, indent=1, default=str))
    # every trade under every exit (the frozen fills and the new names), one row per (key, rule)
    out_rows = []
    for r in EXITS:
        for k, t in list(recs[r].items()) + list(new_recs[r].items()):
            if not t.get("filled"):
                continue
            out_rows.append({"rule": r, "key": k, "E": t["E"], "ticker": t["ticker"], "era": t["era"], "rs_best": t["rs_best"],
                             "new_name": bool(t.get("new_name")), "fill": t["fill"], "stop": t["stop"], "status": t["status"],
                             "exit_kind": t.get("exit_kind"), "sessions_held": t.get("sessions_held"), "decisive": t["decisive"],
                             "r_0c": t.get("r_0c"), "r_2c": t.get("r_2c"), "free_date": t["free_date"], "events": json.dumps(t["events"])})
    V.write_tsv(OUT / "trades_grid.tsv.gz", out_rows, ["rule", "key", "E", "ticker", "era", "rs_best", "new_name", "fill", "stop", "status",
                                                      "exit_kind", "sessions_held", "decisive", "r_0c", "r_2c", "free_date", "events"])
    return {"pick1": pick1, "pick3": pick3, "cells": len(cells)}


# ═══════════════════════════════════════════════════════════════════════════════════════════════
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("stage", choices=["parity", "population", "request", "coverage", "dryrun", "pins", "walk"])
    ap.add_argument("era", nargs="?", choices=["A", "B"], help="population: which store")
    ap.add_argument("--force-unfrozen", action="store_true", help="walk: skip the freeze and coverage checks (a SMOKE on a few days only; never the registered run)")
    ap.add_argument("--limit-days", type=int, default=None, help="walk --force-unfrozen only: the first N breakout days (<= 5); no R is printed or written")
    ap.add_argument("--smoke-from", default=None, help="walk --force-unfrozen only: start at this breakout day (ISO)")
    args = ap.parse_args(argv)
    if args.stage == "parity":
        return 1 if run_parity()["bad"] else 0
    if args.stage == "population":
        if args.era not in ("A", "B"):
            ap.error("population needs an era: A | B")
        run_population(args.era)
    elif args.stage == "request":
        run_request(Stores())
    elif args.stage == "coverage":
        probs, cov = coverage_problems()
        print(json.dumps({k: (v if not isinstance(v, (set, list)) else len(v)) for k, v in cov.items()}, indent=1, default=str))
        print("coverage: " + ("no problem" if not probs else "\n  ".join(probs)))
        return 1 if probs else 0
    elif args.stage == "dryrun":
        return 1 if run_dryrun()["failed"] else 0
    elif args.stage == "pins":
        print("\n".join(pins()))
        if DOC.is_file():
            print(f"doc_body = {doc_body_sha(DOC.read_text(encoding='utf-8'))}")
    elif args.stage == "walk":
        if args.force_unfrozen and (not args.limit_days or args.limit_days > 5):
            ap.error("a smoke run is at most 5 breakout days (--limit-days <= 5) and needs --force-unfrozen")
        if args.limit_days and not args.force_unfrozen:
            ap.error("--limit-days is a smoke-run option: it needs --force-unfrozen")
        run_walk(force=args.force_unfrozen, limit_days=args.limit_days, smoke_from=args.smoke_from)
    return 0


if __name__ == "__main__":
    sys.exit(main())
