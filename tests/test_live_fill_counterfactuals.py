"""#482 (2026-09-03) live-fill counterfactual recorder tests.

Pure walk (walk_arm / compute_adr20_pct / arm_stop_price / pinned_target / live_actual_outcome)
+ parity against scripts/ep_replay._walk_leg (the only mechanics validated against real
fills) + the orchestration half against a CAPTURING fake pool. Every assertion checks a
computed VALUE against the bars it came from, never a label string.

THE LINE — the three properties the brief demands, proven at the SQL layer:
  1. BYTE-IDENTITY: every statement the run executes is captured; no write names anything
     but mi_live_fill_counterfactuals, and the served mi_live_trades row is `==` a deepcopy
     taken before the run (the #616 acceptance-test analogue for a separate table).
  2. TOTAL FAILURE: every arm raising AND every write raising -> zero rows, counted errors,
     audit rows, the run returns, the live row untouched.
  3. NOTHING LIVE READS IT: no module under agents/ except the scheduler imports the recorder.
"""
from __future__ import annotations

import copy
import re
import sys
from dataclasses import replace as dc_replace
from datetime import date, datetime, time, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.market_intelligence import db
from agents.market_intelligence import live_fill_counterfactuals as lfc
from agents.market_intelligence import rule_eras

_ET = ZoneInfo("America/New_York")
_REPO = Path(__file__).resolve().parent.parent

FILL_DAY = date(2026, 8, 20)                     # Thursday, era C, adm_2026-08-20_gap_floor_9 (the 9% floor committed 08-19 after the ORB window)
ENTRY, ORB_HIGH, ORB_LOW = 10.0, 10.0, 9.5       # R_orb = 0.5
LIVE_STOP = 2 * ORB_LOW - ORB_HIGH               # 9.0 = entry - 2R (risk 1.0 in live units)
TARGET = ENTRY + 2 * (ENTRY - ORB_LOW)           # 11.0, pinned to the ORB R
SESSIONS = [date(2026, 8, 21), date(2026, 8, 24), date(2026, 8, 25), date(2026, 8, 26),
            date(2026, 8, 27), date(2026, 8, 28), date(2026, 8, 31), date(2026, 9, 1),
            date(2026, 9, 2), date(2026, 9, 3), date(2026, 9, 4)]


def _m(hh, mm, o, h, l, c, d=FILL_DAY):
    return {"m": datetime(d.year, d.month, d.day, hh, mm, tzinfo=_ET), "o": o, "h": h, "l": l, "c": c}


def _bar(o, h, l, c):
    return {"o": o, "h": h, "l": l, "c": c}


# Day 0 (scenario A): fill at 09:31, the +2R target touched at 10:00, no stop touched.
DAY0_A = [
    _m(9, 30, 9.8, 10.0, 9.7, 9.95),
    _m(9, 31, 9.98, 10.05, 9.95, 10.02),      # the fill bar
    _m(9, 32, 10.02, 10.3, 10.0, 10.25),
    _m(10, 0, 10.3, 11.05, 10.2, 10.9),       # target 11.0 touched -> 1/3 off
    _m(15, 59, 10.9, 10.95, 10.6, 10.8),
]
FILL_IDX_A = 1

# Sessions after day 0 (scenario A): S1 dips to 9.9 (breakeven touch, not the 9.0 stop),
# S2/S3 run, S4 gaps down through every stop.
SESS_A = [
    (SESSIONS[0], _bar(10.6, 10.8, 9.9, 10.4)),
    (SESSIONS[1], _bar(10.5, 11.5, 10.3, 11.4)),
    (SESSIONS[2], _bar(11.5, 12.2, 11.2, 12.0)),
    (SESSIONS[3], _bar(8.5, 8.7, 8.4, 8.6)),
] + [(d, _bar(8.6, 8.8, 8.5, 8.7)) for d in SESSIONS[4:]]

PRIOR_CLOSES = [9.0] * 20


def _pre_rows():
    """20 stored sessions before FILL_DAY with (high-low)/close = 4% -> ADR20 = 4.0%."""
    days = []
    d = FILL_DAY - timedelta(days=1)
    while len(days) < 20:
        if d.weekday() < 5:
            days.append(d)
        d -= timedelta(days=1)
    return [{"trade_date": x, "open_price": 9.0, "high_price": 9.18, "low_price": 8.82, "close": 9.0}
            for x in sorted(days)]


def _walk(harvest, *, stop=LIVE_STOP, target=TARGET, day0=DAY0_A, fill_idx=FILL_IDX_A,
          sessions=SESS_A, prior=PRIOR_CLOSES, **kw):
    return lfc.walk_arm(entry=ENTRY, stop=stop, target=target, day0_bars=day0, fill_idx=fill_idx,
                        sessions=sessions, prior_closes=prior, harvest=harvest, fill_day=FILL_DAY, **kw)


def _r(res, stop):
    return res["pnl_per_share"] / (ENTRY - stop)


# ── The harvest arms: one bar set, four different answers ─────────────────────────────


def test_live_ladder_reproduces_the_plus_033_scratch():
    """Partial 1/3 at +2R on day 0, then the breakeven stop (raised to entry AT the partial —
    #548) fills on S1's 9.9 low: pnl = 1/3 x 1.0 + 2/3 x 0 = +0.333/share, in live units
    (risk 1.0) exactly +0.333R — the unit effect 26 of 54 partial-takers show."""
    res = _walk("live_ladder")
    assert res["status"] == "settled" and res["partial_fired"] is True
    assert res["final_reason"] == "stop_hit" and res["exit_session"] == 1
    assert _r(res, LIVE_STOP) == pytest.approx(1 / 3)
    assert [e["reason"] for e in res["exits"]] == ["partial_profit", "stop_hit"]
    assert res["exits"][1]["price"] == pytest.approx(ENTRY)      # the breakeven level, not 9.0


