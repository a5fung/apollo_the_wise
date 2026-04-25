"""
Parabolic-short candidate detector (Stage 1 — telemetry only).

Encodes the Stamatoudis / Qullamaggie parabolic-exhaustion playbook as a
nightly scan. Sources synthesised in `~/.claude/plans/shiny-mapping-locket.md`
(rule citations live there); promotion path lives in
`memory/project_trading_ideas_backlog.md` (TI1).

Three stages emitted per (ticker, scan_date):
  * unqualified  — any qualifying gate fails. Persisted, no alert.
  * anticipation — all gates pass; final-3-5d burst criteria 1-4 satisfied;
                   `gapped_today` not yet. Telegram watchlist.
  * climax       — all gates pass; `gapped_today` true; burst+aux score >= 4/6.
                   Telegram trigger list.

The compute function is pure (`compute_parabolic_metrics(rows, market_cap)`)
so it can be unit-validated against historical CAR data via
`scripts/backfill_parabolic_car.py` before any infrastructure (scheduler,
persistence, Telegram digest) gets wired up.
"""
from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


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

# ── Burst checklist thresholds (final 3-5 days) ──────────────────────────────
_MIN_DAYS_UP_STREAK    = 3
_MIN_GAP_COUNT_3D      = 2
_GAP_OPEN_PCT          = 0.01        # open > prior close × 1.01
_MIN_RANGE_EXP_3D      = 2
_MIN_VOL_EXP_3D        = 2
_GAPPED_TODAY_PCT      = 0.02        # today's open > yesterday's close × 1.02

# ── Climax score (burst items 1-5 + climax_volume_flag = 6 total) ────────────
_MIN_CLIMAX_SCORE      = 4

# ── Lookback windows ─────────────────────────────────────────────────────────
_BASE_LOOKBACK_DAYS    = 60
_SMA20_DAYS            = 20
_SMA50_DAYS            = 50
_SLOPE_WINDOW_DAYS     = 5           # roc_5d_today vs roc_5d_ending_5d_ago

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


def _roc_5d(rows: list[dict], end_idx: int) -> Optional[float]:
    """5-day ROC ending at end_idx. (close[end_idx] / close[end_idx-5]) - 1."""
    if end_idx - _SLOPE_WINDOW_DAYS < 0:
        return None
    c_now = float(rows[end_idx]["close"])
    c_then = float(rows[end_idx - _SLOPE_WINDOW_DAYS]["close"])
    if c_then <= 0:
        return None
    return (c_now / c_then) - 1.0


def _compute_slope_accel(rows: list[dict], today_idx: int) -> Optional[float]:
    """slope_accel = roc_5d_today - roc_5d_ending_5d_ago.

    Positive → recent 5-day move is steeper than the 5-day move before it
    (acceleration). Negative → decelerating, parabola is unwinding.
    """
    recent = _roc_5d(rows, today_idx)
    earlier = _roc_5d(rows, today_idx - _SLOPE_WINDOW_DAYS)
    if recent is None or earlier is None:
        return None
    return recent - earlier


# ─────────────────────────────────────────────────────────────────────────────
# Pure compute function (no DB, no IO) — unit-validate against CAR
# ─────────────────────────────────────────────────────────────────────────────

def compute_parabolic_metrics(
    rows: list[dict],
    market_cap: Optional[int] = None,
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
    scan_date = today["trade_date"]
    cap_tier, prior_move_threshold = _classify_cap_tier(market_cap)

    base_record: dict[str, Any] = {
        "ticker": None,                    # caller fills in
        "scan_date": scan_date,
        "market_cap": market_cap,
        "cap_tier": cap_tier,
        "prior_move_pct": None,
        "base_date": None,
        "ext_vs_sma20": None,
        "ext_vs_sma50": None,
        "slope_accel": None,
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

    # ── Gate 4: parabolic curve (acceleration + few pullbacks) ───────────
    slope_accel = _compute_slope_accel(rows, today_idx)
    base_record["slope_accel"] = slope_accel
    if slope_accel is None or slope_accel <= 0:
        base_record["reason"] = "slope_not_accelerating"
        return base_record

    if today_idx + 1 < 21:                  # need 20 prior closes
        base_record["reason"] = "insufficient_pullback_history"
        return base_record
    pullback_count_20d = 0
    for i in range(today_idx - 19, today_idx + 1):
        if float(rows[i]["close"]) < float(rows[i - 1]["close"]):
            pullback_count_20d += 1
    base_record["pullback_count_20d"] = pullback_count_20d
    if pullback_count_20d >= _MAX_PULLBACK_COUNT_20D:
        base_record["reason"] = f"linear_ascent_{pullback_count_20d}_pullbacks_in_20d"
        return base_record

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

    # ── Stage assignment ─────────────────────────────────────────────────
    burst_1_4_pass = (
        days_up_streak >= _MIN_DAYS_UP_STREAK
        and gap_count_3d >= _MIN_GAP_COUNT_3D
        and range_expansion_count_3d >= _MIN_RANGE_EXP_3D
        and vol_expansion_count_3d >= _MIN_VOL_EXP_3D
    )
    score = sum([
        days_up_streak >= _MIN_DAYS_UP_STREAK,
        gap_count_3d >= _MIN_GAP_COUNT_3D,
        range_expansion_count_3d >= _MIN_RANGE_EXP_3D,
        vol_expansion_count_3d >= _MIN_VOL_EXP_3D,
        gapped_today,
        climax_volume_flag,
    ])
    base_record["score"] = score

    if gapped_today and score >= _MIN_CLIMAX_SCORE:
        base_record["stage"] = "climax"
    elif burst_1_4_pass and not gapped_today:
        base_record["stage"] = "anticipation"
    else:
        base_record["reason"] = (
            f"burst_score_{score}/6_gapped_{gapped_today}_burst1_4_{burst_1_4_pass}"
        )

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
