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
from agents.market_intelligence.db import insert_ep_alert, get_adv_map, get_latest_regime, get_volume_history, get_pool, log_ep_scan_candidates, log_audit_event, enqueue_pending_allocation
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
from agents.market_intelligence.earnings_calendar import is_earnings_day, is_revenue_stage

logger = logging.getLogger(__name__)

# Hard filters
# MIN_GAP_PCT: 2026-05-17 R2 ship — lifted 8.0 → 10.0. The 8-10% gap
# bucket had 0/8 WR over the 60d cohort (ADR 0003 §3). Env override
# available via EP_MIN_GAP_PCT for fast rollback without redeploy.
_MIN_GAP_PCT_DEFAULT = 10.0
MIN_GAP_PCT = float(os.environ.get("EP_MIN_GAP_PCT", _MIN_GAP_PCT_DEFAULT))
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

# Prose-mismatch downgrade markers (#72, 2026-05-11). When the catalyst
# classifier returns "strong" but the prose explicitly says "no catalyst" or
# "no fresh news", the classifier is over-weighting volume/gap features
# against hedged news. MRAM 5/11 was the motivating case (-$2200 compound
# loss). Only fires when earnings backstop did NOT fire — MNDY 5/11 had
# the same prose pattern but was earnings day, the boost correctly graded
# it strong, downgrade must not fight the boost.
from agents.market_intelligence.prose_markers import NEGATIVE_CATALYST_MARKERS_BASE

