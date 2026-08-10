"""Shared teardown for probes that SUBMIT orders. PAPER ONLY.

WHY THIS EXISTS — a real incident, 2026-08-06. `_541_bisect_6098.py` replayed INSM's rejected
live order on the paper account to find out what reject code 6098 checks. Its teardown did what
every probe here did: cancel every order id it collected, in a `finally` block. That is not
enough, and the gap is obvious in hindsight:

    a CANCEL cannot undo a FILL.

One case deliberately placed a stop-buy ~5% ABOVE the market to test acceptance geometry. INSM
then ran +33% that session, the trigger was hit, the order filled, and the cancel silently did
nothing because the order was already terminal. Result: 7 unowned shares sitting on the paper
account, which the position-sync watchdog correctly flagged — and then kept flagging. It produced
**27 `coverage_drift_detected` events in one day** (polled every 15 min, 10:30-16:45 ET) plus two
Telegram sync alerts, and those 27 events became the top "explanatory delta" in the hypothesis
text of BOTH of that evening's L2 anomaly alerts. So a probe artifact did not merely add noise —
it actively misdirected two unrelated investigations.

The lesson generalises past this one bug: **teardown must assert the world is as it was, not
merely issue the undo commands.** Cancel, then LOOK.

SECOND INCIDENT, 2026-08-10 (#548) — "cancelled N/N" meant "cancel REQUEST sent N/N", not
confirmed. `alpaca_client.cancel_order` returns True on success and swallows ANY exception
(including "already terminal") into False, and the old teardown never inspected that return
value at all; its one verify pass only checked whether the order had FILLED — never whether the
cancel had actually landed. `_548_resting_limit_smoke.py` hit this directly: teardown reported
"cancelled 1/1" for a sell-stop that a direct `get_open_orders` check showed was STILL resting,
and the probe's next phase then had its own order REJECTED — Alpaca's opposite-side wash-trade
guard cited that "cancelled" order as a live position. Fixed the same way
`order_manager._reduce_stop_via_cancel_new` (money path, NOT touched by this fix) already does
it: classify against the order's OWN status, read back from the broker with a bounded poll,
never against the cancel request's return value. `teardown` now also sweeps every touched
symbol's open-orders list (not just the order ids it was handed) — a `replace_order_by_id` call
mints a NEW id, invisible to a per-id check, and this probe's Q3 hit exactly that shape. See
`_TERMINAL_ORDER_STATUSES` / `_CANCEL_CONFIRM_BUDGET_S` / `wait_for_open_orders_clear` below.

Usage — replace the bare cancel loop in a probe's `finally:` with:

    from _probe_safety import teardown
    ...
    finally:
        await teardown(alpaca, placed, account_mode=_ACCOUNT_MODE, symbols=touched)

It cancels, confirms each order reached a real terminal state (bounded poll, not a single read),
sweeps each touched symbol's open-orders list for anything the id list missed, then flattens any
position the probe created, then reports. It NEVER raises — a teardown that explodes leaves more
mess than it cleans.
"""
from __future__ import annotations

import asyncio
import time


def ensure_alpaca_credentials() -> tuple[str, bool]:
    """Fail-loud credential preflight for a probe run via `docker exec ... python`.

    Reuses `agent._bootstrap_alpaca_credentials()` verbatim — DO NOT re-implement
    the ALPACA_API_KEY -> ALPACA_PAPER_* mapping here. A second copy of that
    mapping is exactly the drift class this repo keeps getting bitten by.

    WHAT THIS ACTUALLY BUYS YOU (2026-08-10, #548 credential-wall investigation):
      `docker exec` spawns a FRESH python interpreter that starts from the
      container's DECLARED env (docker-compose `environment:` + `env_file:`).
      It does NOT see the agent process's own in-memory `os.environ` mutations
      from its `@app.on_event("startup")` boot — those live only in that one
      process. So every credentialed probe must re-run this itself; that part
      is real and this call is required.

      What it does NOT do: manufacture missing credentials. Production runs
      `ENABLE_LIVE_MODE=true` (documented default, `constants.py`) — under that
      branch `_bootstrap_alpaca_credentials` only VALIDATES the four
      `ALPACA_{PAPER,LIVE}_{API_KEY,SECRET_KEY}` vars are present and raises a
      clear `RuntimeError` if not; it does NOT remap the legacy `ALPACA_API_KEY`
      var (that remap is dev-only, the `ENABLE_LIVE_MODE=false` branch). So this
      call turns a missing/misconfigured var into a loud, immediate, documented
      failure instead of a confusing downstream Alpaca 401 — it is a preflight,
      not a fix for absent creds.

    CONTAINER MATTERS MORE THAN THIS CALL. `apollo-market` (SERVICE_ROLE=
    intelligence) force-blanks all four ALPACA_* vars to `""` in
    `docker-compose.prod.yml`'s `environment:` block (creds isolation, #256 W2,
    operator-authorized 2026-06-13) — PRESENT or overriding `.env`, not absent,
    so no remap could fix it there even if one existed for the live branch, and
    working around that would defeat a deliberate security boundary. Any probe
    that touches real broker state must run against `apollo-execution` instead
    (the only container `deploy.sh` treats as `CREDS_CONTAINER`) — see
    `docs/ops/execution_split_cutover.md`.
    """
    from agents.market_intelligence.agent import _bootstrap_alpaca_credentials
    return _bootstrap_alpaca_credentials()


