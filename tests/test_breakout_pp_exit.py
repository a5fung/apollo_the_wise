"""Breakout v1 PAPER — part B: the `pp` exit on the paper book (build 2026-10-30).

The acceptance bar: on random daily paths (and day-0 minute paths) the LIVE MAPPING's decisions for a 'breakout_pp' row —
the third at +2R, the session-3 third, the stop to cost, the 20-day trail sale at the next open, the stall cut — equal
`consolidation_breakout_pp.walk_pp` (arm `pp`) EVENT FOR EVENT, in the pattern of tests/test_cb_pp_recorder.py.

WHAT "THE LIVE MAPPING" IS HERE. The jobs decide with the pure functions of `broker/breakout_pp_rules.py`, and the same
functions are driven below, one session at a time, in the jobs' order:
  * the breakout day: `rules.day0_facts` (what the 16:45 job stores; the poll and the broker act on the same minutes);
  * each session: the broker's resting stop at the level the live rows carry (`hard_stop`, then `stop_after_third`), the
    poll's +2R third at `rules.target_price` (pinned below to `scan_profit_triggers`' own target for a breakout row),
    then the 15:45 `session3_decision`, then the 16:45 `trail_decision`, whose `sell` is the 19:02 PAPER DAY market sale
    filling at the NEXT session's open.
The two things the live system does at the BROKER — the stop and the +2R third fill — are modelled with the walk's own
daily conventions (a stop fills at the stop, or at the open when the session opened under it; the +2R third at the
target, or at the open when the session opened above it). Where the live machinery cannot express the walk exactly, the
differences are named in the SSoT entry (intrabar order, the 15:45 price as the session-3 close, whole shares, no
horizon) and are NOT bent into either side here.

HIS RULING 2026-10-29 ("Go with rec", the first third at +2R): "a third sold" is what ACTUALLY FILLED (the row's
`partial_taken`), never a high at +2R. The equality bar therefore holds on the paths where the resting +2R limit filled
in the session that touched the target (`LIMIT_AT_TOUCH` — every path of the fuzz), and on the paths where an intrabar
touch did NOT fill (`LIMIT_NEXT_TOUCH`) live departs from the walk by design: `TestTheDefinedDivergenceWhenTheLimitDidNotFill`
asserts that divergence rule by rule (it never skips those paths), and asserts equality on every path of that model
with no touch or a touch that fills.

HIS RULING 2026-10-29 late ("option a"), on those same unfilled paths: (i) on session 3, with the close above the fill
and the +2R limit still resting, the limit is CANCELLED and the third sold at the close (exactly one third ever — a fill
in the race IS the third: that race is not expressible on daily bars and is pinned at the job level below); (ii) the
stop stays where it was until a third ACTUALLY sells — placing the +2R limit no longer moves it to cost. So in the
replay the stop moves only inside `third()`, and an unfilled day-0 touch walks the rest of the breakout day's minutes
against the ORIGINAL stop (`day0_minutes`), not the minute walk's modelled stop at cost.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
from datetime import date, datetime
from unittest.mock import AsyncMock

import numpy as np
import pytest

from agents.market_intelligence import consolidation_breakout as cb
from agents.market_intelligence import consolidation_breakout_pp as ppx
from agents.market_intelligence.broker import breakout_pp_exit as bpe
from agents.market_intelligence.broker import breakout_pp_rules as rules
from agents.market_intelligence.broker import live_tracker as lt
from agents.market_intelligence.broker import order_manager as om
from agents.market_intelligence.broker.exit_logic import ExitStep
from tests.test_cb_backtest_runner import (STALL_TAIL, XP_FILL, XP_GOLDEN_TAIL, XP_PROFIT_TAIL, XP_STOP, _mb,
                                           _stall_minutes, _weekdays, _xp_bars)

ET = rules._ET


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 0. the numbers are the walk's
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_five_numbers_are_the_pp_arms():
    b = ppx._BASE
    assert rules.PARTIAL_FRAC == b.partial_frac
    assert rules.PARTIAL_R == b.partial_r
    assert rules.STALL_CUT_R == b.stall_cut_r and rules.STALL_CUT_SESSION == b.stall_cut_session
    assert rules.TRAIL_SMA == b.trail_sma and b.trail_fill == "next_open"
    assert rules.LEG_SESSION == ppx.LEG_FIRST
    assert rules.DAY0_FACTS_VERSION == ppx.DAY0_FACTS_VERSION
    assert ppx.SESSION_RULE["pp"] == "profit_only"


def test_the_rules_module_is_pure_and_loads_no_cb():
    """It is EXECUTION-loaded (live_tracker imports it): no consolidation_breakout* import may ride in with it."""
    import subprocess
    import sys
    from pathlib import Path
    repo = Path(__file__).resolve().parent.parent
    code = ("import sys; import agents.market_intelligence.broker.breakout_pp_rules, "
            "agents.market_intelligence.broker.breakout_pp_exit, agents.market_intelligence.broker.live_tracker; "
            "sys.exit(int(any(m.startswith('agents.market_intelligence.consolidation_breakout') for m in sys.modules)))")
    r = subprocess.run([sys.executable, "-c", code], cwd=repo, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    listed = (repo / "scripts" / "exec_loaded_modules.txt").read_text()
    assert "agents/market_intelligence/broker/breakout_pp_rules.py" in listed
    assert "agents/market_intelligence/broker/breakout_pp_exit.py" in listed


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 1. day 0: the port equals the recorder's day0_facts
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def _mins(mb) -> list[tuple]:
    return [(int(m), float(o), float(h), float(lo)) for m, o, h, lo in zip(mb.minute, mb.o, mb.h, mb.l)]


def _random_minutes(rng, fill, drift=None):
    px, rows = fill, []
    drift = float(rng.choice([-0.0004, 0.0, 0.00005, 0.0002, 0.0012])) if drift is None else drift
    for m in range(390):
        px *= 1 + rng.normal(drift, 0.002)
        mo, mc = px, px * (1 + rng.normal(0, 0.001))
        rows.append((m, mo, max(mo, mc) * (1 + rng.uniform(0, 0.002)), min(mo, mc) * (1 - rng.uniform(0, 0.002)), mc))
    return rows


def test_day0_facts_equal_the_recorders_on_random_minute_days():
    rng = np.random.default_rng(1030)
    kinds = set()
    for _ in range(600):
        fill = float(rng.uniform(5, 200))
        stop = fill * (1 - rng.uniform(0.005, 0.06))
        mb = _mb(_random_minutes(rng, fill))
        fm = int(rng.integers(5, 380))
        want = json.loads(json.dumps(ppx.day0_facts(mb, fill=fill, stop=stop, fill_minute=fm)))
        got = rules.day0_facts(_mins(mb), fill=fill, stop=stop, fill_minute=fm)
        assert got == want
        assert json.loads(json.dumps(got)) == got
        kinds.add((got["stopped"], got["partial_price"] is not None))
    assert kinds == {(False, False), (False, True), (True, False), (True, True)}


def test_day0_facts_with_no_minute_after_the_fill_have_no_peak():
    mb = _mb([(m, 10.3, 10.32, 10.28, 10.3) for m in range(8)])
    assert rules.day0_facts(_mins(mb), fill=XP_FILL, stop=XP_STOP, fill_minute=7) == \
        ppx.day0_facts(mb, fill=XP_FILL, stop=XP_STOP, fill_minute=7)
    assert rules.day0_facts(_mins(mb), fill=XP_FILL, stop=XP_STOP, fill_minute=7)["peak"] is None


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 2. THE ACCEPTANCE BAR — the live mapping equals walk_pp (arm 'pp') event for event
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def _fwd_dicts(fwd) -> list[dict]:
    return [{"o": float(fwd.o[k]), "h": float(fwd.h[k]), "l": float(fwd.l[k]), "c": float(fwd.c[k])}
            for k in range(len(fwd.c))]


LIMIT_AT_TOUCH = "at_touch"        # the resting +2R limit fills in the session that touched the target (the walk's book)
LIMIT_NEXT_TOUCH = "next_touch"    # an INTRABAR first touch does not fill; the GTC limit fills on the next session that
                                   # reaches the target (or never, when none does) — his ruling 2026-10-29's other kind


def live_replay(*, fill: float, stop: float, closes_before, fwd: list[dict], facts: dict, adr20: float,
                horizon: int = cb.EXIT_HORIZON, limit_fill: str = LIMIT_AT_TOUCH, day0_minutes=None) -> dict:
    """The live system on this path, session by session, deciding ONLY with breakout_pp_rules (see the module docstring).
    Returns `walk_exit`'s shape so it compares with `walk_pp_arms` directly.

    "A third sold" is the row's `partial_taken` — what actually FILLED (his ruling 2026-10-29). The +2R third is the
    poll's RESTING limit (an OCO) at the target, placed when the target trades. Placing it does NOT move the stop (his
    ruling 2026-10-29 late: for a breakout row `execute_partial_exit` never moves the stop, and the third's OCO sibling
    sits at the stop the shares already had); the stop moves to the fill when a third FILLS
    (`order_manager.finalize_partial_exit`). A gap open above the target always fills (the limit is placed below the
    market). `limit_fill` says whether an INTRABAR touch fills: `LIMIT_AT_TOUCH` (the walk's convention — equality) or
    `LIMIT_NEXT_TOUCH` (the defined divergence). On session 3 with the close above the fill and the limit still resting,
    the limit is cancelled ('limit_cancelled') and the third sold at that close ('partial'). `day0_minutes` (the
    breakout day's [(minute, open, high, low)]) is needed only for an unfilled day-0 touch: the rest of the day is then
    walked against the ORIGINAL stop."""
    fill, stop = float(fill), float(stop)
    risk = fill - stop
    F = rules.PARTIAL_FRAC
    events: list = []
    pnl, remaining = 0.0, 1.0
    partial = False                        # the row's partial_taken: a third FILLED
    resting = False                        # a +2R third placed at the target and not filled yet
    stop_now = stop                        # the broker's resting stop (the row's stop_price)
    closes_before = [float(x) for x in closes_before]
    target = rules.target_price(fill, stop)
    assert limit_fill in (LIMIT_AT_TOUCH, LIMIT_NEXT_TOUCH)

    def out(status, held):
        return cb._outcome(status, pnl, risk, fill, adr20, held, events)

    def stop_to_cost(j, close_j):
        nonlocal stop_now
        stop_now = rules.stop_after_third(stop_now, fill)
        events.append((j, "stop_to", stop_now, 0.0))
        if stop_now > close_j:
            events.append((j, "be_above_close", close_j, 0.0))

    def third(j, kind, px, close_j):       # a third FILLED -> partial_taken; ONLY NOW the stop to cost
        nonlocal pnl, remaining, partial, resting
        events.append((j, kind, px, F))
        pnl += (px - fill) * F
        remaining -= F
        partial, resting = True, False
        stop_to_cost(j, close_j)

    def rest_limit(j):                     # an intrabar touch the limit did not fill: placed, resting, stop UNCHANGED
        nonlocal resting
        resting = True
        events.append((j, "limit_rested", target, 0.0))

    def walk_the_resting_third(j0):        # after a trail sale of the 2/3, the third rests under its own OCO
        nonlocal pnl, remaining
        for k in range(j0, min(int(horizon), n) + 1):
            b = fwd[k - 1]
            o, h, lo = b["o"], b["h"], b["l"]
            if o >= target:
                events.append((k, "partial_r", o, F))
                pnl += (o - fill) * F
                remaining -= F
                return k
            if o <= stop_now or lo <= stop_now:
                px = o if o <= stop_now else stop_now
                events.append((k, "stop_gap" if o < stop_now else "stop", px, F))
                pnl += (px - fill) * F
                remaining -= F
                return k
            if h >= target:
                events.append((k, "partial_r", target, F))
                pnl += (target - fill) * F
                remaining -= F
                return k
        k = min(int(horizon), n)
        events.append((k, "mark", fwd[k - 1]["c"], F))
        pnl += (fwd[k - 1]["c"] - fill) * F
        remaining -= F
        return k

    # day 0 — the stored facts ARE the breakout day's minutes walked against the stop and the poll's +2R
    pp0 = facts["partial_price"]
    fills0 = pp0 is not None and (limit_fill == LIMIT_AT_TOUCH or float(pp0) > target)   # an open above always fills
    if pp0 is not None and not fills0:
        # an unfilled day-0 touch: the limit rests and the stop stays at the ORIGINAL stop for the rest of the day (the
        # minute walk's facts model a third at the touch and the stop at cost after it — live does neither)
        assert day0_minutes is not None, "an unfilled day-0 touch needs the breakout day's minutes"
        rest_limit(0)
        for m, op, _hi, lo in day0_minutes:
            if int(m) <= int(facts["partial_minute"]):
                continue
            if lo <= stop or op < stop:
                px = op if op < stop else stop
                events.append((0, "day0_gap" if px < stop else "day0_stop", px, remaining))
                pnl += (px - fill) * remaining
                return out("stopped_day0", 0)
    elif facts["stopped"]:
        if pp0 is not None:
            events.append((0, "partial_r", float(pp0), F))
            pnl += (float(pp0) - fill) * F
            remaining -= F
            events.append((0, "stop_to", float(facts["stop_in_force"]), 0.0))
        px = float(facts["exit_price"])
        events.append((0, "day0_gap" if px < float(facts["stop_in_force"]) else "day0_stop", px, remaining))
        pnl += (px - fill) * remaining
        return out("stopped_day0", 0)
    elif pp0 is not None:
        third(0, "partial_r", float(pp0), closes_before[-1])

    n = len(fwd)
    for j in range(1, min(int(horizon), n) + 1):
        b = fwd[j - 1]
        o, h, lo, c = b["o"], b["h"], b["l"], b["c"]
        stop_j = stop_now
        gap = (not partial) and o >= target
        if o <= stop_j or lo <= stop_j:                    # the broker's stop (a gap-open third first)
            if gap:
                events.append((j, "partial_r", o, F))
                pnl += (o - fill) * F
                remaining -= F
            px = o if o <= stop_j else stop_j
            events.append((j, "stop_gap" if o < stop_j else "stop", px, remaining))
            pnl += (px - fill) * remaining
            return out("stopped", j)
        if gap:                                            # a gap open above the target fills the third at the open
            third(j, "partial_r", o, c)
        elif not partial and h >= target:
            if resting or limit_fill == LIMIT_AT_TOUCH:    # the resting limit (or the at-touch book) fills at the target
                third(j, "partial_r", target, c)
            else:
                rest_limit(j)
        d = rules.session3_decision(fill=fill, stop=stop, day0=facts, fwd=fwd[:j], partial_taken=partial,
                                    third_resting=resting)                                          # 15:45
        if d == "cut":
            assert not resting, "a stall cut beside a resting +2R third (a +2R touch is past +1R)"
            events.append((j, "cut", c, remaining))
            pnl += (c - fill) * remaining
            return out("time_exit", j)
        if d == "session_third":
            assert not resting
            third(j, "partial", c, c)
        if d == rules.CANCEL_RESTING_THIRD:                # cancel the resting limit (confirmed), sell the third at c
            assert resting
            events.append((j, "limit_cancelled", target, 0.0))
            third(j, "partial", c, c)
        t = rules.trail_decision(closes_before=closes_before, fwd=fwd[:j], partial_taken=partial)   # 16:45
        if t["sell"] and j < n:                            # 19:02 PAPER DAY market sale -> fills at the next open
            opx = fwd[j]["o"]
            sold = remaining - (F if resting else 0.0)    # the sale goes beside a resting third (it keeps its OCO)
            events.append((j + 1, "trail", opx, sold))
            pnl += (opx - fill) * sold
            remaining -= sold
            if resting:
                return out("trailed", walk_the_resting_third(j + 1))
            return out("censored" if j == int(horizon) else "trailed", j + 1)
        if j == int(horizon):                              # (the recorder's horizon; live has none — a mark only)
            events.append((j, "mark", c, remaining))
            pnl += (c - fill) * remaining
            return out("censored", j)
    if n > 0:                                              # (the data ran out: the recorder's degraded mark)
        events.append((n, "mark", fwd[n - 1]["c"], remaining))
        pnl += (fwd[n - 1]["c"] - fill) * remaining
    else:
        events.append((0, "mark", closes_before[-1], remaining))
        pnl += (closes_before[-1] - fill) * remaining
    return out("degraded", n)


def _same(a: dict, b: dict) -> None:
    assert [tuple(e) for e in a["events"]] == [tuple(e) for e in b["events"]]
    assert a["status"] == b["status"] and a["sessions_held"] == b["sessions_held"]
    assert a["realized_r"] == pytest.approx(b["realized_r"], abs=1e-12)


def _both(bars, e, mb, *, fill, stop, fill_minute=7, adr20=0.10, horizon=cb.EXIT_HORIZON, limit_fill=LIMIT_AT_TOUCH):
    fwd, _cut = cb.forward_window(bars, np.arange(len(bars)), e, horizon)
    want_facts = json.loads(json.dumps(ppx.day0_facts(mb, fill=fill, stop=stop, fill_minute=fill_minute)))
    got_facts = rules.day0_facts(_mins(mb), fill=fill, stop=stop, fill_minute=fill_minute)
    assert got_facts == want_facts
    want = ppx.walk_pp_arms({"fill": fill, "stop": stop}, want_facts, closes_before=bars.c[:e + 1], fwd=fwd,
                            adr20=adr20, horizon=horizon, arms=("pp",))["pp"]
    got = live_replay(fill=fill, stop=stop, closes_before=list(bars.c[:e + 1]), fwd=_fwd_dicts(fwd), facts=got_facts,
                      adr20=adr20, horizon=horizon, limit_fill=limit_fill, day0_minutes=_mins(mb))
    return want, got


class TestTheLiveMappingEqualsWalkPP:
    def test_the_scenario_tails(self):
        seen = set()
        for tail in (XP_GOLDEN_TAIL, XP_PROFIT_TAIL, STALL_TAIL,
                     [(10.60, 10.85, 10.50, 10.80), (10.70, 10.75, 10.25, 10.70), (9.50, 9.60, 9.40, 9.50)]):
            for hist in (10.0, 10.5):
                for minutes in (None, _stall_minutes()):
                    bars, e = _xp_bars(tail, hist=hist)
                    want, got = _both(bars, e, _mb(minutes), fill=XP_FILL, stop=XP_STOP)
                    _same(want, got)
                    seen.add(got["status"])
        assert {"stopped", "time_exit", "trailed"} <= seen

    def test_a_fuzz_of_random_days(self):
        rng = np.random.default_rng(1031)
        statuses, kinds = set(), set()
        for seed in range(500):
            n, e = 200, 150
            sig = float(rng.choice([0.015, 0.03, 0.05]))
            steps = rng.normal(0.002, sig, n)
            if seed % 2 == 1:                                    # reach +1R early, then roll over through the fill
                steps[e + 1:] = rng.normal(-0.012, 0.012, n - e - 1)
            c = 10.0 * np.exp(np.cumsum(steps))
            o = c * (1 + rng.normal(0, 0.01, n))
            h = np.maximum(o, c) * (1 + rng.uniform(0, 0.03, n))
            lo = np.minimum(o, c) * (1 - rng.uniform(0, 0.03, n))
            bars = cb.daily_bars_from_arrays(_weekdays(n), o, h, lo, c, np.full(n, 1e6))
            fill = float(o[e]) * 1.01
            stop = fill * (1 - rng.uniform(0.01, 0.06))
            mb = _mb(_random_minutes(rng, fill))
            fm = int(rng.integers(5, 60))
            want, got = _both(bars, e, mb, fill=fill, stop=stop, fill_minute=fm, adr20=0.05)
            _same(want, got)
            statuses.add(got["status"])
            kinds.update(ev[1] for ev in got["events"])
        # the fuzz reaches every decision the live mapping makes
        assert {"stopped", "stopped_day0", "trailed", "time_exit"} <= statuses
        assert {"partial_r", "partial", "stop_to", "be_above_close", "cut", "trail", "stop"} <= kinds

    def test_long_horizons_and_short_histories(self):
        """Paths longer than the walk's 120-session horizon (the trail / the mark at the horizon) and histories shorter
        than 20 closes (no 20-day yet)."""
        rng = np.random.default_rng(1032)
        for seed in range(120):
            n, e = (300, 150) if seed % 2 == 0 else (60, 12)
            c = 10.0 * np.exp(np.cumsum(rng.normal(0.003, 0.02, n)))
            o = c * (1 + rng.normal(0, 0.005, n))
            h = np.maximum(o, c) * (1 + rng.uniform(0, 0.02, n))
            lo = np.minimum(o, c) * (1 - rng.uniform(0, 0.02, n))
            bars = cb.daily_bars_from_arrays(_weekdays(n), o, h, lo, c, np.full(n, 1e6))
            fill = float(o[e]) * 1.005
            stop = fill * (1 - rng.uniform(0.03, 0.08))
            mb = _mb([(m, fill, fill * 1.001, fill * 0.999, fill) for m in range(390)])
            want, got = _both(bars, e, mb, fill=fill, stop=stop, adr20=0.05)
            _same(want, got)

    def test_the_pp_session_third_is_only_ever_above_the_fill(self):
        rng = np.random.default_rng(1033)
        n_session = 0
        for _ in range(200):
            n, e = 200, 150
            c = 10.0 * np.exp(np.cumsum(rng.normal(0.002, 0.03, n)))
            o = c * (1 + rng.normal(0, 0.01, n))
            h = np.maximum(o, c) * (1 + rng.uniform(0, 0.03, n))
            lo = np.minimum(o, c) * (1 - rng.uniform(0, 0.03, n))
            bars = cb.daily_bars_from_arrays(_weekdays(n), o, h, lo, c, np.full(n, 1e6))
            fill = float(o[e]) * 1.01
            stop = fill * (1 - rng.uniform(0.02, 0.06))
            mb = _mb([(m, fill, fill * 1.001, fill * 0.999, fill) for m in range(390)])
            _w, got = _both(bars, e, mb, fill=fill, stop=stop, adr20=0.05)
            for ev in got["events"]:
                if ev[1] == "partial":
                    assert ev[0] == 3 and ev[2] > fill
                    n_session += 1
        assert n_session > 0


def _fuzz_path(rng, seed):
    """One random daily path + breakout-day minutes (the generator of `test_a_fuzz_of_random_days`)."""
    n, e = 200, 150
    sig = float(rng.choice([0.015, 0.03, 0.05]))
    steps = rng.normal(0.002, sig, n)
    if seed % 2 == 1:                                    # reach +1R early, then roll over through the fill
        steps[e + 1:] = rng.normal(-0.012, 0.012, n - e - 1)
    c = 10.0 * np.exp(np.cumsum(steps))
    o = c * (1 + rng.normal(0, 0.01, n))
    h = np.maximum(o, c) * (1 + rng.uniform(0, 0.03, n))
    lo = np.minimum(o, c) * (1 - rng.uniform(0, 0.03, n))
    bars = cb.daily_bars_from_arrays(_weekdays(n), o, h, lo, c, np.full(n, 1e6))
    fill = float(o[e]) * 1.01
    stop = fill * (1 - rng.uniform(0.01, 0.06))
    mb = _mb(_random_minutes(rng, fill))
    fm = int(rng.integers(5, 60))
    return bars, e, mb, fill, stop, fm


class TestTheDefinedDivergenceWhenTheLimitDidNotFill:
    """His ruling 2026-10-29 (the first third at +2R): follow what ACTUALLY FILLED. On a path where the +2R target was
    first touched INTRABAR and the resting limit did NOT fill there (`LIMIT_NEXT_TOUCH`: it fills on the next session
    that reaches the target, or never), live departs from `walk_pp` BY DESIGN. Every path of the fuzz is classified:
      * no +2R touch, or a first touch that fills (a gap open above the target) -> live == the walk, event for event;
      * a first touch that does not fill -> the DEFINED divergence, asserted rule by rule (never skipped):
          D1 every event before the touch session is the walk's;
          D2 at the touch: no third — the limit rests at the target ('limit_rested') and the stop does NOT move
             (his ruling 2026-10-29 late: placing the +2R limit never moves a breakout row's stop);
          D3 a third is only ever booked when it FILLS: after the touch, at the target or at an open above it — or as
             the session-3 third after the resting limit is cancelled;
          D4 no 20-day trail sale is decided before session 3 unless a third really filled by then;
          D5 session 3 with the limit still resting and the close above the fill: the limit is cancelled
             ('limit_cancelled') and the third sold at that close ('partial'), the stop to the fill with it;
          D6 on EVERY path (both models): at most one third is ever sold, and the stop moves only in the session a
             third sold, never before one.
    Each class must be non-empty, so a generator change cannot silently stop exercising one."""

    def test_the_fuzz_partitions_into_walk_equal_and_the_defined_divergence(self):
        rng = np.random.default_rng(1031)
        counts = {"no_touch": 0, "filled_at_touch": 0, "unfilled_touch": 0, "diverged": 0, "later_fill": 0,
                  "cancelled_and_sold_at_3": 0, "walk_trailed_early_live_did_not": 0, "day0_unfilled": 0,
                  "stop_held_past_the_touch": 0}
        for seed in range(500):
            bars, e, mb, fill, stop, fm = _fuzz_path(rng, seed)
            want, at_touch = _both(bars, e, mb, fill=fill, stop=stop, fill_minute=fm, adr20=0.05)
            _same(want, at_touch)                                       # the first kind: equality
            _w, got = _both(bars, e, mb, fill=fill, stop=stop, fill_minute=fm, adr20=0.05,
                            limit_fill=LIMIT_NEXT_TOUCH)
            target = rules.target_price(fill, stop)
            for run in (at_touch, got):                                 # D6, on every path of both models
                rev = [tuple(x) for x in run["events"]]
                thirds = [x for x in rev if x[1] in ("partial_r", "partial")]
                assert len(thirds) <= 1, (seed, rev)
                for x in rev:
                    if x[1] == "stop_to":
                        assert thirds and thirds[0][0] == x[0], (seed, rev)
            touches = [ev for ev in want["events"] if ev[1] == "partial_r"]
            if not touches:
                counts["no_touch"] += 1
                _same(want, got)
                continue
            j0, px0 = touches[0][0], touches[0][2]
            if px0 > target:                                            # a gap open above the target: it fills
                counts["filled_at_touch"] += 1
                _same(want, got)
                continue
            counts["unfilled_touch"] += 1
            wev, gev = [tuple(x) for x in want["events"]], [tuple(x) for x in got["events"]]
            counts["diverged"] += wev != gev
            # D1
            assert [x for x in gev if x[0] < j0] == [x for x in wev if x[0] < j0]
            # D2
            assert (j0, "limit_rested", target, 0.0) in gev
            assert not [x for x in gev if x[0] == j0 and x[1] == "partial_r"]
            if j0 != rules.LEG_SESSION:     # (a touch ON session 3 can be cancelled and sold that close — D5)
                assert not [x for x in gev if x[0] == j0 and x[1] in ("partial", "stop_to")]
            counts["day0_unfilled"] += j0 == 0
            if any(x[0] > j0 for x in gev) and not any(x[1] == "stop_to" and x[0] <= j0 + 1 for x in gev):
                counts["stop_held_past_the_touch"] += 1
            # D3
            for x in gev:
                if x[1] == "partial_r":
                    assert x[0] > j0 and x[2] >= target - 1e-12
                    counts["later_fill"] += 1
                if x[1] == "partial":
                    assert x[0] == rules.LEG_SESSION and x[2] > fill
            filled_by = {x[0] for x in gev if x[1] == "partial_r"}
            # D4
            for x in gev:
                if x[1] == "trail" and x[0] - 1 < rules.LEG_SESSION:
                    assert any(s <= x[0] - 1 for s in filled_by), (seed, gev)
            if any(x[1] == "trail" and x[0] - 1 < rules.LEG_SESSION for x in wev) and \
                    not any(x[1] == "trail" and x[0] - 1 < rules.LEG_SESSION for x in gev):
                counts["walk_trailed_early_live_did_not"] += 1
            # D5
            resting_at_3 = j0 <= rules.LEG_SESSION and not any(s <= rules.LEG_SESSION for s in filled_by)
            if resting_at_3:
                alive_at_3 = not any(x[0] <= rules.LEG_SESSION and x[1] in ("stop", "stop_gap", "day0_stop",
                                                                             "day0_gap", "cut") for x in gev) \
                    and not any(x[1] == "trail" and x[0] <= rules.LEG_SESSION for x in gev)
                s3 = _fwd_dicts(cb.forward_window(bars, np.arange(len(bars)), e, cb.EXIT_HORIZON)[0])[2]
                if alive_at_3 and s3["c"] > fill:
                    k = gev.index((rules.LEG_SESSION, "limit_cancelled", target, 0.0))
                    assert gev[k + 1] == (rules.LEG_SESSION, "partial", s3["c"], rules.PARTIAL_FRAC), (seed, gev)
                    assert gev[k + 2][:2] == (rules.LEG_SESSION, "stop_to")
                    assert not [x for x in gev if x[1] == "partial_r"]          # never a second third after it
                    counts["cancelled_and_sold_at_3"] += 1
                else:
                    assert not [x for x in gev if x[1] in ("partial", "limit_cancelled")], (seed, gev)
        assert all(v > 0 for v in counts.values()), counts

    def test_the_reviewers_case_exactly(self):
        """The review's shape (fill 10.30, stop 10.10, target 10.70): session 1 trades 10.71 intrabar and closes 10.45
        under a 20-day of 10.50; the resting limit does not fill. The walk books the third and sells the rest at
        session 2's open; live rests the limit with the stop UNCHANGED at 10.10, starts NO trail, and at session 3
        (close 10.46 above the fill) CANCELS the resting limit and sells the third at that close, the stop to the fill
        with it (his ruling 2026-10-29 late, "option a"); the 20-day trail (live from session 3) then sells the rest
        at session 4's open. Session 5's high at the target sells nothing: the third was sold once."""
        fill, stop = 10.30, 10.10
        day0 = {"v": rules.DAY0_FACTS_VERSION, "stopped": False, "peak": 10.40, "exit_price": None,
                "exit_minute": None, "partial_price": None, "partial_minute": None, "stop_in_force": None}
        fwd = [{"o": 10.35, "h": 10.71, "l": 10.31, "c": 10.45}, {"o": 10.44, "h": 10.60, "l": 10.40, "c": 10.55},
               {"o": 10.55, "h": 10.60, "l": 10.40, "c": 10.46}, {"o": 10.47, "h": 10.50, "l": 10.42, "c": 10.48},
               {"o": 10.50, "h": 10.75, "l": 10.45, "c": 10.70}]
        got = live_replay(fill=fill, stop=stop, closes_before=[10.50] * 20, fwd=fwd, facts=day0, adr20=0.05,
                          limit_fill=LIMIT_NEXT_TOUCH)
        target = rules.target_price(fill, stop)
        F = rules.PARTIAL_FRAC
        assert [tuple(x) for x in got["events"]] == [
            (1, "limit_rested", target, 0.0),
            (3, "limit_cancelled", target, 0.0), (3, "partial", 10.46, F), (3, "stop_to", 10.30, 0.0),
            (4, "trail", 10.47, pytest.approx(1 - F))]
        assert got["status"] == "trailed" and got["sessions_held"] == 4
        at = live_replay(fill=fill, stop=stop, closes_before=[10.50] * 20, fwd=fwd, facts=day0, adr20=0.05)
        assert [x[:2] for x in at["events"]][:3] == [(1, "partial_r"), (1, "stop_to"), (2, "trail")]


def test_the_polls_target_for_a_breakout_row_is_the_pp_target():
    """The +2R third is `scan_profit_triggers` as it is: `breakout_v1` is not ORB-framed (R = entry - hard_stop), its
    strategy row carries no profit_trigger_r override, and the global multiple is 2.0 — the scan's own expression then
    equals `rules.target_price` bit for bit. A change of the global multiple fails HERE (it would move the pp third)."""
    from agents.market_intelligence.constants import PROFIT_TRIGGER_R
    assert "breakout_v1" not in om._ORB_R_FRAME_SIGNAL_TYPES
    assert "breakout_v1" not in om._PLUS8R_PARTIAL_SIGNAL_TYPES          # a plain third, rounded down
    rng = np.random.default_rng(7)
    for _ in range(200):
        entry = float(rng.uniform(2, 300))
        stop = entry * (1 - rng.uniform(0.005, 0.08))
        r_mult = om.resolve_profit_trigger_r("breakout_v1", {}, PROFIT_TRIGGER_R)
        rps = om.profit_target_r_per_share("breakout_v1", entry, stop, entry * 0.9)
        assert entry + r_mult * rps == rules.target_price(entry, stop)
    assert om.profit_take_shares(9, "breakout_v1") == 3 and om.profit_take_shares(2, "breakout_v1") == 0


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 3. the sessions as the jobs read them
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def _t(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, 0, 0, tzinfo=ET).timestamp() * 1000)


def _bar(d, o, h, lo, c):
    return {"t": _t(d), "o": o, "h": h, "l": lo, "c": c}


def test_split_sessions_puts_es_close_last_and_today_from_the_jobs_bar():
    days = _weekdays(30, dt.date(2026, 9, 1))
    alert = days[24]
    today = days[27]
    hist = [_bar(d, 10, 11, 9, 10 + k * 0.01) for k, d in enumerate(days[:28])]
    hist[27] = _bar(today, 1, 1, 1, 1)                     # a stale today in the history: replaced by the job's bar
    cbf, fwd = rules.split_sessions(hist, alert_date=alert, today=today, today_bar={"o": 12, "h": 13, "l": 11, "c": 12.5})
    assert len(cbf) == 25 and cbf[-1] == pytest.approx(10.24)
    assert len(fwd) == 3 and fwd[-1] == {"o": 12.0, "h": 13.0, "l": 11.0, "c": 12.5}
    # the breakout day itself: no session yet
    assert rules.split_sessions(hist, alert_date=alert, today=alert, today_bar={"o": 1, "h": 1, "l": 1, "c": 1})[1] == []


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 4. the jobs — wiring (fakes; no network)
# ═══════════════════════════════════════════════════════════════════════════════════════════════
ALERT = date(2026, 10, 26)            # a Monday: the breakout day
S3 = date(2026, 10, 29)               # session 3
FILL, STOP0 = 10.30, 10.10            # R = 0.20: +1R 10.50, +2R 10.70


def _hist_for(today: date, *, prior_close=10.0, fwd_bars=()):
    """25 flat sessions before the breakout day, the breakout day (close 10.55), then `fwd_bars` (o, h, l, c) for the
    sessions after it up to (not incl.) today."""
    days = []
    d = ALERT - dt.timedelta(days=40)
    while d <= today:
        if d.weekday() < 5:
            days.append(d)
        d += dt.timedelta(days=1)
    before = [x for x in days if x < ALERT][-25:]
    out = [_bar(x, prior_close, prior_close + 0.1, prior_close - 0.1, prior_close) for x in before]
    out.append(_bar(ALERT, 10.20, 10.60, 10.10, 10.55))
    after = [x for x in days if ALERT < x < today]
    for x, b in zip(after, fwd_bars):
        out.append(_bar(x, *b))
    return out


FACTS_REACHED = {"v": 1, "stopped": False, "exit_price": None, "exit_minute": None, "partial_price": None,
                 "partial_minute": None, "stop_in_force": None, "peak": 10.60}      # +1R reached on the breakout day
FACTS_QUIET = dict(FACTS_REACHED, peak=10.40)                                     # never +1R on the breakout day


def _row(**over):
    r = {"id": 701, "ticker": "BRK", "alert_date": ALERT, "account_mode": "paper", "signal_type": "breakout_v1",
         "exit_rule": "breakout_pp", "remaining_shares": 9, "entry_price": FILL, "hard_stop": STOP0,
         "stop_price": STOP0, "stop_order_id": "stop-1", "partial_taken": False, "breakeven_active": False,
         "exits": [], "running_closes": [], "status": "filled",
         "filled_at": datetime(2026, 10, 26, 9, 37, 20, tzinfo=ET), "breakout_day0_pp": FACTS_REACHED}
    r.update(over)
    return r


class _Conn:
    def __init__(self, rows):
        self.rows, self.executed, self.fetchvals = rows, [], []
        self.raw = None                      # the stored OCO parent row's raw_response (its legs), when a test sets one
        self.fail_order_close = 0            # how many order-row closes raise (the finding-1 case 2 shape)
        self.fetchrow_result = None

    async def fetch(self, *_a, **_k):
        return self.rows

    async def execute(self, *a, **_k):
        self.executed.append(a)
        if "UPDATE mi_live_orders SET status = 'cancelled'" in a[0] and self.fail_order_close > 0:
            self.fail_order_close -= 1
            raise RuntimeError("db write timed out")

    async def fetchval(self, *a, **_k):
        self.fetchvals.append(a)
        if "raw_response" in a[0]:
            return self.raw
        return 1

    async def fetchrow(self, *a, **_k):
        return self.fetchrow_result


class _Acq:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *exc):
        return False


class _Pool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self, *a, **k):
        return _Acq(self.conn)


def _step(action="updated", close=10.40, low=10.20):
    return ExitStep(
        action=action, closed=action == "stopped_out", close_reason=None, close_price=None, close_shares=None,
        close_pnl=None, partial_fired=False, partial_shares=0, partial_price=None, partial_pnl=None,
        effective_stop=10.50, active_sma=10.50, bar_low=low, bar_close=close, hold_days=3, new_remaining=9,
        new_partial_taken=False, new_breakeven_active=False, new_running_closes=[close], new_exits=[],
        new_total_pnl=0.0, stop_source="trail")


def _install(monkeypatch, row, *, today, today_bar, fwd_bars=(), prior_close=10.0, step=None, resting=None):
    conn = _Conn([row])
    pool = _Pool(conn)
    monkeypatch.setattr(lt, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(bpe, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(lt, "et_today", lambda: today)

    async def _lt_hist(ticker, start, end, *a, **k):
        if start == end:
            return [dict(today_bar, t=_t(today))]
        return [b for b in _hist_for(today, prior_close=prior_close, fwd_bars=fwd_bars) if b["t"] < _t(ALERT)]

    async def _bpe_hist(ticker, start, end, *a, **k):
        return _hist_for(today, prior_close=prior_close, fwd_bars=fwd_bars)

    monkeypatch.setattr(lt, "get_index_history", _lt_hist)
    monkeypatch.setattr(bpe, "get_index_history", _bpe_hist)
    if step is not None:
        monkeypatch.setattr(lt, "apply_daily_exit_step", lambda *a, **k: step)
    calls = {"update_stop": AsyncMock(return_value=True), "execute_full_exit": AsyncMock(return_value=True),
             "execute_partial_exit": AsyncMock(return_value=True), "send_telegram_message": AsyncMock(),
             "log_audit_event": AsyncMock(), "finalize_stop_fill": AsyncMock()}
    for name, mock in calls.items():
        monkeypatch.setattr(lt, name, mock)
    calls["resting_third"] = AsyncMock(return_value=(resting is not None, resting))
    monkeypatch.setattr(bpe, "resting_third", calls["resting_third"])
    calls["bpe_audit"] = AsyncMock()
    calls["bpe_page"] = AsyncMock()
    monkeypatch.setattr(bpe, "log_audit_event", calls["bpe_audit"])
    monkeypatch.setattr(bpe, "send_telegram_message", calls["bpe_page"])
    calls["ensure_cov"] = AsyncMock(return_value=None)
    monkeypatch.setattr(om, "_ensure_stop_coverage", calls["ensure_cov"])
    monkeypatch.setattr(bpe.alpaca, "get_position", AsyncMock(return_value={"qty": 9.0}))
    bpe._paged.clear()
    return conn, calls


# ── 16:45 ────────────────────────────────────────────────────────────────────────────────────────
def test_1645_a_session3_close_under_the_20day_is_marked_for_the_next_open_not_sold(monkeypatch):
    """History at 10.5 puts the 20-day near 10.5; session 3 closes 10.25 -> under it: MARK, nothing sold or moved."""
    tb = {"o": 10.35, "h": 10.40, "l": 10.20, "c": 10.25}
    conn, calls = _install(monkeypatch, _row(), today=S3, today_bar=tb, prior_close=10.5,
                           fwd_bars=[(10.40, 10.55, 10.35, 10.50), (10.45, 10.50, 10.30, 10.40)], step=_step(close=10.25))
    out = asyncio.run(lt.update_open_positions_live(S3))
    assert out == [{"ticker": "BRK", "action": "breakout_pp_sell_pending", "session": 3}]
    calls["execute_full_exit"].assert_not_awaited()
    calls["update_stop"].assert_not_awaited()
    marks = [a for a in conn.executed if "depth_sell_pending_on" in a[0]]
    assert len(marks) == 1 and marks[0][4] == S3
    assert any(c.args[0] == "breakout_pp_close_below_sma20" for c in calls["log_audit_event"].await_args_list)


def test_1645_a_close_above_the_20day_rests_no_trail_stop(monkeypatch):
    """The pp walk's stop is the day's low at the fill until a third: the ladder's stop raise to the 10/20 line (the step
    says effective_stop 10.50) must NOT run on a breakout row."""
    tb = {"o": 10.40, "h": 10.48, "l": 10.35, "c": 10.45}
    conn, calls = _install(monkeypatch, _row(), today=S3, today_bar=tb, prior_close=10.0,
                           fwd_bars=[(10.40, 10.55, 10.35, 10.50), (10.45, 10.50, 10.30, 10.40)], step=_step(close=10.45))
    out = asyncio.run(lt.update_open_positions_live(S3))
    assert out[0]["action"] == "breakout_pp_held" and out[0]["trail_live"] is True
    calls["update_stop"].assert_not_awaited()
    calls["execute_full_exit"].assert_not_awaited()
    assert not [a for a in conn.executed if "depth_sell_pending_on" in a[0]]
    assert [a for a in conn.executed if "breakeven_active = (breakeven_active OR $3)" in a[0]]


def test_1645_session1_under_the_20day_without_a_third_is_not_a_trail_sale(monkeypatch):
    """Before session 3 the trail is live only after a +2R third."""
    d1 = date(2026, 10, 27)
    tb = {"o": 10.35, "h": 10.40, "l": 10.20, "c": 10.25}
    conn, calls = _install(monkeypatch, _row(), today=d1, today_bar=tb, prior_close=10.5, step=_step(close=10.25))
    out = asyncio.run(lt.update_open_positions_live(d1))
    assert out[0]["action"] == "breakout_pp_held" and out[0]["trail_live"] is False
    assert not [a for a in conn.executed if "depth_sell_pending_on" in a[0]]


def test_1645_after_a_third_a_stop_still_under_the_fill_is_lifted_to_the_fill(monkeypatch):
    d1 = date(2026, 10, 27)
    tb = {"o": 10.75, "h": 10.80, "l": 10.60, "c": 10.78}
    _conn, calls = _install(monkeypatch, _row(partial_taken=True, remaining_shares=6, stop_price=STOP0), today=d1,
                            today_bar=tb, prior_close=10.0, step=_step(close=10.78))
    asyncio.run(lt.update_open_positions_live(d1))
    calls["update_stop"].assert_awaited_once()
    assert calls["update_stop"].await_args.args == (701, 10.30)


def test_1645_the_breakout_day_records_the_day0_facts_from_the_minutes(monkeypatch):
    """On the breakout day the shared guard skips the row, but the facts are captured first — the recorder's way."""
    conn, calls = _install(monkeypatch, _row(breakout_day0_pp=None), today=ALERT,
                           today_bar={"o": 10.2, "h": 10.6, "l": 10.1, "c": 10.55})
    rows = [(m, 10.30, 10.32, 10.25, 10.30) for m in range(390)]
    rows[20] = (20, 10.30, 10.72, 10.28, 10.70)                       # +2R = 10.70 touched at minute 20
    mb = _mb(rows)
    open_dt = datetime(2026, 10, 26, 9, 30, tzinfo=ET)
    bars = [{"t_et": open_dt + dt.timedelta(minutes=m), "open": o, "high": h, "low": lo, "close": c, "volume": 100}
            for m, o, h, lo, c in rows]
    monkeypatch.setattr(bpe.alpaca, "get_minute_bars_range", AsyncMock(return_value=bars))
    out = asyncio.run(lt.update_open_positions_live(ALERT))
    assert out == []                                                  # nothing else runs on the breakout day
    [w] = [a for a in conn.fetchvals if "breakout_day0_pp" in a[0]]
    want = json.loads(json.dumps(ppx.day0_facts(mb, fill=FILL, stop=STOP0, fill_minute=7)))
    assert w[2] == want and w[3] == "breakout_pp" and w[4] == "paper"
    assert want["partial_price"] == pytest.approx(10.70)


def test_1645_and_1545_refuse_a_breakout_row_that_is_not_paper(monkeypatch):
    tb = {"o": 10.35, "h": 10.40, "l": 10.20, "c": 10.25}
    for job in (lt.update_open_positions_live, lt.run_partial_exits):
        _conn, calls = _install(monkeypatch, _row(account_mode="live"), today=S3, today_bar=tb, prior_close=10.5,
                                fwd_bars=[(10.40, 10.45, 10.35, 10.40), (10.45, 10.48, 10.30, 10.40)],
                                step=_step(close=10.25))
        out = asyncio.run(job(S3))
        assert out == [{"ticker": "BRK", "action": "breakout_pp_refused"}]
        for k in ("execute_full_exit", "execute_partial_exit", "update_stop"):
            calls[k].assert_not_awaited()
        assert any(c.args[0] == "breakout_pp_refused_not_paper" for c in calls["bpe_audit"].await_args_list)
        assert calls["bpe_page"].await_args.args[0].startswith(lt.mode_prefix("paper"))


# ── 15:45 ────────────────────────────────────────────────────────────────────────────────────────
def test_1545_session3_with_no_plus1r_is_the_stall_cut(monkeypatch):
    tb = {"o": 10.35, "h": 10.45, "l": 10.30, "c": 10.40}
    _conn, calls = _install(monkeypatch, _row(breakout_day0_pp=FACTS_QUIET), today=S3, today_bar=tb,
                            fwd_bars=[(10.35, 10.42, 10.25, 10.38), (10.38, 10.45, 10.30, 10.40)])
    out = asyncio.run(lt.run_partial_exits(S3))
    calls["execute_full_exit"].assert_awaited_once_with(701, "breakout_stall_cut")
    calls["execute_partial_exit"].assert_not_awaited()
    assert out == [{"ticker": "BRK", "action": "breakout_pp_cut_submitted"}]


def test_1545_session3_above_the_fill_sells_a_third(monkeypatch):
    tb = {"o": 10.40, "h": 10.50, "l": 10.35, "c": 10.46}
    _conn, calls = _install(monkeypatch, _row(), today=S3, today_bar=tb,
                            fwd_bars=[(10.40, 10.52, 10.35, 10.45), (10.45, 10.50, 10.35, 10.42)])
    out = asyncio.run(lt.run_partial_exits(S3))
    calls["execute_partial_exit"].assert_awaited_once_with(701, 3)
    calls["execute_full_exit"].assert_not_awaited()
    assert out == [{"ticker": "BRK", "action": "partial_submitted", "shares": 3}]


def test_1545_session3_at_or_under_the_fill_sells_nothing(monkeypatch):
    tb = {"o": 10.35, "h": 10.40, "l": 10.20, "c": 10.25}
    _conn, calls = _install(monkeypatch, _row(), today=S3, today_bar=tb,
                            fwd_bars=[(10.40, 10.55, 10.35, 10.50), (10.45, 10.50, 10.30, 10.40)])
    asyncio.run(lt.run_partial_exits(S3))
    calls["execute_partial_exit"].assert_not_awaited()
    calls["execute_full_exit"].assert_not_awaited()


def test_1545_any_other_session_does_nothing_and_never_takes_the_day3_ladder(monkeypatch):
    d4 = date(2026, 10, 30)
    tb = {"o": 10.40, "h": 10.50, "l": 10.35, "c": 10.46}
    _conn, calls = _install(monkeypatch, _row(breakout_day0_pp=FACTS_QUIET), today=d4, today_bar=tb,
                            fwd_bars=[(10.35, 10.42, 10.25, 10.38), (10.38, 10.45, 10.30, 10.40),
                                      (10.38, 10.45, 10.30, 10.40)])
    def _ladder(*_a, **_k):
        raise AssertionError("the day-3/5 ladder ran on a breakout row")
    monkeypatch.setattr(lt, "apply_daily_exit_step", _ladder)
    out = asyncio.run(lt.run_partial_exits(d4))
    assert out == [{"ticker": "BRK", "action": "breakout_pp_not_session3", "session": 4}]
    calls["execute_partial_exit"].assert_not_awaited()
    calls["execute_full_exit"].assert_not_awaited()


def test_1545_with_no_breakout_day_record_the_cut_is_not_applied_and_he_is_told(monkeypatch):
    tb = {"o": 10.35, "h": 10.45, "l": 10.30, "c": 10.29}
    _conn, calls = _install(monkeypatch, _row(breakout_day0_pp=None, filled_at=None), today=S3, today_bar=tb,
                            fwd_bars=[(10.35, 10.42, 10.25, 10.38), (10.38, 10.45, 10.30, 10.40)])
    asyncio.run(lt.run_partial_exits(S3))
    calls["execute_full_exit"].assert_not_awaited()
    assert any(c.args[0] == "breakout_pp_day0_facts_missing" for c in calls["bpe_audit"].await_args_list)
    assert "stall cut" in calls["bpe_page"].await_args.args[0]


# ── 19:02: the next-open sale ────────────────────────────────────────────────────────────────────
def test_1902_a_marked_breakout_row_is_sold_at_the_open_on_the_paper_book(monkeypatch):
    from tests.test_depth_exit_rule import TODAY, _sale_wire
    row = _row(remaining_shares=6, stop_price=STOP0, depth_sell_pending_on=TODAY)
    h = _sale_wire(monkeypatch, row=row)
    assert asyncio.run(om.execute_depth_open_sale(701)) is True
    assert h["opg_calls"] == []
    [sale] = h["day_calls"]
    assert sale["mode"] == "paper" and sale["qty"] == 6
    assert sale["coid"].startswith("apollo_paper_breakout_v1_BRK_")
    assert all("depth stop" not in m for m in h["sent"]), h["sent"]


def test_1902_the_runner_selects_breakout_pp_rows_and_the_depth_runner_is_unchanged(monkeypatch):
    seen: list = []

    class _C:
        async def fetch(self, q, *a, **k):
            seen.append(a)
            return [{"id": 701, "ticker": "BRK", "account_mode": "paper"}]

    class _A:
        async def __aenter__(self):
            return _C()

        async def __aexit__(self, *e):
            return False

    class _P:
        def acquire(self, *a, **k):
            return _A()

    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=_P()))
    sale = AsyncMock(return_value=True)
    monkeypatch.setattr(om, "execute_depth_open_sale", sale)
    assert asyncio.run(om.run_breakout_pp_open_sales()) == [{"trade_id": 701, "ticker": "BRK", "placed": True}]
    asyncio.run(om.run_depth_open_sales())
    assert seen == [("breakout_pp",), ("depth",)]
    assert [c.args for c in sale.await_args_list] == [(701,), (701,)]


