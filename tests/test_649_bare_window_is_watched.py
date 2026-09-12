"""#649 (2026-09-12) — a stop lost after the close is now noticed inside the window, not at 9 PM.

WHAT THIS CLOSES. OKTA lost its stop at 16:02 on 2026-09-11 and the first thing that could
have noticed was the 21:00 backstop: **about five hours bare, four of them inside
extended-hours trading, when the position was tradeable and unprotected.** #646 (a1) added
one check at 21:10, which verifies the 21:00 REPAIR — it cannot help during the window
itself.

⚠ WHY THERE IS NO REPAIR HERE, and it is the whole design constraint: widening
`stop_ack_timeout_watchdog` past 16:00 is the obvious fix and it is BARRED — it re-arms at
the ORIGINAL `orb_low` with no #600 re-protect floor, so on a trailed position it would
LOWER protection. That is a price change and THE LINE, and he ruled the sibling fork the
same day: page only. These slots TELL him; they place, cancel and replace nothing.

WHY THE THREE TIMES: 17:00 is after the 16:20 post-close refresh has restored the
overnight GTC stop, so a gap there is real rather than the ordinary 16:15 expiry; 19:00 is
mid-window with extended hours still trading; 21:10 keeps #646 (a1)'s slot and its own
wording, because by then a repair has been attempted and failed.

MUTATION-PROVEN, reported as the runs came back rather than as a tidy pairing:
  - delete the post_close/late entries from the registration loop -> ONE:
    test_all_three_slots_are_registered_and_execution_owned;
  - give every slot the evening wording -> ONE: test_each_slot_says_what_actually_happens_next;
  - drop `notify=False` -> ONE: test_every_slot_bypasses_the_detectors_day_dedup;
  - trust the repairer and skip the re-read -> FOUR: verdict_is_a_fresh_broker_read,
    every_slot_pages_on_a_real_gap, a_raising_repairer_still_pages,
    each_slot_says_what_actually_happens_next;
  - let the evening slot repair too -> ONE: test_the_evening_slot_still_repairs_NOTHING.
"""
from __future__ import annotations

import json
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

SLOTS = ("post_close", "late", "evening")


def _wire(monkeypatch, *, result):
    from agents.market_intelligence import scheduler as sch
    from agents.market_intelligence.broker import order_manager as om
    from agents.market_intelligence import constants as const

    audited, sent = [], []

    async def _audit(evt, summary=None, detail=None):
        audited.append((evt, summary, detail))

    async def _tg(msg, *a, **k):
        sent.append(msg)
        return True

    detector = AsyncMock(return_value=result)
    monkeypatch.setattr(om, "check_position_coverage", detector)
    monkeypatch.setattr(sch, "log_audit_event", _audit)
    monkeypatch.setattr(sch, "send_telegram_message", _tg)
    monkeypatch.setattr(sch, "notify_job_failure", AsyncMock())
    monkeypatch.setattr(const, "LIVE_TRADING_ENABLED", True)
    writes = {n: AsyncMock() for n in
              ("place_stop_order", "cancel_order", "replace_order", "close_position")}
    for n, m in writes.items():
        if hasattr(om.alpaca, n):
            monkeypatch.setattr(om.alpaca, n, m)
    return {"detector": detector, "audited": audited, "sent": sent, "writes": writes}


def _gap():
    return {"examined": 2, "covered": 1,
            "gaps": [{"trade_id": 382, "ticker": "OKTA", "target": 2.0, "live_qty": 0.0}],
            "check_failed": [], "deferred": []}


def _clean():
    return {"examined": 2, "covered": 2, "gaps": [], "check_failed": [], "deferred": []}


