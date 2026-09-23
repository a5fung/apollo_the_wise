"""#508 partial-exit bracket-leg bug — EMPIRICAL Alpaca probe (PAPER ONLY).

Establishes what Alpaca actually permits on the stop leg of a filled OTO
bracket. Run on the execution server:

    docker exec apollo-execution python scripts/probes/_508_oto_leg_probe.py

PAPER-PINNED: constructs its own TradingClient(paper=True) from
ALPACA_PAPER_API_KEY/SECRET only. Never reads live keys, never touches the DB,
never imports app modules. Full raw responses + timings are captured to
/tmp/_508_oto_leg_probe_output.json (COST RULE: one run, everything captured).

TEST SEQUENCE (on a filled OTO position, stop leg live for full qty):
  T1  replace leg qty+stop_price          -> reproduce today's 42210000
  T1b verify original leg STILL LIVE after the failed replace
  T2  replace leg stop_price ONLY         -> allowed on advanced legs?
  T2b inspect replacement: still order_class=oto? still a leg?
  T3  replace the replacement with qty    -> does replacing DETACH the leg?
  T4  place standalone 2-sh stop while leg holds all shares -> expect reject
  T5  market sell 2 sh while leg holds all shares           -> expect reject
  T6  cancel stop -> poll status+qty_available (ms timing) -> place reduced
      stop -> verify live -> market sell 2. Measures the REAL naked window
      and whether waiting-for-release closes the IBM 5/27 race.
Cleanup: cancel open orders, close position.
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback
from datetime import datetime, timezone

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    GetOrdersRequest,
    MarketOrderRequest,
    ReplaceOrderRequest,
    StopLossRequest,
    StopOrderRequest,
)
from alpaca.trading.enums import OrderClass, OrderSide, TimeInForce, QueryOrderStatus

OUT_PATH = "/tmp/_508_oto_leg_probe_output.json"
EVENTS: list[dict] = []
T0 = time.perf_counter()


def log(event: str, **kw):
    rec = {
        "t_ms": round((time.perf_counter() - T0) * 1000, 1),
        "utc": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **kw,
    }
    EVENTS.append(rec)
    print(json.dumps(rec, default=str), flush=True)


def dump(obj):
    """Best-effort full serialization of an alpaca-py model / exception."""
    if obj is None:
        return None
    for attr in ("model_dump", "dict"):
        fn = getattr(obj, attr, None)
        if fn:
            try:
                return json.loads(json.dumps(fn(), default=str))
            except Exception:
                pass
    return str(obj)


def err_info(e: Exception) -> dict:
    return {"type": type(e).__name__, "str": str(e), "args": [str(a) for a in e.args]}


def main() -> int:
    key = os.environ.get("ALPACA_PAPER_API_KEY")
    sec = os.environ.get("ALPACA_PAPER_SECRET_KEY")
    if not key or not sec:
        print("FATAL: ALPACA_PAPER_API_KEY/SECRET_KEY not set", file=sys.stderr)
        return 2
    client = TradingClient(key, sec, paper=True)  # paper endpoint, hard-pinned

    acct = client.get_account()
    log("account", account_number=getattr(acct, "account_number", None),
        status=str(getattr(acct, "status", None)))

    # Pick a cheap liquid ticker with NO existing position/open orders.
    candidates = ["F", "SIRI", "AAL", "PLUG", "T"]
    positions = {p.symbol for p in client.get_all_positions()}
    open_orders = client.get_orders(GetOrdersRequest(status=QueryOrderStatus.OPEN))
    order_syms = {o.symbol for o in open_orders}
    ticker = next((c for c in candidates if c not in positions and c not in order_syms), None)
    if not ticker:
        log("fatal_no_clean_ticker", positions=sorted(positions), order_syms=sorted(order_syms))
        return 3
    log("ticker_chosen", ticker=ticker)

    # Latest price via the data API (paper keys, IEX feed).
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockLatestTradeRequest

    data = StockHistoricalDataClient(key, sec)
    lt = data.get_stock_latest_trade(StockLatestTradeRequest(symbol_or_symbols=ticker))
    last = float(lt[ticker].price)
    stop_px = round(last * 0.70, 2)
    log("latest_trade", ticker=ticker, last=last, stop_px=stop_px)

    QTY = 6
    PARTIAL = 2  # 1/3 — mirrors #508's remaining//3

    def get_order(oid):
        return client.get_order_by_id(oid)

    def pos_avail():
        try:
            p = client.get_open_position(ticker)
            return float(p.qty), float(p.qty_available)
        except Exception:
            return None, None

    final = {"ticker": ticker}
    try:
        # ── Establish the OTO bracket ────────────────────────────────────
        parent = client.submit_order(MarketOrderRequest(
            symbol=ticker, qty=QTY, side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
            order_class=OrderClass.OTO,
            stop_loss=StopLossRequest(stop_price=stop_px),
        ))
        log("oto_submitted", parent=dump(parent))
        leg_id = None
        for leg in (parent.legs or []):
            if getattr(leg, "stop_price", None):
                leg_id = str(leg.id)
        # Wait for parent fill.
        for _ in range(120):
            p = get_order(parent.id)
            if str(p.status).lower().endswith("filled"):
                log("parent_filled", parent=dump(p))
                if not leg_id:
                    for leg in (p.legs or []):
                        if getattr(leg, "stop_price", None):
                            leg_id = str(leg.id)
                break
            time.sleep(0.5)
        else:
            log("fatal_parent_not_filled", parent=dump(get_order(parent.id)))
            return 4
        if not leg_id:
            # refetch with nested legs
            log("fatal_no_leg_id")
            return 5
        # Wait for leg to activate (held -> new after parent fill).
        for _ in range(60):
            leg = get_order(leg_id)
            st = str(leg.status).lower()
            if "new" in st or "accepted" in st:
                break
            time.sleep(0.5)
        log("leg_active", leg=dump(get_order(leg_id)))
        q, avail = pos_avail()
        log("position_after_fill", qty=q, qty_available=avail)

        # ── T1: qty+price replace on the leg (today's PLTR call) ─────────
        try:
            r = client.replace_order_by_id(leg_id, ReplaceOrderRequest(
                qty=QTY - PARTIAL, stop_price=stop_px))
            log("T1_replace_qty_on_leg", result="SUCCEEDED", order=dump(r))
            leg_id = str(r.id)
        except Exception as e:
            log("T1_replace_qty_on_leg", result="REJECTED", error=err_info(e))

        # ── T1b: original leg still live after failed replace? ───────────
        leg = get_order(leg_id)
        log("T1b_leg_after_failed_replace", status=str(leg.status), leg=dump(leg))

        # ── T2: price-ONLY replace on the leg ────────────────────────────
        new_px = round(stop_px - 0.05, 2)
        t2_id = None
        try:
            t_start = time.perf_counter()
            r = client.replace_order_by_id(leg_id, ReplaceOrderRequest(stop_price=new_px))
            dt = round((time.perf_counter() - t_start) * 1000, 1)
            t2_id = str(r.id)
            log("T2_replace_price_only", result="SUCCEEDED", ms=dt, order=dump(r))
        except Exception as e:
            log("T2_replace_price_only", result="REJECTED", error=err_info(e))

        # ── T2b: is the replacement still an advanced-order leg? ─────────
        cur_stop = t2_id or leg_id
        for _ in range(20):
            o = get_order(cur_stop)
            if "new" in str(o.status).lower() or "accepted" in str(o.status).lower():
                break
            time.sleep(0.25)
        o = get_order(cur_stop)
        log("T2b_replacement_inspect", order_class=str(getattr(o, "order_class", None)),
            status=str(o.status), legs=dump(getattr(o, "legs", None)), order=dump(o))

        # ── T3: qty replace on the REPLACEMENT ───────────────────────────
        t3_ok = False
        try:
            r = client.replace_order_by_id(cur_stop, ReplaceOrderRequest(qty=QTY - PARTIAL))
            t3_ok = True
            cur_stop = str(r.id)
            log("T3_replace_qty_on_replacement", result="SUCCEEDED", order=dump(r))
        except Exception as e:
            log("T3_replace_qty_on_replacement", result="REJECTED", error=err_info(e))

        q, avail = pos_avail()
        log("position_after_T3", qty=q, qty_available=avail)

        # ── T4: standalone 2-sh stop WHILE existing stop holds shares ────
        if not t3_ok:
            try:
                r = client.submit_order(StopOrderRequest(
                    symbol=ticker, qty=PARTIAL, side=OrderSide.SELL,
                    time_in_force=TimeInForce.GTC, stop_price=round(stop_px - 0.10, 2)))
                log("T4_second_stop_while_leg_live", result="ACCEPTED", order=dump(r))
                # If accepted, cancel it immediately — over-covered state.
                client.cancel_order_by_id(r.id)
                log("T4_cleanup_cancelled", order_id=str(r.id))
            except Exception as e:
                log("T4_second_stop_while_leg_live", result="REJECTED", error=err_info(e))

            # ── T5: market sell PARTIAL while stop holds all shares ──────
            try:
                r = client.submit_order(MarketOrderRequest(
                    symbol=ticker, qty=PARTIAL, side=OrderSide.SELL,
                    time_in_force=TimeInForce.DAY))
                log("T5_market_sell_while_leg_live", result="ACCEPTED", order=dump(r))
            except Exception as e:
                log("T5_market_sell_while_leg_live", result="REJECTED", error=err_info(e))

        # ── T6: cancel -> timed release -> reduced stop -> sell ──────────
        # Measures the true naked window of a verified cancel+new.
        t6 = {"cancel_sent_ms": None, "cancel_confirmed_ms": None,
              "avail_released_ms": None, "new_stop_accepted_ms": None}
        base = time.perf_counter()
        client.cancel_order_by_id(cur_stop)
        t6["cancel_sent_ms"] = round((time.perf_counter() - base) * 1000, 1)
        # Poll order status until canceled.
        for _ in range(400):
            o = get_order(cur_stop)
            if "cancel" in str(o.status).lower():
                t6["cancel_confirmed_ms"] = round((time.perf_counter() - base) * 1000, 1)
                break
            time.sleep(0.05)
        # Poll qty_available until the reservation releases.
        for _ in range(400):
            q, avail = pos_avail()
            if avail is not None and q is not None and avail >= q:
                t6["avail_released_ms"] = round((time.perf_counter() - base) * 1000, 1)
                break
            time.sleep(0.05)
        remaining_for_stop = int(q) - PARTIAL if q else QTY - PARTIAL
        new_stop = None
        t6["stop_attempts"] = []
        for attempt in range(5):
            try:
                new_stop = client.submit_order(StopOrderRequest(
                    symbol=ticker, qty=remaining_for_stop, side=OrderSide.SELL,
                    time_in_force=TimeInForce.GTC, stop_price=stop_px))
                t6["new_stop_accepted_ms"] = round((time.perf_counter() - base) * 1000, 1)
                t6["stop_attempts"].append({"attempt": attempt + 1, "result": "accepted"})
                break
            except Exception as e:
                t6["stop_attempts"].append({"attempt": attempt + 1, "result": "rejected",
                                            "error": err_info(e)})
                time.sleep(0.25)
        log("T6_cancel_release_replace_timing", **t6,
            new_stop=dump(new_stop))
        # Verify the new stop is live, then sell the partial.
        if new_stop is not None:
            for _ in range(20):
                o = get_order(new_stop.id)
                if "new" in str(o.status).lower() or "accepted" in str(o.status).lower():
                    break
                time.sleep(0.25)
            log("T6_new_stop_verified", status=str(get_order(new_stop.id).status))
            try:
                r = client.submit_order(MarketOrderRequest(
                    symbol=ticker, qty=PARTIAL, side=OrderSide.SELL,
                    time_in_force=TimeInForce.DAY))
                log("T6_partial_sell", result="ACCEPTED", order=dump(r))
            except Exception as e:
                log("T6_partial_sell", result="REJECTED", error=err_info(e))
        q, avail = pos_avail()
        log("position_after_T6", qty=q, qty_available=avail)

    except Exception as e:
        log("probe_exception", error=err_info(e), tb=traceback.format_exc())
    finally:
        # ── Cleanup: cancel this ticker's open orders, close the position ─
        try:
            for o in client.get_orders(GetOrdersRequest(status=QueryOrderStatus.OPEN,
                                                        symbols=[ticker])):
                try:
                    client.cancel_order_by_id(o.id)
                    log("cleanup_cancel", order_id=str(o.id))
                except Exception as e:
                    log("cleanup_cancel_failed", order_id=str(o.id), error=err_info(e))
            time.sleep(1.0)
            try:
                client.close_position(ticker)
                log("cleanup_close_position", ticker=ticker)
            except Exception as e:
                log("cleanup_close_failed", error=err_info(e))
        finally:
            with open(OUT_PATH, "w") as f:
                json.dump({"final": final, "events": EVENTS}, f, indent=1, default=str)
            print(f"WROTE {OUT_PATH} ({len(EVENTS)} events)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
