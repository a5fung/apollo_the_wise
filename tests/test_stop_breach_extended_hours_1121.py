"""Operator ruling 2026-11-20 (PLAN.md #728, EVER paper trade 1427): a stop the broker refuses as
"above the market" OUTSIDE the regular session must NOT trigger the #687 ruling (iii) market sale.

EVER: the entry bracket's DAY stop leg expired at 16:00 ET; at 16:05 the position sync's orphan
repair re-placed the stop at $28.68; the broker refused it against an AFTER-HOURS print of $27.50
(the regular close was $29.00), and ruling (iii) queued a market sale for Monday's open. The
regular session never traded through the stop.

What this file proves, per site, in the #687 convergence harness's fake world:
  * outside the regular session → no `close_position`, a `stop_breach_sale_deferred_extended_hours`
    row, and a page that says no sale was queued and the stop is retried;
  * inside the regular session → the sale, unchanged (the control: the same world sells);
  * any other refusal → unchanged, whatever the clock says;
  * the NEXT regular session still sells a stop that is still refused (09:35 refresh → `update_stop`);
  * the stream's DEAD full-exit restore (a queued sale cancelled / expired / rejected) defers the
    same way since 2026-11-21, inline and in its background held-shares retry;
  * ruling (3)'s FAILED-sale restore (`_restore_stop_after_failed_exit`) is NOT gated.
`_regular_session_open_now` itself is tested on the clock edges (09:29 / 09:30 / 15:59 / 16:00,
a Saturday, a holiday, a 13:00 half day, an unreadable calendar).
"""
from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import tests._convergence_687_harness as H
from agents.market_intelligence.broker import live_tracker as lt
from agents.market_intelligence.broker import order_manager as om
from agents.market_intelligence.broker import trade_stream as ts
from tests._convergence_687_harness import (
    BREACH,
    World,
    _bsell,
    _bstop,
    _mirror,
    _position,
    _trade,
    _ws_order,
)

# The real clock read, captured before the harness swaps the module attribute for its fake.
_REAL_SESSION_READ = om._regular_session_open_now
_ET = ZoneInfo("America/New_York")
OTHER = "insufficient qty available"
DEFERRED = "stop_breach_sale_deferred_extended_hours"


def _world(*, in_session: bool) -> World:
    w = World()
    w.regular_session = in_session
    return w


def _breach(w, n=8):
    w.place_errors = [Exception(BREACH) for _ in range(n)]


async def _drive(w, *steps):
    # The harness patches the broker client it finds as `broker.alpaca_client`. Two earlier suites
    # (test_broker_reject_reason_540, test_replace_order_kwargs_numeric) re-import that module and
    # can leave the package attribute on a COPY the code under test does not use — the fake broker
    # would then never be reached. Point both names at the module `order_manager` really holds.
    import sys

    import agents.market_intelligence.broker as broker_pkg
    name = "agents.market_intelligence.broker.alpaca_client"
    before = (getattr(broker_pkg, "alpaca_client", None), sys.modules.get(name))
    broker_pkg.alpaca_client = sys.modules[name] = om.alpaca
    undo = H._install(w)
    try:
        return [await step() for step in steps]
    finally:
        H._uninstall(undo)
        broker_pkg.alpaca_client, sys.modules[name] = before


def _sales(w) -> list:
    return [c["args"].get("qty") for c in w.calls if c["method"] == "close_position"]


def _audits(w, event_type) -> list[dict]:
    return [json.loads(a["detail"] or "{}") for a in w.audits if a["event_type"] == event_type]


def _no_sale_anywhere(w):
    assert _sales(w) == [], w.calls
    assert [o for o in w.orders if o["purpose"] == "full_exit"] == [], w.orders
    assert not _audits(w, "stop_breach_market_sale"), w.audits
    assert not any("Price already below the stop" in p for p in w.pages), w.pages


def _says_deferred(text: str):
    assert "NO sale was queued" in text and "outside regular hours" in text, text
    assert "retried" in text and "sold at market then" in text, text


