#!/usr/bin/env python3
"""#548 — does a RESTING LIMIT collide with the full-size stop? PAPER ONLY.

THE QUESTION, flagged in the 2026-08-01 build-prep doc and never answered:

`execute_partial_exit` deliberately REDUCES THE STOP FIRST and only then sells, so the position
is never unprotected. A resting limit at the +2R level INVERTS that — the broker sells first and
we learn on the fill event, leaving a window in which the stop order covers MORE shares than are
actually held. Does Alpaca reject the stop, auto-reduce it, leave it stale, or fill it for shares
that no longer exist?

**The answer decides which designs are viable at all**, so it must come before any live code.

TWO PHASES, because only one of them works outside market hours:

  PHASE A — SUBMISSION-TIME VALIDATION (runs any time, including weekends).
    With a FLAT account, submit a sell-stop for shares we do not own. If Alpaca rejects it at
    submission, we learn that sell quantity is validated up front — which is strong evidence
    that a resting limit and a full-size stop CANNOT coexist against the same shares, and that
    is precisely the collision the current stop-first ordering exists to avoid.

  PHASE B — THE REAL SEQUENCE (needs REGULAR HOURS; exits 2 otherwise).
    Buy a small position, attach a full-size stop, rest a limit for 1/3 above the market, and
    observe: does the limit even get accepted? On fill, what happens to the oversized stop?

EXIT CODES: 0 = ran and learned something · 2 = could not run (market closed / setup) ·
            1 = the probe itself failed.

SAFETY: paper account only, hard-asserted (see `_ACCOUNT_MODE` below — this was
NOT actually a top-level assert until 2026-08-10; only `_probe_safety.teardown`
enforced it, and only in the `finally` block, after submission). Every
submitted order id goes through `_probe_safety.teardown` (cancel → verify →
flatten) in a finally block.

RUN LOCATION (2026-08-10, credential-wall fix): this probe does REAL order
submission via the raw `broker.alpaca_client`, which only has credentials
inside `apollo-execution` — `apollo-market` force-blanks all four ALPACA_*
vars by design (creds isolation, #256 W2). Run via:
    docker exec apollo-execution python scripts/probes/_548_resting_limit_smoke.py
NOT `apollo-market` — that container cannot produce real creds no matter what
bootstraps here; that's a deliberate security boundary, not a bug.
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

TICKER = "F"          # deliberately cheap + liquid: a stray fill costs a few dollars
SHARES = 1
_ACCOUNT_MODE = "paper"          # LITERAL. never parameterised, never read from env —
                                  # matches the pattern in _540_/_541_ sibling probes.


async def phase_a(alpaca) -> None:
    """Is sell quantity validated at SUBMISSION? Answerable with the market shut."""
    print("\n── PHASE A — submission-time validation (flat account) " + "─" * 20)
    positions = await alpaca.get_all_positions(account_mode=_ACCOUNT_MODE)
    held = {p.symbol: float(p.qty) for p in positions}
    print(f"   paper positions: {held or '(flat)'}")
    if held.get(TICKER):
        print(f"   SKIP — already hold {TICKER}; this phase needs to be flat in it.")
        return

    order_ids: list[str] = []
    try:
        print(f"   submitting a SELL STOP for {SHARES} {TICKER} while holding ZERO…")
        # The raw client, as every other order-submitting probe here does — the execution
        # facade is a READ surface plus named operations; it exposes no generic submit, and
        # inventing one for a probe would put a new writer inside the execution boundary.
        from agents.market_intelligence.broker import alpaca_client
        from alpaca.trading.requests import StopOrderRequest
        from alpaca.trading.enums import OrderSide, TimeInForce
        client = alpaca_client.get_trading_client(_ACCOUNT_MODE)
        try:
            o = client.submit_order(StopOrderRequest(
                symbol=TICKER, qty=SHARES, side=OrderSide.SELL,
                time_in_force=TimeInForce.DAY, stop_price=1.00,
            ))
            oid = getattr(o, "id", None)
            if oid:
                order_ids.append(str(oid))
            print(f"   ACCEPTED — id={oid} status={getattr(o, 'status', '?')}")
            print("   ⇒ Alpaca does NOT validate sell qty at submission. A resting limit and a")
            print("     full-size stop could then coexist, and the collision would surface only")
            print("     at FILL time — which is the dangerous shape, not the safe one.")
        except Exception as e:
            print(f"   REJECTED — {type(e).__name__}: {str(e)[:200]}")
            print("   ⇒ Alpaca DOES validate sell qty at submission. Strong evidence that a")
            print("     resting limit cannot coexist with a full-size stop against the same")
            print("     shares — i.e. the current stop-FIRST ordering is load-bearing, and any")
            print("     resting-limit design must reduce the stop before resting the limit.")
    finally:
        if order_ids:
            from scripts.probes._probe_safety import teardown
            # the BROKER client, not the read facade — the facade cannot cancel (see
            # _probe_safety's fallback note; this probe is the incident that added it)
            res = await teardown(alpaca_client, order_ids, account_mode=_ACCOUNT_MODE,
                                 symbols=[TICKER])
            print(f"   teardown: {res}")


async def main() -> int:
    # PAPER ONLY — hard-asserted BEFORE any credential or broker call. See module
    # docstring: this used to be enforced only inside `_probe_safety.teardown`'s
    # `finally` block, i.e. AFTER submission. Fixed 2026-08-10 alongside the
    # credential-wall fix, since this probe (unlike its _540_/_541_ siblings) now
    # runs in `apollo-execution`, which holds LIVE creds too — a typo'd literal
    # here would reach the live account where it could not in credential-less
    # `apollo-market`.
    assert _ACCOUNT_MODE == "paper", "PROBE IS PAPER-ONLY"

    # Fail loud + immediately if this process's env lacks Alpaca creds, instead of
    # a confusing downstream 401. See `_probe_safety.ensure_alpaca_credentials`
    # docstring for exactly what this does and does not fix — short version: it
    # does NOT manufacture credentials, it validates them are already present
    # (which they will be in `apollo-execution`, not in `apollo-market`).
    from scripts.probes._probe_safety import ensure_alpaca_credentials
    creds_status, creds_fallback = ensure_alpaca_credentials()
    print(f"alpaca creds: {creds_status} (legacy_fallback={creds_fallback})")

    from agents.market_intelligence import execution_client as alpaca
    # The repo's own market-hours helper, not a hand-rolled hour comparison — it already knows
    # about holidays and early closes, which a naive (9,30)<=t<16 check does not.
    from agents.market_intelligence.trading_calendar import is_market_hours_now_et
    from datetime import datetime
    from zoneinfo import ZoneInfo

    now_et = datetime.now(ZoneInfo("America/New_York"))
    open_now = is_market_hours_now_et()
    print(f"ET now: {now_et:%Y-%m-%d %H:%M} · regular hours: {open_now}")

    await phase_a(alpaca)

    if not open_now:
        print("\n── PHASE B — SKIPPED, market closed " + "─" * 32)
        print("   The fill-time question (what happens to an oversized stop when the resting")
        print("   limit fills) CANNOT be answered off-hours: a buy will not fill, so the")
        print("   position the test needs cannot be established. Run 09:30-16:00 ET.")
        print("   ⚠ Do NOT read Phase A alone as the whole answer.")
        return 2

    return await phase_b(alpaca)


async def phase_b(alpaca) -> int:
    """The three questions that actually remain. Needs REGULAR HOURS (a buy must fill).

    Re-scoped 2026-08-08 after reading `_508_oto_leg_probe.py`'s T1-T6, already recorded in
    order_manager.py, which answers most of what this probe was created to ask:
      T4  a 2nd stop while the bracket leg holds  -> REJECTED 40310000 insufficient qty
      T5  a market sell while the leg holds       -> REJECTED 40310000 "can't sell first"
      T2  price-only replace on a leg             -> OK
    So "rest a limit alongside the full-size stop" is already dead on T5, and the real open
    question is narrower.
    """
    from agents.market_intelligence.broker import alpaca_client
    from alpaca.trading.requests import (
        LimitOrderRequest, MarketOrderRequest, StopOrderRequest)
    from alpaca.trading.enums import OrderSide, TimeInForce
    from scripts.probes._probe_safety import teardown

    print("\n── PHASE B — the three questions that remain " + "─" * 22)
    client = alpaca_client.get_trading_client(_ACCOUNT_MODE)
    placed: list[str] = []
    try:
        print(f"   1. market BUY {SHARES * 3} {TICKER} …")
        buy = client.submit_order(MarketOrderRequest(
            symbol=TICKER, qty=SHARES * 3, side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY))
        placed.append(str(buy.id))
        for _ in range(20):
            await asyncio.sleep(1)
            pos = await alpaca_client.get_position(TICKER, account_mode=_ACCOUNT_MODE)
            if pos and float(pos.get("qty") or 0) >= SHARES * 3:
                break
        else:
            print("   buy did not fill in 20s — INCONCLUSIVE")
            return 2
        px = float(pos.get("current_price") or pos.get("avg_entry_price"))
        print(f"      filled, holding {pos.get('qty')} @ ~${px:.2f}")

        print("   2. attach a FULL-SIZE stop (reserves every share) …")
        stop = client.submit_order(StopOrderRequest(
            symbol=TICKER, qty=SHARES * 3, side=OrderSide.SELL,
            time_in_force=TimeInForce.DAY, stop_price=round(px * 0.90, 2)))
        placed.append(str(stop.id))
        print(f"      stop live: {stop.id}")

        # Q1 — THE DECIDING QUESTION. T5 rejected a MARKET sell while the leg holds. Is a
        # LIMIT sell treated identically? If yes, every candidate design must reduce the stop
        # FIRST and the choice collapses to sequencing (already-hardened code).
        print("   3. Q1: LIMIT sell for 1/3 while the stop holds every share …")
        try:
            lim = client.submit_order(LimitOrderRequest(
                symbol=TICKER, qty=SHARES, side=OrderSide.SELL,
                time_in_force=TimeInForce.DAY, limit_price=round(px * 1.10, 2)))
            placed.append(str(lim.id))
            print(f"      ACCEPTED — id={lim.id} status={lim.status}")
            print("      => a LIMIT is NOT treated like the market sell in T5. A resting limit")
            print("         CAN coexist with the full stop, and the collision moves to FILL time.")
        except Exception as e:
            print(f"      REJECTED — {str(e)[:160]}")
            print("      => same reservation rule as T5. EVERY design must reduce the stop")
            print("         first; candidate C collapses into B and the choice is sequencing.")

        # Q3 — defect 2's mechanism, at the moment we would actually use it.
        print("   4. Q3: price-only replace of the stop to breakeven …")
        try:
            from alpaca.trading.requests import ReplaceOrderRequest
            rep = client.replace_order_by_id(
                str(stop.id), ReplaceOrderRequest(stop_price=round(px * 0.99, 2)))
            placed.append(str(rep.id))
            print(f"      ACCEPTED — new id={rep.id} (price-only replace works on a live stop)")
        except Exception as e:
            print(f"      REJECTED — {str(e)[:160]}")
        return 0
    finally:
        res = await teardown(alpaca_client, placed, account_mode=_ACCOUNT_MODE, symbols=[TICKER])
        print(f"   teardown: {res}")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
