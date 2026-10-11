"""#687 / #482 flip-day duty (2026-10-11): the replay walkers model the DEPTH exit, and the era
that labels it is ROW-STAMPED (the toggle for a counterfactual), never a hand-typed date.

Before this, no replay or counterfactual walker knew the depth rule existed: `rule_eras` had no
depth era, the four lanes priced every row under `exit_rules_as_of(date)`, and from the Monday
2026-10-12 go-live every depth-stamped trade and every post-flip counterfactual would have been
walked under the OLD exit — the check-the-rule-era failure, built in. Each test here is RED on
origin/main.

What is pinned:
  1. rule_eras — era E exists only for a row/toggle that says 'depth'; a date alone never produces
     it until the dated record is set on flip day; the broker's own constants are mirrored.
  2. walk_arm(depth_exit=True) — the resting stop is the LIVE function's number (one ADR20 under
     the line), a close below the line sells at the NEXT open, pending until that open is stored,
     the +3R breakeven arm still floors the stop at entry, no ADR20 rests at the floor; default
     off is byte-identical.
  3. The recorder — the ROW decides: a depth-stamped fill is era_e and its follows-live SMA arms
     walk depth; the trail arms and the fixed harvest arms do not.
  4. The lanes — the toggle row decides from its first acting session; no row → era D unchanged.
  5. live_rules — DRIFT from the flip until rule_eras.DEPTH_EXIT_LIVE_DATE agrees with the toggle.
"""
from __future__ import annotations

from datetime import date, datetime
from unittest.mock import AsyncMock, patch

import pytest

from agents.market_intelligence import db
from agents.market_intelligence import live_fill_counterfactuals as lfc
from agents.market_intelligence import rule_eras
from agents.market_intelligence.broker import exit_logic as el
from agents.market_intelligence.trading_calendar import get_market_status
from shared.dates import _ET
from tests.test_live_fill_counterfactuals import (
    DAY0_A,
    ENTRY,
    FILL_DAY,
    FILL_IDX_A,
    LIVE_STOP,
    R_PS,
    SESSIONS,
    TARGET_8R,
    _NOW,
    _TODAY,
    _bar,
    _pre_rows,
    _trade_row,
    _wire,
)

_ITD = lambda d: get_market_status(d).is_trading_day   # noqa: E731
PRIOR_CLOSES = [10.0] * 20          # SMA10 = SMA20 = 10.0 before any held close
ADR = 0.04                          # _pre_rows(): (9.18 - 8.82) / 9.0 on every one of 20 sessions

# A tape where the depth rule and today's rule part ways. Day 0 = DAY0_A (fill 10.02 @ 09:31,
# close 10.80; the +8R target 14.0 and the +3R arm 11.5 are never reached). The trail's running
# closes start EMPTY at the fill (the 16:45 job skips the alert day), so day 0's close is not in
# the line. Then:
#   S1  close 11.40 -> SMA10 over (9x10.0, 11.4) = 10.14 = the line. Today's rule rests the stop
#       ON 10.14; depth rests it at round(10.14 - 0.04 x 10.14, 2) = 9.73.
#   S2  low 10.00: pierces 10.14 (today's rule stops out at 10.14, +0.14R) but not 9.73 (depth
#       survives); close 10.30 >= the new line 10.17.
#   S3  close 10.15 < the line 10.185 -> both rules' close test says sell; depth sells at S4's open.
#   S4  open 10.05 -> the depth sale fills there (+0.05R).
S1, S2, S3, S4 = SESSIONS[0], SESSIONS[1], SESSIONS[2], SESSIONS[3]
TAPE = [(S1, _bar(11.0, 11.4, 10.9, 11.4)),
        (S2, _bar(10.3, 10.4, 10.0, 10.3)),
        (S3, _bar(10.2, 10.3, 10.1, 10.15)),
        (S4, _bar(10.05, 10.2, 9.9, 10.0))]
LINE_S1 = 10.14
TODAY_R = (LINE_S1 - ENTRY) / (ENTRY - LIVE_STOP)                                # +0.14R
DEPTH_S1 = el.depth_stop_price(line=LINE_S1, hard_stop=LIVE_STOP, entry_price=ENTRY,
                               breakeven_active=False, adr20_pct=ADR)            # 9.73


def _walk(sessions=TAPE, **kw):
    base = dict(entry=ENTRY, stop=LIVE_STOP, target=TARGET_8R, day0_bars=DAY0_A, fill_idx=FILL_IDX_A,
                sessions=sessions, prior_closes=PRIOR_CLOSES, harvest="live_ladder", fill_day=FILL_DAY,
                breakeven_at_r=3.0, r_frame_ps=R_PS)
    base.update(kw)
    return lfc.walk_arm(**base)


# ── 1. rule_eras: era E is row-stamped ────────────────────────────────────────────────────


