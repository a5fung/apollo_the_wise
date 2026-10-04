"""#687 RULING (a), operator 2026-10-04 ("A"): the coverage repair also reads the broker and places
nothing when it shows no position.

THE GAP IT CLOSES. Ruling (i) taught the failed-exit stop restore to tell a FLAT broker from an
UNREADABLE one and place nothing on a real zero. The stop-coverage reconciler
(`_ensure_stop_coverage_outcome`, its PLACE branch — no live stop, under-covered) sized its target
from whatever the caller gave it and placed with no position read of its own; the 17:00 / 19:00 ET
coverage slot hands it `remaining_shares` from the BOOKS — so on a broker that held nothing it
re-placed the very sell stop ruling (i) had just withheld, on shares we do not own.

THE SHAPE. ONE helper, `_read_broker_position` (factored out of `_broker_free_qty_for_restore`, which
now calls it), answers HELD / FLAT / UNREADABLE for both consumers. In the place branch, BEFORE placing:
FLAT → nothing placed, a FLAGGED outcome whose message says so in plain words, one
`coverage_skipped_broker_flat` audit row, and no retry (no `stop_coverage_repair_failed` row is
written, and `retry_failed_coverage_repairs` treats the flat row as terminal, as it treats a breach);
UNREADABLE → exactly today's behaviour (place from the books); HELD → exactly today's behaviour
(`target` is NOT re-sized from the position read). Only the place branch reads: the resize/replace
branch, the no-price return and the detector-only path are untouched.

Red without the change (run against origin/main 4e454395, 2026-10-04):
  flat → nothing placed / the outcome / the audit row; the retry's terminal; the page sentence; the
  shared-helper routing (a stubbed helper steers both consumers); the 17:00 slot end to end; the
  'held' and 'unreadable' CALL-LIST pins (the extra read). Green on main, pinning unchanged behaviour: the held / unreadable PLACEMENTS (same qty,
  same price), the replace branch, the no-price return, the detector.

The worlds come from the convergence harness (`tests/_convergence_687_harness.py`).
"""
from __future__ import annotations

import json

import pytest

import tests._convergence_687_harness as H
from agents.market_intelligence.broker import order_manager as om
import agents.market_intelligence.scheduler as sched
from tests._convergence_687_harness import (
    NOW_UTC,
    World,
    _bstop,
    _position,
    _trade,
)

UNREADABLE = Exception("HTTP 503 Service Unavailable")


async def _drive(w, *steps):
    undo = H._install(w)
    try:
        return [await step() for step in steps]
    finally:
        H._uninstall(undo)


def _calls(w) -> list[str]:
    return [c["method"] for c in w.calls]


def _audits(w, event_type) -> list[dict]:
    return [json.loads(a["detail"] or "{}") for a in w.audits if a["event_type"] == event_type]


def _placed(w) -> list:
    return [c["args"] for c in w.calls if c["method"] == "place_stop_order"]


def _repair(stop_price=58.0):
    """The reconciler as the 17:00 slot / the sync drive it: target 10 from the books."""
    return om._ensure_stop_coverage_outcome(401, "KOD", 10.0, stop_price, "magna53", "live")


# ── the place branch on a FLAT broker ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_flat_broker_places_nothing_and_says_so_in_plain_words():
    w = World()
    _trade(w, stop_id=None)                       # the books: 10 sh, no stop pointer; the broker: nothing
    [out] = await _drive(w, _repair)
    assert _placed(w) == [], w.calls
    assert _calls(w) == ["get_open_orders", "get_position", "get_all_positions"], w.calls
    assert out.status == om.COVERAGE_FLAGGED and out.reason == "broker_flat", out
    low = out.message.lower()
    assert "no position" in low and "no stop was placed" in low, out.message
    assert "still show the trade open" in low and "/syncnow" in low and "by hand" in low, out.message
    assert "breached" not in low and "above market" not in low and "manual intervention" not in low
    assert w.trades[401]["stop_order_id"] is None          # no pointer written


