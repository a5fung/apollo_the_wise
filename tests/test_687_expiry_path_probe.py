"""#687 — unit checks of the paper test of the expired depth-sale restore
(scripts/probes/_687/expiry_path_test.py).

The script itself is NOT run against a broker here (it trades on the paper account at 08:30 ET on a
market day, from the server). What is pinned:
  * the verdict classifier (PASS / FAIL / INCONCLUSIVE / VOID and what each needs) and the small pure
    helpers;
  * THE STEP ORDER (2026-10-12 rework — Monday's run was void because the sale went in on top of the
    watchdog's stop, was refused, and the exception reached no verdict): the row's own stop first,
    then the planned sale in PRODUCTION ORDER (marker -> cancel the stop -> shares free -> opg order
    -> full_exit row) under the per-trade lock, a pre-open precondition check, then the watch — run
    end to end against the rehearsal's broker model (which refuses a sale on shares a stop holds),
    for every outcome including an unexpected exception, which must still end in a RESULT line and
    the rehearsal's cleanup;
  * that every production helper the probe reaches for exists with the signature it is called with.
"""
from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import inspect
import os
import sys
from datetime import datetime, time as dtime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

_PATH = os.path.join(os.path.dirname(__file__), "..", "scripts", "probes", "_687", "expiry_path_test.py")
_ET = ZoneInfo("America/New_York")


