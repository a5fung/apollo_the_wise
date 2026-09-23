"""Live end-to-end verification: AGYS extraction → rubric → gate decision.

Run: docker exec apollo-market python -m scripts._verify_agys_full_rubric
"""
import asyncio
import json
from datetime import date

from agents.market_intelligence.catalyst_metrics_extractor import (
    lookup_cached_metrics, extract_earnings_metrics,
)
from agents.market_intelligence.catalyst_rubric_runtime import (
    score_ep_with_rubric, build_rubric_inputs_hybrid,
)
from agents.market_intelligence.collector import get_fmp_news, search_news_perplexity
from agents.market_intelligence.constants import (
    EARNINGS_REVENUE_GATE_MIN_YOY, CATALYST_RUBRIC_MIN_COMPOSITE,
)


async def main():
    ticker = "AGYS"
    today = date.today()

    cached = await lookup_cached_metrics(ticker, today)
    if cached:
        extracted = cached
        print(f"Using cached extraction for {ticker}")
    else:
        print(f"No cache — running fresh extraction...")
        fmp_news = await get_fmp_news(ticker, limit=5)
        perplexity_text = await search_news_perplexity(
            f"What caused {ticker} stock to gap up today? Latest catalyst and earnings results.",
            recency="week",
        )
        extracted = await extract_earnings_metrics(
            ticker, today,
            claude_analysis=None, perplexity_text=perplexity_text, fmp_news=fmp_news,
        )

    print("\n=== Extracted metrics ===")
    qr = extracted.get("q_revenue_usd") or {}
    print(f"  q_revenue: ${qr.get('value')} YoY {qr.get('yoy_pct')}% (conf={qr.get('confidence')})")
    qe = extracted.get("q_eps") or {}
    print(f"  q_eps: ${qe.get('value')} YoY {qe.get('yoy_pct')}% beat_vs_est={qe.get('beat_vs_est_pct')}%")
    gf = extracted.get("guidance_fy_revenue_usd") or {}
    print(f"  guidance: ${gf.get('low')}-${gf.get('high')} midpoint_yoy={gf.get('midpoint_yoy_pct')}%")

    print("\n=== Hybrid inputs to rubric ===")
    fund, beat, guidance = build_rubric_inputs_hybrid(ticker, extracted, today)
    print(f"  fund.deltas:")
    for k, v in fund["deltas"].items():
        if v is not None and v != {}:
            print(f"    {k}: {v}")
    print(f"  beat: {beat}")
    print(f"  guidance: {guidance}")

    print("\n=== Rubric scoring ===")
    result = score_ep_with_rubric(ticker, extracted, today)
    if result is None:
        print("  Rubric returned None (couldn't score)")
        return

    print(f"  composite_raw: {result.get('composite_raw')}")
    print(f"  composite_scaled: {result.get('composite_scaled')} / 39")
    print(f"  max_available: {result.get('max_available')}")
    print(f"  label: {result.get('label')}")
    print(f"  caps_applied: {result.get('caps_applied')}")
    print(f"  Per-axis scores:")
    for axis in ("a1", "a2", "a3", "a4", "a5", "a6"):
        score = result.get(f"{axis}_score")
        reason = result.get(f"{axis}_reason")
        print(f"    {axis}: score={score} reason={reason}")

    print(f"\n=== Gate decision ===")
    comp = result.get("composite_scaled")
    label = result.get("label")
    if comp is not None and comp < CATALYST_RUBRIC_MIN_COMPOSITE:
        print(f"  VERDICT: DOWNGRADE — rubric composite {comp:.1f} < {CATALYST_RUBRIC_MIN_COMPOSITE:.0f} (label={label})")
    else:
        print(f"  VERDICT: PASS — rubric composite {comp:.1f} >= {CATALYST_RUBRIC_MIN_COMPOSITE:.0f} (label={label})")


if __name__ == "__main__":
    asyncio.run(main())