def test_the_depth_constants_mirror_the_broker_without_importing_it():
    from agents.market_intelligence.broker import order_manager as om
    assert rule_eras.DEPTH_EXIT_RULE == om.DEPTH_EXIT_RULE == "depth"
    assert rule_eras.DEPTH_EXIT_SIGNAL_TYPES == om._DEPTH_EXIT_STRATEGIES


def test_a_depth_stamped_row_is_era_e_and_an_unstamped_row_never_is(monkeypatch):
    """The ROW decides. The same date, the same strategy: 'depth' -> era_e with the three depth
    fields; None (today's rule) -> era D with the dict EXACTLY as before (#631's byte pin).

    The dated record is patched to None HERE so this test states "no dated record" for itself and
    keeps passing on and after flip day, when `DEPTH_EXIT_LIVE_DATE` is set (review fix 2026-10-11:
    it asserted the live constant was None and went RED on the Tuesday commit)."""
    monkeypatch.setattr(rule_eras, "DEPTH_EXIT_LIVE_DATE", None)
    for d in (date(2026, 9, 8), date(2026, 10, 13), date(2027, 1, 4)):
        assert rule_eras.exit_era_label(d, "magna53", "depth") == "era_e"
        assert rule_eras.exit_era_label(d, "magna53", None) == "era_d"
        assert rule_eras.exit_era_label(d, "magna53") == "era_d"          # no dated record yet
        plain = rule_eras.exit_rules_as_of(d, "magna53")
        assert rule_eras.exit_rules_as_of(d, "magna53", None) == plain
        assert set(plain) == {"stop_mode", "intraday_partial_r", "breakeven_at_r", "trail_prior_closes",
                              "breakeven_at_partial", "ladder_partial", "score_separation"}
        depth = rule_eras.exit_rules_as_of(d, "magna53", "depth")
        assert {k: depth[k] for k in plain} == plain
        assert (depth["exit_rule"], depth["stop_rest"], depth["close_below_sale"]) == \
            ("depth", "one_adr20_under_line", "next_open")
    # the stamp is per-row, so even a strategy outside the stamp set is labelled by its row
    assert rule_eras.exit_era_label(date(2026, 10, 13), "magna53_smallcap", "depth") == "era_e"
    assert rule_eras.exit_era_start("era_e") is None                  # no dated record -> no start


def test_the_dated_record_drives_the_date_only_readers_once_set(monkeypatch):
    """The weekly review's era counts and the #482 YAML literal hold no row and no toggle: once
    DEPTH_EXIT_LIVE_DATE is set they label by date — for the stamped strategies only — while an
    explicit None (a row the stamp did not reach) still reads era D."""
    monkeypatch.setattr(rule_eras, "DEPTH_EXIT_LIVE_DATE", date(2026, 10, 13))
    assert rule_eras.exit_era_label(date(2026, 10, 13), "magna53") == "era_e"
    assert rule_eras.exit_era_label(date(2026, 10, 12), "magna53") == "era_d"
    assert rule_eras.exit_era_label(date(2026, 10, 13), "magna53_smallcap") == "era_e"
    assert rule_eras.exit_era_label(date(2026, 10, 13), "parabolic_short") == "era_c"
    assert rule_eras.exit_era_label(date(2026, 10, 13)) == "era_c"
    assert rule_eras.exit_era_label(date(2026, 10, 13), "magna53", None) == "era_d"
    assert rule_eras.exit_rules_as_of(date(2026, 10, 13), "magna53")["exit_rule"] == "depth"
    assert rule_eras.exit_era_start("era_e") == date(2026, 10, 13)
    split = rule_eras.split_current_vs_older(
        [1, 2, 3],
        [{"alert_date": date(2026, 10, 14), "signal_type": "magna53", "exit_rule": "depth"},
         {"alert_date": date(2026, 10, 14), "signal_type": "magna53", "exit_rule": None},
         {"alert_date": date(2026, 10, 14), "signal_type": "magna53"}],
        date(2026, 10, 20))
    assert split["current"] == [1, 3] and split["older"] == [2]
    assert split["by_era"] == {"era_d": 1, "era_e": 2} and split["current_since"] == date(2026, 10, 13)


