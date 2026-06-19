"""#344 arm-(a) pivotal check — is the BFLY 6/18 PR full body recoverable? READ-ONLY.

The grounded corpus saw the 8:12 ET PR as headline-only (body=0 chars). get_alpaca_news
builds NewsRequest WITHOUT include_content=True. Alpaca's News API only returns the full
Benzinga article body when include_content=True is requested. This probe re-fetches BFLY
6/18 BOTH ways and prints the body length delta — if include_content recovers the body,
arm (a) is a one-line fix (and may rescue BFLY without needing the prior 8-K).
"""
import asyncio
import os
from datetime import datetime, timezone


async def _fetch(symbol, include_content):
    from alpaca.data.historical.news import NewsClient
    from alpaca.data.requests import NewsRequest
    api_key = os.environ.get("ALPACA_PAPER_API_KEY") or os.environ.get("ALPACA_API_KEY", "")
    secret = os.environ.get("ALPACA_PAPER_SECRET_KEY") or os.environ.get("ALPACA_SECRET_KEY", "")
    client = NewsClient(api_key=api_key, secret_key=secret)
    start = datetime(2026, 6, 17, tzinfo=timezone.utc)
    end = datetime(2026, 6, 18, 23, 59, 59, tzinfo=timezone.utc)
    kw = dict(symbols=symbol, start=start, end=end, limit=20)
    try:
        req = NewsRequest(include_content=include_content, **kw)
    except TypeError as e:
        return f"NewsRequest rejects include_content kwarg: {e}", None
    loop = asyncio.get_event_loop()
    resp = await loop.run_in_executor(None, lambda: client.get_news(req))
    items = resp.dict().get("news", []) if hasattr(resp, "dict") else resp.model_dump().get("news", [])
    return None, items


async def main():
    for inc in (False, True):
        err, items = await _fetch("BFLY", inc)
        print(f"\n{'='*70}\ninclude_content={inc}\n{'='*70}")
        if err:
            print(f"  ERROR: {err}")
            continue
        for n in items:
            hl = n.get("headline", "")
            body = n.get("content", "") or ""
            summ = n.get("summary", "") or ""
            print(f"  [{n.get('created_at')}] body={len(body):>5}c summary={len(summ):>4}c  {hl[:70]}")
            if "Provides Updates" in hl and body:
                print(f"      BODY HEAD: {body[:900]}")


if __name__ == "__main__":
    asyncio.run(main())
