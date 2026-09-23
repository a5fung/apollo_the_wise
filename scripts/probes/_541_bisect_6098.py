"""Bisect the INSM [6098] rejection. PAPER ONLY. No hypotheses — one variable at a time.

Four explanations have already died to evidence:
  1. "the stock had faded"              — that was OUR synthesised text, not Alpaca's.
  2. "trigger == the ORB high"          — RDW's trigger was ALSO exactly its ORB high, accepted.
  3. "we misread price off the IEX tape"— SIP shows the same 128.96 prints at submit.
  4. "trigger already traded through"   — TESTED on paper: both arms accepted. Refuted.

Also ruled out from the record: buying power ($17,355 vs a $910 order), account state, symbol
restrictions, and the stop_loss<=base_price-0.01 rule (126.15 <= 130.05 passes).

The one difference never tested is the one I flagged as a blind spot and then ignored: every
paper probe ran on F at ~$14, while INSM was $129. So start by replaying INSM ITSELF, then bisect.

    python scripts/probes/_541_bisect_6098.py            # dry
    python scripts/probes/_541_bisect_6098.py --execute  # PAPER, cancels everything

Report the result as it comes out. A refutation is a finding; a guess dressed as one is not.
"""
import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone

_ACCOUNT_MODE = "paper"
_OUT = "/tmp/_541_bisect_6098.json"

# INSM's exact live order, 2026-08-06 13:31:11.892606Z
_INSM = {"symbol": "INSM", "qty": 7, "trig": 129.41, "limit": 130.06, "sl": 126.15}


def _plan(insm_last: float | None) -> list[dict]:
    """Each case changes ONE thing from the INSM original. `expect` is stated so a wrong
    prediction is visible rather than quietly rationalised afterwards."""
    t, l, s, q = _INSM["trig"], _INSM["limit"], _INSM["sl"], _INSM["qty"]
    return [
        {"id": "1_EXACT_INSM_replay", "sym": "INSM", "qty": q, "trig": t, "limit": l, "sl": s,
         "expect": "?", "why": "the original order, unchanged. If this ACCEPTS now, the "
                               "condition was transient market state, not the order."},
        {"id": "2_INSM_trigger_far_above_market", "sym": "INSM", "qty": q,
         "trig": round((insm_last or t) * 1.05, 2), "limit": round((insm_last or t) * 1.056, 2),
         "sl": round((insm_last or t) * 1.02, 2),
         "expect": "?", "why": "same symbol, trigger 5% above the market — nowhere near any print"},
        {"id": "3_INSM_qty_1", "sym": "INSM", "qty": 1, "trig": t, "limit": l, "sl": s,
         "expect": "?", "why": "isolates share count / notional from the price geometry"},
        {"id": "4_INSM_wide_limit", "sym": "INSM", "qty": q, "trig": t,
         "limit": round(t * 1.02, 2), "sl": s,
         "expect": "?", "why": "INSM's limit was only 0.50% over its trigger; widen it to 2%"},
        {"id": "5_INSM_no_OTO_plain_stop_limit", "sym": "INSM", "qty": q, "trig": t,
         "limit": l, "sl": None,
         "expect": "?", "why": "drops the attached stop-loss entirely — separates the ENTRY "
                               "from the bracket. If this accepts, the OTO leg is implicated."},
        {"id": "6_HIGH_PRICED_CONTROL", "sym": "MSFT", "qty": 1, "trig": None, "limit": None,
         "sl": None,
         "expect": "?", "why": "a DIFFERENT ~$400 symbol at INSM-like proportions — tests price "
                               "level itself, the blind spot every earlier probe carried"},
    ]


async def _last(alpaca, sym):
    t = await alpaca.get_latest_trade(sym)
    return float(t["price"]) if t and t.get("price") else None


async def run(execute: bool) -> int:
    from agents.market_intelligence.broker import alpaca_client as alpaca
    assert _ACCOUNT_MODE == "paper", "PAPER ONLY"

    insm_last = await _last(alpaca, "INSM")
    cases = _plan(insm_last)
    msft_last = await _last(alpaca, "MSFT")
    for c in cases:
        if c["id"].startswith("6"):
            if not msft_last:
                c["skip"] = "no MSFT price"
                continue
            c["trig"] = round(msft_last * 1.0035, 2)
            c["limit"] = round(c["trig"] * 1.005, 2)
            c["sl"] = round(c["trig"] * 0.975, 2)

    print(f"INSM last={insm_last}  MSFT last={msft_last}  account={_ACCOUNT_MODE}")
    for c in cases:
        if c.get("skip"):
            print(f"  {c['id']:34} SKIP {c['skip']}"); continue
        print(f"  {c['id']:34} {c['sym']:5} qty={c['qty']:>2} trig={c['trig']} "
              f"lim={c['limit']} sl={c['sl']}")
        print(f"      {c['why']}")
    if not execute:
        print("\nDRY RUN — nothing submitted.")
        return 0

    placed, results = [], []
    try:
        for c in cases:
            if c.get("skip"):
                continue
            rec = dict(c)
            try:
                if c["sl"] is None:
                    o = await alpaca.place_stop_limit_buy_no_bracket(
                        c["sym"], c["qty"], c["trig"], c["limit"], account_mode=_ACCOUNT_MODE) \
                        if hasattr(alpaca, "place_stop_limit_buy_no_bracket") else None
                    if o is None:
                        rec["status"] = "SKIPPED_no_helper"
                        results.append(rec); print(f"  {c['id']:34} -> no plain stop-limit helper")
                        continue
                else:
                    o = await alpaca.place_bracket_order(
                        c["sym"], c["qty"], c["trig"], c["limit"], c["sl"],
                        account_mode=_ACCOUNT_MODE)
                if o.get("id"):
                    placed.append(o["id"])
                await asyncio.sleep(1.2)
                fresh = await alpaca.get_order(o["id"], account_mode=_ACCOUNT_MODE)
                rec["status"] = (fresh or {}).get("status")
                if rec["status"] == "rejected":
                    rec["broker_reason"] = await alpaca.fetch_broker_reject_reason(
                        o["id"], datetime.now(timezone.utc), account_mode=_ACCOUNT_MODE)
            except Exception as e:
                rec["status"] = f"EXC:{type(e).__name__}"
                rec["raw"] = str(e)[:500]
            results.append(rec)
            print(f"  {rec['id']:34} -> {rec.get('status')}  "
                  f"{rec.get('broker_reason') or rec.get('raw','')}")
    finally:
        # Cancel-then-LOOK. A bare cancel loop lived here until 2026-08-06 and it is what
        # left 7 unowned INSM shares on the paper account: case 2 places a trigger ~5% above
        # the market, INSM ran +33% that session, the order FILLED, and the cancel silently
        # no-op'd on an already-terminal order. See _probe_safety.teardown's docstring.
        from _probe_safety import teardown
        await teardown(alpaca, placed, account_mode=_ACCOUNT_MODE,
                       symbols=[c["sym"] for c in cases if not c.get("skip")])

    with open(_OUT, "w") as f:
        json.dump({"insm_last": insm_last, "msft_last": msft_last, "results": results},
                  f, indent=2, default=str)
    print(f"saved {_OUT}")
    rejected = [r["id"] for r in results if r.get("status") == "rejected"]
    print(f"\nREJECTED: {rejected or 'none — the condition did not reproduce on paper'}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true")
    sys.exit(asyncio.run(run(ap.parse_args().execute)))