def test_the_first_acting_session_is_the_next_orb_after_the_flip():
    """A flip at/after the 09:30 open stamps nothing that day (fills run 09:31-09:45); weekends
    and holidays are skipped by the real calendar. His planned Monday-noon switch -> Tuesday."""
    f = rule_eras.first_acting_session_after
    assert f(datetime(2026, 10, 12, 12, 0, tzinfo=_ET), is_trading_day=_ITD) == date(2026, 10, 13)
    assert f(datetime(2026, 10, 9, 19, 0, tzinfo=_ET), is_trading_day=_ITD) == date(2026, 10, 12)   # Fri evening -> Mon (Columbus Day: NYSE open)
    assert f(datetime(2026, 10, 13, 9, 29, 59, tzinfo=_ET), is_trading_day=_ITD) == date(2026, 10, 13)
    assert f(datetime(2026, 10, 13, 9, 30, 0, tzinfo=_ET), is_trading_day=_ITD) == date(2026, 10, 14)
    assert f(datetime(2026, 9, 4, 12, 0, tzinfo=_ET), is_trading_day=_ITD) == date(2026, 9, 8)       # Labor Day skipped
    # the lanes' wrapper takes the row's own timestamp shapes (aware datetime / ISO string / None)
    assert lfc.depth_first_acting_session("2026-10-12 16:00:00+00") == date(2026, 10, 13)
    assert lfc.depth_first_acting_session(datetime(2026, 10, 12, 12, 0, tzinfo=_ET)) == date(2026, 10, 13)
    assert lfc.depth_first_acting_session(None) is None


# ── 2. walk_arm: the depth branch ─────────────────────────────────────────────────────────


def test_depth_adr20_is_the_live_functions_fraction_on_the_same_rows():
    rows = _pre_rows()
    assert lfc.depth_adr20_from_rows(rows) == pytest.approx(ADR)
    assert lfc.depth_adr20_from_rows(rows) == el.adr20_pct_from_bars(
        [{"h": r["high_price"], "l": r["low_price"], "c": r["close"]} for r in rows])
    assert lfc.depth_adr20_from_rows(rows) * 100 == pytest.approx(lfc.compute_adr20_pct(rows)[0])
    assert lfc.depth_adr20_from_rows(rows[:9]) is None            # < 10 sessions: abstain, as live


def test_depth_rests_one_adr_under_the_line_and_sells_a_close_below_at_the_next_open():
    today = _walk()
    assert today["status"] == "settled" and today["final_reason"] == "stop_hit"
    assert today["exit_session"] == 2 and today["exits"][-1]["price"] == pytest.approx(LINE_S1)
    assert today["pnl_per_share"] / (ENTRY - LIVE_STOP) == pytest.approx(TODAY_R)

    depth = _walk(depth_exit=True, depth_adr20_pct=ADR)
    assert depth["status"] == "settled" and depth["final_reason"] == "sma_trail_stop"
    assert depth["exit_session"] == 4 and depth["sessions_walked"] == 4
    leg = depth["exits"][-1]
    assert leg["fill"] == "next_open" and leg["price"] == pytest.approx(10.05) and leg["time"] == str(S4)
    assert leg["reason"] == "sma_trail_stop" and leg["shares"] == pytest.approx(1.0)
    assert depth["pnl_per_share"] / (ENTRY - LIVE_STOP) == pytest.approx(0.05)
    assert depth["gap_through"] is False and depth["partial_fired"] is False


@pytest.mark.parametrize("s2_low, expect_reason, expect_price", [
    (DEPTH_S1 + 0.01, "sma_trail_stop", 10.05),   # 9.74: above the depth stop -> survives to the S3 close test
    (DEPTH_S1 - 0.01, "stop_hit", DEPTH_S1),      # 9.72: through it -> stopped AT the live function's number
])
def test_the_depth_stop_is_exactly_depth_stop_price(s2_low, expect_reason, expect_price):
    assert DEPTH_S1 == pytest.approx(9.73)
    tape = [TAPE[0], (S2, _bar(10.3, 10.4, s2_low, 10.3)), TAPE[2], TAPE[3]]
    res = _walk(sessions=tape, depth_exit=True, depth_adr20_pct=ADR)
    assert res["status"] == "settled" and res["final_reason"] == expect_reason
    assert res["exits"][-1]["price"] == pytest.approx(expect_price)


def test_no_adr20_rests_the_depth_stop_at_the_floor_never_the_line():
    """Fewer than 10 pre-entry sessions: live rests at the hard/breakeven floor (exit_discipline.md
    2026-10-01, design default), so S2's 10.00 low is nowhere near a stop; a 9.00 low is."""
    res = _walk(depth_exit=True, depth_adr20_pct=None)
    assert res["final_reason"] == "sma_trail_stop" and res["exit_session"] == 4
    tape = [TAPE[0], (S2, _bar(10.3, 10.4, 9.0, 10.3))]
    res = _walk(sessions=tape, depth_exit=True, depth_adr20_pct=None)
    assert res["final_reason"] == "stop_hit" and res["exits"][-1]["price"] == pytest.approx(LIVE_STOP)
    assert el.depth_stop_price(line=LINE_S1, hard_stop=LIVE_STOP, entry_price=ENTRY,
                               breakeven_active=False, adr20_pct=None) == LIVE_STOP


