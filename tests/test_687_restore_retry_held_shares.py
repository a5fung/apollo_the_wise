"""#687 — operator ruling 2026-10-06: the failed-exit stop restore WAITS for the broker to release
the cancelled stop's shares instead of giving up on its first refusal.

THE EVIDENCE (paper rehearsal Day A, 2026-10-06, step B2 — scripts/probes/_1006/a2_why.out):
    09:35:43  planned_sale_stop_cancel   PEP: cancelling stop 97039c8b (a planned sale replaces it)
    09:35:48  full_exit_rejected         held_for_orders 4 — `_await_shares_released` gave up at 5 s
    09:35:48  ONE restore attempt         refused the same way — the cancel had not settled
    09:35:50  dead_stop_price_preserved   ... status=CANCELED — the broker confirms the cancel NOW
    09:36:30  stop_ack_timeout_remediated the watchdog's fallback stop — ~40 s with no stop

THE BEHAVIOUR (`order_manager._retry_restore_while_shares_held`): a placement refused because the
shares are still HELD is retried — poll the position every `_RESTORE_RETRY_SLEEP_S`, at most
`_RESTORE_RETRY_POLLS` times (~15 s); once the broker shows the shares free, place the SAME stop.
Every other refusal and every first attempt that succeeds are today's path, untouched; the window
running out is today's RESTORE_FAILED and today's page.

Time is FAKE here: `asyncio.sleep` advances a counter, so 15 s of polling costs nothing.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from agents.market_intelligence.broker import order_manager as om
from tests.test_646_full_exit_never_returns_naked import STOP_PRICE, _audit_rows, _wire

HELD = ('{"available":"0","code":40310000,"existing_qty":"4","held_for_orders":"4",'
        '"message":"insufficient qty available for order (requested: 3, available: 0)"}')
BREACH = '{"code":42210000,"message":"stop price must be less than current price"}'
# The SAME code (40310000) as a held-shares refusal, for a reason waiting cannot cure — the
# 10-06 A7 opening-auction probe's real text.
OPG_CUTOFF = '{"code":40310000,"message":"opg orders must be submitted after 7:00pm and before 9:28am"}'
EXTRA = {"id": "extra-1", "side": "sell", "type": "limit", "qty": 1, "filled_qty": 0,
         "status": "new", "order_class": "simple"}


def _b2(monkeypatch, *, release_at=7.0, place_errors=None, signal_type="magna53"):
    """The B2 shape on a fake clock: 4 sh at the broker, the row's 3-sh stop `stop-1` cancelled at
    t=0 (its shares stay HELD until `release_at`), one extra 1-sh resting sell the books do not
    know. The sale is refused. `place_errors` (callable t -> Exception | None) overrides the
    broker's answer to a stop placement; by default it refuses while the shares are held."""
    h = _wire(monkeypatch, close_raises=True, remaining=3, position_qty=4,
              open_orders=[EXTRA, {"id": "stop-1", "side": "sell", "type": "stop", "qty": 3,
                                   "filled_qty": 0, "status": "pending_cancel",
                                   "order_class": "simple"}])
    h["trade"]["signal_type"] = signal_type
    clock = {"t": 0.0}
    sleeps: list = []
    real_sleep = asyncio.sleep

    async def _sleep(s, *a, **k):
        sleeps.append(s)
        clock["t"] += s
        await real_sleep(0)

    monkeypatch.setattr(om.asyncio, "sleep", _sleep)
    monkeypatch.setattr(om, "_EXIT_RELEASE_SLEEP_S", 0.5)      # the real 5 s wait, on fake time
    monkeypatch.setattr(om, "_RESTORE_RETRY_SLEEP_S", 0.5)

    def _released():
        return clock["t"] >= release_at

    h["pos"].side_effect = lambda *a, **k: {
        "symbol": "OKTA", "qty": 4.0, "qty_available": 3.0 if _released() else 0.0}
    placed: list = []

    def _place(ticker, qty, stop_price, account_mode=None, client_order_id=None):
        placed.append({"t": clock["t"], "qty": qty, "price": stop_price,
                       "coid": client_order_id, "mode": account_mode})
        err = place_errors(clock["t"]) if place_errors else (None if _released() else Exception(HELD))
        if err:
            raise err
        return {"id": "stop-2", "status": "new"}

    h["place"].side_effect = _place
    h.update(clock=clock, sleeps=sleeps, placed=placed)
    return h


def _rows(rows, event):
    return [json.loads(d) for e, _s, d in rows if e == event]


# ── (a) the B2 shape: refused while held, the cancel settles at +7 s → restored ────────────────

