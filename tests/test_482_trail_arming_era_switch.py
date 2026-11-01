"""#482 follow-up (2026-11-01): the replays model the 2026-10-28 trail-arming fix from the SESSION it
went live — exit_discipline.md 2026-10-28 "Known divergence", now closed.

The live tracker has passed `trail_arm_on_close_above=True` on its three ladder calls since the Thu
2026-10-29 12:00-12:06 ET deploy; the first pass under it was that day's 16:45 ET decision on the 10-29
close. Before that, the #482 recorder's arms, the book arms and `scripts/ep_replay` walked the ladder
WITHOUT the flag, so from the deploy they differed from live on any trade bought below its line.

Pinned here:
  1. the boundary — the 10-28 session is decided by the OLD rule, the 10-29 session by the NEW one,
     on the same below-line fill (what live did on each date);
  2. byte-identity before the boundary — a walk whose sessions precede 2026-10-29 adds NO kwarg to
     the ladder call (the #705 frozen reads walk 2016-2022, so their numbers cannot move), and the
     recorder's five equality scenarios still produce the pre-change golden;
  3. the recorder and the book arms hand the walk the live date and the ENTRY DAY's close, split
     off a daily read that now reaches the alert day (the `pre` rows unchanged);
  4. ep_replay — `ruleset_as_of` and `current` carry the date, the named era sets do not, and its
     forward walk agrees with the recorder's on a below-line fill across the boundary;
  5. the date is NOT an exit-era switch in rule_eras (the #631 gated reads keep their anchor).
"""
from __future__ import annotations

from dataclasses import replace as dc_replace
from datetime import date, datetime

import pytest

from agents.market_intelligence import book_geometry_arms as bga
from agents.market_intelligence import live_fill_counterfactuals as lfc
from agents.market_intelligence import rule_eras
from agents.market_intelligence.broker import exit_logic as el
from tests import test_book_geometry_arms_482 as book
from tests import test_live_fill_counterfactuals as base

_ET = base._ET
ENTRY, ORB_LOW = base.ENTRY, base.ORB_LOW          # 10.0 / 9.5 → live stop 9.0
STOP = base.LIVE_STOP
BELOW_LINE_PRIOR = [30.0] * 20                       # the stock's line sits far ABOVE the entry (the CLS shape)


def _day0(d: date) -> list[dict]:
    return [dict(b, m=b["m"].replace(year=d.year, month=d.month, day=d.day)) for b in base.DAY0_A]


def _walk(fill_day: date, sessions, **kw):
    """A below-line fill with NO target (so only the trail or the hard stop can end it)."""
    return lfc.walk_arm(entry=ENTRY, stop=STOP, target=None, day0_bars=_day0(fill_day), fill_idx=base.FILL_IDX_A,
                        sessions=sessions, prior_closes=BELOW_LINE_PRIOR, harvest="live_ladder",
                        fill_day=fill_day, **kw)


# every held close sits under the 30.0 line and above the 9.0 stop
HELD = base._bar(10.6, 10.8, 10.2, 10.4)


def test_the_live_date_is_the_first_decided_session_not_a_rule_eras_era():
    assert el.TRAIL_ARM_LIVE_FROM == date(2026, 10, 29)          # deployed 12:00-12:06 ET; first pass 16:45 ET
    assert el.trail_arming_live_on(date(2026, 10, 28)) is False   # that close was decided by the old code
    assert el.trail_arming_live_on(date(2026, 10, 29)) is True
    # not an exit-ERA switch: the #631 gated reads anchor on the latest `*_DATE` in rule_eras and stay there
    assert not any(n.startswith("TRAIL_ARM") for n in vars(rule_eras))
    latest = max(v for k, v in vars(rule_eras).items() if k.endswith("_DATE") and isinstance(v, date))
    assert latest == rule_eras.DEPTH_EXIT_LIVE_DATE == date(2026, 10, 13)