def _load():
    spec = importlib.util.spec_from_file_location("expiry_path_test_687", _PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["expiry_path_test_687"] = mod
    spec.loader.exec_module(mod)
    return mod


E = _load()
PR = E.PR
EXPIRY = datetime(2026, 10, 12, 9, 30, 57, tzinfo=_ET)


def _good(**over) -> dict:
    obs = {"sale_status": "expired", "expiry_at": EXPIRY,
           "stop": {"id": "stop-2", "qty": 3.0, "price": 74.8,
                    "created_at": (EXPIRY + timedelta(seconds=0.4)).isoformat()},
           "expected_qty": 3, "expected_price": 74.8, "row_stop_id": "stop-2",
           "pointer_row": True, "retry_row": False, "watchdog_row": False, "bad_page_seen": None}
    obs.update(over)
    return obs


# ── classify ─────────────────────────────────────────────────────────────────────────────────────

def test_a_first_attempt_stop_passes_and_says_the_retry_is_still_unit_tested_only():
    verdict, why = E.classify(_good())
    assert verdict == E.PASS, why
    assert "FIRST attempt" in why and "unit-tested only" in why and "CHECK TELEGRAM" in why


def test_a_retry_stop_passes_and_records_the_retry_proven_live():
    verdict, why = E.classify(_good(
        retry_row=True,
        stop={"id": "stop-2", "qty": 3.0, "price": 74.8,
              "created_at": (EXPIRY + timedelta(seconds=9)).isoformat()}))
    assert verdict == E.PASS and "PROVEN live" in why, why


def test_no_stop_at_the_broker_is_the_day_b_failure():
    verdict, why = E.classify(_good(stop=None, row_stop_id=None, pointer_row=False))
    assert verdict == E.FAIL and "NO stop" in why, why


@pytest.mark.parametrize("over, needle", [
    ({"stop": {"id": "stop-2", "qty": 2.0, "price": 74.8,
               "created_at": EXPIRY.isoformat()}}, "not 3"),
    ({"stop": {"id": "stop-2", "qty": 3.0, "price": 70.0,
               "created_at": EXPIRY.isoformat()}}, "price"),
    ({"row_stop_id": None}, "stop_order_id"),
    ({"stop": {"id": "stop-2", "qty": 3.0, "price": 74.8,
               "created_at": (EXPIRY + timedelta(seconds=16)).isoformat()}}, "after the expiry"),
    ({"stop": {"id": "stop-2", "qty": 3.0, "price": 74.8,
               "created_at": (EXPIRY - timedelta(seconds=2)).isoformat()}}, "BEFORE the expiry"),
    ({"pointer_row": False}, "cancel_or_reject_restored"),
    ({"bad_page_seen": True}, "page"),
])
def test_a_stop_that_is_wrong_late_unpointed_or_paged_over_fails(over, needle):
    verdict, why = E.classify(_good(**over))
    assert verdict == E.FAIL and needle in why, (verdict, why)


def _late(seconds, **over):
    return _good(stop={"id": "stop-2", "qty": 3.0, "price": 74.8,
                       "created_at": (EXPIRY + timedelta(seconds=seconds)).isoformat()}, **over)


def test_a_retry_stop_a_few_seconds_past_the_bar_fails_but_names_the_retry_window():
    """Review 10-12: the bar is 15 s from the EXPIRY (the task's DoD); the production retry's window is
    15 s from its first refusal, 1-2 s later - so a retry that worked can read 'late'. Still a FAIL
    (the bar is the DoD), but the reason sends it to him as bar-vs-retry-window, not as Day B."""
    verdict, why = E.classify(_late(16.5, retry_row=True))
    assert verdict == E.FAIL and "16.5s after the expiry" in why, why
    assert "retry" in why and "first refusal" in why.lower() and "NOT as the Day B bug" in why, why


def test_a_late_stop_without_a_retry_row_does_not_get_the_retry_excuse():
    verdict, why = E.classify(_late(16.5, retry_row=False))
    assert verdict == E.FAIL and "retry window" not in why and "Day B" not in why, why


def test_a_retry_stop_far_past_the_bar_does_not_get_the_retry_excuse():
    verdict, why = E.classify(_late(40, retry_row=True))
    assert verdict == E.FAIL and "retry window" not in why, why


def test_a_sale_that_fills_is_void_not_a_pass():
    assert E.classify(_good(sale_status="filled"))[0] == E.VOID


def test_a_rejected_opg_order_or_no_expiry_is_inconclusive():
    assert E.classify(_good(sale_status="rejected"))[0] == E.INCONCLUSIVE
    assert E.classify(_good(sale_status="accepted", expiry_at=None, stop=None))[0] == E.INCONCLUSIVE


def test_a_pass_needs_the_pointer_row_a_bare_stop_is_not_the_restore():
    """The broker listing a stop of the right size is what a later 09:35 refresh would leave too —
    the pointer row (`cancel_or_reject_restored`) is the marker that the stream's branch ran."""
    assert E.classify(_good(pointer_row=False))[0] == E.FAIL


def test_a_stop_the_watchdog_placed_after_the_expiry_is_never_read_as_the_restores_pass():
    """The watchdog beating the stream to it protects the shares but proves nothing about the
    restore: FAIL, and the reason names the watchdog."""
    verdict, why = E.classify(_good(pointer_row=False, watchdog_row=True))
    assert verdict == E.FAIL and "WATCHDOG" in why and "did not get there first" in why, why
    # and the same observation without the watchdog row does not name it
    assert "WATCHDOG" not in E.classify(_good(pointer_row=False))[1]


# ── the small pure helpers ───────────────────────────────────────────────────────────────────────

def test_the_row_stop_is_far_below_the_fill():
    assert E.stop_price_for(88.0) == 74.8 and E.stop_price_for(88.0) < 88.0 * 0.9
    assert E.stop_price_for(88.40) == 75.14        # Monday's number


def test_the_row_stop_is_a_gtc_stop_sell_of_the_whole_position_under_the_fill():
    assert E.row_stop_fields("KO", 3, 88.4) == {
        "ticker": "KO", "qty": 3, "side": "sell", "kind": "stop", "tif": "gtc", "stop": 75.14}


def test_launch_refusal_needs_a_market_day_in_the_window():
    tue = datetime(2026, 10, 13, 8, 25, tzinfo=_ET)
    assert E.launch_refusal(tue) is None
    assert "market day" in E.launch_refusal(datetime(2026, 10, 10, 8, 25, tzinfo=_ET))   # Saturday
    assert "launch window" in E.launch_refusal(datetime(2026, 10, 13, 10, 0, tzinfo=_ET))
    assert "launch window" in E.launch_refusal(datetime(2026, 10, 13, 7, 0, tzinfo=_ET))


def test_the_schedule_is_ordered_and_matches_the_card():
    assert (E.T_BUY.hour, E.T_BUY.minute) == (8, 30) and (E.T_SELL.hour, E.T_SELL.minute) == (9, 5)
    assert E.T_LAUNCH_FROM < E.T_BUY < E.T_BUY_FILL_DEADLINE < E.T_SELL < E.T_PREOPEN < E.T_OPEN
    assert E.T_OPEN < E.T_FAIL_DEADLINE < E.T_NO_EXPIRY_DEADLINE < E.T_CLEANUP
    assert (E.T_PREOPEN.hour, E.T_PREOPEN.minute) == (9, 29)
    assert (E.T_FAIL_DEADLINE.minute, E.T_FAIL_DEADLINE.second) == (31, 30)
    assert (E.T_CLEANUP.hour, E.T_CLEANUP.minute) == (9, 46) and E.PASS_WITHIN_S == 15.0
    # an opg order is refused after 09:28 — the sale goes in well before
    assert E.T_SELL < dtime(9, 28)


def test_the_extended_hours_buy_is_a_day_limit_with_extended_hours_set():
    f = E.ext_hours_buy_fields("KO", 3, 88.123, "apollo_paper_integration_test_KO_1")
    assert f == {"symbol": "KO", "qty": 3, "side": "buy", "time_in_force": "day",
                 "limit_price": round(88.123 * (1 + E.BUY_LIMIT_BUFFER), 2), "extended_hours": True,
                 "client_order_id": "apollo_paper_integration_test_KO_1"}
    E.build_ext_hours_buy("KO", 3, 88.123, "x")       # builds against whatever alpaca-py (or its stub) is there


def test_find_restored_stop_takes_only_a_live_sell_stop_of_the_right_size():
    orders = [{"id": "a", "side": "OrderSide.SELL", "type": "OrderType.LIMIT", "qty": 3},
              {"id": "b", "side": "sell", "type": "stop", "qty": 2},
              {"id": "c", "side": "buy", "type": "stop", "qty": 3},
              {"id": "d", "side": "OrderSide.SELL", "type": "OrderType.STOP", "qty": 3.0}]
    assert E.find_restored_stop(orders, 3)["id"] == "d"
    assert E.find_restored_stop(orders[:3], 3) is None


def test_terminal_at_prefers_the_expiry_stamp():
    t = E.terminal_at({"expired_at": "2026-10-09T13:30:57.284614+00:00",
                       "updated_at": "2026-10-09T13:30:57.286739+00:00"})
    assert t.astimezone(_ET).strftime("%H:%M:%S") == "09:30:57"
    assert E.terminal_at({}) is None


def test_the_probe_reuses_the_rehearsals_paper_guards():
    """Paper only comes from paper_rehearsal's guards (account-id check, live tripwire, the
    integration_test tag) - the probe imports them rather than copying."""
    assert PR.ACCOUNT_MODE == "paper" and PR.TAG_SIGNAL_TYPE == "integration_test"
    with pytest.raises(PR.RehearsalRefused, match="SAME"):
        PR.check_account_ids({"paper_id": "A", "live_id": "A"})
    assert callable(PR.arm_live_tripwire) and E.TICKER == "KO" and E.QTY == 3


# ── the step order (pure) ────────────────────────────────────────────────────────────────────────

def test_the_sale_sequence_is_the_production_order():
    assert E.SALE_SEQUENCE == ("planned_sale_stop_cancel", "cancel_order", "await_shares_released",
                               "place_market_on_open_sell", "record_full_exit_order")
    assert E.sale_sequence_problems(E.SALE_SEQUENCE) == []


@pytest.mark.parametrize("steps, needle", [
    # Monday: the sale went in on top of the stop — no marker, no cancel, no wait
    (["place_market_on_open_sell", "record_full_exit_order"], "missing"),
    # the cancel before its marker: the stream would page "unprotected"
    (["cancel_order", "planned_sale_stop_cancel", "await_shares_released",
      "place_market_on_open_sell", "record_full_exit_order"], "out of order"),
    # the sale before the shares are free
    (["planned_sale_stop_cancel", "cancel_order", "place_market_on_open_sell",
      "await_shares_released", "record_full_exit_order"], "out of order"),
    # a DAY market sale or any other helper
    (["planned_sale_stop_cancel", "cancel_order", "await_shares_released", "place_market_sell",
      "record_full_exit_order"], "unexpected"),
    (["planned_sale_stop_cancel", "cancel_order", "await_shares_released", "place_market_on_open_sell",
      "record_full_exit_order", "cancel_order"], "repeated"),
])
def test_a_sale_that_skips_or_reorders_the_production_helpers_is_named(steps, needle):
    problems = E.sale_sequence_problems(steps)
    assert problems and any(needle in p for p in problems), problems


def test_preopen_problems_names_what_blocks_the_run():
    sale = {"id": "sale-1", "side": "sell", "type": "market", "qty": 3}
    assert E.preopen_problems("accepted", [sale], "sale-1") == []
    assert E.preopen_problems("new", [], "sale-1") == []               # the listing may omit an opg order
    stray = {"id": "stop-9", "side": "OrderSide.SELL", "type": "stop", "qty": 3}
    assert any("other live sell" in p for p in E.preopen_problems("new", [sale, stray], "sale-1"))
    assert any("not queued" in p for p in E.preopen_problems("expired", [sale], "sale-1"))


def test_a_pointer_that_still_names_the_cancelled_stop_is_a_note_not_a_problem():
    """Review 10-12: the stale pointer alone must not abort the only slot - §3's restore leaves the
    cancelled stop's id out of the held-share count. The verdict (classify) still needs it moved."""
    assert E.preopen_notes(None) == []
    notes = E.preopen_notes("stop-1-long-id")
    assert len(notes) == 1 and "stop-1-l" in notes[0] and "NULL" in notes[0]
    # ...and it no longer appears among the blocking problems, whatever the pointer is
    assert E.preopen_problems("new", [], "sale-1") == []


def test_adoptable_stops_are_only_unknown_three_share_sell_stops():
    orders = [{"id": "a", "side": "OrderSide.SELL", "type": "OrderType.STOP", "qty": 3.0},
              {"id": "b", "side": "sell", "type": "stop", "qty": 2},           # wrong size
              {"id": "c", "side": "buy", "type": "stop", "qty": 3},            # a buy
              {"id": "d", "side": "sell", "type": "limit", "qty": 3},          # not a stop
              {"id": "e", "side": "sell", "type": "stop", "qty": 3}]           # known already
    assert E.adoptable_stops(orders, ["e"], 3) == ["a"]
    assert E.adoptable_stops(orders, None, 3) == ["a", "e"]
    assert E.adoptable_stops([], ["e"], 3) == []


def test_watchdog_stop_after_counts_only_a_fallback_stop_at_or_after_the_expiry():
    def row(event, at, tid=7):
        return {"event_type": event, "at": at, "detail": {"trade_id": tid}}
    before = EXPIRY - timedelta(minutes=25)
    assert not E.watchdog_stop_after([row("stop_ack_timeout_remediated", before)], 7, EXPIRY)
    assert E.watchdog_stop_after([row("stop_ack_timeout_remediated", EXPIRY + timedelta(seconds=3))], 7, EXPIRY)
    assert not E.watchdog_stop_after([row("stop_ack_broker_covered", EXPIRY + timedelta(seconds=3))], 7, EXPIRY)
    assert not E.watchdog_stop_after([row("stop_ack_timeout_remediated", EXPIRY, tid=8)], 7, EXPIRY)


# ── the seam to the production helpers (a fake cannot prove these) ───────────────────────────────

def test_every_production_helper_the_probe_calls_exists_with_the_shape_it_is_called_with():
    from agents.market_intelligence.broker import alpaca_client as ac
    from agents.market_intelligence.broker import order_manager as om
    calls = [
        (om._record_planned_sale_stop_cancel, (1, "KO", "sid", PR.REASON, PR.ACCOUNT_MODE),
         {"site": E.SITE}),
        (om._await_shares_released, ("KO", 3.0, PR.ACCOUNT_MODE), {}),
        (om._record_full_exit_order, (1, "KO", {"id": "x"}, 3, PR.REASON), {}),
        (ac.place_market_on_open_sell, ("KO", 3), {"account_mode": PR.ACCOUNT_MODE,
                                                   "client_order_id": "c"}),
        (ac.cancel_order, ("sid",), {"account_mode": PR.ACCOUNT_MODE}),
    ]
    for fn, args, kwargs in calls:
        assert inspect.iscoroutinefunction(fn), fn.__name__
        inspect.signature(fn).bind(*args, **kwargs)           # raises TypeError on a shape mismatch
    assert callable(om._trade_advisory_lock)
    for name in ("trade_lock", "cancel", "submit", "get_order", "open_orders", "position", "trade",
                 "insert_trade", "audit_rows", "write_audit", "_coid"):
        assert hasattr(PR.RealEnv, name), name
    sig = inspect.signature(PR.RealEnv.submit)
    sig.bind(None, "KO", 3, "sell", kind="stop", tif="gtc", stop=75.14)


# ── end to end against the rehearsal's broker model ──────────────────────────────────────────────

class ExpiryEnv(PR.FakeEnv):
    """The rehearsal's FakeEnv (a broker that holds shares for resting sells and REFUSES a sale on
    shares a stop holds, a book, the stream's planned-cancel handler, a virtual clock) plus what the
    probe reaches through `env.alpaca` / `env.om`, and the opening auction: an opg sale EXPIRES at
    09:30:57 and the stream's §3 restore follows (or not, per `restore`)."""

    def __init__(self, *, restore="ok", sale_fills=False, refuse_stop=False, stray_stop=False,
                 opg_error=None, record_error=None, stop_reserves=True, stale_pointer=False, **kw):
        super().__init__(start=datetime(2026, 10, 13, 8, 25, tzinfo=_ET), **kw)
        self.prices["KO"] = 88.4
        self.restore, self.sale_fills, self.refuse_stop = restore, sale_fills, refuse_stop
        self.stray_stop, self.opg_error, self.record_error = stray_stop, opg_error, record_error
        self.stop_reserves, self.stale_pointer = stop_reserves, stale_pointer
        self.journal: list[tuple] = []          # (step, trade lock held when it ran)
        self.alpaca = SimpleNamespace(
            get_latest_quote=self._quote, get_latest_trade=self._last, get_trading_client=self._client,
            _order_to_dict=lambda o: o, place_market_on_open_sell=self._place_opg)
        self.om = SimpleNamespace(
            _record_planned_sale_stop_cancel=self._om_marker, _await_shares_released=self._om_released,
            _record_full_exit_order=self._om_record)

    def _coid(self, ticker):
        return f"apollo_paper_integration_test_{ticker}_{self._n + 1}"

    def _j(self, step, tid=None):
        self.journal.append((step, bool(self.locked) if tid is None else tid in self.locked))

    # what the probe reaches through env.alpaca
    async def _quote(self, t):
        return {"ask": self.prices[t], "bid": self.prices[t] - 0.02}

    async def _last(self, t):
        return {"price": self.prices[t]}

    def _client(self, mode):
        if mode != PR.ACCOUNT_MODE:
            raise PR.LiveTouched(mode)
        return SimpleNamespace(submit_order=self._submit_request, get_order_by_id=self._raw)

    def _submit_request(self, req):               # the extended-hours buy (runs in a thread)
        assert req.extended_hours is True
        o = self._new(req.symbol, req.qty, "buy", "limit", "day", status="new",
                      limit=req.limit_price, coid=req.client_order_id)
        self._fill(o, px=self.prices[req.symbol])
        self._j("buy")
        return dict(o)

    def _raw(self, oid):
        o = self.orders[oid]
        return SimpleNamespace(status=o["status"], expired_at=o.get("expired_at"), canceled_at=None,
                               failed_at=None, updated_at=None)

    async def _place_opg(self, ticker, qty, account_mode=None, client_order_id=None):
        self._j("place_market_on_open_sell")
        if self.opg_error:
            raise RuntimeError(self.opg_error)
        sale = await self.submit(ticker, qty, "sell", kind="market", tif="opg")   # refused on held shares
        self.orders[sale["id"]]["client_order_id"] = client_order_id
        return sale

    # what the probe reaches through env.om
    async def _om_marker(self, tid, ticker, stop_id, reason, mode, site):
        self._j("planned_sale_stop_cancel", tid)
        self._audit("planned_sale_stop_cancel", {"trade_id": tid, "stop_order_id": stop_id, "site": site})

    async def _om_released(self, ticker, need, mode):
        self._j("await_shares_released")
        pos = await self.position(ticker)
        return pos is None or pos["qty_available"] >= need

    async def _om_record(self, tid, ticker, order, qty, reason):
        self._j("record_full_exit_order", tid)
        if self.record_error:
            raise ValueError(self.record_error)
        self._record_order(tid, order, "full_exit")

    async def cancel(self, oid):
        self._j("cancel_order")
        return await super().cancel(oid)

    # The probe must drive the helpers itself: execute_depth_open_sale's PAPER vehicle is a DAY market
    # sell (#687 c) that FILLS at the open - the opg is what expires - and the 16:45 sale closes the
    # position. Calling either (or any vehicle but the opg order) would void the test, so here they raise.
    async def depth_open_sale(self, tid):
        raise AssertionError("the probe must not call execute_depth_open_sale (paper vehicle: DAY market)")

    async def full_exit(self, tid, reason):
        raise AssertionError("the probe must not call execute_full_exit")

    # the stop at placement, the watchdog's fallback, a stray stop
    async def submit(self, t, qty, side, *, kind, tif, limit=None, stop=None):
        if kind == "stop" and self.refuse_stop:
            raise RuntimeError("stop orders are not accepted pre-market")
        o = await super().submit(t, qty, side, kind=kind, tif=tif, limit=limit, stop=stop)
        if kind == "stop" and not self.stop_reserves and self.clock.time() < dtime(8, 45):
            self.orders[o["id"]]["unrouted"] = True     # a pre-market stop the broker has not routed yet
        return o

    def _held(self, t, exclude=()):
        unrouted = tuple(i for i, o in self.orders.items() if o.get("unrouted"))
        return super()._held(t, tuple(exclude) + unrouted)

    async def insert_trade(self, **kw):
        tid = await super().insert_trade(**kw)
        day = self.clock.date()
        if kw["stop_id"] is None:                 # the production watchdog's 09:00 tick
            self._timers.append((datetime.combine(day, dtime(9, 0, 30), tzinfo=_ET),
                                 lambda: self._watchdog_stop(tid, "before")))
        if self.stray_stop:
            self._timers.append((datetime.combine(day, dtime(9, 20), tzinfo=_ET),
                                 lambda: self._stray(tid)))
        if self.stale_pointer:
            self._timers.append((datetime.combine(day, dtime(9, 20), tzinfo=_ET),
                                 lambda: self._stale(tid)))
        return tid

    def _stale(self, tid):
        """The row points at the stop the planned sale cancelled (a stream that missed the null)."""
        cancelled = next(a["detail"]["stop_order_id"] for a in self.audit
                         if a["event_type"] == "planned_sale_stop_cancel")
        self.trades[tid]["stop_order_id"] = cancelled

    def _stray(self, tid):
        """A stop on the row at 09:20 (what a watchdog fallback would leave): it holds the shares."""
        n = self._new("KO", 3, "sell", "stop", "gtc", status="new", stop=70.0)
        self.trades[tid]["stop_order_id"] = n["id"]

    def _watchdog_stop(self, tid, when):
        r = self.trades.get(tid)
        if r is None or r["stop_order_id"] is not None:
            return
        n = self._new(r["ticker"], r["remaining_shares"], "sell", "stop", "gtc", status="new",
                      stop=r["stop_price"])
        n["created_at"] = self.clock.isoformat()
        r["stop_order_id"] = n["id"]
        self._audit("stop_ack_timeout_remediated", {"trade_id": tid, "when": when})

    # the opening auction: an opg sale expires at 09:30:57, then the stream's §3 restore
    async def _open_auction(self):
        if self.sale_fills:
            return await super()._open_auction()
        for o in list(self.orders.values()):
            if o["side"] == "sell" and o["type"] == "market" and o["tif"] == "opg" \
                    and o["status"] in PR.QUEUED_OK:
                at = datetime.combine(self.clock.date(), dtime(9, 30, 57), tzinfo=_ET)
                self._timers.append((at, lambda o=o: self._expire(o)))

    def _expire(self, o):
        o["status"], o["expired_at"] = "expired", self.clock.isoformat()
        tid = next(x["trade_id"] for x in self.live_orders if x["alpaca_order_id"] == o["id"])
        r = self.trades[tid]
        if self.restore in ("ok", "retry", "no_pointer_row", "orphan", "late_retry"):
            n = self._new(r["ticker"], r["remaining_shares"], "sell", "stop", "gtc", status="new",
                          stop=r["stop_price"])      # no client order id: the stream's first attempt sends none
            n["created_at"] = (self.clock + timedelta(
                seconds={"retry": 9, "late_retry": 16.5}.get(self.restore, 0.4))).isoformat()
            if self.restore != "orphan":             # orphan: the stop is placed, the row never learns of it
                r["stop_order_id"] = n["id"]
            if self.restore not in ("no_pointer_row", "orphan"):
                self._audit("stop_order_id_changed", {"trade_id": tid, "new_id": n["id"],
                                                      "reason": "cancel_or_reject_restored"})
            if self.restore in ("retry", "late_retry"):
                self._audit("stop_restore_retried", {"trade_id": tid, "attempts": 3})
        elif self.restore == "watchdog":
            self._timers.append((self.clock + timedelta(seconds=3),
                                 lambda: self._watchdog_stop(tid, "after")))


@pytest.fixture(autouse=True)
def _plain_buy_request(monkeypatch):
    """alpaca-py is a MagicMock stub in the suite, so the buy request carries no real fields: hand
    the fake client the same fields (`ext_hours_buy_fields`) as a plain object. The real request
    builder is still built, against the stub, in test_the_extended_hours_buy_is_a_day_limit_...."""
    def build(ticker, qty, ask, client_order_id):
        f = E.ext_hours_buy_fields(ticker, qty, ask, client_order_id)
        return SimpleNamespace(symbol=f["symbol"], qty=f["qty"], limit_price=f["limit_price"],
                               extended_hours=f["extended_hours"],
                               client_order_id=f["client_order_id"])
    monkeypatch.setattr(E, "build_ext_hours_buy", build)


def _run(tmp_path, **kw):
    env = ExpiryEnv(**kw)
    log = PR.StepLog(str(tmp_path / "expiry.log"), env.now)
    reh = PR.Rehearsal(env, log, ("KO", "KO", "KO"), r1_ticker=None)
    out = asyncio.run(E.run(env, log, reh, "KO"))
    return env, log, out, (tmp_path / "expiry.log").read_text()


def _statuses(log):
    return {r["step"]: r["status"] for r in log.results}


def _sale_steps(env):
    """The helper calls the planned sale made, in order (the journal also holds the buy and the
    cleanup's own cancels, which are not part of the sale)."""
    steps = [s for s, _ in env.journal if s != "buy"]
    return steps[:steps.index("record_full_exit_order") + 1] if "record_full_exit_order" in steps else steps


def _early_cleanup_left_only_the_queued_flatten(env):
    """A cleanup before the open cannot sell: paper queues the market flatten for the open (Monday's
    did). Nothing else of ours may be live, the opg sale must be dead, and the rows must be gone."""
    live = [o for o in env.orders.values() if o["status"] in PR.LIVE_STATUSES]
    assert all(o["type"] == "market" and o["tif"] == "day" and o["side"] == "sell" for o in live), live
    assert not [o for o in env.orders.values() if o["tif"] == "opg" and o["status"] in PR.LIVE_STATUSES]
    assert not env.trades


def test_the_whole_sequence_passes_in_production_order_under_the_lock(tmp_path):
    env, log, (verdict, why, rc), text = _run(tmp_path)
    assert (verdict, rc) == (E.PASS, 0), why
    # the row's own stop was live with every share reserved, the planned sale ran in production order
    st = _statuses(log)
    assert [st[k] for k in ("T1", "T1b", "T2", "T2b", "T2c", "T3", "CLEANUP")] == ["PASS"] * 7, st
    steps = _sale_steps(env)
    assert steps == list(E.SALE_SEQUENCE), steps
    assert [s for s, _ in env.journal].count("place_market_on_open_sell") == 1
    # the only sale ever sent is the opening-auction one (a DAY market sale would FILL at the open)
    sells = [o for o in env.orders.values() if o["side"] == "sell" and o["type"] == "market"]
    assert [(o["tif"], o["qty"]) for o in sells if o["tif"] == "opg"] == [("opg", 3.0)]
    # ...and the four helpers the production sale holds the per-trade lock for did (the cancel, the
    # marker and the row all inside it)
    held = dict(env.journal)
    assert held["planned_sale_stop_cancel"] and held["record_full_exit_order"], env.journal
    assert [e for e in env.journal if e[0] == "cancel_order"][0][1] is True
    # mode-bound client order id on the buy and the sale
    coids = [o["client_order_id"] for o in env.orders.values() if o.get("client_order_id")]
    assert coids and all(c.startswith("apollo_paper_integration_test_KO_") for c in coids), coids
    # the cleanup left the account flat and the rows gone, and the log ends in its verdict
    assert env.positions.get("KO", 0) == 0 and not env.trades
    assert "KO is FLAT at the broker" in text
    assert text.rstrip().splitlines()[-1].endswith(f"RESULT: PASS — {why}")
    assert any(r["event_type"] == E.RESULT_EVENT for r in env.audit)


def test_the_restored_stop_is_a_new_stop_the_row_pointed_at_the_old_one_before(tmp_path):
    """The stop the verdict looks at is the RESTORE's, not the row's own T1b stop (cancelled at T2)."""
    env, log, (verdict, _, _), _ = _run(tmp_path)
    first = next(r for r in env.audit if r["event_type"] == "planned_sale_stop_cancel")
    restored = next(r for r in env.audit if r["event_type"] == "stop_order_id_changed")
    assert first["detail"]["stop_order_id"] != restored["detail"]["new_id"]
    assert first["detail"]["site"] == E.SITE


def test_a_retry_restore_passes_and_says_so(tmp_path):
    _, _, (verdict, why, rc), _ = _run(tmp_path, restore="retry")
    assert (verdict, rc) == (E.PASS, 0) and "PROVEN live" in why, why


def test_no_restore_at_all_is_a_fail_with_exit_code_1(tmp_path):
    env, log, (verdict, why, rc), text = _run(tmp_path, restore="none")
    assert (verdict, rc) == (E.FAIL, 1) and "NO stop" in why, why
    assert _statuses(log)["T3"] == "FAIL" and "RESULT: FAIL" in text
    assert env.positions.get("KO", 0) == 0 and not env.trades        # cleaned up regardless


def test_a_restore_without_its_pointer_row_is_a_fail(tmp_path):
    _, _, (verdict, why, rc), _ = _run(tmp_path, restore="no_pointer_row")
    assert (verdict, rc) == (E.FAIL, 1) and "cancel_or_reject_restored" in why, why


def test_a_watchdog_stop_after_the_expiry_fails_and_names_the_watchdog(tmp_path):
    _, _, (verdict, why, rc), _ = _run(tmp_path, restore="watchdog")
    assert (verdict, rc) == (E.FAIL, 1) and "WATCHDOG" in why, why


def test_a_sale_that_fills_is_void_and_still_cleaned_up(tmp_path):
    env, log, (verdict, why, rc), _ = _run(tmp_path, sale_fills=True)
    assert (verdict, rc) == (E.VOID, 0), why
    assert env.positions.get("KO", 0) == 0 and not env.trades


def test_a_refused_row_stop_accepts_the_watchdogs_fallback_and_still_runs_the_sequence(tmp_path):
    """The row's own stop is refused: T1b is INFO, the watchdog's 09:00 tick puts a stop on the row,
    the planned sale cancels THAT one — same sequence, same verdict. (The watchdog row sits BEFORE
    the expiry, so it is not read as the watchdog beating the restore.)"""
    env, log, (verdict, why, rc), _ = _run(tmp_path, refuse_stop=True)
    st = _statuses(log)
    assert st["T1b"] == "INFO" and (verdict, rc) == (E.PASS, 0), (st, why)
    assert _sale_steps(env) == list(E.SALE_SEQUENCE)
    assert any(r["event_type"] == "stop_ack_timeout_remediated" and r["detail"]["when"] == "before"
               for r in env.audit)


def test_a_stop_resting_at_the_pre_open_check_is_inconclusive_not_a_fail(tmp_path):
    env, log, (verdict, why, rc), _ = _run(tmp_path, stray_stop=True)
    assert verdict == E.INCONCLUSIVE and rc == 2 and "precondition" in why, why
    assert _statuses(log)["T2c"] == "FAIL"
    _early_cleanup_left_only_the_queued_flatten(env)


def test_a_stream_that_records_nothing_is_flagged_but_does_not_decide_the_verdict(tmp_path):
    _, log, (verdict, _, rc), _ = _run(tmp_path, stream_silent=False)
    assert _statuses(log)["T2b"] == "INFO" and (verdict, rc) == (E.PASS, 0)


def test_a_refused_opening_auction_order_is_inconclusive_with_a_result_line(tmp_path):
    env, log, (verdict, why, rc), text = _run(tmp_path, opg_error="opg orders are not accepted")
    assert verdict == E.INCONCLUSIVE and rc == 2 and "REFUSED" in why, why
    assert "RESULT: INCONCLUSIVE" in text
    _early_cleanup_left_only_the_queued_flatten(env)
    assert "KO still holds 3.0 sh" in text            # the queued flatten has not filled: said, not hidden


def test_monday_the_unexpected_exception_now_ends_in_a_result_line_and_the_cleanup(tmp_path):
    """The sale is on the books at the broker when a step raises something nobody planned for: the
    log must still say INCONCLUSIVE (with the error), the sale must be cancelled and the position
    flat — Monday ended with a bare traceback and no verdict."""
    env, log, (verdict, why, rc), text = _run(tmp_path, record_error="boom")
    assert verdict == E.INCONCLUSIVE and rc == 2 and "raised: ValueError: boom" in why, why
    assert "RESULT: INCONCLUSIVE" in text and _statuses(log)["T0"] == "INFO"
    _early_cleanup_left_only_the_queued_flatten(env)
    assert any(r["event_type"] == E.RESULT_EVENT and r["detail"]["verdict"] == E.INCONCLUSIVE
               for r in env.audit)


def test_a_live_touch_is_never_swallowed_into_a_verdict(tmp_path):
    env = ExpiryEnv()
    env.alpaca.get_trading_client = lambda mode: (_ for _ in ()).throw(PR.LiveTouched(mode))
    log = PR.StepLog(str(tmp_path / "expiry.log"), env.now)
    reh = PR.Rehearsal(env, log, ("KO", "KO", "KO"), r1_ticker=None)
    with pytest.raises(PR.LiveTouched):
        asyncio.run(E.run(env, log, reh, "KO"))


def test_the_launch_guards_still_refuse_before_anything_is_placed(tmp_path):
    env = ExpiryEnv()
    env.clock = datetime(2026, 10, 13, 10, 0, tzinfo=_ET)          # outside the launch window
    log = PR.StepLog(str(tmp_path / "expiry.log"), env.now)
    reh = PR.Rehearsal(env, log, ("KO", "KO", "KO"), r1_ticker=None)
    with pytest.raises(PR.RehearsalRefused, match="launch window"):
        asyncio.run(E.run(env, log, reh, "KO"))
    assert not env.orders
    env2 = ExpiryEnv(same_account=True)
    reh2 = PR.Rehearsal(env2, PR.StepLog(str(tmp_path / "e2.log"), env2.now), ("KO", "KO", "KO"),
                        r1_ticker=None)
    with pytest.raises(PR.RehearsalRefused, match="SAME"):
        asyncio.run(E.run(env2, reh2.log, reh2, "KO"))
    assert not env2.orders


# ── the review-10-12 fixes, end to end ───────────────────────────────────────────────────────────

def test_t1b_is_info_not_fail_when_the_stop_is_live_but_the_shares_show_unreserved(tmp_path):
    """A pre-market stop that the broker has not routed yet reserves nothing: T1b must not read FAIL
    beside a T3 PASS (the verdict is T3's alone)."""
    env, log, (verdict, why, rc), text = _run(tmp_path, stop_reserves=False)
    st = _statuses(log)
    assert st["T1b"] == "INFO" and st["T3"] == "PASS" and (verdict, rc) == (E.PASS, 0), (st, why)
    assert "cosmetic" in text and not log.failed(), log.failed()
    assert _sale_steps(env) == list(E.SALE_SEQUENCE)


def test_a_stale_row_pointer_at_the_pre_open_check_is_noted_and_the_watch_goes_on(tmp_path):
    """The row still names the stop the planned sale cancelled; nothing else rests on KO. That used to
    abort the only slot (INCONCLUSIVE); now T2c is INFO and the restore is judged as usual."""
    env, log, (verdict, why, rc), text = _run(tmp_path, stale_pointer=True)
    st = _statuses(log)
    assert st["T2c"] == "INFO" and "NOTE" in text, st
    assert (verdict, rc) == (E.PASS, 0), why


def test_a_stale_pointer_that_never_moves_is_still_a_fail(tmp_path):
    """Going on is not the same as passing: with no restore at all the verdict is the Day B FAIL."""
    _, log, (verdict, why, rc), _ = _run(tmp_path, stale_pointer=True, restore="none")
    assert _statuses(log)["T2c"] == "INFO" and (verdict, rc) == (E.FAIL, 1) and "NO stop" in why, why


def test_a_retry_that_lands_just_past_the_bar_fails_with_the_retry_window_named(tmp_path):
    _, _, (verdict, why, rc), _ = _run(tmp_path, restore="late_retry")
    assert (verdict, rc) == (E.FAIL, 1) and "16.5s after the expiry" in why, why
    assert "NOT as the Day B bug" in why, why


def test_an_orphan_restore_stop_is_adopted_so_cleanup_still_flattens_the_ticker(tmp_path):
    """The stream's first restore attempt sends its stop with no client order id. If its pointer never
    lands, cleanup used to class it as someone else's, refuse to flatten KO and still delete the row -
    leaving KO held with no row, and the next run refusing the ticker."""
    env, log, (verdict, why, rc), text = _run(tmp_path, restore="orphan")
    assert (verdict, rc) == (E.FAIL, 1) and "cancel_or_reject_restored" in why, why
    orphans = [o for o in env.orders.values()
               if o["type"] == "stop" and o["tif"] == "gtc" and o["client_order_id"] is None
               and o["status"] == "canceled" and o.get("created_at")]
    assert orphans, "the uncoded restore stop must be there, and cancelled by the cleanup"
    assert not [o for o in env.orders.values() if o["status"] in PR.LIVE_STATUSES], \
        "nothing of the test may be left live"
    assert env.positions.get("KO", 0) == 0 and not env.trades, "KO flattened and the row gone"
    assert "adopted" in text and "NOT flattened" not in text
    assert text.rstrip().splitlines()[-1].endswith(f"RESULT: FAIL — {why}")


def test_a_late_stop_after_the_watch_ended_is_adopted_just_before_cleanup(tmp_path):
    """No stop during the watch (FAIL: Day B), then a 3-sh KO sell stop appears before cleanup runs
    (a late watchdog fallback). Cleanup must still cancel it and flatten KO."""
    env = ExpiryEnv(restore="none")
    log = PR.StepLog(str(tmp_path / "expiry.log"), env.now)
    reh = PR.Rehearsal(env, log, ("KO", "KO", "KO"), r1_ticker=None)
    env._timers.append((datetime(2026, 10, 13, 9, 40, tzinfo=_ET), lambda: env._new(
        "KO", 3, "sell", "stop", "gtc", status="new", stop=70.0)))
    verdict, why, rc = asyncio.run(E.run(env, log, reh, "KO"))
    assert (verdict, rc) == (E.FAIL, 1), why
    assert not [o for o in env.orders.values() if o["status"] in PR.LIVE_STATUSES]
    assert env.positions.get("KO", 0) == 0 and not env.trades


def test_a_cleanup_that_raises_still_ends_in_a_result_line_and_keeps_the_verdict(tmp_path):
    """Review 10-12: `reh.cleanup()` was unguarded in the `finally` - a transient broker error there
    skipped the RESULT line (and `docker exec -d` threw the traceback away). The verdict reached is a
    real observation and is NOT replaced; the failure rides on the line."""
    env = ExpiryEnv()
    log = PR.StepLog(str(tmp_path / "expiry.log"), env.now)
    reh = PR.Rehearsal(env, log, ("KO", "KO", "KO"), r1_ticker=None)

    async def boom():
        raise RuntimeError("broker 503 while listing orders")
    reh.cleanup = boom
    verdict, why, rc = asyncio.run(E.run(env, log, reh, "KO"))
    text = (tmp_path / "expiry.log").read_text()
    assert (verdict, rc) == (E.PASS, 0) and "CLEANUP RAISED" in why and "broker 503" in why, why
    assert text.rstrip().splitlines()[-1].endswith(f"RESULT: PASS — {why}")
    assert _statuses(log)["CLEANUP"] == "FAIL" and "RAISED RuntimeError" in text
    assert "run `status`, then `cleanup`" in why


def test_a_live_touch_in_cleanup_is_never_swallowed(tmp_path):
    env = ExpiryEnv()
    log = PR.StepLog(str(tmp_path / "expiry.log"), env.now)
    reh = PR.Rehearsal(env, log, ("KO", "KO", "KO"), r1_ticker=None)

    async def touched():
        raise PR.LiveTouched("live")
    reh.cleanup = touched
    with pytest.raises(PR.LiveTouched):
        asyncio.run(E.run(env, log, reh, "KO"))


# ── `status` (the pre-arming look) ───────────────────────────────────────────────────────────────

def _status(tmp_path, **kw):
    env = ExpiryEnv(**kw)
    log = PR.StepLog(str(tmp_path / "status.log"), env.now)
    reh = PR.Rehearsal(env, log, ("KO", "KO", "KO"), r1_ticker=None)
    rc = asyncio.run(E.status(env, log, reh, "KO"))
    return rc, (tmp_path / "status.log").read_text(), env


def test_status_says_which_file_is_in_the_container_and_that_ko_is_clean(tmp_path):
    rc, text, env = _status(tmp_path)
    assert rc == 0 and "KO CLEAN" in text and "KO NOT CLEAN" not in text, text
    assert f"script md5 {E.script_md5()}" in text            # the same value the recipe pins
    assert "SALE_SEQUENCE ['planned_sale_stop_cancel'" in text
    assert env.orders == {}, "status places nothing"


@pytest.mark.parametrize("kw, needle", [
    ({"held": {"KO": 3}}, "already holds"),
    ({"open_orders": {"KO": 3}}, "open order(s)"),          # e.g. Monday's GTC watchdog stop left behind
    ({"foreign_rows": {"KO": 1}}, "open paper trade row"),
])
def test_status_refuses_exactly_what_the_run_refuses_on(tmp_path, kw, needle):
    rc, text, _ = _status(tmp_path, **kw)
    assert rc == 2 and "KO NOT CLEAN" in text and needle in text, text
    # ...and it is the very check the run uses: the run refuses on the same state, placing nothing
    env = ExpiryEnv(**kw)
    log = PR.StepLog(str(tmp_path / "run.log"), env.now)
    reh = PR.Rehearsal(env, log, ("KO", "KO", "KO"), r1_ticker=None)
    n = len(env.orders)
    with pytest.raises(PR.RehearsalRefused, match=needle.split("(")[0]):
        asyncio.run(E.run(env, log, reh, "KO"))
    assert len(env.orders) == n


def test_status_refuses_a_left_over_rehearsal_row(tmp_path):
    env = ExpiryEnv()
    asyncio.run(env.insert_trade(ticker="KO", shares=3, entry=88.4, stop=75.14, stop_id=None,
                                 alert_date=env.et_today()))
    log = PR.StepLog(str(tmp_path / "status.log"), env.now)
    reh = PR.Rehearsal(env, log, ("KO", "KO", "KO"), r1_ticker=None)
    assert asyncio.run(E.status(env, log, reh, "KO")) == 2
    assert "KO NOT CLEAN" in (tmp_path / "status.log").read_text()


# ── main(): nothing leaves a bare traceback behind ──────────────────────────────────────────────

def test_main_turns_a_crash_outside_the_guarded_run_into_a_result_line_and_a_traceback(
        monkeypatch, capsys):
    """Review 10-12: a crash in `run_real` before `run()` (credentials, the DB pool, a transient
    broker read) reached no RESULT line, and `docker exec -d` discards stdout anyway - so main prints
    both on stdout, which the launcher redirects into /app/logs."""
    async def boom(cmd, ticker, *, force_time, send_pages):
        raise ConnectionError("db pool refused")
    monkeypatch.setattr(E, "run_real", boom)
    assert E.main(["run"]) == 2
    out = capsys.readouterr()
    text = out.out + out.err
    assert "RESULT: INCONCLUSIVE" in text and "ConnectionError: db pool refused" in text
    assert "Traceback" in text and "run `status`" in text


def test_main_still_reports_a_refusal_and_a_live_touch_as_before(monkeypatch, capsys):
    async def refuse(*a, **k):
        raise PR.RehearsalRefused("KO is held")
    monkeypatch.setattr(E, "run_real", refuse)
    assert E.main(["run"]) == 2 and "REFUSED: KO is held" in capsys.readouterr().out

    async def touch(*a, **k):
        raise PR.LiveTouched("live")
    monkeypatch.setattr(E, "run_real", touch)
    assert E.main(["run"]) == 2 and "LIVE TOUCHED" in capsys.readouterr().out


# ── the arming recipe (finding 1: it must not be able to ship Monday's file) ─────────────────────

def test_script_md5_hashes_the_bytes_of_the_file_it_is_given_or_its_own(tmp_path, monkeypatch):
    f = tmp_path / "probe.py"
    f.write_bytes(b"print('a stand-in for the probe')\n")
    want = hashlib.md5(b"print('a stand-in for the probe')\n").hexdigest()
    assert E.script_md5(str(f)) == want
    monkeypatch.setattr(E, "__file__", str(f))               # the default is the script's own path
    assert E.script_md5() == want
    f.write_bytes(b"print('edited')\n")                      # any edit moves the pin
    assert E.script_md5() != want


def test_the_launcher_recipe_checks_the_file_before_it_launches_and_keeps_the_stdout():
    from datetime import date
    md5 = "0123456789abcdef0123456789abcdef"
    text = E.launcher_text(date(2026, 10, 13), md5)
    # a script under `set -e`; the local wrong-file guard runs BEFORE the copy; the container md5 and the
    # new symbol are ENFORCED (each `|| { ...; exit 1; }`, not printed for the person to eyeball); `status`
    # (which exits 2 on a dirty KO) comes before anything is armed
    assert "\nset -e\n" in text
    wrong_local = text.index('echo "WRONG FILE')
    wrong_box = text.index('echo "CONTAINER HAS THE WRONG FILE')
    no_symbol = text.index('echo "CONTAINER FILE HAS NO SALE_SEQUENCE')
    assert wrong_local < text.index("docker cp") < wrong_box < no_symbol
    assert f'= "{md5}" ] || {{ echo "CONTAINER HAS THE WRONG FILE' in text
    assert "e.SALE_SEQUENCE" in text and "grep -q planned_sale_stop_cancel" in text
    assert no_symbol < text.index("expiry_path_test.py status") < text.index("nohup")
    # inside the launcher: the md5 compare comes before the one `docker exec -d`, and refuses on mismatch
    launcher = text.split("<<'LAUNCHER_EOF'\n")[1].split("LAUNCHER_EOF")[0]
    assert launcher.count("docker exec -d") == 1
    assert launcher.index("MD5 MISMATCH - not launched") < launcher.index("docker exec -d")
    assert f'[ "$GOT" = "{md5}" ] ||' in launcher and "exit 1" in launcher
    # wall-clock wait for 08:25 ET (string compare on the ET date+time) and the Monday log shape
    assert "TZ=America/New_York" in launcher and "2026-10-13 0824" in launcher
    assert "expiry_test_launch_2026-10-13.log" in launcher and "echo LAUNCHED" in launcher
    # stdout survives a recreate: sh -c with the redirect into the bind-mounted /app/logs, in /app
    assert ("docker exec -d -w /app apollo-execution sh -c 'python scripts/probes/_687/expiry_path_test.py "
            "run >> /app/logs/expiry_test_2026-10-13.stdout 2>&1'") in launcher
    assert "@DAY@" not in text and "@MD5@" not in text and "@REMOTE@" not in text, "unfilled token"


def test_the_launcher_refuses_a_weekend_day():
    from datetime import date
    with pytest.raises(ValueError, match="market day"):
        E.launcher_text(date(2026, 10, 10), "x")


def test_the_launcher_command_prints_the_recipe_for_this_very_file_and_arms_nothing(capsys):
    assert E.main(["launcher", "--day", "2026-10-13"]) == 0
    out = capsys.readouterr().out
    assert E.script_md5() in out and "LAUNCHER_EOF" in out
    with pytest.raises(SystemExit):
        E.main(["launcher"])                                    # --day is required
