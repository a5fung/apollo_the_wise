"""Does Alpaca reject a stop-buy whose trigger the session has ALREADY TRADED THROUGH? PAPER ONLY.

2026-08-06. INSM was rejected `[6098] Stop Price Already Triggered/Exceeds $ Threshold`; RDW,
submitted in the same second with the same shape, was accepted. Three explanations died to
evidence already in hand:

  1. "the stock had faded"          — dead: that was OUR synthesised diagnosis, not Alpaca's.
  2. "trigger == the ORB high"      — dead: RDW's trigger was ALSO exactly its ORB high.
  3. "we misread price off IEX"     — dead: SIP shows the same 128.96 prints at submit.

The one thing that still separates them, measured on the SIP tape before each submit:

    RDW   trigger 12.75   max print 12.75    touched, never exceeded   -> ACCEPTED
    INSM  trigger 129.41  max print 129.48   traded $0.07 THROUGH      -> REJECTED

That is a hypothesis on n=2, which is not evidence. This probe TESTS it instead of arguing it:
same symbol, same second, same shape, ONE variable — whether the session has already printed
above the trigger.

    python scripts/probes/_541_stop_already_triggered_probe.py            # dry
    python scripts/probes/_541_stop_already_triggered_probe.py --execute  # PAPER, cancels all

READ THE RESULT HONESTLY. If BOTH are accepted the hypothesis is dead and the cause is still
unknown — say so. If BOTH are rejected, something about the shape is wrong and RDW becomes the
anomaly instead. Only A-rejected + B-accepted supports it.
"""
import argparse
import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone

_ACCOUNT_MODE = "paper"      # LITERAL — asserted before every submit
_OUT = "/tmp/_541_stop_already_triggered_probe.json"
_CANDIDATES = ("F", "T", "SOFI", "PLTR")   # liquid, so the session has a real range


async def _session_high_and_last(sym: str):
    """(session high, last) from the SIP tape since today's open — the same statistic the
    hypothesis is about. Uses SIP explicitly: an IEX-only read is a partial tape and would
    understate the high, which is the exact confound this probe must not import."""
    import os, urllib.request
    now = datetime.now(timezone.utc)
    start = now.replace(hour=13, minute=30, second=0, microsecond=0)
    if now < start:
        return None, None
    url = (f"https://data.alpaca.markets/v2/stocks/{sym}/trades"
           f"?start={start.strftime('%Y-%m-%dT%H:%M:%SZ')}"
           f"&end={now.strftime('%Y-%m-%dT%H:%M:%SZ')}&feed=sip&limit=10000")
    req = urllib.request.Request(url, headers={
        "APCA-API-KEY-ID": os.environ["ALPACA_LIVE_API_KEY"],
        "APCA-API-SECRET-KEY": os.environ["ALPACA_LIVE_SECRET_KEY"]})
    tr = (json.loads(urllib.request.urlopen(req).read()).get("trades") or [])
    if not tr:
        return None, None
    return max(t["p"] for t in tr), tr[-1]["p"]


async def run(execute: bool) -> int:
    from agents.market_intelligence.broker import alpaca_client as alpaca
    assert _ACCOUNT_MODE == "paper", "PROBE IS PAPER-ONLY"

    sym = hi = last = None
    for c in _CANDIDATES:
        h, l = await _session_high_and_last(c)
        # need the last price meaningfully BELOW the session high, so that a trigger can sit
        # between them: already traded through, but not currently in the money.
        if h and l and h - l > 0.05:
            sym, hi, last = c, h, l
            break
    if not sym:
        print("no candidate has enough range between last and session high yet — try later")
        return 2

    # A: trigger BETWEEN last and the session high -> already traded THROUGH, not in the money now
    a_trig = round((last + hi) / 2, 2)
    # B: trigger ABOVE the session high -> never printed at all
    b_trig = round(hi + 0.15, 2)
    cases = [
        {"id": "A_trigger_ALREADY_traded_through", "trig": a_trig, "expect": "rejected 6098",
         "why": f"{sym} session high {hi} > trigger {a_trig} > last {last} — the INSM shape"},
        {"id": "B_trigger_NEVER_traded", "trig": b_trig, "expect": "accepted",
         "why": f"trigger {b_trig} above the session high {hi} — nothing has printed there"},
    ]
    print(f"{sym}: session_high={hi}  last={last}  account={_ACCOUNT_MODE}")
    for c in cases:
        print(f"  {c['id']:36} trig={c['trig']:>8}  expect={c['expect']}")
        print(f"      {c['why']}")
    if not execute:
        print("\nDRY RUN — nothing submitted.")
        return 0

    placed, results = [], []
    try:
        for c in cases:
            lim = round(c["trig"] * 1.005, 2)
            sl = round(c["trig"] * 0.97, 2)
            rec = {**c, "limit": lim, "stop_loss": sl, "symbol": sym,
                   "session_high": hi, "last": last}
            try:
                o = await alpaca.place_bracket_order(
                    sym, 1, c["trig"], lim, sl, account_mode=_ACCOUNT_MODE)
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
                rec["raw"] = str(e)[:600]
            results.append(rec)
            print(f"  {rec['id']:36} -> {rec.get('status')}  {rec.get('broker_reason') or rec.get('raw','')}")
    finally:
        # Cancel-then-LOOK (2026-08-06). Arm A deliberately sits a trigger BETWEEN the last
        # price and the session high — i.e. squarely in reach — so a fill here is likely, not
        # exotic. A cancel cannot undo one. See _probe_safety.teardown.
        from _probe_safety import teardown
        await teardown(alpaca, placed, account_mode=_ACCOUNT_MODE, symbols=[sym])

    a = next(r for r in results if r["id"].startswith("A"))
    b = next(r for r in results if r["id"].startswith("B"))
    if a.get("status") == "rejected" and b.get("status") != "rejected":
        verdict = "SUPPORTED — already-traded-through rejects, never-traded accepts"
    elif a.get("status") != "rejected" and b.get("status") != "rejected":
        verdict = "REFUTED — both accepted; 'already traded through' is NOT the cause"
    else:
        verdict = f"INCONCLUSIVE — A={a.get('status')} B={b.get('status')}; cause still unknown"
    print(f"\nVERDICT: {verdict}")
    with open(_OUT, "w") as f:
        json.dump({"verdict": verdict, "results": results}, f, indent=2, default=str)
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true")
    sys.exit(asyncio.run(run(ap.parse_args().execute)))