def test_1902_a_marked_breakout_row_not_on_paper_is_never_sold(monkeypatch):
    """THE LINE at the order site itself: the sale picks its account from the row, so the runner refuses any book but
    paper — audited + paged, `execute_depth_open_sale` never called. The depth runner keeps serving both books."""
    class _C:
        async def fetch(self, q, *a, **k):
            return [{"id": 702, "ticker": "LIV", "account_mode": "live"},
                    {"id": 701, "ticker": "BRK", "account_mode": "paper"}]

    class _A:
        async def __aenter__(self):
            return _C()

        async def __aexit__(self, *e):
            return False

    class _P:
        def acquire(self, *a, **k):
            return _A()

    monkeypatch.setattr(om, "get_pool", AsyncMock(return_value=_P()))
    sale = AsyncMock(return_value=True)
    audit, page = AsyncMock(), AsyncMock()
    monkeypatch.setattr(om, "execute_depth_open_sale", sale)
    monkeypatch.setattr(om, "log_audit_event", audit)
    monkeypatch.setattr(om, "send_telegram_message", page)
    out = asyncio.run(om.run_breakout_pp_open_sales())
    assert [c.args for c in sale.await_args_list] == [(701,)]
    assert out[0] == {"trade_id": 702, "ticker": "LIV", "placed": False, "refused": "account_mode"}
    assert audit.await_args.args[0] == "breakout_pp_refused_not_paper"
    page.assert_awaited_once()
    sale.reset_mock()
    asyncio.run(om.run_depth_open_sales())
    assert [c.args for c in sale.await_args_list] == [(702,), (701,)]


