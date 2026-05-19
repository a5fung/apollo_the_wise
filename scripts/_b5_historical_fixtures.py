"""B5 — Fixture re-validation through runtime path using historical
Polygon news (on_or_before=alert_date).

Validates that runtime extraction + rubric scoring reproduces the
weekend operator labels for NBIS/CSCO/KLAR/TRT/ONDS/CPA.

PARTIALLY DEGRADED EXTRACTION CAVEAT
------------------------------------
Perplexity cannot time-travel. This script passes perplexity_text=None
to extract_earnings_metrics, so extraction relies on:
  - Polygon news (historical, gated by on_or_before)
  - FMP news (historical, gated by from_date/to_date — 2026-05-19 fix)
  - yfinance (current — fine for q1+/historical, but q0 may be stale
    if quarter changed since alert_date)

Polygon + FMP both cover the press-release window, so extraction is
substantially less degraded than the first B5 run (pre FMP date fix).
Still no Perplexity synthesis, so reasoning depth is lower than live
runtime. Use this for code-path sanity + better calibration evidence
than the v1 pass, but forward operator-feedback remains the canonical
gate-threshold validator.

Run: docker exec apollo-market python -m scripts._b5_historical_fixtures
"""
import asyncio
from datetime import date

from agents.market_intelligence.catalyst_metrics_extractor import extract_earnings_metrics
from agents.market_intelligence.catalyst_rubric_runtime import score_ep_with_rubric
from agents.market_intelligence.collector import get_fmp_news
from agents.market_intelligence.constants import CATALYST_RUBRIC_MIN_COMPOSITE


# (ticker, alert_date, expected weekend label)
# Dates sourced from mi_ep_alerts (NBIS/CSCO/KLAR/CPA) and
# mi_ep_scan_log (TRT/ONDS were filtered, not alerted).
FIXTURES = [
    ("NBIS", date(2026, 3, 16), "game_changer"),
    ("CSCO", date(2026, 5, 14), "routine_correct"),
    ("KLAR", date(2026, 5, 14), "routine_correct"),
    ("CPA",  date(2026, 5, 14), "strong"),
    ("ONDS", date(2026, 5, 14), "strong"),
    ("TRT",  date(2026, 5, 15), "strong"),
]


async def score_one(ticker: str, alert_date: date) -> dict:
    # FMP date-windowed: 7d window ending on alert_date (catalyst day inclusive)
    from datetime import timedelta as _td
    fmp_news = await get_fmp_news(
        ticker, limit=10,
        from_date=alert_date - _td(days=7),
        to_date=alert_date,
    )
    extracted = await extract_earnings_metrics(
        ticker, alert_date,
        claude_analysis=None,
        perplexity_text=None,  # explicit: no time-travel
        fmp_news=fmp_news,
        news_on_or_before=alert_date,
    )
    rubric = score_ep_with_rubric(ticker, extracted, alert_date)
    return {"extracted": extracted, "rubric": rubric, "fmp_n": len(fmp_news)}


async def main():
    print("=" * 95)
    print("B5 — Historical fixture re-validation (DEGRADED extraction: no Perplexity)")
    print("=" * 95)
    print(f"{'ticker':<6} {'date':<12} {'expected':<16} {'composite':<12} {'label':<18} {'match':<6} {'verdict':<10}")
    print("-" * 95)

    matches = 0
    diffs = 0
    not_scored = 0

    for ticker, alert_date, expected in FIXTURES:
        try:
            result = await score_one(ticker, alert_date)
        except Exception as e:
            print(f"{ticker:<6} {alert_date} {expected:<16} ERROR: {e}")
            continue

        rubric = result["rubric"]
        extracted = result["extracted"]
        fmp_n = result.get("fmp_n", 0)
        polygon_n = extracted.get("_polygon_news_count", 0)
        if rubric is None:
            q_rev = "(no q_rev)"
            extraction_quality = extracted.get("extraction_quality", "?")
            print(f"{ticker:<6} {alert_date} {expected:<16} {q_rev:<12} "
                  f"(not scored)        -      safety_net  "
                  f"[xq={extraction_quality}, polygon_n={polygon_n}, fmp_n={fmp_n}]")
            not_scored += 1
            continue

        comp = rubric.get("composite_scaled")
        label = rubric.get("label", "?")
        match = "OK" if label == expected else "DIFF"
        verdict = "DOWNGRADE" if comp is not None and comp < CATALYST_RUBRIC_MIN_COMPOSITE else "PASS"
        if match == "OK":
            matches += 1
        else:
            diffs += 1
        comp_str = f"{comp:>5.1f}/39" if comp is not None else "(none)/39"
        print(f"{ticker:<6} {alert_date} {expected:<16} {comp_str:<12} {label:<18} {match:<6} {verdict:<10} "
              f"[polygon_n={polygon_n}, fmp_n={fmp_n}]")

    print("-" * 95)
    print(f"Summary: {matches} match, {diffs} diff, {not_scored} not_scored "
          f"(of {len(FIXTURES)} fixtures)")
    print()
    print("NOTE: 'DIFF' is expected for some fixtures since extraction is degraded")
    print("(no Perplexity, FMP news may be current-only). Interpret as 'code-path")
    print("sanity surfaced edge cases' not 'gate threshold needs adjustment'.")


if __name__ == "__main__":
    asyncio.run(main())
