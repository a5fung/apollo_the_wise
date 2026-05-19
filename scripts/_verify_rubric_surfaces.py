"""Render the readable rubric surfaces for AGYS — preview what the
operator will see in Telegram.

Run: docker exec apollo-market python -m scripts._verify_rubric_surfaces
"""
import asyncio
from datetime import date

from agents.market_intelligence.catalyst_metrics_extractor import lookup_cached_metrics
from agents.market_intelligence.catalyst_rubric_runtime import (
    format_rubric_for_telegram, format_rubric_full_breakdown,
)


async def main():
    ticker = "AGYS"
    today = date.today()
    extracted = await lookup_cached_metrics(ticker, today)
    if not extracted:
        print(f"No cached extraction for {ticker} {today}")
        return

    print("=" * 60)
    print("COMPACT (EP alert snapshot)")
    print("=" * 60)
    print(format_rubric_for_telegram(ticker, extracted, today))
    print()
    print("=" * 60)
    print("FULL (/rubric TICKER command)")
    print("=" * 60)
    print(format_rubric_full_breakdown(ticker, extracted, today))


if __name__ == "__main__":
    asyncio.run(main())