def test_the_1902_job_is_scheduled_and_execution_owned(monkeypatch):
    from agents.market_intelligence import constants, scheduler as sched
    from tests.test_672_missed_job_recovery import _real_job_list
    _s, jobs = _real_job_list(monkeypatch)
    job = next(j for j in jobs if j.id == "breakout_pp_open_sale")
    trig = str(job.trigger)
    assert "hour='19'" in trig and "minute='2'" in trig and "day_of_week='mon-fri'" in trig, trig
    assert str(job.trigger.timezone) == "America/New_York"
    assert "breakout_pp_open_sale" in sched.EXECUTION_OWNED_JOB_IDS
    monkeypatch.setattr(constants, "LIVE_TRADING_ENABLED", True)
    runner = AsyncMock(return_value=[])
    depth = AsyncMock(side_effect=AssertionError("the depth runner is not this job's"))
    monkeypatch.setattr(om, "run_breakout_pp_open_sales", runner)
    monkeypatch.setattr(om, "run_depth_open_sales", depth)
    asyncio.run(sched._breakout_pp_open_sale_job())
    runner.assert_awaited_once()


# ── gates ─────────────────────────────────────────────────────────────────────────────────────────
def test_the_preflight_copy_of_the_facts_write_is_the_sql_the_writer_runs(monkeypatch):
    """The preflight list holds a COPY of the write for type deduction: the writer must execute exactly that SQL."""
    from scripts.preflight_db_updates import TRADE_LIFECYCLE_UPDATES
    norm = lambda q: " ".join(q.split())                      # noqa: E731
    [copy] = [q for name, q in TRADE_LIFECYCLE_UPDATES if name.startswith("breakout_pp_exit._store_day0_facts")]
    conn = _Conn([])
    monkeypatch.setattr(bpe, "get_pool", AsyncMock(return_value=_Pool(conn)))
    assert asyncio.run(bpe._store_day0_facts(701, dict(FACTS_REACHED), "paper")) is True
    [ran] = conn.fetchvals
    assert norm(ran[0]) == norm(copy)
    assert ran[1:] == (701, FACTS_REACHED, "breakout_pp", "paper")


