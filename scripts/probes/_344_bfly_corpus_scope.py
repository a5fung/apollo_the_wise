"""#344 root-cause scoping for BFLY 6/18 — READ-ONLY. Throwaway.

Operator labeled BFLY 6/18 a real EP and corrected the grade reasoning: the partner
IS named (Midjourney) and the contract value DOES exist ($74M / 5yr, prior 8-K). This
probe determines WHICH fix that implies:
  (a) corpus-completeness gap — the $74M prior-agreement context was NOT in the grounded
      corpus the grader saw (replay found SEC=0 in-window); confirm the prior 8-K exists.
  (b) named-partner / materiality recognition — did the 6/18 PR text the grader saw
      actually name Midjourney as the external partner, or was it vague ("Its Midjourney
      Medical" reads like a Butterfly product)?
Prints the FULL primary-subject PR text + any prior BFLY filing mentioning midjourney/$74M.
"""
import asyncio
from datetime import date

from agents.market_intelligence.collector import (
    get_alpaca_news, get_sec_recent_filings, is_primary_subject_news,
)


async def main():
    tk, ad = "BFLY", date(2026, 6, 18)

    print("=" * 78)
    print("1) BENZINGA primary-subject items the grader's corpus drew from (6/18)")
    print("=" * 78)
    news = await get_alpaca_news(tk, to_date=ad, lookback_days=10, limit=30)
    for n in news or []:
        prim = is_primary_subject_news(n, tk, "Butterfly Network")
        hl = n.get("headline") or n.get("title") or ""
        if not prim:
            continue
        body = (n.get("content") or n.get("summary") or n.get("text") or "")
        print(f"\n[{n.get('created_at')}] (primary_subject={prim})")
        print(f"  HEADLINE: {hl}")
        print(f"  BODY ({len(body)} chars): {body[:1400]}")
        low = (hl + ' ' + body).lower()
        print(f"  >>> names 'midjourney'? {'midjourney' in low}   mentions '74'? {'74' in low}")

    print("\n" + "=" * 78)
    print("2) PRIOR BFLY 8-K/6-K filings — does the $74M Midjourney agreement exist on file?")
    print("=" * 78)
    filings = await get_sec_recent_filings(
        tk, forms=("8-K", "6-K"), lookback_days=400, max_filings=30, want_text=True)
    print(f"  fetched {len(filings or [])} filings (400d lookback)")
    for f in filings or []:
        txt = (f.get("text") or "")
        low = txt.lower()
        hit_mj = "midjourney" in low
        hit_74 = "74" in low and ("million" in low or "$74" in low or "74,000,000" in low)
        flag = "  <<< MIDJOURNEY" if hit_mj else ("  <<< $74?" if hit_74 else "")
        print(f"  {f.get('filed')}  {f.get('form'):5} items={f.get('items')}  "
              f"textlen={len(txt)}{flag}")
        if hit_mj or hit_74:
            # show the snippet around the first midjourney / 74 mention
            idx = low.find("midjourney")
            if idx < 0:
                idx = low.find("74")
            print(f"      …{txt[max(0,idx-120):idx+260]}…")


if __name__ == "__main__":
    asyncio.run(main())