def test_the_plus3r_breakeven_arm_still_floors_the_depth_stop_at_entry():
    """S1's high touches the +3R arm (11.5): the stop moves to entry at the broker, raise-only, and
    the depth stop (9.81) can never pull it back down — S2's 9.95 low stops the trade at 10.00."""
    tape = [(S1, _bar(11.0, 11.5, 10.9, 11.4)), (S2, _bar(10.3, 10.4, 9.95, 10.3))]
    res = _walk(sessions=tape, depth_exit=True, depth_adr20_pct=ADR)
    assert res["status"] == "settled" and res["final_reason"] == "stop_hit"
    assert res["exits"][-1]["price"] == pytest.approx(ENTRY) and res["exit_session"] == 2


def test_a_depth_sale_waits_for_the_next_open_and_blocks_on_a_missing_one():
    res = _walk(sessions=TAPE[:3], depth_exit=True, depth_adr20_pct=ADR)
    assert res["status"] == "pending" and res["reason"] == "depth_next_open_not_yet_settled"
    assert res["pending_at"] == S3 and res["remaining"] == pytest.approx(1.0) and res["exits"] == []
    res = _walk(sessions=TAPE[:3] + [(S4, None)], depth_exit=True, depth_adr20_pct=ADR)
    assert res["status"] == "pending" and res["reason"] == f"missing_session:{S4.isoformat()}"
    assert res["pending_at"] == S4
    # a sale decided on the LAST horizon session is written at the horizon, with the mark and why
    res = _walk(sessions=TAPE[:3], depth_exit=True, depth_adr20_pct=ADR, horizon=3)
    assert res["status"] == "horizon" and res["reason"] == f"depth_sale_decided_at_horizon:{S3.isoformat()}"
    assert res["mark_pnl_per_share"] == pytest.approx(10.15 - ENTRY)


def test_depth_off_is_byte_identical_and_depth_needs_the_live_sma_ladder():
    from tests.test_live_fill_counterfactuals import SESS_A
    for harvest in ("live_ladder", "no_breakeven", "trail_only", "t3"):
        for sessions in (TAPE, SESS_A):
            plain = _walk(sessions=sessions, harvest=harvest, breakeven_at_r=None)
            assert plain == _walk(sessions=sessions, harvest=harvest, breakeven_at_r=None,
                                  depth_exit=False, depth_adr20_pct=ADR)
    with pytest.raises(ValueError):
        _walk(harvest="t3", breakeven_at_r=None, depth_exit=True, depth_adr20_pct=ADR)
    with pytest.raises(ValueError):
        _walk(trail_mode="pivot_swing", pivot_stops=[None] * 4, depth_exit=True, depth_adr20_pct=ADR)
    # stack_walk_inputs: a depth stack asks for the depth walk; an era D stack is unchanged
    _, kw = lfc.stack_walk_inputs(rule_eras.exit_rules_as_of(date(2026, 10, 13), "magna53", "depth"), 10.5, 9.5)
    assert kw["depth_exit"] is True
    # an explicit None = "the row says today's rule" — true on every date, whatever the dated
    # record says (an UNSPECIFIED call would read the record and turn depth after flip day)
    _, kw = lfc.stack_walk_inputs(rule_eras.exit_rules_as_of(date(2026, 10, 13), "magna53", None), 10.5, 9.5)
    assert "depth_exit" not in kw


# ── 3. the recorder: the ROW decides ──────────────────────────────────────────────────────


def _pre_rows_10():
    """The recorder derives the trail's prior closes AND the ADR from the stored pre-entry rows:
    20 sessions closing at 10.0 (so the line matches TAPE's arithmetic) with a 4% daily range."""
    return [dict(r, open_price=10.0, high_price=10.2, low_price=9.8, close=10.0) for r in _pre_rows()]


def _daily_for(tape):
    return _pre_rows_10() + [{"trade_date": d, "open_price": b["o"], "high_price": b["h"],
                              "low_price": b["l"], "close": b["c"]} for d, b in tape]


_OVR = ({"signal_type": "magna53", "profit_trigger_r": 8.0, "breakeven_arm_r": 3.0},)