def test_no_breakeven_keeps_the_hard_stop_and_rides_the_trail_into_the_gap():
    """Same bars, the stop does NOT move to entry: S1's 9.9 low is survived, the SMA trail
    (prior closes 9.0 x20, #548) raises the resting stop to 9.68 by S3, S4 opens at 8.5
    through it -> gap-through fill at the OPEN: pnl = 1/3 x 1.0 + 2/3 x (8.5-10) = -0.667."""
    res = _walk("no_breakeven")
    assert res["status"] == "settled" and res["gap_through"] is True
    assert res["exit_session"] == 4 and res["final_reason"] == "stop_hit"
    assert res["exits"][-1]["price"] == pytest.approx(8.5)
    assert _r(res, LIVE_STOP) == pytest.approx(1 / 3 - 2 / 3 * 1.5)


def test_t3_sells_the_runner_at_the_third_close_after_the_partial():
    """Partial day 0 -> S1, S2, S3 are post-sessions 1-3 -> time_close at S3's 12.0:
    pnl = 1/3 x 1.0 + 2/3 x 2.0 = +1.667. The hard stop stays at 9.0 meanwhile (S1 9.9 ok)."""
    res = _walk("t3")
    assert res["status"] == "settled" and res["final_reason"] == "time_close"
    assert res["exit_session"] == 3
    assert _r(res, LIVE_STOP) == pytest.approx(1 / 3 + 2 / 3 * 2.0)


def test_trail_only_never_partials_and_pays_the_whole_gap():
    """No partial at +2R (the 11.05 high is ignored); the trail raises the resting stop; S4's
    gap fills the WHOLE position at 8.5: pnl = 1 x (8.5-10) = -1.5 -> -1.5R."""
    res = _walk("trail_only")
    assert res["status"] == "settled" and res["partial_fired"] is False
    assert res["gap_through"] is True and res["exit_session"] == 4
    assert _r(res, LIVE_STOP) == pytest.approx(-1.5)


def test_stop_arms_settle_in_their_own_units_on_the_same_scratch():
    """ORB-low (risk 0.5) and 0.5xADR (risk 0.2) arms, same bars: the same +0.333/share
    scratch reads +0.667R and +1.667R in their OWN units — a wider stop is never flattered."""
    orb = _walk("live_ladder", stop=ORB_LOW)
    adr = _walk("live_ladder", stop=ENTRY - 0.5 * 0.4)
    assert _r(orb, ORB_LOW) == pytest.approx((1 / 3) / 0.5)
    assert _r(adr, ENTRY - 0.2) == pytest.approx((1 / 3) / 0.2)


# ── Day-0 mechanics (stop-first, same-bar abstain, fill-bar rules) ────────────────────


def test_tight_stops_die_on_day_zero_while_the_live_stop_survives():
    """09:33 prints a 9.45 low: ORB low 9.5 / 0.5xADR 9.8 / 0.75xADR 9.7 are stopped at
    -1R in their own units on session 0; the live 9.0 stop is untouched and goes on to the
    +2R partial at 10:00."""
    day0 = [DAY0_A[0], DAY0_A[1], _m(9, 33, 10.0, 10.02, 9.45, 9.6), DAY0_A[3], DAY0_A[4]]
    for stop in (ORB_LOW, 9.8, 9.7):
        res = _walk("live_ladder", stop=stop, day0=day0)
        assert res["status"] == "settled" and res["exit_session"] == 0
        assert _r(res, stop) == pytest.approx(-1.0)
        assert res["partial_fired"] is False
    live = _walk("live_ladder", day0=day0)
    assert live["partial_fired"] is True and live["exit_session"] == 1


def test_stop_and_target_in_one_minute_bar_abstains():
    """A bar spanning 9.4-11.1 touches the ORB-low stop AND the target: order unknowable
    at 1-min grain -> abstain, nothing settled, nothing guessed."""
    day0 = [DAY0_A[0], DAY0_A[1], _m(9, 33, 10.0, 11.1, 9.4, 10.5)]
    res = _walk("live_ladder", stop=ORB_LOW, day0=day0)
    assert res["status"] == "abstain" and res["reason"] == "day0_stop_and_target_same_bar"
    assert res["pnl_per_share"] is None


def test_fill_bar_rules_close_below_stop_is_a_stop_close_above_abstains():
    fb_below = [DAY0_A[0], _m(9, 31, 9.98, 10.05, 9.4, 9.45)]     # descended through 9.5
    fb_above = [DAY0_A[0], _m(9, 31, 9.98, 10.05, 9.4, 9.9)]      # straddles 9.5
    r1 = _walk("live_ladder", stop=ORB_LOW, day0=fb_below)
    r2 = _walk("live_ladder", stop=ORB_LOW, day0=fb_above)
    assert r1["status"] == "settled" and _r(r1, ORB_LOW) == pytest.approx(-1.0)
    assert r2["status"] == "abstain" and r2["reason"] == "day0_fill_bar_straddles_stop"


def test_minute_gap_through_fills_at_the_open():
    """09:33 opens at 9.3, below the 9.5 stop: the resting stop fills at the open, not the
    stop level — -1.4R in ORB-low units, gap_through stamped."""
    day0 = [DAY0_A[0], DAY0_A[1], _m(9, 33, 9.3, 9.35, 9.2, 9.25)]
    res = _walk("live_ladder", stop=ORB_LOW, day0=day0)
    assert res["gap_through"] is True and res["exits"][0]["price"] == pytest.approx(9.3)
    assert _r(res, ORB_LOW) == pytest.approx((9.3 - 10.0) / 0.5)


def test_forward_stop_and_target_same_day_abstains():
    """No partial on day 0; S1 spans 8.9-11.2 -> both the resting 9.0 stop and the 11.0
    target inside one daily bar -> abstain (the _walk_leg rule)."""
    day0 = [DAY0_A[0], DAY0_A[1], DAY0_A[4]]
    sess = [(SESSIONS[0], _bar(10.0, 11.2, 8.9, 10.5))]
    res = _walk("live_ladder", day0=day0, sessions=sess)
    assert res["status"] == "abstain" and res["reason"].startswith("fwd_stop_and_target_same_day")


# ── Pending / horizon / gaps ──────────────────────────────────────────────────────────


def test_open_walk_short_of_horizon_is_pending_not_a_result():
    day0 = [DAY0_A[0], DAY0_A[1], DAY0_A[4]]
    sess = [(SESSIONS[0], _bar(10.6, 10.8, 10.2, 10.4))]
    res = _walk("live_ladder", day0=day0, sessions=sess)
    assert res["status"] == "pending" and res["pending_at"] is None
    assert res["pnl_per_share"] is None and res["mark_pnl_per_share"] is None