# Statuses meaning the order is DONE — no further transitions expected. Mirrors (but does NOT
# import) order_manager._TERMINAL_ORDER_STATUSES (broker/order_manager.py ~L3451): duplicated
# on purpose so this probe helper has no import-time dependency on the money-path module, which
# this card is explicitly barred from touching. Keep the two in sync by hand if Alpaca's status
# vocabulary changes. "filled" is handled as its own branch below (a fill, not a cancel).
_TERMINAL_ORDER_STATUSES = frozenset({
    "canceled", "cancelled", "expired", "rejected", "replaced", "done_for_day",
})

# Bounded budget for confirming a cancel actually reached one of the statuses above (or a real
# fill) — deliberately NOT tuned to either broker-side guard measured 2026-08-10 (#548) in the
# SAME run: an opposite-side wash-trade guard cleared in 0.268s/2 polls, a same-side qty-
# reservation release in 0.009s/1 poll. Different mechanisms, different lag — the fix is a
# generous shared bound plus real polling, not a number picked to match either measurement.
_CANCEL_CONFIRM_BUDGET_S = 10.0
_CANCEL_CONFIRM_POLL_S = 0.25


async def wait_for_open_orders_clear(alpaca, ticker: str, account_mode: str, *,
                                      timeout: float = 30.0, interval: float = 0.25) -> dict:
    """Poll `get_open_orders(ticker)` — broker-side filtered to OPEN status — until it is EMPTY.
    Returns `{"cleared": bool, "elapsed_s": float, "polls": int, ...}`; on a genuine timeout adds
    `"remaining_ids"`, on a read failure adds `"error"` instead (see below — never folds a failed
    read into a false "cleared").

    Moved here 2026-08-10 (#548) from a probe-local copy in `_548_resting_limit_smoke.py`, which
    discovered that Alpaca's opposite-side wash-trade guard can still see a just-cancelled order
    for a window AFTER that order's own status has gone terminal — a per-order-id `get_order`
    check (what `teardown` does below) and a per-SYMBOL open-orders listing are two different
    views of broker state, and `teardown` needs both: per-id for the orders it was handed,
    symbol-level for anything it wasn't (e.g. a `replace_order_by_id` successor — a NEW id the
    caller never saw to pass in).

    Passes `raise_on_error=True` on every read. `get_open_orders`'s bare default silently
    returns `[]` on a broker-read FAILURE, indistinguishable from a genuinely empty book — the
    exact swallow-into-false-success shape this whole module exists to catch one layer up. A
    read failure is reported via the `error` key instead.
    """
    t0 = time.monotonic()
    polls = 0
    while True:
        polls += 1
        try:
            open_orders = await alpaca.get_open_orders(
                ticker, account_mode=account_mode, raise_on_error=True)
        except Exception as e:
            return {"cleared": False, "elapsed_s": round(time.monotonic() - t0, 3),
                    "polls": polls, "error": f"{type(e).__name__}: {str(e)[:160]}"}
        elapsed = time.monotonic() - t0
        if not open_orders:
            return {"cleared": True, "elapsed_s": round(elapsed, 3), "polls": polls}
        if elapsed >= timeout:
            return {"cleared": False, "elapsed_s": round(elapsed, 3), "polls": polls,
                    "remaining_ids": [o.get("id") for o in open_orders]}
        await asyncio.sleep(interval)