@pytest.mark.asyncio
async def test_a_depth_stamped_fill_is_era_e_and_its_live_arms_walk_depth(monkeypatch):
    trade = _trade_row(exit_rule="depth", status="filled", total_pnl=None, exits=[], partial_taken=False)
    _, inserts, _, _ = _wire(monkeypatch, trade=trade, daily=_daily_for(TAPE), overrides=_OVR)
    await lfc.run_live_fill_counterfactuals(_TODAY, now_et=_NOW)
    rows = {r["arm"]: r for r in inserts}
    assert rows and all(r["exit_era"] == "era_e" for r in inserts)
    assert all(r["exit_rules"]["exit_rule"] == "depth" for r in inserts)
    assert all(r["exit_rules"]["close_below_sale"] == "next_open" for r in inserts)
    live = rows["live_replay"]
    assert live["outcome"] == "settled" and live["final_reason"] == "sma_trail_stop"
    assert live["exit_session"] == 4 and live["exits"][-1]["fill"] == "next_open"
    assert live["realized_r"] == pytest.approx(0.05)
    # a FIXED harvest arm keeps today's exit: stopped ON the line at S2
    fixed = rows["harvest_trail_only"]
    assert fixed["final_reason"] == "stop_hit" and fixed["exit_session"] == 2
    assert fixed["realized_r"] == pytest.approx(TODAY_R)
    assert "fill" not in fixed["exits"][-1]


@pytest.mark.asyncio
async def test_the_same_fill_without_the_stamp_keeps_todays_exit_and_era(monkeypatch):
    trade = _trade_row(status="filled", total_pnl=None, exits=[], partial_taken=False)
    assert trade.get("exit_rule") is None
    _, inserts, _, _ = _wire(monkeypatch, trade=trade, daily=_daily_for(TAPE), overrides=_OVR)
    await lfc.run_live_fill_counterfactuals(_TODAY, now_et=_NOW)
    rows = {r["arm"]: r for r in inserts}
    assert all(r["exit_era"] == "era_c" for r in inserts)        # alert 2026-08-20, no stamp
    assert all("exit_rule" not in r["exit_rules"] for r in inserts)
    assert rows["live_replay"]["final_reason"] == "stop_hit" and rows["live_replay"]["exit_session"] == 2
    assert rows["live_replay"]["realized_r"] == pytest.approx(TODAY_R)


@pytest.mark.asyncio
async def test_depth_goes_to_the_follows_live_sma_arms_only(monkeypatch):
    seen: dict[str, tuple] = {}
    real = lfc.walk_arm

    def spy(**kw):
        seen[kw["harvest"] + "/" + kw["trail_mode"] + "/" + str(kw.get("depth_exit", False))] = \
            (kw.get("depth_exit", False), kw.get("depth_adr20_pct"))
        return real(**kw)
    monkeypatch.setattr(lfc, "walk_arm", spy)
    trade = _trade_row(exit_rule="depth", status="filled", total_pnl=None, exits=[], partial_taken=False)
    _, inserts, _, _ = _wire(monkeypatch, trade=trade, daily=_daily_for(TAPE), overrides=_OVR)
    await lfc.run_live_fill_counterfactuals(_TODAY, now_et=_NOW)
    assert seen["live_ladder/sma/True"] == (True, pytest.approx(ADR))       # live_replay + stop_* arms
    assert seen["live_ladder/sma/False"] == (False, None)                   # harvest_legacy_2r (fixed)
    for key in ("no_breakeven/sma/False", "trail_only/sma/False", "t3/sma/False",
                "live_ladder/pivot_swing/False"):
        assert seen[key] == (False, None), key
    assert "live_ladder/character_ma/True" not in seen and "live_ladder/pivot_swing/True" not in seen


def test_the_fill_query_carries_the_rows_stamp():
    assert "t.exit_rule" in db._COUNTERFACTUAL_FILLS_SQL


# ── 4. the lanes: the toggle row decides, from its first acting session ───────────────────


_STRATS = [{"strategy_id": "magna53", "phase": "live", "enabled": True, "live_real_enabled": True},
           {"strategy_id": "magna53_smallcap", "phase": "paper", "enabled": True, "live_real_enabled": False},
           {"strategy_id": "magna53_lowcap", "phase": "shadow", "enabled": True, "live_real_enabled": False}]
_ON_LIVE = {"safeguard": "magna53_depth_exit", "account_mode": "live", "state": "on",
            "last_transition_at": "2026-10-12 16:00:00+00"}          # Mon noon ET -> first acting Tue
_ON_PAPER = {"safeguard": "magna53_depth_exit", "account_mode": "paper", "state": "on",
             "last_transition_at": datetime(2026, 10, 12, 12, 1, tzinfo=_ET)}


