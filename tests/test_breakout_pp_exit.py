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


def live_replay(*, fill: float, stop: float, closes_before, fwd: list[dict], facts: dict, adr20: float,
                horizon: int = cb.EXIT_HORIZON) -> dict:
    """The live system on this path, session by session, deciding ONLY with breakout_pp_rules (see the module docstring).
    Returns `walk_exit`'s shape so it compares with `walk_pp_arms` directly."""
    fill, stop = float(fill), float(stop)
    risk = fill - stop
    F = rules.PARTIAL_FRAC
    events: list = []
    pnl, remaining = 0.0, 1.0
    partial = False                        # the row's partial_taken
    stop_now = stop                        # the broker's resting stop (the row's stop_price)
    closes_before = [float(x) for x in closes_before]

    def out(status, held):
        return cb._outcome(status, pnl, risk, fill, adr20, held, events)

    def third(j, kind, px, close_j):       # a third sold -> the stop to cost (execute_partial_exit does it in the call)
        nonlocal pnl, remaining, partial, stop_now
        events.append((j, kind, px, F))
        pnl += (px - fill) * F
        remaining -= F
        partial = True
        stop_now = rules.stop_after_third(stop_now, fill)
        events.append((j, "stop_to", stop_now, 0.0))
        if stop_now > close_j:
            events.append((j, "be_above_close", close_j, 0.0))

    # day 0 — the stored facts ARE the breakout day's minutes walked against the stop and the poll's +2R
    if facts["stopped"]:
        if facts["partial_price"] is not None:
            events.append((0, "partial_r", float(facts["partial_price"]), F))
            pnl += (float(facts["partial_price"]) - fill) * F
            remaining -= F
            events.append((0, "stop_to", float(facts["stop_in_force"]), 0.0))
        px = float(facts["exit_price"])
        events.append((0, "day0_gap" if px < float(facts["stop_in_force"]) else "day0_stop", px, remaining))
        pnl += (px - fill) * remaining
        return out("stopped_day0", 0)
    if facts["partial_price"] is not None:
        third(0, "partial_r", float(facts["partial_price"]), closes_before[-1])

    target = rules.target_price(fill, stop)
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
        if gap:                                            # the poll's +2R third (a gap open sells at the open)
            third(j, "partial_r", o, c)
        elif not partial and h >= target:
            third(j, "partial_r", target, c)
        d = rules.session3_decision(fill=fill, stop=stop, day0=facts, fwd=fwd[:j], partial_taken=partial)   # 15:45
        if d == "cut":
            events.append((j, "cut", c, remaining))
            pnl += (c - fill) * remaining
            return out("time_exit", j)
        if d == "session_third":
            third(j, "partial", c, c)
        t = rules.trail_decision(fill=fill, stop=stop, day0=facts, closes_before=closes_before, fwd=fwd[:j],
                                 partial_taken=partial)                                                     # 16:45
        if t["sell"] and j < n:                            # 19:02 PAPER DAY market sale -> fills at the next open
            opx = fwd[j]["o"]
            events.append((j + 1, "trail", opx, remaining))
            pnl += (opx - fill) * remaining
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


def _both(bars, e, mb, *, fill, stop, fill_minute=7, adr20=0.10, horizon=cb.EXIT_HORIZON):
    fwd, _cut = cb.forward_window(bars, np.arange(len(bars)), e, horizon)
    want_facts = json.loads(json.dumps(ppx.day0_facts(mb, fill=fill, stop=stop, fill_minute=fill_minute)))
    got_facts = rules.day0_facts(_mins(mb), fill=fill, stop=stop, fill_minute=fill_minute)
    assert got_facts == want_facts
    want = ppx.walk_pp_arms({"fill": fill, "stop": stop}, want_facts, closes_before=bars.c[:e + 1], fwd=fwd,
                            adr20=adr20, horizon=horizon, arms=("pp",))["pp"]
    got = live_replay(fill=fill, stop=stop, closes_before=list(bars.c[:e + 1]), fwd=_fwd_dicts(fwd), facts=got_facts,
                      adr20=adr20, horizon=horizon)
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

    async def fetch(self, *_a, **_k):
        return self.rows

    async def execute(self, *a, **_k):
        self.executed.append(a)

    async def fetchval(self, *a, **_k):
        self.fetchvals.append(a)
        return 1


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


def _install(monkeypatch, row, *, today, today_bar, fwd_bars=(), prior_close=10.0, step=None):
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
    calls["bpe_audit"] = AsyncMock()
    calls["bpe_page"] = AsyncMock()
    monkeypatch.setattr(bpe, "log_audit_event", calls["bpe_audit"])
    monkeypatch.setattr(bpe, "send_telegram_message", calls["bpe_page"])
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


def test_disclosed_a_target_touch_counts_as_the_third_even_when_the_resting_limit_did_not_fill():
    """Review finding 3 (2026-10-30), DISCLOSED, a fork for him (not changed in code): `partial_done_through` follows
    the walk — a daily high at +2R means the third is sold — whatever the row's `partial_taken` says. On the paper book
    the +2R third is a resting limit (or OCO) at the target, so a touch the limit does not fill still counts: the trail
    turns live before session 3 and the session-3 third is skipped. Pinned on the reviewer's case (fill 10.30, stop
    10.10, target 10.70; session 1 trades 10.71 and closes 10.45 under a 20-day of 10.50; partial_taken False). If
    this test starts failing, the behaviour changed — update the SSoT's tenth named live-vs-walk difference with it."""
    fill, stop = 10.30, 10.10
    assert rules.target_price(fill, stop) == pytest.approx(10.70)
    day0 = {"v": rules.DAY0_FACTS_VERSION, "stopped": False, "peak": 10.40, "exit_price": None, "exit_minute": None,
            "partial_price": None, "partial_minute": None, "stop_in_force": None}
    closes_before = [10.50] * 20
    s1 = {"o": 10.35, "h": 10.71, "l": 10.30, "c": 10.45}
    t = rules.trail_decision(fill=fill, stop=stop, day0=day0, closes_before=closes_before, fwd=[s1],
                             partial_taken=False)
    assert t["trail_live"] is True and t["sell"] is True             # trail live on session 1, no third really sold
    # a session-3 close above the fill: the session-3 third is skipped (the touch already "sold" it)
    s2 = {"o": 10.45, "h": 10.60, "l": 10.40, "c": 10.55}
    s3 = {"o": 10.55, "h": 10.60, "l": 10.40, "c": 10.46}
    assert rules.session3_decision(fill=fill, stop=stop, day0=day0, fwd=[s1, s2, s3], partial_taken=False) is None
    # without the touch (high 10.69) the same session 3 sells its third
    s1_no = dict(s1, h=10.69)
    assert rules.session3_decision(fill=fill, stop=stop, day0=day0, fwd=[s1_no, s2, s3],
                                   partial_taken=False) == "session_third"