def test_horizon_writes_a_mark_never_a_return():
    day0 = [DAY0_A[0], DAY0_A[1], DAY0_A[4]]
    sess = [(SESSIONS[0], _bar(10.6, 10.8, 10.2, 10.4)), (SESSIONS[1], _bar(10.5, 10.9, 10.3, 10.7))]
    res = _walk("live_ladder", day0=day0, sessions=sess, horizon=2)
    assert res["status"] == "horizon" and res["final_reason"] == "horizon"
    assert res["pnl_per_share"] is None
    assert res["mark_pnl_per_share"] == pytest.approx(10.7 - 10.0)   # open remainder at the last close


def test_missing_session_blocks_the_walk_instead_of_leaping_it():
    """S2's bar is missing: the walk stops AT S2 (pending_at = S2) — it does not read S3's
    gap-down as if S2 never existed (the #616 abstain rule; a deliberate deviation from
    _walk_leg's `sessions_abstained += 1; continue`)."""
    day0 = [DAY0_A[0], DAY0_A[1], DAY0_A[4]]
    sess = [(SESSIONS[0], _bar(10.6, 10.8, 10.2, 10.4)), (SESSIONS[1], None),
            (SESSIONS[2], _bar(8.5, 8.7, 8.4, 8.6))]
    res = _walk("live_ladder", day0=day0, sessions=sess)
    assert res["status"] == "pending" and res["pending_at"] == SESSIONS[1]
    assert res["sessions_walked"] == 1


def test_missing_day0_minutes_is_pending_at_the_fill_day():
    res = _walk("live_ladder", day0=None, fill_idx=None)
    assert res["status"] == "pending" and res["pending_at"] == FILL_DAY
    assert res["reason"] == "no_day0_minute_bars"


# ── ADR / stops / target: NULL and counted, never substituted ────────────────────────


def test_adr20_is_the_mean_range_pct_and_null_below_ten_sessions():
    pct, n = lfc.compute_adr20_pct(_pre_rows())
    assert n == 20 and pct == pytest.approx(4.0)
    pct9, n9 = lfc.compute_adr20_pct(_pre_rows()[-9:])
    assert pct9 is None and n9 == 9
    pct_gap, n_gap = lfc.compute_adr20_pct(_pre_rows()[:8] + [{"trade_date": FILL_DAY, "close": 9.0}])
    assert pct_gap is None and n_gap == 8          # the incomplete bar is skipped, not guessed


def test_arm_stop_prices_and_missing_adr():
    assert lfc.arm_stop_price("live", entry=ENTRY, orb_low=ORB_LOW, live_stop=LIVE_STOP, adr_dollar=0.4) == LIVE_STOP
    assert lfc.arm_stop_price("orb_low", entry=ENTRY, orb_low=ORB_LOW, live_stop=LIVE_STOP, adr_dollar=0.4) == ORB_LOW
    assert lfc.arm_stop_price("adr_050", entry=ENTRY, orb_low=ORB_LOW, live_stop=LIVE_STOP, adr_dollar=0.4) == pytest.approx(9.8)
    assert lfc.arm_stop_price("adr_075", entry=ENTRY, orb_low=ORB_LOW, live_stop=LIVE_STOP, adr_dollar=0.4) == pytest.approx(9.7)
    assert lfc.arm_stop_price("adr_050", entry=ENTRY, orb_low=ORB_LOW, live_stop=LIVE_STOP, adr_dollar=None) is None
    with pytest.raises(ValueError):
        lfc.arm_stop_price("atr", entry=ENTRY, orb_low=ORB_LOW, live_stop=LIVE_STOP, adr_dollar=0.4)


def test_target_is_pinned_to_the_orb_r_not_the_placed_stop():
    """entry 10, ORB low 9.5, live stop 9.0: the target is 11.0 (+2 x 0.5), NOT 12.0 (+2 x
    1.0) — the 08-16 rule that the stop moved and the target did not."""
    assert lfc.pinned_target(ENTRY, ORB_LOW) == pytest.approx(11.0)
    assert lfc.pinned_target(ENTRY, 10.0) is None and lfc.pinned_target(None, 9.5) is None


def test_live_actual_reads_the_row_in_placed_stop_units():
    trade = {"status": "closed", "total_pnl": 10.0, "entry_shares": 30, "partial_taken": True,
             "exits": [{"reason": "partial_profit", "price": 11.0, "shares": 10, "pnl": 10.0},
                       {"reason": "stop_hit", "price": 10.0, "shares": 20, "pnl": 0.0}],
             "closed_at": datetime(2026, 8, 21, 10, 5, tzinfo=_ET)}
    res = lfc.live_actual_outcome(trade, fill_day=FILL_DAY, entry=ENTRY, live_stop=LIVE_STOP)
    assert res["status"] == "settled" and res["pnl_per_share"] == pytest.approx(10.0 / 30)
    assert res["exit_session"] == 1 and res["final_reason"] == "stop_hit" and res["partial_fired"]
    open_res = lfc.live_actual_outcome({"status": "filled", "total_pnl": None}, fill_day=FILL_DAY,
                                       entry=ENTRY, live_stop=LIVE_STOP)
    assert open_res["status"] == "pending"


def test_last_settled_session_never_uses_a_partial_day():
    fri = date(2026, 9, 4)
    assert lfc.last_settled_session(fri, datetime(2026, 9, 4, 12, 0, tzinfo=_ET)) == date(2026, 9, 3)
    assert lfc.last_settled_session(fri, datetime(2026, 9, 4, 18, 4, tzinfo=_ET)) == fri
    assert lfc.last_settled_session(date(2026, 9, 6), datetime(2026, 9, 6, 18, 4, tzinfo=_ET)) == fri
    # Labor Day 2026-09-07: not a session
    assert lfc.last_settled_session(date(2026, 9, 7), datetime(2026, 9, 7, 18, 4, tzinfo=_ET)) == fri


# ── Parity with scripts/ep_replay._walk_leg (the validated mechanics) ─────────────────


