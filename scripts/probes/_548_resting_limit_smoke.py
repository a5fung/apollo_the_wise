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

⚠ FINDING (2026-08-10) — Alpaca's opposite-side/wash-trade guard OUTLIVES a
cancel REQUEST/ACK, and this probe used to walk straight into it. Phase A
submits then cancels a sell-stop on TICKER while flat (submission-time
validation test); Phase B then opens with a market BUY on the same TICKER.
On the first credentialed run, that BUY was REJECTED — 40310000 "potential
wash trade detected... opposite side market/stop order exists" — citing Phase
A's OWN, by-then-cancelled order id as `existing_order_id`. Note the precision
here: `_probe_safety.teardown` reported "cancelled 1/1" for that order, but
`alpaca_client.cancel_order` swallows a broker-side failure into a bool
return rather than raising, and `teardown`'s cancel loop never inspected that
return value — so "cancelled 1/1" was a REQUEST-SENT count, not a confirmed-
terminal count. What actually proved non-release was direct: the order was
STILL present in `get_open_orders(ticker)`'s OPEN set after teardown declared
success. This matters for #548's real design, not just this probe: T6 in
`_508_oto_leg_probe.py` measured ~78ms for the SAME-side qty_available
reservation to clear after a verified cancel, but never tested an
OPPOSITE-side fresh order — this run measured that guard too, at 0.268s / 2
polls to clear (see the "inter-phase guard" log line, pre-fix) — an order of
magnitude slower than T6's same-side number, and NOT proven to share its
mechanism. A cancel-then-new sequence (the shape `execute_partial_exit`
already uses, and the shape any resting-limit design collapses into per
Phase B's Q1/Q2 below) must not assume "cancel accepted" means "released" —
for the opposite-side guard specifically, Q2 below shows the SAME-side case
cleared near-instantly (9ms/1 poll) once verified-clear, so the two guards
are NOT the same lag class and a design must not extrapolate one number to
cover both.

FIXED 2026-08-10 (#548) at the SOURCE instead of papering over it here:
`_probe_safety.teardown` now polls each order's own status until it reaches
a real terminal state (bounded, not a single read — see its module
docstring's "SECOND INCIDENT"), and separately sweeps every touched symbol's
open-orders list (the same `wait_for_open_orders_clear` this probe used to
define locally — moved to `_probe_safety.py` so there is one implementation,
not two disagreeing about the same fact). Phase A's `finally:` teardown call
already passes `symbols=[TICKER]`, so by the time `phase_a()` returns, the
symbol-level sweep below has ALREADY confirmed TICKER carries no resting
orders (or reported loudly that it could not). The standalone "inter-phase
guard" wait that used to re-check this a second time, via a second
implementation, after `main()` resumed is therefore gone — `main()` instead
reads `phase_a()`'s teardown result and SKIPS Phase B if it was not clean,
rather than the old "proceeding anyway" which just walked into the same
40310000 reject a second time. `_wait_for_open_orders_clear` remains as
`_probe_safety.wait_for_open_orders_clear` and Phase B's Q2 below still calls
it directly — that usage is not teardown cleanup, it is the
experiment payload itself (measuring how long the SAME-side qty-reservation
guard takes to clear after a raw cancel-then-new, mid-flow, before the probe
continues) and must stay.
"""
from __future__ import annotations

import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

TICKER = "F"          # deliberately cheap + liquid: a stray fill costs a few dollars
SHARES = 1
_ACCOUNT_MODE = "paper"          # LITERAL. never parameterised, never read from env —
                                  # matches the pattern in _540_/_541_ sibling probes.


async def phase_a(alpaca) -> dict | None:
    """Is sell quantity validated at SUBMISSION? Answerable with the market shut.

    Returns `_probe_safety.teardown`'s result dict if any order was submitted (so `main()` can
    decide whether it is safe to proceed to Phase B), or `None` if nothing was submitted (flat
    account already, or the stop was REJECTED and never got an id — nothing to tear down).
    """
    print("\n── PHASE A — submission-time validation (flat account) " + "─" * 20)
    positions = await alpaca.get_all_positions(account_mode=_ACCOUNT_MODE)
    held = {p.symbol: float(p.qty) for p in positions}
    print(f"   paper positions: {held or '(flat)'}")
    if held.get(TICKER):
        print(f"   SKIP — already hold {TICKER}; this phase needs to be flat in it.")
        return None

    order_ids: list[str] = []
    teardown_result: dict | None = None
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
            # _probe_safety's fallback note; this probe is the incident that added it).
            # `symbols=[TICKER]` means teardown's symbol-level sweep (2026-08-10 fix) already
            # confirms TICKER carries no resting orders before this returns — see module
            # docstring's "FIXED 2026-08-10" note.
            teardown_result = await teardown(alpaca_client, order_ids, account_mode=_ACCOUNT_MODE,
                                             symbols=[TICKER])
            print(f"   teardown: {teardown_result}")
    return teardown_result


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

    teardown_result = await phase_a(alpaca)

    if not open_now:
        print("\n── PHASE B — SKIPPED, market closed " + "─" * 32)
        print("   The fill-time question (what happens to an oversized stop when the resting")
        print("   limit fills) CANNOT be answered off-hours: a buy will not fill, so the")
        print("   position the test needs cannot be established. Run 09:30-16:00 ET.")
        print("   ⚠ Do NOT read Phase A alone as the whole answer.")
        return 2

    # SELF-COLLISION GUARD (2026-08-10) — see module docstring's "FIXED 2026-08-10" note.
    # Phase A submits-then-cancels a sell-stop on TICKER; Phase B opens with a market BUY on the
    # same TICKER, and Alpaca's wash-trade guard can still see a just-cancelled order as an
    # "opposite side order exists" for a window after cancellation. `_probe_safety.teardown`
    # (called in phase_a's `finally:`, symbols=[TICKER]) now confirms via a bounded poll that
    # TICKER carries no resting orders before phase_a() returns — a SEPARATE post-teardown wait
    # here would just re-check the identical fact through a second implementation, which is the
    # exact "two mechanisms disagreeing" shape that produced the false "cancelled 1/1" this fix
    # exists for. If teardown could not confirm clean, do not walk into Phase B's collision —
    # skip instead of the old "proceeding anyway."
    #
    # Gate ONLY on `unconfirmed` / `unswept_symbols` — the specific "TICKER may still carry
    # something live" signals — NOT on the generic `errors` grab-bag. `errors` also catches
    # things unrelated to TICKER's cleanliness (e.g. a `flatten` failure on a different symbol,
    # or a `cancel request` exception that step 2 went on to confirm terminal anyway — see
    # `test_cancel_request_return_value_is_never_trusted` in tests/test_probe_safety.py, where
    # the account ends up clean despite an `errors` entry). Gating on `errors` would skip Phase
    # B — and burn a market-hours window — on a run that was actually fine.
    if teardown_result is not None and (teardown_result.get("unconfirmed")
                                         or teardown_result.get("unswept_symbols")):
        print(f"\n── PHASE B — SKIPPED, Phase A teardown did not confirm clean " + "─" * 6)
        print(f"   {teardown_result}")
        print("   Proceeding risks the same 40310000 wash-trade reject this probe hit 2026-08-10")
        print("   (see module docstring FINDING). Re-run once the account is confirmed clean.")
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
    from scripts.probes._probe_safety import teardown, wait_for_open_orders_clear

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
        lim = None
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

        # Q2 — after the stop is reduced via CANCEL-THEN-NEW (the #508 T6 shape, and the shape
        # `execute_partial_exit` already uses), is a limit sell for the newly-freed share
        # accepted IMMEDIATELY, or does it hit the same reservation lag Phase A's opposite-side
        # collision did (see module docstring FINDING)? This is the experiment measurement
        # itself — a raw SDK cancel-then-new, mid-flow, NOT routed through `teardown` (which
        # only runs once at the very end) — so it stays a direct `wait_for_open_orders_clear`
        # call here rather than folding into teardown. Clear the board first (cancels the full
        # stop + Q1's limit, if Q1 rested one) so the freed-share count is unambiguous: 3 held,
        # a 2-share stop leaves exactly 1 free.
        print("   4. Q2: reduce the stop via cancel-then-new, then limit-sell the freed share …")
        for oid in (str(stop.id), *([str(lim.id)] if lim is not None else [])):
            try:
                client.cancel_order_by_id(oid)
            except Exception:
                pass  # already terminal/rejected — expected for a REJECTED Q1 limit
        board = await wait_for_open_orders_clear(alpaca_client, TICKER, _ACCOUNT_MODE)
        print(f"      board cleared before reducing: {board}")
        if board["cleared"]:
            # drop the now-cancelled ids so the FINAL teardown report doesn't list expected
            # "already terminal" duplicate-cancel errors for orders we deliberately cleared here
            placed[:] = [oid for oid in placed
                         if oid not in (str(stop.id), str(lim.id) if lim is not None else None)]

        current_stop = client.submit_order(StopOrderRequest(
            symbol=TICKER, qty=SHARES * 2, side=OrderSide.SELL,
            time_in_force=TimeInForce.DAY, stop_price=round(px * 0.90, 2)))
        placed.append(str(current_stop.id))
        print(f"      reduced stop live: {current_stop.id} (qty={SHARES * 2}, frees {SHARES} share)")

        t0 = time.perf_counter()
        lim2 = None
        attempts: list[dict] = []
        for attempt in range(20):        # mirrors _508's T6 retry shape — no arbitrary sleep,
            try:                          # just keep asking until accepted or budget runs out
                lim2 = client.submit_order(LimitOrderRequest(
                    symbol=TICKER, qty=SHARES, side=OrderSide.SELL,
                    time_in_force=TimeInForce.DAY, limit_price=round(px * 1.10, 2)))
                placed.append(str(lim2.id))
                attempts.append({"attempt": attempt + 1, "result": "accepted"})
                break
            except Exception as e:
                attempts.append({"attempt": attempt + 1, "result": "rejected",
                                  "error": str(e)[:120]})
                await asyncio.sleep(0.25)
        dt_ms = round((time.perf_counter() - t0) * 1000, 1)
        if lim2 is not None and len(attempts) == 1:
            print(f"      ACCEPTED on the FIRST try ({dt_ms}ms) — id={lim2.id} status={lim2.status}")
            print("      => GIVEN a VERIFIED-CLEAR cancel (the board-clear poll above ran first),")
            print("         the freed share is available immediately — no lag observed at this")
            print("         granularity. This does NOT mean cancel-then-new needs no polling: it")
            print("         means polling-until-clear is sufficient — same conclusion Phase A's")
            print("         opposite-side collision (module docstring FINDING) reached.")
        elif lim2 is not None:
            print(f"      accepted after {len(attempts)} tries ({dt_ms}ms) — id={lim2.id}")
            print(f"      => the freed share needed {dt_ms}ms / {len(attempts)} tries to clear —")
            print("         same reservation-lag class as Phase A's opposite-side collision.")
        else:
            print(f"      REJECTED on all {len(attempts)} tries over {dt_ms}ms — "
                  f"last error: {attempts[-1]['error']}")
            print("      => the freed share never became available inside the retry budget.")

        # Q3 — defect 2's mechanism, at the moment we would actually use it. Runs on
        # `current_stop` (post-Q2) — the original `stop` was cancelled above and is terminal.
        # NOTE: `current_stop` is a STANDALONE stop (raw StopOrderRequest), never a bracket/OTO
        # LEG — this only answers the standalone case. `_508_oto_leg_probe.py` T2 already
        # answered the leg case (price-only replace OK); this is not new leg coverage.
        print("   5. Q3: price-only replace of the (now-reduced, standalone) stop to breakeven …")
        try:
            from alpaca.trading.requests import ReplaceOrderRequest
            rep = client.replace_order_by_id(
                str(current_stop.id), ReplaceOrderRequest(stop_price=round(px * 0.99, 2)))
            placed.append(str(rep.id))
            print(f"      ACCEPTED (request) — new id={rep.id} — replace was accepted by the API;")
            print("         this run did not re-fetch the new order to confirm it is LIVE (not")
            print("         still mid-replace) — teardown's later 'pending replacement' error on")
            print("         the superseded id is consistent with the chain still settling.")
        except Exception as e:
            print(f"      REJECTED — {str(e)[:160]}")
        return 0
    finally:
        res = await teardown(alpaca_client, placed, account_mode=_ACCOUNT_MODE, symbols=[TICKER])
        print(f"   teardown: {res}")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