# ── The clock read ────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("stamp, expected", [
    ((2026, 11, 20, 9, 29), False),     # Friday, pre-market
    ((2026, 11, 20, 9, 30), True),      # the open
    ((2026, 11, 20, 15, 59), True),
    ((2026, 11, 20, 16, 0), False),     # the close minute is already extended hours
    ((2026, 11, 20, 16, 5), False),     # EVER: the 16:05 sync
    ((2026, 11, 20, 21, 0), False),     # the 21:00 backstop sync
    ((2026, 11, 21, 11, 0), False),     # Saturday
    ((2026, 11, 26, 11, 0), False),     # Thanksgiving
    ((2026, 11, 27, 12, 59), True),     # half day, before the 13:00 close
    ((2026, 11, 27, 13, 5), False),     # half day, after it — 16:00 would have read in-session
])
def test_the_regular_session_read(stamp, expected):
    assert _REAL_SESSION_READ(datetime(*stamp, tzinfo=_ET)) is expected


def test_an_unreadable_calendar_falls_back_to_the_plain_clock(monkeypatch):
    """A calendar failure must not switch the signed in-session sale off."""
    from agents.market_intelligence import trading_calendar

    def _boom(*a, **k):
        raise RuntimeError("calendar down")

    monkeypatch.setattr(trading_calendar, "get_market_status", _boom)
    assert _REAL_SESSION_READ(datetime(2026, 11, 20, 11, 0, tzinfo=_ET)) is True
    assert _REAL_SESSION_READ(datetime(2026, 11, 20, 16, 5, tzinfo=_ET)) is False
    assert _REAL_SESSION_READ(datetime(2026, 11, 21, 11, 0, tzinfo=_ET)) is False


# ── The helper itself ─────────────────────────────────────────────────────────────────────────

def _helper(refusal):
    return lambda: om._sell_at_market_for_refused_stop(
        401, "KOD", "paper", stop_price=58.0, site="test.site", refusal=refusal)


@pytest.mark.asyncio
async def test_helper_outside_the_session_sells_nothing_and_returns_the_falsy_marker():
    w = _world(in_session=False)
    _trade(w, stop_id=None)
    _position(w, "KOD", 10, 10)
    [out] = await _drive(w, _helper(Exception(BREACH)))
    assert out is om.STOP_BREACH_SALE_DEFERRED and not out
    _no_sale_anywhere(w)
    assert w.pages == []                                   # the caller words the page
    [row] = _audits(w, DEFERRED)
    assert row["trade_id"] == 401 and row["site"] == "test.site" and row["stop_price"] == 58.0
    assert row["account_mode"] == "paper" and "less than current price" in row["stop_error"]


@pytest.mark.asyncio
async def test_helper_inside_the_session_sells_as_before():
    w = _world(in_session=True)
    _trade(w, stop_id=None)
    _position(w, "KOD", 10, 10)
    [out] = await _drive(w, _helper(Exception(BREACH)))
    assert out and out[1] == 10 and _sales(w) == [10]
    assert not _audits(w, DEFERRED)
    assert _audits(w, "stop_breach_market_sale")[0]["site"] == "test.site"


@pytest.mark.asyncio
@pytest.mark.parametrize("in_session", [True, False])
async def test_helper_any_other_refusal_is_untouched_by_the_clock(in_session):
    w = _world(in_session=in_session)
    _trade(w, stop_id=None)
    _position(w, "KOD", 10, 10)
    out_other, out_none = await _drive(w, _helper(Exception(OTHER)), _helper(None))
    assert out_other is None and out_none is None
    assert _sales(w) == [] and w.audits == [] and w.pages == []


# ── Site 2 — the position sync's orphan repair (EVER's own path: 16:05 ET) ───────────────────

def _orphan_world(*, in_session):
    w = _world(in_session=in_session)
    _trade(w, stop_id=None)
    _position(w, "KOD", 10, 10)
    return w


def _sync():
    return lambda: om._sync_positions_for_mode("live")


@pytest.mark.asyncio
async def test_sync_orphan_after_hours_queues_no_sale_and_says_so():
    w = _orphan_world(in_session=False)
    _breach(w)
    await _drive(w, _sync())
    _no_sale_anywhere(w)
    [digest] = [p for p in w.pages if "Position Sync Discrepancies" in p]
    assert "Orphaned position KOD" in digest
    _says_deferred(digest)
    # nothing in the digest claims a breach, a failed repair or a decision waiting on him
    for false_line in ("SOLD AT MARKET", "Failed to remediate", "Operator decision needed",
                       "ABOVE market"):
        assert false_line not in digest, digest
    sites = {d["site"] for d in _audits(w, DEFERRED)}
    assert "order_manager.sync_orphan_remediation" in sites, w.audits
    assert not _audits(w, "stop_coverage_breach")           # not "through the stop"
    assert not [d for d in _audits(w, "stop_ack_remediation_failed")
                if d.get("reason") == "place_stop_failed_3_attempts"]
    assert w.trades[401]["stop_order_id"] is None           # still an orphan → the next pass retries
    assert w.trades[401]["stop_price"] == 58.0              # the stop level is untouched