@pytest.mark.asyncio
async def test_b2_the_restore_waits_for_the_release_and_restores_the_same_stop(monkeypatch):
    rows = _audit_rows(monkeypatch)
    h = _b2(monkeypatch, release_at=7.0)

    assert await om.execute_full_exit(382, "sma_trail_stop") is False   # the SALE still failed

    # attempt 1 at +5 s (right after the 5 s release wait gave up) refused; attempt 2 at +7 s,
    # the first poll that shows the shares free — same price, same count.
    assert [(p["t"], p["qty"], p["price"]) for p in h["placed"]] == [
        (5.0, 3, STOP_PRICE), (7.0, 3, STOP_PRICE)], h["placed"]
    om.set_stop_order_id.assert_awaited_once()
    assert om.set_stop_order_id.await_args.args[:2] == (382, "stop-2")
    page = h["sent"][-1]
    assert "Stop RESTORED" in page and "NOT RESTORED" not in page and "UNPROTECTED" not in page, page
    ok = _rows(rows, om.STOP_RESTORE_RETRIED_EVENT)
    assert len(ok) == 1 and not _rows(rows, om.STOP_RESTORE_RETRY_ENDED_EVENT), rows
    assert (ok[0]["attempts"], ok[0]["polls"], ok[0]["slept_s"]) == (2, 4, 2.0), ok
    assert (ok[0]["qty"], ok[0]["stop_price"], ok[0]["order_id"]) == (3, STOP_PRICE, "stop-2")
    assert ok[0]["cancelled_stop_id"] == "stop-1" and "held_for_orders" in ok[0]["last_error"]


@pytest.mark.asyncio
async def test_b2_only_the_retry_carries_a_mode_bound_client_order_id(monkeypatch):
    """The FIRST attempt is today's call exactly (no client order id — unchanged so a restore that
    succeeds first time is byte-identical); the retry is a new submission and carries one."""
    _audit_rows(monkeypatch)
    h = _b2(monkeypatch, release_at=7.0)
    await om.execute_full_exit(382, "sma_trail_stop")
    first, retry = h["placed"]
    assert first["coid"] is None and first["mode"] == "live"
    assert retry["coid"].startswith("apollo_live_magna53_OKTA_") and retry["mode"] == "live"


# ── (b) the shares never come free inside the window → today's failure and today's page ───────

@pytest.mark.asyncio
async def test_a_refusal_that_outlasts_the_window_fails_with_todays_page(monkeypatch):
    rows = _audit_rows(monkeypatch)
    h = _b2(monkeypatch, release_at=10_000.0)

    assert await om.execute_full_exit(382, "sma_trail_stop") is False

    assert len(h["placed"]) == 1, "never re-placed while the broker still showed the shares held"
    assert h["sleeps"].count(0.5) == om._EXIT_RELEASE_ATTEMPTS + om._RESTORE_RETRY_POLLS
    om.set_stop_order_id.assert_not_awaited()
    assert "STOP NOT RESTORED" in h["sent"][-1] and "UNPROTECTED" in h["sent"][-1], h["sent"]
    end = _rows(rows, om.STOP_RESTORE_RETRY_ENDED_EVENT)
    assert len(end) == 1 and not _rows(rows, om.STOP_RESTORE_RETRIED_EVENT)
    assert (end[0]["outcome"], end[0]["attempts"], end[0]["polls"], end[0]["slept_s"]) == (
        om.RESTORE_FAILED, 1, om._RESTORE_RETRY_POLLS,
        om._RESTORE_RETRY_POLLS * om._RESTORE_RETRY_SLEEP_S), end


@pytest.mark.asyncio
async def test_the_window_is_about_fifteen_seconds():
    assert om._RESTORE_RETRY_SLEEP_S == 0.5
    assert om._RESTORE_RETRY_POLLS * om._RESTORE_RETRY_SLEEP_S == 15.0
    assert om._RESTORE_RETRY_WINDOW_S == 15.0


def _slow_reads(monkeypatch, h, read_s):
    """Every position read the RETRY makes (after the first restore attempt) costs `read_s` seconds
    on the fake clock, and the retry's wall clock is that fake clock (only `order_manager`'s `time`
    is swapped — the event loop keeps the real one)."""
    import time as _time
    import types
    fake_time = types.SimpleNamespace(
        **{k: getattr(_time, k) for k in dir(_time) if not k.startswith("_")})
    fake_time.monotonic = lambda: h["clock"]["t"]
    monkeypatch.setattr(om, "time", fake_time)
    answer = h["pos"].side_effect

    def _pos(*a, **k):
        if h["placed"]:
            h["clock"]["t"] += read_s
        return answer(*a, **k)

    h["pos"].side_effect = _pos


