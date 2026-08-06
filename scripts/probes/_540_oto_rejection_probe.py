"""Why did Alpaca reject the INSM entry in 3.4ms? — an empirical probe. PAPER ONLY.

2026-08-06. INSM: buy 7 @ stop_limit trigger 129.41 / limit 130.06, OTO stop-loss 126.15.
Submitted 13:31:11.892606Z, `failed_at` 13:31:11.896Z — 3.4 MILLISECONDS. Alpaca returned the
order object with status=rejected and NO reason field anywhere. The stock then ran to +33%.

Ruled out from the record already:
  * buying power — $17,355 available against a $910 order; cash $4,147
  * account state — ACTIVE, nothing blocked, no PDT flag
  * the symbol — tradable, marginable, NASDAQ, shortable, easy-to-borrow
  * an in-the-money entry stop — last $128.96 was BELOW the $129.41 trigger (normal)
  * price below the stop-loss (the Gemini hypothesis) — last $128.96 was ABOVE the $126.15 stop
  * a systemic bug — RDW was ACCEPTED in the same second with the same shape
    (buy 74, stop_limit 12.75/12.81, OTO, $948 notional)

So the cause is a validation rule we have not identified. This probe finds it by submitting the
SAME GEOMETRY on paper and varying ONE parameter at a time.

    python scripts/probes/_540_oto_rejection_probe.py            # dry — prints the plan only
    python scripts/probes/_540_oto_rejection_probe.py --execute  # submits to PAPER, cancels all

⚠ SAFETY, and it is not negotiable:
  * PAPER account only. `_ACCOUNT_MODE` is a literal and is asserted before every submit.
  * Every order placed is cancelled in a finally block, whatever happens.
  * Triggers sit FAR above the market so nothing can fill while the probe runs.
"""
import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone

_ACCOUNT_MODE = "paper"          # LITERAL. never parameterised, never read from env.
_SYMBOL = "F"                    # cheap, liquid, fractionable — the #508 probe's symbol
_OUT = "/tmp/_540_oto_rejection_probe.json"


async def _last(alpaca, sym):
    t = await alpaca.get_latest_trade(sym)
    return float(t["price"]) if t and t.get("price") else None


def _cases(px: float) -> list[dict]:
    """One knob per case. `expect` is what I predict; the POINT is where I'm wrong.

    Geometry mirrors INSM proportionally: trigger ~+0.35% over last, limit ~+0.50% over trigger,
    stop-loss ~2.5% under trigger.
    """
    trig = round(px * 1.0035, 2)
    lim = round(trig * 1.005, 2)
    sl = round(trig * 0.975, 2)
    return [
        {"id": "A_baseline_like_INSM", "expect": "accepted",
         "why": "the exact INSM shape at live prices — if this REJECTS, the shape itself is bad",
         "stop": trig, "limit": lim, "stop_loss": sl},

        {"id": "B_stop_loss_ABOVE_market", "expect": "rejected",
         "why": "Gemini's hypothesis: a stop-loss above the current price is logically invalid. "
                "INSM did NOT look like this (128.96 > 126.15), so a rejection here would still "
                "not explain INSM — it would only confirm the rule exists",
         "stop": trig, "limit": lim, "stop_loss": round(px * 1.02, 2)},

        {"id": "C_stop_loss_BELOW_market_but_above_nothing", "expect": "accepted",
         "why": "control for B — same order, stop-loss safely under the market",
         "stop": trig, "limit": lim, "stop_loss": round(px * 0.95, 2)},

        {"id": "D_tight_limit_over_trigger", "expect": "accepted",
         "why": "INSM's limit was only 0.50% over its trigger. Tests whether a narrow "
                "trigger→limit band trips a minimum-spread rule",
         "stop": trig, "limit": round(trig * 1.001, 2), "stop_loss": sl},

        {"id": "E_limit_BELOW_trigger", "expect": "rejected",
         "why": "a buy stop-limit whose limit is under its trigger can never fill — if Alpaca "
                "rejects this silently in ~3ms, that is the signature we saw",
         "stop": trig, "limit": round(trig * 0.999, 2), "stop_loss": sl},

        {"id": "F_high_priced_proportions", "expect": "accepted",
         "why": "INSM was $129 and RDW $12.75 — the one obvious difference. Same PERCENTAGES "
                "cannot test that on a $12 symbol, so this is recorded as a known blind spot "
                "rather than pretended",
         "stop": trig, "limit": lim, "stop_loss": sl},
    ]


async def run(execute: bool) -> int:
    from agents.market_intelligence.broker import alpaca_client as alpaca

    assert _ACCOUNT_MODE == "paper", "PROBE IS PAPER-ONLY"
    px = await _last(alpaca, _SYMBOL)
    if not px:
        print(f"no last price for {_SYMBOL}; aborting")
        return 2
    cases = _cases(px)
    print(f"{_SYMBOL} last=${px:.2f}  account={_ACCOUNT_MODE}  cases={len(cases)}")
    for c in cases:
        print(f"  {c['id']:38} trig={c['stop']:>8} lim={c['limit']:>8} sl={c['stop_loss']:>8}"
              f"  expect={c['expect']}")
    if not execute:
        print("\nDRY RUN — nothing submitted. Re-run with --execute.")
        return 0

    placed, results = [], []
    try:
        for c in cases:
            rec = {"id": c["id"], "why": c["why"], "expect": c["expect"],
                   "stop": c["stop"], "limit": c["limit"], "stop_loss": c["stop_loss"]}
            t0 = datetime.now(timezone.utc)
            try:
                # place_bracket_order IS the ORB entry path: stop-limit buy + OTO stop-loss.
                # Using the same helper is the whole point — a probe against a different
                # submission path would prove nothing about the order that was rejected.
                o = await alpaca.place_bracket_order(
                    _SYMBOL, 1, c["stop"], c["limit"], c["stop_loss"],
                    account_mode=_ACCOUNT_MODE)
                rec["submitted"] = True
                rec["order_id"] = o.get("id")
                rec["status_at_submit"] = o.get("status")
                if o.get("id"):
                    placed.append(o["id"])
                await asyncio.sleep(1.0)
                fresh = await alpaca.get_order(o["id"], account_mode=_ACCOUNT_MODE) if o.get("id") else None
                rec["status_after_1s"] = (fresh or {}).get("status")
                rec["failed_at"] = (fresh or {}).get("failed_at")
            except Exception as e:
                # THE INTERESTING PATH: an HTTP error carries Alpaca's message, which the
                # order object never does. Capture it verbatim — that is the whole point.
                rec["submitted"] = False
                rec["exception_type"] = type(e).__name__
                rec["exception_raw"] = str(e)[:1200]
            rec["elapsed_ms"] = round((datetime.now(timezone.utc) - t0).total_seconds() * 1000, 1)
            results.append(rec)
            print(f"  {rec['id']:38} -> {rec.get('status_after_1s') or rec.get('exception_type')}"
                  f"  {rec.get('exception_raw','')[:110]}")
    finally:
        for oid in placed:
            try:
                await alpaca.cancel_order(oid, account_mode=_ACCOUNT_MODE)
            except Exception:
                pass
        print(f"\ncleanup: cancelled {len(placed)} order(s)")

    with open(_OUT, "w") as f:
        json.dump({"symbol": _SYMBOL, "last": px, "results": results}, f, indent=2, default=str)
    print(f"saved {_OUT}  (capture once, read many)")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true")
    sys.exit(asyncio.run(run(ap.parse_args().execute)))
