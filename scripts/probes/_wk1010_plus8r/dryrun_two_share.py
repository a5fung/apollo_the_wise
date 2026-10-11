"""Dry run of the +8R profit-take SIZING path against FABRICATED in-memory positions. NEVER an order.

Why it exists (2026-10-10, MAGNA53 "2-share +8R sells 1" ruling): the rule is event-gated in
production — it can only fire when a 2-share position first trades +8R, which has never happened.
After the deploy this proves, the same day and with no market open, that the code the SCHEDULER
runs (`order_manager.scan_profit_triggers`, in the apollo-execution container) sizes the rung by
the signed rule. It drives the REAL scan function over a fake in-memory pool; the only thing it
replaces is the money action (`execute_partial_exit` -> a recorder) and the I/O around it.

  docker exec -i apollo-execution python - < scripts/probes/_wk1010_plus8r/dryrun_two_share.py

PASS prints `DRYRUN PASS` and exits 0. On the PRIOR code a 2-share MAGNA53 row sells 0 and the
helper does not exist, so it prints `DRYRUN FAIL` and exits 1 — the broken system cannot print PASS.
No database connection is opened (get_pool is patched), no broker call can complete (every order
function is replaced by one that raises), nothing is written anywhere.
"""
from __future__ import annotations

import asyncio
import json
import sys
from contextlib import ExitStack
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from agents.market_intelligence.broker import order_manager as om

ENTRY, ORB_LOW = 100.0, 95.0            # R = 5 -> +8R = 140.0
HI = 141.0                              # the in-hold high is through the +8R price


class _Conn:
    def __init__(self, rows, overrides):
        self.rows, self.overrides = rows, overrides

    async def fetch(self, sql, *a, **k):
        if "FROM mi_strategies" in sql:
            return self.overrides
        if "FROM mi_live_trades" in sql:
            return self.rows
        return []

    async def fetchval(self, sql, *a, **k):
        return HI if "MAX(high)" in sql else True


class _Acquire:
    def __init__(self, conn):
        self._c = conn

    def __await__(self):
        async def _x():
            return self._c
        return _x().__await__()

    async def __aenter__(self):
        return self._c

    async def __aexit__(self, *exc):
        return False


class _Pool:
    def __init__(self, conn):
        self._c = conn

    def acquire(self, *a, **k):
        return _Acquire(self._c)


class _NoonET(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 10, 12, 12, 0, tzinfo=tz)


def _row(i, signal_type, held):
    return {
        "id": i, "ticker": f"T{i}", "entry_price": ENTRY, "hard_stop": 90.0, "stop_price": 90.0,
        "orb_low": ORB_LOW, "signal_type": signal_type, "remaining_shares": float(held),
        "partial_taken": False, "filled_at": datetime(2026, 10, 12, 13, 31, tzinfo=timezone.utc),
        "account_mode": "paper",
    }


async def _scan(rows, overrides):
    sold: list[tuple] = []

    async def _recorder(trade_id, shares, **kw):      # the money action, replaced
        sold.append((trade_id, shares))
        return True

    def _boom(*a, **k):
        raise RuntimeError("DRY RUN: a broker order function was reached")

    with ExitStack() as st:
        st.enter_context(patch("agents.market_intelligence.constants.PROFIT_TRIGGER_R", 2.0))
        st.enter_context(patch.object(om, "get_pool",
                                      AsyncMock(return_value=_Pool(_Conn(rows, overrides)))))
        st.enter_context(patch.object(om, "datetime", _NoonET))
        st.enter_context(patch.object(om, "execute_partial_exit", _recorder))
        st.enter_context(patch.object(om, "_profit_take_resting_limit_enabled",
                                      AsyncMock(return_value=True)))
        st.enter_context(patch.object(om, "_profit_trigger_already_announced",
                                      AsyncMock(return_value=True)))
        st.enter_context(patch.object(om, "send_telegram_message", AsyncMock(return_value=True)))
        st.enter_context(patch.object(om, "log_audit_event", AsyncMock()))
        for name in ("place_market_sell", "place_limit_sell", "place_oco_sell",
                     "replace_order", "cancel_order"):
            if hasattr(om.alpaca, name):
                st.enter_context(patch.object(om.alpaca, name, _boom))
        results = await om.scan_profit_triggers()
    return results, sold


async def main() -> int:
    overrides = [
        {"signal_type": "magna53", "profit_trigger_r": 8.0, "breakeven_arm_r": 3.0},
        {"signal_type": "magna53_smallcap", "profit_trigger_r": 8.0, "breakeven_arm_r": 3.0},
    ]
    signed = {0: 0, 1: 0, 2: 1, 3: 1, 4: 1, 5: 1, 6: 2}      # MAGNA53 + its paper lane
    plain = {0: 0, 1: 0, 2: 0, 3: 1, 4: 1, 5: 1, 6: 2}       # every other strategy: int(n // 3)
    want = {"magna53": signed, "magna53_smallcap": signed, "9m_day2": plain}
    rows, i = [], 0
    plan: dict[int, tuple[str, int]] = {}
    for held in range(1, 7):
        for st_ in ("magna53", "magna53_smallcap", "9m_day2"):
            i += 1
            rows.append(_row(i, st_, held))   # 9m_day2 has no override row -> the global +2R = 120
            plan[i] = (st_, held)
    results, sold = await _scan(rows, overrides)
    got = {tid: n for tid, n in sold}
    fails = []
    for tid, (st_, held) in plan.items():
        expected = want[st_][held]
        have = got.get(tid, 0)
        if have != expected:
            fails.append(f"{st_} holding {held}: sold {have}, signed rule says {expected}")
    skipped = sorted(r["ticker"] for r in results if r["action"] == "too_small_to_split")
    print(json.dumps({"sold_by_trade_id": got, "too_small_to_split": skipped,
                      "plan": {k: list(v) for k, v in plan.items()}}, sort_keys=True))
    helper = getattr(om, "plus8r_partial_shares", None)
    if helper is None:
        fails.append("order_manager has no plus8r_partial_shares - the pre-ruling code is running")
    else:
        table = [helper(n) for n in range(7)]
        print("helper table 0..6:", table)
        if table != [0, 0, 1, 1, 1, 1, 2]:
            fails.append("plus8r_partial_shares table is not 0/0/1/1/1/1/2")
    if fails:
        print("DRYRUN FAIL")
        for f in fails:
            print("  -", f)
        return 1
    print("DRYRUN PASS")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
