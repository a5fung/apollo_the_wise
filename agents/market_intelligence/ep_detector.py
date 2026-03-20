"""
EP (Episodic Pivot) Detector.

Scans pre-market for gap-up stocks and scores them using the MAGNA53 model
(Pradeep Bonde / Kullamägi methodology).

EP hard filters:
- Gap ≥ 8% vs previous close
- Relative volume ≥ 2x ADV in first 15-20 min

MAGNA53 scoring (0-100):
- Gap magnitude:     20%+ = 25pts, 15%+ = 20pts, 10%+ = 15pts, 8-9% = 10pts
- Catalyst quality:  game-changer = 25pts, strong = 15pts, routine = 0pts
- Relative volume:   5x+ ADV = 15pts, 2-4x = 10pts, 1-2x = 5pts
- Neglect period:    6mo+ base = 15pts, 3mo = 8pts
- Volume conviction: pre-mkt vol ≥90th pct = 5pts, ≥70th = 3pts
- Analyst upgrades:  3+ = 5pts
- Low float:         <50M shares = 5pts
- Market multiplier: Bull regime = 1.2x, Gemini agreement = 1.2x (stack)

Max raw: 95. A 20%+ game-changer gap scores ≥70 before bonuses.
Thresholds: ≥ ep_threshold (regime-dependent) = HIGH, 50-69 = MODERATE, <50 = skip
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import date
from typing import Any, Optional

import anthropic

from agents.market_intelligence.collector import (
    get_snapshot_all,
    get_fmp_profile,
    get_fmp_earnings,
    get_fmp_analyst_ratings,
    get_fmp_news,
    search_news_perplexity,
)
from agents.market_intelligence.db import insert_ep_alert, get_adv_map, get_latest_regime, get_volume_history

logger = logging.getLogger(__name__)

# Hard filters
MIN_GAP_PCT = 8.0
MIN_REL_VOLUME = 2.0
MIN_PREMARKET_SHARES = 25_000  # Absolute minimum — filters micro-float noise
MIN_PREV_CLOSE = 5.0           # Skip sub-$5 stocks — noise, not EPs
MAX_TICKER_LEN = 5             # Skip warrants/units (long symbols like ABCDW)

# Auto-disqualifiers
MAX_EXTENSION_PCT = 50.0   # Skip if already up 50%+ before the gap
EP_COOLDOWN_DAYS = 60       # Skip if this ticker had an EP in last 60 days

# Leveraged/inverse ETFs and broad ETFs — never real EPs
_SKIP_TICKERS = frozenset({
    # Leveraged / inverse
    "TQQQ", "SQQQ", "SPXL", "SPXS", "UPRO", "SDS", "SSO", "QLD", "QID",
    "UDOW", "SDOW", "LABU", "LABD", "SOXL", "SOXS", "TNA", "TZA",
    "FNGU", "FNGD", "TECL", "TECS", "FAS", "FAZ", "NUGT", "DUST",
    "JNUG", "JDST", "GDXD", "ERX", "ERY", "GUSH", "DRIP", "UVXY",
    "SVXY", "VXX", "UVIX", "SVIX", "BOIL", "KOLD", "UCO", "SCO",
    "AGQ", "ZSL", "GLL", "DULL", "UGL", "YANG", "YINN", "CWEB",
    "BRZU", "BZQ", "EDC", "EDZ", "DRN", "DRV", "RETL", "BNKU",
    "MSTZ", "MSTU", "CONL", "TSLL", "NVDL", "NVDS",  # Single-stock leveraged
    # Broad index ETFs
    "SPY", "QQQ", "IWM", "DIA", "VOO", "VTI", "IVV", "RSP",
    # Sector ETFs (not individual stock EPs)
    "XLK", "XLE", "XLF", "XLV", "XLI", "XLB", "XLP", "XLU", "XLY",
    "XLRE", "XLC", "SMH", "IBB", "XBI", "GDX", "GDXJ", "KRE",
})

_claude = None


def _get_claude():
    global _claude
    if _claude is None:
        _claude = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    return _claude


def _get_gemini():
    """Get Gemini client if API key is configured."""
    try:
        from google import genai
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            return None
        return genai.Client(api_key=api_key)
    except ImportError:
        logger.warning("google-genai not installed, skipping Gemini validation")
        return None


_CATALYST_TOOL = {
    "name": "classify_catalyst",
    "description": "Classify the quality of a stock EP catalyst and provide analysis.",
    "input_schema": {
        "type": "object",
        "properties": {
            "quality": {
                "type": "string",
                "enum": ["game_changer", "strong", "routine"],
                "description": (
                    "game_changer: massive earnings beat + guidance raise, FDA approval, "
                    "transformative contract. strong: solid beat + guidance raise, analyst "
                    "upgrade cluster, major partnership. routine: in-line results, no "
                    "company-specific catalyst."
                ),
            },
            "analysis": {
                "type": "string",
                "description": "2-3 sentences on the specific catalyst and classification rationale.",
            },
        },
        "required": ["quality", "analysis"],
    },
}


async def _classify_catalyst_claude(ticker: str, news: list[dict], profile: dict) -> tuple[str, str]:
    """
    Use Claude to classify catalyst quality via structured tool use.
    Returns: (quality, analysis_text)
    quality: "game_changer" | "strong" | "routine"

    Uses tool_choice to guarantee schema-valid output — no string parsing,
    no silent fallback to "routine" on format deviations.
    """
    news_text = "\n".join([f"- {n.get('title', '')} {n.get('text', '')[:200]}" for n in news[:5]])
    company_desc = profile.get("description", "")[:300]

    prompt = f"""You are analyzing a stock gap-up for EP (Episodic Pivot) trading.