def test_the_boundary_on_one_below_line_fill_matches_what_live_did_on_each_date():
    """Bought 10-27 under its line (CLS): the 10-28 close below the line SELLS — the old code decided
    that close (live marked CLS that evening; the hand clear that followed is a recorded prod write
    the walk cannot know). Bought 10-28: the 10-29 close is decided WITH the arming — unarmed, the
    line does not govern, the stop is the hard stop and the walk stays open."""
    straddle = _walk(date(2026, 10, 27), [(date(2026, 10, 28), HELD), (date(2026, 10, 29), HELD)],
                     trail_arm_from=el.TRAIL_ARM_LIVE_FROM, entry_day_close=10.3)
    old = _walk(date(2026, 10, 27), [(date(2026, 10, 28), HELD), (date(2026, 10, 29), HELD)])
    assert straddle == old and old["final_reason"] == "sma_trail_stop" and old["exit_session"] == 1

    after = _walk(date(2026, 10, 28), [(date(2026, 10, 29), HELD), (date(2026, 10, 30), HELD)],
                  trail_arm_from=el.TRAIL_ARM_LIVE_FROM, entry_day_close=10.3)
    before = _walk(date(2026, 10, 28), [(date(2026, 10, 29), HELD), (date(2026, 10, 30), HELD)])
    assert before["final_reason"] == "sma_trail_stop" and before["exit_session"] == 1   # the divergence
    assert after["status"] == "pending" and after["final_reason"] is None and after["exits"] == []
    assert after["sessions_walked"] == 2                                                # both closes held


def test_armed_by_the_entry_days_close_the_line_still_sells_after_the_switch():
    """The entry day closed ABOVE its line → armed from day 0 → a later close below the line sells,
    exactly as before the fix (the bought-above / closed-above trade is unchanged)."""
    sessions = [(date(2026, 10, 29), HELD), (date(2026, 10, 30), HELD)]
    armed = _walk(date(2026, 10, 28), sessions, trail_arm_from=el.TRAIL_ARM_LIVE_FROM, entry_day_close=31.0)
    assert armed["final_reason"] == "sma_trail_stop" and armed["exit_session"] == 1
    assert armed == _walk(date(2026, 10, 28), sessions)


def _capture_ladder(monkeypatch):
    calls: list[tuple[date, dict]] = []
    real = lfc.apply_daily_exit_step

    def spy(state, bar, today, **kw):
        calls.append((today, dict(kw)))
        return real(state, bar, today, **kw)
    monkeypatch.setattr(lfc, "apply_daily_exit_step", spy)
    return calls


def test_before_the_boundary_the_ladder_call_is_byte_identical_and_after_it_carries_the_flag(monkeypatch):
    """The #705 frozen reads walk 2016-2022 sessions: with the date passed, no kwarg reaches the
    ladder on any of them — the call is the pre-change call, not a `False` that happens to match."""
    calls = _capture_ladder(monkeypatch)
    sess_2017 = [(date(2017, 3, 3), HELD), (date(2017, 3, 6), HELD)]
    _walk(date(2017, 3, 2), sess_2017, trail_arm_from=el.TRAIL_ARM_LIVE_FROM, entry_day_close=10.3)
    _walk(base.FILL_DAY, base.SESS_A, trail_arm_from=el.TRAIL_ARM_LIVE_FROM, entry_day_close=10.3)
    assert calls and all("trail_arm_on_close_above" not in kw and "entry_day_close" not in kw for _, kw in calls)
    calls.clear()
    _walk(date(2026, 10, 27), [(date(2026, 10, 28), HELD), (date(2026, 10, 29), HELD), (date(2026, 10, 30), HELD)],
          trail_arm_from=el.TRAIL_ARM_LIVE_FROM, entry_day_close=10.3)
    # the 10-28 call (the old rule) sells, so the walk ends there: one call, no flag
    assert [(d, "trail_arm_on_close_above" in kw) for d, kw in calls] == [(date(2026, 10, 28), False)]
    calls.clear()
    _walk(date(2026, 10, 28), [(date(2026, 10, 29), HELD), (date(2026, 10, 30), HELD)],
          trail_arm_from=el.TRAIL_ARM_LIVE_FROM, entry_day_close=10.3)
    assert [(d, kw.get("trail_arm_on_close_above"), kw.get("entry_day_close")) for d, kw in calls] == [
        (date(2026, 10, 29), True, 10.3), (date(2026, 10, 30), True, 10.3)]