def _ep_daily():
    d = {}
    for r in _pre_rows():
        d[r["trade_date"]] = {"o": 9.0, "h": 9.18, "l": 8.82, "c": 9.0}
    d[FILL_DAY] = {"o": 9.8, "h": 11.05, "l": 9.7, "c": 10.8}
    for day, b in SESS_A:
        d[day] = dict(b)
    return {"XYZ": d}


@pytest.mark.parametrize("harvest,runner,target", [
    ("live_ladder", "live", TARGET), ("trail_only", "live", None), ("t3", "t3", TARGET)])
def test_walk_matches_the_validated_harness_on_identical_bars(monkeypatch, harvest, runner, target):
    """scripts/ep_replay._walk_leg is the only walk validated per-trade against real fills.
    The recorder's walk must produce the SAME realized R, exit reason and legs on the same
    bars for the live rule (with and without the partial) and for t3 — at every stop."""
    import scripts.ep_replay as ep
    monkeypatch.setattr(ep, "LAST_SETTLED", SESSIONS[-1])
    rs = dc_replace(ep.RULESETS["era_c"], runner_rule=runner)
    for stop in (LIVE_STOP, ORB_LOW, 9.8, 9.7):
        theirs = ep._walk_leg(ticker="XYZ", leg_date=FILL_DAY, entry_px=ENTRY, stop=stop,
                              target=target, bars=DAY0_A, fill_idx=FILL_IDX_A, rs=rs,
                              daily=_ep_daily(), shares=None, integer_shares=False,
                              adr_dollar=None, minutes_extra={})
        ours = _walk(harvest, stop=stop, target=target)
        assert theirs["status"] == "settled" == ours["status"], (stop, theirs["reason"], ours["reason"])
        assert ours["pnl_per_share"] / (ENTRY - stop) == pytest.approx(theirs["realized_r"])
        assert ours["final_reason"] == theirs["final_reason"]
        assert [e["reason"] for e in ours["exits"]] == [e["reason"] for e in theirs["exits"]]
        assert [e["price"] for e in ours["exits"]] == pytest.approx([e["price"] for e in theirs["exits"]])


# ── Orchestration against a CAPTURING fake pool — THE LINE at the SQL layer ──────────


def _trade_row(**over):
    row = {
        "id": 42, "ticker": "XYZ", "alert_date": FILL_DAY, "account_mode": "live",
        "signal_type": "magna53", "entry_attempt": 1, "status": "closed",
        "entry_price": ENTRY, "entry_shares": 30.0, "orb_high": ORB_HIGH, "orb_low": ORB_LOW,
        "hard_stop": LIVE_STOP, "regime": "Bull",
        "exits": [{"reason": "partial_profit", "price": 11.0, "shares": 10, "pnl": 10.0},
                  {"reason": "stop_hit", "price": 10.0, "shares": 20, "pnl": 0.0}],
        "partial_taken": True, "total_pnl": 10.0, "pnl_attribution": None,
        "filled_at": datetime(2026, 8, 20, 9, 31, 7, tzinfo=_ET),
        "closed_at": datetime(2026, 8, 21, 10, 5, tzinfo=_ET),
    }
    row.update(over)
    return row


def _wire(monkeypatch, *, trade, written=(), daily=None, minutes=None, stamp=None,
          execute_result="INSERT 0 1"):
    """A fake asyncpg pool that ROUTES every statement by the table it reads and RECORDS
    every statement executed. Returns (statements, inserts, audits, trade_store)."""
    daily = daily if daily is not None else (_pre_rows() + [
        {"trade_date": d, "open_price": b["o"], "high_price": b["h"], "low_price": b["l"], "close": b["c"]}
        for d, b in SESS_A])
    minutes = minutes if minutes is not None else DAY0_A
    stamp = stamp if stamp is not None else {
        "rubric_version": "v3", "score_tier": "HIGH", "ep_score": 71.0, "judge_grade": "strong",
        "judge_tier": "A", "grade_engine_authority": "lattice", "setup_class": "ep",
        "baseline_floor_tier": "B", "alert_source": "live"}
    statements: list[tuple[str, str, tuple]] = []
    inserts: list[dict] = []
    audits: list[tuple[str, str]] = []
    trade_store = {"row": trade}

    async def fetch(sql, *args):
        statements.append(("fetch", sql, args))
        if "FROM mi_live_trades" in sql:
            return [trade_store["row"]] if trade_store["row"] is not None else []
        if "FROM mi_live_fill_counterfactuals WHERE trade_id" in sql:
            return [{"arm": a} for a in written]
        if "FROM mi_daily_closes" in sql:
            lo, hi = args[1], args[2]
            return [dict(r) for r in daily if lo <= r["trade_date"] <= hi]
        if "FROM mi_intraday_bars" in sql:
            lo, hi = args[1], args[2]
            return [{"bar_time": b["m"], "open": b["o"], "high": b["h"], "low": b["l"], "close": b["c"]}
                    for b in minutes if lo <= b["m"] <= hi]
        raise AssertionError(f"unexpected fetch: {sql[:80]}")

    async def fetchrow(sql, *args):
        statements.append(("fetchrow", sql, args))
        if "FROM mi_ep_alerts" in sql:
            return dict(stamp) if stamp else None
        if "FROM mi_daily_closes" in sql:
            return None
        raise AssertionError(f"unexpected fetchrow: {sql[:80]}")

    async def execute(sql, *args):
        statements.append(("execute", sql, args))
        if sql.startswith("INSERT INTO mi_live_fill_counterfactuals"):
            inserts.append(dict(zip(db.LIVE_FILL_CF_COLS, args)))
            return execute_result
        raise AssertionError(f"unexpected execute: {sql[:80]}")

    conn = MagicMock()
    conn.fetch, conn.fetchrow, conn.execute = fetch, fetchrow, execute
    conn.fetchval = AsyncMock(side_effect=AssertionError("unexpected fetchval"))
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=cm)

    async def get_pool():
        return pool

    async def audit(event_type, summary, detail=""):
        audits.append((event_type, summary))

    async def no_fallback(conn_, ticker, d):
        return None, None, None, None, None

    monkeypatch.setattr(db, "get_pool", get_pool)
    monkeypatch.setattr(lfc, "get_pool", get_pool)
    monkeypatch.setattr(lfc, "log_audit_event", audit)
    monkeypatch.setattr(lfc, "get_daily_bar_with_fallback", no_fallback)
    return statements, inserts, audits, trade_store