def test_the_column_has_exactly_one_writer():
    from scripts.audit_column_writes import ALLOWED_WRITERS
    assert ALLOWED_WRITERS["breakout_day0_pp"] == {"breakout_pp_exit._store_day0_facts"}


def test_ruled_a_target_touch_whose_limit_did_not_fill_is_not_a_third_sold():
    """Review finding 3 (2026-10-30) — RULED 2026-10-29 ("Go with rec": follow what actually filled). The reviewer's case
    (fill 10.30, stop 10.10, target 10.70; session 1 trades 10.71 and closes 10.45 under a 20-day of 10.50;
    partial_taken False because the resting limit did not fill): the trail is NOT live on session 1, and on session 3
    (close above the fill) the third still applies — 'session_third' with nothing resting, 'cancel_resting_third' (cancel
    the +2R limit, then sell the third at the close — his ruling 2026-10-29 late, "option a") while it still rests. A
    third that really filled (partial_taken) turns the trail live and skips the session-3 third, as before."""
    fill, stop = 10.30, 10.10
    assert rules.target_price(fill, stop) == pytest.approx(10.70)
    day0 = {"v": rules.DAY0_FACTS_VERSION, "stopped": False, "peak": 10.40, "exit_price": None, "exit_minute": None,
            "partial_price": None, "partial_minute": None, "stop_in_force": None}
    closes_before = [10.50] * 20
    s1 = {"o": 10.35, "h": 10.71, "l": 10.30, "c": 10.45}
    t = rules.trail_decision(closes_before=closes_before, fwd=[s1], partial_taken=False)
    assert t["trail_live"] is False and t["sell"] is False          # a touch is not a sale
    t = rules.trail_decision(closes_before=closes_before, fwd=[s1], partial_taken=True)
    assert t["trail_live"] is True and t["sell"] is True            # a third that FILLED starts the trail
    s2 = {"o": 10.45, "h": 10.60, "l": 10.40, "c": 10.55}
    s3 = {"o": 10.55, "h": 10.60, "l": 10.40, "c": 10.46}
    kw = dict(fill=fill, stop=stop, day0=day0, fwd=[s1, s2, s3])
    assert rules.session3_decision(**kw, partial_taken=False) == "session_third"
    assert rules.session3_decision(**kw, partial_taken=False, third_resting=True) == "cancel_resting_third"
    assert rules.CANCEL_RESTING_THIRD == "cancel_resting_third"
    # at or under the fill on session 3 a resting limit is left alone (nothing to sell at the close)
    s3_low = dict(s3, c=10.30)
    assert rules.session3_decision(fill=fill, stop=stop, day0=day0, fwd=[s1, s2, s3_low], partial_taken=False,
                                   third_resting=True) is None
    assert rules.session3_decision(**kw, partial_taken=True) is None
    assert rules.session3_decision(**kw, partial_taken=True, third_resting=True) is None
    # a day-0 MODELLED third (the minute walk's partial_price) is not a sale either
    d0 = dict(day0, partial_price=10.70, partial_minute=30)
    assert rules.session3_decision(fill=fill, stop=stop, day0=d0, fwd=[s1, s2, s3], partial_taken=False) == \
        "session_third"
    assert rules.third_sold(partial_taken=False) is False and rules.third_sold(partial_taken=True) is True