def test_lane_exit_rule_is_depth_only_from_the_toggles_first_acting_session():
    rule = lfc.lane_exit_rule
    assert rule(_STRATS, [], "magna53", date(2026, 10, 20)) == (None, "magna53_depth_exit[live] absent — era D")
    assert rule(_STRATS, [_ON_LIVE], "magna53", date(2026, 10, 12))[0] is None       # the flip day itself
    assert rule(_STRATS, [_ON_LIVE], "magna53", date(2026, 10, 13)) == \
        ("depth", "magna53_depth_exit[live] on since 2026-10-13 — depth")
    assert rule(_STRATS, [_ON_LIVE], "magna53_smallcap", date(2026, 10, 13))[0] is None   # paper row absent
    assert rule(_STRATS, [_ON_LIVE, _ON_PAPER], "magna53_smallcap", date(2026, 10, 13))[0] == "depth"
    assert rule(_STRATS, [dict(_ON_LIVE, state="off")], "magna53", date(2026, 10, 20))[0] is None
    assert rule(_STRATS, [_ON_LIVE], "magna53_lowcap", date(2026, 10, 20))[0] is None   # shadow: never stamped
    assert rule([], [_ON_LIVE], "magna53", date(2026, 10, 20))[0] is None             # no strategy row
    assert rule(_STRATS, [dict(_ON_LIVE, last_transition_at=None)], "magna53", date(2026, 10, 20))[0] is None


@pytest.mark.asyncio
async def test_load_lane_exit_rule_reads_once_on_the_lanes_connection_and_fails_to_today():
    conn = AsyncMock()
    conn.fetch = AsyncMock(side_effect=[_STRATS, [_ON_LIVE]])
    assert await lfc.load_lane_exit_rule(conn, "magna53", date(2026, 10, 13)) == \
        ("depth", "magna53_depth_exit[live] on since 2026-10-13 — depth")
    assert conn.fetch.await_count == 2
    broken = AsyncMock()
    broken.fetch = AsyncMock(side_effect=RuntimeError("db down"))
    rule, why = await lfc.load_lane_exit_rule(broken, "magna53", date(2026, 10, 13))
    assert rule is None and "unreadable" in why


@pytest.mark.asyncio
async def test_load_lane_exit_rule_fails_to_today_on_a_row_of_an_unexpected_shape():
    """Review fix (2026-10-11): only the two DB reads sat inside the try; the pure step ran after
    it, so a strategy row of an unexpected shape (here: no `strategy_id`) raised into the runner's
    outer handler and EVERY candidate that night was skipped, instead of the promised fall-back
    to today's rule for this run. The shape error must read as 'unreadable' and say era D."""
    conn = AsyncMock()
    conn.fetch = AsyncMock(side_effect=[[{"bogus": 1}], [_ON_LIVE]])
    rule, why = await lfc.load_lane_exit_rule(conn, "magna53", date(2026, 10, 13))
    assert rule is None and "unreadable" in why and "KeyError" in why and "era D" in why
    assert conn.fetch.await_count == 2          # both reads still happen once, in order


@pytest.mark.asyncio
async def test_the_lowcap_lane_stamps_era_e_and_walks_depth_with_the_rows_adr(monkeypatch):
    from agents.market_intelligence import lowcap_lane_replay as lcl
    from tests.test_624_lowcap_lane import _out, _sig, _wire_walker
    day0 = [{"m": datetime(2026, 9, 3, 9, 30 + i, tzinfo=_ET), "o": o, "h": h, "l": l, "c": c}
            for i, (o, h, l, c) in enumerate([(10.0, 10.5, 9.5, 10.3), (10.3, 10.4, 10.2, 10.35),
                                               (10.3, 10.4, 10.2, 10.35), (10.3, 10.45, 10.2, 10.4),
                                               (10.4, 10.6, 10.3, 10.55)] + [(10.55, 10.7, 10.5, 10.6)] * 25)]
    d1 = date(2026, 9, 4)
    sessions = [(d1, {"o": 11.0, "h": 13.0, "l": 10.8, "c": 12.8})]
    seen = {}
    real = lcl.walk_arm

    def spy(**kw):
        seen.update(kw)
        return real(**kw)
    monkeypatch.setattr(lcl, "walk_arm", spy)
    # tests/conftest.py stubs backtester.filters under pytest (the lane suites each patch in a
    # faithful validator through an autouse fixture that does not reach this module)
    monkeypatch.setattr(lcl, "validate_orb_entry", lambda orb_high, orb_low, atr_14: (orb_high > orb_low, None))
    written, _ = _wire_walker(monkeypatch, day0=day0, sessions=sessions)
    tick = datetime(2026, 9, 3, 9, 33, 40, tzinfo=_ET)
    await lcl._record_one_signal(conn=object(), sig=_sig(tick=tick), last_session=d1,
                                 run_date=date(2026, 10, 13), out=_out(), exit_rule="depth")
    f = written[0]
    assert f["replay_exit_era"] == "era_e" and f["replay_exit_rules"]["exit_rule"] == "depth"
    assert f["replay_exit_rules"]["intraday_partial_r"] == 8.0        # the depth stack is era D's levels + depth
    assert seen["depth_exit"] is True and seen["depth_adr20_pct"] == pytest.approx((10.6 - 9.4) / 10.0)
    # the control: no exit rule -> today's stamp, no depth kwargs at all
    seen.clear(); written.clear()
    await lcl._record_one_signal(conn=object(), sig=_sig(tick=tick), last_session=d1,
                                 run_date=date(2026, 10, 13), out=_out())
    assert written[0]["replay_exit_era"] == "era_d" and "exit_rule" not in written[0]["replay_exit_rules"]
    assert "depth_exit" not in seen and "depth_adr20_pct" not in seen