_NOW = datetime(2026, 9, 4, 18, 4, tzinfo=_ET)
_TODAY = _NOW.date()


@pytest.mark.asyncio
async def test_run_writes_one_row_per_arm_and_only_to_its_own_table(monkeypatch):
    """THE BYTE-IDENTITY ACCEPTANCE TEST. Every statement the run executes is captured:
    the only writes are INSERTs into mi_live_fill_counterfactuals; every read of
    mi_live_trades is a SELECT; the served trade row is EQUAL to a deepcopy taken before.
    And the eight arms carry the values the pure tests derived from the same bars."""
    trade = _trade_row()
    before = copy.deepcopy(trade)
    statements, inserts, audits, store = _wire(monkeypatch, trade=trade)
    out = await lfc.run_live_fill_counterfactuals(_TODAY, now_et=_NOW)

    writes = [(k, sql) for k, sql, _ in statements if k == "execute"
              or re.match(r"\s*(INSERT|UPDATE|DELETE)", sql, re.I)]
    assert writes and all(sql.startswith("INSERT INTO mi_live_fill_counterfactuals") for _, sql in writes)
    assert not any("mi_live_trades" in sql for _, sql in writes)
    assert not any("mi_live_orders" in sql for _, sql, _ in statements)
    live_reads = [sql for k, sql, _ in statements if "mi_live_trades" in sql]
    assert live_reads and all(sql.lstrip().upper().startswith("SELECT") for sql in live_reads)
    assert store["row"] == before                      # byte-identical after the run

    assert out["errors"] == 0 and out["population"] == 1 and out["written"] == 8
    assert out["settled"] == 8 and out["pending"] == 0
    by = {r["arm"]: r for r in inserts}
    assert set(by) == set(lfc.ARM_NAMES)
    assert by["live_actual"]["realized_r"] == pytest.approx(1 / 3)          # 10 / (30 x 1.0)
    assert by["live_replay"]["realized_r"] == pytest.approx(1 / 3)          # the fidelity check agrees
    assert by["stop_orb_low"]["realized_r"] == pytest.approx((1 / 3) / 0.5)
    assert by["stop_adr_050"]["stop_price"] == pytest.approx(9.8)
    assert by["stop_adr_075"]["stop_price"] == pytest.approx(9.7)
    assert by["harvest_no_breakeven"]["realized_r"] == pytest.approx(1 / 3 - 1.0)
    assert by["harvest_t3"]["realized_r"] == pytest.approx(1 / 3 + 4 / 3)
    assert by["harvest_trail_only"]["realized_r"] == pytest.approx(-1.5)
    for r in inserts:
        assert r["target_price"] == pytest.approx(11.0) and r["target_r"] == 2.0
        assert r["adr20_pct"] == pytest.approx(4.0) and r["adr20_n"] == 20
        assert r["adr_dollar"] == pytest.approx(0.4) and r["live_stop"] == LIVE_STOP
        assert r["outcome"] == "settled" and r["settle_version"] == lfc.SETTLE_VERSION
        assert r["realized_pct"] == pytest.approx(r["realized_r"] * r["risk_per_share"] / ENTRY * 100)
    assert by["harvest_no_breakeven"]["gap_through"] is True
    assert by["stop_orb_low"]["stop_width_adr"] == pytest.approx(0.5 / 0.4)
    assert any(e == "live_fill_counterfactual_recorded" for e, _ in audits)


@pytest.mark.asyncio
async def test_every_row_carries_the_era_stamp(monkeypatch):
    """alert 2026-08-20: exit era C (2R stop + partial + trail + breakeven), admission era =
    the 9% gap floor's first acting session (committed 08-19 after the ORB window; the 08-22
    lattice switch has not acted yet), and the alert row's own admission-time stamps copied
    verbatim — not derived from a date."""
    _, inserts, _, _ = _wire(monkeypatch, trade=_trade_row())
    await lfc.run_live_fill_counterfactuals(_TODAY, now_et=_NOW)
    for r in inserts:
        assert r["exit_era"] == "era_c"
        assert r["exit_rules"] == {"stop_mode": "entry_minus_2r", "intraday_partial_r": 2.0,
                                   "trail_prior_closes": True, "breakeven_at_partial": True,
                                   "ladder_partial": False, "score_separation": False}
        assert r["admission_era"] == "adm_2026-08-20_gap_floor_9"
        assert r["rubric_version"] == "v3" and r["grade_engine_authority"] == "lattice"
        assert r["score_tier"] == "HIGH" and r["ep_score"] == 71.0 and r["alert_source"] == "live"
        assert r["account_mode"] == "live" and r["regime"] == "Bull" and r["entry_attempt"] == 1
        assert r["fill_day"] == FILL_DAY and r["trade_id"] == 42
        assert r["settled_session"] == _TODAY          # the last settled session this run walked


@pytest.mark.asyncio
async def test_a_later_admission_era_gets_a_different_label(monkeypatch):
    """The same trade admitted on 2026-08-28 is stamped with the rubric-v4 stack (flipped 08-27
    after the ORB window, first acting 08-28): two rows from two filter sets are readable
    apart, which pooling could never do."""
    d = date(2026, 8, 28)
    trade = _trade_row(alert_date=d, filled_at=datetime(2026, 8, 28, 9, 31, tzinfo=_ET),
                       closed_at=datetime(2026, 8, 31, 10, 0, tzinfo=_ET))
    day0 = [dict(b, m=b["m"].replace(day=28)) for b in DAY0_A]
    sess = [(date(2026, 8, 31), _bar(10.6, 10.8, 9.9, 10.4))]
    pre = [{"trade_date": x, "open_price": 9.0, "high_price": 9.18, "low_price": 8.82, "close": 9.0}
           for x in [d - timedelta(days=k) for k in range(1, 40)] if x.weekday() < 5]
    daily = sorted(pre, key=lambda r: r["trade_date"]) + [
        {"trade_date": s, "open_price": b["o"], "high_price": b["h"], "low_price": b["l"], "close": b["c"]}
        for s, b in sess]
    _, inserts, _, _ = _wire(monkeypatch, trade=trade, daily=daily, minutes=day0)
    await lfc.run_live_fill_counterfactuals(_TODAY, now_et=_NOW)
    assert inserts and all(r["admission_era"] == "adm_2026-08-28_rubric_v4_rt_gap_authority" for r in inserts)
    assert all(r["exit_rules"]["score_separation"] is True for r in inserts)


