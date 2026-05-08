"""
Parabolic-short candidate detector (Stage 1 — telemetry only).

Encodes the Stamatoudis / Qullamaggie parabolic-exhaustion playbook as a
nightly scan. Sources synthesised in `~/.claude/plans/shiny-mapping-locket.md`
(rule citations live there); promotion path lives in
`memory/project_trading_ideas_backlog.md` (TI1).

Four stages emitted per (ticker, scan_date):
  * unqualified  — any qualifying gate fails. Persisted, no alert.
  * watch        — all qualifying gates pass; burst checklist not yet aligned.
                   Silent DB row — proves the structural setup caught early.
  * anticipation — watch + burst_score >= 3/4 (gaps, range, vol, streak).
                   Telegram watchlist — "the pot is boiling."
  * climax       — anticipation + `gapped_today` + `climax_volume_flag`.
                   Telegram trigger — "the snap." Intraday VWAP failure live.

The compute function is pure (`compute_parabolic_metrics(rows, market_cap)`)
so it can be unit-validated against historical CAR data via
`scripts/backfill_parabolic_car.py` before any infrastructure (scheduler,
persistence, Telegram digest) gets wired up.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Bound concurrency for the per-ticker compute loop. Each ticker may trigger
# an FMP profile fetch (cap-tier classification) — same rate-limit envelope as
# the rest of the system uses for FMP.
_SCAN_CONCURRENCY = 10
_HISTORY_DAYS = 120  # 60d base anchor walk + 50d SMA + buffer

# ── News-check exclusion (M&A / FDA / single-news pop) ──────────────────────
# Parabolic-short setups need ongoing momentum; a single one-shot news event
# (buyout announcement, FDA approval, lawsuit win) produces a parabolic-shaped
# spike that won't mean-revert — the stock is now pinned to the deal price or
# new fundamental level. Rather than try to detect this from price action alone
# (M&A and textbook climax candles look similar on day 1), we ask Perplexity
# for context on each climax / anticipation candidate and exclude if positive.
# Watch-stage candidates skip the check — too many to be worth the API spend,
# and they're not yet alert-worthy anyway.
_NEWS_CHECK_CONCURRENCY = 3                # Perplexity is paid per call; cap fan-out
_NEWS_CHECK_TTL_DAYS    = 14               # Re-check after 2 weeks (deals fall through)


# ── Cap-tier prior-move thresholds (Qullamaggie / TradeZella) ────────────────
_LARGE_CAP_USD = 10_000_000_000      # ≥ $10B
_MID_CAP_USD   = 2_000_000_000       # $2B - $10B
# < _MID_CAP_USD is small/micro
_PRIOR_MOVE_LARGE = 0.50             # 50%
_PRIOR_MOVE_MID   = 1.00             # 100%
_PRIOR_MOVE_SMALL = 2.00             # 200%

# ── Other qualifying gates ───────────────────────────────────────────────────
_MIN_DOLLAR_VOL_TODAY  = 10_000_000  # $10M today, so we can borrow + short
_MIN_EXT_VS_SMA50      = 1.50        # close >= 1.5 × SMA-50 (Uncharted Territory)
_MAX_PULLBACK_COUNT_20D = 6          # < 6 down days in last 20 (parabolic, not linear)

# ── Velocity-delta gate (parabolic curve, not linear) ───────────────────────
# Compare daily compound rates, not raw ROCs: in a sustained exponential
# parabola, 20d ROC structurally dwarfs 5d ROC (the 5d window IS part of
# the 20d window) — a raw-ROC threshold is mathematically infeasible for
# stocks already weeks into a run. Daily-rate comparison stays stable as
# the run lengthens — it asks "is recent daily velocity faster than
# medium-term daily velocity?", which is the actual definition of acceleration.
#
# Threshold 1.10 is sticky enough to hold a name on the radar during the
# final 1-2 day consolidation right before the climax gap (CAR 4/20 had
# daily-ratio 1.11, just clears 1.10 — drops out of 1.15).
_VELOCITY_DAILY_RATIO_MIN = 1.10

# ── Burst checklist thresholds (final 3-5 days) ──────────────────────────────
_MIN_DAYS_UP_STREAK    = 3
_MIN_GAP_COUNT_3D      = 2
_GAP_OPEN_PCT          = 0.01        # open > prior close × 1.01
_MIN_RANGE_EXP_3D      = 2
_MIN_VOL_EXP_3D        = 2
_GAPPED_TODAY_PCT      = 0.02        # today's open > yesterday's close × 1.02

# ── Anticipation promotion: burst items 1-4, need ≥ this many ────────────────
_MIN_ANTICIPATION_SCORE = 3          # 3 of 4 burst items

# ── Climax hard gate: days_up_streak (NOT just a burst component) ────────────
# AGL/XMTR 5/07 incident: both gapped on earnings from tight 3-week bases.
# burst checklist passed 3/4 via gap+range+vol, but days_up=2 (AGL) / 3 (XMTR).
# A real parabolic short setup requires the move into climax day was already
# vertical — multiple consecutive up-days, not a single fresh-news gap.
_MIN_DAYS_UP_STREAK_FOR_CLIMAX = 3

# ── Lookback windows ─────────────────────────────────────────────────────────
_BASE_LOOKBACK_DAYS    = 60
_SMA20_DAYS            = 20
_SMA50_DAYS            = 50
_ROC_SHORT_DAYS        = 5
_ROC_LONG_DAYS         = 20

# ── Market cap cache TTL ─────────────────────────────────────────────────────
_MARKET_CAP_TTL_DAYS   = 30


# ─────────────────────────────────────────────────────────────────────────────
# Cap-tier classification
# ─────────────────────────────────────────────────────────────────────────────

def _classify_cap_tier(market_cap: Optional[int]) -> tuple[str, float]:
    """Return (tier_name, prior_move_threshold). Unknown defaults to mid-cap."""
    if market_cap is None:
        return ("unknown", _PRIOR_MOVE_MID)
    if market_cap >= _LARGE_CAP_USD:
        return ("large", _PRIOR_MOVE_LARGE)
    if market_cap >= _MID_CAP_USD:
        return ("mid", _PRIOR_MOVE_MID)
    return ("small", _PRIOR_MOVE_SMALL)


# ─────────────────────────────────────────────────────────────────────────────
# SMA / ROC helpers (operate on ascending OHLCV row lists)
# ─────────────────────────────────────────────────────────────────────────────

def _sma(rows: list[dict], end_idx: int, window: int) -> Optional[float]:
    """SMA of `close` ending at end_idx inclusive. Returns None if insufficient data."""
    if end_idx + 1 < window:
        return None
    closes = [float(r["close"]) for r in rows[end_idx + 1 - window : end_idx + 1]]
    return sum(closes) / window


def _compute_base_low(rows: list[dict], today_idx: int) -> tuple[Optional[date], Optional[float]]:
    """Walk back from today, find most recent close ≤ SMA-20 within 60d.
    That day's low is the base. If no touch in 60d, anchor at the 60d-ago low.

    Returns (base_date, base_low). (None, None) if insufficient history.
    """
    earliest = max(0, today_idx - _BASE_LOOKBACK_DAYS)
    for i in range(today_idx, earliest - 1, -1):
        sma20 = _sma(rows, i, _SMA20_DAYS)
        if sma20 is None:
            continue
        if float(rows[i]["close"]) <= sma20:
            return (rows[i]["trade_date"], float(rows[i]["low_price"]))
    # No touch in lookback — anchor at the lookback floor's low.
    if today_idx - _BASE_LOOKBACK_DAYS >= 0:
        anchor = rows[today_idx - _BASE_LOOKBACK_DAYS]
        return (anchor["trade_date"], float(anchor["low_price"]))
    return (None, None)


def _roc(rows: list[dict], end_idx: int, window: int) -> Optional[float]:
    """N-day ROC ending at end_idx. (close[end_idx] / close[end_idx-window]) - 1."""
    if end_idx - window < 0:
        return None
    c_now = float(rows[end_idx]["close"])
    c_then = float(rows[end_idx - window]["close"])
    if c_then <= 0:
        return None
    return (c_now / c_then) - 1.0


def _compute_velocity_delta(
    rows: list[dict], today_idx: int
) -> tuple[Optional[float], Optional[float], Optional[bool]]:
    """Velocity-delta gate: daily_compound_rate_5d > 1.10 × daily_compound_rate_20d.

    Daily compound rates: (1 + roc_n) ^ (1/n) − 1. Comparing these (not raw
    ROCs) keeps the test stable as a parabola lengthens — raw 5d ROC is a
    structurally-bounded fraction of raw 20d ROC once the run is weeks deep,
    but the daily compound rate is the per-day rate of price change and is
    directly comparable across windows of any length.

    Returns (roc_5d, roc_20d, passes). `passes` is None if either ROC is
    incomputable, False if 20d isn't positive (no parabola without an uptrend)
    or if 5d collapsed to ≤ -100% (math undefined).
    """
    roc_5d = _roc(rows, today_idx, _ROC_SHORT_DAYS)
    roc_20d = _roc(rows, today_idx, _ROC_LONG_DAYS)
    if roc_5d is None or roc_20d is None:
        return (roc_5d, roc_20d, None)
    if roc_20d <= 0 or roc_5d <= -1:
        return (roc_5d, roc_20d, False)
    daily_5d = (1.0 + roc_5d) ** (1.0 / _ROC_SHORT_DAYS) - 1.0
    daily_20d = (1.0 + roc_20d) ** (1.0 / _ROC_LONG_DAYS) - 1.0
    if daily_20d <= 0:
        return (roc_5d, roc_20d, False)
    return (roc_5d, roc_20d, daily_5d > daily_20d * _VELOCITY_DAILY_RATIO_MIN)


# ─────────────────────────────────────────────────────────────────────────────
# Pure compute function (no DB, no IO) — unit-validate against CAR
# ─────────────────────────────────────────────────────────────────────────────

def compute_parabolic_metrics(
    rows: list[dict],
    market_cap: Optional[int] = None,
    is_earnings_today: Optional[bool] = None,
) -> dict[str, Any]:
    """Score the LAST row in `rows` as a parabolic-short candidate.

    `rows` is OHLCV ascending by trade_date. Each row needs keys:
    `trade_date`, `open_price`, `high_price`, `low_price`, `close`, `volume`.
    Caller is responsible for passing enough history (at least ~60 sessions).

    Returns a dict with every metric value plus the final `stage`.
    `stage ∈ {"unqualified", "anticipation", "climax"}`.

    The detector is intentionally permissive about missing data — anything that
    can't be computed yields `unqualified` with a `reason` explaining why.
    """
    if not rows:
        return {"stage": "unqualified", "reason": "no_rows"}

    today_idx = len(rows) - 1
    today = rows[today_idx]
    # scan_date is derived from rows[-1]["trade_date"] — the caller is responsible
    # for slicing `rows` so its last row matches the intended scan date. Historical
    # replay must use `get_recent_daily_history(..., end_date=...)`; passing today's
    # full history with a scan_date arg would silently disagree (persistence-bug
    # source — see CLAUDE.md 2026-04-25 session 1).
    scan_date = today["trade_date"]
    cap_tier, prior_move_threshold = _classify_cap_tier(market_cap)

    # OHLC + volume must all be present for today's scoring row.
    if any(today.get(k) is None for k in ("open_price", "high_price", "low_price", "close", "volume")):
        return {
            "ticker": None, "scan_date": scan_date, "market_cap": market_cap,
            "cap_tier": cap_tier, "stage": "unqualified", "reason": "missing_ohlcv_today",
            "score": 0,
        }

    base_record: dict[str, Any] = {
        "ticker": None,                    # caller fills in
        "scan_date": scan_date,
        "market_cap": market_cap,
        "cap_tier": cap_tier,
        "prior_move_pct": None,
        "base_date": None,
        "ext_vs_sma20": None,
        "ext_vs_sma50": None,
        "roc_5d": None,
        "roc_20d": None,
        "pullback_count_20d": None,
        "days_up_streak": None,
        "gap_count_3d": None,
        "range_expansion_count_3d": None,
        "vol_expansion_count_3d": None,
        "gapped_today": None,
        "climax_volume_flag": None,
        "score": 0,
        "stage": "unqualified",
        "reason": None,
    }

    close_today = float(today["close"])
    open_today = float(today["open_price"])
    vol_today = float(today["volume"]) if today["volume"] is not None else 0.0

    # ── Gate 1: liquidity ────────────────────────────────────────────────
    dollar_vol_today = close_today * vol_today
    if dollar_vol_today < _MIN_DOLLAR_VOL_TODAY:
        base_record["reason"] = f"dollar_vol_{dollar_vol_today/1e6:.1f}M_below_10M"
        return base_record

    # ── Gate 2: prior move from base ─────────────────────────────────────
    base_date, base_low = _compute_base_low(rows, today_idx)
    base_record["base_date"] = base_date
    if base_low is None or base_low <= 0:
        base_record["reason"] = "no_base_anchor"
        return base_record
    prior_move_pct = (close_today / base_low) - 1.0
    base_record["prior_move_pct"] = prior_move_pct
    if prior_move_pct < prior_move_threshold:
        base_record["reason"] = (
            f"prior_move_{prior_move_pct*100:.0f}%_below_{cap_tier}_"
            f"threshold_{prior_move_threshold*100:.0f}%"
        )
        return base_record

    # ── Gate 3: extension vs SMAs ────────────────────────────────────────
    sma20 = _sma(rows, today_idx, _SMA20_DAYS)
    sma50 = _sma(rows, today_idx, _SMA50_DAYS)
    if sma20 is None or sma50 is None or sma50 <= 0:
        base_record["reason"] = "insufficient_sma_history"
        return base_record
    ext_vs_sma20 = close_today / sma20 if sma20 > 0 else None
    ext_vs_sma50 = close_today / sma50
    base_record["ext_vs_sma20"] = ext_vs_sma20
    base_record["ext_vs_sma50"] = ext_vs_sma50
    if ext_vs_sma50 < _MIN_EXT_VS_SMA50:
        base_record["reason"] = f"ext_sma50_{ext_vs_sma50:.2f}_below_1.5"
        return base_record

    # ── Gate 4: parabolic curve (velocity-delta + few pullbacks) ─────────
    roc_5d, roc_20d, velocity_pass = _compute_velocity_delta(rows, today_idx)
    base_record["roc_5d"] = roc_5d
    base_record["roc_20d"] = roc_20d
    if velocity_pass is None:
        base_record["reason"] = "insufficient_roc_history"
        return base_record
    if not velocity_pass:
        # Surface the daily-rate comparison the gate actually uses.
        daily_5d = ((1 + roc_5d) ** (1/_ROC_SHORT_DAYS) - 1) * 100 if roc_5d is not None and roc_5d > -1 else 0
        daily_20d = ((1 + roc_20d) ** (1/_ROC_LONG_DAYS) - 1) * 100 if roc_20d is not None and roc_20d > 0 else 0
        base_record["reason"] = (
            f"not_accelerating_daily5_{daily_5d:.1f}%_vs_daily20_{daily_20d:.1f}%"
        )
        return base_record

    # Pullback count is telemetry-only (NOT a gate). Velocity-delta is the
    # canonical "parabolic vs linear" discriminator — measuring acceleration
    # of compounding directly. The pullback-count gate was a heuristic from
    # before velocity-delta existed; the two contradicted each other on
    # short-duration parabolas (GME 1/27: velocity ratio 3.6× said screaming
    # parabolic, pullback count said linear because the 20d window straddled
    # the pre-runup chop).
    if today_idx + 1 >= 21:
        pullback_count_20d = 0
        for i in range(today_idx - 19, today_idx + 1):
            if float(rows[i]["close"]) < float(rows[i - 1]["close"]):
                pullback_count_20d += 1
        base_record["pullback_count_20d"] = pullback_count_20d

    # ── Burst checklist (final 3-5d) ────────────────────────────────────
    # 1. days_up_streak (consecutive close > prior close, ending today)
    days_up_streak = 0
    for i in range(today_idx, 0, -1):
        if float(rows[i]["close"]) > float(rows[i - 1]["close"]):
            days_up_streak += 1
        else:
            break
    base_record["days_up_streak"] = days_up_streak

    # 2. gap_count_3d: last 3 sessions where open > prior close × 1.01
    gap_count_3d = 0
    for i in range(today_idx - 2, today_idx + 1):
        if i <= 0:
            continue
        prior_close = float(rows[i - 1]["close"])
        if prior_close > 0 and float(rows[i]["open_price"]) > prior_close * (1 + _GAP_OPEN_PCT):
            gap_count_3d += 1
    base_record["gap_count_3d"] = gap_count_3d

    # 3. range_expansion_count_3d: (high-low) > prior (high-low)
    range_expansion_count_3d = 0
    for i in range(today_idx - 2, today_idx + 1):
        if i <= 0:
            continue
        rng_now = float(rows[i]["high_price"]) - float(rows[i]["low_price"])
        rng_prev = float(rows[i - 1]["high_price"]) - float(rows[i - 1]["low_price"])
        if rng_now > rng_prev:
            range_expansion_count_3d += 1
    base_record["range_expansion_count_3d"] = range_expansion_count_3d

    # 4. vol_expansion_count_3d: volume > prior volume
    vol_expansion_count_3d = 0
    for i in range(today_idx - 2, today_idx + 1):
        if i <= 0:
            continue
        v_now = float(rows[i]["volume"]) if rows[i]["volume"] is not None else 0.0
        v_prev = float(rows[i - 1]["volume"]) if rows[i - 1]["volume"] is not None else 0.0
        if v_now > v_prev:
            vol_expansion_count_3d += 1
    base_record["vol_expansion_count_3d"] = vol_expansion_count_3d

    # 5. gapped_today: today's open > yesterday's close × 1.02
    yclose = float(rows[today_idx - 1]["close"])
    gapped_today = yclose > 0 and open_today > yclose * (1 + _GAPPED_TODAY_PCT)
    base_record["gapped_today"] = gapped_today

    # 6. climax_volume_flag: today's volume = MAX over last 20 sessions
    if today_idx + 1 >= _SMA20_DAYS:
        recent_vols = [
            float(r["volume"]) if r["volume"] is not None else 0.0
            for r in rows[today_idx + 1 - _SMA20_DAYS : today_idx + 1]
        ]
        climax_volume_flag = vol_today >= max(recent_vols) and vol_today > 0
    else:
        climax_volume_flag = False
    base_record["climax_volume_flag"] = climax_volume_flag

    # ── Stage assignment (3-tier: watch / anticipation / climax) ─────────
    # All qualifying gates passed by the time we get here. Burst checklist
    # promotes the candidate up the ladder.
    burst_score = sum([
        days_up_streak >= _MIN_DAYS_UP_STREAK,
        gap_count_3d >= _MIN_GAP_COUNT_3D,
        range_expansion_count_3d >= _MIN_RANGE_EXP_3D,
        vol_expansion_count_3d >= _MIN_VOL_EXP_3D,
    ])
    base_record["score"] = burst_score
    base_record["is_earnings_today"] = is_earnings_today

    # Climax-tier earnings-day exclusion (AGL/XMTR 5/07 incident class:
    # earnings-day gap from a flat base mistaken for parabolic continuation).
    # Earnings gaps are catalyst events, not multi-day acceleration.
    #
    # NOTE 2026-05-08: original ship also had a `days_up_streak >= 3` HARD
    # gate but 30d backtest showed 6 of 16 (38%) climaxes would be filtered,
    # including VECO 5/6 — which was a correctly-anticipated Pradeep setup
    # (3-week run + tight base + breakout 5/7). days_up is a structural
    # signal but a single up-day before climax is the canonical Pradeep
    # entry shape (consolidation → breakout). Reverted to 1-of-4 burst
    # component status. is_earnings_today catches AGL/XMTR/AMD/INTC class
    # cleanly without false-negative on VECO.
    climax_hard_gates_pass = not is_earnings_today

    if (
        burst_score >= _MIN_ANTICIPATION_SCORE
        and gapped_today
        and climax_volume_flag
        and climax_hard_gates_pass
    ):
        base_record["stage"] = "climax"
    elif burst_score >= _MIN_ANTICIPATION_SCORE:
        base_record["stage"] = "anticipation"
    else:
        base_record["stage"] = "watch"

    return base_record


# ─────────────────────────────────────────────────────────────────────────────
# Market cap fetcher with 30-day cache
# ─────────────────────────────────────────────────────────────────────────────

async def _get_or_fetch_market_cap(ticker: str) -> Optional[int]:
    """Return cached market cap if fresh (<30d); else fetch from FMP/yfinance and upsert.

    Returns None if the upstream profile doesn't include marketCap. NULL is
    cached too, so we don't hammer yfinance for known-missing tickers.
    """
    from agents.market_intelligence import db
    from agents.market_intelligence.collector import get_fmp_profile

    cached = await db.get_market_cap(ticker)
    if cached is not None:
        fetched_at = cached["fetched_at"]
        age = datetime.now(timezone.utc) - fetched_at
        if age < timedelta(days=_MARKET_CAP_TTL_DAYS):
            return cached["market_cap"]

    profile = await get_fmp_profile(ticker)
    cap = profile.get("marketCap") if profile else None
    cap_int = int(cap) if cap else None
    await db.upsert_market_cap(ticker, cap_int)
    return cap_int


# ─────────────────────────────────────────────────────────────────────────────
# News-check exclusion (Perplexity)
# ─────────────────────────────────────────────────────────────────────────────

_NEWS_CHECK_PROMPT = (
    "Recent news for ${TICKER}: has there been a buyout, acquisition, merger, "
    "take-private, or other one-shot news event (FDA approval, lawsuit ruling, "
    "earnings surprise) in the last 30 days that drove the share price sharply "
    "higher? "
    "Reply with valid JSON only, no prose:\n"
    "{\"is_event_driven\": true|false, "
    "\"event_type\": \"buyout|acquisition|merger|fda|lawsuit|earnings|other|none\", "
    "\"reason\": \"<one short sentence citing the catalyst>\"}"
)


def _parse_news_verdict(raw: str) -> Optional[dict]:
    """Extract `{is_event_driven, event_type, reason}` from a Perplexity reply.
    Returns None if parsing fails — caller treats that as "no verdict, don't
    exclude" (fail-open). Handles markdown code fences + nested objects."""
    if not raw:
        return None
    s = raw.strip()
    if s.startswith("```"):
        parts = s.split("\n", 1)
        s = parts[1].rstrip("` \n").strip() if len(parts) > 1 else s.strip("` ")
    # Brace-depth-aware extraction (same trick as theme_engine._extract_json_object).
    depth = 0
    start = -1
    for i, ch in enumerate(s):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                s = s[start:i + 1]
                break
    try:
        obj = json.loads(s)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(obj, dict):
        return None
    return {
        "is_event_driven": bool(obj.get("is_event_driven")),
        "event_type": str(obj.get("event_type") or "other"),
        "reason": str(obj.get("reason") or "")[:300],
    }