This stock is gapping up significantly in pre-market. Your job is to identify the catalyst.

Stock: {ticker}
Company: {profile.get('companyName', '')} — {profile.get('sector', '')}
Description: {company_desc}

Recent news (may include earnings announcements, guidance, contracts, upgrades):
{news_text or "No news found — check if this is an after-hours earnings release."}

IMPORTANT: If the stock is gapping 8%+ on high volume, there is almost certainly a catalyst.
Look for: earnings releases, guidance raises, FDA decisions, major contracts, analyst upgrades.
An earnings beat with guidance raise on a neglected stock = game_changer or strong.
Only use routine if you've confirmed there is genuinely no company-specific catalyst."""

    try:
        response = _get_claude().messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            tools=[_CATALYST_TOOL],
            tool_choice={"type": "tool", "name": "classify_catalyst"},
            messages=[{"role": "user", "content": prompt}],
        )
        tool_block = next(b for b in response.content if b.type == "tool_use")
        result = tool_block.input
        return result["quality"], result["analysis"]
    except Exception as e:
        logger.error(f"Claude catalyst classification failed for {ticker}: {e}")
        return "routine", "Classification failed — treating as routine."


async def _validate_catalyst_gemini(ticker: str, news_summary: str) -> Optional[str]:
    """
    Use Gemini to cross-validate catalyst quality.
    Returns "game_changer", "strong", "routine", or None if unavailable.
    """
    gemini = _get_gemini()
    if not gemini:
        return None

    prompt = f"""For stock {ticker}, classify this catalyst as GAME_CHANGER, STRONG, or ROUTINE:
{news_summary}

Respond with ONLY the classification word."""

    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: gemini.models.generate_content(model="gemini-2.0-flash", contents=prompt)
        )
        text = response.text.strip().upper()
        if "GAME_CHANGER" in text or "GAME CHANGER" in text:
            return "game_changer"
        elif "STRONG" in text:
            return "strong"
        else:
            return "routine"
    except Exception as e:
        logger.warning(f"Gemini validation failed for {ticker}: {e}")
        return None


