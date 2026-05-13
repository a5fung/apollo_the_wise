"""Single-source M&A / buyout / take-private filter.

Used by every detector that emits actionable trade ideas (EP, flag, 9M, etc.)
to reject names whose momentum is structurally capped by an announced deal —
price is pinned at the deal value, no further gain available.

Two layers:

1. **Catalyst keyword scan** — `matches_mna_keywords(text)` walks `_MNA_KEYWORDS`
   over any text source. Drives Claude/Perplexity catalyst summaries on EP, and
   raw Polygon news titles on flag/9M (which don't run an LLM catalyst pass).

2. **Polygon news backstop** — when Perplexity hedges ("no specific news") and
   Claude grades `routine`, the keyword scan has no text to match. AVNS 5/4
   surfaced this gap: Polygon had the 4/14 "Avanos To Go Private" headline the
   whole time. Fetching Polygon titles directly closes the coverage gap.

Future Layer 3 (filed as data-gated review `flag_ma_pin_filter`): deal-pin
price signature — median daily (H-L)/close < ~0.3% across 7+ of 10 sessions.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Iterable, Optional

logger = logging.getLogger(__name__)

# Keep this list as the single canonical source — every detector reads from here.
#
# Target-direction only: every keyword below should imply the ticker is the
# TARGET of a deal, not the acquirer. Bare "acquire" / "acquisition" were
# removed 2026-05-13 after NBIS (acquired Eigen AI for $643M; NBIS = buyer)
# was wrongly filtered. 90d backtest: 13 acquirer-side FPs vs 2 real targets
# already covered by Claude `catalyst_quality='mna'` (EBAY) or `"take-private"`
# (WEN). See ma_filter.py change log + magna53_ep.md 2026-05-13.
_MNA_KEYWORDS: tuple[str, ...] = (
    "buyout", "takeover", "merger", "bought by",
    "being acquired", "definitive agreement", "tender offer", "going private",
    "taken private", "to go private", "strategic transaction", "merger agreement",
    "to be acquired", "all-cash buyout", "halper sadeh",  # shareholder-investigation firm; always follows M&A
    "take-private", "private deal for",
)


def matches_mna_keywords(text: Optional[str]) -> Optional[str]:
    """Return the first M&A keyword found in `text` (lowercased), else None."""
    if not text:
        return None
    low = text.lower()
    for kw in _MNA_KEYWORDS:
        if kw in low:
            return kw
    return None


def matches_mna_in_any(texts: Iterable[Optional[str]]) -> Optional[tuple[str, int]]:
    """Scan multiple text blobs; return (keyword, index_of_first_hit) or None.

    `index_of_first_hit` lets the caller report which source matched (Claude
    analysis vs Perplexity summary vs Polygon title #3, etc.) for telemetry.
    """
    for i, t in enumerate(texts):
        kw = matches_mna_keywords(t)
        if kw:
            return kw, i
    return None


async def polygon_news_has_mna_headline(
    ticker: str,
    *,
    lookback_days: int = 14,
    on_or_before: Optional[date] = None,
) -> Optional[dict]:
    """Fetch recent Polygon news titles and scan for M&A keywords.

    Returns the first matching headline dict ({title, kw, published_utc, ...})
    or None. Local import of `get_polygon_news` to avoid module-load circularity
    (collector imports nothing from this file, but better safe).
    """
    from agents.market_intelligence.collector import get_polygon_news

    items = await get_polygon_news(
        ticker, lookback_days=lookback_days, on_or_before=on_or_before, limit=20
    )
    for item in items:
        kw = matches_mna_keywords(item.get("title")) or matches_mna_keywords(item.get("description"))
        if kw:
            return {
                "ticker": ticker,
                "matched_keyword": kw,
                "title": item.get("title", "")[:200],
                "published_utc": item.get("published_utc", ""),
                "publisher": item.get("publisher", ""),
            }
    return None


async def is_likely_ma(
    ticker: str,
    *,
    catalyst_quality: Optional[str] = None,
    catalyst_texts: Optional[list[Optional[str]]] = None,
    check_polygon: bool = True,
    polygon_lookback_days: int = 14,
    on_or_before: Optional[date] = None,
) -> tuple[bool, Optional[dict]]:
    """Single-call M&A check used by all detectors.

    Sources, in order of cost (cheap → expensive):
      1. `catalyst_quality == 'mna'` (Claude classifier verdict; EP only)
      2. Keyword scan over `catalyst_texts` (Claude analysis, news_summary, …)
      3. Polygon news headlines (`check_polygon=True`)

    Returns (is_mna, telemetry_dict). The telemetry dict identifies which
    source fired so audit events can distinguish "Claude flagged it" from
    "we caught it via Polygon despite Perplexity hedging".
    """
    if catalyst_quality == "mna":
        return True, {
            "source": "claude_classifier",
            "ticker": ticker,
            "catalyst_quality": catalyst_quality,
        }

    if catalyst_texts:
        hit = matches_mna_in_any(catalyst_texts)
        if hit:
            kw, idx = hit
            return True, {
                "source": f"keyword_in_text_{idx}",
                "ticker": ticker,
                "matched_keyword": kw,
            }

    if check_polygon:
        polygon_hit = await polygon_news_has_mna_headline(
            ticker,
            lookback_days=polygon_lookback_days,
            on_or_before=on_or_before,
        )
        if polygon_hit:
            return True, {
                "source": "polygon_news",
                **polygon_hit,
            }

    return False, None