@pytest.mark.asyncio
async def test_total_recorder_failure_leaves_the_live_trade_untouched(monkeypatch):
    """REQUIRED: the walk raises on every arm AND the writer raises. Zero rows land, every
    failure is counted + audited, the run RETURNS (never raises), no Telegram path exists,
    and the served live row is byte-identical."""
    trade = _trade_row()
    before = copy.deepcopy(trade)
    statements, inserts, audits, store = _wire(monkeypatch, trade=trade)

    def boom(**kw):
        raise RuntimeError("walk boom")

    async def write_boom(fields):
        raise RuntimeError("write boom")

    monkeypatch.setattr(lfc, "walk_arm", boom)
    monkeypatch.setattr(lfc, "insert_live_fill_counterfactual", write_boom)
    out = await lfc.run_live_fill_counterfactuals(_TODAY, now_et=_NOW)
    assert out["written"] == 0 and inserts == []
    assert out["errors"] == 8                        # 7 walked arms + the live_actual write
    errs = [s for e, s in audits if e == "live_fill_counterfactual_error"]
    assert sum("walk boom" in s for s in errs) == 7 and sum("write boom" in s for s in errs) == 1
    assert store["row"] == before
    assert not any(k == "execute" for k, _, _ in statements)


@pytest.mark.asyncio
async def test_fill_query_failure_returns_counted_not_raised(monkeypatch):
    audits = []

    async def audit(e, s, d=""):
        audits.append((e, s))

    async def fills_boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(lfc, "get_counterfactual_fills", fills_boom)
    monkeypatch.setattr(lfc, "log_audit_event", audit)
    out = await lfc.run_live_fill_counterfactuals(_TODAY, now_et=_NOW)
    assert out["errors"] == 1 and out["written"] == 0
    assert any("db down" in s for e, s in audits if e == "live_fill_counterfactual_error")


@pytest.mark.asyncio
async def test_missing_adr_closes_the_adr_arms_unscoreable_and_settles_the_rest(monkeypatch):
    """Only 6 stored pre-alert sessions: ADR is NULL (never substituted). The two ADR arms
    are written `unscoreable` with every R NULL and the shortfall named; the other six
    settle normally on the same run."""
    daily = _pre_rows()[-6:] + [
        {"trade_date": d, "open_price": b["o"], "high_price": b["h"], "low_price": b["l"], "close": b["c"]}
        for d, b in SESS_A]
    _, inserts, _, _ = _wire(monkeypatch, trade=_trade_row(), daily=daily)
    out = await lfc.run_live_fill_counterfactuals(_TODAY, now_et=_NOW)
    by = {r["arm"]: r for r in inserts}
    assert out["unscoreable"] == 2 and out["settled"] == 6
    for arm in ("stop_adr_050", "stop_adr_075"):
        assert by[arm]["outcome"] == "unscoreable" and by[arm]["final_reason"] == "no_adr20:6_sessions"
        assert by[arm]["realized_r"] is None and by[arm]["stop_price"] is None
        assert by[arm]["adr20_pct"] is None and by[arm]["adr20_n"] == 6
    assert by["stop_orb_low"]["outcome"] == "settled" and by["live_replay"]["outcome"] == "settled"


@pytest.mark.asyncio
async def test_open_live_trade_defers_live_actual_and_settles_the_tight_arms(monkeypatch):
    """The live trade is still open and only S1 has printed: live_actual is pending (no
    row), the live-stop arms are pending (open walk), and every arm that is definitive on
    the bars so far writes — nothing waits on anything else (the #616 lesson)."""
    trade = _trade_row(status="filled", total_pnl=None, closed_at=None)
    day0 = [DAY0_A[0], DAY0_A[1], _m(9, 33, 10.0, 10.02, 9.45, 9.6), DAY0_A[4]]   # tight stops die
    daily = _pre_rows() + [{"trade_date": SESSIONS[0], "open_price": 10.6, "high_price": 10.8,
                            "low_price": 10.2, "close": 10.4}]
    now = datetime(2026, 8, 21, 18, 4, tzinfo=_ET)
    _, inserts, _, _ = _wire(monkeypatch, trade=trade, daily=daily, minutes=day0)
    out = await lfc.run_live_fill_counterfactuals(now.date(), now_et=now)
    arms = {r["arm"] for r in inserts}
    assert arms == {"stop_orb_low", "stop_adr_050", "stop_adr_075"}
    assert all(r["realized_r"] == pytest.approx(-1.0) and r["exit_session"] == 0 for r in inserts)
    assert out["pending"] == 5 and out["written"] == 3


@pytest.mark.asyncio
async def test_a_stale_gap_is_written_abstain_a_fresh_one_waits(monkeypatch):
    """Day-0 minutes are missing. One session after the fill the arms wait (pending);
    once the gap is GAP_RETRY_SESSIONS old they are written `abstain` naming it — counted,
    never leapt, never fabricated."""
    trade = _trade_row(status="filled", total_pnl=None, closed_at=None)
    daily = _pre_rows() + [
        {"trade_date": d, "open_price": b["o"], "high_price": b["h"], "low_price": b["l"], "close": b["c"]}
        for d, b in SESS_A]
    fresh = datetime(2026, 8, 21, 18, 4, tzinfo=_ET)
    _, inserts, _, _ = _wire(monkeypatch, trade=trade, daily=daily, minutes=[])
    out = await lfc.run_live_fill_counterfactuals(fresh.date(), now_et=fresh)
    assert inserts == [] and out["pending"] == 8

    stale = datetime(2026, 8, 28, 18, 4, tzinfo=_ET)          # 6 sessions past the fill day
    _, inserts2, _, _ = _wire(monkeypatch, trade=trade, daily=daily, minutes=[])
    out2 = await lfc.run_live_fill_counterfactuals(stale.date(), now_et=stale)
    assert out2["abstained"] == 7 and out2["pending"] == 1          # live_actual still open
    assert all(r["outcome"] == "abstain" and r["final_reason"] == "no_day0_minute_bars"
               and r["realized_r"] is None for r in inserts2)