def _volume_percentile(today_volume: float, adv_history: list[float]) -> float:
    """
    Percentile rank of today's pre-market volume vs the stock's historical ADV values.
    Returns 0-100.

    Interpretation: a score of 80 means today's pre-market volume already
    exceeds 80% of this stock's typical full-day average volumes — genuine
    conviction, not thin-float RVOL inflation.
    """
    if not adv_history or today_volume <= 0:
        return 50.0  # unknown — neutral
    below = sum(1 for v in adv_history if today_volume > v)
    return round(below / len(adv_history) * 100, 1)


def _score_ep(
    gap_pct: float,
    rel_volume: float,
    catalyst_quality: str,
    profile: dict,
    analyst_upgrades: int,
    regime_multiplier: float,
    vol_percentile: float = 50.0,
) -> tuple[float, dict]:
    """
    Calculate MAGNA53 EP score (0-100 before multiplier).
    Returns: (final_score, score_breakdown)

    Weights emphasize the two strongest EP signals: gap size + catalyst quality.
    A 20%+ game-changer gap should score ≥70 on its own before bonuses.
    """
    breakdown = {}

    # Gap magnitude (max 25) — scaled: bigger gaps = stronger signal
    if gap_pct >= 20:
        breakdown["gap"] = 25
    elif gap_pct >= 15:
        breakdown["gap"] = 20
    elif gap_pct >= 10:
        breakdown["gap"] = 15
    elif gap_pct >= 8:
        breakdown["gap"] = 10
    else:
        breakdown["gap"] = 0

    # Relative volume (max 15)
    if rel_volume >= 5:
        breakdown["rel_volume"] = 15
    elif rel_volume >= 2:
        breakdown["rel_volume"] = 10
    elif rel_volume >= 1:
        breakdown["rel_volume"] = 5
    else:
        breakdown["rel_volume"] = 0

    # Catalyst quality (max 25) — the single most important EP signal
    if catalyst_quality == "game_changer":
        breakdown["catalyst"] = 25
    elif catalyst_quality == "strong":
        breakdown["catalyst"] = 15
    else:
        breakdown["catalyst"] = 0

    # Low float bonus (max 5)
    float_shares = profile.get("floatShares", 0) or 0
    if float_shares > 0 and float_shares < 50_000_000:
        breakdown["float"] = 5
    else:
        breakdown["float"] = 0

    # Analyst upgrades (max 5)
    breakdown["analyst"] = min(analyst_upgrades * 2, 5) if analyst_upgrades >= 3 else 0

    # Neglect period — approximate from 52-week range
    # If price < 70% of 52-week high before the gap, it was neglected
    price = profile.get("price", 0) or 0
    high_52w = profile.get("52WeekHigh", price) or price
    if high_52w > 0 and price > 0:
        pct_of_high = price / high_52w
        if pct_of_high < 0.5:
            breakdown["neglect"] = 15  # 6mo+ base
        elif pct_of_high < 0.7:
            breakdown["neglect"] = 8   # 3mo base
        else:
            breakdown["neglect"] = 0
    else:
        breakdown["neglect"] = 0

    # Volume conviction: pre-market volume vs stock's own historical ADV distribution (max 5)
    if vol_percentile >= 90:
        breakdown["vol_conviction"] = 5
    elif vol_percentile >= 70:
        breakdown["vol_conviction"] = 3
    else:
        breakdown["vol_conviction"] = 0

    raw_score = sum(breakdown.values())

    # Conviction floor: massive gap + strong catalyst = minimum 75 raw score
    # A 15%+ game_changer or 20%+ strong gap is inherently high-conviction
    if gap_pct >= 15 and catalyst_quality == "game_changer":
        raw_score = max(raw_score, 75)
        breakdown["conviction_floor"] = max(0, 75 - sum(v for k, v in breakdown.items() if k != "conviction_floor"))
    elif gap_pct >= 20 and catalyst_quality == "strong":
        raw_score = max(raw_score, 70)
        breakdown["conviction_floor"] = max(0, 70 - sum(v for k, v in breakdown.items() if k != "conviction_floor"))

    final_score = min(raw_score * regime_multiplier, 100)
    return round(final_score, 1), breakdown


