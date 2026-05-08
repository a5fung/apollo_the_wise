"""
EP (Episodic Pivot) Detector.

Scans pre-market for gap-up stocks and scores them using the MAGNA53 model
(Pradeep Bonde / Kullamägi methodology).

Hard filters (applied BEFORE scoring — stocks that fail never reach the DB or briefing):
- Gap ≥ 8% vs previous close
- Previous close ≥ $5, previous day volume ≥ 50K shares
- Post-open only: relative volume ≥ 2x ADV. Pre-market: only 25K share floor (pre-market vol is structurally tiny vs full-day ADV even on huge news days — gap + catalyst carry the signal)
- Pre-trade quality: ADV dollar volume ≥ $1M, ATR% ≤ 15%, market cap ≥ $500M
  (same check_filters used by backtester/tracker — single source of truth)
- Extension: skip if already up ≥ 50% in last 5 trading days
- Cooldown: skip if this ticker had an EP alert in last 60 days
- No M&A/buyout catalysts

MAGNA53 scoring (0-100):
- Gap magnitude:     20%+ = 25pts, 15%+ = 20pts, 10%+ = 15pts, 8-9% = 10pts
- Catalyst quality:  game-changer = 25pts, strong = 15pts, routine = 0pts
- Relative volume:   5x+ ADV = 15pts, 2-4x = 10pts, 1-2x = 5pts
- Neglect period:    6mo+ base = 15pts, 3mo = 8pts
- Volume conviction: pre-mkt vol ≥90th pct = 5pts, ≥70th = 3pts
- Analyst upgrades:  3+ = 5pts
- Low float:         <50M shares = 5pts
- Market multiplier: Bull regime = 1.2x, Perplexity agreement = 1.2x (stack)

Max raw: 95. A 20%+ game-changer gap scores ≥70 before bonuses.
Thresholds: ≥ ep_threshold (regime-dependent) = HIGH, 50-69 = MODERATE, <50 = skip
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
from datetime import date, datetime, timedelta
from typing import Any, Optional

import anthropic

from agents.market_intelligence.collector import et_today
from agents.market_intelligence.collector import (
    get_snapshot_all,
    get_index_history,
    get_fmp_profile,
    get_fmp_earnings,
    get_fmp_analyst_ratings,
    get_fmp_news,
    search_news_perplexity,
)
from agents.market_intelligence.constants import SKIP_TICKERS
from agents.market_intelligence.db import insert_ep_alert, get_adv_map, get_latest_regime, get_volume_history, get_pool, log_ep_scan_candidates, log_audit_event
from agents.market_intelligence.backtester.filters import check_filters
from agents.market_intelligence.minute_volume import (
    compute_rvol_at_time,
    MIN_PM_RVOL,
    MIN_SESSION_RVOL,
    MIN_BASELINE_N_FOR_GATE,
)
from agents.market_intelligence.broker.skip_reasons import (
    FILTER_PM_RVOL_TOO_LOW,
    FILTER_SESSION_RVOL_TOO_LOW,
)
from agents.market_intelligence.ma_filter import is_likely_ma
from agents.market_intelligence.earnings_calendar import is_earnings_day

logger = logging.getLogger(__name__)

# Hard filters
MIN_GAP_PCT = 8.0
MIN_PREMARKET_SHARES = 25_000  # Absolute minimum — filters micro-float noise
MIN_PREV_CLOSE = 5.0           # Skip sub-$5 stocks — noise, not EPs
MAX_TICKER_LEN = 5             # Skip warrants/units (long symbols like ABCDW)
MIN_PREV_DAY_VOLUME = 50_000   # Skip illiquid stocks — stale quotes create phantom gaps

# Auto-disqualifiers (hard filters — applied before scoring)
MAX_EXTENSION_PCT = 50.0   # Skip if already up 50%+ in last 5 trading days before the gap
EP_COOLDOWN_DAYS = 60       # Skip if this ticker had an EP alert in last 60 days

# Leveraged/inverse ETFs and broad ETFs — never real EPs
_SKIP_TICKERS = SKIP_TICKERS

# Catalyst cache — FMP + Claude + Perplexity results for today.
# A stock oscillating near the 15% conviction threshold (e.g. BE at 13-15%)
# gets re-scored every 5 min. The catalyst doesn't change; skip the API calls.
# Keys: ticker → (catalyst_quality, confidence_multiplier, news_summary, claude_analysis)
# Resets automatically when the calendar date changes.
_catalyst_cache: dict[str, tuple[str, float, str, str]] = {}
_catalyst_cache_date: "date | None" = None

# Per-day audit dedupe: keys (ticker, date, event_type). EP scan runs every 5 min
# from 7:00–10:00 ET (~36 ticks); without dedup, the same ticker emits ~36 rows
# of `earnings_override_no_match` / `tape_conviction_shadow` per day.
_audit_dedupe: set[tuple[str, "date", str]] = set()
_audit_dedupe_date: "date | None" = None


def _audit_dedupe_check(ticker: str, scan_date: "date", event: str) -> bool:
    """Returns True if (ticker, date, event) hasn't been logged this session."""
    global _audit_dedupe, _audit_dedupe_date
    if _audit_dedupe_date != scan_date:
        _audit_dedupe.clear()
        _audit_dedupe_date = scan_date
    key = (ticker, scan_date, event)
    if key in _audit_dedupe:
        return False
    _audit_dedupe.add(key)
    return True

_claude = None
# Cap concurrent Anthropic calls — earnings days can gap 30+ stocks simultaneously,
# and unbounded parallel requests → 429s → degraded catalyst classification.
_ANTHROPIC_SEMAPHORE = asyncio.Semaphore(5)


def _get_claude():
    global _claude
    if _claude is None:
        _claude = anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    return _claude


