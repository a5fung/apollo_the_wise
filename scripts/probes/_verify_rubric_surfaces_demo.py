"""Render rubric surfaces with a synthetic 'good extraction' dict —
demonstrates what operator sees when extraction succeeds.

Run: docker exec apollo-market python -m scripts._verify_rubric_surfaces_demo
"""
import asyncio
from datetime import date

from agents.market_intelligence.catalyst_rubric_runtime import (
    format_rubric_for_telegram, format_rubric_full_breakdown,
)


# Synthetic extraction matching the earlier-successful AGYS run
DEMO_EXTRACTED = {
    "q_revenue_usd": {
        "value": 82950000,
        "yoy_pct": 11.7,
        "beat_vs_est_pct": 1.7,
        "sources": ["perplexity", "reuters"],
        "confidence": "high",
    },
    "fy_revenue_usd": {
        "value": 319300000,
        "yoy_pct": 14.7,
        "sources": ["reuters"],
        "confidence": "medium",
    },
    "q_eps": {
        "value": 0.63,
        "yoy_pct": None,
        "beat_vs_est_pct": 26.0,
        "sources": ["dowjones", "reuters"],
        "confidence": "high",
    },
    "subscription_revenue_yoy_pct": {
        "value": 30.0, "sources": ["dowjones"], "confidence": "medium",
    },
    "q_margins": None,
    "guidance_change": {
        "direction": "raised",
        "raise_pct_vs_consensus": 1.0,
        "sources": ["dowjones"],
        "confidence": "medium",
    },
    "guidance_fy_revenue_usd": {
        "low": 365000000, "high": 370000000, "midpoint_yoy_pct": 15.2,
        "sources": ["dowjones"], "confidence": "high",
    },
    "disagreement_flags": [
        "Perplexity refers to 'Q1 CY2026' while FMP refers to 'Q4 2026' — calendar vs fiscal labeling"
    ],
    "extraction_quality": "high",
    "reasoning_brief": "Perplexity synthesis explicitly states 'Revenue: $82.95M, up 11.7% year-on-year' for the quarter ended March 2026.",
}


async def main():
    ticker = "AGYS"
    today = date.today()

    print("=" * 70)
    print("WHAT OPERATOR SEES IN HIGH EP TELEGRAM ALERT")
    print("(appended below the existing alert body)")
    print("=" * 70)
    snapshot = format_rubric_for_telegram(ticker, DEMO_EXTRACTED, today)
    print(snapshot or "(none — extraction not scoreable)")

    print()
    print("=" * 70)
    print("WHAT OPERATOR SEES VIA /rubric AGYS")
    print("=" * 70)
    full = format_rubric_full_breakdown(ticker, DEMO_EXTRACTED, today)
    print(full)


if __name__ == "__main__":
    asyncio.run(main())