@pytest.mark.asyncio
async def test_the_two_magna53_lanes_stamp_the_toggle_rule(monkeypatch):
    from agents.market_intelligence import gap_near_miss_replay as gnm
    from agents.market_intelligence import sustain_reject_replay as srr
    from tests.test_gap_near_miss_replay import PRIOR_ROWS as G_PRIOR, _m as gm, _pop_row as g_row
    from tests.test_sustain_reject_replay import D0_ROW as S_D0, PRIOR_ROWS as S_PRIOR, _m as sm, _pop_row as s_row
    day0 = [gm(9, 30, 10.0, 10.5, 9.5, 10.3), gm(9, 31, 10.3, 10.4, 10.2, 10.35),
            gm(9, 32, 10.4, 10.6, 10.3, 10.55), gm(9, 33, 10.5, 10.55, 8.0, 8.2)]
    out = {"settled": 0, "no_trade": 0, "unscoreable": 0, "open": 0, "horizon": 0,
           "pending": 0, "errors": 0, "candidates": 0, "written": 0}
    written = []

    async def ups(fields):
        written.append(dict(fields))
        return True

    def _validate(orb_high, orb_low, atr_14):
        return (orb_high - orb_low > 0), None
    monkeypatch.setattr(gnm, "validate_orb_entry", _validate)
    monkeypatch.setattr(srr, "validate_orb_entry", _validate)
    with patch.object(gnm, "get_daily_ohlc_range", AsyncMock(return_value=G_PRIOR)), \
            patch.object(gnm, "get_intraday_bars_window", AsyncMock(return_value=day0)), \
            patch.object(gnm.lfc, "_assemble_sessions", AsyncMock(return_value=[])), \
            patch.object(gnm, "upsert_gap_near_miss_replay", ups):
        await gnm._record_one_near_miss(conn=object(), row=g_row(), last_session=date(2026, 10, 13),
                                        run_date=date(2026, 10, 13), out=out, exit_rule="depth")
    s_day0 = [sm(9, 30, 10.0, 10.5, 9.5, 10.3), sm(9, 31, 10.3, 10.4, 10.2, 10.35),
              sm(9, 32, 10.4, 10.6, 10.3, 10.55), sm(9, 33, 10.5, 10.55, 8.0, 8.2)]
    with patch.object(srr, "get_daily_ohlc_range", AsyncMock(return_value=S_PRIOR + [S_D0])), \
            patch.object(srr, "get_intraday_bars_window", AsyncMock(return_value=s_day0)), \
            patch.object(srr.lfc, "_assemble_sessions", AsyncMock(return_value=[])), \
            patch.object(srr, "upsert_sustain_reject_replay", ups):
        await srr._record_one_reject(conn=object(), row=s_row(), last_session=date(2026, 10, 13),
                                     run_date=date(2026, 10, 13), out=out, exit_rule="depth")
    assert out["errors"] == 0 and len(written) == 2
    for f in written:
        assert f["replay_exit_era"] == "era_e" and f["replay_exit_rules"]["exit_rule"] == "depth"
        assert f["replay_asof_date"] == date(2026, 10, 13) and f["outcome"] == "settled"