async def _compute_adv_from_polygon(ticker: str, trade_date: date, days: int = 20) -> Optional[float]:
    """Fetch recent daily bars from Polygon and compute 20-day median daily volume.
    Used for EP candidates not in the RS universe.
    Uses median (not mean) — consistent with get_adv_from_daily_closes in db.py."""
    from_date = (trade_date - timedelta(days=days * 2)).strftime("%Y-%m-%d")  # fetch extra for weekends/holidays
    to_date = (trade_date - timedelta(days=1)).strftime("%Y-%m-%d")  # exclude today
    bars = await get_index_history(ticker, from_date, to_date)
    volumes = sorted(b["v"] for b in bars if "v" in b and b["v"] > 0)
    if len(volumes) < 5:
        return None  # not enough data
    recent = volumes[-days:] if len(volumes) > days else volumes
    # Median: immune to single-day volume spikes that would inflate mean
    mid = len(recent) // 2
    if len(recent) % 2 == 1:
        return float(recent[mid])
    return float((recent[mid - 1] + recent[mid]) / 2)


_CATALYST_TOOL = {
    "name": "classify_catalyst",
    "description": "Classify the quality of a stock EP catalyst and provide analysis.",
    "input_schema": {
        "type": "object",
        "properties": {
            "quality": {
                "type": "string",
                "enum": ["game_changer", "strong", "routine", "mna"],
                "description": (
                    "game_changer: massive earnings beat + guidance raise, FDA approval, "
                    "transformative contract. strong: solid beat + guidance raise, analyst "
                    "upgrade cluster, major partnership. routine: in-line results, no "
                    "company-specific catalyst. mna: merger, acquisition, buyout, takeover, "
                    "going-private, tender offer, or any deal where the company is being acquired — "
                    "price is capped at deal value, no momentum trade possible."
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
    quality: "game_changer" | "strong" | "routine" | "mna"

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
{news_text or "No news found."}

IMPORTANT RULES:
1. Look for: earnings releases, guidance raises, FDA decisions, major contracts, analyst upgrades.
2. An earnings beat with guidance raise on a neglected stock = game_changer or strong.
3. If the catalyst is a MERGER, ACQUISITION, BUYOUT, TAKEOVER, TENDER OFFER, GOING-PRIVATE, or any
   deal where the company is being acquired — classify as "mna". This is a hard skip: price is capped
   at deal value, there is no momentum trade. Keywords: "definitive agreement", "to be acquired",
   "tender offer", "going private", "taken private", "strategic transaction", "buyout", "merger agreement".

CRITICAL — VERIFY THE CATALYST IS REAL:
- If the news text mentions "earnings" or "quarterly results" but does NOT include specific numbers
  (revenue, EPS, guidance figures), the catalyst is likely FABRICATED. Classify as "routine".
- If the news is vague, generic, or reads like a summary with no specific details (no dates, no
  numbers, no named sources), classify as "routine" — the news source may have hallucinated.
- If none of the news items clearly explain WHY the stock gapped, classify as "routine".
- Penny stocks, biotechs with no revenue, and SPACs frequently gap on low-quality catalysts
  (press releases, conference presentations, speculative articles). Be skeptical — classify as "routine"
  unless the catalyst is concrete and verifiable.
- Do NOT assume earnings occurred just because news mentions "earnings" — look for actual reported
  numbers (EPS beat/miss, revenue figures, guidance).

In your analysis, state the SPECIFIC catalyst clearly. If you cannot identify a concrete, verifiable
catalyst, say so explicitly."""

    try:
        async with _ANTHROPIC_SEMAPHORE:
            for attempt in range(2):
                try:
                    response = await _get_claude().messages.create(
                        model="claude-haiku-4-5-20251001",
                        max_tokens=300,
                        tools=[_CATALYST_TOOL],
                        tool_choice={"type": "tool", "name": "classify_catalyst"},
                        messages=[{"role": "user", "content": prompt}],
                    )
                    break
                except anthropic.RateLimitError:
                    if attempt == 1:
                        raise
                    from agents.market_intelligence.db import log_audit_event
                    await log_audit_event("anthropic_rate_limited", ticker, "retrying ep catalyst")
                    await asyncio.sleep(2 + random.random() * 3)
        tool_block = next(b for b in response.content if b.type == "tool_use")
        result = tool_block.input
        return result["quality"], result["analysis"]
    except Exception as e:
        logger.error(f"Claude catalyst classification failed for {ticker}: {e}")
        return "routine", "Classification failed — treating as routine."


async def _validate_catalyst_perplexity(ticker: str, news_summary: str) -> Optional[str]:
    """
    Use Perplexity Sonar to cross-validate catalyst quality.
    Returns "game_changer", "strong", "routine", or None if unavailable.
    """
    import httpx

    api_key = os.environ.get("PERPLEXITY_API_KEY")
    if not api_key:
        return None

    prompt = f"""For stock {ticker}, classify this catalyst as GAME_CHANGER, STRONG, or ROUTINE:
{news_summary}

Respond with ONLY the classification word."""

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                "https://api.perplexity.ai/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": "sonar",
                    "messages": [
                        {"role": "system", "content": "You classify stock catalysts. Respond with exactly one word: GAME_CHANGER, STRONG, or ROUTINE."},
                        {"role": "user", "content": prompt},
                    ],
                    "return_citations": False,
                },
            )
            r.raise_for_status()
            text = r.json()["choices"][0]["message"]["content"].strip().upper()
        if "GAME_CHANGER" in text or "GAME CHANGER" in text:
            return "game_changer"
        elif "STRONG" in text:
            return "strong"
        else:
            return "routine"
    except Exception as e:
        logger.warning(f"Perplexity validation failed for {ticker}: {e}")
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
    prior_3m_change: float | None = None,
    projected_vol_multiple: float | None = None,
) -> tuple[float, dict]:
    """
    Calculate MAGNA53 EP score (0-100 before multiplier).
    Returns: (final_score, score_breakdown)

    Weights emphasize the two strongest EP signals: gap size + catalyst quality.
    A 20%+ game-changer gap should score ≥70 on its own before bonuses.

    projected_vol_multiple: open intensity — raw_rvol * (390 / min_since_open).
    Measures how many times above the normal rate-for-this-time the stock is trading.
    Linear extrapolation overstates final daily RVOL (opening minutes are always dense),
    but correctly rewards early institutional conviction. Pre-market: raw RVOL used instead.
    """
    breakdown = {}

    # Gap magnitude (max 15) — scaled: bigger gaps = stronger signal
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

    # Volume intensity (max 15)
    # Post-open: use projected daily multiple (pace-normalised) — 10x projected at 9:35
    # is Godzilla volume, very different from 10x raw at 2pm.
    # Pre-market: use raw RVOL — no intraday projection possible.
    vol_signal = projected_vol_multiple if projected_vol_multiple is not None else rel_volume
    if vol_signal >= 10:
        breakdown["rel_volume"] = 15
    elif vol_signal >= 5:
        breakdown["rel_volume"] = 12
    elif vol_signal >= 3:
        breakdown["rel_volume"] = 10
    elif vol_signal >= 2:
        breakdown["rel_volume"] = 7
    else:
        breakdown["rel_volume"] = 0

    # Catalyst quality (max 25) — the single most important EP signal
    # "mna" should never reach scoring (hard-filtered above), but treat as 0 if it does
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

    # Prior momentum penalty — Qullamaggie: "best if stock has not rallied past 3-6 months"
    if prior_3m_change is not None:
        if prior_3m_change >= 50:
            breakdown["prior_momentum"] = -25
        elif prior_3m_change >= 30:
            breakdown["prior_momentum"] = -15
        else:
            breakdown["prior_momentum"] = 0
    else:
        breakdown["prior_momentum"] = 0

    raw_score = sum(breakdown.values())

    # Conviction floor: massive gap + quality catalyst = high-conviction regardless
    # of secondary factors. The gap itself is evidence of institutional conviction.
    # 20%+ strong = same floor as 15%+ game_changer (market voted with its feet)
    # 10-15% game_changer: floor 60 → MODERATE at minimum; fires HIGH in Bull w/ Gemini
    if gap_pct >= 15 and catalyst_quality == "game_changer":
        raw_score = max(raw_score, 80)
        breakdown["conviction_floor"] = max(0, 80 - sum(v for k, v in breakdown.items() if k != "conviction_floor"))
    elif gap_pct >= 20 and catalyst_quality == "strong":
        raw_score = max(raw_score, 80)
        breakdown["conviction_floor"] = max(0, 80 - sum(v for k, v in breakdown.items() if k != "conviction_floor"))
    elif gap_pct >= 15 and catalyst_quality == "strong":
        raw_score = max(raw_score, 70)
        breakdown["conviction_floor"] = max(0, 70 - sum(v for k, v in breakdown.items() if k != "conviction_floor"))
    elif gap_pct >= 10 and catalyst_quality == "game_changer":
        raw_score = max(raw_score, 60)
        breakdown["conviction_floor"] = max(0, 60 - sum(v for k, v in breakdown.items() if k != "conviction_floor"))

    final_score = min(raw_score * regime_multiplier, 100)
    return round(final_score, 1), breakdown


async def run_ep_scan(prev_close_date: str | None = None) -> list[dict]:
    """
    Run pre-market EP scan.
    Returns list of EP candidates with scores.

    prev_close_date: "YYYY-MM-DD" of the last trading day
    """
    today = et_today()
    today_str = today.strftime("%Y-%m-%d")
    prev_date = prev_close_date or today_str  # fallback

    # Get regime for threshold adjustment
    regime = await get_latest_regime()
    regime_label = regime.get("regime", "Unknown") if regime else "Unknown"
    ep_threshold = regime.get("ep_threshold", 70) if regime else 70
    regime_multiplier = 1.2 if regime_label == "Bull" else 1.0

    # Get stored ADV map (from last RS run)
    adv_map = await get_adv_map(prev_date)

    # Authoritative ETF/non-stock filter from security_types table.
    # _SKIP_TICKERS catches known leveraged ETFs fast; this catches anything
    # classified as non-common-stock in our reference data (ETF, ETP, ETPT, etc.).
    _non_stock_tickers: set[str] = set()
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT ticker FROM mi_security_types WHERE security_type NOT IN ('CS', 'ADRC')"
            )
        _non_stock_tickers = {r["ticker"] for r in rows}
        logger.info(f"EP scan: {len(_non_stock_tickers)} non-stock tickers loaded from security_types")
    except Exception as e:
        logger.warning(f"EP scan: could not load security_types ({e}) — relying on SKIP_TICKERS only")

    logger.info(f"EP scan: regime={regime_label}, threshold={ep_threshold}")

    # Minutes since market open — used for projected volume calculation post-open
    from agents.market_intelligence.collector import _ET
    now_et = datetime.now(_ET)
    _SESSION_MINUTES = 390  # 6.5-hour regular session
    if now_et.hour > 9 or (now_et.hour == 9 and now_et.minute >= 30):
        _minutes_since_open = max(1, (now_et.hour - 9) * 60 + (now_et.minute - 30))
    else:
        _minutes_since_open = None  # pre-market — no projection

    # Fetch all snapshots (1 Polygon call)
    snapshots = await get_snapshot_all()
    if not snapshots:
        logger.warning("No snapshot data — market may not be open yet")
        return []

    # Find gap candidates
    candidates = []
    for ticker, snap in snapshots.items():
        try:
            # Skip warrants, units, non-standard symbols, ETFs, and leveraged products
            if len(ticker) > MAX_TICKER_LEN or ticker in _SKIP_TICKERS or "." in ticker:
                continue
            if ticker in _non_stock_tickers:
                continue

            prev_close = snap.get("prevDay", {}).get("c", 0)
            if not prev_close or prev_close < MIN_PREV_CLOSE:
                continue

            # Skip illiquid stocks — stale/erroneous quotes create phantom gaps
            prev_volume = snap.get("prevDay", {}).get("v", 0) or 0
            if prev_volume < MIN_PREV_DAY_VOLUME:
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
            # prevDay.v as temporary placeholder — proper 20-day ADV computed below for non-universe stocks
            adv_source = "rs_universe" if adv else "pending"
            if not adv:
                adv = snap.get("prevDay", {}).get("v") or None

            raw_rvol = round((today_volume / adv), 2) if adv and adv > 0 else None
            # Open intensity: projected full-day RVOL = raw_rvol * (390 / min_elapsed)
            # Gate: only project after 15 minutes (9:45 AM). The opening 15 minutes are
            # structurally dense — every stock shows 10-30x projected RVOL at 9:31 AM
            # regardless of real institutional interest. Before the gate, use raw RVOL.
            open_intensity = None
            if raw_rvol is not None and _minutes_since_open and today_volume > 0:
                if _minutes_since_open >= 15:
                    open_intensity = round(raw_rvol * (_SESSION_MINUTES / _minutes_since_open), 1)
                # else: intensity stays None — vol filter uses raw_rvol pre-9:45

            candidates.append({
                "ticker": ticker,
                "prev_close": prev_close,
                "current_price": current_price,
                "gap_pct": round(gap_pct, 2),
                "today_volume": today_volume,
                "adv": adv,
                "adv_source": adv_source,
                "rel_volume": raw_rvol,
                "projected_vol_multiple": open_intensity,  # field name kept for DB compat
            })
        except Exception:
            continue

    # Sort by gap size descending — score the biggest movers first
    candidates.sort(key=lambda c: c["gap_pct"], reverse=True)
    rank_by_gap = {c["ticker"]: i + 1 for i, c in enumerate(candidates)}
    logger.info(f"Gap candidates ≥{MIN_GAP_PCT}%: {len(candidates)}"
                + (f" (top: {candidates[0]['ticker']} {candidates[0]['gap_pct']:.1f}%)" if candidates else ""))
    if not candidates:
        return []

    # Batch-fetch volume history for all candidates (one DB query)
    candidate_tickers = [c["ticker"] for c in candidates]
    vol_history_map = await get_volume_history(candidate_tickers)

    # Batch-fetch 3-month-ago closes for prior momentum check
    prior_3m_map: dict[str, float] = {}
    try:
        pool = await get_pool()
        target_date = today - timedelta(days=90)
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT DISTINCT ON (ticker) ticker, close
                FROM mi_daily_closes
                WHERE ticker = ANY($1) AND trade_date <= $2 AND trade_date >= $3
                ORDER BY ticker, trade_date DESC
            """, candidate_tickers, target_date, target_date - timedelta(days=14))
        prior_3m_map = {r["ticker"]: float(r["close"]) for r in rows}
    except Exception as e:
        logger.warning(f"Failed to fetch 3-month closes for prior momentum: {e}")

    # Compute proper 20-day ADV for non-universe candidates.
    # Top 20 are the scored cohort. Ranks 21-50 are a telemetry-only probe
    # (Option 2): synthesize ADV → rel_volume so we can detect "did rank
    # 21-50 candidates with high rel_volume turn into winners?" Without
    # ADV those rows hit mi_ep_scan_log with placeholder prevDay.v which
    # is useless for outcome analysis. Probe-stage results emit an
    # `ep_adv_probe_synthesized` audit event — `data_gated_reviews.yaml`
    # entry `adv_probe_retirement` triggers a manual review at 30 days.
    non_universe = [c for c in candidates[:50] if c["adv_source"] == "pending"]
    if non_universe:
        logger.info(f"Fetching 20-day ADV for {len(non_universe)} non-universe candidates (incl. rank 21-50 probe)...")
        adv_tasks = [_compute_adv_from_polygon(c["ticker"], today) for c in non_universe]
        adv_results = await asyncio.gather(*adv_tasks)
        for c, computed_adv in zip(non_universe, adv_results):
            if computed_adv:
                c["adv"] = computed_adv
                c["adv_source"] = "polygon_20d"
                c["rel_volume"] = round(c["today_volume"] / computed_adv, 2) if computed_adv > 0 else None
                if c["rel_volume"] and _minutes_since_open and _minutes_since_open >= 15:
                    c["projected_vol_multiple"] = round(c["rel_volume"] * (_SESSION_MINUTES / _minutes_since_open), 1)
                logger.info(f"  {c['ticker']}: ADV={computed_adv:,.0f} → rel_vol={c.get('rel_volume')}x")
                # Probe-only event for ranks 21-50. The top-20 cohort is the
                # canonical scored set and doesn't need a separate event.
                gap_rank = rank_by_gap.get(c["ticker"])
                if gap_rank and gap_rank > 20:
                    await log_audit_event(
                        "ep_adv_probe_synthesized",
                        f"{c['ticker']} rank={gap_rank} gap={c['gap_pct']:.1f}% rel_vol={c['rel_volume']}x",
                        json.dumps({
                            "ticker": c["ticker"],
                            "scan_date": today.isoformat(),
                            "rank_by_gap": gap_rank,
                            "gap_pct": round(c["gap_pct"], 2),
                            "adv_polygon_20d": int(computed_adv),
                            "rel_volume": c.get("rel_volume"),
                            "projected_vol_multiple": c.get("projected_vol_multiple"),
                            "today_volume": int(c["today_volume"]),
                        }),
                    )

    # Batch-fetch MIN close over last 5 trading days for extension check.
    # Using MIN (not the close from exactly 5 days ago) catches stocks that surged
    # 3 days ago and are now re-extending — a single look-back point would miss this.
    extension_map: dict[str, float] = {}
    try:
        window_start = today - timedelta(days=10)  # ~5 trading days + buffer
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT ticker, MIN(close) AS low_close
                FROM mi_daily_closes
                WHERE ticker = ANY($1) AND trade_date >= $2 AND trade_date < $3
                GROUP BY ticker
            """, candidate_tickers, window_start, today)
        extension_map = {r["ticker"]: float(r["low_close"]) for r in rows}
    except Exception as e:
        logger.warning(f"Failed to fetch 5-day closes for extension check: {e}")

    # Batch-fetch recent EP alerts for cooldown check (same ticker in last 60 days)
    # Also check today — skip re-scoring tickers already alerted in an earlier scan run
    cooldown_tickers: set[str] = set()
    already_today: set[str] = set()
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT DISTINCT ticker FROM mi_ep_alerts
                WHERE ticker = ANY($1) AND alert_date >= $2 AND alert_date < $3
            """, candidate_tickers, today - timedelta(days=EP_COOLDOWN_DAYS), today)
            cooldown_tickers = {r["ticker"] for r in rows}
            rows_today = await conn.fetch("""
                SELECT DISTINCT ticker FROM mi_ep_alerts
                WHERE ticker = ANY($1) AND alert_date = $2
            """, candidate_tickers, today)
            already_today = {r["ticker"] for r in rows_today}
    except Exception as e:
        logger.warning(f"Failed to fetch EP cooldown data: {e}")

    # Score each candidate (rate-limited FMP calls)
    results = []
    scan_log: list[dict] = []  # accumulated for batch DB write at end

    def _scan_row(c: dict, *, reason: str | None, ep_score: float | None,
                  tier: str | None, catalyst_quality: str | None) -> dict:
        return {
            "scan_date": today,
            "ticker": c["ticker"],
            "gap_pct": c.get("gap_pct"),
            "prev_close": c.get("prev_close"),
            "rel_volume": c.get("rel_volume"),
            "filter_reason": reason,
            "ep_score": ep_score,
            "score_tier": tier,
            "catalyst_quality": catalyst_quality,
            "scan_time_et": now_et,
            "rank_by_gap": rank_by_gap.get(c["ticker"]),
            "projected_vol_multiple": c.get("projected_vol_multiple"),
            "pm_rvol": c.get("pm_rvol"),
            "adv": c.get("adv"),
            "adv_source": c.get("adv_source"),
            "minutes_since_open": _minutes_since_open,
        }

    def _log_filtered(c: dict, reason: str) -> None:
        scan_log.append(_scan_row(
            c, reason=reason, ep_score=None, tier=None, catalyst_quality=None,
        ))

    # Log candidates beyond top-20 cap
    for c in candidates[20:]:
        _log_filtered(c, f"outside top-20 gap cap (gap {c['gap_pct']:.1f}%)")

    for c in candidates[:20]:  # Cap at 20 to stay within FMP call budget
        ticker = c["ticker"]
        rel_volume = c.get("rel_volume") or 0

        # ── Volume gate (RVOL@T) ──────────────────────────────────────────
        # ONE primitive, two anchors. Pre-9:30 → pm anchor (cumulative from
        # 4:00 ET vs 22-day pre-market baseline). 9:30 onward → session
        # anchor (cumulative from 9:30 vs 22-day session baseline). RVOL@T
        # answers: "is today's pace at this clock-minute above this ticker's
        # normal pace at this clock-minute." Replaces the structurally broken
        # `today_5min_vol / 390min_ADV` ratio that mathematically rejected
        # every name in the first 15 min unless they had outsized pre-market
        # volume (HUT/BLMN/GLW false-rejects 5/6).
        #
        # Silent fallback: if the ticker has no baseline (outside dollar-vol
        # universe, or curves not yet refreshed), the gate passes — the
        # absolute-share floor below catches micro-float noise.
        try:
            if _minutes_since_open is None:
                premkt_vol, session_vol = c["today_volume"], 0
            else:
                premkt_vol, session_vol = 0, c["today_volume"]
            rvol_info = await compute_rvol_at_time(
                ticker=ticker,
                now_et=now_et,
                today_premkt_vol=premkt_vol,
                today_session_vol=session_vol,
            )
        except Exception as e:
            logger.warning(f"RVOL@T lookup failed for {ticker}: {e}")
            rvol_info = None
        if rvol_info:
            anchor = rvol_info["anchor"]
            threshold = MIN_PM_RVOL if anchor == "pm" else MIN_SESSION_RVOL
            reason_const = (
                FILTER_PM_RVOL_TOO_LOW if anchor == "pm" else FILTER_SESSION_RVOL_TOO_LOW
            )
            audit_event = "ep_filter_pm_rvol" if anchor == "pm" else "ep_filter_session_rvol"
            phase_label = "pre-open" if anchor == "pm" else "session"
            c["pm_rvol"] = rvol_info["rvol_at_time"]  # column reused for both anchors
            c["pm_rvol_baseline_n"] = rvol_info["baseline_n"]
            if (
                rvol_info["baseline_n"] >= MIN_BASELINE_N_FOR_GATE
                and rvol_info["rvol_at_time"] < threshold
            ):
                detail = (
                    f"{anchor}_rvol={rvol_info['rvol_at_time']:.2f}x "
                    f"(today {rvol_info['today_cum_vol']:,} / "
                    f"baseline {rvol_info['baseline_mean']:,.0f} "
                    f"n={rvol_info['baseline_n']}) < {threshold}x"
                )
                reason = f"{reason_const}: {detail}"
                logger.info(f"Skip {ticker}: {detail} (gap={c['gap_pct']:.1f}%)")
                _log_filtered(c, reason)
                await log_audit_event(
                    audit_event,
                    f"{ticker} {phase_label} pace below normal",
                    f"{detail} | gap={c['gap_pct']:.1f}%",
                )
                continue

        # Hard filter: absolute pre-market volume (filters micro-float noise),
        # UNLESS pm_rvol confirms relative anomaly (AAON 5/07 class: low-float
        # name with pm_rvol 32-60× normal still tripped 25K absolute floor).
        # The relative gate is the better signal; the absolute floor is just
        # a backup for names with no pm_rvol baseline.
        if c["today_volume"] < MIN_PREMARKET_SHARES:
            pm_rvol_cur = c.get("pm_rvol")
            if pm_rvol_cur is not None and pm_rvol_cur >= 5.0:
                # Relative anomaly clearly anomalous — don't reject on absolute count.
                pass  # fall through to next gate
            else:
                reason = f"pre-mkt volume {c['today_volume']:,} < {MIN_PREMARKET_SHARES:,} shares"
                logger.info(f"Skip {ticker}: {reason} (gap={c['gap_pct']:.1f}%)")
                _log_filtered(c, reason)
                continue

        # Hard filter: EP cooldown — don't re-alert same ticker within 60 days,
        # UNLESS a fresh earnings catalyst is firing (HIMX 5/07 incident class:
        # ticker on cooldown from prior alert, but fresh earnings + qualifying
        # gap is structurally a new event — earnings are quarterly, the prior
        # alert was a different catalyst). Bypass requires both gap >= 15%
        # AND is_earnings_day to avoid bypassing on routine post-news bumps.
        if ticker in cooldown_tickers:
            cooldown_bypass = False
            if c["gap_pct"] >= 15.0:
                # Fail-soft direction (advisor alignment 2026-05-08): on
                # yfinance error, treat as earnings day → cooldown BYPASSED.
                # Defensive: rather over-allow on data outage than block a
                # real fresh-earnings EP.
                try:
                    earnings_match_cd, _ = await is_earnings_day(ticker, today)
                except Exception:
                    earnings_match_cd = True
                if earnings_match_cd:
                    cooldown_bypass = True
                    await log_audit_event(
                        "ep_cooldown_bypassed_earnings",
                        f"{ticker}: cooldown bypassed — fresh earnings + gap {c['gap_pct']:.1f}%",
                        json.dumps({
                            "ticker": ticker,
                            "alert_date": today.isoformat(),
                            "gap_pct": c["gap_pct"],
                            "cooldown_days": EP_COOLDOWN_DAYS,
                        }),
                    )
            if not cooldown_bypass:
                reason = f"EP cooldown — alerted within last {EP_COOLDOWN_DAYS} days"
                logger.info(f"Skip {ticker}: {reason}")
                _log_filtered(c, reason)
                continue

        # Skip if already scored in an earlier scan run today
        if ticker in already_today:
            logger.debug(f"Skip {ticker}: already scored today")
            _log_filtered(c, "already scored earlier today")
            continue

        # Hard filter: extension — skip if already up 50%+ before today's gap
        close_5d_ago = extension_map.get(ticker)
        if close_5d_ago and close_5d_ago > 0 and c["prev_close"]:
            extension_pct = (c["prev_close"] - close_5d_ago) / close_5d_ago * 100
            if extension_pct >= MAX_EXTENSION_PCT:
                reason = f"already up {extension_pct:.0f}% in prior 5 days (extended)"
                logger.info(f"Skip {ticker}: {reason}")
                _log_filtered(c, reason)
                continue

        # Hard filter: pre-trade quality (ADV $1M, ATR%, market cap)
        # Single source of truth — same filters used by backtester and live tracker
        passed, skip_reason = await check_filters(ticker, today)
        if not passed:
            reason = f"quality filter: {skip_reason}"
            logger.info(f"Skip {ticker}: pre-trade filter — {skip_reason}")
            _log_filtered(c, reason)
            continue

        # Volume conviction percentile — only valid pre-open (compares cumulative
        # to full-day ADV history). Post-open the partial-day cumulative would
        # falsely rank near 0 against full-day distributions, so return neutral.
        # Post-open conviction is captured via projected_vol_multiple (rel_volume slot).
        if _minutes_since_open is None:
            vol_pct = _volume_percentile(c["today_volume"], vol_history_map.get(ticker, []))
        else:
            vol_pct = 50.0

        # Catalyst cache check — skip FMP/Claude/Perplexity if already evaluated today.
        # A stock oscillating near the 15% threshold gets re-scored every 5 min;
        # the catalyst is the same each time. One evaluation per ticker per day.
        global _catalyst_cache, _catalyst_cache_date
        if _catalyst_cache_date != today:
            _catalyst_cache.clear()
            _catalyst_cache_date = today

        cached = _catalyst_cache.get(ticker)
        if cached:
            catalyst_quality, confidence_multiplier, news_summary, claude_analysis = cached
            profile = await get_fmp_profile(ticker)  # still need profile for neglect/float scoring
            upgrades_30d = 0  # ratings don't change scan-to-scan; skip re-fetch
            logger.debug(f"{ticker}: using cached catalyst ({catalyst_quality}, {confidence_multiplier}x)")
        else:
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

            # Claude + Perplexity in parallel — cancel Perplexity if catalyst is routine
            claude_task = asyncio.create_task(_classify_catalyst_claude(ticker, all_news, profile))
            pplx_task = asyncio.create_task(_validate_catalyst_perplexity(ticker, news_summary))

            catalyst_quality, claude_analysis = await claude_task

            # Skip M&A / buyout — price capped at deal value, no momentum trade.
            # Single-source filter (ma_filter.is_likely_ma) — same logic used by
            # flag/9M/parabolic detectors. Polygon backstop closes the Perplexity
            # coverage-gap (AVNS 5/4: Perplexity returned "no specific news" for
            # 4/14 going-private; Polygon had the headline the whole time).
            is_mna, mna_meta = await is_likely_ma(
                ticker,
                catalyst_quality=catalyst_quality,
                catalyst_texts=[claude_analysis, news_summary],
                check_polygon=True,
                on_or_before=today,
            )
            if is_mna:
                pplx_task.cancel()
                reason = "M&A/buyout catalyst — no momentum trade"
                logger.info(f"Skip {ticker}: {reason} ({(mna_meta or {}).get('source')})")
                await log_audit_event(
                    "mna_filter_fired",
                    f"{ticker} via {(mna_meta or {}).get('source', 'unknown')}",
                    json.dumps({
                        "ticker": ticker,
                        "alert_date": today.isoformat(),
                        "detector": "ep",
                        "catalyst_quality": catalyst_quality,
                        "news_summary": (news_summary or "")[:200],
                        **(mna_meta or {}),
                    }),
                )
                _log_filtered(c, reason)
                continue

            # Skip routine catalysts outright
            if catalyst_quality == "routine" and c["gap_pct"] < 12:
                pplx_task.cancel()
                reason = f"routine catalyst, gap {c['gap_pct']:.1f}%"
                logger.info(f"Skip {ticker}: {reason}")
                _log_filtered(c, reason)
                continue

            pplx_quality = await pplx_task

            # Agreement logic
            confidence_multiplier = 1.0
            if pplx_quality and pplx_quality == catalyst_quality:
                confidence_multiplier = 1.2
                logger.info(f"{ticker}: Claude+Perplexity agree on {catalyst_quality} → 1.2x confidence")
            elif pplx_quality and pplx_quality != catalyst_quality:
                logger.info(f"{ticker}: Claude={catalyst_quality}, Perplexity={pplx_quality} → disagreement, no boost")

            # Hedge-phrase downgrade: when Perplexity self-acknowledges null search
            # results, both classifiers are grading a hollow news_summary. RDDT 5/1
            # case: Q1 earnings beat 4/30 AH was the real catalyst, but Perplexity
            # returned hedged synthesis → Claude classified an Evercore initiation
            # blurb as "strong". Downgrade by one notch and cancel agreement boost.
            _PPLX_HEDGE_PHRASES = (
                "no specific information",
                "couldn't find",
                "could not find",
                "search results don't contain",
                "search results do not contain",
                "no recent news",
                "unable to find",
                "i don't have",
                "i do not have",
            )
            pplx_low = (perplexity_answer or "").lower()
            hedged = any(p in pplx_low for p in _PPLX_HEDGE_PHRASES)
            if hedged and catalyst_quality in ("game_changer", "strong"):
                _DOWNGRADE = {"game_changer": "strong", "strong": "routine"}
                downgraded = _DOWNGRADE[catalyst_quality]
                logger.info(
                    f"{ticker}: Perplexity hedge detected — downgrading "
                    f"{catalyst_quality} → {downgraded}"
                )
                await log_audit_event(
                    "catalyst_pplx_hedge_downgrade",
                    f"{ticker} {catalyst_quality} → {downgraded}",
                    json.dumps({
                        "ticker": ticker,
                        "alert_date": today.isoformat(),
                        "from_quality": catalyst_quality,
                        "to_quality": downgraded,
                        "pplx_excerpt": (perplexity_answer or "")[:200],
                    }),
                )
                catalyst_quality = downgraded
                confidence_multiplier = 1.0  # cancel any agreement boost

            # Store in cache for subsequent scans today
            _catalyst_cache[ticker] = (catalyst_quality, confidence_multiplier, news_summary, claude_analysis)

        # Earnings-day pre-score catalyst boost (DDOG/AAON 5/07 incident class).
        # Existing earnings-day override (below) only fires for MODERATE→HIGH
        # promotion (score ≥ 50). DDOG/AAON scored 30 because catalyst='routine'
        # mathematically caps score below 50 regardless of gap/volume. The
        # classifier (Claude + Perplexity) returned 'routine' because the news
        # scrape was hedged/hollow. is_earnings_day is structurally independent
        # evidence — when yfinance confirms today is the earnings date, the
        # catalyst IS the earnings event regardless of LLM grade. Upgrade
        # routine→strong (or no-op if already strong/game_changer) so the
        # score can clear the 50 threshold.
        # Fail-soft direction (advisor alignment 2026-05-08): on yfinance
        # error, treat as earnings day → catalyst boost FIRES. Defensive:
        # rather over-boost on data outage than miss a real earnings EP.
        try:
            earnings_today_match, earnings_src = await is_earnings_day(ticker, today)
        except Exception:
            earnings_today_match, earnings_src = True, "unavailable"
        if earnings_today_match and catalyst_quality in ("routine", None):
            original_quality = catalyst_quality
            catalyst_quality = "strong"
            await log_audit_event(
                "catalyst_earnings_boost",
                f"{ticker}: {original_quality} → strong (earnings_day, source={earnings_src})",
                json.dumps({
                    "ticker": ticker,
                    "alert_date": today.isoformat(),
                    "from_quality": original_quality,
                    "to_quality": "strong",
                    "earnings_source": earnings_src,
                    "gap_pct": c["gap_pct"],
                }),
            )
            # Also update cache so subsequent scan ticks see the boosted grade.
            _catalyst_cache[ticker] = (
                catalyst_quality, confidence_multiplier, news_summary, claude_analysis,
            )

        # Compute prior 3-month change %
        prior_3m_change = None
        close_3m_ago = prior_3m_map.get(ticker)
        if close_3m_ago and close_3m_ago > 0 and c["prev_close"]:
            prior_3m_change = (c["prev_close"] - close_3m_ago) / close_3m_ago * 100

        # Score
        ep_score, breakdown = _score_ep(
            gap_pct=c["gap_pct"],
            rel_volume=rel_volume,
            catalyst_quality=catalyst_quality,
            profile=profile,
            analyst_upgrades=upgrades_30d,
            regime_multiplier=regime_multiplier * confidence_multiplier,
            projected_vol_multiple=c.get("projected_vol_multiple"),
            vol_percentile=vol_pct,
            prior_3m_change=prior_3m_change,
        )

        if ep_score < 50:
            reason = f"score {ep_score:.0f} < 50 (catalyst={catalyst_quality})"
            logger.info(f"Skip {ticker}: {reason} (gap={c['gap_pct']:.1f}% breakdown={breakdown})")
            scan_log.append(_scan_row(
                c, reason=reason, ep_score=ep_score, tier=None,
                catalyst_quality=catalyst_quality,
            ))
            continue

        tier = "HIGH" if ep_score >= ep_threshold else "MODERATE"

        # Earnings-day HIGH override. The catalyst classifier rates textual
        # news_summary; when news ingest lags the announcement (DOCN 5/05: Q1
        # beat pre-market, no headlines yet → catalyst='routine'), a qualifying
        # gap silently scores below threshold. Per Pradeep Bonde, a meaningful
        # gap on an earnings day is a qualified EP regardless of beat/miss
        # prose grade — downside bounded by ORB stop-limit + 10:00 cancel + ATR.
        if tier == "MODERATE" and c["gap_pct"] >= 10.0:
            # Fail-soft direction (advisor alignment 2026-05-08): on yfinance
            # error, treat as earnings day → MODERATE→HIGH override fires.
            # Defensive: rather over-promote than miss a real earnings EP.
            try:
                earnings_match, earnings_source = await is_earnings_day(ticker, today)
            except Exception:
                earnings_match, earnings_source = True, "unavailable"

            if earnings_match:
                logger.info(
                    f"{ticker}: earnings-day override MODERATE→HIGH "
                    f"(gap={c['gap_pct']:.1f}% source={earnings_source})"
                )
                await log_audit_event(
                    "earnings_override_applied",
                    f"{ticker} MODERATE→HIGH via {earnings_source}",
                    json.dumps({
                        "ticker": ticker,
                        "alert_date": today.isoformat(),
                        "gap_pct": round(c["gap_pct"], 2),
                        "ep_score": round(ep_score, 1),
                        "ep_threshold": ep_threshold,
                        "catalyst_quality": catalyst_quality,
                        "source": earnings_source,
                    }),
                )
                tier = "HIGH"
            else:
                event = (
                    "earnings_override_unavailable"
                    if earnings_source == "unavailable"
                    else "earnings_override_no_match"
                )
                if _audit_dedupe_check(ticker, today, event):
                    await log_audit_event(
                        event,
                        f"{ticker} {earnings_source}",
                        json.dumps({
                            "ticker": ticker,
                            "alert_date": today.isoformat(),
                            "gap_pct": round(c["gap_pct"], 2),
                            "ep_score": round(ep_score, 1),
                            "catalyst_quality": catalyst_quality,
                            "source": earnings_source,
                        }),
                    )

        # Tape-conviction shadow — forward-only baseline for a future tape-only
        # override; one row per ticker per scan_date (deduped across cron ticks).
        proj_vol = c.get("projected_vol_multiple")
        if (
            c["gap_pct"] >= 12.0
            and proj_vol is not None
            and proj_vol >= 5.0
            and _audit_dedupe_check(ticker, today, "tape_conviction_shadow")
        ):
            await log_audit_event(
                "tape_conviction_shadow",
                f"{ticker} gap={c['gap_pct']:.1f}% proj={proj_vol:.1f}x tier={tier}",
                json.dumps({
                    "ticker": ticker,
                    "alert_date": today.isoformat(),
                    "gap_pct": round(c["gap_pct"], 2),
                    "projected_vol_multiple": round(proj_vol, 2),
                    "ep_score": round(ep_score, 1),
                    "tier": tier,
                    "catalyst_quality": catalyst_quality,
                }),
            )

        result = {
            **c,
            "ep_score": ep_score,
            "score_tier": tier,
            "catalyst_quality": catalyst_quality,
            "catalyst": news_summary[:500],
            "claude_analysis": claude_analysis,
            "gemini_validation": pplx_quality,  # DB column name kept for compatibility
            "confidence_multiplier": confidence_multiplier,
            "vol_percentile": vol_pct,
            "score_breakdown": breakdown,
            "alert_date": today,
        }
        results.append(result)

        # Log to scan log as passed
        scan_log.append(_scan_row(
            c, reason=None, ep_score=ep_score, tier=tier,
            catalyst_quality=catalyst_quality,
        ))

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
            "gemini_validation": pplx_quality,  # DB column name kept for compatibility
            "confidence_multiplier": confidence_multiplier,
            "vol_percentile": vol_pct,
            "pm_rvol": c.get("pm_rvol"),
            "pm_rvol_baseline_n": c.get("pm_rvol_baseline_n"),
            "detected_at": now_et,
        })

        # Telemetry for `conviction_floor_extension` review (data_gated_reviews.yaml).
        # Cell under evaluation: gap∈[10,15) + catalyst='strong'. Logs whether the
        # candidate would have been promoted to HIGH at floors 55/58/60.
        if catalyst_quality == "strong" and 10 <= c["gap_pct"] < 15:
            await log_audit_event(
                "conviction_floor_eligible",
                f"{ticker} gap={c['gap_pct']:.1f}% score={ep_score:.0f} tier={tier}",
                json.dumps({
                    "ticker": ticker,
                    "alert_date": today.isoformat(),
                    "gap_pct": round(c["gap_pct"], 2),
                    "ep_score": round(ep_score, 1),
                    "ep_threshold": ep_threshold,
                    "actual_tier": tier,
                    "would_be_high_at_55": max(ep_score, 55) >= ep_threshold,
                    "would_be_high_at_58": max(ep_score, 58) >= ep_threshold,
                    "would_be_high_at_60": max(ep_score, 60) >= ep_threshold,
                }),
            )

        proj = c.get("projected_vol_multiple")
        pm_rvol_val = c.get("pm_rvol")
        vol_parts = [f"rvol={rel_volume:.1f}x"]
        if proj:
            vol_parts.append(f"proj={proj:.0f}x")
        if pm_rvol_val is not None:
            vol_parts.append(f"pm_rvol@t={pm_rvol_val:.2f}x")
        vol_str = " ".join(vol_parts)
        logger.info(f"EP alert: {ticker} gap={c['gap_pct']:.1f}% {vol_str} score={ep_score} tier={tier}")

    results.sort(key=lambda r: r["ep_score"], reverse=True)

    # Batch-write scan log (fire and forget — never block results)
    asyncio.create_task(log_ep_scan_candidates(scan_log))

    # Summary log — always visible, even when no alerts fire. Helps verify the scan ran
    # and diagnose why candidates were filtered out.
    high = [r for r in results if r["score_tier"] == "HIGH"]
    moderate = [r for r in results if r["score_tier"] == "MODERATE"]
    logger.info(
        f"EP scan complete: {len(candidates)} gap candidates → {len(results)} scored "
        f"({len(high)} HIGH, {len(moderate)} MODERATE) | "
        f"regime={regime_label} threshold={ep_threshold}"
    )

    return results