class _Broker:
    """The paper broker for the session-3 cancel: `cancel_order` and the confirmation reads (`get_order`, oldest first;
    the last answer repeats). Records the order of the calls against the audit log (the marker must come FIRST)."""

    def __init__(self, monkeypatch, calls, reads, *, accepted=True, legs=None):
        self.log, self.reads, self.accepted = calls.setdefault("seq", []), list(reads), accepted
        self.legs = dict(legs or {})         # leg order id -> its read (the OCO's sibling stop)
        self.timeouts: list = []
        monkeypatch.setattr(bpe.alpaca, "cancel_order", self._cancel)
        monkeypatch.setattr(bpe.alpaca, "get_order", self._get)
        monkeypatch.setattr(bpe.asyncio, "sleep", AsyncMock())

        async def _audit(evt, *a, **k):
            self.log.append(("audit", evt, a[1] if len(a) > 1 else None))
        calls["bpe_audit"].side_effect = _audit

    async def _cancel(self, oid, account_mode=None):
        self.log.append(("cancel", oid, account_mode))
        return self.accepted

    async def _get(self, oid, account_mode=None, timeout=None):
        self.log.append(("get", oid, account_mode))
        self.timeouts.append(timeout)
        assert timeout is not None and timeout <= 5.0, "finding 3: every confirmation read is bounded"
        if oid in self.legs:
            return self.legs[oid]
        return self.reads.pop(0) if len(self.reads) > 1 else self.reads[0]

    def withdrawals(self):
        return [x for x in self.log if x[0] == "audit" and x[1] == bpe.PLANNED_THIRD_CANCEL_WITHDRAWN]


