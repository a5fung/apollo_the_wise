"""Dry run of the 19:01 depth SALE VEHICLE over FABRICATED rows. NEVER a database read, NEVER a broker call.

Why it exists (#687 option (c), his ruling 2026-10-10 *"got it, c"*): the change is event-gated in
production — the vehicle can only be seen on the first real depth sale of a PAPER row (the small-cap
lane fills ~1 a month), and on LIVE only after the first close below the line. After the deploy this
proves, the same weekend and with no market open and no row written, that the code the 19:01 job runs
(the `apollo-execution` container; `run_depth_open_sales` -> `order_manager.execute_depth_open_sale`)
sends a DAY MARKET sell for a PAPER row and the opening-auction (opg) order for a LIVE row.

It drives the REAL `execute_depth_open_sale` — the real sizing, the real stop cancel, the real wait
for the shares, the real mode-bound client order id (`alpaca.make_client_order_id`), the real
full_exit recording, the real restore on a rejection, the real pages. What it replaces:
  * the database pool -> an in-memory fake (one fabricated trade row; every INSERT is recorded);
  * EVERY coroutine function on `alpaca` -> a TRIPWIRE that records the call and raises
    AssertionError — then ONLY the six the sale path legitimately calls are re-faked as recorders.
    So no order can be sent, and a call the sale was never meant to make FAILS the run;
  * `get_trading_client` -> raises (no client is ever built);
  * Telegram / audit writes -> recorders.

  docker exec -i apollo-execution python - < scripts/probes/_wk1011_depth_paper_day/dryrun_vehicle.py

PASS prints `DRYRUN PASS` and exits 0. On the PRIOR code a PAPER row's sale goes to the opening
auction (`place_market_on_open_sell`), so it prints `DRYRUN FAIL` and exits 1 — the broken system
cannot print PASS.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import os
import sys
from contextlib import asynccontextmanager
from datetime import date

try:   # run as a file from anywhere: put the repo root on the path (stdin runs have no __file__)
    sys.path.insert(0, os.path.abspath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")))
except NameError:
    pass

from agents.market_intelligence import collector
from agents.market_intelligence.broker import order_manager as om

TODAY = date(2026, 10, 13)          # a fabricated 'today' — the sale refuses a mark from another day
DEPTH_STOP = 67.58
SHARES = 6


def _row(account_mode: str, signal_type: str) -> dict:
    return {"id": 501, "ticker": "KOD", "alert_date": date(2026, 9, 28),
            "account_mode": account_mode, "signal_type": signal_type, "status": "filled",
            "remaining_shares": SHARES, "entry_price": 63.15, "hard_stop": 58.08,
            "stop_price": DEPTH_STOP, "stop_order_id": "stop-1", "partial_taken": False,
            "breakeven_active": True, "exits": [], "running_closes": [70.0, 71.0],
            "exit_rule": "depth", "depth_sell_pending_on": TODAY}


class Rig:
    """One fabricated run of `execute_depth_open_sale` with every outward call recorded."""

    def __init__(self, row: dict, sale_raises: Exception | None = None):
        self.row = row
        self.sale_raises = sale_raises
        self.cancelled = False
        self.calls: list[tuple] = []          # ordered: ("cancel", id) / ("opg"|"day", ...) / ("stop", ...)
        self.tripwire: list[str] = []         # any alpaca function the sale was never meant to call
        self.inserts: list[tuple] = []        # every INSERT into mi_live_orders
        self.audit: list[tuple] = []          # (event, summary, detail-dict)
        self.pages: list[str] = []
        self.cleared = False

    # ── fabricated database ──────────────────────────────────────────────────────────────
    def pool(self):
        rig = self

        class _C:
            async def fetchrow(self, q, *a):
                return rig.row if "mi_live_trades" in q else None

            async def fetch(self, q, *a, **k):
                return []                      # no pending exit orders

            async def execute(self, *a, **k):
                if "depth_sell_pending_on = NULL" in a[0]:
                    rig.cleared = True
                if "INSERT INTO mi_live_orders" in a[0]:
                    rig.inserts.append(a)
                return "UPDATE 1"

            async def fetchval(self, *a, **k):
                return None

        class _A:
            async def __aenter__(self):
                return _C()

            async def __aexit__(self, *e):
                return False

        class _P:
            def acquire(self, *a, **k):
                return _A()

        return _P()

    # ── fabricated broker ────────────────────────────────────────────────────────────────
    async def cancel_order(self, order_id, account_mode=None):
        self.cancelled = True
        self.calls.append(("cancel", order_id, account_mode))
        return True

    async def get_position(self, ticker, account_mode=None):
        return {"qty": SHARES, "qty_available": SHARES}

    async def get_open_orders(self, ticker, account_mode=None, raise_on_error=False, **k):
        if self.cancelled:
            return []                          # the depth stop is gone
        return [{"id": "stop-1", "side": "sell", "type": "stop", "qty": SHARES,
                 "filled_qty": 0, "status": "new", "order_class": "simple"}]

    async def place_market_on_open_sell(self, ticker, qty, account_mode=None, client_order_id=None):
        self.calls.append(("opg", ticker, qty, account_mode, client_order_id))
        if self.sale_raises:
            raise self.sale_raises
        return {"id": "opg-1", "status": "accepted"}

    async def place_market_sell(self, ticker, qty, account_mode=None, client_order_id=None):
        self.calls.append(("day", ticker, qty, account_mode, client_order_id))
        if self.sale_raises:
            raise self.sale_raises
        return {"id": "day-1", "status": "accepted"}

    async def place_stop_order(self, ticker, qty, stop_price, account_mode=None,
                               client_order_id=None, **k):
        self.calls.append(("stop", ticker, qty, stop_price, account_mode))
        return {"id": "stop-restored", "status": "accepted"}

    async def run(self) -> bool:
        rig = self
        saved: dict = {}

        def _swap(obj, name, value):
            saved[(id(obj), name)] = (obj, name, getattr(obj, name))
            setattr(obj, name, value)

        # TRIPWIRE: every coroutine function on `alpaca` records + raises, so nothing can reach a broker
        for name, fn in list(vars(om.alpaca).items()):
            if inspect.iscoroutinefunction(fn):
                def _trip(_n=name):
                    async def _boom(*a, **k):
                        rig.tripwire.append(_n)
                        raise AssertionError(f"UNEXPECTED broker call alpaca.{_n}")
                    return _boom
                _swap(om.alpaca, name, _trip())

        def _no_client(*a, **k):
            rig.tripwire.append("get_trading_client")
            raise AssertionError("UNEXPECTED broker client lookup")

        _swap(om.alpaca, "get_trading_client", _no_client)
        for name in ("cancel_order", "get_position", "get_open_orders", "place_market_on_open_sell",
                     "place_market_sell", "place_stop_order"):
            _swap(om.alpaca, name, getattr(self, name))

        async def _pool():
            return rig.pool()

        @asynccontextmanager
        async def _lock(trade_id):
            yield

        async def _audit(event, summary="", detail=""):
            rig.audit.append((event, summary, json.loads(detail) if detail else {}))

        async def _tg(msg, *a, **k):
            rig.pages.append(msg)
            return True

        async def _set_stop(*a, **k):
            return True

        _swap(om, "get_pool", _pool)
        _swap(om, "_trade_advisory_lock", _lock)
        _swap(om, "log_audit_event", _audit)
        _swap(om, "send_telegram_message", _tg)
        _swap(om, "set_stop_order_id", _set_stop)
        _swap(om, "_EXIT_RELEASE_SLEEP_S", 0)
        _swap(collector, "et_today", lambda: TODAY)
        try:
            return await om.execute_depth_open_sale(self.row["id"])
        finally:
            for obj, name, orig in saved.values():
                setattr(obj, name, orig)

    def sale_calls(self) -> list[tuple]:
        return [c for c in self.calls if c[0] in ("opg", "day")]

    def audit_vehicle(self, event: str):
        hit = [d for e, _s, d in self.audit if e == event]
        return hit[0].get("vehicle") if hit else None


# (label, account_mode, signal_type, sale raises?, expected first sale call kind, vehicle in audit,
#  expected wording in a page, wording that must NOT appear)
CASES = [
    ("paper smallcap", "paper", "magna53_smallcap", None, "day", "day_market", "at the open", "opening auction"),
    ("paper magna53 ", "paper", "magna53", None, "day", "day_market", "at the open", "opening auction"),
    ("live  magna53 ", "live", "magna53", None, "opg", "opg", "opening auction", "at the open"),
    ("paper rejected", "paper", "magna53_smallcap", RuntimeError("insufficient qty available"),
     "day", "day_market", "Sale at the open FAILED", "Opening-auction"),
    ("live  rejected", "live", "magna53", RuntimeError("opg rejected"),
     "opg", "opg", "Opening-auction sale FAILED", "Sale at the open"),
]


async def main() -> int:
    bad: list = []
    for label, mode, sig, raises, want_kind, want_vehicle, want_text, banned in CASES:
        rig = Rig(_row(mode, sig), sale_raises=raises)
        try:
            ok = await rig.run()
        except Exception as e:       # an unexpected raise out of the REAL function is a failure
            ok = f"RAISED {type(e).__name__}: {e}"
        sale = rig.sale_calls()
        kinds = [c[0] for c in sale]
        why = []
        if ok is not (raises is None):
            why.append(f"returned {ok!r}")
        if kinds != [want_kind]:
            why.append(f"sale calls {kinds} (want ['{want_kind}'])")
        if sale:
            _k, ticker, qty, call_mode, coid = sale[0]
            if call_mode != mode:
                why.append(f"sale account_mode {call_mode!r} (want {mode!r})")
            if qty != SHARES:
                why.append(f"sale qty {qty!r} (want {SHARES})")
            if not str(coid).startswith(f"apollo_{mode}_{sig}_KOD_"):
                why.append(f"client order id {coid!r} is not mode-bound apollo_{mode}_{sig}_KOD_...")
        if rig.tripwire:
            why.append(f"unexpected broker calls {rig.tripwire}")
        if not any(c[0] == "cancel" and c[2] == mode for c in rig.calls):
            why.append("the depth stop was not cancelled on the row's account")
        if not rig.cleared:
            why.append("the 'sell at the next open' mark was not cleared")
        if raises is None:
            if rig.audit_vehicle("depth_open_sale_placed") != want_vehicle:
                why.append(f"placed audit vehicle {rig.audit_vehicle('depth_open_sale_placed')!r} "
                           f"(want {want_vehicle!r})")
            if not (rig.inserts and rig.inserts[0][2] == ("opg-1" if want_kind == "opg" else "day-1")
                    and "'full_exit'" in rig.inserts[0][0]):
                why.append("the sale was not recorded as the trade's full_exit order")
        else:
            if rig.audit_vehicle("full_exit_rejected") != want_vehicle:
                why.append(f"rejected audit vehicle {rig.audit_vehicle('full_exit_rejected')!r} "
                           f"(want {want_vehicle!r})")
            stops = [c for c in rig.calls if c[0] == "stop"]
            if not (len(stops) == 1 and stops[0][2:5] == (SHARES, DEPTH_STOP, mode)):
                why.append(f"the stop was not restored for {SHARES} sh @ {DEPTH_STOP} on {mode}: {stops}")
        text = "\n".join(rig.pages) + "\n" + "\n".join(s for _e, s, _d in rig.audit)
        if want_text not in text:
            why.append(f"no page/audit text says {want_text!r}")
        if banned in "\n".join(rig.pages):
            why.append(f"a page says {banned!r}")
        print(f"  {'ok  ' if not why else 'BAD '}{label} -> sale {kinds or 'none'}"
              + ("" if not why else "  " + "; ".join(why)))
        if why:
            bad.append((label, why))

    if bad:
        print(f"DRYRUN FAIL — {len(bad)} case(s) wrong: {bad}")
        return 1
    print("DRYRUN PASS")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