async def teardown(alpaca, order_ids, *, account_mode: str, symbols=None) -> dict:
    """Cancel `order_ids`, CONFIRM each reached a real terminal broker state, sweep each touched
    symbol's open-orders list for anything the id list missed, flatten any position the probe
    created, then report. Never raises — a teardown that explodes leaves more mess than it
    cleans.

    `symbols` is the set of tickers the probe touched — checked for resting orders AND positions
    even when the matching order id was lost (a probe that crashed mid-submit, or whose order
    was superseded by a `replace_order_by_id` successor it never saw the id of, still owes this).

    "cancelled" in the returned dict means CONFIRMED terminal via a cancel-like status, not
    "a cancel request was sent" — see the module docstring's second incident. A cancel that does
    not confirm within the deadline is never counted as success; it lands in `unconfirmed` and
    `errors` instead.
    """
    assert account_mode == "paper", "probe teardown is PAPER-ONLY"
    order_ids = list(order_ids or [])
    # NOT sorted/deduped here — the classify pass below appends to `symbols` and the flatten
    # pass re-derives sorted(set(...)) anyway, so doing it now is work whose result is discarded.
    symbols = list(symbols or [])
    out = {"cancelled": 0, "filled": [], "flattened": [], "errors": [],
           "unconfirmed": [], "unswept_symbols": []}

    # ⚠ FALL BACK TO THE CANONICAL BROKER CLIENT IF THE CALLER PASSED THE WRONG OBJECT.
    # 2026-08-08: `_548_resting_limit_smoke` passed `execution_client` — the READ facade, which
    # has `get_all_positions`/`get_open_orders` but no `cancel_order`/`get_order`. Every cancel
    # and every read died on a bare AttributeError, teardown reported `cancelled 0/1`, and a
    # live ACCEPTED order was left sitting on the paper account. That is the EXACT outcome this
    # module was written to prevent, arriving through a door it had not thought to lock.
    # `get_open_orders` joined this check 2026-08-10 alongside the symbol-level sweep below —
    # same failure mode, one more required capability.
    #
    # A teardown that cannot clean up is worse than no teardown, because the probe author reads
    # "teardown: …" and believes it ran. So this does not merely warn — it goes and gets an
    # object that works. The wrong-object case is still recorded in `errors` so it is visible.
    if not all(hasattr(alpaca, m) for m in
               ("cancel_order", "get_order", "get_position", "get_open_orders")):
        out["errors"].append(
            f"caller passed {getattr(alpaca, '__name__', type(alpaca).__name__)} which cannot "
            "cancel/read orders — fell back to broker.alpaca_client")
        from agents.market_intelligence.broker import alpaca_client as alpaca

    # 1) REQUEST the cancel for every id. The return value is deliberately IGNORED —
    #    `alpaca_client.cancel_order` returns True on success and swallows ANY exception
    #    (including "already terminal/gone") into False, so the return value cannot distinguish
    #    "genuinely failed" from "already fine." Classification happens in step 2, against the
    #    order's own status read back from the broker — same principle
    #    `order_manager._reduce_stop_via_cancel_new` already uses on the money path.
    for oid in order_ids:
        try:
            await alpaca.cancel_order(oid, account_mode=account_mode)
        except Exception as e:          # cancel_order itself shouldn't raise; belt-and-braces
            out["errors"].append(f"cancel request {oid}: {type(e).__name__}")

    # 2) CONFIRM — poll every order until it reaches a TERMINAL status or fully FILLS, bounded
    #    by ONE shared deadline (not summed per-order — an id that never resolves must not
    #    starve the others' polling budget). `partially_filled` is deliberately NOT terminal
    #    here: a cancel against a partial fill is still settling the remainder, so it stays
    #    pending until it resolves one way or the other, or the deadline passes.
    last_status: dict[str, str | None] = {}
    last_order: dict[str, dict] = {}
    last_read_error: dict[str, str] = {}
    pending = set(order_ids)
    deadline = time.monotonic() + _CANCEL_CONFIRM_BUDGET_S
    while True:
        for oid in list(pending):
            try:
                o = await alpaca.get_order(oid, account_mode=account_mode) or {}
                status = (o.get("status") or "").lower() or None
                last_status[oid] = status
                last_order[oid] = o
                if status == "filled" or status in _TERMINAL_ORDER_STATUSES:
                    pending.discard(oid)
            except Exception as e:
                last_read_error[oid] = f"{type(e).__name__}: {str(e)[:120]}"
        if not pending or time.monotonic() >= deadline:
            break
        await asyncio.sleep(_CANCEL_CONFIRM_POLL_S)

    # LOOK — classify what step 2 actually observed. Genuinely-fine terminal cases (already
    # filled, already cancelled, before we even asked) are NOT errors — only a cancel that
    # never confirmed within the deadline is loud.
    for oid in order_ids:
        status = last_status.get(oid)
        o = last_order.get(oid, {})
        if status == "filled":
            out["filled"].append({"id": oid, "symbol": o.get("symbol"),
                                  "qty": o.get("filled_qty") or o.get("qty"),
                                  "status": status})
            if o.get("symbol"):
                symbols.append(o["symbol"])
            continue
        if status in _TERMINAL_ORDER_STATUSES:
            out["cancelled"] += 1
            continue
        # NOT confirmed within the deadline: still resting, still partially filled (remainder
        # unresolved), or unreadable. This is the fix — report it, never count it as success.
        out["unconfirmed"].append(oid)
        if status == "partially_filled":
            out["filled"].append({"id": oid, "symbol": o.get("symbol"),
                                  "qty": o.get("filled_qty") or o.get("qty"),
                                  "status": status})
            if o.get("symbol"):
                symbols.append(o["symbol"])
            detail = (f"partially filled ({o.get('filled_qty')}/{o.get('qty')}), "
                      "remainder status unresolved")
        elif status:
            detail = f"still {status}"
        else:
            detail = last_read_error.get(oid, "unreadable")
        out["errors"].append(
            f"cancel not confirmed for {oid}: {detail} after "
            f"{_CANCEL_CONFIRM_BUDGET_S:g}s — CHECK THE ACCOUNT BY HAND")

    # 3) SYMBOL-LEVEL SWEEP — catches resting orders the per-id loop above structurally cannot
    #    see (e.g. a `replace_order_by_id` successor mints a NEW id the caller never passed in).
    #    MUST run before the flatten pass below: `close_position` submits a market order, which
    #    would itself show up as an open order and falsely trip this check if swept afterward.
    for sym in sorted(set(symbols)):
        swept = await wait_for_open_orders_clear(
            alpaca, sym, account_mode,
            timeout=_CANCEL_CONFIRM_BUDGET_S, interval=_CANCEL_CONFIRM_POLL_S)
        if not swept.get("cleared"):
            out["unswept_symbols"].append(sym)
            detail = swept.get("error") or f"still open: {swept.get('remaining_ids')}"
            out["errors"].append(
                f"open orders not confirmed clear for {sym} after "
                f"{swept.get('elapsed_s')}s/{swept.get('polls')} polls: {detail} — "
                "CHECK THE ACCOUNT BY HAND")

    for sym in sorted(set(symbols)):
        try:
            pos = await alpaca.get_position(sym, account_mode=account_mode)
            if not pos or not float(pos.get("qty") or 0):
                continue
            await alpaca.close_position(sym, account_mode=account_mode)
            out["flattened"].append({"symbol": sym, "qty": pos.get("qty")})
        except Exception as e:
            out["errors"].append(f"flatten {sym}: {type(e).__name__}: {str(e)[:160]}")

    print(f"teardown: cancelled {out['cancelled']}/{len(order_ids)} "
          "(confirmed terminal — a request sent does not count)")
    if out["unconfirmed"]:
        print(f"  🔴 {len(out['unconfirmed'])} cancel(s) did NOT confirm within "
              f"{_CANCEL_CONFIRM_BUDGET_S:g}s — see errors below")
    if out["filled"]:
        print(f"  ⚠ {len(out['filled'])} order(s) had already FILLED — a cancel could not undo them:")
        for f in out["filled"]:
            print(f"      {f['symbol']} {f['qty']} ({f['status']})")
    if out["flattened"]:
        print(f"  ✅ flattened {len(out['flattened'])} probe-created position(s):")
        for f in out["flattened"]:
            print(f"      {f['symbol']} {f['qty']}")
    if out["errors"]:
        # LOUD, not swallowed: an un-flattened probe position is exactly what generated 27
        # spurious drift events and misdirected two anomaly investigations.
        print(f"  🔴 {len(out['errors'])} teardown error(s) — CHECK THE ACCOUNT BY HAND:")
        for e in out["errors"]:
            print(f"      {e}")
    if not out["filled"] and not out["errors"]:
        print("  clean — nothing filled, nothing left behind")
    return out