@pytest.mark.asyncio
async def test_flat_broker_writes_one_audit_row_and_no_repair_failed_row():
    w = World()
    _trade(w, stop_id=None)
    await _drive(w, _repair)
    rows = _audits(w, "coverage_skipped_broker_flat")
    assert len(rows) == 1, w.audits
    assert rows[0]["trade_id"] == 401 and rows[0]["ticker"] == "KOD"
    assert rows[0]["account_mode"] == "live" and rows[0]["target_qty"] == 10.0
    assert rows[0]["db_stop_price"] == 58.0
    # no failure row → a flat never STARTS a retry; no breach row either (no stop was ever sent)
    assert _audits(w, "stop_coverage_repair_failed") == []
    assert _audits(w, "stop_coverage_breach") == []
    assert _audits(w, "stop_coverage_repaired") == []
    assert all("may re-place" not in a["summary"] for a in w.audits), w.audits


@pytest.mark.asyncio
async def test_the_retry_treats_a_flat_row_after_a_failure_as_terminal(monkeypatch):
    """The 09:40 repair failed (a failure row); the 09:45 pass read a flat broker (a flat row). The
    5-minute retry must leave the trade alone — not examine it, not read the broker, not spend an
    attempt — exactly as it leaves a breached trade alone."""
    monkeypatch.setattr(om, "active_account_modes", lambda: ["paper", "live"])
    w = World()
    _trade(w, stop_id=None)
    for ev in ("stop_coverage_repair_failed", "coverage_skipped_broker_flat"):
        w.audits.append({"event_type": ev, "summary": "KOD: …", "created_at": NOW_UTC,
                         "detail": json.dumps({"trade_id": 401, "ticker": "KOD",
                                               "account_mode": "live", "target_qty": 10.0})})
    [out] = await _drive(w, om.retry_failed_coverage_repairs)
    assert out["examined"] == 0 and out["retried"] == 0, out
    assert _calls(w) == [], w.calls
    assert [a["event_type"] for a in w.audits[2:]] == []       # no attempt / defer row written


@pytest.mark.asyncio
async def test_the_retry_still_examines_a_failure_with_no_flat_row(monkeypatch):
    """Pins that the terminal check is narrow: a failure on its own is still retried (and the retry's
    own position read then skips the flat broker as it always has)."""
    monkeypatch.setattr(om, "active_account_modes", lambda: ["paper", "live"])
    w = World()
    _trade(w, stop_id=None)
    w.audits.append({"event_type": "stop_coverage_repair_failed", "summary": "KOD: …",
                     "created_at": NOW_UTC,
                     "detail": json.dumps({"trade_id": 401, "ticker": "KOD",
                                           "account_mode": "live"})})
    [out] = await _drive(w, om.retry_failed_coverage_repairs)
    assert out["examined"] == 1, out
    assert _calls(w) == ["get_position"], w.calls


# ── UNREADABLE and HELD: exactly today's behaviour ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_unreadable_broker_places_from_the_books_exactly_as_before():
    w = World()
    _trade(w, stop_id=None)
    w.list_errors = [UNREADABLE]                  # the single read is blank, the list read fails
    [out] = await _drive(w, _repair)
    assert [(p["qty"], p["stop_price"]) for p in _placed(w)] == [(10, 58.0)], w.calls
    assert out.status == om.COVERAGE_REPAIRED and out.reason == "placed_coverage_stop", out
    assert w.trades[401]["stop_order_id"] == "stop-1"
    assert _audits(w, "coverage_skipped_broker_flat") == []
    # the ONLY difference from main is the read that told unreadable from flat
    assert _calls(w) == ["get_open_orders", "get_position", "get_all_positions",
                         "place_stop_order"], w.calls


@pytest.mark.asyncio
async def test_held_broker_places_exactly_as_before_and_never_touches_the_list():
    w = World()
    _trade(w, stop_id=None)
    _position(w, "KOD", 10, 10)
    [out] = await _drive(w, _repair)
    assert [(p["qty"], p["stop_price"]) for p in _placed(w)] == [(10, 58.0)], w.calls
    assert out.status == om.COVERAGE_REPAIRED and out.reason == "placed_coverage_stop", out
    assert _calls(w) == ["get_open_orders", "get_position", "place_stop_order"], w.calls


@pytest.mark.asyncio
async def test_held_broker_with_a_different_count_does_not_resize_the_target():
    """Ruling (a) is a READ before placing, not a re-sizing: the broker shows 7, the caller said 10
    (the books) — the stop is still placed for 10, exactly as main places it. Widening the target to
    the position read would be a sizing change, which is his, not this ruling's."""
    w = World()
    _trade(w, stop_id=None)
    _position(w, "KOD", 7, 7)
    await _drive(w, _repair)
    assert [p["qty"] for p in _placed(w)] == [10], w.calls