@pytest.mark.asyncio
async def test_sync_orphan_in_the_regular_session_sells_unchanged():
    w = _orphan_world(in_session=True)
    _breach(w)
    await _drive(w, _sync())
    assert _sales(w) == [10], w.calls
    [digest] = [p for p in w.pages if "Position Sync Discrepancies" in p]
    assert "SOLD AT MARKET" in digest and "NO sale was queued" not in digest
    assert not _audits(w, DEFERRED)


@pytest.mark.asyncio
async def test_sync_orphan_any_other_refusal_after_hours_keeps_todays_line():
    w = _orphan_world(in_session=False)
    w.place_errors = [Exception(OTHER) for _ in range(4)]
    await _drive(w, _sync())
    assert _sales(w) == [] and not _audits(w, DEFERRED)
    [digest] = [p for p in w.pages if "Position Sync Discrepancies" in p]
    assert "Failed to remediate orphaned stop for KOD" in digest


@pytest.mark.asyncio
async def test_a_later_sync_whose_stop_is_accepted_places_it_at_the_same_price():
    """The after-hours print lifts back above the stop by the next pass: the stop goes on, at the
    trade's own stop price, for the same shares — nothing was sold in between."""
    w = _orphan_world(in_session=False)
    w.place_errors = [Exception(BREACH) for _ in range(4)]   # the first sync: 3 orphan + 1 coverage
    await _drive(w, _sync(), _sync())
    _no_sale_anywhere(w)
    placed = [c["args"] for c in w.calls if c["method"] == "place_stop_order"]
    assert float(placed[-1]["stop_price"]) == 58.0 and float(placed[-1]["qty"]) == 10, placed
    assert w.trades[401]["stop_order_id"] is not None


# ── Site 1 — the coverage reconciler ──────────────────────────────────────────────────────────

def _reconcile():
    return lambda: om._ensure_stop_coverage_outcome(401, "KOD", 10.0, 58.0, "magna53", "live")


@pytest.mark.asyncio
async def test_coverage_reconciler_after_hours_flags_without_a_sale_or_a_breach_row():
    w = _world(in_session=False)
    _trade(w, stop_id=None)
    _position(w, "KOD", 10, 10)
    _breach(w)
    [out] = await _drive(w, _reconcile())
    _no_sale_anywhere(w)
    assert out.status == om.COVERAGE_FLAGGED and out.reason == DEFERRED, out
    _says_deferred(out.message)
    assert not _audits(w, "stop_coverage_breach")
    assert _audits(w, DEFERRED)[0]["site"] == "order_manager.ensure_stop_coverage"


@pytest.mark.asyncio
async def test_coverage_reconciler_in_the_regular_session_sells_unchanged():
    w = _world(in_session=True)
    _trade(w, stop_id=None)
    _position(w, "KOD", 10, 10)
    _breach(w)
    [out] = await _drive(w, _reconcile())
    assert _sales(w) == [10] and out.reason == "stop_breach_sold_at_market", out


# ── Site 3 — `update_stop` (the 16:20 / 09:35 refresh, the 16:45 trail raise) ────────────────

def _expired_stop_world(*, in_session):
    """A DAY stop that expired at the close; the refresh re-places it."""
    w = _world(in_session=in_session)
    _trade(w)
    _position(w, "KOD", 10, 10)
    _bstop(w, "stop-1", "KOD", 10, 58.0, status="expired")
    return w


def _refresh(label):
    return lambda: lt._stop_refresh(include_same_day=(label == "post-close"), label=label)


@pytest.mark.asyncio
async def test_post_close_refresh_after_hours_queues_no_sale_and_pages_once():
    w = _expired_stop_world(in_session=False)
    _breach(w)
    [placed] = await _drive(w, _refresh("post-close"))
    assert placed == 0
    _no_sale_anywhere(w)
    assert len(w.pages) == 1, w.pages                       # one page, not NAKED + "No stop on"
    assert "No stop resting, no sale queued" in w.pages[0] and "KOD" in w.pages[0]
    _says_deferred(w.pages[0])
    assert "STOP FAILED — position NAKED" not in w.pages[0]
    ran = _audits(w, "stop_refresh_ran")[0]
    assert ran["no_stop_sale_deferred_extended_hours"] == ["KOD"] and ran["unprotected"] == []
    assert _audits(w, DEFERRED)[0]["site"] == "order_manager.update_stop"
    # the position IS without a stop, and the books say so: the pointer is cleared for the sync
    assert w.trades[401]["stop_order_id"] is None and w.trades[401]["stop_price"] == 58.0
    assert _audits(w, "stop_update_failed") and _audits(w, "naked_position_detected")