async def _news_check_for_exclusion(ticker: str) -> Optional[dict]:
    """Ask Perplexity whether `ticker`'s recent move is news-driven. Returns
    `{event_type, reason}` if yes (caller persists exclusion), None if no /
    failed. Errors are swallowed — fail-open is the right default since news
    check is a noise reducer, not a safety gate."""
    from agents.market_intelligence.collector import search_news_perplexity

    query = _NEWS_CHECK_PROMPT.replace("${TICKER}", ticker)
    try:
        raw = await search_news_perplexity(query, recency="month")
    except Exception as e:
        logger.warning(f"parabolic news-check: {ticker} Perplexity call failed: {e}")
        return None
    verdict = _parse_news_verdict(raw)
    if verdict is None:
        logger.warning(f"parabolic news-check: {ticker} unparseable verdict (raw len={len(raw)})")
        return None
    if not verdict["is_event_driven"]:
        return None
    return {
        "event_type": verdict["event_type"],
        "reason": verdict["reason"] or "Event-driven price move per news search",
        "raw": raw[:1000],
    }


async def _apply_exclusions(
    candidates: list[dict],
    trade_date: date,
) -> tuple[list[dict], list[dict]]:
    """For each climax/anticipation candidate, apply manual exclusions first,
    then run a news check on what's left. Returns `(kept, excluded)`. Excluded
    rows have `excluded_reason` / `excluded_source` / `excluded_detail` set;
    `mi_parabolic_candidates` is updated to persist the verdict. Active news
    verdicts are also written to `mi_parabolic_exclusions` with TTL so the
    next scan can short-circuit without another Perplexity call."""
    from agents.market_intelligence import db

    if not candidates:
        return [], []

    # Dedupe by ticker — a stock that promotes anticipation→climax in the same
    # scan would otherwise hit Perplexity twice (gather races past the cache
    # write). Climax wins because it's the higher-priority alert.
    by_ticker: dict[str, dict] = {}
    for c in candidates:
        existing = by_ticker.get(c["ticker"])
        if existing is None or (existing.get("stage") != "climax" and c.get("stage") == "climax"):
            by_ticker[c["ticker"]] = c
    unique_candidates = list(by_ticker.values())

    active = await db.get_active_parabolic_exclusions()
    sem = asyncio.Semaphore(_NEWS_CHECK_CONCURRENCY)

    async def _check(c: dict) -> tuple[dict, Optional[dict]]:
        ticker = c["ticker"]
        # Cache hit. `manual_keep` is the operator's "trust me, don't auto-
        # exclude this" sentinel — short-circuit without calling Perplexity
        # AND without excluding the candidate.
        if ticker in active:
            row = active[ticker]
            if row["source"] == "manual_keep":
                return c, None
            return c, {
                "source": row["source"],
                "reason": row["reason"],
                "detail": row.get("detail"),
            }
        # Cache miss — call Perplexity (climax / anticipation only).
        async with sem:
            verdict = await _news_check_for_exclusion(ticker)
        if not verdict:
            return c, None
        # Persist verdict so the next scan reuses it without another call.
        until = trade_date + timedelta(days=_NEWS_CHECK_TTL_DAYS)
        try:
            await db.add_parabolic_exclusion(
                ticker,
                source="news_check",
                reason=f"{verdict['event_type']}: {verdict['reason']}",
                detail=verdict["raw"],
                excluded_until=until,
            )
        except Exception as e:
            logger.warning(f"parabolic news-check: {ticker} persist failed: {e}")
        return c, {
            "source": "news_check",
            "reason": f"{verdict['event_type']}: {verdict['reason']}",
            "detail": verdict["raw"],
        }

    results = await asyncio.gather(*[_check(c) for c in unique_candidates])

    verdict_by_ticker = {c["ticker"]: v for c, v in results if v is not None}
    kept: list[dict] = []
    excluded: list[dict] = []
    # Walk the original list (not unique_candidates) so a ticker present in
    # both climax and anticipation gets the same verdict applied to both rows.
    for c in candidates:
        verdict = verdict_by_ticker.get(c["ticker"])
        if verdict is None:
            kept.append(c)
            continue
        c["excluded_reason"] = verdict["reason"]
        c["excluded_source"] = verdict["source"]
        c["excluded_detail"] = verdict.get("detail")
        excluded.append(c)
        # Update the persisted candidate row for review-trail.
        try:
            await db.update_parabolic_exclusion(
                c["ticker"], trade_date,
                excluded_reason=verdict["reason"],
                excluded_source=verdict["source"],
                excluded_detail=verdict.get("detail"),
            )
        except Exception as e:
            logger.warning(
                f"parabolic news-check: {c['ticker']} candidate update failed: {e}"
            )
        logger.info(
            f"parabolic_scan: filtered {c['ticker']} ({c.get('stage')}) "
            f"— {verdict['source']}: {verdict['reason']}"
        )
    return kept, excluded