# EP downgrade fires on the shared base plus the EP-specific shorter form
# "no specific news" (catches summaries that don't include " or catalyst" tail).
_PROSE_NEGATIVE_MARKERS = NEGATIVE_CATALYST_MARKERS_BASE + (
    "no specific news",
)

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
    in_active_theme: bool = False,
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

    in_active_theme: ticker is in an Accelerating or Mainstream theme on
    alert_date. Adds +10 to score breakdown (R4 ship 2026-05-17). Evidence:
    in-theme alerts had 67% WR vs 40% uncovered in label cross-tab; +27pp
    lift. Under current ep_threshold=70 the bonus is decorative (60d
    verification: 0 MODERATE-in-theme alerts would have crossed to HIGH
    with +10). Shipped for telemetry/visibility — future Phase 5 meta-
    rubric will use theme_context as a composite input with its own
    weight calibration. Env-flagged for fast rollback.
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

    # R4 in-theme bonus (2026-05-17 ship). +10 when ticker is in an
    # Accelerating or Mainstream theme on alert_date. Env-flagged.
    # Under current ep_threshold=70 this is decorative — verified via
    # pre-ship SQL (0 MODERATE-in-theme alerts in 60d would cross HIGH
    # with +10). Shipped for telemetry/visibility: score breakdown
    # surfaces the theme context, and Phase 5 meta-rubric will compose
    # theme_context as a separate scoring input with its own calibrated
    # weights. The +10 contributes to ep_score regardless of HIGH/MOD
    # outcome — useful as a paired-data signal for Phase 5 regression.
    _R4_ENABLED = os.environ.get("R4_THEME_BONUS_ENABLED", "true").lower() == "true"
    if _R4_ENABLED and in_active_theme:
        breakdown["theme_bonus"] = 10
    else:
        breakdown["theme_bonus"] = 0

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

    # Removed prior `min(..., 100)` cap (#42, 2026-05-09). The cap squashed
    # multiple high-conviction setups to identical 100s — 5/8 spike showed
    # 3+ MAGNA53 names tied at 100 on 3/8 sampled days. Cross-strategy
    # allocator (#31) needs ranking resolution at the top tier; uncapping
    # gives natural 100-115 spread under Bull regime (×1.2 multiplier on
    # raw_score that maxes near 95). Tier thresholds (HIGH ≥ 70-90 by
    # regime) unchanged — uncap never promotes a candidate that wasn't
    # already capped, and conviction floors apply to raw_score pre-multiplier
    # so they aren't affected.
    final_score = raw_score * regime_multiplier
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
    #
    # Fix 2026-05-17 (P2.0b): also build `_known_stock_tickers` so we can
    # detect candidates that are NEITHER classified as stock NOR non-stock
    # (i.e., not in mi_security_types at all). USAX/USGG 4/20 case: the
    # weekly Monday refresh hadn't run yet for those names, so they slipped
    # through `_non_stock_tickers` (empty for unknown tickers) and got
    # admitted as EP candidates despite being ETFs. Fail-safe: skip
    # unclassified candidates entirely — the next weekly refresh adds them
    # to mi_security_types and they'll be properly admitted/excluded.
    _non_stock_tickers: set[str] = set()
    _known_stock_tickers: set[str] = set()
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            non_stock_rows = await conn.fetch(
                "SELECT ticker FROM mi_security_types WHERE security_type NOT IN ('CS', 'ADRC')"
            )
            stock_rows = await conn.fetch(
                "SELECT ticker FROM mi_security_types WHERE security_type IN ('CS', 'ADRC')"
            )
        _non_stock_tickers = {r["ticker"] for r in non_stock_rows}
        _known_stock_tickers = {r["ticker"] for r in stock_rows}
        logger.info(
            f"EP scan: security_types loaded — "
            f"{len(_known_stock_tickers)} stock, "
            f"{len(_non_stock_tickers)} non-stock"
        )
    except Exception as e:
        logger.warning(f"EP scan: could not load security_types ({e}) — relying on SKIP_TICKERS only")

    logger.info(f"EP scan: regime={regime_label}, threshold={ep_threshold}")

    # R4 (2026-05-17 ship): cache the set of tickers currently in an
    # active (Accelerating/Mainstream) theme. Built once per scan tick
    # to avoid N+1 PostgreSQL array-containment queries per ticker
    # (Gemini 2026-05-17). Per-ticker membership check is O(1) on the
    # set. Lookups against `_in_active_theme_set` happen inside
    # `_score_ep` via the new `in_active_theme` parameter.
    _in_active_theme_set: set[str] = set()
    try:
        from agents.market_intelligence.db import get_active_themes
        _active_themes = await get_active_themes(stale_after_days=7)
        for _theme in _active_themes:
            stage = (_theme.get("stage") or "").strip()
            if stage in ("Accelerating", "Mainstream"):
                for _t in (_theme.get("tickers") or []):
                    _in_active_theme_set.add(_t)
        logger.info(
            f"EP scan: {len(_in_active_theme_set)} tickers in active themes "
            f"(Accelerating/Mainstream) for R4 bonus"
        )
    except Exception as e:
        logger.warning(f"EP scan: theme set load failed ({e}) — R4 bonus disabled this tick")

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
    _unclassified_skipped = 0  # P2.0b counter
    for ticker, snap in snapshots.items():
        try:
            # Skip warrants, units, non-standard symbols, ETFs, and leveraged products
            if len(ticker) > MAX_TICKER_LEN or ticker in _SKIP_TICKERS or "." in ticker:
                continue
            if ticker in _non_stock_tickers:
                continue
            # P2.0b 2026-05-17: fail-safe for unclassified candidates.
            # If a ticker is not in EITHER set, mi_security_types hasn't
            # classified it yet (weekly cadence — gap window up to 7 days).
            # USAX/USGG class names slipped through this gap on 4/20.
            # Skip the unknown — next weekly refresh will classify. Don't
            # per-ticker log (would flood scan_log with thousands of names);
            # the aggregate count is logged once at scan end.
            if _known_stock_tickers and ticker not in _known_stock_tickers:
                _unclassified_skipped += 1
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
    # P2.0b 2026-05-17: log aggregate count of unclassified-skip — surfaces
    # when the weekly mi_security_types refresh is overdue. If this is high
    # (≥10/scan), there are many new tickers that haven't been classified;
    # consider bumping the refresh cadence from weekly to daily.
    if _unclassified_skipped > 0:
        logger.info(
            f"EP scan: {_unclassified_skipped} candidates skipped — unclassified "
            f"(not in mi_security_types). Weekly refresh runs Mondays; if "
            f"this number is high consistently, bump to daily."
        )
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

        # NOTE: pm-shares absolute-floor gate moved post-catalyst (R6 ship,
        # 2026-05-17) so we can carve out high-conviction names. The new
        # location is after catalyst classification — search for "R6 pm-shares".

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
            #
            # Sanitize Perplexity disclaimer text before feeding to keyword
            # scanner (2026-05-14 perplexity_hallucination_keyword_leak fix).
            # When Perplexity returns "No recent catalysts... Nearest match is X"
            # the unrelated content trips M&A keywords on the wrong company.
            from agents.market_intelligence.collector import strip_perplexity_disclaimer
            _, news_is_disclaimer = strip_perplexity_disclaimer(news_summary)
            catalyst_texts_for_filter = [claude_analysis]
            if not news_is_disclaimer:
                catalyst_texts_for_filter.append(news_summary)
            else:
                logger.info(f"{ticker}: Perplexity disclaimer in news_summary — excluding from M&A keyword scan")
                await log_audit_event(
                    "perplexity_disclaimer_stripped",
                    f"{ticker}: news_summary suppressed from M&A keyword scan",
                    json.dumps({
                        "ticker": ticker,
                        "news_summary_lead": (news_summary or "")[:200],
                    }),
                )
            is_mna, mna_meta = await is_likely_ma(
                ticker,
                catalyst_quality=catalyst_quality,
                catalyst_texts=catalyst_texts_for_filter,
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

            # R6 pm-shares carve-out (2026-05-17 ship). Moved from pre-catalyst
            # position so we can use catalyst_quality in the carve-out condition.
            # Reject the absolute pm-shares floor UNLESS one of the carve-outs
            # bypasses it:
            #   1. pm_rvol ≥ 5x (relative anomaly — original 2026-05-08 carve-out)
            #   2. gap ≥ 10% AND catalyst_quality='strong' (high-conviction —
            #      NEW R6 carve-out; CPA 5/14 class: gap 13%, strong, but
            #      pm-shares=7K blocked entry for 24 min in old pre-catalyst
            #      position)
            # Env-flagged for fast rollback: set R6_PMSHARES_CARVEOUT_ENABLED=false
            # to disable carve-out #2 only (carve-out #1 always active).
            _R6_ENABLED = os.environ.get(
                "R6_PMSHARES_CARVEOUT_ENABLED", "true"
            ).lower() == "true"
            if c["today_volume"] < MIN_PREMARKET_SHARES:
                pm_rvol_cur = c.get("pm_rvol")
                bypass_reason = None
                if pm_rvol_cur is not None and pm_rvol_cur >= 5.0:
                    bypass_reason = f"pm_rvol={pm_rvol_cur:.1f}x ≥ 5.0x"
                elif (
                    _R6_ENABLED
                    and c["gap_pct"] >= 10.0
                    and catalyst_quality == "strong"
                ):
                    bypass_reason = (
                        f"R6 carve-out: gap={c['gap_pct']:.1f}% + catalyst=strong"
                    )
                if bypass_reason is None:
                    pplx_task.cancel()
                    reason = (
                        f"pre-mkt volume {c['today_volume']:,} < "
                        f"{MIN_PREMARKET_SHARES:,} shares"
                    )
                    logger.info(f"Skip {ticker}: {reason} (gap={c['gap_pct']:.1f}%)")
                    _log_filtered(c, reason)
                    continue
                logger.info(
                    f"{ticker}: pm-shares floor bypassed — {bypass_reason}"
                )

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

        # Revenue-stage check (2026-05-20): pre-revenue companies (clinical-
        # stage biotech, SPACs, blank-check) shouldn't be earnings-boosted.
        # Their "earnings" event is really management commentary on pipeline
        # / trials, not a Q-rev catalyst. Triggering the boost makes the
        # rubric gate engage and produces misleading "Q-rev YoY un-extractable"
        # downgrades. Fail-soft to revenue-stage on data outage.
        # IMVT 2026-05-20 was the trigger case.
        if earnings_today_match:
            try:
                revenue_stage = await is_revenue_stage(ticker)
            except Exception:
                revenue_stage = True
        else:
            revenue_stage = True  # not used when not earnings day

        if earnings_today_match and revenue_stage and catalyst_quality in ("routine", None):
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
        elif earnings_today_match and not revenue_stage and catalyst_quality in ("routine", None):
            # Pre-revenue company on earnings day — log the skip so operator
            # can see WHY the boost didn't fire. Catalyst grade stays at
            # Claude's original verdict (likely routine, no HIGH alert).
            await log_audit_event(
                "catalyst_earnings_boost_skipped",
                f"{ticker}: pre-revenue company on earnings day, boost skipped "
                f"(catalyst stays {catalyst_quality}, source={earnings_src})",
                json.dumps({
                    "ticker": ticker,
                    "alert_date": today.isoformat(),
                    "catalyst_quality": catalyst_quality,
                    "earnings_source": earnings_src,
                    "reason": "pre_revenue_company",
                    "gap_pct": c["gap_pct"],
                }),
            )

        # ── Revenue-growth gate (2026-05-19, AGYS hotfix) ──────────────
        # The LLM catalyst classifier returns 'strong' based on overall
        # earnings narrative (beat %, qualitative factors like "record Q4",
        # "SaaS growth", "AI innovation"). AGYS 2026-05-19 fired HIGH on
        # 24% earnings beat + record-revenue prose despite ~1% revenue
        # growth. The Pradeep catalyst hierarchy + weekend Phase-5 rubric
        # work established: revenue growth IS the substance of earnings
        # catalysts; narrative-only "strong" without revenue substance is
        # a non-EP wearing EP clothing.
        #
        # Gate logic: for earnings catalysts (LLM 'strong' or 'game_changer'
        # on is_earnings_day=True), look up mi_fundamental_flags.sales_yoy_latest.
        # If < 5% (or missing — fail-closed; can't verify substance), downgrade
        # to 'routine'. The 50-score threshold will then filter naturally.
        #
        # 5% threshold is conservative ("company actually growing"). Refine
        # via Phase 5 calibration with operator labels. Env flag for fast
        # rollback if a real EP gets blocked.
        from agents.market_intelligence.constants import (
            EARNINGS_REVENUE_GATE_ENABLED, EARNINGS_REVENUE_GATE_MIN_YOY,
        )
        # Belt-and-suspenders: also skip the revenue gate entirely for
        # pre-revenue companies (clinical-stage biotechs, SPACs). Even if
        # Claude graded the catalyst strong on its own merit (e.g. FDA
        # news, trial readout, M&A), the Q-rev YoY check is structurally
        # inapplicable. Without this, the rubric would always downgrade
        # pre-revenue strong-catalyst names with the misleading "Q-rev YoY
        # un-extractable" reason. 2026-05-20 IMVT trigger case.
        if (EARNINGS_REVENUE_GATE_ENABLED
                and earnings_today_match
                and revenue_stage
                and catalyst_quality in ("strong", "game_changer")):
            # Multi-source FRESH extraction (2026-05-19, AGYS hotfix).
            # yfinance quarterly_financials lags announcements by 24-72h →
            # stale data on catalyst-day. Read structured numbers FROM the
            # actual press-release news corpus (Polygon + FMP + Perplexity +
            # internal Claude analysis) via Sonnet extraction → cache to
            # mi_ep_catalyst_metrics for subsequent scan ticks + /why.
            from agents.market_intelligence.catalyst_metrics_extractor import (
                extract_earnings_metrics, lookup_cached_metrics,
                persist_catalyst_metrics, get_q_revenue_yoy_pct,
            )

            _cached = await lookup_cached_metrics(ticker, today)
            if _cached:
                _extracted = _cached
                logger.info(f"{ticker}: catalyst metrics cached (extraction_quality={_extracted.get('extraction_quality')})")
            else:
                try:
                    _extracted = await extract_earnings_metrics(
                        ticker, today,
                        claude_analysis=claude_analysis,
                        perplexity_text=news_summary,
                        fmp_news=fmp_news if 'fmp_news' in dir() else None,
                    )
                    await persist_catalyst_metrics(ticker, today, _extracted)
                    logger.info(
                        f"{ticker}: catalyst metrics extracted "
                        f"(quality={_extracted.get('extraction_quality')}, "
                        f"q_rev_yoy={get_q_revenue_yoy_pct(_extracted)})"
                    )
                except Exception as e:
                    # Silent extraction failures leave the rubric gate unused
                    # (falls through to Q-rev safety net). Surface as audit
                    # event + Telegram so operator knows the gate wasn't
                    # exercised. (Item #15, 2026-05-19.)
                    logger.warning(f"{ticker}: catalyst metrics extraction failed: {e}")
                    _extracted = {"extraction_quality": "low", "extraction_error": str(e)[:200]}
                    # NOTE: do NOT do `from agents.market_intelligence.db import log_audit_event`
                    # here — log_audit_event is imported at module level (line 53) and a local
                    # import INSIDE this 1000+ line function would make `log_audit_event` a local
                    # variable, causing UnboundLocalError at ALL prior references in run_ep_scan.
                    # This is the 2026-05-20 bug class. Use the module-level import directly.
                    try:
                        await log_audit_event(
                            "extraction_error",
                            f"{ticker}: catalyst extraction failed — {str(e)[:200]} "
                            f"(rubric gate skipped; Q-rev safety-net engaged)",
                        )
                    except Exception:
                        pass
                    # Only Telegram on HIGH-tier catalysts — extraction failures
                    # on MODERATE are noise (rubric doesn't gate MODERATE anyway).
                    if catalyst_quality in ("strong", "game_changer"):
                        try:
                            from agents.market_intelligence.briefing import send_telegram_message
                            await send_telegram_message(
                                f"⚠️ *{ticker}*: catalyst extraction failed — "
                                f"rubric gate not exercised, Q-rev safety-net engaged. "
                                f"_See `/why {ticker}` for context; `mi_audit_log` for full error._"
                            )
                        except Exception:
                            pass

            _q_rev_yoy = get_q_revenue_yoy_pct(_extracted)
            _quality = _extracted.get("extraction_quality", "low")
            _reasoning = _extracted.get("reasoning_brief", "")

            # 6-axis rubric gate (Phase 5 ship 2026-05-19). Runs on fresh
            # multi-source extraction; composite_scaled < threshold →
            # downgrade. Falls through to Q-rev safety net if rubric
            # can't score.
            _downgrade_reason = None
            _rubric_result = None
            from agents.market_intelligence.constants import (
                CATALYST_RUBRIC_GATE_ENABLED, CATALYST_RUBRIC_MIN_COMPOSITE,
            )
            if CATALYST_RUBRIC_GATE_ENABLED:
                try:
                    from agents.market_intelligence.catalyst_rubric_runtime import (
                        score_ep_with_rubric,
                    )
                    _rubric_result = score_ep_with_rubric(ticker, _extracted, today)
                    if _rubric_result:
                        _composite = _rubric_result.get("composite_scaled")
                        _label = _rubric_result.get("label")
                        _caps = _rubric_result.get("caps_applied", [])
                        logger.info(
                            f"{ticker}: rubric composite={_composite}/39 "
                            f"label={_label} caps={_caps}"
                        )
                        if _composite is not None and _composite < CATALYST_RUBRIC_MIN_COMPOSITE:
                            _downgrade_reason = (
                                f"rubric_composite_{_composite:.1f}_below_"
                                f"{CATALYST_RUBRIC_MIN_COMPOSITE:.0f}_"
                                f"label_{_label}"
                            )
                except Exception as e:
                    logger.warning(f"{ticker}: rubric scoring failed: {e}")
                    _rubric_result = None

            # Safety-net Q-rev threshold gate (fires when rubric couldn't
            # score, e.g. extraction lacks q_revenue_yoy_pct entirely).
            if _downgrade_reason is None and _rubric_result is None:
                if _q_rev_yoy is None:
                    _downgrade_reason = f"q_rev_yoy_unextractable_quality_{_quality}"
                elif _q_rev_yoy < EARNINGS_REVENUE_GATE_MIN_YOY:
                    _downgrade_reason = (
                        f"q_rev_yoy_{_q_rev_yoy:.1f}pct_below_"
                        f"{EARNINGS_REVENUE_GATE_MIN_YOY:.0f}pct"
                    )

            if _downgrade_reason:
                _original_quality = catalyst_quality
                catalyst_quality = "routine"
                _qr_block = _extracted.get("q_revenue_usd") or {}
                _gf_block = _extracted.get("guidance_fy_revenue_usd") or {}
                # Rubric details if available (Phase 5 ship)
                _rubric_summary = None
                if _rubric_result:
                    _rubric_summary = {
                        "composite_scaled": _rubric_result.get("composite_scaled"),
                        "label": _rubric_result.get("label"),
                        "caps_applied": _rubric_result.get("caps_applied"),
                        "axes_scored": {
                            f"a{i}": _rubric_result.get(f"a{i}_score")
                            for i in range(1, 7)
                        },
                    }
                await log_audit_event(
                    "catalyst_earnings_revenue_weak_downgrade",
                    f"{ticker}: {_original_quality} → routine "
                    f"(earnings catalyst, {_downgrade_reason})",
                    json.dumps({
                        "ticker": ticker,
                        "alert_date": today.isoformat(),
                        "from_quality": _original_quality,
                        "to_quality": "routine",
                        "reason": _downgrade_reason,
                        "q_revenue_yoy_pct": _q_rev_yoy,
                        "extraction_quality": _quality,
                        "extraction_reasoning": _reasoning,
                        "extraction_sources": _qr_block.get("sources"),
                        "extraction_confidence": _qr_block.get("confidence"),
                        "guidance_midpoint_yoy_pct": _gf_block.get("midpoint_yoy_pct"),
                        "rubric": _rubric_summary,
                        "earnings_source": earnings_src,
                        "gap_pct": c["gap_pct"],
                    }),
                )
                _catalyst_cache[ticker] = (
                    catalyst_quality, confidence_multiplier,
                    news_summary, claude_analysis,
                )
                # Telegram surface so operator sees the downgrade in real
                # time + can use /why to inspect full extraction.
                # Dedup repeated rubric-downgrade Telegrams across consecutive
                # scan ticks. EP scans run every 5 min; without dedup, the
                # same ticker generates a fresh downgrade message each tick
                # until cooldown — CAVA 2026-05-20 fired 4 times this morning.
                # Audit event still fires for telemetry; only Telegram is
                # suppressed when an identical downgrade was logged in the
                # last 1h for the same ticker+alert_date.
                _suppress_telegram = False
                try:
                    pool = await get_pool()
                    async with pool.acquire() as conn:
                        prior = await conn.fetchrow("""
                            SELECT 1 FROM mi_audit_log
                            WHERE event_type = 'catalyst_earnings_revenue_weak_downgrade'
                              AND summary LIKE $1
                              AND created_at > NOW() - INTERVAL '1 hour'
                              AND created_at < NOW() - INTERVAL '1 second'
                            LIMIT 1
                        """, f"{ticker}:%")
                        _suppress_telegram = prior is not None
                except Exception:
                    # On DB error fail-open (send Telegram) — better to over-
                    # alert than miss a real downgrade signal.
                    _suppress_telegram = False

                if not _suppress_telegram:
                    try:
                        from agents.market_intelligence.briefing import send_telegram_message
                        from agents.market_intelligence.catalyst_rubric_runtime import (
                            format_rubric_for_telegram,
                        )
                        # Compose readable downgrade message: headline + rubric breakdown
                        _msg_lines = [
                            f"📉 *Earnings catalyst DOWNGRADED: {ticker}*",
                            f"LLM graded `{_original_quality}` on narrative, "
                            f"but methodology rubric disagrees.",
                            "",
                        ]
                        _rubric_block = format_rubric_for_telegram(ticker, _extracted, today)
                        if _rubric_block:
                            _msg_lines.append(_rubric_block)
                        elif _q_rev_yoy is not None:
                            _msg_lines.append(
                                f"Q-rev YoY *{_q_rev_yoy:.1f}%* below "
                                f"*{EARNINGS_REVENUE_GATE_MIN_YOY:.0f}%* threshold "
                                f"(safety net; extraction quality={_quality})"
                            )
                        else:
                            _msg_lines.append(
                                f"Q-rev YoY un-extractable from news "
                                f"(extraction quality={_quality}) — fail-loud"
                            )
                        _msg_lines.append("")
                        _msg_lines.append(f"`/rubric {ticker}` for full breakdown.")
                        await send_telegram_message("\n".join(_msg_lines))
                    except Exception:
                        pass

        # Prose-mismatch downgrade (#72, 2026-05-11). Strong-graded alerts
        # whose prose explicitly says "no catalyst / no fresh news" are
        # late-stage retail-driven gappers (MRAM 5/11 class). The classifier
        # over-weights volume+gap features against hedged news. Downgrade to
        # 'routine' so the score-50 threshold filters them out. Must run
        # AFTER the earnings boost so legitimate earnings-day strongs are
        # preserved (MNDY 5/11 same prose, but earnings = real catalyst).
        if catalyst_quality == "strong" and not earnings_today_match:
            matched_marker: Optional[str] = None
            matched_source: Optional[str] = None
            for src_name, text in (
                ("claude_analysis", claude_analysis or ""),
                ("news_summary", news_summary or ""),
            ):
                if not text:
                    continue
                low = text.lower()
                for marker in _PROSE_NEGATIVE_MARKERS:
                    if marker in low:
                        matched_marker = marker
                        matched_source = src_name
                        break
                if matched_marker:
                    break
            if matched_marker:
                original_quality = catalyst_quality
                catalyst_quality = "routine"
                await log_audit_event(
                    "catalyst_prose_mismatch_downgrade",
                    f"{ticker}: strong → routine "
                    f"(prose marker '{matched_marker}' in {matched_source})",
                    json.dumps({
                        "ticker": ticker,
                        "alert_date": today.isoformat(),
                        "from_quality": original_quality,
                        "to_quality": "routine",
                        "matched_marker": matched_marker,
                        "matched_source": matched_source,
                        "gap_pct": c["gap_pct"],
                    }),
                )
                _catalyst_cache[ticker] = (
                    catalyst_quality, confidence_multiplier,
                    news_summary, claude_analysis,
                )
                # Visibility surface (advisor 2026-05-11): user needs to see
                # the new behavior in action, not discover it by missing
                # alerts. Telegram once per (ticker, date) — already gated
                # by _catalyst_cache (one decision per ticker per day).
                try:
                    from agents.market_intelligence.briefing import send_telegram_message
                    from agents.market_intelligence.constants import mode_prefix
                    await send_telegram_message(
                        f"{mode_prefix()}📰 *Catalyst downgrade:* `{ticker}` "
                        f"gap +{c['gap_pct']:.1f}%\n"
                        f"Grade strong → routine — prose marker "
                        f"\"{matched_marker}\" in {matched_source}\n"
                        f"_Late-stage / no-fresh-news filter (#72). "
                        f"This alert will not promote to HIGH._"
                    )
                except Exception as e:
                    logger.warning(
                        f"catalyst_downgrade_telegram_failed: {ticker}: {e}"
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
            in_active_theme=(ticker in _in_active_theme_set),
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

        # Cross-strategy allocator (#31) Phase 1A — shadow enqueue. HIGH and
        # MODERATE tiers are slot contenders. Legacy submission pipeline runs
        # unchanged; the 9:28 AM allocator job reads this queue, scores, and
        # writes shadow_rank for offline comparison vs actual fills. UPSERT —
        # later-tick re-scores update in place. Failure here MUST NOT block
        # the alert path; wrap defensively.
        if tier in ("HIGH", "MODERATE"):
            try:
                from agents.market_intelligence.cross_strategy_allocator import score_magna53
                cand = score_magna53(
                    ticker=ticker,
                    alert_date=today,
                    ep_score=ep_score,
                    catalyst_quality=catalyst_quality,
                    pm_rvol=c.get("pm_rvol"),
                    gap_pct=c.get("gap_pct"),
                    regime_label=regime_label,
                )
                await enqueue_pending_allocation(
                    ticker=ticker, alert_date=today, strategy="magna53",
                    composite_score=cand.composite,
                    raw_dimensions=cand.raw_dimensions,
                )
            except Exception as e:
                logger.warning(f"allocator enqueue failed for {ticker} ({tier}): {e}")

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