def test_the_two_trail_lines_never_receive_the_flag(monkeypatch):
    """pivot_swing / character_ma never had the rule and the ladder refuses the flag on them."""
    calls = _capture_ladder(monkeypatch)
    sessions = [(date(2026, 10, 29), HELD), (date(2026, 10, 30), HELD)]
    lfc.walk_arm(entry=ENTRY, stop=STOP, target=None, day0_bars=_day0(date(2026, 10, 28)), fill_idx=base.FILL_IDX_A,
                 sessions=sessions, prior_closes=BELOW_LINE_PRIOR, harvest="live_ladder", fill_day=date(2026, 10, 28),
                 trail_mode="pivot_swing", pivot_stops=[None, None],
                 trail_arm_from=el.TRAIL_ARM_LIVE_FROM, entry_day_close=10.3)
    assert calls and all(kw.get("trail_mode") == "pivot_swing" and "trail_arm_on_close_above" not in kw
                         for _, kw in calls)


def test_split_entry_day_keeps_the_pre_rows_and_lifts_the_alert_days_close():
    rows = base._pre_rows() + [{"trade_date": base.FILL_DAY, "open_price": 10.0, "high_price": 11.0,
                                "low_price": 9.7, "close": 10.8}]
    pre, close = lfc.split_entry_day(rows, base.FILL_DAY)
    assert pre == base._pre_rows() and close == 10.8
    assert lfc.split_entry_day(base._pre_rows(), base.FILL_DAY) == (base._pre_rows(), None)   # no alert-day row


def _capture_walks(monkeypatch, module):
    seen: list[dict] = []
    real = module.walk_arm

    def spy(**kw):
        seen.append(dict(kw))
        return real(**kw)
    monkeypatch.setattr(module, "walk_arm", spy)
    return seen


@pytest.mark.asyncio
async def test_the_recorder_hands_every_walk_the_live_date_and_the_alert_days_close(monkeypatch):
    """The daily read reaches the alert day; its row is the arming input and the `pre` rows (ADR,
    prior closes) are the same 20 sessions as before. The row's exit_rules stamp is untouched."""
    alert_row = {"trade_date": base.FILL_DAY, "open_price": 10.0, "high_price": 11.0, "low_price": 9.7, "close": 10.8}
    daily = base._pre_rows() + [alert_row] + [
        {"trade_date": d, "open_price": b["o"], "high_price": b["h"], "low_price": b["l"], "close": b["c"]}
        for d, b in base.SESS_A]
    statements, inserts, _, _ = base._wire(monkeypatch, trade=base._trade_row(), daily=daily)
    seen = _capture_walks(monkeypatch, lfc)
    out = await lfc.run_live_fill_counterfactuals(base._TODAY, now_et=base._NOW)
    assert out["errors"] == 0 and seen
    assert all(kw["trail_arm_from"] == el.TRAIL_ARM_LIVE_FROM and kw["entry_day_close"] == 10.8 for kw in seen)
    reads = [args for k, sql, args in statements if "FROM mi_daily_closes" in sql and args[2] == base.FILL_DAY]
    assert reads, "the pre-alert read no longer reaches the alert day"
    by = {r["arm"]: r for r in inserts}
    assert by["live_replay"]["adr20_n"] == 20 and by["live_replay"]["realized_r"] == pytest.approx(1 / 3)
    assert by["live_replay"]["exit_rules"] == rule_eras.exit_rules_as_of(base.FILL_DAY, "magna53", None)


@pytest.mark.asyncio
async def test_the_book_arms_hand_their_walks_the_same_inputs(monkeypatch):
    statements, inserts, _, _ = book._wire_book(monkeypatch, sessions=book.SESS_OPEN, day0_high=12.9)
    seen = _capture_walks(monkeypatch, bga)
    out = await book._run()
    assert out["errors"] == 0 and len(seen) == 3                       # the three walked book arms
    assert all(kw["trail_arm_from"] == el.TRAIL_ARM_LIVE_FROM and kw["entry_day_close"] == 10.0 for kw in seen)


