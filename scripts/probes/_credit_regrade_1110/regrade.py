"""11-10 credit-outage regrade — READ-ONLY w.r.t. live state. Re-runs the live enriched
catalyst grade for the 11 names whose 07:00-09:20 ET grade hit the credits-exhausted
fail-routine sentinel. Audit writes are stubbed out (no rows that would confuse the
record); api_usage cost rows still land (they are true spend). News is as of NOW
(after the open), so this leans generous vs what the 07:00 grade could have seen."""
import asyncio, json, sys
from datetime import date
import agents.market_intelligence.ep_detector as ed

async def _noop(*a, **k):
    return True
ed.log_audit_event = _noop

TICKERS = ["QMCO","HROW","SECZ","EIKN","RLGT","CSQR","VMD","CCAP","PAYS","MCFT","CTY"]

async def one(t):
    try:
        profile = await ed.get_fmp_profile(t)
        out = await ed._build_enriched_corpus(t, date(2026, 11, 10), profile or {}, deal_sink={})
        q, analysis = out[0], out[1]
        sentinel = ed._CLASSIFY_FAIL_SENTINEL in (analysis or "")
        return {"ticker": t, "quality": q, "sentinel": sentinel, "analysis": (analysis or "")[:600]}
    except Exception as e:
        return {"ticker": t, "error": f"{type(e).__name__}: {e}"[:300]}

async def main():
    for t in TICKERS:
        r = await one(t)
        print(json.dumps(r), flush=True)

asyncio.run(main())