def test_all_three_slots_are_registered_and_execution_owned():
    """The window is ~5 hours; one slot at the end of it was the gap."""
    from agents.market_intelligence.scheduler import (
        EXECUTION_OWNED_JOB_IDS, INTELLIGENCE_OWNED_JOB_IDS,
    )
    src = open("agents/market_intelligence/scheduler.py").read()
    for slot, hh, mm in (("post_close", 17, 0), ("late", 19, 0), ("evening", 21, 10)):
        assert f'("{slot}", {hh}, {mm})' in src, f"{slot} slot missing from the loop"
        jid = f"coverage_watch_{slot}"
        assert jid in EXECUTION_OWNED_JOB_IDS, f"{jid} must hold broker credentials"
        assert jid not in INTELLIGENCE_OWNED_JOB_IDS


@pytest.mark.asyncio
@pytest.mark.parametrize("slot", SLOTS)
async def test_every_slot_pages_on_a_real_gap(monkeypatch, slot):
    from agents.market_intelligence import scheduler as sch
    h = _wire(monkeypatch, result=_gap())

    await sch._coverage_watch_job(slot)

    assert len(h["sent"]) == 1, f"{slot} must page"
    assert "OKTA" in h["sent"][0] and "2 sh" in h["sent"][0]


@pytest.mark.asyncio
async def test_each_slot_says_what_actually_happens_next(monkeypatch):
    """THE POINT OF SEPARATE SLOTS. A 17:00 page that said 'the 9 PM sync already tried'
    would be a lie — nothing has tried yet, and he would stand down on it."""
    from agents.market_intelligence import scheduler as sch
    msgs = {}
    for slot in SLOTS:
        h = _wire(monkeypatch, result=_gap())
        await sch._coverage_watch_job(slot)
        msgs[slot] = h["sent"][0]

    assert "Extended hours are still trading" in msgs["post_close"]
    assert "the automatic repair above did not hold" in msgs["post_close"]
    assert "the 9:00 PM sync is the next automatic attempt" in msgs["late"]
    assert "already tried and did not fix this" in msgs["evening"]
    assert "9:00 AM ET" in msgs["evening"], (
        "only the evening page should send him to the morning watchdog — the in-window "
        "slots have a nearer automatic attempt to name"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("slot", SLOTS)
async def test_every_slot_writes_its_row_even_when_clean(monkeypatch, slot):
    """Liveness: without a row on a quiet evening, a covered book and a dead job are the
    same silence — the reading this repo refuses to accept."""
    from agents.market_intelligence import scheduler as sch
    h = _wire(monkeypatch, result=_clean())

    await sch._coverage_watch_job(slot)

    assert len(h["audited"]) == 1
    evt, _summary, detail = h["audited"][0]
    assert slot in evt or evt == "coverage_verified_evening"
    assert json.loads(detail)["examined"] == 2
    assert not h["sent"]


@pytest.mark.asyncio
async def test_the_evening_slot_still_repairs_NOTHING(monkeypatch):
    """His ruling of 2026-09-12 stands for 21:10 on its own evidence: the 21:00 backstop
    has already made three attempts with backoff, so a fourth ten minutes later adds
    little. The in-window slots are the opposite case — nothing has tried."""
    from agents.market_intelligence import scheduler as sch
    from agents.market_intelligence.broker import order_manager as om
    h = _wire(monkeypatch, result=_gap())
    repairer = AsyncMock()
    monkeypatch.setattr(om, "_ensure_stop_coverage", repairer)

    await sch._coverage_watch_job("evening")

    repairer.assert_not_called()
    for _n, m in h["writes"].items():
        m.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("slot", ("post_close", "late"))
async def test_an_in_window_slot_drives_the_SIGNED_repairer_and_never_the_broker_directly(
        monkeypatch, slot):
    """THE LINE, in the shape he authorised. The job may re-drive `_ensure_stop_coverage`
    — which places at `_apply_reprotect_floor`, floored to the last level the broker held,
    so it can never place worse than the position's current stop. It may NOT reach the
    broker itself, because that would bypass the floor and is exactly how the morning
    watchdog hands back a trail."""
    from agents.market_intelligence import scheduler as sch
    from agents.market_intelligence.broker import order_manager as om
    h = _wire(monkeypatch, result=_gap())
    repairer = AsyncMock()
    monkeypatch.setattr(om, "_ensure_stop_coverage", repairer)

    await sch._coverage_watch_job(slot)

    repairer.assert_awaited_once()
    assert repairer.await_args.args[1] == "OKTA"
    for _n, m in h["writes"].items():
        m.assert_not_called(), "the job must never place a stop itself — only via the floor"


@pytest.mark.asyncio
@pytest.mark.parametrize("slot", ("post_close", "late"))
async def test_the_verdict_is_a_fresh_broker_read_not_the_repairers_word(monkeypatch, slot):
    """A repairer that returns happily while leaving no live stop must still page.
    'I tried' is not coverage — the #527 detector is asked again and IT decides."""
    from agents.market_intelligence import scheduler as sch
    from agents.market_intelligence.broker import order_manager as om
    h = _wire(monkeypatch, result=_gap())
    monkeypatch.setattr(om, "_ensure_stop_coverage", AsyncMock(return_value="repaired!"))

    await sch._coverage_watch_job(slot)

    assert h["detector"].await_count == 2, "the broker must be re-read after the repair"
    assert h["sent"], "still uncovered on the re-read -> he is told, whatever the repairer said"


@pytest.mark.asyncio
@pytest.mark.parametrize("slot", ("post_close", "late"))
async def test_a_successful_repair_is_silent_but_recorded(monkeypatch, slot):
    """No page when the re-read comes back clean — but a durable row either way, so a
    repair that happened is distinguishable from a night nothing needed."""
    from agents.market_intelligence import scheduler as sch
    from agents.market_intelligence.broker import order_manager as om
    h = _wire(monkeypatch, result=_gap())
    h["detector"].side_effect = [_gap(), _clean()]
    monkeypatch.setattr(om, "_ensure_stop_coverage", AsyncMock())

    await sch._coverage_watch_job(slot)

    assert not h["sent"], "a repair that worked should not page him at 5pm"
    evts = [e for e, *_ in h["audited"]]
    assert any(e.endswith("_repair_attempted") for e in evts)
    row = json.loads(next(d for e, _s, d in h["audited"] if e.endswith("_repair_attempted")))
    assert row["attempted"] == ["OKTA"] and row["still_uncovered"] == []


@pytest.mark.asyncio
async def test_a_raising_repairer_still_pages(monkeypatch):
    """The repairer blowing up must not swallow the alarm — the gap is the point."""
    from agents.market_intelligence import scheduler as sch
    from agents.market_intelligence.broker import order_manager as om
    h = _wire(monkeypatch, result=_gap())
    monkeypatch.setattr(om, "_ensure_stop_coverage",
                        AsyncMock(side_effect=RuntimeError("broker down")))

    await sch._coverage_watch_job("post_close")

    assert h["sent"] and "OKTA" in h["sent"][0]


@pytest.mark.asyncio
@pytest.mark.parametrize("slot", SLOTS)
async def test_every_slot_bypasses_the_detectors_day_dedup(monkeypatch, slot):
    """The detector's own page is deduped per trade per ET day, so without this the 19:00
    and 21:10 slots would be silenced by the 17:00 one on the same ticker."""
    from agents.market_intelligence import scheduler as sch
    h = _wire(monkeypatch, result=_gap())

    await sch._coverage_watch_job(slot)

    assert h["detector"].await_args.kwargs.get("notify") is False


def test_the_evening_slot_keeps_the_event_name_its_heartbeat_asserts():
    """`run_evening_verify_heartbeat` looks for `coverage_verified_evening`. Renaming it
    during the generalisation would have silently blinded that heartbeat."""
    from agents.market_intelligence.scheduler import _COVERAGE_SLOTS
    from agents.market_intelligence.health_checks import _EVENING_VERIFY_AUDIT_EVENTS
    assert _COVERAGE_SLOTS["evening"][0] in _EVENING_VERIFY_AUDIT_EVENTS