async def run_ep_scan(prev_close_date: str | None = None) -> list[dict]:
    """
    Run pre-market EP scan.
    Returns list of EP candidates with scores.

    prev_close_date: "YYYY-MM-DD" of the last trading day
    """
    today = date.today()
    today_str = today.strftime("%Y-%m-%d")
    prev_date = prev_close_date or today_str  # fallback

    # Get regime for threshold adjustment
    regime = await get_latest_regime()
    regime_label = regime.get("regime", "Unknown") if regime else "Unknown"
    ep_threshold = regime.get("ep_threshold", 70) if regime else 70
    regime_multiplier = 1.2 if regime_label == "Bull" else 1.0

    # Get stored ADV map (from last RS run)
    adv_map = await get_adv_map(prev_date)

    logger.info(f"EP scan: regime={regime_label}, threshold={ep_threshold}")

    # Fetch all snapshots (1 Polygon call)
    snapshots = await get_snapshot_all()
    if not snapshots:
        logger.warning("No snapshot data — market may not be open yet")
        return []

    # Find gap candidates
    candidates = []
    for ticker, snap in snapshots.items():
        try:
            # Skip warrants, units, non-standard symbols, and ETFs
            if len(ticker) > MAX_TICKER_LEN or ticker in _SKIP_TICKERS or "." in ticker:
                continue

            prev_close = snap.get("prevDay", {}).get("c", 0)
            if not prev_close or prev_close < MIN_PREV_CLOSE:
                continue

            # Current price: min.c (latest minute bar, includes pre/post-market)
            # → day.o (regular session open) → lastTrade.p (fallback)
            # Pre-market: min.c is the only field that updates before 9:30 open
            current_price = (
                snap.get("min", {}).get("c")
                or snap.get("day", {}).get("o")
                or snap.get("lastTrade", {}).get("p", 0)
            )
            if not current_price:
                continue

            gap_pct = (current_price - prev_close) / prev_close * 100
            if gap_pct < MIN_GAP_PCT:
                continue

            # Volume: day.v for regular session, min.av for accumulated (includes pre-mkt)
            today_volume = snap.get("day", {}).get("v", 0) or snap.get("min", {}).get("av", 0) or 0
            adv = adv_map.get(ticker)
            if not adv:
                # Fallback: previous day's volume from snapshot (works for all tickers)
                adv = snap.get("prevDay", {}).get("v") or None
            rel_volume = (today_volume / adv) if adv and adv > 0 else None

            candidates.append({
                "ticker": ticker,
                "prev_close": prev_close,
                "current_price": current_price,
                "gap_pct": round(gap_pct, 2),
                "today_volume": today_volume,
                "adv": adv,
                "rel_volume": round(rel_volume, 2) if rel_volume else None,
            })
        except Exception:
            continue

    # Sort by gap size descending — score the biggest movers first
    candidates.sort(key=lambda c: c["gap_pct"], reverse=True)
    logger.info(f"Gap candidates ≥{MIN_GAP_PCT}%: {len(candidates)}"
                + (f" (top: {candidates[0]['ticker']} {candidates[0]['gap_pct']:.1f}%)" if candidates else ""))
    if not candidates:
        return []

    # Batch-fetch volume history for all candidates (one DB query)
    candidate_tickers = [c["ticker"] for c in candidates]
    vol_history_map = await get_volume_history(candidate_tickers)

    # Score each candidate (rate-limited FMP calls)
    results = []
    for c in candidates[:20]:  # Cap at 20 to stay within FMP call budget
        ticker = c["ticker"]
        rel_volume = c.get("rel_volume") or 0

        # Hard filter: rel volume (skip if no ADV data available — can't verify)
        if c.get("adv") and rel_volume < MIN_REL_VOLUME:
            logger.debug(f"Skip {ticker}: rel_volume {rel_volume:.1f}x < {MIN_REL_VOLUME}x")
            continue

        # Hard filter: absolute pre-market volume (filters micro-float noise)
        if c["today_volume"] < MIN_PREMARKET_SHARES:
            logger.debug(f"Skip {ticker}: pre-market volume {c['today_volume']:,} < {MIN_PREMARKET_SHARES:,} shares")
            continue

        # Volume conviction percentile
        vol_pct = _volume_percentile(c["today_volume"], vol_history_map.get(ticker, []))

        # Fetch all external data concurrently
        profile, fmp_news, ratings, perplexity_answer = await asyncio.gather(
            get_fmp_profile(ticker),
            get_fmp_news(ticker),
            get_fmp_analyst_ratings(ticker),
            search_news_perplexity(f"What caused {ticker} stock to gap up? Latest catalyst and news.", recency="week"),
        )
        await asyncio.sleep(0.5)  # Single FMP cooldown after concurrent burst
        upgrades_30d = sum(1 for r in ratings if r.get("analystRatingsStrongBuy", 0) > 0)

        # Combine news sources — Perplexity synthesized answer + yfinance headlines
        all_news = fmp_news + ([{"title": "Perplexity synthesis", "text": perplexity_answer}]
                                if perplexity_answer else [])
        news_summary = perplexity_answer[:500] if perplexity_answer else "\n".join(
            [n.get("title", "") for n in fmp_news[:3]]
        )

        # Claude + Gemini in parallel — cancel Gemini if catalyst is routine
        claude_task = asyncio.create_task(_classify_catalyst_claude(ticker, all_news, profile))
        gemini_task = asyncio.create_task(_validate_catalyst_gemini(ticker, news_summary))

        catalyst_quality, claude_analysis = await claude_task

        # Skip routine catalysts outright
        if catalyst_quality == "routine" and c["gap_pct"] < 12:
            gemini_task.cancel()
            logger.info(f"Skip {ticker}: routine catalyst, gap {c['gap_pct']:.1f}%")
            continue

        gemini_quality = await gemini_task

        # Agreement logic
        confidence_multiplier = 1.0
        if gemini_quality and gemini_quality == catalyst_quality:
            confidence_multiplier = 1.2
            logger.info(f"{ticker}: Claude+Gemini agree on {catalyst_quality} → 1.2x confidence")
        elif gemini_quality and gemini_quality != catalyst_quality:
            logger.info(f"{ticker}: Claude={catalyst_quality}, Gemini={gemini_quality} → disagreement, no boost")

        # Score
        ep_score, breakdown = _score_ep(
            gap_pct=c["gap_pct"],
            rel_volume=rel_volume,
            catalyst_quality=catalyst_quality,
            profile=profile,
            analyst_upgrades=upgrades_30d,
            regime_multiplier=regime_multiplier * confidence_multiplier,
            vol_percentile=vol_pct,
        )

        if ep_score < 50:
            logger.info(f"Skip {ticker}: score {ep_score} < 50 (gap={c['gap_pct']:.1f}% catalyst={catalyst_quality} breakdown={breakdown})")
            continue

        tier = "HIGH" if ep_score >= ep_threshold else "MODERATE"

        result = {
            **c,
            "ep_score": ep_score,
            "score_tier": tier,
            "catalyst_quality": catalyst_quality,
            "catalyst": news_summary[:500],
            "claude_analysis": claude_analysis,
            "gemini_validation": gemini_quality,
            "confidence_multiplier": confidence_multiplier,
            "vol_percentile": vol_pct,
            "score_breakdown": breakdown,
            "alert_date": today,
        }
        results.append(result)

        # Store in DB
        await insert_ep_alert({
            "ticker": ticker,
            "alert_date": today,
            "gap_pct": c["gap_pct"],
            "rel_volume": rel_volume,
            "ep_score": ep_score,
            "score_tier": tier,
            "catalyst": news_summary[:500],
            "catalyst_quality": catalyst_quality,
            "claude_analysis": claude_analysis,
            "gemini_validation": gemini_quality,
            "confidence_multiplier": confidence_multiplier,
            "vol_percentile": vol_pct,
        })

        logger.info(f"EP alert: {ticker} gap={c['gap_pct']:.1f}% score={ep_score} tier={tier}")

    results.sort(key=lambda r: r["ep_score"], reverse=True)
    return results