@pytest.mark.asyncio
async def test_slow_broker_reads_cannot_stretch_the_window_past_fifteen_seconds(monkeypatch):
    """Review 2026-10-06 (NICE 3): bounded by the poll COUNT alone, 30 polls whose reads each took
    5 s held the per-trade lock for ~165 s. The wall clock now ends it: no poll STARTS once 15 s
    have passed since the first refusal — 3 polls here (5.5 s each), today's page, one row."""
    rows = _audit_rows(monkeypatch)
    h = _b2(monkeypatch, release_at=10_000.0)
    _slow_reads(monkeypatch, h, read_s=5.0)

    assert await om.execute_full_exit(382, "sma_trail_stop") is False

    end = _rows(rows, om.STOP_RESTORE_RETRY_ENDED_EVENT)
    assert len(end) == 1 and end[0]["outcome"] == om.RESTORE_FAILED, end
    assert end[0]["polls"] == 3, end
    assert 15.0 <= end[0]["elapsed_s"] < 15.0 + 5.5, end    # the read in flight may finish
    assert len(h["placed"]) == 1 and "STOP NOT RESTORED" in h["sent"][-1]


@pytest.mark.asyncio
async def test_slow_reads_still_restore_when_the_shares_free_inside_the_window(monkeypatch):
    """The cap only ends a retry the broker never answers in time — shares freed 10 s into the
    retry on 2 s reads are still re-protected (the B2 shape, slower broker)."""
    rows = _audit_rows(monkeypatch)
    h = _b2(monkeypatch, release_at=15.0)          # first attempt at +5 s; freed at +15 s
    _slow_reads(monkeypatch, h, read_s=2.0)

    await om.execute_full_exit(382, "sma_trail_stop")

    ok = _rows(rows, om.STOP_RESTORE_RETRIED_EVENT)
    assert len(ok) == 1 and ok[0]["order_id"] == "stop-2", rows
    assert ok[0]["polls"] == 4 and ok[0]["elapsed_s"] == 10.0, ok
    assert [p["t"] for p in h["placed"]] == [5.0, 15.0] and "Stop RESTORED" in h["sent"][-1]


# ── (c) the first attempt succeeds → no polling, today's result exactly ───────────────────────

@pytest.mark.asyncio
async def test_a_first_attempt_that_succeeds_never_polls(monkeypatch):
    rows = _audit_rows(monkeypatch)
    h = _b2(monkeypatch, release_at=0.0)           # the cancel had settled before the restore

    assert await om.execute_full_exit(382, "sma_trail_stop") is False

    assert [(p["qty"], p["price"], p["coid"]) for p in h["placed"]] == [(3, STOP_PRICE, None)]
    assert h["place"].await_args.kwargs == {"account_mode": "live"}     # today's call, exactly
    assert h["sleeps"] == [], "the release wait and the retry must both be skipped"
    # broker reads: the release wait's one read, then the restore sizing's position + orders.
    assert h["pos"].await_count == 2 and h["orders"].await_count == 1
    assert not _rows(rows, om.STOP_RESTORE_RETRIED_EVENT)
    assert not _rows(rows, om.STOP_RESTORE_RETRY_ENDED_EVENT)
    assert "Stop RESTORED" in h["sent"][-1]


@pytest.mark.asyncio
async def test_direct_call_first_attempt_success_returns_restored(monkeypatch):
    _audit_rows(monkeypatch)
    h = _b2(monkeypatch, release_at=0.0)
    out = await om._restore_stop_after_failed_exit(
        382, "OKTA", 3.0, STOP_PRICE, "live", cancelled_stop_id="stop-1", reason="sma_trail_stop")
    assert out == om.RESTORE_PLACED and len(h["placed"]) == 1 and h["sleeps"] == []


# ── (d) any refusal that is NOT "shares held" → today's branch, at once ────────────────────────

@pytest.mark.asyncio
async def test_a_price_through_the_stop_on_the_first_attempt_sells_at_market_as_today(monkeypatch):
    rows = _audit_rows(monkeypatch)
    h = _b2(monkeypatch, place_errors=lambda t: Exception(BREACH))
    sold: list = []

    async def _close(ticker, qty=None, account_mode=None):
        sold.append(qty)
        if len(sold) == 1:
            raise Exception("insufficient qty available")      # the planned sale
        return {"id": "breach-sale-1", "status": "accepted"}

    h["close"].side_effect = _close
    await om.execute_full_exit(382, "sma_trail_stop")
    assert len(h["placed"]) == 1 and sold == [None, 3], (h["placed"], sold)
    assert h["sleeps"].count(0.5) == om._EXIT_RELEASE_ATTEMPTS, "the restore must not poll"
    assert "SOLD AT MARKET" in h["sent"][-1]
    assert not [e for e, *_ in rows if e.startswith("stop_restore_retr")]


