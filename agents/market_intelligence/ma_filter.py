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
    """Fetch recent Polygon news and scan for M&A keywords with the
    multi-ticker-tag-bleed discriminator (#88 fix, 2026-05-23).

    Two-path acceptance:

      Path A (title match) — M&A keyword in article TITLE. High specificity:
      title is the article's primary topic; if M&A keyword appears there
      it's almost certainly about *one* of the tagged tickers' M&A activity.
      We accept and let the broader filter graph + downstream
      direction-blindness fixes (#90) handle acquirer-side leaks.

      Path B (description-only match) — M&A keyword in description but NOT
      in title. The article may be tagged with multiple tickers; require:
        (i)  filtering ticker present in article's `insights` array
             (Polygon's per-ticker AI tagging — proxy for "article is
             relevant to this ticker, not just multi-tagged"), AND
        (ii) that ticker's `sentiment_reasoning` text itself contains an
             M&A keyword (proxy for "Polygon's AI thinks this ticker's
             move is M&A-related").

    If `insights` field is missing entirely (Polygon hasn't AI-graded the
    article — rare for recent ≤21d window where Polygon Insights has
    near-100% coverage), Path B SKIPS the article entirely (conservative;
    avoids resurrecting the QBTS-class bug for un-graded articles). Emits
    `polygon_news_insights_missing` audit event for future false-negative
    quantification.

    Loop semantics: when Path B rejects an article (description-only match
    but ticker not in insights or reasoning lacks M&A kw), continue to next
    article. Don't terminate on first rejection.

    Returns the first qualifying headline dict or None.

    Pre-ship backward verification (#88, 2026-05-23): 9 of 9 classified
    historical cases (2 TP + 7 FP from 90d audit) behave as expected
    under this logic. Replay script: scripts/_replay_88_mna_filter_fix.py
    """
    from agents.market_intelligence.collector import get_polygon_news

    items = await get_polygon_news(
        ticker, lookback_days=lookback_days, on_or_before=on_or_before, limit=20
    )
    for item in items:
        title = item.get("title", "")
        description = item.get("description", "")

        title_kw = matches_mna_keywords(title)
        if title_kw:
            # Path A: title match — accept
            return {
                "ticker": ticker,
                "matched_keyword": title_kw,
                "match_path": "title",
                "title": title[:200],
                "published_utc": item.get("published_utc", ""),
                "publisher": item.get("publisher", ""),
            }

        desc_kw = matches_mna_keywords(description)
        if not desc_kw:
            continue  # neither title nor description matched — try next article

        # Path B: description match — verify ticker is article subject
        insights = item.get("insights") or []
        if not insights:
            # Polygon hasn't AI-graded this article. Skip Path B (conservative
            # missing-insights handling per advisor 2026-05-23). Emit audit so
            # we can quantify the false-negative risk over time. Use lazy import
            # to avoid circularity (ma_filter is imported by detectors that
            # also import db).
            try:
                from agents.market_intelligence.db import log_audit_event
                await log_audit_event(
                    "polygon_news_insights_missing",
                    f"{ticker} skipped Path B — no insights field on '{title[:120]}'",
                )
            except Exception:
                pass
            continue

        # Ticker must be in article's insights list (filtering ticker is a
        # subject of Polygon's AI tagging, not just a multi-tag bleed).
        ticker_insight = next(
            (i for i in insights if i.get("ticker") == ticker),
            None,
        )
        if ticker_insight is None:
            continue  # ticker tagged on article but not insighted — QBTS class

        # Ticker's per-ticker sentiment_reasoning must contain an M&A keyword
        # (Polygon's AI thinks THIS ticker's move is M&A-related).
        reasoning = ticker_insight.get("sentiment_reasoning") or ""
        reasoning_kw = matches_mna_keywords(reasoning)
        if not reasoning_kw:
            continue  # ticker insighted but not for M&A reason — MNST/ONDS/INFQ class

        return {
            "ticker": ticker,
            "matched_keyword": desc_kw,
            "match_path": "description+insights",
            "title": title[:200],
            "published_utc": item.get("published_utc", ""),
            "publisher": item.get("publisher", ""),
            "insight_reasoning": reasoning[:200],
            "insight_reasoning_kw": reasoning_kw,
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