# ─────────────────────────────────────────────────────────────────────────────
# Nightly scan orchestrator (Step 3 — persistence) + Telegram digest (Step 4)
# ─────────────────────────────────────────────────────────────────────────────

async def run_parabolic_scan(trade_date: date) -> dict[str, list[dict]]:
    """Nightly scan: SQL pre-filter → per-ticker compute → persist all rows.

    Every scored ticker gets persisted to `mi_parabolic_candidates` (including
    `unqualified` so we can tune thresholds against historical scans). Returns
    results grouped by stage, used by the Telegram digest.

    Bounded concurrency so the FMP cap-tier fetch (called once per ticker on
    cache miss) doesn't burst the rate limit.
    """
    from agents.market_intelligence import db
    from agents.market_intelligence.strategies.registry import should_run

    if not await should_run("parabolic_short"):
        await db.log_audit_event(
            "strategy_disabled_skip",
            "parabolic_short disabled — skipping nightly scan",
        )
        return {"climax": [], "anticipation": [], "watch": [], "unqualified": []}

    universe = await db.get_parabolic_universe(trade_date)
    by_stage: dict[str, list[dict]] = {
        "climax": [], "anticipation": [], "watch": [], "unqualified": [],
    }
    if not universe:
        logger.info(f"parabolic_scan {trade_date}: empty universe (no tickers passed pre-filter)")
        return by_stage

    logger.info(f"parabolic_scan {trade_date}: scoring {len(universe)} candidates")
    sem = asyncio.Semaphore(_SCAN_CONCURRENCY)

    # Earnings-day exclusion: AGL/XMTR 5/07 class. yfinance is_earnings_day
    # already cached per-ticker per-day inside earnings_calendar.py.
    from agents.market_intelligence.earnings_calendar import is_earnings_day

    async def _score(ticker: str) -> Optional[dict]:
        async with sem:
            try:
                history = await db.get_recent_daily_history(ticker, _HISTORY_DAYS, end_date=trade_date)
                if not history or len(history) < 60:
                    return None
                cap = await _get_or_fetch_market_cap(ticker)
                # is_earnings_day returns (bool, source); fail-soft on any
                # yfinance error → treat as False (don't suppress climax on
                # data outage, which would be the wrong direction).
                try:
                    earnings_today, _src = await is_earnings_day(ticker, trade_date)
                except Exception:
                    earnings_today = False
                metrics = compute_parabolic_metrics(
                    history, market_cap=cap, is_earnings_today=earnings_today,
                )
                metrics["ticker"] = ticker
                await db.insert_parabolic_candidate(metrics)
                return metrics
            except Exception as e:
                logger.error(f"parabolic_scan: {ticker} failed: {e}", exc_info=True)
                return None

    results = await asyncio.gather(*(_score(t) for t in universe))
    for r in results:
        if r is None:
            continue
        by_stage.setdefault(r["stage"], []).append(r)

    # Apply M&A / one-shot-news exclusions to alert-worthy stages only. Watch
    # stage stays untouched (no Telegram alert, no API spend justified). The
    # candidate row persists with `excluded_reason` set, so OGN-class filters
    # are reviewable in `mi_parabolic_candidates` after the fact.
    alert_candidates = by_stage["climax"] + by_stage["anticipation"]
    if alert_candidates:
        kept, excluded = await _apply_exclusions(alert_candidates, trade_date)
        kept_set = {id(c) for c in kept}
        by_stage["climax"] = [c for c in by_stage["climax"] if id(c) in kept_set]
        by_stage["anticipation"] = [c for c in by_stage["anticipation"] if id(c) in kept_set]
        if excluded:
            by_stage["excluded"] = excluded

    logger.info(
        f"parabolic_scan {trade_date}: "
        f"{len(by_stage['climax'])} climax, "
        f"{len(by_stage['anticipation'])} anticipation, "
        f"{len(by_stage['watch'])} watch, "
        f"{len(by_stage['unqualified'])} unqualified, "
        f"{len(by_stage.get('excluded', []))} excluded (M&A/news)"
    )
    return by_stage