# ── only the place branch reads ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_replace_branch_does_not_read_the_position():
    """A live but under-covering stop goes through `replace_order`; no position read is added."""
    w = World()
    _trade(w)
    _position(w, "KOD", 10, 4)
    _bstop(w, "stop-1", "KOD", 6, 58.0)
    await _drive(w, _repair)
    assert _calls(w) == ["get_open_orders", "replace_order"], w.calls


@pytest.mark.asyncio
async def test_the_no_price_return_does_not_read_the_position():
    """No stop and no stop price places nothing either way, so it does not read — its message is
    byte-identical to main."""
    w = World()
    _trade(w, stop_id=None, stop_price=None)
    [out] = await _drive(w, lambda: _repair(stop_price=None))
    assert _calls(w) == ["get_open_orders"], w.calls
    assert out.reason == "no_stop_and_no_stop_price" and out.status == om.COVERAGE_FLAGGED


@pytest.mark.asyncio
async def test_the_detector_only_path_does_not_read_the_position():
    """`check_position_coverage` (repairs OFF, the intraday 09:31-15:55 job) still reads orders only."""
    w = World()
    _trade(w, stop_id=None)
    [out] = await _drive(w, lambda: om.check_position_coverage(notify=False))
    assert _calls(w) == ["get_open_orders"], w.calls
    assert [g["ticker"] for g in out["gaps"]] == ["KOD"]


# ── ONE shared helper ──────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_helper_names_the_three_answers():
    w = World()
    _trade(w)
    [flat] = await _drive(w, lambda: om._read_broker_position("KOD", "live"))
    assert flat == (om.BROKER_FLAT, None)
    w.list_errors = [UNREADABLE]
    [unreadable] = await _drive(w, lambda: om._read_broker_position("KOD", "live"))
    assert unreadable == (om.BROKER_UNREADABLE, None)
    _position(w, "KOD", 10, 10)
    [held] = await _drive(w, lambda: om._read_broker_position("KOD", "live"))
    assert held[0] == om.BROKER_HELD and held[1]["qty"] == 10.0


@pytest.mark.asyncio
async def test_a_stubbed_helper_steers_both_consumers(monkeypatch):
    seen = []

    async def _flat(ticker, account_mode):
        seen.append((ticker, account_mode))
        return om.BROKER_FLAT, None

    monkeypatch.setattr(om, "_read_broker_position", _flat)
    w = World()
    _trade(w, stop_id=None)
    [sized, out] = await _drive(
        w, lambda: om._broker_free_qty_for_restore("KOD", "live", 10.0), _repair)
    assert sized == (0, "broker_flat")
    assert out.reason == "broker_flat"
    assert seen == [("KOD", "live"), ("KOD", "live")]
    assert _calls(w) == ["get_open_orders"]       # neither consumer read the broker on its own


# ── the page sentence and the 17:00 slot end to end ────────────────────────────────────────────

def test_the_flat_page_sentence_now_tells_the_truth_about_the_repair():
    low = om.FLAT_RESTORE_PAGE_BODY.lower()
    assert "may re-place" not in low
    assert "coverage repair" in low and "reads the broker" in low
    assert "will not re-place a stop while it shows no position" in low


@pytest.mark.asyncio
async def test_the_1700_slot_on_a_flat_broker_places_nothing():
    """The slot's detector sizes the gap from the books and re-drives the repairer; the repairer
    reads the broker flat and withholds the stop. Main placed a 10-share sell stop on the empty
    account here. The slot's own page still reads the ROW ('holds 10 sh') — that wording is the
    slot's, not this ruling's, and is recorded in the SSoT."""
    w = World()
    _trade(w, stop_id=None)
    await _drive(w, lambda: sched._coverage_watch_job("post_close"))
    assert _placed(w) == [], w.calls
    assert "close_position" not in _calls(w)
    assert len(_audits(w, "coverage_skipped_broker_flat")) == 1
    assert w.trades[401]["stop_order_id"] is None
    assert len(w.pages) == 1 and "UNPROTECTED AFTER THE CLOSE" in w.pages[0], w.pages