@pytest.mark.asyncio
async def test_update_stop_returns_the_falsy_marker_after_hours():
    w = _world(in_session=False)
    _trade(w, stop_price=58.0)
    _position(w, "KOD", 10, 0)
    _bstop(w, "stop-1", "KOD", 10, 58.0)
    _breach(w)
    [out] = await _drive(w, lambda: om.update_stop(401, 61.5, stop_source="trail"))
    assert out is om.STOP_BREACH_SALE_DEFERRED and not out
    _no_sale_anywhere(w)
    assert w.trades[401]["stop_price"] == 58.0              # a refused raise never moves the level


@pytest.mark.asyncio
async def test_the_next_sessions_refresh_still_sells_a_stop_that_is_still_refused():
    """The signed rule still acts in-session. After hours: deferred (16:20). Next morning, 09:35,
    the stop is still refused through the price → the shares are sold at market, as ruling (iii)."""
    w = _expired_stop_world(in_session=False)
    _breach(w, n=16)

    async def _the_open():
        w.regular_session = True

    await _drive(w, _refresh("post-close"), _the_open, _refresh("Morning"))
    assert _sales(w) == [10], w.calls
    assert len([p for p in w.pages if "Price already below the stop" in p]) == 1, w.pages
    assert _audits(w, "stop_breach_market_sale")[0]["site"] == "order_manager.update_stop"
    assert [r.get("sold_at_market") for r in _audits(w, "stop_refresh_ran")] == [None, ["KOD"]]


# ── Site 4 — the stop-ACK watchdog (its cron starts 09:00 ET, before the open) ────────────────

def _watchdog():
    import agents.market_intelligence.scheduler as sched
    return sched._stop_ack_timeout_watchdog_job


@pytest.mark.asyncio
async def test_watchdog_pre_market_defers_without_spending_its_daily_attempt(monkeypatch):
    monkeypatch.setenv("STOP_ACK_TIMEOUT_GATE_ENABLED", "true")
    w = _world(in_session=False)
    _trade(w, stop_id=None)
    _position(w, "KOD", 10, 10)
    _breach(w, n=16)

    async def _the_open():
        w.regular_session = True

    await _drive(w, _watchdog(), _watchdog())               # two pre-market ticks
    _no_sale_anywhere(w)
    assert not any("CRITICAL" in p for p in w.pages), w.pages
    assert len(w.pages) == 1, w.pages                       # one page an hour, not one per tick
    _says_deferred(w.pages[0])
    assert len(_audits(w, "stop_ack_deferred_extended_hours")) == 1
    assert not _audits(w, "stop_ack_remediation_failed")    # would stand the watchdog down all day
    assert [c["method"] for c in w.calls].count("place_stop_order") == 2   # it did try again

    await _drive(w, _the_open, _watchdog())                 # the first tick inside the session
    assert _sales(w) == [10], w.calls
    assert len(_audits(w, "stop_ack_breach_sold_at_market")) == 1


# ── Site 5 — the stream's partial-exit restore ────────────────────────────────────────────────

def _partial_world(*, in_session):
    w = _world(in_session=in_session)
    _trade(w, stop_id="stop-r")
    _position(w, "KOD", 10, 0)
    _bstop(w, "stop-r", "KOD", 7, 58.0)
    _bsell(w, "sell-p", "KOD", 3, status="canceled")
    _mirror(w, "sell-p", 401, "KOD", "partial_exit", 3, status="accepted",
            exit_reason="partial_profit", raw={"order_class": "simple"})
    return w


def _partial_died():
    return lambda: ts._handle_cancel_or_reject(_ws_order("sell-p", "KOD"), "canceled", "live")


@pytest.mark.asyncio
async def test_partial_restore_after_hours_queues_no_sale_and_says_so():
    w = _partial_world(in_session=False)
    _breach(w)
    await _drive(w, _partial_died())
    _no_sale_anywhere(w)
    assert len(w.pages) == 1 and "no sale queued" in w.pages[0], w.pages
    _says_deferred(w.pages[0])
    assert "STOP RESTORE FAILED" not in w.pages[0] and "manual intervention" not in w.pages[0]
    assert _audits(w, DEFERRED)[0]["site"] == "trade_stream.partial_exit_cancel_restore"


