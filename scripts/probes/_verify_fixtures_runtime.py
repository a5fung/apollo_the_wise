"""Run the weekend fixtures (NBIS/CSCO/KLAR/TRT/ONDS/CPA) through the
runtime extraction + rubric path. Compare to expected operator labels.

Calibration sanity check — does the live pipeline reproduce the offline
labeling work the weekend did?

Run: docker exec apollo-market python -m scripts._verify_fixtures_runtime
"""
import asyncio
from datetime import date

from agents.market_intelligence.catalyst_metrics_extractor import extract_earnings_metrics
from agents.market_intelligence.catalyst_rubric_runtime import score_ep_with_rubric
from agents.market_intelligence.collector import get_fmp_news, search_news_perplexity
from agents.market_intelligence.constants import CATALYST_RUBRIC_MIN_COMPOSITE


# Expected labels (from catalyst_rubric.py FIXTURES dict, weekend labeling)
FIXTURES = {
    "NBIS": "game_changer",
    "CSCO": "routine_correct",
    "KLAR": "routine_correct",
    "TRT":  "strong",
    "ONDS": "strong",
    "CPA":  "strong",
}


async def score_one(ticker: str) -> dict:
    today = date.today()
    fmp_news = await get_fmp_news(ticker, limit=5)
    perplexity_text = await search_news_perplexity(
        f"What caused {ticker} stock to gap up recently? Latest earnings results.",
        recency="month",
    )
    extracted = await extract_earnings_metrics(
        ticker, today,
        claude_analysis=None, perplexity_text=perplexity_text, fmp_news=fmp_news,
    )
    rubric = score_ep_with_rubric(ticker, extracted, today)
    return {"extracted": extracted, "rubric": rubric}


async def main():
    print(f"{'ticker':<6} {'expected':<16} {'composite':<10} {'label':<18} {'match':<6} {'verdict':<12}")
    print("-" * 80)
    for ticker, expected in FIXTURES.items():
        try:
            result = await score_one(ticker)
        except Exception as e:
            print(f"{ticker:<6} {expected:<16} ERROR: {e}")
            continue

        rubric = result["rubric"]
        if rubric is None:
            print(f"{ticker:<6} {expected:<16} {'(no q_rev)':<10} {'(not scored)':<18} {'-':<6} {'safety_net'}")
            continue

        comp = rubric.get("composite_scaled")
        label = rubric.get("label", "?")
        match = "OK" if label == expected else "DIFF"
        verdict = "DOWNGRADE" if comp is not None and comp < CATALYST_RUBRIC_MIN_COMPOSITE else "PASS"
        print(f"{ticker:<6} {expected:<16} {comp:>5.1f}/39   {label:<18} {match:<6} {verdict:<12}")


if __name__ == "__main__":
    asyncio.run(main())