def test_ep_replay_rule_sets_carry_the_date_only_where_live_does():
    import scripts.ep_replay as ep
    assert ep.RULESETS["era_a"].trail_arm_from is None
    assert ep.RULESETS["era_b"].trail_arm_from is None
    assert ep.RULESETS["era_c"].trail_arm_from is None
    assert ep.RULESETS["current"].trail_arm_from == ep.RULESETS["era_d"].trail_arm_from == el.TRAIL_ARM_LIVE_FROM
    assert ep.ruleset_as_of(date(2026, 7, 1)).trail_arm_from == el.TRAIL_ARM_LIVE_FROM   # per-session: the walk gates
    assert ep.ruleset_as_of(date(2026, 10, 30)).trail_arm_from == el.TRAIL_ARM_LIVE_FROM


def test_ep_replay_forward_walk_agrees_with_the_recorder_across_the_boundary(monkeypatch):
    """The recorder's walk mirrors ep_replay._walk_leg (the only walk validated against real fills):
    on a below-line fill straddling the switch both sell on 10-28; on one whose first held close is
    10-29 both hold while unarmed; with the date absent both sell as before."""
    import scripts.ep_replay as ep
    monkeypatch.setattr(ep, "LAST_SETTLED", date(2026, 10, 30))
    prior = {date(2026, 9, 29 + i) if i < 2 else date(2026, 10, i - 1): {"o": 30.0, "h": 30.2, "l": 29.8, "c": 30.0}
             for i in range(2, 22)}
    for fill_day, held_days in ((date(2026, 10, 27), [date(2026, 10, 28), date(2026, 10, 29)]),
                                (date(2026, 10, 28), [date(2026, 10, 29), date(2026, 10, 30)])):
        day0 = _day0(fill_day)
        daily = dict(prior)
        daily[fill_day] = {"o": day0[0]["o"], "h": max(b["h"] for b in day0), "l": min(b["l"] for b in day0),
                           "c": 10.3}                                             # the entry day closes under its line
        for d in held_days:
            daily[d] = dict(HELD)
        for rs_name, trail_arm_from in (("era_c", None), ("current", el.TRAIL_ARM_LIVE_FROM)):
            rs = dc_replace(ep.RULESETS[rs_name], intraday_partial_r=None, breakeven_at_r=None,
                            partial_min_one_share=False)
            theirs = ep._walk_leg(ticker="XYZ", leg_date=fill_day, entry_px=ENTRY, stop=STOP, target=None,
                                  bars=day0, fill_idx=base.FILL_IDX_A, rs=rs, daily={"XYZ": daily}, shares=None,
                                  integer_shares=False, adr_dollar=None, minutes_extra={})
            ours = lfc.walk_arm(entry=ENTRY, stop=STOP, target=None, day0_bars=day0, fill_idx=base.FILL_IDX_A,
                                sessions=[(d, HELD) for d in held_days],
                                prior_closes=[prior[k]["c"] for k in sorted(prior)], harvest="live_ladder",
                                fill_day=fill_day, trail_arm_from=trail_arm_from, entry_day_close=10.3)
            assert rs.trail_arm_from == trail_arm_from
            sold = ours["final_reason"] == "sma_trail_stop"
            assert (theirs["final_reason"] == "sma_trail_stop") is sold, (fill_day, rs_name, theirs, ours)
            expect_sold = trail_arm_from is None or held_days[0] < el.TRAIL_ARM_LIVE_FROM
            assert sold is expect_sold, (fill_day, rs_name)


def test_the_equality_scenarios_still_match_the_pre_change_golden():
    """Already asserted per scenario by tests/test_book_geometry_arms_482.py (the five-scenario golden);
    named here so the proof this switch rests on is visible from this file."""
    from tests._lfc_equality_scenarios import scenarios
    assert set(scenarios()) == {"default", "override_8r_3r", "depth_row", "missing_orb_low", "open_trade"}
