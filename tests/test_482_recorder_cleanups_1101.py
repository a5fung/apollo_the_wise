"""#482 follow-up (3), 2026-11-01: the deferred behaviour-neutral tidy-ups in the two hour-bar recorders
(commit 7e44b589's list) — shared row / session-bar / walked-field builders and the pass scaffold in
`shadow_orb_tracker`, one gap-by-daily-high helper and one 2R-stop formula in `hour_bar_walk` for both
recorders, and the exit pass fetching today's bar once per ticker and never for a row the ladder skips.

The proof that the ROWS are identical is the OLD-vs-NEW capture (`scripts/probes/_482_followups_1101/
tracker_old_vs_new_probe.py`: 26 hour-lane scenarios, the 5-minute lane, 5 exit-pass scenarios, 2
replays and 10 book-arm scenarios — byte-identical payloads on the tree before and after) plus the
5-minute golden; what is pinned here is the one INTENDED change (fewer fetches) and the helpers' own
contracts.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from unittest.mock import AsyncMock

import pytest

from agents.market_intelligence import book_geometry_arms as bga
from agents.market_intelligence.broker import hour_bar_walk as hbw
from agents.market_intelligence.broker import shadow_orb_tracker as sot
from tests.test_482_shadow_hour_lane import DAY, _Captured, _ms, _open_5m_row, _patch_common


def test_the_2r_stop_is_one_formula_shared_by_both_recorders_and_equal_to_the_replays():
    import scripts.ep_replay as ep
    from agents.market_intelligence.sustain_reject_replay import current_era_stop
    assert sot.two_r_stop is hbw.two_r_stop and bga.two_r_stop is hbw.two_r_stop
    for hi, lo in ((11.0, 9.5), (10.0, 9.5), (100.0, 97.25), (11.0, 5.0)):
        assert hbw.two_r_stop(hi, lo) == ep.RULESETS["era_c"].stop_price(hi, lo) == 2 * lo - hi
        # simplify 2026-11-01: the third copy outside the recorders, pinned to the same formula
        assert current_era_stop("entry_minus_2r", hi, lo) == hbw.two_r_stop(hi, lo)


def test_the_exit_pass_skips_its_fetch_exactly_when_the_ladder_would_skip():
    """simplify 2026-11-01: the exit pass decides whether to fetch today's bar with its own copy of the ladder's
    first check (`exit_logic.py` is freeze-pinned, so the predicate cannot be exported). This pins the copy to
    the ladder: the pass fetches iff `apply_daily_exit_step` would read a bar rather than `skip_pre_alert`."""
    from agents.market_intelligence.broker.exit_logic import apply_daily_exit_step
    for remaining in (0.0, 5.0):
        for offset in (-1, 0, 1, 3):
            row = _open_5m_row("AAA", DAY, remaining_shares=remaining)
            state = sot._row_to_state(row)
            today = DAY + timedelta(days=offset)
            pass_fetches = state["remaining_shares"] > 0 and today > state["alert_date"]
            ladder_skips = apply_daily_exit_step(state, None, today, integer_partial_shares=False).action == "skip_pre_alert"
            assert pass_fetches == (not ladder_skips), (remaining, offset)


def test_decide_with_daily_high_is_the_shared_second_half_of_the_gap_rule():
    bars = []                                                         # never read when the verdict decides
    needs = {"kind": "needs_daily_high", "high": 11.0, "low": 9.5, "walk_reason": "entry_window_gaps:3_of_330"}
    assert hbw.decide_with_daily_high(bars, time(16, 0), needs, None, missing_reason="no_day0_daily_bar") == {
        "kind": "pending", "high": 11.0, "low": 9.5, "reason": "entry_window_gaps:3_of_330:no_day0_daily_bar"}
    assert hbw.decide_with_daily_high(bars, time(16, 0), needs, None, missing_reason="no_stored_day0_daily_bar")["reason"] \
        == "entry_window_gaps:3_of_330:no_stored_day0_daily_bar"
    for other in ({"kind": "filled", "px": 11.0}, {"kind": "no_entry", "reason": "x"}, {"kind": "pending", "reason": "y"}):
        assert hbw.decide_with_daily_high(bars, time(16, 0), other, 10.0, missing_reason="z") is other
    # with a high in hand it re-classifies through the one walk (its strict-below rule)
    from tests.test_482_shadow_hour_lane import _hour_day
    gappy = sot._alpaca_bars_to_walk_shape(_hour_day(DAY, skip={(11, 0), (11, 1), (14, 30)}))
    v = hbw.classify_hour_entry(gappy, time(16, 0))
    assert v["kind"] == "needs_daily_high"
    assert hbw.decide_with_daily_high(gappy, time(16, 0), v, 10.95, missing_reason="m")["reason"] \
        == "no_entry:never_crossed_hour_high:proven_by_daily_high"
    assert hbw.decide_with_daily_high(gappy, time(16, 0), v, 11.0, missing_reason="m")["kind"] == "pending"


def test_session_bars_keeps_the_window_drops_unstamped_bars_and_sorts():
    d = date(2026, 10, 20)
    bars = [{"t": _ms(d + timedelta(days=3)), "c": 3}, {"c": 9}, {"t": _ms(d), "c": 0},
            {"t": _ms(d + timedelta(days=1)), "c": 1}, {"t": _ms(d + timedelta(days=7)), "c": 7}]
    assert [(x, b["c"]) for x, b in sot._session_bars(bars, after=d, through=d + timedelta(days=6))] == [
        (d + timedelta(days=1), 1), (d + timedelta(days=3), 3)]
    assert [b["c"] for _, b in sot._session_bars(bars)] == [0, 1, 3, 7]        # the replay: everything stamped
    assert sot._session_bars(None) == []


def test_walked_fields_are_the_carried_state_plus_the_last_steps_two_numbers():
    from agents.market_intelligence.broker.exit_logic import iter_exit_ladder, seed_exit_state
    state = seed_exit_state(alert_date=date(2026, 10, 20), entry_price=11.0, hard_stop=8.0, remaining_shares=1.0)
    last = None
    for _, _, step in iter_exit_ladder(state, [(date(2026, 10, 21), {"l": 10.8, "c": 10.9})], integer_partial_shares=False):
        last = step
    f = sot._walked_fields(state, last)
    assert f == {"running_closes": [10.9], "exits": [], "remaining_shares": 1.0, "partial_taken": False,
                 "breakeven_active": False, "total_pnl": 0, "hold_days": 1, "stop_price": last.effective_stop}
    assert set(sot._closed_fields()) == {"status", "closed_at"} and sot._closed_fields()["status"] == "closed"


@pytest.mark.asyncio
async def test_the_exit_pass_fetches_todays_bar_once_per_ticker_and_never_for_a_row_the_ladder_skips(monkeypatch):
    """The one INTENDED change: the 5-minute and 60-minute siblings share one fetch; a row on its alert
    day or with nothing left is not fetched (the ladder returns skip_pre_alert before reading a bar);
    an EMPTY answer is not cached — `collector.get_index_history` never raises (a Polygon failure logs
    and returns []), so the next row of the same ticker makes its own attempt, as every row did before:
    BAD answers [] to its 5-minute row (no_data, as before) and a bar to its 60-minute sibling (updated)."""
    fetched: list[str] = []

    async def _daily(t, a, b):
        fetched.append(t)
        if t == "BAD" and fetched.count("BAD") == 1:
            return []                                   # the real failure shape: logged, [] returned
        return [{"o": 10.4, "h": 10.9, "l": 10.1, "c": 10.2, "t": 0}]
    cap = _Captured()
    _patch_common(monkeypatch, cap, minute_bars=lambda *a: [], daily_bars=_daily)
    rows = [_open_5m_row("AAA", DAY, id=1), _open_5m_row("AAA", DAY, id=2, bar_size_minutes=60),
            _open_5m_row("DDD", DAY + timedelta(days=1), id=4),                 # the alert day itself
            _open_5m_row("FFF", DAY, id=6, remaining_shares=0.0),               # nothing left
            _open_5m_row("BAD", DAY, id=7), _open_5m_row("BAD", DAY, id=8, bar_size_minutes=60)]

    async def _open(bar_size_minutes=None):
        return rows
    monkeypatch.setattr(sot, "get_open_shadow_trades", _open)
    out = await sot.update_shadow_positions(DAY + timedelta(days=1))
    assert fetched == ["AAA", "BAD", "BAD"]                                     # AAA once; BAD retried after []
    assert out == {"closed": 0, "updated": 3, "no_data": 3, "error": 0, "quarantined_stale": 0}
    assert sorted(i for i, _ in cap.updates) == [1, 2, 8]                       # the skipped rows and BAD's [] row write nothing


def test_both_inserts_build_the_one_row_shape_carrying_every_column_the_insert_reads():
    # simplify 2026-11-01: the INSERT reads by key name, so the invariant is the key SET, not its order
    import agents.market_intelligence.db as db
    row = sot._shadow_row("AAA", DAY, 60, "magna53", None, "HIGH", status="open", entry_price=11.0, entry_shares=1.0)
    cols = db.SHADOW_TRADE_INSERT_SQL.split("(", 1)[1].split(")", 1)[0].replace("\n", " ").split(",")
    assert set(row) == {c.strip() for c in cols}
    assert row["remaining_shares"] == 1.0 and sot._shadow_row("AAA", DAY, 5, "magna53", None, None, status="no_entry")["remaining_shares"] == 0


def test_the_old_vs_new_capture_is_recorded_beside_the_probe():
    from pathlib import Path
    d = Path(__file__).resolve().parent.parent / "scripts" / "probes" / "_482_followups_1101"
    before = (d / "tracker_old_vs_new.before.sha256").read_text().split()[0]
    after = (d / "tracker_old_vs_new.after.sha256").read_text().split()[0]
    assert before == after and len(before) == 64