@pytest.mark.asyncio
async def test_each_runner_reads_the_toggle_once_and_hands_the_rule_to_every_row(monkeypatch):
    from agents.market_intelligence import gap_near_miss_replay as gnm
    from agents.market_intelligence import lowcap_lane_replay as lcl
    from agents.market_intelligence import sustain_reject_replay as srr
    from tests.conftest import make_mock_pool
    pool, _ = make_mock_pool()
    loads: list[tuple] = []

    async def fake_load(conn, strategy_id, run_date):
        loads.append((strategy_id, run_date))
        return "depth", "test says depth"
    monkeypatch.setattr(lfc, "load_lane_exit_rule", fake_load)
    today = date(2026, 10, 13)
    now = datetime(2026, 10, 13, 18, 14, tzinfo=_ET)

    # gap near-miss
    handed, audits = [], []

    async def rec(conn, row, last_session, run_date, out, **kw):
        handed.append(kw.get("exit_rule"))

    async def audit(ev, summary, detail=""):
        audits.append((ev, summary))
    rows = [{"ticker": "AAAA", "trade_date": today}, {"ticker": "BBBB", "trade_date": today}]
    monkeypatch.setattr(gnm, "get_gap_near_miss_population", AsyncMock(return_value=rows))
    monkeypatch.setattr(gnm, "get_gap_near_miss_existing", AsyncMock(return_value={}))
    monkeypatch.setattr(gnm, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(gnm, "_record_one_near_miss", rec)
    monkeypatch.setattr(gnm, "log_audit_event", audit)
    await gnm.run_gap_near_miss_replay(today, now_et=now)
    assert handed == ["depth", "depth"] and loads == [("magna53", today)]
    assert any("exit rule: test says depth" in s for _, s in audits)

    # sustain reject
    handed.clear(); loads.clear()
    rows = [{"ticker": "AAAA", "decline_date": today}]
    monkeypatch.setattr(srr, "get_sustain_reject_population", AsyncMock(return_value=rows))
    monkeypatch.setattr(srr, "get_sustain_replay_existing", AsyncMock(return_value={}))
    monkeypatch.setattr(srr, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(srr, "_record_one_reject", rec)
    monkeypatch.setattr(srr, "log_audit_event", AsyncMock())
    await srr.run_sustain_reject_replay(today, now_et=now)
    assert handed == ["depth"] and loads == [("magna53", today)]

    # the low-cap shadow lane reads MAGNA53's row; the PAPER lane reads its own strategy's
    handed.clear(); loads.clear()

    async def rec_sig(conn, sig, last_session, run_date, out, **kw):
        handed.append(kw.get("exit_rule"))
    rows = [{"signal_id": 1, "ticker": "SMLL", "scan_date": today, "tick_wallclock_et": now}]
    monkeypatch.setattr(lcl, "get_lowcap_lane_population", AsyncMock(return_value=rows))
    monkeypatch.setattr(lcl, "get_lowcap_lane_replay_existing", AsyncMock(return_value={}))
    monkeypatch.setattr(db, "get_lowcap_paper_lane_population", AsyncMock(return_value=rows))
    monkeypatch.setattr(db, "get_lowcap_paper_lane_replay_existing", AsyncMock(return_value={}))
    monkeypatch.setattr(lcl, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(lcl, "_record_one_signal", rec_sig)
    monkeypatch.setattr(lcl, "log_audit_event", AsyncMock())
    await lcl.run_lowcap_lane_replay(today, now_et=now)
    await lcl.run_paper_lane_replay(today, now_et=now)
    assert handed == ["depth", "depth"] and loads == [("magna53", today), ("magna53_smallcap", today)]


# ── 5. live_rules: DRIFT until the dated record agrees with the toggle ────────────────────


def _res(toggles, strategies=None, reachable=True):
    from scripts.live_rules import ProdState, Resolver
    prod = ProdState(reachable=reachable, toggles=list(toggles),
                     strategies=strategies if strategies is not None else
                     [{"strategy_id": "magna53", "phase": "live", "enabled": True,
                       "live_real_enabled": True, "position_size_multiplier": "1.0"}])
    return Resolver({}, {}, prod)


def test_live_rules_reports_the_unpinned_depth_era_until_the_constant_matches(monkeypatch):
    from scripts import live_rules
    on = {"safeguard": "magna53_depth_exit", "account_mode": "live", "state": "on",
          "last_transition_at": "2026-10-12T16:00:00+00:00"}
    monkeypatch.setattr(rule_eras, "DEPTH_EXIT_LIVE_DATE", None)
    rows = live_rules.scan_depth_era_pin(_res([on]))
    assert len(rows) == 1 and rows[0].rule == "depth-era-unpinned" and rows[0].severity == "DRIFT"
    assert "date(2026, 10, 13)" in rows[0].words and "first acting session 2026-10-13" in rows[0].actual
    monkeypatch.setattr(rule_eras, "DEPTH_EXIT_LIVE_DATE", date(2026, 10, 12))   # the flip day, not the acting one
    assert len(live_rules.scan_depth_era_pin(_res([on]))) == 1
    monkeypatch.setattr(rule_eras, "DEPTH_EXIT_LIVE_DATE", date(2026, 10, 13))
    assert live_rules.scan_depth_era_pin(_res([on])) == []
    # the constant set while the toggle is off/absent is drift too; the paper row alone never anchors
    assert len(live_rules.scan_depth_era_pin(_res([]))) == 1
    assert len(live_rules.scan_depth_era_pin(_res([dict(on, account_mode="paper")]))) == 1
    monkeypatch.setattr(rule_eras, "DEPTH_EXIT_LIVE_DATE", None)
    assert live_rules.scan_depth_era_pin(_res([])) == []                      # today's prod state: quiet
    assert live_rules.scan_depth_era_pin(_res([on], reachable=False)) == []    # never guess offline
    # and the session-open / nightly entry point (detect_drift) carries the rule
    rows = live_rules.detect_drift([], _res([on]))
    assert [r.rule for r in rows if r.rule == "depth-era-unpinned"] == ["depth-era-unpinned"]
