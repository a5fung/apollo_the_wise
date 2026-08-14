#!/usr/bin/env python3
"""#548 — can an OCO (limit above + stop below) cover the freed 1/3 while a SEPARATE
plain stop covers the other 2/3? PAPER ONLY.

THE HOLE THIS DECIDES (found live 2026-08-14, ETON): the +2R rule reduces the stop to
2/3 and rests a plain GTC limit for the freed 1/3 at the target. If that limit never
fills, the 1/3 has NO stop. The operator's proposed fix: make the 1/3's exit an OCO —
limit at the 2R target, stop at breakeven, whichever fills cancels the other — while
the 2/3 keeps its plain breakeven stop. The limit must STAY RESTING (his explicit
constraint: cancel/re-place on 2R re-touches would miss fills on volatile names).

PRIOR FINDINGS BUILT ON, NOT RE-DERIVED (_548_resting_limit_smoke.py, run 2026-08-10;
_508_oto_leg_probe.py T1-T6, run 2026-08-04):
  - a limit sell is REJECTED (40310000, available:0) while a FULL-size stop holds the
    shares — so the stop MUST be reduced first, verified-clear cancel-then-new;
  - after a verified-clear reduction, a plain limit for the freed share was accepted
    first try in 12.8ms — the freed-share reservation is available immediately;
  - price-only replace on a reduced standalone stop is accepted.
What is NOT known, and what this probe answers: whether Alpaca accepts an OCO
(order_class=oco) on the freed shares while a separate plain stop reserves the rest —
an OCO adds a broker-side sibling STOP leg on the same shares the limit references,
and nothing prior tested an advanced-order class coexisting with a standalone stop on
one position.

SEQUENCE (needs REGULAR HOURS — the buy must fill; exits 2 otherwise):
  1. market BUY 3 F, wait for fill
  2. plain GTC stop SELL 2 below the market            (the "2/3 breakeven stop")
  3. Q1: OCO SELL 1 — limit above + stop below, GTC    (the freed 1/3)
       shape A: LimitOrderRequest(limit_price=…, order_class=OCO, stop_loss=…)
       shape B (only if A is rejected on a param-validation shape): same + take_profit
  4. Q2: if accepted — read back F's open orders; both OCO legs + the plain stop
       should coexist; then submit ONE MORE 1-share limit sell, expecting 40310000
       available:0 — broker-side PROOF every share is reserved, i.e. no uncovered
       share remains (the exact property the ETON hole lacks)
  5. Q3: cancel the OCO parent — does the sibling leg go terminal with it? (the
       unwind semantics any later modify/close path needs)

EXIT CODES: 0 = ran and learned something · 2 = could not run (market closed / not
flat / setup) · 1 = the probe itself failed.

SAFETY: paper account only, hard-asserted first line of main (matches the _540_/_541_/
_548_ siblings). Every submitted order id goes through `_probe_safety.teardown`
(cancel → confirm-terminal → symbol sweep → flatten) in a finally block — the 2026-08-10
version that confirms cancels LANDED rather than trusting the request.

RUN LOCATION: apollo-execution (apollo-market force-blanks all ALPACA_* vars — creds
isolation, #256 W2):
    docker exec apollo-execution python scripts/probes/_548_oco_alongside_stop_probe.py
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

TICKER = "F"          # deliberately cheap + liquid: a stray fill costs a few dollars
SHARES = 1            # OCO qty; total position = SHARES * 3
_ACCOUNT_MODE = "paper"          # LITERAL. never parameterised, never read from env.


def _g(o, key, default=None):
    """SDK object OR _order_to_dict dict — the board readback returns dicts."""
    return o.get(key, default) if isinstance(o, dict) else getattr(o, key, default)


def _dump_order(o, indent="      "):
    print(f"{indent}id={_g(o, 'id', '?')} class={_g(o, 'order_class', '?')} "
          f"type={_g(o, 'type', '?')} qty={_g(o, 'qty', '?')} "
          f"status={_g(o, 'status', '?')} tif={_g(o, 'time_in_force', '?')} "
          f"limit={_g(o, 'limit_price')} stop={_g(o, 'stop_price')}")
    for leg in (_g(o, "legs") or []):
        print(f"{indent}  LEG: id={_g(leg, 'id', '?')} type={_g(leg, 'type', '?')} "
              f"qty={_g(leg, 'qty', '?')} status={_g(leg, 'status', '?')} "
              f"limit={_g(leg, 'limit_price')} stop={_g(leg, 'stop_price')}")


async def main() -> int:
    assert _ACCOUNT_MODE == "paper", "PROBE IS PAPER-ONLY"

    from scripts.probes._probe_safety import ensure_alpaca_credentials
    creds_status, creds_fallback = ensure_alpaca_credentials()
    print(f"alpaca creds: {creds_status} (legacy_fallback={creds_fallback})")

    from agents.market_intelligence.trading_calendar import is_market_hours_now_et
    from datetime import datetime
    from zoneinfo import ZoneInfo
    now_et = datetime.now(ZoneInfo("America/New_York"))
    open_now = is_market_hours_now_et()
    print(f"ET now: {now_et:%Y-%m-%d %H:%M} · regular hours: {open_now}")
    if not open_now:
        print("SKIP — the buy cannot fill off-hours; run 09:30-16:00 ET.")
        return 2

    from agents.market_intelligence.broker import alpaca_client
    from alpaca.trading.requests import (
        LimitOrderRequest, MarketOrderRequest, StopOrderRequest,
        StopLossRequest, TakeProfitRequest)
    from alpaca.trading.enums import OrderClass, OrderSide, TimeInForce
    from scripts.probes._probe_safety import teardown

    client = alpaca_client.get_trading_client(_ACCOUNT_MODE)

    # must be flat in TICKER with no resting orders — anything else makes the
    # reservation arithmetic (2 + 1 = 3 = held) ambiguous.
    pos = await alpaca_client.get_position(TICKER, account_mode=_ACCOUNT_MODE)
    open_orders = await alpaca_client.get_open_orders(TICKER, account_mode=_ACCOUNT_MODE)
    if pos or open_orders:
        print(f"SKIP — not flat/clean in {TICKER}: pos={pos} open_orders={len(open_orders or [])}")
        return 2

    placed: list[str] = []
    try:
        print(f"\n   1. market BUY {SHARES * 3} {TICKER} …")
        buy = client.submit_order(MarketOrderRequest(
            symbol=TICKER, qty=SHARES * 3, side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY))
        placed.append(str(buy.id))
        for _ in range(20):
            await asyncio.sleep(1)
            p = await alpaca_client.get_position(TICKER, account_mode=_ACCOUNT_MODE)
            if p and float(p.get("qty") or 0) >= SHARES * 3:
                break
        else:
            print("      buy did not fill in 20s — INCONCLUSIVE")
            return 2
        px = float(p.get("current_price") or p.get("avg_entry_price"))
        print(f"      filled, holding {p.get('qty')} @ ~${px:.2f}")

        print(f"\n   2. plain GTC stop SELL {SHARES * 2} @ {round(px * 0.90, 2)} "
              f"(the '2/3 breakeven stop') …")
        stop23 = client.submit_order(StopOrderRequest(
            symbol=TICKER, qty=SHARES * 2, side=OrderSide.SELL,
            time_in_force=TimeInForce.GTC, stop_price=round(px * 0.90, 2)))
        placed.append(str(stop23.id))
        print(f"      live: {stop23.id} status={stop23.status}")

        # ── Q1 — THE DECIDING QUESTION ─────────────────────────────────────────
        lim_px, oco_stop_px = round(px * 1.10, 2), round(px * 0.95, 2)
        print(f"\n   3. Q1: OCO SELL {SHARES} — limit {lim_px} above + stop {oco_stop_px} "
              f"below, GTC, alongside the separate plain stop …")
        oco = None
        try:
            print("      shape A: LimitOrderRequest(limit_price=…, order_class=OCO, stop_loss=…)")
            oco = client.submit_order(LimitOrderRequest(
                symbol=TICKER, qty=SHARES, side=OrderSide.SELL,
                time_in_force=TimeInForce.GTC, limit_price=lim_px,
                order_class=OrderClass.OCO,
                stop_loss=StopLossRequest(stop_price=oco_stop_px)))
        except Exception as e:
            print(f"      shape A REJECTED — {type(e).__name__}: {str(e)[:400]}")
            # only retry on a request-shape complaint (take_profit/limit_price param
            # validation) — a reservation/qty reject is THE answer, not a shape issue
            msg = str(e).lower()
            if "take_profit" in msg or "limit_price" in msg or "invalid" in msg:
                try:
                    print("      shape B: + take_profit=TakeProfitRequest(limit_price=…) …")
                    oco = client.submit_order(LimitOrderRequest(
                        symbol=TICKER, qty=SHARES, side=OrderSide.SELL,
                        time_in_force=TimeInForce.GTC, limit_price=lim_px,
                        order_class=OrderClass.OCO,
                        take_profit=TakeProfitRequest(limit_price=lim_px),
                        stop_loss=StopLossRequest(stop_price=oco_stop_px)))
                except Exception as e2:
                    print(f"      shape B REJECTED — {type(e2).__name__}: {str(e2)[:400]}")
        if oco is None:
            print("      ⇒ ANSWER: Alpaca REJECTS an OCO on freed shares alongside a")
            print("        separate plain stop. The operator's OCO design cannot ship as")
            print("        specified — record the code+message above and surface the fork.")
            return 0
        placed.append(str(oco.id))
        print("      ACCEPTED —")
        _dump_order(oco)
        for leg in (getattr(oco, "legs", None) or []):
            placed.append(str(leg.id))

        print(f"\n   4. Q2: read back {TICKER}'s open orders (coexistence check) …")
        await asyncio.sleep(2)     # let the OCO legs register
        board = await alpaca_client.get_open_orders(TICKER, account_mode=_ACCOUNT_MODE)
        for o in (board or []):
            _dump_order(o, indent="      ")
        # broker-side proof of FULL coverage: one more sell should find 0 available
        print(f"      now submit ONE MORE 1-share limit sell — expecting 40310000 "
              f"available:0 (proof all {SHARES * 3} shares are reserved) …")
        try:
            extra = client.submit_order(LimitOrderRequest(
                symbol=TICKER, qty=SHARES, side=OrderSide.SELL,
                time_in_force=TimeInForce.DAY, limit_price=lim_px))
            placed.append(str(extra.id))
            print(f"      ⚠ ACCEPTED ({extra.id}) — a share is NOT reserved by the OCO;")
            print("        coverage is not what it appears. Investigate before designing on this.")
        except Exception as e:
            print(f"      REJECTED — {str(e)[:300]}")
            print("      ⇒ every share is reserved: 2 by the plain stop, 1 by the OCO.")
            print("        The ETON hole (an uncovered 1/3) does not exist under this shape.")

        print("\n   5. Q3: cancel the OCO parent — does the sibling leg die with it? …")
        try:
            client.cancel_order_by_id(str(oco.id))
        except Exception as e:
            print(f"      cancel request failed: {str(e)[:200]}")
        await asyncio.sleep(2)
        board2 = await alpaca_client.get_open_orders(TICKER, account_mode=_ACCOUNT_MODE)
        oco_ids = {str(oco.id)} | {str(l.id) for l in (getattr(oco, "legs", None) or [])}
        still_live = [o for o in (board2 or []) if str(_g(o, "id", "")) in oco_ids]
        if still_live:
            print("      ⚠ sibling leg(s) STILL LIVE after parent cancel:")
            for o in still_live:
                _dump_order(o)
        else:
            print("      both OCO legs terminal after one cancel — the pair unwinds as a unit.")
        return 0
    finally:
        res = await teardown(alpaca_client, placed, account_mode=_ACCOUNT_MODE,
                             symbols=[TICKER])
        print(f"   teardown: {res}")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