@pytest.mark.asyncio
@pytest.mark.parametrize("err", [OPG_CUTOFF, "HTTP 503 Service Unavailable"])
async def test_any_other_refusal_fails_at_once_as_today(monkeypatch, err):
    rows = _audit_rows(monkeypatch)
    h = _b2(monkeypatch, place_errors=lambda t: Exception(err))
    await om.execute_full_exit(382, "sma_trail_stop")
    assert len(h["placed"]) == 1
    assert h["sleeps"].count(0.5) == om._EXIT_RELEASE_ATTEMPTS, "the restore must not poll"
    assert "UNPROTECTED" in h["sent"][-1]
    assert not [e for e, *_ in rows if e.startswith("stop_restore_retr")]


def test_the_held_classifier_needs_the_text_not_the_code():
    assert om._is_shares_held_refusal(Exception(HELD))
    assert om._is_shares_held_refusal(Exception("insufficient qty available"))
    assert not om._is_shares_held_refusal(Exception(OPG_CUTOFF))
    assert not om._is_shares_held_refusal(Exception(BREACH))
    assert not om._is_shares_held_refusal(Exception('{"code":40310000,"message":"insufficient '
                                                    'buying power"}'))


# ── what the retry does when the broker changes under it ──────────────────────────────────────

@pytest.mark.asyncio
async def test_a_retry_refused_because_the_price_fell_through_the_stop_sells_at_market(monkeypatch):
    rows = _audit_rows(monkeypatch)
    h = _b2(monkeypatch, release_at=7.0,
            place_errors=lambda t: Exception(HELD) if t < 7.0 else Exception(BREACH))
    sold: list = []

    async def _close(ticker, qty=None, account_mode=None):
        sold.append(qty)
        if len(sold) == 1:
            raise Exception("insufficient qty available")
        return {"id": "breach-sale-1", "status": "accepted"}

    h["close"].side_effect = _close
    await om.execute_full_exit(382, "sma_trail_stop")
    assert len(h["placed"]) == 2 and sold == [None, 3], (h["placed"], sold)
    assert "SOLD AT MARKET" in h["sent"][-1]
    end = _rows(rows, om.STOP_RESTORE_RETRY_ENDED_EVENT)
    assert len(end) == 1 and end[0]["outcome"] == om.RESTORE_SOLD, end


@pytest.mark.asyncio
async def test_a_flat_broker_seen_while_waiting_places_nothing(monkeypatch):
    """The cancelled stop filled while it was pending cancel: the position is gone. A poll whose
    read is empty asks the shared sizing, which reads the positions LIST → flat → ruling (i)."""
    rows = _audit_rows(monkeypatch)
    h = _b2(monkeypatch, release_at=10_000.0)
    reads = {"n": 0}

    def _pos(*a, **k):
        reads["n"] += 1
        if h["clock"]["t"] >= 6.0:
            return None
        return {"symbol": "OKTA", "qty": 4.0, "qty_available": 0.0}

    h["pos"].side_effect = _pos
    h["all_pos"].return_value = []
    out = await om._restore_stop_after_failed_exit(
        382, "OKTA", 3.0, STOP_PRICE, "live", cancelled_stop_id="stop-1", reason="sma_trail_stop")
    assert out == om.RESTORE_FLAT
    assert len(h["placed"]) == 1
    assert _rows(rows, "restore_skipped_broker_flat")
    end = _rows(rows, om.STOP_RESTORE_RETRY_ENDED_EVENT)
    assert len(end) == 1 and end[0]["outcome"] == om.RESTORE_FLAT


@pytest.mark.asyncio
async def test_the_opening_auction_sale_restore_retries_too(monkeypatch):
    """The 19:01 depth sale shares the restore: a refused opg sale whose restore is refused for
    held shares re-places the stop once the broker frees them, with the trade's strategy on the
    retry's client order id."""
    from tests.test_depth_exit_rule import DEPTH_STOP, _sale_wire
    h = _sale_wire(monkeypatch, opg_raises=Exception("opg rejected"))
    monkeypatch.setattr(om, "_RESTORE_RETRY_SLEEP_S", 0)
    calls: list = []

    def _place(ticker, qty, stop_price, account_mode=None, client_order_id=None):
        calls.append((qty, stop_price, client_order_id))
        if len(calls) == 1:
            raise Exception(HELD)
        return {"id": "stop-restored"}

    h["place_stop"].side_effect = _place
    assert await om.execute_depth_open_sale(501) is False
    assert [c[:2] for c in calls] == [(6, DEPTH_STOP), (6, DEPTH_STOP)], calls
    assert calls[0][2] is None and calls[1][2].startswith("apollo_live_magna53_KOD_")
    assert "Stop RESTORED" in h["sent"][-1]
    assert [c for c in h["audit"].await_args_list if c.args[0] == om.STOP_RESTORE_RETRIED_EVENT]
