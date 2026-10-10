"""#687 — unit checks of the PURE parts of the Monday paper test (scripts/probes/_687/expiry_path_test.py).

The script itself is NOT run here (it buys on the paper account at 08:30 ET on a market day, from the
server). What is pinned: the verdict classifier (PASS / FAIL / INCONCLUSIVE / VOID and what each
needs), the launch refusal, the stop price (far below the market), the extended-hours buy request
(LIMIT, DAY, extended_hours) and that importing the module touches no broker and no database.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from datetime import datetime, timedelta
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
EXPIRY = datetime(2026, 10, 12, 9, 30, 57, tzinfo=_ET)


def _good(**over) -> dict:
    obs = {"sale_status": "expired", "expiry_at": EXPIRY,
           "stop": {"id": "stop-2", "qty": 3.0, "price": 74.8,
                    "created_at": (EXPIRY + timedelta(seconds=0.4)).isoformat()},
           "expected_qty": 3, "expected_price": 74.8, "row_stop_id": "stop-2",
           "pointer_row": True, "retry_row": False, "bad_page_seen": None}
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


def test_a_sale_that_fills_is_void_not_a_pass():
    assert E.classify(_good(sale_status="filled"))[0] == E.VOID


def test_a_rejected_opg_order_or_no_expiry_is_inconclusive():
    assert E.classify(_good(sale_status="rejected"))[0] == E.INCONCLUSIVE
    assert E.classify(_good(sale_status="accepted", expiry_at=None, stop=None))[0] == E.INCONCLUSIVE


def test_a_pass_needs_the_pointer_row_a_bare_stop_is_not_the_restore():
    """The broker listing a stop of the right size is what a later 09:35 refresh would leave too —
    the pointer row (`cancel_or_reject_restored`) is the marker that the stream's branch ran."""
    assert E.classify(_good(pointer_row=False))[0] == E.FAIL


# ── the small pure helpers ───────────────────────────────────────────────────────────────────────

def test_the_row_stop_is_far_below_the_fill_and_the_sale_limit_cannot_fill():
    assert E.stop_price_for(88.0) == 74.8 and E.stop_price_for(88.0) < 88.0 * 0.9
    assert E.sale_limit_for(88.0) == 176.0


def test_launch_refusal_needs_a_market_day_in_the_window():
    mon = datetime(2026, 10, 12, 8, 25, tzinfo=_ET)
    assert E.launch_refusal(mon) is None
    assert "market day" in E.launch_refusal(datetime(2026, 10, 10, 8, 25, tzinfo=_ET))   # Saturday
    assert "launch window" in E.launch_refusal(datetime(2026, 10, 12, 10, 0, tzinfo=_ET))
    assert "launch window" in E.launch_refusal(datetime(2026, 10, 12, 7, 0, tzinfo=_ET))


def test_the_schedule_is_ordered_and_matches_the_card():
    assert (E.T_BUY.hour, E.T_BUY.minute) == (8, 30) and (E.T_SELL.hour, E.T_SELL.minute) == (9, 5)
    assert E.T_LAUNCH_FROM < E.T_BUY < E.T_BUY_FILL_DEADLINE < E.T_SELL < E.T_OPEN
    assert E.T_OPEN < E.T_FAIL_DEADLINE < E.T_NO_EXPIRY_DEADLINE < E.T_CLEANUP
    assert (E.T_FAIL_DEADLINE.minute, E.T_FAIL_DEADLINE.second) == (31, 30)
    assert (E.T_CLEANUP.hour, E.T_CLEANUP.minute) == (9, 46) and E.PASS_WITHIN_S == 15.0


def test_the_extended_hours_buy_is_a_day_limit_with_extended_hours_set():
    f = E.ext_hours_buy_fields("KO", 3, 88.123, "apollo_paper_integration_test_KO_1")
    assert f == {"symbol": "KO", "qty": 3, "side": "buy", "time_in_force": "day",
                 "limit_price": 88.12, "extended_hours": True,
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
    assert E.PR.ACCOUNT_MODE == "paper" and E.PR.TAG_SIGNAL_TYPE == "integration_test"
    with pytest.raises(E.PR.RehearsalRefused, match="SAME"):
        E.PR.check_account_ids({"paper_id": "A", "live_id": "A"})
    assert callable(E.PR.arm_live_tripwire) and E.TICKER == "KO" and E.QTY == 3