_S3_ABOVE = {"o": 10.40, "h": 10.50, "l": 10.35, "c": 10.46}
_S12 = [(10.40, 10.52, 10.35, 10.45), (10.45, 10.50, 10.35, 10.42)]


def test_1545_session3_with_the_2r_third_resting_cancels_it_then_sells_the_third_at_the_close(monkeypatch):
    """His ruling 2026-10-29 late ("option a"): the close above the fill and the +2R limit still resting -> the marker,
    THEN the cancel, the broker's confirmation, the order row closed (so execute_partial_exit's dedup sees no open
    third), and the third — the cancelled limit's OWN size — sold at the close."""
    conn, calls = _install(monkeypatch, _row(), today=S3, today_bar=_S3_ABOVE, resting="lim-9", fwd_bars=_S12)
    br = _Broker(monkeypatch, calls, [{"id": "lim-9", "status": "pending_cancel", "qty": 3, "filled_qty": 0},
                                      {"id": "lim-9", "status": "canceled", "qty": 3, "filled_qty": 0}])
    out = asyncio.run(lt.run_partial_exits(S3))
    assert out == [{"ticker": "BRK", "action": "partial_submitted", "shares": 3}]
    calls["execute_partial_exit"].assert_awaited_once_with(701, 3)
    calls["execute_full_exit"].assert_not_awaited()
    seq = br.log
    assert seq[0][:2] == ("audit", bpe.PLANNED_THIRD_CANCEL) and seq[1] == ("cancel", "lim-9", "paper")
    assert not br.withdrawals()                                     # the step sold: the marker stands
    closed = [a for a in conn.executed if "UPDATE mi_live_orders SET status = 'cancelled'" in a[0]]
    assert len(closed) == 1 and closed[0][1:3] == ("lim-9", 701)
    assert list(closed[0][3]) == list(om.PENDING_EXIT_TERMINAL_STATUSES)
    ev = [c.args[0] for c in calls["log_audit_event"].await_args_list]
    assert "breakout_pp_third_cancelled_for_session_third" in ev and "breakout_pp_session_third" in ev
    marker = [c.args for c in calls["bpe_audit"].await_args_list if c.args[0] == bpe.PLANNED_THIRD_CANCEL]
    assert json.loads(marker[0][2])["trade_id"] == 701 and json.loads(marker[0][2])["order_id"] == "lim-9"
    msg = calls["send_telegram_message"].await_args.args[0]
    assert "cancelled" in msg and "once it sells" in msg


def test_1545_the_race_a_limit_that_fills_while_being_cancelled_is_the_third_and_nothing_more_is_sold(monkeypatch):
    for read in ({"id": "lim-9", "status": "filled", "qty": 3, "filled_qty": 3},
                 {"id": "lim-9", "status": "canceled", "qty": 3, "filled_qty": 1}):     # in full, or in part
        conn, calls = _install(monkeypatch, _row(), today=S3, today_bar=_S3_ABOVE, resting="lim-9", fwd_bars=_S12)
        _Broker(monkeypatch, calls, [read])
        out = asyncio.run(lt.run_partial_exits(S3))
        assert out == [{"ticker": "BRK", "action": "breakout_pp_third_filled_in_race", "session": 3}]
        calls["execute_partial_exit"].assert_not_awaited()
        calls["execute_full_exit"].assert_not_awaited()
        # the order row is left to the trade stream (it books the fill and re-protects any unfilled rest)
        assert not [a for a in conn.executed if "UPDATE mi_live_orders" in a[0]]
        assert any(c.args[0] == "breakout_pp_third_filled_in_race" for c in calls["log_audit_event"].await_args_list)


def test_1545_a_cancel_the_broker_does_not_confirm_sells_nothing_and_he_is_told(monkeypatch):
    """Findings 1 + 2 (pre-merge 2026-10-31): an unconfirmed cancel sells nothing — AND never leaves the third to the
    5-minute coverage repair: the marker is WITHDRAWN (a late settle is the stream's ordinary OCO-parent re-protect)
    and the cover is converged from broker truth at once (a no-op while the limit really rests). The page says
    plainly that no third was sold and that the +2R limit will not be re-placed (finding 6: his open question)."""
    for reads, accepted in (([{"id": "lim-9", "status": "new", "qty": 3, "filled_qty": 0}], True),   # still live
                            ([{"id": "lim-9", "status": "new", "qty": 3, "filled_qty": 0}], False),  # refused
                            ([None], True)):                                                        # unreadable
        conn, calls = _install(monkeypatch, _row(), today=S3, today_bar=_S3_ABOVE, resting="lim-9", fwd_bars=_S12)
        br = _Broker(monkeypatch, calls, reads, accepted=accepted)
        out = asyncio.run(lt.run_partial_exits(S3))
        assert out == [{"ticker": "BRK", "action": "breakout_pp_third_cancel_unconfirmed", "session": 3}]
        calls["execute_partial_exit"].assert_not_awaited()
        assert not [a for a in conn.executed if "UPDATE mi_live_orders" in a[0]]      # a live limit's row stays open
        [wd] = br.withdrawals()
        assert json.loads(wd[2]) | {"trade_id": 701, "order_id": "lim-9"} == json.loads(wd[2])
        calls["ensure_cov"].assert_awaited_once_with(701, "BRK", 9.0, STOP0, "breakout_v1", "paper")
        msg = calls["send_telegram_message"].await_args.args[0]
        assert "No third was sold" in msg and "will not be re-placed" in msg


def test_1545_a_resting_third_whose_order_id_cannot_be_read_is_never_cancelled_or_doubled(monkeypatch):
    """`resting_third` fails safe to (True, None) on an unreadable book: there is nothing to cancel, so nothing is sold."""
    conn, calls = _install(monkeypatch, _row(), today=S3, today_bar=_S3_ABOVE, resting=None, fwd_bars=_S12)
    calls["resting_third"].return_value = (True, None)
    br = _Broker(monkeypatch, calls, [None])
    out = asyncio.run(lt.run_partial_exits(S3))
    assert out == [{"ticker": "BRK", "action": "breakout_pp_third_cancel_unconfirmed", "session": 3}]
    calls["execute_partial_exit"].assert_not_awaited()
    assert not [x for x in br.log if x[0] == "cancel"]


def test_1545_a_failed_sale_after_the_cancel_re_protects_the_third_from_broker_truth(monkeypatch):
    conn, calls = _install(monkeypatch, _row(), today=S3, today_bar=_S3_ABOVE, resting="lim-9", fwd_bars=_S12)
    _Broker(monkeypatch, calls, [{"id": "lim-9", "status": "canceled", "qty": 3, "filled_qty": 0}])
    calls["execute_partial_exit"].return_value = False
    cov = AsyncMock(return_value="stop placed for 3 sh")
    monkeypatch.setattr(om, "_ensure_stop_coverage", cov)
    monkeypatch.setattr(bpe.alpaca, "get_position", AsyncMock(return_value={"qty": 9.0}))
    out = asyncio.run(lt.run_partial_exits(S3))
    assert out == [{"ticker": "BRK", "action": "partial_failed", "shares": 3}]
    cov.assert_awaited_once_with(701, "BRK", 9.0, STOP0, "breakout_v1", "paper")
    assert any(c.args[0] == "breakout_pp_session_third_unsold_reprotected"
               for c in calls["log_audit_event"].await_args_list)


def test_1545_a_sale_that_raises_after_the_cancel_still_re_protects_the_third_and_pages(monkeypatch):
    """The cancel is confirmed (its OCO stop is gone) and execute_partial_exit RAISES (a lock/pool timeout): the third's
    shares are re-protected from broker truth exactly as on a False, he is paged, and the pass returns partial_failed."""
    conn, calls = _install(monkeypatch, _row(), today=S3, today_bar=_S3_ABOVE, resting="lim-9", fwd_bars=_S12)
    _Broker(monkeypatch, calls, [{"id": "lim-9", "status": "canceled", "qty": 3, "filled_qty": 0}])
    calls["execute_partial_exit"].side_effect = TimeoutError("advisory lock acquire timed out")
    cov = AsyncMock(return_value="stop placed for 3 sh")
    monkeypatch.setattr(om, "_ensure_stop_coverage", cov)
    monkeypatch.setattr(bpe.alpaca, "get_position", AsyncMock(return_value={"qty": 9.0}))
    out = asyncio.run(lt.run_partial_exits(S3))
    assert out == [{"ticker": "BRK", "action": "partial_failed", "shares": 3}]
    cov.assert_awaited_once_with(701, "BRK", 9.0, STOP0, "breakout_v1", "paper")
    rep = [c.args for c in calls["log_audit_event"].await_args_list
           if c.args[0] == "breakout_pp_session_third_unsold_reprotected"]
    assert len(rep) == 1 and "TimeoutError" in json.loads(rep[0][2])["sale_error"]
    assert "NOT sold" in calls["send_telegram_message"].await_args.args[0]


def test_1545_a_breakout_row_that_raises_does_not_skip_the_later_trades_in_the_pass(monkeypatch):
    """A raise out of the session-3 step (no cancel happened, so it propagates) is audited for THAT row and the pass
    carries on; the row after it is still evaluated."""
    conn, calls = _install(monkeypatch, _row(), today=S3, today_bar=_S3_ABOVE, resting=None, fwd_bars=_S12)
    conn.rows = [_row(), dict(_row(), id=702, ticker="BRK2")]
    seen = []

    async def _s3(trade, today, state, bar):
        seen.append(trade["id"])
        if trade["id"] == 701:
            raise RuntimeError("boom")
        return {"ticker": trade["ticker"], "action": "no_partial", "session": 3}

    monkeypatch.setattr(lt, "_breakout_pp_session3", _s3)
    out = asyncio.run(lt.run_partial_exits(S3))
    assert seen == [701, 702]
    assert out[0] == {"ticker": "BRK", "action": "breakout_pp_error"}
    assert out[1]["ticker"] == "BRK2"
    assert any(c.args[0] == "breakout_pp_session3_raised" for c in calls["log_audit_event"].await_args_list)


def test_1545_with_no_breakout_day_record_a_resting_third_is_still_cancelled_before_the_third(monkeypatch):
    conn, calls = _install(monkeypatch, _row(breakout_day0_pp=None, filled_at=None), today=S3, today_bar=_S3_ABOVE,
                           resting="lim-9", fwd_bars=_S12)
    _Broker(monkeypatch, calls, [{"id": "lim-9", "status": "canceled", "qty": 3, "filled_qty": 0}])
    out = asyncio.run(lt.run_partial_exits(S3))
    calls["execute_partial_exit"].assert_awaited_once_with(701, 3)
    calls["execute_full_exit"].assert_not_awaited()
    assert out == [{"ticker": "BRK", "action": "partial_submitted", "shares": 3}]


def test_1545_at_or_under_the_fill_a_resting_third_is_left_alone(monkeypatch):
    tb = {"o": 10.35, "h": 10.40, "l": 10.20, "c": 10.25}
    conn, calls = _install(monkeypatch, _row(), today=S3, today_bar=tb, resting="lim-9",
                           fwd_bars=[(10.40, 10.75, 10.35, 10.50), (10.45, 10.50, 10.30, 10.40)])
    br = _Broker(monkeypatch, calls, [None])
    asyncio.run(lt.run_partial_exits(S3))
    calls["execute_partial_exit"].assert_not_awaited()
    assert not [x for x in br.log if x[0] == "cancel"]


