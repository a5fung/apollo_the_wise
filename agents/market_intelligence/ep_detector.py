"""
EP (Episodic Pivot) Detector.

Scans pre-market for gap-up stocks and scores them using the MAGNA53 model
(Pradeep Bonde / Kullamägi methodology).

Hard filters (applied BEFORE scoring — stocks that fail never reach the DB or briefing):
- Gap ≥ 8% vs previous close
- Previous close ≥ $5, previous day volume ≥ 50K shares
- Relative volume ≥ 2x ADV, pre-market volume ≥ 25K shares
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
import logging
import os
from datetime import date
from typing import Any, Optional

import anthropic

from datetime import timedelta

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
from agents.market_intelligence.db import insert_ep_alert, get_adv_map, get_latest_regime, get_volume_history, get_pool, log_ep_scan_candidates
from agents.market_intelligence.backtester.filters import check_filters

logger = logging.getLogger(__name__)

# Hard filters
MIN_GAP_PCT = 8.0
MIN_REL_VOLUME = 2.0
MIN_PREMARKET_SHARES = 25_000  # Absolute minimum — filters micro-float noise
MIN_PREV_CLOSE = 5.0           # Skip sub-$5 stocks — noise, not EPs
MAX_TICKER_LEN = 5             # Skip warrants/units (long symbols like ABCDW)
MIN_PREV_DAY_VOLUME = 50_000   # Skip illiquid stocks — stale quotes create phantom gaps

# Auto-disqualifiers (hard filters — applied before scoring)
MAX_EXTENSION_PCT = 50.0   # Skip if already up 50%+ in last 5 trading days before the gap
EP_COOLDOWN_DAYS = 60       # Skip if this ticker had an EP alert in last 60 days

# Leveraged/inverse ETFs and broad ETFs — never real EPs
_SKIP_TICKERS = SKIP_TICKERS

_claude = None


def _get_claude():
    global _claude
    if _claude is None:
        _claude = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
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
    if gap_pct >= 15 and catalyst_quality == "game_changer":
        raw_score = max(raw_score, 80)
        breakdown["conviction_floor"] = max(0, 80 - sum(v for k, v in breakdown.items() if k != "conviction_floor"))
    elif gap_pct >= 20 and catalyst_quality == "strong":
        raw_score = max(raw_score, 80)
        breakdown["conviction_floor"] = max(0, 80 - sum(v for k, v in breakdown.items() if k != "conviction_floor"))
    elif gap_pct >= 15 and catalyst_quality == "strong":
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
            # Skip warrants, units, non-standard symbols, and ETFs
            if len(ticker) > MAX_TICKER_LEN or ticker in _SKIP_TICKERS or "." in ticker:
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
            # Open intensity: current_vol / expected_vol_by_now = raw_rvol * (390 / min_elapsed)
            # Measures how many times above the *normal rate for this time* the stock is trading.
            # Linear — overstates final daily RVOL (opening minutes are always dense), but
            # correctly captures institutional conviction intensity at the moment of the EP.
            open_intensity = None
            if raw_rvol is not None and _minutes_since_open and today_volume > 0:
                open_intensity = round(raw_rvol * (_SESSION_MINUTES / _minutes_since_open), 1)

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

    # Compute proper 20-day ADV for non-universe candidates (top 20 only)
    # These stocks aren't in mi_stock_scores, so we fetch bars from Polygon
    non_universe = [c for c in candidates[:20] if c["adv_source"] == "pending"]
    if non_universe:
        logger.info(f"Fetching 20-day ADV for {len(non_universe)} non-universe candidates...")
        adv_tasks = [_compute_adv_from_polygon(c["ticker"], today) for c in non_universe]
        adv_results = await asyncio.gather(*adv_tasks)
        for c, computed_adv in zip(non_universe, adv_results):
            if computed_adv:
                c["adv"] = computed_adv
                c["adv_source"] = "polygon_20d"
                c["rel_volume"] = round(c["today_volume"] / computed_adv, 2) if computed_adv > 0 else None
                if c["rel_volume"] and _minutes_since_open:
                    c["projected_vol_multiple"] = round(c["rel_volume"] * (_SESSION_MINUTES / _minutes_since_open), 1)
                logger.info(f"  {c['ticker']}: ADV={computed_adv:,.0f} → rel_vol={c.get('rel_volume')}x")

    # Batch-fetch 5-day-ago closes for extension check (already up 50%+ before today's gap)
    extension_map: dict[str, float] = {}
    try:
        target_5d = today - timedelta(days=8)  # ~5 trading days
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT DISTINCT ON (ticker) ticker, close
                FROM mi_daily_closes
                WHERE ticker = ANY($1) AND trade_date <= $2 AND trade_date >= $3
                ORDER BY ticker, trade_date DESC
            """, candidate_tickers, target_5d, target_5d - timedelta(days=7))
        extension_map = {r["ticker"]: float(r["close"]) for r in rows}
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

    def _log_filtered(c: dict, reason: str) -> None:
        scan_log.append({
            "scan_date": today,
            "ticker": c["ticker"],
            "gap_pct": c.get("gap_pct"),
            "prev_close": c.get("prev_close"),
            "rel_volume": c.get("rel_volume"),
            "filter_reason": reason,
            "ep_score": None,
            "score_tier": None,
            "catalyst_quality": None,
        })

    # Log candidates beyond top-20 cap
    for c in candidates[20:]:
        _log_filtered(c, f"outside top-20 gap cap (gap {c['gap_pct']:.1f}%)")

    for c in candidates[:20]:  # Cap at 20 to stay within FMP call budget
        ticker = c["ticker"]
        rel_volume = c.get("rel_volume") or 0

        # Hard filter: rel volume (skip if no ADV data available — can't verify)
        if c.get("adv") and rel_volume < MIN_REL_VOLUME:
            reason = f"low rel volume {rel_volume:.1f}x < {MIN_REL_VOLUME}x"
            logger.info(f"Skip {ticker}: {reason} (gap={c['gap_pct']:.1f}%)")
            _log_filtered(c, reason)
            continue

        # Hard filter: absolute pre-market volume (filters micro-float noise)
        if c["today_volume"] < MIN_PREMARKET_SHARES:
            reason = f"pre-mkt volume {c['today_volume']:,} < {MIN_PREMARKET_SHARES:,} shares"
            logger.info(f"Skip {ticker}: {reason} (gap={c['gap_pct']:.1f}%)")
            _log_filtered(c, reason)
            continue

        # Hard filter: EP cooldown — don't re-alert same ticker within 60 days
        if ticker in cooldown_tickers:
            reason = f"EP cooldown — alerted within last {EP_COOLDOWN_DAYS} days"
            logger.info(f"Skip {ticker}: {reason}")
            _log_filtered(c, reason)
            continue

        # Skip if already scored in an earlier scan run today
        if ticker in already_today:
            logger.debug(f"Skip {ticker}: already scored today")
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

        # Claude + Perplexity in parallel — cancel Perplexity if catalyst is routine
        claude_task = asyncio.create_task(_classify_catalyst_claude(ticker, all_news, profile))
        pplx_task = asyncio.create_task(_validate_catalyst_perplexity(ticker, news_summary))

        catalyst_quality, claude_analysis = await claude_task

        # Skip M&A / buyout — price capped at deal value, no momentum trade
        _MNA_KEYWORDS = [
            "acquisition", "acquire", "buyout", "takeover", "merger", "bought by",
            "being acquired", "definitive agreement", "tender offer", "going private",
            "taken private", "strategic transaction", "merger agreement", "to be acquired",
        ]
        analysis_low = claude_analysis.lower()
        catalyst_low = news_summary.lower() if news_summary else ""
        is_mna = (
            catalyst_quality == "mna"
            or any(kw in analysis_low or kw in catalyst_low for kw in _MNA_KEYWORDS)
        )
        if is_mna:
            pplx_task.cancel()
            reason = "M&A/buyout catalyst — no momentum trade"
            logger.info(f"Skip {ticker}: {reason}")
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
            scan_log.append({
                "scan_date": today, "ticker": ticker,
                "gap_pct": c.get("gap_pct"), "prev_close": c.get("prev_close"),
                "rel_volume": rel_volume, "filter_reason": reason,
                "ep_score": ep_score, "score_tier": None,
                "catalyst_quality": catalyst_quality,
            })
            continue

        tier = "HIGH" if ep_score >= ep_threshold else "MODERATE"

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
        scan_log.append({
            "scan_date": today, "ticker": ticker,
            "gap_pct": c.get("gap_pct"), "prev_close": c.get("prev_close"),
            "rel_volume": rel_volume, "filter_reason": None,
            "ep_score": ep_score, "score_tier": tier,
            "catalyst_quality": catalyst_quality,
        })

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
        })

        proj = c.get("projected_vol_multiple")
        vol_str = f"rvol={rel_volume:.1f}x proj={proj:.0f}x" if proj else f"rvol={rel_volume:.1f}x"
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