@pytest.mark.asyncio
async def test_partial_restore_in_the_regular_session_sells_unchanged():
    w = _partial_world(in_session=True)
    _breach(w)
    await _drive(w, _partial_died())
    assert _sales(w) == [10], w.calls
    assert not _audits(w, DEFERRED)


# ── The stream's DEAD full-exit restore (operator "ok" 2026-11-21) ───────────────────────────
# EVER 1427: the queued after-hours breach sale is cancelled by hand at the weekend; the cancel
# event reaches this restore, the broker refuses the stop against the after-hours print — and
# before this change the restore queued the very sale that had just been cancelled.

HELD = ('{"available":"0","code":40310000,"existing_qty":"10","held_for_orders":"10",'
        '"message":"insufficient qty available for order (requested: 10, available: 0)"}')
FULL_EXIT_SITE = "trade_stream.full_exit_cancel_restore"


def _dead_sale_world(*, in_session):
    w = _world(in_session=in_session)
    _trade(w, stop_id=None)
    _position(w, "KOD", 10, 10)
    _bsell(w, "sell-q", "KOD", 10, status="canceled")
    _mirror(w, "sell-q", 401, "KOD", "full_exit", 10, status="accepted", exit_reason="stop_hit")
    return w


def _full_exit_died():
    async def _go():
        await ts._handle_cancel_or_reject(_ws_order("sell-q", "KOD"), "canceled", "paper")
        for task in list(ts._RESTORE_RETRY_BG_TASKS):     # the held-shares retry, when one started
            await task
    return _go


def _dead_sale_deferred(w):
    _no_sale_anywhere_but_the_dead_one(w)
    [row] = _audits(w, DEFERRED)
    assert row["site"] == FULL_EXIT_SITE and row["stop_price"] == 58.0 and row["trade_id"] == 401
    [page] = w.pages
    assert "Close order CANCELLED, no stop resting, no sale queued" in page, page
    _says_deferred(page)
    assert "STOP RESTORE FAILED" not in page and "manual intervention" not in page
    assert "selling" not in page
    # the dead sale's row is terminal, so no later pass reads the trade as "covered by a pending exit"
    [dead] = [o for o in w.orders if o["alpaca_order_id"] == "sell-q"]
    assert dead["status"] in om.PENDING_EXIT_TERMINAL_STATUSES, dead
    assert w.trades[401]["status"] == "filled" and w.trades[401]["stop_price"] == 58.0


def _no_sale_anywhere_but_the_dead_one(w):
    assert _sales(w) == [], w.calls
    assert [o["alpaca_order_id"] for o in w.orders if o["purpose"] == "full_exit"] == ["sell-q"]
    assert not _audits(w, "stop_breach_market_sale"), w.audits


@pytest.mark.asyncio
async def test_dead_full_exit_restore_after_hours_queues_no_sale_and_says_so():
    w = _dead_sale_world(in_session=False)
    _breach(w)
    await _drive(w, _full_exit_died())
    _dead_sale_deferred(w)
    assert len([c for c in w.calls if c["method"] == "place_stop_order"]) == 1


@pytest.mark.asyncio
async def test_dead_full_exit_restore_in_the_regular_session_sells_unchanged():
    w = _dead_sale_world(in_session=True)
    _breach(w)
    await _drive(w, _full_exit_died())
    assert _sales(w) == [10], w.calls
    assert not _audits(w, DEFERRED)
    assert _audits(w, "stop_breach_market_sale")[0]["site"] == FULL_EXIT_SITE
    assert len(w.pages) == 1 and "selling 10 sh at market now" in w.pages[0], w.pages


@pytest.mark.asyncio
async def test_dead_full_exit_restore_any_other_refusal_after_hours_keeps_todays_page():
    w = _dead_sale_world(in_session=False)
    w.place_errors = [Exception("order rejected: account restricted")]
    await _drive(w, _full_exit_died())
    assert _sales(w) == [] and not _audits(w, DEFERRED)
    assert len(w.pages) == 1 and "STOP RESTORE FAILED" in w.pages[0], w.pages


