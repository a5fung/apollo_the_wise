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

Usage — replace the bare cancel loop in a probe's `finally:` with:

    from _probe_safety import teardown
    ...
    finally:
        await teardown(alpaca, placed, account_mode=_ACCOUNT_MODE, symbols=touched)

It cancels, then re-reads each order, then flattens any position the probe created, then reports.
It NEVER raises — a teardown that explodes leaves more mess than it cleans.
"""
from __future__ import annotations


async def teardown(alpaca, order_ids, *, account_mode: str, symbols=None) -> dict:
    """Cancel `order_ids`, then verify nothing filled; flatten anything that did.

    `symbols` is the set of tickers the probe touched — checked for positions even when the
    matching order id was lost (a probe that crashed mid-submit still owes this).

    Returns a summary dict and prints it. Never raises.
    """
    assert account_mode == "paper", "probe teardown is PAPER-ONLY"
    order_ids = list(order_ids or [])
    symbols = sorted(set(symbols or []))
    out = {"cancelled": 0, "filled": [], "flattened": [], "errors": []}

    for oid in order_ids:
        try:
            await alpaca.cancel_order(oid, account_mode=account_mode)
            out["cancelled"] += 1
        except Exception as e:                     # already terminal, or gone
            out["errors"].append(f"cancel {oid}: {type(e).__name__}")

    # LOOK — the step whose absence caused the incident above. A cancel that "succeeded" tells
    # you nothing about whether the order had already filled.
    for oid in order_ids:
        try:
            o = await alpaca.get_order(oid, account_mode=account_mode) or {}
            status = (o.get("status") or "").lower()
            if status in ("filled", "partially_filled"):
                out["filled"].append({"id": oid, "symbol": o.get("symbol"),
                                      "qty": o.get("filled_qty") or o.get("qty"),
                                      "status": status})
                if o.get("symbol"):
                    symbols.append(o["symbol"])
        except Exception as e:
            out["errors"].append(f"read {oid}: {type(e).__name__}")

    for sym in sorted(set(symbols)):
        try:
            pos = await alpaca.get_position(sym, account_mode=account_mode)
            if not pos or not float(pos.get("qty") or 0):
                continue
            await alpaca.close_position(sym, account_mode=account_mode)
            out["flattened"].append({"symbol": sym, "qty": pos.get("qty")})
        except Exception as e:
            out["errors"].append(f"flatten {sym}: {type(e).__name__}: {str(e)[:160]}")

    print(f"teardown: cancelled {out['cancelled']}/{len(order_ids)}")
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