@pytest.mark.asyncio
async def test_write_once_a_fully_recorded_fill_is_skipped(monkeypatch):
    statements, inserts, _, _ = _wire(monkeypatch, trade=_trade_row(), written=lfc.ARM_NAMES)
    out = await lfc.run_live_fill_counterfactuals(_TODAY, now_et=_NOW)
    assert inserts == [] and out["fills_considered"] == 0 and out["errors"] == 0
    assert not any(k == "execute" for k, _, _ in statements)


@pytest.mark.asyncio
async def test_conflict_is_not_counted_as_written(monkeypatch):
    _, inserts, _, _ = _wire(monkeypatch, trade=_trade_row(), execute_result="INSERT 0 0")
    out = await lfc.run_live_fill_counterfactuals(_TODAY, now_et=_NOW)
    assert len(inserts) == 8 and out["written"] == 0 and out["settled"] == 0


# ── THE LINE, statically ──────────────────────────────────────────────────────────────

_MODULE = _REPO / "agents" / "market_intelligence" / "live_fill_counterfactuals.py"


def test_recorder_has_exactly_one_writer_and_no_inline_sql():
    src = _MODULE.read_text()
    assert not re.search(r"\b(UPDATE|DELETE FROM|INSERT INTO)\b", src), "inline SQL in the recorder"
    imports = re.search(r"from agents\.market_intelligence\.db import \((.*?)\)", src, re.S).group(1)
    names = {n.strip() for n in imports.replace("\n", "").split(",") if n.strip()}
    writers = {n for n in names if n.startswith(("insert_", "update_", "upsert_", "record_", "settle_", "delete_"))}
    assert writers == {"insert_live_fill_counterfactual"}
    assert db.LIVE_FILL_CF_INSERT_SQL.startswith("INSERT INTO mi_live_fill_counterfactuals (")
    assert db.LIVE_FILL_CF_INSERT_SQL.endswith("ON CONFLICT (trade_id, arm) DO NOTHING")
    assert db.LIVE_FILL_CF_INSERT_SQL.count("::jsonb") == 2


def test_recorder_imports_only_the_pure_ladder_from_broker_with_the_marker():
    src = _MODULE.read_text()
    broker_imports = [l for l in src.splitlines() if "agents.market_intelligence.broker" in l and "import" in l]
    assert len(broker_imports) == 1
    assert ".broker.exit_logic import" in broker_imports[0] and "# exec-boundary-ok:" in broker_imports[0]
    import_lines = [l for l in src.splitlines() if re.match(r"\s*(from|import)\s", l)]
    for banned in ("alpaca_client", "order_manager", "live_tracker", "entry_pipeline",
                   "execution_client", "telegram", "briefing"):
        assert not any(banned in l for l in import_lines), banned


def test_nothing_live_imports_the_recorder():
    """No module under agents/ except the scheduler (the job registration) — and, since
    2026-09-03, the #593 sustain-reject bracket replay and the #617 Step 2 gap-floor
    near-miss replay, both of which reuse walk_arm/pinned_target rather than writing a
    fourth/fifth walker (see each module's own docstring: WHAT IT MIRRORS) — may import
    the recorder. None of these consumers is on a decision path; all are telemetry."""
    importers = []
    for py in sorted((_REPO / "agents").rglob("*.py")):
        if py == _MODULE:
            continue
        if re.search(r"^\s*(from|import)\s+[\w.]*live_fill_counterfactuals\b", py.read_text(), re.M):
            importers.append(str(py.relative_to(_REPO)))
    assert importers == ["agents/market_intelligence/gap_near_miss_replay.py",
                        "agents/market_intelligence/scheduler.py",
                        "agents/market_intelligence/sustain_reject_replay.py"], importers
    # and the TABLE is named nowhere on the execution side or in the detector/judge/sizing paths
    for py in (_REPO / "agents" / "market_intelligence").rglob("*.py"):
        if py.name in ("db.py", "health_checks.py", "live_fill_counterfactuals.py",
                      "sustain_reject_replay.py"):
            continue
        assert "mi_live_fill_counterfactuals" not in py.read_text(), py.relative_to(_REPO)


def test_registrations_job_liveness_preflight_schema():
    from agents.market_intelligence import scheduler as sched, health_checks as hc
    import scripts.preflight_db_updates as pf
    assert "live_fill_counterfactuals" in sched.INTELLIGENCE_OWNED_JOB_IDS
    assert "live_fill_counterfactuals" not in sched.EXECUTION_OWNED_JOB_IDS
    assert any(t[0] == "mi_live_fill_counterfactuals" and t[2] == "settled_session" for t in hc._DETECTOR_LIVENESS_TABLES)
    assert any(sql is db.LIVE_FILL_CF_INSERT_SQL for _, sql in pf.SHADOW_WRITER_STATEMENTS)
    src = (_REPO / "agents" / "market_intelligence" / "db.py").read_text()
    block = re.search(r"CREATE TABLE IF NOT EXISTS mi_live_fill_counterfactuals \((.*?)\n\s*\);", src, re.S).group(1)
    assert "UNIQUE (trade_id, arm)" in block
    for col in db.LIVE_FILL_CF_COLS:
        assert re.search(rf"^\s*{col}\s+", block, re.M), f"column {col} missing from CREATE"
    assert "mi_live_fill_counterfactuals" not in (_REPO / "scripts" / "exec_loaded_modules.txt").read_text()
    assert "live_fill_counterfactuals" not in (_REPO / "scripts" / "exec_loaded_modules.txt").read_text()