@pytest.mark.asyncio
async def test_dead_full_exit_background_retry_after_hours_queues_no_sale(monkeypatch):
    """The likelier EVER order of events: the just-cancelled sale still holds the shares (first
    refusal = held shares), the background retry waits, and ITS re-attempt is refused through the
    after-hours price."""
    monkeypatch.setattr(om, "_RESTORE_RETRY_SLEEP_S", 0.0)
    w = _dead_sale_world(in_session=False)
    w.place_errors = [Exception(HELD), Exception(BREACH)]
    await _drive(w, _full_exit_died())
    _dead_sale_deferred(w)
    [ended] = _audits(w, "stop_restore_retry_ended")
    assert ended["outcome"] == om.RESTORE_DEFERRED


@pytest.mark.asyncio
async def test_dead_full_exit_background_retry_in_the_regular_session_sells_unchanged(monkeypatch):
    monkeypatch.setattr(om, "_RESTORE_RETRY_SLEEP_S", 0.0)
    w = _dead_sale_world(in_session=True)
    w.place_errors = [Exception(HELD), Exception(BREACH)]
    await _drive(w, _full_exit_died())
    assert _sales(w) == [10], w.calls
    assert not _audits(w, DEFERRED)
    assert _audits(w, "stop_restore_retry_ended")[0]["outcome"] == om.RESTORE_SOLD


@pytest.mark.asyncio
async def test_a_later_pass_re_places_the_stop_after_a_deferred_dead_sale_restore():
    """After the deferral nothing reads the trade as covered by a pending exit: the 16:20 refresh
    places the stop at the same price once the broker accepts it."""
    w = _dead_sale_world(in_session=False)
    w.place_errors = [Exception(BREACH)]
    await _drive(w, _full_exit_died(), _refresh("Post-close"))
    assert _sales(w) == []
    live = [o for o in w.broker_orders if o["type"] == "stop" and o["status"] in H.LIVE_ORDER_STATUSES]
    assert [(o["qty"], o["stop_price"]) for o in live] == [(10.0, 58.0)], w.broker_orders
    assert w.trades[401]["stop_order_id"] == live[0]["id"]


# ── Ruling (3)'s FAILED-sale restore is NOT gated: the exit rule decided to sell moments ago ──

@pytest.mark.asyncio
async def test_the_failed_exit_restores_own_retry_after_hours_still_sells(monkeypatch):
    """`_retry_restore_while_shares_held` is shared with the stream's background retry. Without
    the stream's opt-in it sells after hours exactly as before; with it, it defers."""
    monkeypatch.setattr(om, "_RESTORE_RETRY_SLEEP_S", 0.0)

    def _retry(**kw):
        return lambda: om._retry_restore_while_shares_held(
            401, "KOD", 10, 58.0, "live", qty=10, first_error=Exception(HELD),
            cancelled_stop_id=None, reason="sma_trail_stop", signal_type="magna53", **kw)

    w = _world(in_session=False)
    _trade(w, stop_id=None)
    _position(w, "KOD", 10, 10)
    _breach(w)
    [out] = await _drive(w, _retry())
    assert out.outcome == om.RESTORE_SOLD and _sales(w) == [10] and not _audits(w, DEFERRED)

    w = _world(in_session=False)
    _trade(w, stop_id=None)
    _position(w, "KOD", 10, 10)
    _breach(w)
    [out] = await _drive(w, _retry(defer_breach_sale_outside_session_site=FULL_EXIT_SITE))
    assert out.outcome == om.RESTORE_DEFERRED and _sales(w) == []
    assert _audits(w, DEFERRED)[0]["site"] == FULL_EXIT_SITE


@pytest.mark.asyncio
async def test_a_failed_planned_sale_after_hours_still_sells_when_its_restore_is_refused(monkeypatch):
    """The 16:45 close-below sale runs after hours BY DESIGN. Its failed restore, refused through
    the price, still sells (`_sell_free_shares_after_stop_breach` called directly) — this
    restore has no session gate."""
    from tests.test_646_full_exit_never_returns_naked import _wire
    from tests.test_687_ruling3_stop_through_price_sells import BREACH as BREACH_EXC
    from tests.test_687_ruling3_stop_through_price_sells import _sale_on_second_close

    monkeypatch.setattr(om, "_regular_session_open_now", lambda *a, **k: False)
    h = _wire(monkeypatch, close_raises=True)
    calls = _sale_on_second_close(h)
    h["place"].side_effect = BREACH_EXC
    assert await om.execute_full_exit(382, "sma_trail_stop") is False
    assert calls == [None, 2], calls
    assert "SOLD AT MARKET" in h["sent"][-1], h["sent"]
