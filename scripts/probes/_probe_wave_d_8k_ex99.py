"""Wave D probe — confirm 8-K EX-99 concatenation pulls the press-release body.
Read-only SEC fetch. Throwaway."""
import asyncio
import sys


async def main():
    from agents.market_intelligence.collector import get_sec_recent_filings
    tickers = sys.argv[1:] or ["CRM", "AVGO", "COST", "HPE", "CRWD", "ADBE"]
    for t in tickers:
        fs = await get_sec_recent_filings(t, forms=("8-K",), lookback_days=30, max_filings=4)
        if not fs:
            print(f"{t:6} — no 8-K in window")
            continue
        for f in fs:
            has_ex = "[EX-99]" in (f.get("text") or "")
            print(f"{t:6} {f['form']:5} filed {f['filed']} items={f.get('items','')!r:18} "
                  f"len={len(f.get('text') or ''):5} ex99={'Y' if has_ex else 'n'} "
                  f"exhibit={'Y' if f.get('exhibit_url') else 'n'}")


if __name__ == "__main__":
    asyncio.run(main())