def _fmt_candidate(r: dict) -> str:
    """One-line formatter for digest entries."""
    ticker = r["ticker"]
    prior = (r.get("prior_move_pct") or 0) * 100
    ext50 = r.get("ext_vs_sma50") or 0
    cap_tier = r.get("cap_tier") or "?"
    score = r.get("score") or 0
    return f"  • `{ticker}` +{prior:.0f}% from base · {ext50:.1f}× SMA50 · {cap_tier}-cap · burst {score}/4"


async def send_parabolic_digest(by_stage: dict[str, list[dict]]) -> None:
    """Two-section Telegram digest. Suppressed entirely when nothing fired —
    parabolas are rare (Stamatoudis: ~1/month), so silence is the expected
    daily state. Per `feedback_alert_vs_audit`, only ping for terminal/actionable.

    Excluded candidates (M&A, news events, manual bans) are appended as a
    transparency footer so the operator can see what was filtered and why.
    """
    from agents.market_intelligence.briefing import send_telegram_message

    climaxes = sorted(
        by_stage.get("climax", []),
        key=lambda r: r.get("prior_move_pct") or 0,
        reverse=True,
    )
    anticipations = sorted(
        by_stage.get("anticipation", []),
        key=lambda r: r.get("prior_move_pct") or 0,
        reverse=True,
    )
    excluded = by_stage.get("excluded", [])
    if not climaxes and not anticipations and not excluded:
        logger.info("parabolic_scan: zero anticipation, zero climax, zero excluded — digest suppressed")
        return

    lines = ["📉 *Parabolic-short scan*"]
    if climaxes:
        lines.append("")
        lines.append("🔥 *CLIMAX (entry trigger)*")
        for r in climaxes[:5]:
            lines.append(_fmt_candidate(r))
    if anticipations:
        lines.append("")
        lines.append("👀 *ANTICIPATION (watchlist)*")
        for r in anticipations[:10]:
            lines.append(_fmt_candidate(r))
    if excluded:
        lines.append("")
        lines.append(f"🚫 *FILTERED ({len(excluded)})* — excluded as event-driven")
        for r in excluded[:5]:
            ticker = r["ticker"]
            stage = r.get("stage", "?")
            source = r.get("excluded_source") or "?"
            reason = (r.get("excluded_reason") or "").strip()
            lines.append(f"  • `{ticker}` ({stage}) — {source}: {reason[:120]}")
        if len(excluded) > 5:
            lines.append(f"  …{len(excluded) - 5} more")
    # If everything got filtered there's no actionable signal, but we still
    # send the footer so the operator sees the system worked (didn't silently
    # eat OGN-class alerts).
    if not climaxes and not anticipations:
        lines.append("")
        lines.append("_No parabolic-short setups today after filtering._")
    await send_telegram_message("\n".join(lines))