def test_1545_a_third_already_filled_is_not_asked_about_a_resting_order(monkeypatch):
    tb = {"o": 10.40, "h": 10.50, "l": 10.35, "c": 10.46}
    _conn, calls = _install(monkeypatch, _row(partial_taken=True, remaining_shares=6), today=S3, today_bar=tb,
                            fwd_bars=[(10.40, 10.52, 10.35, 10.45), (10.45, 10.50, 10.35, 10.42)])
    asyncio.run(lt.run_partial_exits(S3))
    calls["execute_partial_exit"].assert_not_awaited()
    calls["resting_third"].assert_not_awaited()


def test_resting_third_reads_the_open_partial_exits_with_the_shared_terminal_set_and_fails_safe(monkeypatch):
    seen = []

    class _C:
        async def fetchval(self, sql, *a):
            seen.append((sql, a))
            return "lim-1"
    monkeypatch.setattr(bpe, "get_pool", AsyncMock(return_value=_Pool(_C())))
    assert asyncio.run(bpe.resting_third(701)) == (True, "lim-1")
    sql, args = seen[0]
    assert "purpose = 'partial_exit'" in sql and args == (701, list(om.PENDING_EXIT_TERMINAL_STATUSES))

    class _None:
        async def fetchval(self, sql, *a):
            return None
    monkeypatch.setattr(bpe, "get_pool", AsyncMock(return_value=_Pool(_None())))
    assert asyncio.run(bpe.resting_third(701)) == (False, None)

    audit = AsyncMock()
    monkeypatch.setattr(bpe, "log_audit_event", audit)
    monkeypatch.setattr(bpe, "get_pool", AsyncMock(side_effect=RuntimeError("db down")))
    assert asyncio.run(bpe.resting_third(701)) == (True, None)         # unreadable -> resting: no second third
    assert audit.await_args.args[0] == "breakout_pp_resting_third_unreadable"


def test_1645_on_the_breakout_day_a_third_that_sold_lifts_a_stop_still_under_the_fill(monkeypatch):
    """The backstop for "after a third SOLD the stop rests at the fill" on the breakout day itself (the shared entry-day
    guard skips the rest of the job that day); the move itself is `finalize_partial_exit`'s at the fill. No third sold
    -> nothing moves (his ruling 2026-10-29 late: the stop stays until a third actually sells)."""
    tb = {"o": 10.2, "h": 10.8, "l": 10.1, "c": 10.55}
    _conn, calls = _install(monkeypatch, _row(partial_taken=True, remaining_shares=6), today=ALERT, today_bar=tb)
    assert asyncio.run(lt.update_open_positions_live(ALERT)) == []
    calls["update_stop"].assert_awaited_once_with(701, 10.30, stop_source="breakeven")
    _conn, calls = _install(monkeypatch, _row(), today=ALERT, today_bar=tb)
    asyncio.run(lt.update_open_positions_live(ALERT))
    calls["update_stop"].assert_not_awaited()


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 5. pre-merge 2026-10-31 — the unstopped-third window (findings 1, 2, 3 + advisor item 1): one defect
# ═══════════════════════════════════════════════════════════════════════════════════════════════
_PENDING_CANCEL = {"id": "lim-9", "status": "pending_cancel", "qty": 3, "filled_qty": 0}
_CANCELLED_EMPTY = {"id": "lim-9", "status": "canceled", "qty": 3, "filled_qty": 0}
_OCO_RAW = {"id": "lim-9", "order_class": "oco", "type": "limit", "side": "sell", "qty": 3.0,
            "legs": [{"id": "leg-9", "type": "stop", "status": "held", "qty": 3.0, "stop_price": 10.10}]}


def _marker_pool(monkeypatch, rows):
    """A fake audit log for the marker readers (`rows` newest first, as the query orders them)."""
    class _C:
        async def fetch(self, sql, *a):
            assert sorted(a[0]) == sorted([bpe.PLANNED_THIRD_CANCEL, bpe.PLANNED_THIRD_CANCEL_WITHDRAWN])
            return rows
    monkeypatch.setattr(bpe, "get_pool", AsyncMock(return_value=_Pool(_C())))


def test_1545_a_cancel_that_settles_after_the_deadline_is_handed_back_to_the_stream_and_the_third_is_covered(monkeypatch):
    """Finding 1 case 1 + finding 3: the broker accepts the cancel but it is still 'pending_cancel' when the WALL-CLOCK
    deadline ends the wait (each read bounded <= 5 s). The step sells nothing and (a) WITHDRAWS the marker, so when the
    cancel settles later the stream treats it as any OCO-parent cancel (re-protect from broker truth), and (b) converges
    cover from broker truth at once — a no-op while the limit rests, the cover if the settle already raced the
    withdrawal. No bare stop is ever placed on top of a possibly-live leg (that is two sells for one third)."""
    conn, calls = _install(monkeypatch, _row(), today=S3, today_bar=_S3_ABOVE, resting="lim-9", fwd_bars=_S12)
    br = _Broker(monkeypatch, calls, [_PENDING_CANCEL])
    ticks = iter(range(0, 10_000))
    monkeypatch.setattr(bpe, "_clock", lambda: float(next(ticks)))            # a second a read: the deadline ends it
    place = AsyncMock()
    monkeypatch.setattr(bpe.alpaca, "place_stop_order", place, raising=False)
    out = asyncio.run(lt.run_partial_exits(S3))
    assert out == [{"ticker": "BRK", "action": "breakout_pp_third_cancel_unconfirmed", "session": 3}]
    reads = [x for x in br.log if x[0] == "get"]
    assert 2 <= len(reads) < bpe.CANCEL_POLL_ATTEMPTS                         # the clock ended the wait, not the cap
    assert bpe.CANCEL_READ_TIMEOUT_S <= 5.0 and all(t == bpe.CANCEL_READ_TIMEOUT_S for t in br.timeouts)
    calls["execute_partial_exit"].assert_not_awaited()
    [wd] = br.withdrawals()
    d = json.loads(wd[2])
    assert (d["trade_id"], d["order_id"]) == (701, "lim-9")
    seq = [x[:2] for x in br.log]
    assert seq.index(("audit", bpe.PLANNED_THIRD_CANCEL_WITHDRAWN)) > max(i for i, x in enumerate(seq) if x[0] == "get")
    calls["ensure_cov"].assert_awaited_once_with(701, "BRK", 9.0, STOP0, "breakout_v1", "paper")
    place.assert_not_awaited()
    assert not [a for a in conn.executed if "UPDATE mi_live_orders" in a[0]]       # a live limit's row stays open
    msg = calls["send_telegram_message"].await_args.args[0]
    assert "No third was sold" in msg and "will not be re-placed" in msg
    # the stream's late settle: the withdrawal (newer) outranks the marker -> NOT planned -> the ordinary re-protect;
    # the POLL's ban reads the marker alone -> still banned (one third ever stays his question, finding 6)
    rows = [{"event_type": bpe.PLANNED_THIRD_CANCEL_WITHDRAWN, "detail": json.dumps({"trade_id": 701, "order_id": "lim-9"})},
            {"event_type": bpe.PLANNED_THIRD_CANCEL, "detail": json.dumps({"trade_id": 701, "order_id": "lim-9"})}]
    _marker_pool(monkeypatch, rows)
    assert asyncio.run(bpe.planned_third_cancel_marked(701, "lim-9")) is False
    assert asyncio.run(bpe.third_replacement_banned(701)) is True
    _marker_pool(monkeypatch, rows[1:])                                         # the marker alone: still planned
    assert asyncio.run(bpe.planned_third_cancel_marked(701, "lim-9")) is True


def test_1545_a_cancel_that_settles_on_the_last_read_still_sells_the_third_and_keeps_the_marker(monkeypatch):
    """The read BEFORE the withdrawal decides: a settle seen on the last read is the 'dead' path (the third sold at the
    close) — never 'not selling' announced and then a sale."""
    conn, calls = _install(monkeypatch, _row(), today=S3, today_bar=_S3_ABOVE, resting="lim-9", fwd_bars=_S12)
    br = _Broker(monkeypatch, calls, [_PENDING_CANCEL, _PENDING_CANCEL, _PENDING_CANCEL, _CANCELLED_EMPTY])
    out = asyncio.run(lt.run_partial_exits(S3))
    assert out == [{"ticker": "BRK", "action": "partial_submitted", "shares": 3}]
    calls["execute_partial_exit"].assert_awaited_once_with(701, 3)
    assert not br.withdrawals() and not calls["ensure_cov"].await_count


def test_1545_a_stop_leg_fill_during_the_cancel_is_the_third_sold_at_its_stop_and_nothing_more_is_sold(monkeypatch):
    """Finding 2: the OCO's sibling STOP leg fills while the parent is being cancelled — the parent reads 'canceled'
    with nothing filled (which alone reads 'dead' and sold a SECOND third). The leg is read (from the stored OCO row's
    legs, or a nested read): a leg fill IS the third, sold at its stop. The parent's row is closed; nothing is sold."""
    for source in ("stored_row", "nested_read"):
        conn, calls = _install(monkeypatch, _row(), today=S3, today_bar=_S3_ABOVE, resting="lim-9", fwd_bars=_S12)
        parent = dict(_CANCELLED_EMPTY)
        if source == "stored_row":
            conn.raw = dict(_OCO_RAW)
        else:
            parent["legs"] = list(_OCO_RAW["legs"])
        br = _Broker(monkeypatch, calls, [parent],
                     legs={"leg-9": {"id": "leg-9", "status": "filled", "qty": 3, "filled_qty": 3}})
        out = asyncio.run(lt.run_partial_exits(S3))
        assert out == [{"ticker": "BRK", "action": "breakout_pp_third_stopped_in_race", "session": 3}], source
        calls["execute_partial_exit"].assert_not_awaited()
        calls["execute_full_exit"].assert_not_awaited()
        assert ("get", "leg-9", "paper") in br.log
        closed = [a for a in conn.executed if "UPDATE mi_live_orders SET status = 'cancelled'" in a[0]]
        assert len(closed) == 1 and closed[0][1:3] == ("lim-9", 701)
        assert any(c.args[0] == "breakout_pp_third_stopped_in_race" for c in calls["log_audit_event"].await_args_list)
        assert not br.withdrawals() and not calls["ensure_cov"].await_count   # the third is gone: nothing to cover
    # the control: the leg still HELD when the parent died -> the whole OCO unwound unfilled -> the third at the close
    conn, calls = _install(monkeypatch, _row(), today=S3, today_bar=_S3_ABOVE, resting="lim-9", fwd_bars=_S12)
    conn.raw = dict(_OCO_RAW)
    _Broker(monkeypatch, calls, [_CANCELLED_EMPTY],
            legs={"leg-9": {"id": "leg-9", "status": "canceled", "qty": 3, "filled_qty": 0}})
    out = asyncio.run(lt.run_partial_exits(S3))
    assert out == [{"ticker": "BRK", "action": "partial_submitted", "shares": 3}]


def test_1545_a_dead_parent_whose_stop_leg_cannot_be_read_sells_nothing_and_covers_from_broker_truth(monkeypatch):
    """A dead parent with a leg that will not read: a leg fill cannot be ruled out, so no third is sold (a second third
    is the worse error). The dead row is closed, the marker withdrawn, and cover converged from the broker's position
    (which already reflects a leg fill, if there was one)."""
    conn, calls = _install(monkeypatch, _row(), today=S3, today_bar=_S3_ABOVE, resting="lim-9", fwd_bars=_S12)
    conn.raw = dict(_OCO_RAW)
    br = _Broker(monkeypatch, calls, [_CANCELLED_EMPTY], legs={"leg-9": None})
    out = asyncio.run(lt.run_partial_exits(S3))
    assert out == [{"ticker": "BRK", "action": "breakout_pp_third_cancel_unconfirmed", "session": 3}]
    calls["execute_partial_exit"].assert_not_awaited()
    assert len([a for a in conn.executed if "UPDATE mi_live_orders SET status = 'cancelled'" in a[0]]) == 1
    assert len(br.withdrawals()) == 1
    calls["ensure_cov"].assert_awaited_once()


