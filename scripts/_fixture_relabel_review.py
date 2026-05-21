"""Fixture re-review (#57) — compare operator weekend labels to current
rubric output after all 2026-05-19/20/21 methodology + extraction work.

For each of the 6 weekend-labeled fixtures, pull the cached extraction
from mi_ep_catalyst_metrics + score via the rubric + display side-by-
side with operator label + reasoning brief.

Goal: identify which operator labels remain methodologically defensible
vs which should be re-labeled given the cohort-evidence framing.

Run: docker exec apollo-market python -m scripts._fixture_relabel_review
"""
import asyncio
from datetime import date


# Operator weekend labels per catalyst_rubric.FIXTURES dict
FIXTURES = [
    ("NBIS", date(2026, 3, 16), "game_changer"),
    ("CSCO", date(2026, 5, 14), "routine"),
    ("KLAR", date(2026, 5, 14), "routine"),
    ("TRT",  date(2026, 5, 15), "strong"),
    ("ONDS", date(2026, 5, 14), "strong"),
    ("CPA",  date(2026, 5, 14), "strong"),
]


async def _re_extract(ticker: str, alert_date: date):
    """For fixtures without cached extraction, re-extract using historical
    news (Polygon time-windowed + Alpaca News). Perplexity is current-only
    so historical extraction is degraded, but still informs the rubric.
    Persists so subsequent calls hit the cache.
    """
    from agents.market_intelligence.catalyst_metrics_extractor import (
        extract_earnings_metrics, persist_catalyst_metrics,
    )
    from agents.market_intelligence.collector import get_fmp_news
    from datetime import timedelta
    fmp_news = await get_fmp_news(
        ticker, limit=10,
        from_date=alert_date - timedelta(days=7),
        to_date=alert_date,
    )
    extracted = await extract_earnings_metrics(
        ticker, alert_date,
        claude_analysis=None,
        perplexity_text=None,  # no time-travel
        fmp_news=fmp_news,
        news_on_or_before=alert_date,
    )
    await persist_catalyst_metrics(ticker, alert_date, extracted)
    return extracted


async def main():
    from agents.market_intelligence.catalyst_metrics_extractor import lookup_cached_metrics
    from agents.market_intelligence.catalyst_rubric_runtime import score_ep_with_rubric

    print("=" * 100)
    print(f"{'TICKER':<8} {'DATE':<12} {'OPERATOR LABEL':<16} {'RUBRIC':<22} {'COMP':<8} {'MATCH'}")
    print("-" * 100)

    rows = []
    for ticker, alert_date, expected in FIXTURES:
        extracted = await lookup_cached_metrics(ticker, alert_date)
        if not extracted:
            print(f"  ... re-extracting {ticker} (no cached row)")
            try:
                extracted = await _re_extract(ticker, alert_date)
            except Exception as e:
                rows.append({
                    "ticker": ticker, "date": alert_date, "expected": expected,
                    "extracted": None, "rubric": None, "composite": None,
                    "label": None, "match": f"re_extract_failed: {type(e).__name__}",
                    "reasoning": None,
                })
                continue
        if not extracted or extracted.get("extraction_quality") == "low" and extracted.get("extraction_error"):
            rows.append({
                "ticker": ticker, "date": alert_date, "expected": expected,
                "extracted": extracted, "rubric": None, "composite": None,
                "label": None, "match": "extraction_failed",
                "reasoning": None,
            })
            continue
        result = score_ep_with_rubric(ticker, extracted, alert_date)
        if not result:
            rows.append({
                "ticker": ticker, "date": alert_date, "expected": expected,
                "extracted": extracted, "rubric": None, "composite": None,
                "label": "no_yoy_data", "match": "rubric_safety_net",
                "reasoning": extracted.get("reasoning_brief", "")[:100],
            })
            continue
        label = result.get("label")
        composite = result.get("composite_scaled")
        match = "✓" if label == expected else "DIFF"
        rows.append({
            "ticker": ticker, "date": alert_date, "expected": expected,
            "extracted": extracted, "rubric": result,
            "composite": composite, "label": label, "match": match,
            "reasoning": extracted.get("reasoning_brief", "")[:100],
        })

    for r in rows:
        comp_str = f"{r['composite']:.1f}/39" if r['composite'] is not None else "—"
        rubric_label = r['label'] if r['label'] else "—"
        print(f"{r['ticker']:<8} {str(r['date']):<12} {r['expected']:<16} "
              f"{rubric_label:<22} {comp_str:<8} {r['match']}")
    print()

    # Per-fixture detail block
    for r in rows:
        print("=" * 100)
        print(f"{r['ticker']} ({r['date']})")
        print("=" * 100)
        print(f"Operator label: {r['expected']}")
        if r['rubric']:
            print(f"Rubric verdict: {r['label']} (composite {r['composite']:.1f}/39)")
            print(f"Caps applied:   {r['rubric'].get('caps_applied') or 'none'}")
            print(f"Per-axis:")
            for i in range(1, 7):
                score = r['rubric'].get(f"a{i}_score")
                reason = r['rubric'].get(f"a{i}_reason", "")[:80]
                if score is not None:
                    print(f"  a{i}: {score}/5 — {reason}")
                else:
                    print(f"  a{i}: not scored")
            if r['reasoning']:
                print(f"Reasoning: {r['reasoning']}")
        else:
            print(f"No rubric score: {r['match']}")
            if r['extracted']:
                qrv = (r['extracted'].get('q_revenue_usd') or {})
                print(f"q_revenue: value={qrv.get('value')} yoy={qrv.get('yoy_pct')}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
