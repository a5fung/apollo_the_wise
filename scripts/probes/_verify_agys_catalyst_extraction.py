"""Live verification: run the catalyst metrics extractor against AGYS,
inspect what the multi-source LLM extraction produces.

Run: docker exec apollo-market python -m scripts._verify_agys_catalyst_extraction
"""
import asyncio
import json
from datetime import date

from agents.market_intelligence.catalyst_metrics_extractor import (
    extract_earnings_metrics, get_q_revenue_yoy_pct,
)
from agents.market_intelligence.collector import (
    get_fmp_news, search_news_perplexity,
)


async def main():
    ticker = "AGYS"
    today = date.today()

    # Mimic what ep_detector passes: FMP news + Perplexity synthesis
    print(f"Fetching FMP news for {ticker}...")
    fmp_news = await get_fmp_news(ticker, limit=5)
    print(f"  FMP news items: {len(fmp_news)}")

    print(f"Fetching Perplexity catalyst search...")
    perplexity_text = await search_news_perplexity(
        f"What caused {ticker} stock to gap up today? Latest catalyst and earnings results.",
        recency="week",
    )
    print(f"  Perplexity text len: {len(perplexity_text or '')}")

    print(f"\nRunning multi-source extraction (Polygon + FMP + Perplexity + claude_analysis=None)...")
    extracted = await extract_earnings_metrics(
        ticker, today,
        claude_analysis=None,  # ep_detector would have this; using None for raw test
        perplexity_text=perplexity_text,
        fmp_news=fmp_news,
    )

    print(f"\n=== Extraction output for {ticker} ===")
    print(json.dumps(extracted, indent=2, default=str))

    print(f"\n=== Gate decision ===")
    q_rev_yoy = get_q_revenue_yoy_pct(extracted)
    quality = extracted.get("extraction_quality", "unknown")
    print(f"  q_revenue_yoy_pct: {q_rev_yoy}")
    print(f"  extraction_quality: {quality}")
    print(f"  reasoning_brief: {extracted.get('reasoning_brief')}")

    from agents.market_intelligence.constants import EARNINGS_REVENUE_GATE_MIN_YOY
    if q_rev_yoy is None:
        print(f"  VERDICT: DOWNGRADE — q_rev_yoy unextractable (quality={quality})")
    elif q_rev_yoy < EARNINGS_REVENUE_GATE_MIN_YOY:
        print(f"  VERDICT: DOWNGRADE — {q_rev_yoy:.1f}% < {EARNINGS_REVENUE_GATE_MIN_YOY:.0f}%")
    else:
        print(f"  VERDICT: PASS — {q_rev_yoy:.1f}% >= {EARNINGS_REVENUE_GATE_MIN_YOY:.0f}%")


if __name__ == "__main__":
    asyncio.run(main())