def test_purge_old_data_never_deletes_the_counterfactual_table():
    import asyncio

    executed = []

    async def fake_execute(sql, *a):
        executed.append(sql)
        return "DELETE 0"

    conn = MagicMock()
    conn.execute = fake_execute
    pool = MagicMock()
    pool.acquire = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    from unittest.mock import patch
    with patch.object(db, "get_pool", AsyncMock(return_value=pool)):
        asyncio.run(db.purge_old_data())
    assert executed and not any("mi_live_fill_counterfactuals" in s for s in executed)


def test_gated_review_is_registered_with_its_population_declared():
    import yaml
    reg = yaml.safe_load((_REPO / "data_gated_reviews.yaml").read_text())
    entries = reg["reviews"] if isinstance(reg, dict) else reg
    e = next(x for x in entries if x.get("review_id") == "live_fill_counterfactuals_first_read_482")
    assert e["threshold"] == 20 and e["status"] == "pending" and e["kind"] == "accrual"
    assert "HAVING COUNT(DISTINCT arm) = 4" in e["predicate_sql"]
    assert "to_regclass('mi_live_fill_counterfactuals')" in e["predicate_sql"]
    assert "mi_live_fill_counterfactuals.admission_era" in e["discriminates_on"]


# ── rule_eras: one table, cited by the SSoT, read by every consumer ───────────────────


def test_exit_switch_dates_are_the_operator_signed_facts_and_shared():
    import scripts.ep_replay as ep
    from agents.market_intelligence import system_review as sr
    assert rule_eras.STOP_2R_DATE == date(2026, 8, 16) == ep.STOP_2R_DATE == sr._STOP_GEOMETRY_ERA_START
    assert rule_eras.PARTIAL_LIVE_DATE == date(2026, 8, 1) == ep.PARTIAL_LIVE_DATE == sr._PROFIT_TRIGGER_ERA_START
    assert rule_eras.SEP_SCORE_DATE == date(2026, 8, 22) == ep.SEP_SCORE_DATE
    assert rule_eras.TRAIL_PRIOR_CLOSES_DATE == date(2026, 8, 8) == ep.TRAIL_PRIOR_CLOSES_DATE
    assert rule_eras.BREAKEVEN_AT_PARTIAL_DATE == date(2026, 8, 8) == ep.BREAKEVEN_AT_PARTIAL_DATE
    # the harness composes its RuleSet from the SAME fields
    for d in (date(2026, 7, 15), date(2026, 8, 5), date(2026, 8, 20), date(2026, 9, 3)):
        rs, ours = ep.ruleset_as_of(d), rule_eras.exit_rules_as_of(d)
        assert (rs.stop_mode, rs.intraday_partial_r, rs.trail_prior_closes, rs.breakeven_at_partial,
                rs.ladder_partial, rs.score_separation) == tuple(ours.values())


def test_exit_era_labels_at_the_boundaries():
    assert rule_eras.exit_era_label(date(2026, 7, 31)) == "era_a"
    assert rule_eras.exit_era_label(date(2026, 8, 1)) == "era_b"
    assert rule_eras.exit_era_label(date(2026, 8, 15)) == "era_b"
    assert rule_eras.exit_era_label(date(2026, 8, 16)) == "era_c"


def test_admission_era_is_the_first_acting_session_not_the_flip_day():
    """A fill happens 09:31-09:45 ET. The 08-19 gap floor was committed 15:37 ET, the 08-25
    universe flip was 11:02 ET, the 08-27 rubric/gap-authority flips were 11:19-13:55 ET —
    the fills of THOSE days were admitted by the OLD stack. The label must say so."""
    assert rule_eras.admission_era_as_of(date(2026, 8, 19)) == rule_eras.PRE_SWITCH_ADMISSION_ERA
    assert rule_eras.admission_era_as_of(date(2026, 8, 20)) == "adm_2026-08-20_gap_floor_9"
    assert rule_eras.admission_era_as_of(date(2026, 8, 21)) == "adm_2026-08-20_gap_floor_9"   # Sat 08-22 deploy not yet acting
    assert rule_eras.admission_era_as_of(date(2026, 8, 24)) == "adm_2026-08-24_lattice_separation_shortlist"
    assert rule_eras.admission_era_as_of(date(2026, 8, 25)) == "adm_2026-08-24_lattice_separation_shortlist"
    assert rule_eras.admission_era_as_of(date(2026, 8, 26)) == "adm_2026-08-26_rt_universe_authoritative"
    assert rule_eras.admission_era_as_of(date(2026, 8, 27)) == "adm_2026-08-26_rt_universe_authoritative"
    assert rule_eras.admission_era_as_of(date(2026, 8, 28)) == "adm_2026-08-28_rubric_v4_rt_gap_authority"
    assert rule_eras.admission_era_as_of(date(2026, 8, 30)) == "adm_2026-08-28_rubric_v4_rt_gap_authority"
    assert rule_eras.admission_era_as_of(date(2026, 9, 3)) == "adm_2026-08-31_extension_cap_50_slot_rank_rs"
    dates = [d for d, *_ in rule_eras.ADMISSION_SWITCHES]
    assert dates == sorted(dates) and len(set(dates)) == len(dates)
    from agents.market_intelligence.trading_calendar import get_market_status
    assert all(get_market_status(d).is_trading_day for d in dates)   # an acting session IS a session


def test_every_admission_switch_cites_a_dated_heading_in_the_setup_ssot():
    """The forward half of the same-commit rule: a row here must point at a `### <date>`
    change-log heading in magna53_ep.md, so the table can never cite a change the SSoT
    does not record. (The reverse — an SSoT entry with no row — is not decidable here.)"""
    ssot = (_REPO / "docs" / "setups" / "magna53_ep.md").read_text()
    headings = set(re.findall(r"^### (\d{4}-\d{2}-\d{2})", ssot, re.M))
    for d, name, desc, recorded_under in rule_eras.ADMISSION_SWITCHES:
        assert recorded_under.isoformat() in headings, (
            f"{name}: no ### {recorded_under} heading in magna53_ep.md")
        assert desc and len(desc) > 10
        # the heading records the change; the acting session is on or after it — except the
        # 08-25 universe flip, only recorded under the 08-28 status record
        assert recorded_under <= d or (d, recorded_under) == (date(2026, 8, 26), date(2026, 8, 28))