def test_1545_an_order_row_that_cannot_be_closed_after_a_confirmed_cancel_sells_nothing_and_covers_the_third(monkeypatch):
    """Finding 1 case 2: the cancel is confirmed dead but the order-row close RAISES (twice). The step must not trust
    the DB (the dedup would refuse the sale on the stale row; `_ensure_stop_coverage` would net the dead limit as
    pending and read 'covered'): the result is 'dead' + row_update_error, nothing is sold, the marker is withdrawn,
    the row close is tried ONCE MORE inside the re-protect and cover is converged from broker truth. He is told no
    third was sold."""
    conn, calls = _install(monkeypatch, _row(), today=S3, today_bar=_S3_ABOVE, resting="lim-9", fwd_bars=_S12)
    conn.fail_order_close = 2
    br = _Broker(monkeypatch, calls, [_CANCELLED_EMPTY])
    out = asyncio.run(lt.run_partial_exits(S3))
    assert out == [{"ticker": "BRK", "action": "breakout_pp_third_cancel_unconfirmed", "session": 3}]
    calls["execute_partial_exit"].assert_not_awaited()
    closes = [a for a in conn.executed if "UPDATE mi_live_orders SET status = 'cancelled'" in a[0]]
    assert len(closes) == 3                                                  # two in the step, one in the re-protect
    assert len(br.withdrawals()) == 1
    calls["ensure_cov"].assert_awaited_once_with(701, "BRK", 9.0, STOP0, "breakout_v1", "paper")
    unc = [c.args for c in calls["log_audit_event"].await_args_list if c.args[0] == "breakout_pp_third_cancel_unconfirmed"]
    assert json.loads(unc[0][2])["row_update_error"]
    assert "No third was sold" in calls["send_telegram_message"].await_args.args[0]


def test_1545_a_cancel_the_step_never_sent_withdraws_nothing_and_covers_nothing(monkeypatch):
    """No order id (an unreadable book) / a marker that could not be written: the OCO was never touched — nothing to
    hand back, nothing to cover."""
    conn, calls = _install(monkeypatch, _row(), today=S3, today_bar=_S3_ABOVE, resting=None, fwd_bars=_S12)
    calls["resting_third"].return_value = (True, None)
    br = _Broker(monkeypatch, calls, [None])
    asyncio.run(lt.run_partial_exits(S3))
    assert not br.withdrawals() and not calls["ensure_cov"].await_count
    conn, calls = _install(monkeypatch, _row(), today=S3, today_bar=_S3_ABOVE, resting="lim-9", fwd_bars=_S12)
    br = _Broker(monkeypatch, calls, [None])
    calls["bpe_audit"].side_effect = RuntimeError("audit log down")           # the marker cannot be written
    out = asyncio.run(lt.run_partial_exits(S3))
    assert out == [{"ticker": "BRK", "action": "breakout_pp_third_cancel_unconfirmed", "session": 3}]
    assert not [x for x in br.log if x[0] == "cancel"] and not calls["ensure_cov"].await_count


def test_the_poll_ban_fails_closed_and_the_stream_reader_fails_open(monkeypatch):
    """Finding 4: an unreadable audit log -> the poll places no +2R limit (banned); the stream reads 'not planned'
    (it re-protects — the safe side for shares). Both are the safe direction for their caller."""
    monkeypatch.setattr(bpe, "get_pool", AsyncMock(side_effect=RuntimeError("db down")))
    assert asyncio.run(bpe.third_replacement_banned(701)) is True
    assert asyncio.run(bpe.planned_third_cancel_marked(701, "lim-9")) is False
    _marker_pool(monkeypatch, [])
    assert asyncio.run(bpe.third_replacement_banned(701)) is False


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 6. pre-merge 2026-10-31 (advisor item 2) — a stop LOWERED after the fill is the exit's R
# ═══════════════════════════════════════════════════════════════════════════════════════════════
class TestTheLoweredStopIsTheExitsR:
    """His ruling 2026-10-29 (the stop at the fill): a minute after the fill the stop may be LOWERED to the true low —
    the row's `hard_stop` moves with it (`breakout_v1_entry._record_stop_lowered`), so the pp exit's R, its +2R target
    and its stall cut are the walk's (the day's low at the fill), not the resting order's placed stop. The harness
    exercises that trade: the replay on the lowered stop equals `walk_pp` on the lowered stop and DIFFERS from the
    replay on the placed stop (a non-vacuous check), and the live readers frame on `hard_stop`."""
    PLACED, LOWERED = 10.10, 10.00          # fill 10.30: R 0.20 -> +2R 10.70, cut 10.50 | R 0.30 -> +2R 10.90, cut 10.60

    def test_the_replay_on_the_lowered_stop_equals_the_walk_and_differs_from_the_placed_stop(self):
        tail = [(10.40, 10.75, 10.35, 10.50), (10.50, 10.55, 10.40, 10.52), (10.52, 10.58, 10.45, 10.56),
                (10.56, 10.95, 10.50, 10.90), (10.90, 10.95, 10.60, 10.70)]
        bars, e = _xp_bars(tail)
        mb = _mb(None)
        want_l, got_l = _both(bars, e, mb, fill=XP_FILL, stop=self.LOWERED)
        _same(want_l, got_l)
        want_p, got_p = _both(bars, e, mb, fill=XP_FILL, stop=self.PLACED)
        _same(want_p, got_p)
        # session 1's high 10.75 touches the PLACED target (10.70) but not the LOWERED one (10.90): on the placed stop
        # a third goes at 10.70 on session 1; on the lowered stop no third until the session-3 third at the close
        assert got_p["events"][0][:2] == (1, "partial_r") and got_p["events"][0][2] == pytest.approx(10.70)
        assert got_l["events"][0][:2] == (3, "partial") and got_l["events"][0][2] == pytest.approx(10.56)
        assert [tuple(x) for x in got_l["events"]] != [tuple(x) for x in got_p["events"]]
        assert rules.target_price(XP_FILL, self.LOWERED) == pytest.approx(10.90)
        assert rules.cut_level(XP_FILL, self.LOWERED) == pytest.approx(10.60)

    def test_the_1545_step_frames_the_stall_cut_on_hard_stop_not_stop_price(self, monkeypatch):
        """Session 3 at 15:45: the forming bar's high 10.55 reaches the PLACED +1R (10.50) but not the LOWERED one
        (10.60). A row whose `hard_stop` is the lowered stop is CUT; one whose hard_stop is the placed stop sells the
        session-3 third. The columns are crossed on purpose: it is `hard_stop` the step reads, never `stop_price`."""
        tb = {"o": 10.50, "h": 10.55, "l": 10.45, "c": 10.52}
        facts = dict(FACTS_REACHED, peak=10.45)
        fwd = [(10.40, 10.48, 10.35, 10.45), (10.45, 10.47, 10.35, 10.42)]
        _c, calls = _install(monkeypatch, _row(hard_stop=self.LOWERED, stop_price=self.PLACED, breakout_day0_pp=facts),
                             today=S3, today_bar=tb, fwd_bars=fwd)
        asyncio.run(lt.run_partial_exits(S3))
        calls["execute_full_exit"].assert_awaited_once_with(701, "breakout_stall_cut")
        calls["execute_partial_exit"].assert_not_awaited()
        _c, calls = _install(monkeypatch, _row(hard_stop=self.PLACED, stop_price=self.LOWERED, breakout_day0_pp=facts),
                             today=S3, today_bar=tb, fwd_bars=fwd)
        asyncio.run(lt.run_partial_exits(S3))
        calls["execute_full_exit"].assert_not_awaited()
        calls["execute_partial_exit"].assert_awaited_once_with(701, 3)

    def test_the_day0_facts_frame_the_2r_target_on_hard_stop(self, monkeypatch):
        """The breakout day's minutes print 10.75 after the fill: on the placed stop that is a +2R touch (10.70), on
        the lowered stop it is not (10.90). `ensure_day0_facts` reads `hard_stop`."""
        open_dt = datetime(2026, 10, 26, 9, 30, tzinfo=ET)
        bars = [{"t_et": open_dt + dt.timedelta(minutes=m), "open": 10.30, "high": 10.35, "low": 10.28}
                for m in range(0, 8)] + [{"t_et": open_dt + dt.timedelta(minutes=9), "open": 10.40, "high": 10.75,
                                           "low": 10.38}]
        monkeypatch.setattr(bpe.alpaca, "get_minute_bars_range", AsyncMock(return_value=bars))
        monkeypatch.setattr(bpe, "_store_day0_facts", AsyncMock(return_value=True))
        monkeypatch.setattr(bpe, "log_audit_event", AsyncMock())
        lowered = asyncio.run(bpe.ensure_day0_facts(_row(hard_stop=self.LOWERED, stop_price=self.PLACED,
                                                         breakout_day0_pp=None)))
        placed = asyncio.run(bpe.ensure_day0_facts(_row(hard_stop=self.PLACED, stop_price=self.LOWERED,
                                                        breakout_day0_pp=None)))
        assert lowered["partial_price"] is None and placed["partial_price"] == pytest.approx(10.70)


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 7. pre-merge 2026-10-31 (advisor item 3) — a fill the minute job never checked is checked by the 16:45 pass
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def test_1645_a_fill_the_minute_job_never_checked_is_checked_before_the_day0_facts(monkeypatch):
    """A 15:55 fill has no tick after it. The 16:45 pass (the next pass that exists — the minute job never visits a row
    from an earlier day) runs the stop-at-the-fill check FIRST, then captures the day-0 facts on the row AS CHECKED
    (a lowered stop changes the +2R target they model); a sale (too wide) ends the row's pass; a row already checked
    costs one marker read and the facts run as before."""
    from agents.market_intelligence.broker import breakout_v1_entry as bv1
    tb = {"o": 10.2, "h": 10.8, "l": 10.1, "c": 10.55}
    seen: list = []

    def _chk_returning(label):
        async def _chk(trade, now_et=None):
            seen.append(("check", trade["hard_stop"], now_et))
            return label
        return _chk

    async def _facts(trade):
        seen.append(("facts", trade["hard_stop"]))
        return FACTS_REACHED

    monkeypatch.setattr(bpe, "ensure_day0_facts", _facts)
    # lowered: the check runs first, at 16:45 on the breakout day; the facts see the LOWERED stop
    conn, _calls = _install(monkeypatch, _row(breakout_day0_pp=None), today=ALERT, today_bar=tb)
    conn.fetchrow_result = {"stop_price": 10.00, "hard_stop": 10.00, "stop_order_id": "gtc-2", "remaining_shares": 9,
                            "status": "filled", "risk_dollars_actual": 2.7}
    monkeypatch.setattr(bv1, "check_stop_at_fill_after_close", _chk_returning("fill_stop_lowered"))
    asyncio.run(lt.update_open_positions_live(ALERT))
    assert seen == [("check", STOP0, datetime(2026, 10, 26, 16, 45, tzinfo=ET)), ("facts", 10.00)]
    # sold too wide: the row's pass ends — no facts
    seen.clear()
    conn, _calls = _install(monkeypatch, _row(breakout_day0_pp=None), today=ALERT, today_bar=tb)
    monkeypatch.setattr(bv1, "check_stop_at_fill_after_close", _chk_returning("fill_sold_too_wide"))
    out = asyncio.run(lt.update_open_positions_live(ALERT))
    assert seen == [("check", STOP0, datetime(2026, 10, 26, 16, 45, tzinfo=ET))]
    assert out == [{"ticker": "BRK", "action": "breakout_v1_fill_stop_sold"}]
    # already checked: the facts run on the row as it is
    seen.clear()
    conn, _calls = _install(monkeypatch, _row(breakout_day0_pp=None), today=ALERT, today_bar=tb)
    monkeypatch.setattr(bv1, "check_stop_at_fill_after_close", _chk_returning("fill_checked"))
    asyncio.run(lt.update_open_positions_live(ALERT))
    assert seen == [("check", STOP0, datetime(2026, 10, 26, 16, 45, tzinfo=ET)), ("facts", STOP0)]
