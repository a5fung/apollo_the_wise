"""
Continuation-flag detector (Stage 1 — pure compute).

Codifies the post-runup VCP / Qullamaggie tightening flag as a daily
state-machine scan. Per-ticker metrics anchor to that ticker's own
pivot-high bar — *not* against rigid global thresholds — because the
shape of the contraction differs by stock and base age.

Five stages emitted per (ticker, scan_date):
  * unqualified  — universe / runup / proximity gates fail. Persisted, no alert.
  * WATCH        — runup present, currently consolidating near highs.
  * TIGHTENING   — at least one of {range, volume} contracting vs early-base.
  * COILED       — range AND volume contracted + small bodies + holding MAs.
  * TRIGGERED    — broke base_high on volume, was COILED-eligible recently.
  * INVALIDATED  — lost base_low / SMA20 / aged out (>25 sessions).
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import date, datetime, time as _dt_time
from statistics import median as _median_stat
from typing import Any, Optional

from agents.market_intelligence.parabolic_detector import _sma

logger = logging.getLogger(__name__)

_SCAN_CONCURRENCY = 8       # bound per-ticker history fetches
_HISTORY_DAYS     = 260     # 40d pole + 25d base + the 200MA / 52w-high Stage-2 gate (needs ~250d)

# ── Universe / runup gates ──────────────────────────────────────────────────
_PIVOT_LOOKBACK_DAYS = 25       # Walk back this far to find pivot-high bar
_PIVOT_HIGH_BAND     = 0.02     # Volume candidate's high must be within 2% of max_high
                                # (was 0.05 — VECO 5/06 case: 5/5 high $52.16 was 2.4%
                                # below period max $53.43 with 3M vol vs 1.5M at the
                                # max-high bar (4/24). Pivot wrongly reset to 5/5 →
                                # base_age=0 → unqualified the day before VECO's +25%
                                # breakout. Tightening keeps non-near-max-high bars
                                # from stealing pivot via volume alone. True blow-off
                                # shooting stars are typically <2% off max anyway.)
_PIVOT_WALK_THRESHOLD = 0.01    # Stable-anchor floor: walk pivot forward only
                                # when the current lookback's max_high beats prior
                                # pivot by ≥ this fraction OR by ≥ 0.25 × ATR-14
                                # (whichever is larger — see _PIVOT_WALK_ATR_MULT).
                                # 1% on $5 stock = 5¢; on a high-ATR runup name
                                # 5¢ is one tick of noise. ATR-relative arm makes
                                # the gate methodology-aware.
_PIVOT_WALK_ATR_MULT = 0.25     # Stable-anchor ATR component. 0.25 × ATR-14 ≈
                                # quarter of a typical day's range. For a $50
                                # name with ATR $5, that's $1.25 (2.5%) vs the
                                # flat 1% floor of $0.50 — the higher gate wins.
                                # For a $100 / ATR $2 name (low vol), flat 1%
                                # = $1 wins over $0.50. Whichever is harder to
                                # cross by accident.
# HTF flagpole (SOURCED — O'Neil/Minervini/Qullamaggie, operator_shared_notes.md 2026-06-22).
# REPLACES the n=1 "50%/60d" (a single-case pick, first commit 2026-05-01, never validated — the
# exact reason Family-A was split into the sourced setups). Spec: flagpole ≥90% in ~8wk.
_RUNUP_LOOKBACK_DAYS = 40       # ~8-wk pole window (spec: C≥1.9×C₄₀ / High₄₀≥1.9×Low₄₀)
_RUNUP_MIN_RATIO     = 1.90     # pivot_high / 40d_low ≥ 1.9×  (flagpole ≥ 90%)
_FLAG_DEPTH_MIN      = 0.75     # flag's ABSOLUTE low ≥ 0.75×pivot_high (≤25% pullback — the "tight")

# Deal-pin M&A signature (Layer 3): once price is pinned at an announced
# deal value, daily ranges collapse to bid-ask noise (~0.2-0.5%). Real
# VCPs run 1.5-3% even when tight, so a strict 0.5% threshold has
# near-zero false-positive risk.
_DEAL_PIN_LOOKBACK_DAYS          = 10
_DEAL_PIN_RANGE_THRESHOLD        = 0.005
_DEAL_PIN_MIN_SUB_THRESHOLD_DAYS = 5
# (Removed 2026-06-27: the #80 runup-scaled proximity band — superseded by the
# HTF flat ≤25% absolute-low depth gate. #80 relaxed the band to ~35% for high-
# runup names, right for a generic flag but wrong for HTF where ≤25% is the
# "tight". Generic-flag recall is now Anticipation's. Rationale at the depth gate.)

# ── Tightening gates ────────────────────────────────────────────────────────
_RANGE_CONTRACTION_MAX = 0.75   # recent_5d / early_5d TR%   — ≤ 0.75 = tight
_VOL_CONTRACTION_MAX   = 0.70   # recent_5d / early_5d vol   — ≤ 0.70 = drying up
_BODY_TIGHTNESS_MAX    = 0.50   # |close-open| / ATR14       — small bodies
_BREAKOUT_VOL_RATIO    = 1.50   # today_vol / 20d_avg_vol    — TRIGGERED gate

# ── Fresh-tightening gates (parallel COILED path for short bases) ───────────
# Fires when last 2 bars are clearly tighter than the post-runup volatility,
# even when base_age is too short for the early-vs-recent window math to
# separate. OKLO 5/4 surfaced the gap: bars 1 and 2 of a 6d base are still in
# both early and recent windows so the ratio sticks near 1.0, but the user
# sees "past 2 sessions are coiling." Fresh path captures that signal directly.
_FRESH_TIGHT_RATIO_MAX     = 0.6   # max(2bar TR%) / ATR14% — ≤ 0.6 = clearly tight
_FRESH_TIGHT_BASE_AGE_MIN  = 4     # relaxed from _BASE_AGE_MIN_COILED (6)

# ── Stage gates ─────────────────────────────────────────────────────────────
_BASE_AGE_MIN_WATCH   = 3
_BASE_AGE_MIN_COILED  = 6
_BASE_AGE_MAX         = 25      # > 25 sessions → INVALIDATED (stale base)
_COILED_LOOKBACK_DAYS = 5       # TRIGGERED requires COILED in last N days
_ATR_WINDOW           = 14
_SMA10_WINDOW         = 10
_SMA20_WINDOW         = 20
_SMA50_WINDOW         = 50      # HTF Stage-2 trend filter (spec: above 10/20/50)
_SMA200_WINDOW        = 200     # Stage-2 long-term trend (above it = a leader, not a crash-recovery)
_STAGE2_NEAR_HIGH_MIN = 0.75    # pole top must be >= 75% of the 52w high (near highs, not -90% in a hole)

_STAGE_ORDER = ("unqualified", "WATCH", "TIGHTENING", "COILED", "TRIGGERED")

# Recency window for "is this a fresh pullback / support test?" Replaces
# day_low (cumulative high-water) with min(low) over last K minutes per
# advisor 2026-05-26 review + #124 backward-check data. Distribution of
# today's 27 events showed median staleness 31min, max 367min; K=30
# preserves bulk of legitimate touches while blocking stale tails.
# Applies to BOTH #95 support-test and #96 MA-pullback.
_INTRADAY_TOUCH_RECENCY_MIN = 30


async def _recent_low_in_window(
    ticker: str, scan_time: datetime, k_minutes: int = _INTRADAY_TOUCH_RECENCY_MIN,
) -> tuple[Optional[float], Optional[datetime]]:
    """Fetch 1-min bars over last k_minutes and return (min_low, low_time).

    Returns (None, None) on fetch failure or no bars in window — caller
    should skip the ticker for the current scan.

    Cost note: 1 Polygon API call per ticker per scan tick. Invoked only
    AFTER existing snapshot-based gates pass, so cost is bounded to
    actual alert candidates (~5-10/scan), not the full watchlist (~25).
    """
    from agents.market_intelligence.collector import _polygon_get
    end_ms = int(scan_time.timestamp() * 1000)
    start_ms = end_ms - (k_minutes * 60_000)
    try:
        data = await _polygon_get(
            f"/v2/aggs/ticker/{ticker}/range/1/minute/{start_ms}/{end_ms}",
            {"adjusted": "true", "sort": "asc", "limit": 100},
        )
    except Exception as e:
        logger.debug(f"recent-low fetch failed for {ticker}: {e}")
        return None, None
    bars = data.get("results") or []
    if not bars:
        return None, None
    lowest = min(bars, key=lambda b: b["l"])
    low_time = datetime.fromtimestamp(lowest["t"] / 1000, tz=scan_time.tzinfo)
    return float(lowest["l"]), low_time


# ─────────────────────────────────────────────────────────────────────────────
# Helpers (operate on ascending OHLCV row lists)
# ─────────────────────────────────────────────────────────────────────────────

def _wilder_tr(bar: dict, prev_close: Optional[float]) -> float:
    """Wilder's true range: max(H-L, |H-C_prev|, |L-C_prev|).

    Falls back to H-L for the first bar in a window (no prev_close available).
    Full-TR computation is non-negotiable for a VCP detector — close-only
    approximations let stocks with wild intraday whips look "tight" if the
    closes happen to land flat. `mi_daily_closes` carries H/L per the
    2026-04-25 OHLC backfill.
    """
    h = float(bar["high_price"])
    l = float(bar["low_price"])
    if prev_close is None:
        return h - l
    pc = float(prev_close)
    return max(h - l, abs(h - pc), abs(l - pc))


def _atr_14(rows: list[dict], end_idx: int) -> Optional[float]:
    """Simple-mean ATR-14 ending at end_idx. Wilder-smoothed EMA overkill for
    the tightness reference point; mean of the last 14 TRs is fine and
    matches what the eyeball-tightness check is comparing against."""
    if end_idx < _ATR_WINDOW:
        return None
    trs = []
    for i in range(end_idx + 1 - _ATR_WINDOW, end_idx + 1):
        prev_close = float(rows[i - 1]["close"]) if i > 0 else None
        trs.append(_wilder_tr(rows[i], prev_close))
    return sum(trs) / len(trs) if trs else None


# RMV ratio-to-baseline calibration. FLOOR = the recent/baseline NTR ratio at which the spring is
# fully coiled (RMV=0); CEILING = the ratio at which volatility is expanding (RMV=100). These are
# CALIBRATABLE from the operator's anticipation-labeling pass (the worksheet that revealed the old
# min-max form was minting false coils) — start at the creator's suggested 0.4 / 1.5.
_RMV_FLOOR = 0.4
_RMV_CEILING = 1.5
# Recent-window NTR floor (percent): if every recent bar's NTR is below this, the recent window is
# range-dead (trading halt / frozen feed / zero-tick days), NOT a coiled spring — return None, not a
# phantom rmv 0 (Gemini-confirmed 2026-06-27). 0.05% sits safely under real ultra-tight coils
# (PAYO 0.14%, NUVL 0.15%) yet above any genuinely halted 3-bar stretch.
_RMV_DEAD_NTR_FLOOR = 0.05


def _ntr(bar: dict, prev_close: Optional[float]) -> Optional[float]:
    """Normalized True Range — the gap-aware Wilder TR as a percent of close. Normalizing by close
    makes RMV price-level neutral (a $10 and a $500 name map onto the same 0-100 scale, no skew).
    Returns None when close is non-positive (degenerate / bad bar)."""
    close = float(bar["close"])
    if close <= 0:
        return None
    return _wilder_tr(bar, prev_close) / close * 100.0


def _compute_rmv(
    rows: list[dict],
    today_idx: int,
    lookback: int = 15,
    current_window: int = 3,
) -> Optional[float]:
    """Relative Measured Volatility (DeepVue / TraderLion) — 0-100 contraction index, low = coiled.

    RATIO-TO-BASELINE form (creator-confirmed 2026-06-27). Compares recent micro-trend volatility to
    the rolling baseline volatility and maps the ratio onto 0-100:
        ratio = mean(NTR over last `current_window` bars) / mean(NTR over last `lookback` bars)
        RMV   = clamp( (ratio - FLOOR) / (CEILING - FLOOR) * 100,  0, 100 )
    where NTR = gap-aware Wilder TR ÷ close × 100 (price-level neutral).

    Why NOT min-max (the prior implementation): min-max normalized today's vol against the [min, max]
    of the window, so a single wide RUNUP bar owned the denominator (ATR_max) and crushed any mildly
    quiet follow-through day to ~0 — flagging "max coil" on the *exhaust* of the preceding move, not a
    real base. That false-positived every post-runup name (operator's 6/27 labeling pass: the entire
    rmv≈0 block was garbage). A ratio to the *average* baseline forces the recent window to be
    legitimately, sustainedly quiet (2-4 bars) before RMV approaches 0.

    Returns None — never 0 — when history is insufficient (today_idx < lookback), a bar's close is
    non-positive, the baseline volatility is 0, or the recent window is range-dead (every recent NTR
    below _RMV_DEAD_NTR_FLOOR — a halt / frozen / dead feed). 0 is a REAL max-coil signal, so these
    degenerate cases must be None: returning 0 there would mint a phantom coil buy on dead data.

    Recorded as telemetry (rmv_5d + rmv_15d); since 2026-06-27 rmv_15d ALSO gates #327's SHADOW
    consolidation-entry (anticipation.is_entry_tight / ENTRY_RMV_MAX) — no longer telemetry-only.
    FLOOR/CEILING are calibratable from the operator's labeling pass.
    """
    if today_idx < lookback or current_window < 1:
        return None

    # NTR for each bar across the baseline window (the recent window is its trailing tail).
    earliest = today_idx - lookback + 1
    ntrs: list[float] = []
    for i in range(earliest, today_idx + 1):
        prev_close = float(rows[i - 1]["close"]) if i > 0 else None
        v = _ntr(rows[i], prev_close)
        if v is None:
            return None  # non-positive close in the window — degenerate
        ntrs.append(v)
    if len(ntrs) < current_window:
        return None
    if max(ntrs[-current_window:]) < _RMV_DEAD_NTR_FLOOR:
        return None  # range-dead recent window (halt / frozen feed) — a void, not a coil (Gemini 2026-06-27)

    base = sum(ntrs) / len(ntrs)
    recent = sum(ntrs[-current_window:]) / current_window
    if base <= 0:
        return None  # dead / frozen feed — never a real coil, do not mint 0

    ratio = recent / base
    rmv = (ratio - _RMV_FLOOR) / (_RMV_CEILING - _RMV_FLOOR) * 100.0
    return max(0.0, min(100.0, rmv))


def _compute_fresh_tightening(
    rows: list[dict], today_idx: int, base_age: int,
    recent_avg_vol: Optional[float] = None,
) -> tuple[bool, Optional[float], Optional[float]]:
    """Last-2-bar tightening relative to ATR-14, with dry-volume confirmation.

    Returns (fires, fresh_2bar_max_tr_pct, atr14_pct). `fires` is True only when:
      - base_age >= _FRESH_TIGHT_BASE_AGE_MIN
      - max(TR% of last 2 bars) ≤ _FRESH_TIGHT_RATIO_MAX × ATR14%
      - max(volume of last 2 bars) ≤ max(recent_avg_vol, 0.5 × ADV20)
        Hybrid reference: recent base avg (matches breakout_vol_ratio
        denominator at L369 — both anchor on contraction floor, not the
        climax-inflated 20d trailing) with an ADV20-floored fallback so a
        single sub-average bar in the recent window can't over-tighten the
        gate. Pure ADV20 was too lenient for post-parabolic names where
        the 20d denominator absorbs runup climax (OKLO 5/4: 14.65M vs
        ADV20 15M = 0.98 barely passing). When recent_avg_vol is None
        (e.g. base_age<2 or unknown), falls back to ADV20-only.

    Designed as a parallel path to the existing range_tight + vol_tight gate,
    not a replacement — kicks in for short bases where early/recent windows
    overlap and the ratio mechanically can't separate.
    """
    if today_idx < 20 or base_age < _FRESH_TIGHT_BASE_AGE_MIN:
        return (False, None, None)
    today = rows[today_idx]
    close_today = float(today["close"])
    if close_today <= 0:
        return (False, None, None)

    # Last 2 bars TR%
    trs_pct: list[float] = []
    for i in (today_idx - 1, today_idx):
        prev_close = float(rows[i - 1]["close"]) if i > 0 else None
        tr = _wilder_tr(rows[i], prev_close)
        c = float(rows[i]["close"])
        trs_pct.append((tr / c * 100.0) if c > 0 else 0.0)
    fresh_max_tr_pct = max(trs_pct)

    atr14 = _atr_14(rows, today_idx)
    if atr14 is None or atr14 <= 0:
        return (False, fresh_max_tr_pct, None)
    atr14_pct = atr14 / close_today * 100.0
    if atr14_pct <= 0:
        return (False, fresh_max_tr_pct, atr14_pct)

    if (fresh_max_tr_pct / atr14_pct) > _FRESH_TIGHT_RATIO_MAX:
        return (False, fresh_max_tr_pct, atr14_pct)

    vols = [float(rows[i]["volume"] or 0) for i in (today_idx - 1, today_idx)]
    adv20_window = [float(rows[i]["volume"] or 0)
                    for i in range(today_idx - 20, today_idx)]
    if len(adv20_window) != 20:
        return (False, fresh_max_tr_pct, atr14_pct)
    adv20 = sum(adv20_window) / 20
    if adv20 <= 0:
        return (False, fresh_max_tr_pct, atr14_pct)

    if recent_avg_vol is not None and recent_avg_vol > 0:
        dry_vol_ceiling = max(recent_avg_vol, 0.5 * adv20)
    else:
        dry_vol_ceiling = adv20
    if max(vols) > dry_vol_ceiling:
        return (False, fresh_max_tr_pct, atr14_pct)

    return (True, fresh_max_tr_pct, atr14_pct)


def _find_pivot_high(
    rows: list[dict],
    today_idx: int,
    prior_pivot_date: Optional[date] = None,
    prior_pivot_high: Optional[float] = None,
) -> tuple[Optional[int], Optional[float]]:
    """Find pivot index (within `rows`) and pivot_high_price.

    Lookback: 25 sessions BEFORE today (today excluded). Anchor = bar with
    highest VOLUME among those whose HIGH is within 2% of max_high in the
    lookback. High-anchored (not close-anchored) so blow-off shooting-star
    reversal days — which carry the runup's true volume climax but close
    well below their high — still get captured.

    Stable-anchor: when `prior_pivot_date`/`prior_pivot_high` are supplied
    AND the prior pivot bar still falls within the current lookback, the
    pivot is held in place unless the current max_high beats prior_pivot_high
    by at least `_PIVOT_WALK_THRESHOLD`. Prevents the pivot from walking
    forward 1¢-at-a-time on a base making slow higher-highs, which leaves
    base_age stuck near zero and starves the contraction window.

    Returns (idx_in_rows, pivot_high_price) or (None, None) if no qualifying
    bar.
    """
    earliest = max(0, today_idx - _PIVOT_LOOKBACK_DAYS)
    lookback = list(range(earliest, today_idx))   # exclude today
    if not lookback:
        return (None, None)
    max_high = max(float(rows[i]["high_price"]) for i in lookback)
    if max_high <= 0:
        return (None, None)

    # Stable-anchor branch: if prior pivot is still within the lookback AND
    # the new max_high doesn't beat it decisively, keep the prior anchor.
    # Look up the prior pivot's index by trade_date — gracefully fall through
    # to fresh re-anchor if the date isn't found (data gap, halt day).
    if (
        prior_pivot_date is not None
        and prior_pivot_high is not None
        and prior_pivot_high > 0
    ):
        prior_idx: Optional[int] = None
        for i in lookback:
            if rows[i]["trade_date"] == prior_pivot_date:
                prior_idx = i
                break
        if prior_idx is not None:
            # ATR-relative walk threshold (filed from #41): take whichever
            # is larger — the flat 1% floor or 0.25× ATR-14. Methodology-aware
            # so a high-ATR runup name needs a real beat, not just one bar
            # of normal volatility. ATR computed on bars ending at prior_idx
            # (history available up to that point); falls back to flat-only
            # if insufficient history.
            atr_at_prior = _atr_14(rows, prior_idx)
            flat_beat = prior_pivot_high * _PIVOT_WALK_THRESHOLD
            atr_beat = (atr_at_prior * _PIVOT_WALK_ATR_MULT) if atr_at_prior else 0.0
            walk_floor = prior_pivot_high + max(flat_beat, atr_beat)
            if max_high <= walk_floor:
                # No decisive break → keep prior anchor. Use the bar's actual
                # current high (in case the row was repaired after the prior
                # scan, e.g. split adjustment); the band recomputes around it.
                return (prior_idx, float(rows[prior_idx]["high_price"]))

    threshold = max_high * (1.0 - _PIVOT_HIGH_BAND)
    candidates = [i for i in lookback if float(rows[i]["high_price"]) >= threshold]
    if not candidates:
        return (None, None)
    pivot_idx = max(candidates, key=lambda i: float(rows[i]["volume"] or 0))
    return (pivot_idx, float(rows[pivot_idx]["high_price"]))


def compute_flag_metrics(
    rows: list[dict],
    ticker: Optional[str] = None,
    rs_rank: Optional[int] = None,
    rs_composite: Optional[float] = None,
    sector: Optional[str] = None,
    yesterday_stage: Optional[str] = None,
    recent_stages: Optional[list[str]] = None,
    prior_pivot_date: Optional[date] = None,
    prior_pivot_high: Optional[float] = None,
) -> dict[str, Any]:
    """Score the LAST row in `rows` as a continuation-flag candidate.

    `rows` is OHLCV ascending by trade_date. Each row needs:
    `trade_date`, `open_price`, `high_price`, `low_price`, `close`, `volume`.
    Caller passes enough history (at least ~60 sessions for runup math).

    `recent_stages` = stages of the last 5 scan_dates (most recent last),
    used for TRIGGERED gate ("was COILED-eligible in last 5 days"). Pass
    empty list during fresh replay.

    Returns a dict with every metric + final `stage`. Hysteresis applied at end:
    a single-day downgrade vs `yesterday_stage` is held one day (except
    INVALIDATED, which fires immediately).
    """
    base = {
        "ticker": ticker,
        "scan_date": rows[-1]["trade_date"] if rows else None,
        "rs_rank": rs_rank,
        "rs_composite": rs_composite,
        "sector": sector,
        "pivot_high_date": None,
        "pivot_high_price": None,
        "base_age": None,
        "base_high": None,
        "base_low": None,
        "runup_pct": None,
        "runup_start_date": None,
        "range_contraction_ratio": None,
        "vol_contraction_ratio": None,
        "last_body_pct": None,
        "prev_body_pct": None,
        "atr_14": None,
        "sma_10": None,
        "sma_20": None,
        "sma_50": None,
        "sma_200": None,
        "high_52w": None,
        "breakout_close": None,
        "breakout_volume_ratio": None,
        "fresh_tight_fires": False,
        "fresh_2bar_tr_pct": None,
        "atr14_pct": None,
        "rmv_5d": None,
        "rmv_15d": None,
        "score": 0,
        "stage": "unqualified",
        "reason": None,
        "held_from_stage": None,
    }

    if not rows:
        base["reason"] = "no_rows"
        return base

    today_idx = len(rows) - 1
    today = rows[today_idx]
    if any(today.get(k) is None for k in ("open_price", "high_price", "low_price", "close", "volume")):
        base["reason"] = "missing_ohlcv_today"
        return base

    close_today = float(today["close"])
    open_today  = float(today["open_price"])
    vol_today   = float(today["volume"] or 0)

    # ── Pivot anchor ─────────────────────────────────────────────────────
    pivot_idx, pivot_high = _find_pivot_high(
        rows, today_idx,
        prior_pivot_date=prior_pivot_date,
        prior_pivot_high=prior_pivot_high,
    )
    if pivot_idx is None:
        base["reason"] = "no_pivot_in_lookback"
        return base
    pivot_close = float(rows[pivot_idx]["close"])
    base["pivot_high_date"]  = rows[pivot_idx]["trade_date"]
    base["pivot_high_price"] = pivot_high

    # ── Base window: strictly between pivot and today ────────────────────
    base_rows = rows[pivot_idx + 1 : today_idx]   # excludes pivot AND today
    base_age = len(base_rows)
    base["base_age"] = base_age

    if base_age < _BASE_AGE_MIN_WATCH:
        base["reason"] = f"base_age_{base_age}_below_{_BASE_AGE_MIN_WATCH}"
        return base

    # Two anchors: intraday extremes (for stop reference / display) and
    # closing extremes (for state-machine gates). Using *closes* for TRIGGERED
    # and INVALIDATED is right because the user trades on closing breakouts —
    # an early-base wicked-up loose bar shouldn't permanently veto a clean
    # closing breakout, and an intraday support test that recovers shouldn't
    # invalidate the structure either.
    base_high       = max(float(r["high_price"]) for r in base_rows)   # intraday — display / stop ref
    base_low        = min(float(r["low_price"])  for r in base_rows)
    base_high_close = max(float(r["close"])      for r in base_rows)   # closing — state gates
    base_low_close  = min(float(r["close"])      for r in base_rows)
    base["base_high"] = base_high
    base["base_low"]  = base_low

    # ── Runup magnitude: pivot_high / min(low) over 60 sessions ending at pivot
    runup_window_start = max(0, pivot_idx - _RUNUP_LOOKBACK_DAYS + 1)
    runup_rows = rows[runup_window_start : pivot_idx + 1]
    if not runup_rows:
        base["reason"] = "runup_window_empty"
        return base
    runup_low = min(float(r["low_price"]) for r in runup_rows)
    if runup_low <= 0:
        base["reason"] = "runup_low_nonpositive"
        return base
    runup_pct = (pivot_high / runup_low) - 1.0
    base["runup_pct"] = runup_pct
    base["runup_start_date"] = next(
        (r["trade_date"] for r in runup_rows if float(r["low_price"]) == runup_low), None
    )
    if (pivot_high / runup_low) < _RUNUP_MIN_RATIO:
        base["reason"] = f"runup_{runup_pct*100:.0f}%_below_90%"
        return base

    # ── Flagpole quality guards (Gemini 6/27) ──────────────────────────────
    # mi_daily_closes is split-ADJUSTED (Polygon grouped-daily, adjusted=true),
    # so reverse-splits shouldn't reach here — but guard the backstop AND require
    # the institutional-volume signature the spec's "undeniable institutional
    # demand" implies:
    #  • data-artifact: a >50% single-day CLOSE jump with NO volume (< 2× the
    #    window avg) is a split / bad tick, not a pole → reject.
    #  • pole-volume: ≥1 day in the window at ≥ 2× the window's avg volume →
    #    real accumulation; 0 spike-days = a slow low-volume "grinder" → reject.
    win_vols = [float(r["volume"] or 0) for r in runup_rows]
    avg_win_vol = (sum(win_vols) / len(win_vols)) if win_vols else 0.0
    spike_days = 0
    for i in range(1, len(runup_rows)):
        prev_c = float(runup_rows[i - 1]["close"])
        cur_c  = float(runup_rows[i]["close"])
        v      = float(runup_rows[i]["volume"] or 0)
        if prev_c > 0 and cur_c / prev_c > 1.50 and avg_win_vol > 0 and v < 2.0 * avg_win_vol:
            base["reason"] = f"flagpole_data_artifact_{cur_c/prev_c:.1f}x_1d_no_vol"
            return base
        if avg_win_vol > 0 and v >= 2.0 * avg_win_vol:
            spike_days += 1
    if avg_win_vol > 0 and spike_days < 1:
        base["reason"] = "flagpole_no_volume_confirmation_grinder"
        return base

    # ── INVALIDATED checks (override everything except actual breakout) ─
    sma_10 = _sma(rows, today_idx, _SMA10_WINDOW)
    sma_20 = _sma(rows, today_idx, _SMA20_WINDOW)
    sma_50 = _sma(rows, today_idx, _SMA50_WINDOW)
    base["sma_10"] = sma_10
    base["sma_20"] = sma_20
    base["sma_50"] = sma_50

    if base_age > _BASE_AGE_MAX:
        base["stage"]  = "INVALIDATED"
        base["reason"] = f"base_age_{base_age}_over_{_BASE_AGE_MAX}"
        return base
    if close_today < base_low_close:
        base["stage"]  = "INVALIDATED"
        base["reason"] = f"close_{close_today:.2f}_below_base_low_close_{base_low_close:.2f}"
        return base
    if sma_20 is not None and close_today < sma_20:
        base["stage"]  = "INVALIDATED"
        base["reason"] = f"close_{close_today:.2f}_below_sma20_{sma_20:.2f}"
        return base
    # Trend filter (SOURCED — Stage-2 uptrend above the MAs; Minervini/O'Neil).
    # Below the 50-day = not a Stage-2 trend → INVALIDATED. The MAs must also be
    # stacked 10≥20≥50 (a proper uptrend) → else unqualified. The 10-day is NOT a
    # close-above floor: a flag routinely tests the 10/20 on a support pullback
    # (that's the stop/trail reference, not a veto). See docs/setups/htf.md.
    if sma_50 is not None and close_today < sma_50:
        base["stage"]  = "INVALIDATED"
        base["reason"] = f"close_{close_today:.2f}_below_sma50_{sma_50:.2f}"
        return base
    if None not in (sma_10, sma_20, sma_50) and not (sma_10 >= sma_20 >= sma_50):
        base["reason"] = f"ma_stack_not_stage2_{sma_10:.1f}/{sma_20:.1f}/{sma_50:.1f}"
        return base
    # ── Stage-2 long-term gate (SOURCED "Stage-2 uptrend", Minervini; operator 6/27
    # NCI catch). The 10/20/50 alone PASSES a sharp CRASH-RECOVERY — the short MAs
    # catch up fast — so NCI (spiked $110 → crashed $4 → bouncing $11 = −90% from its
    # high, BELOW the 200d) slipped through as a "221% flagpole" that was a dead-cat
    # bounce. A real HTF flags NEAR its highs from STRENGTH, so:
    #  • near the 52w high: pivot_high ≥ 75% of the max high over the loaded history;
    #  • above the 200d (when computable): close ≥ sma_200 (a leader, not a broken stock).
    hi_52w = max(float(r["high_price"]) for r in rows)
    base["high_52w"] = hi_52w
    if hi_52w > 0 and pivot_high < _STAGE2_NEAR_HIGH_MIN * hi_52w:
        base["reason"] = (
            f"pole_{pivot_high:.2f}_only_{pivot_high/hi_52w*100:.0f}%_of_52w_high_{hi_52w:.2f}_(not_stage2)"
        )
        return base
    sma_200 = _sma(rows, today_idx, _SMA200_WINDOW)
    base["sma_200"] = sma_200
    if sma_200 is not None and close_today < sma_200:
        base["stage"]  = "INVALIDATED"
        base["reason"] = f"close_{close_today:.2f}_below_sma200_{sma_200:.2f}_(not_stage2)"
        return base

    # ── Flag-depth gate (SOURCED ≤25%, on the ABSOLUTE low — Gemini 6/27) ──
    # The flag's intraday LOW must hold within 25% of the pole top (base_low ≥
    # 0.75×pivot_high). Uses the absolute low, NOT the close: O'Neil/Minervini
    # reject a deep intraday shakeout that rallies to a tight close (the spring
    # uncoiled). REPLACES the old off-pivot-close proximity + its #80 runup-
    # scaling. Why #80 is WRONG for HTF (not just superseded — CHANGE_PROCESS
    # #3): #80 RELAXED the band to ~35% for high-runup names, correct for a
    # GENERIC flag (deeper bases are still valid setups) but WRONG for HTF,
    # where ≤25% tightness is DEFINITIONAL — the "tight" in high-tight-flag.
    # The generic-flag recall #80 served is now Anticipation's job; HTF is the
    # tight subset.
    if base_low < _FLAG_DEPTH_MIN * pivot_high:
        base["reason"] = (
            f"flag_low_{base_low:.2f}_below_{_FLAG_DEPTH_MIN*100:.0f}%_of_pole_{pivot_high:.2f}"
        )
        return base

    # ── Tightening metrics ──────────────────────────────────────────────
    # Use first 5 / last 5 of base; if base_age < 5, both windows = full base
    win = min(5, base_age)
    early = base_rows[:win]
    recent = base_rows[-win:]

    def _tr_pct_at(idx_in_rows: int) -> float:
        prev_close = float(rows[idx_in_rows - 1]["close"]) if idx_in_rows > 0 else None
        tr = _wilder_tr(rows[idx_in_rows], prev_close)
        c  = float(rows[idx_in_rows]["close"])
        return (tr / c * 100.0) if c > 0 else 0.0

    early_idx_set  = [pivot_idx + 1 + i for i in range(win)]
    recent_idx_set = [today_idx - win + i for i in range(win)]   # last `win` base rows = (today_idx - win) ... (today_idx - 1)

    early_tr_pcts  = [_tr_pct_at(i) for i in early_idx_set]
    recent_tr_pcts = [_tr_pct_at(i) for i in recent_idx_set]
    early_med  = _median_stat(early_tr_pcts)  if early_tr_pcts  else 0.0
    recent_med = _median_stat(recent_tr_pcts) if recent_tr_pcts else 0.0
    range_ratio = (recent_med / early_med) if early_med > 0 else None
    base["range_contraction_ratio"] = range_ratio

    early_avg_vol  = sum(float(r["volume"] or 0) for r in early)  / max(1, len(early))
    recent_avg_vol = sum(float(r["volume"] or 0) for r in recent) / max(1, len(recent))
    vol_ratio = (recent_avg_vol / early_avg_vol) if early_avg_vol > 0 else None
    base["vol_contraction_ratio"] = vol_ratio

    # ATR-14 + body tightness on last 2 bars (today + yesterday)
    atr14 = _atr_14(rows, today_idx)
    base["atr_14"] = atr14
    if atr14 and atr14 > 0:
        base["last_body_pct"] = abs(close_today - open_today) / atr14
        if today_idx >= 1:
            prev = rows[today_idx - 1]
            base["prev_body_pct"] = abs(float(prev["close"]) - float(prev["open_price"])) / atr14

    # ── Breakout volume reference: today vs base's recent_5d avg ────────
    # NOT today vs 20d trailing — for a post-parabolic-runup name, the 20d
    # window is half runup-climax volume / half dried-up base volume, which
    # makes the denominator structurally inflated. Today's breakout volume
    # only "looks small" because the climax days are still being averaged
    # in. The right reference is "what did the contraction dry up to" —
    # bursting 1.5× past that is the dry-up-then-burst pattern.
    breakout_vol_ratio = (vol_today / recent_avg_vol) if recent_avg_vol > 0 else None

    # ── Stage classification ────────────────────────────────────────────
    range_tight = range_ratio is not None and range_ratio <= _RANGE_CONTRACTION_MAX
    vol_tight   = vol_ratio   is not None and vol_ratio   <= _VOL_CONTRACTION_MAX
    bodies_tight = (
        base["last_body_pct"] is not None and base["last_body_pct"] <= _BODY_TIGHTNESS_MAX
        and base["prev_body_pct"] is not None and base["prev_body_pct"] <= _BODY_TIGHTNESS_MAX
    )
    ma_aligned = (
        sma_10 is not None and sma_20 is not None
        and close_today >= sma_10 >= sma_20
    )

    # Fresh-tightening complement: catches OKLO-class names where base_age is
    # too short (4-5d) for the early/recent ratio to separate but the last 2
    # bars are clearly tight relative to ATR-14. Computed regardless of stage
    # so the row always carries the metric for offline tuning.
    fresh_fires, fresh_tr_pct, atr14_pct = _compute_fresh_tightening(
        rows, today_idx, base_age, recent_avg_vol=recent_avg_vol,
    )
    base["fresh_tight_fires"]  = fresh_fires
    base["fresh_2bar_tr_pct"]  = fresh_tr_pct
    base["atr14_pct"]          = atr14_pct

    # RMV (Phase 1 telemetry — TI #54). Pure persistence, no gate effect.
    # Computed for every candidate (incl. unqualified) so offline Phase 2
    # divergence analysis has the full distribution. Both 5d (short-base
    # sensitive) and 15d (classic VCP) — Phase 2 picks the more useful
    # window after ≥30 days of data.
    base["rmv_5d"]  = _compute_rmv(rows, today_idx, lookback=5)
    base["rmv_15d"] = _compute_rmv(rows, today_idx, lookback=15)

    # COILED via either path:
    #  (a) existing — full base contraction (range_tight AND vol_tight, age ≥ 6)
    #  (b) fresh    — last-2-bar tight vs ATR (age ≥ 4)
    # Both paths still require bodies_tight + ma_aligned.
    coiled_today = bodies_tight and ma_aligned and (
        (range_tight and vol_tight and base_age >= _BASE_AGE_MIN_COILED)
        or (fresh_fires and base_age >= _FRESH_TIGHT_BASE_AGE_MIN)
    )
    was_coiled_recent = (recent_stages is not None) and (
        "COILED" in recent_stages[-_COILED_LOOKBACK_DAYS:]
    )

    breakout_now = (
        close_today > base_high_close
        and breakout_vol_ratio is not None and breakout_vol_ratio >= _BREAKOUT_VOL_RATIO
    )

    if breakout_now and (coiled_today or was_coiled_recent):
        proposed = "TRIGGERED"
        base["breakout_close"] = close_today
        base["breakout_volume_ratio"] = breakout_vol_ratio
        base["reason"] = (
            f"close_{close_today:.2f}>base_high_close_{base_high_close:.2f} "
            f"vol_{breakout_vol_ratio:.2f}x"
        )
    elif coiled_today:
        proposed = "COILED"
        if fresh_fires and not (range_tight and vol_tight and base_age >= _BASE_AGE_MIN_COILED):
            base["reason"] = (
                f"fresh_2bar {fresh_tr_pct:.1f}%/atr {atr14_pct:.1f}% "
                f"bodies_{base['last_body_pct']:.2f}/{base['prev_body_pct']:.2f}"
            )
        else:
            base["reason"] = (
                f"range_{range_ratio:.2f} vol_{vol_ratio:.2f} "
                f"bodies_{base['last_body_pct']:.2f}/{base['prev_body_pct']:.2f}"
            )
    elif range_tight or vol_tight or fresh_fires:
        proposed = "TIGHTENING"
        rr = f"range_{range_ratio:.2f}" if range_ratio is not None else "range_NA"
        vr = f"vol_{vol_ratio:.2f}"   if vol_ratio   is not None else "vol_NA"
        ft = " fresh" if fresh_fires else ""
        base["reason"] = f"{rr} {vr}{ft}"
    else:
        proposed = "WATCH"
        base["reason"] = (
            f"runup_{runup_pct*100:.0f}% base_{base_age}d "
            f"close_vs_pivot_{(close_today/pivot_high - 1)*100:+.1f}%"
        )

    # ── Score (informational) — count of {runup ✓, base_age ✓, range_tight, vol_tight, bodies_tight}
    base["score"] = sum([
        1,                                     # runup gate already passed if we got here
        1 if base_age >= _BASE_AGE_MIN_COILED else 0,
        1 if range_tight else 0,
        1 if vol_tight else 0,
        1 if bodies_tight else 0,
    ])

    # ── Hysteresis: hold one-day downgrades except INVALIDATED ──────────
    if yesterday_stage and yesterday_stage in _STAGE_ORDER and proposed in _STAGE_ORDER:
        prev_rank = _STAGE_ORDER.index(yesterday_stage)
        new_rank  = _STAGE_ORDER.index(proposed)
        if new_rank < prev_rank:
            base["stage"] = yesterday_stage
            base["held_from_stage"] = proposed
            return base

    base["stage"] = proposed
    return base


async def run_flag_scan(scan_date: date) -> dict[str, list[dict]]:
    """Daily flag-continuation scan: SQL pre-filter → per-ticker compute →
    persist all rows. Mirrors `parabolic_detector.run_parabolic_scan` —
    every scored ticker writes a row (including `unqualified`) so thresholds
    can be retuned offline.

    TRIGGERED rows fire single-ticker Telegram alerts as they're found.
    Daily digest summarizes the rest.
    """
    from agents.market_intelligence import db
    from agents.market_intelligence.strategies.registry import should_run

    if not await should_run("flag_continuation"):
        await db.log_audit_event(
            "strategy_disabled_skip",
            "flag_continuation disabled — skipping daily scan",
        )
        return {"TRIGGERED": [], "COILED": [], "TIGHTENING": [],
                "WATCH": [], "INVALIDATED": [], "unqualified": []}

    # P7.2 (2026-05-17): get_flag_universe now returns dict[ticker, sources]
    # so we can record which universe pattern admitted each ticker. The
    # `universe` list passed downstream is just the keys; sources are
    # threaded into metrics via `universe_sources_map`.
    universe_sources_map = await db.get_flag_universe(scan_date)
    universe = list(universe_sources_map.keys())
    by_stage: dict[str, list[dict]] = {
        "TRIGGERED": [], "COILED": [], "TIGHTENING": [],
        "WATCH": [], "INVALIDATED": [], "unqualified": [],
    }
    if not universe:
        logger.info(f"flag_scan {scan_date}: empty universe")
        return by_stage

    # P7.2 telemetry: log per-source counts
    from collections import Counter as _Counter
    _source_counts = _Counter()
    for _srcs in universe_sources_map.values():
        for _s in _srcs:
            _source_counts[_s] += 1
    logger.info(
        f"flag_scan {scan_date}: universe={len(universe)} | "
        + " ".join(f"{src}={n}" for src, n in _source_counts.most_common())
    )

    yesterday_map, recent_map, rs_map, sector_map, pivot_map = await asyncio.gather(
        db.get_yesterday_flag_stages(scan_date),
        db.get_recent_flag_stages(scan_date, lookback_days=_COILED_LOOKBACK_DAYS),
        db.get_rs_for_tickers(scan_date, universe),
        db.get_sectors_batch(universe),
        db.get_yesterday_flag_pivots(scan_date),
    )

    logger.info(f"flag_scan {scan_date}: scoring {len(universe)} candidates")
    sem = asyncio.Semaphore(_SCAN_CONCURRENCY)

    async def _score(ticker: str) -> Optional[dict]:
        async with sem:
            try:
                history = await db.get_recent_daily_history(ticker, _HISTORY_DAYS, end_date=scan_date)
                if not history or len(history) < 60:
                    return None
                rs = rs_map.get(ticker) or {}
                prior_pivot = pivot_map.get(ticker)
                metrics = compute_flag_metrics(
                    history,
                    ticker=ticker,
                    rs_rank=rs.get("rs_rank"),
                    rs_composite=float(rs["rs_composite"]) if rs.get("rs_composite") is not None else None,
                    sector=sector_map.get(ticker),
                    yesterday_stage=yesterday_map.get(ticker),
                    recent_stages=recent_map.get(ticker, []),
                    prior_pivot_date=prior_pivot[0] if prior_pivot else None,
                    prior_pivot_high=prior_pivot[1] if prior_pivot else None,
                )
                metrics["scan_date"] = scan_date
                # P7.2: record universe-pattern provenance for telemetry
                metrics["universe_sources"] = universe_sources_map.get(ticker, [])
                await db.insert_flag_candidate(metrics)
                if metrics.get("held_from_stage"):
                    await db.log_audit_event(
                        "flag_stage_flip_held",
                        f"{ticker} {metrics['held_from_stage']}→held@{metrics['stage']}",
                        detail=metrics.get("reason") or "",
                    )
                return metrics
            except Exception as e:
                logger.error(f"flag_scan: {ticker} failed: {e}", exc_info=True)
                return None

    results = await asyncio.gather(*(_score(t) for t in universe))

    # M&A filter — only the actionable stages (COILED + TRIGGERED) get the
    # Polygon news lookup. WATCH/TIGHTENING are noise-suppressed in the digest
    # already; gating them at compute time would 5-10x the API cost for no
    # user-visible benefit. Filtered candidates downgrade to `unqualified`
    # with reason="mna_filter:<source>" — preserved in mi_flag_candidates so
    # offline review can audit the filter's hit rate.
    from agents.market_intelligence.ma_filter import is_likely_ma
    actionable = [r for r in results if r is not None and r.get("stage") in ("COILED", "TRIGGERED")]
    if actionable:
        async def _mna_check(r: dict) -> None:
            try:
                is_mna, meta = await is_likely_ma(
                    r["ticker"],
                    check_polygon=True,
                    on_or_before=scan_date,
                    polygon_lookback_days=21,  # base typically forms 6-25d after pivot
                )
                if is_mna:
                    r["original_stage"] = r["stage"]
                    r["stage"] = "unqualified"
                    r["reason"] = f"mna_filter:{(meta or {}).get('source', 'unknown')}"
                    # _score already inserted the row as COILED/TRIGGERED.
                    # Re-upsert so the persisted row reflects the flip.
                    await db.insert_flag_candidate(r)
                    # Filter behavior is ALWAYS applied (re-upsert above);
                    # only audit log is deduped (#89, 2026-05-23). Flag scan
                    # runs once daily but bundle ships consistency across
                    # all 5 mna_filter_fired sites.
                    from agents.market_intelligence.ma_filter import should_log_mna_filter_fired
                    if await should_log_mna_filter_fired(r["ticker"], "flag"):
                        await db.log_audit_event(
                            "mna_filter_fired",
                            f"{r['ticker']} via {(meta or {}).get('source', 'unknown')} (flag)",
                            detail=str({"detector": "flag", "stage": r['original_stage'], **(meta or {})})[:500],
                        )
            except Exception as e:
                logger.warning(f"flag_scan: M&A check failed for {r['ticker']}: {e}")

        await asyncio.gather(*(_mna_check(r) for r in actionable))

        # Layer 3 M&A backstop: deal-pin price signature.
        # KALV 2026-05-11 surfaced the case where Polygon has ZERO news on
        # an M&A target (small biotech, recent announcement, or coverage
        # gap) → L0+L1+L2 all miss. The price action itself is the tell:
        # once price is pinned at the deal value, daily range collapses to
        # bid-ask noise (~0.2-0.5%). Real VCPs have 1.5-3% daily ranges
        # even when tight, so a strict 0.5% threshold has near-zero
        # false-positive risk against legitimate continuation flags.
        # Filter criteria (require all): median (H-L)/C over last 10
        # sessions < 0.5%, AND ≥5 sessions sub-0.5%. KALV today:
        # median 0.22%, 8 of 9 sessions sub-0.5%, vs SXT 3.2% / SEI 6.0%
        # also-COILED → KALV cleanly outlier.
        still_actionable = [
            r for r in actionable if r.get("stage") in ("COILED", "TRIGGERED")
        ]
        if still_actionable:
            try:
                pin_map = await _check_deal_pin_signatures_batch(
                    [r["ticker"] for r in still_actionable], scan_date,
                )
            except Exception as e:
                logger.warning(f"flag_scan: deal-pin batch query failed: {e}")
                pin_map = {}

            async def _deal_pin_check(r: dict) -> None:
                try:
                    sig = pin_map.get(r["ticker"])
                    if sig and sig.get("is_pin"):
                        r["original_stage"] = r["stage"]
                        r["stage"] = "unqualified"
                        r["reason"] = "mna_filter:deal_pin_signature"
                        await db.insert_flag_candidate(r)
                        # Same-trading-day audit dedup (#89). Same detector
                        # tag as the keyword-match flag site above — both
                        # share `(flag)` suffix; dedup is per (ticker,
                        # detector) so first-of-day wins regardless of
                        # which sub-path (keyword vs deal_pin) fires first.
                        from agents.market_intelligence.ma_filter import should_log_mna_filter_fired
                        if await should_log_mna_filter_fired(r["ticker"], "flag"):
                            await db.log_audit_event(
                                "mna_filter_fired",
                                f"{r['ticker']} via deal_pin_signature (flag) — "
                                f"median {sig['median_range_pct']:.3%}, "
                                f"{sig['sub_threshold_days']}/{sig['total_days']} sub-0.5%",
                                detail=str({
                                    "detector": "flag",
                                    "stage": r["original_stage"],
                                    "source": "deal_pin_signature",
                                    **sig,
                                })[:500],
                            )
                except Exception as e:
                    logger.warning(
                        f"flag_scan: deal-pin check failed for {r['ticker']}: {e}"
                    )

            await asyncio.gather(*(_deal_pin_check(r) for r in still_actionable))

    for r in results:
        if r is None:
            continue
        by_stage.setdefault(r["stage"], []).append(r)

    logger.info(
        f"flag_scan {scan_date}: "
        f"{len(by_stage['TRIGGERED'])} triggered, "
        f"{len(by_stage['COILED'])} coiled, "
        f"{len(by_stage['TIGHTENING'])} tightening, "
        f"{len(by_stage['WATCH'])} watch, "
        f"{len(by_stage['INVALIDATED'])} invalidated, "
        f"{len(by_stage['unqualified'])} unqualified"
    )

    # TRIGGERED rows surface in the digest's TRIGGERED section (same minute,
    # same details). Per-ticker alerts deleted as duplicate noise.
    await send_flag_digest(by_stage, scan_date, yesterday_map=yesterday_map)

    # Post-EOD reconciliation for intraday flag-breaks (#94, ADR 0005,
    # 2026-05-23). Flips mi_flag_breaks.parent_invalidated_eod=TRUE for
    # any same-day break whose parent ticker is now INVALIDATED. Backward-
    # check evidence script filters via parent_invalidated_eod=FALSE.
    # Non-blocking; reconciliation failure doesn't break flag scan output.
    try:
        await reconcile_flag_state_post_eod(scan_date)
    except Exception as e:
        logger.warning(f"reconcile_flag_state_post_eod failed (non-critical): {e}")

    return by_stage


def _evaluate_deal_pin(rows: list) -> Optional[dict]:
    """Pure-function evaluator: turn a ticker's daily H/L/C rows into a deal-pin signature dict."""
    if len(rows) < _DEAL_PIN_MIN_SUB_THRESHOLD_DAYS:
        return None
    ranges = [
        (float(r["high_price"]) - float(r["low_price"])) / float(r["close"])
        for r in rows
    ]
    ranges_sorted = sorted(ranges)
    median = ranges_sorted[len(ranges_sorted) // 2]
    sub = sum(1 for x in ranges if x < _DEAL_PIN_RANGE_THRESHOLD)
    return {
        "median_range_pct": median,
        "sub_threshold_days": sub,
        "total_days": len(rows),
        "is_pin": (
            median < _DEAL_PIN_RANGE_THRESHOLD
            and sub >= _DEAL_PIN_MIN_SUB_THRESHOLD_DAYS
        ),
        "range_threshold": _DEAL_PIN_RANGE_THRESHOLD,
    }


async def _check_deal_pin_signatures_batch(
    tickers: list[str],
    scan_date: date,
) -> dict[str, dict]:
    """Batch version: one DB round-trip for N tickers' last _DEAL_PIN_LOOKBACK_DAYS bars.

    Returns {ticker: signature_dict} for every ticker with enough data;
    tickers with insufficient history are omitted (caller fails open).
    """
    if not tickers:
        return {}
    from agents.market_intelligence.db import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT ticker, high_price, low_price, close
            FROM (
                SELECT
                    ticker, high_price, low_price, close,
                    ROW_NUMBER() OVER (
                        PARTITION BY ticker ORDER BY trade_date DESC
                    ) AS rn
                FROM mi_daily_closes
                WHERE ticker = ANY($1)
                  AND trade_date <= $2
                  AND high_price IS NOT NULL
                  AND low_price IS NOT NULL
                  AND close IS NOT NULL
                  AND close > 0
            ) sub
            WHERE rn <= $3
            """,
            tickers, scan_date, _DEAL_PIN_LOOKBACK_DAYS,
        )
    by_ticker: dict[str, list] = {}
    for r in rows:
        by_ticker.setdefault(r["ticker"], []).append(r)
    out: dict[str, dict] = {}
    for ticker, ticker_rows in by_ticker.items():
        sig = _evaluate_deal_pin(ticker_rows)
        if sig is not None:
            out[ticker] = sig
    return out


def _fmt_pct(v: Optional[float], digits: int = 0, sign: bool = False) -> str:
    if v is None:
        return "—"
    fmt = f"{{:+.{digits}f}}%" if sign else f"{{:.{digits}f}}%"
    return fmt.format(v * 100)


def _fmt_ratio(v: Optional[float]) -> str:
    return f"{v:.2f}" if v is not None else "—"


def _fmt_coiled(r: dict) -> str:
    rr = r.get("range_contraction_ratio")
    vr = r.get("vol_contraction_ratio")
    runup = r.get("runup_pct")
    age = r.get("base_age")
    return (
        f"  • `{r['ticker']}` — base {age}d · runup {_fmt_pct(runup, 0, sign=True)} · "
        f"range {_fmt_ratio(rr)} · vol {_fmt_ratio(vr)}"
    )


def _fmt_triggered(r: dict) -> str:
    runup = r.get("runup_pct")
    age = r.get("base_age")
    bvr = r.get("breakout_volume_ratio")
    close = r.get("breakout_close")
    bh = r.get("base_high")
    return (
        f"  • `{r['ticker']}` — base {age}d · runup {_fmt_pct(runup, 0, sign=True)} · "
        f"vol {_fmt_ratio(bvr)}× · close ${close:.2f} > ${bh:.2f}"
        if close is not None and bh is not None else
        f"  • `{r['ticker']}` — base {age}d · runup {_fmt_pct(runup, 0, sign=True)} · vol {_fmt_ratio(bvr)}×"
    )


async def send_flag_digest(
    by_stage: dict[str, list[dict]],
    scan_date: date,
    yesterday_map: Optional[dict[str, str]] = None,
) -> None:
    """Compact daily digest — TRIGGERED + COILED + new-TIGHTENING +
    DROPPED-OUT (INVALIDATED). Suppressed entirely on quiet days
    (no triggered, no coiled, no fresh tightening).

    WATCH-only stocks are silenced — too noisy at 40-50/day. They live in
    `mi_flag_candidates` and surface via `/flags watch` on demand.
    """
    from agents.market_intelligence.briefing import send_telegram_message

    triggered    = by_stage.get("TRIGGERED", [])
    coiled       = by_stage.get("COILED", [])
    tightening   = by_stage.get("TIGHTENING", [])
    watch        = by_stage.get("WATCH", [])
    invalidated  = by_stage.get("INVALIDATED", [])

    if yesterday_map is None:
        from agents.market_intelligence import db
        yesterday_map = await db.get_yesterday_flag_stages(scan_date)
    new_tightening = [r for r in tightening if yesterday_map.get(r["ticker"]) in (None, "WATCH")]

    if not (triggered or coiled or new_tightening):
        logger.info("flag_scan: zero triggered/coiled/new-tightening — digest suppressed")
        return

    universe_total = sum(len(v) for v in by_stage.values())
    date_str = f"{scan_date.strftime('%b')} {scan_date.day}" if hasattr(scan_date, "strftime") else str(scan_date)
    lines = [
        f"🚩 *HTF Scanner — {date_str}*",
        f"_{universe_total} tickers scanned · "
        f"{len(watch)} watch · {len(tightening)} tightening · "
        f"{len(coiled)} coiled · {len(triggered)} triggered_",
    ]

    if triggered:
        lines.append("")
        lines.append(f"🎯 *TRIGGERED ({len(triggered)})*")
        for r in sorted(triggered, key=lambda x: x.get("runup_pct") or 0, reverse=True):
            lines.append(_fmt_triggered(r))

    if coiled:
        lines.append("")
        lines.append(f"🌀 *COILED — actionable setup ({len(coiled)})*")
        for r in sorted(coiled, key=lambda x: x.get("range_contraction_ratio") or 1)[:8]:
            lines.append(_fmt_coiled(r))
        if len(coiled) > 8:
            lines.append(f"  …{len(coiled) - 8} more")

    if new_tightening:
        names = ", ".join(r["ticker"] for r in new_tightening[:12])
        more = f" …+{len(new_tightening) - 12}" if len(new_tightening) > 12 else ""
        lines.append("")
        lines.append(f"🔧 *NEW TIGHTENING ({len(new_tightening)})*")
        lines.append(f"  {names}{more}")

    if invalidated:
        lines.append("")
        lines.append(f"📉 *DROPPED OUT ({len(invalidated)})*")
        for r in invalidated[:5]:
            reason = (r.get("reason") or "").split("_")[0:3]
            short = " ".join(reason) if reason else "invalidated"
            lines.append(f"  • `{r['ticker']}` ({short})")
        if len(invalidated) > 5:
            lines.append(f"  …{len(invalidated) - 5} more")

    await send_telegram_message("\n".join(lines))


# ────────────────────────────────────────────────────────────────────────
# Consolidated EOD digest for the 5 intraday entry-technique shadow detectors
# (#168 noise fix, 2026-06-07). Replaces ~23/day per-tick pings (now default-off)
# with ONE 16:00 ET roll-up. Reads the persisted tables only — detection +
# telemetry are unchanged; this is purely the surfacing layer.
# ────────────────────────────────────────────────────────────────────────

# (table, date_col, emoji, label) — every intraday entry-technique detector.
_INTRADAY_SIGNAL_TABLES = [
    ("mi_flag_breaks",         "break_date",    "🎯", "Flag-break"),
    ("mi_flag_ma_pullbacks",   "pullback_date", "📉", "MA-pullback"),
    ("mi_flag_support_tests",  "test_date",     "🛡", "Support-test"),
    ("mi_flag_undercut_rally", "ur_date",       "↩️", "Undercut&Rally"),
    ("mi_flag_low_vol_rests",  "rest_date",     "😴", "Low-vol-rest"),
]


def _build_intraday_signals_digest(scan_date, per_detector) -> Optional[str]:
    """Pure formatter for the EOD entry-technique digest.

    `per_detector`: list of (emoji, label, [(ticker, in_cohort_bool), ...]).
    Returns the message, or None when EVERY detector is empty (suppress on
    zero-fire days — no message at all).
    """
    sections, total = [], 0
    for emoji, label, rows in per_detector:
        if not rows:
            continue
        total += len(rows)
        names = ", ".join(("🍬" if c else "") + t for t, c in rows[:15])
        more = f" …+{len(rows) - 15}" if len(rows) > 15 else ""
        sections.append(f"{emoji} *{label}* ({len(rows)}): {names}{more}")
    if not sections:
        return None
    date_str = scan_date.strftime("%b %d") if hasattr(scan_date, "strftime") else str(scan_date)
    return "\n".join([
        f"📋 *Stocks-in-Play — entry-technique signals · {date_str}*",
        f"_{total} shadow signals across {len(sections)} techniques · telemetry only, no entries._",
        "",
        *sections,
        "",
        "_Drill-down: `/detectors` · shadow eval pending N≥10._",
    ])


async def run_intraday_signals_eod_digest(scan_date) -> int:
    """One consolidated EOD digest of the day's intraday entry-technique signals
    (#168). Reads each detector's table for `scan_date`, sends ONE message, and
    suppresses entirely on zero-fire days. Error-isolated per table — a missing
    table (e.g. a detector not yet shipped) skips that section, never the digest.
    """
    from agents.market_intelligence import db
    from agents.market_intelligence.briefing import send_telegram_message
    pool = await db.get_pool()
    per_detector = []
    async with pool.acquire() as conn:
        for table, dcol, emoji, label in _INTRADAY_SIGNAL_TABLES:
            try:
                rows = await conn.fetch(
                    f"SELECT ticker, COALESCE(in_sugar_baby_cohort, false) AS coh "
                    f"FROM {table} WHERE {dcol} = $1 ORDER BY ticker",
                    scan_date,
                )
            except Exception as e:
                logger.warning(f"intraday signals digest: {table} skipped — {e}")
                rows = []
            per_detector.append((emoji, label, [(r["ticker"], r["coh"]) for r in rows]))
    msg = _build_intraday_signals_digest(scan_date, per_detector)
    if msg is None:
        logger.info("intraday signals EOD digest: zero fires — suppressed")
        return 0
    await send_telegram_message(msg)
    return sum(len(rows) for _, _, rows in per_detector)


# ────────────────────────────────────────────────────────────────────────
# Intraday flag-break detector (#94, ADR 0005, 2026-05-23 ship Commit 1)
# ────────────────────────────────────────────────────────────────────────
#
# The EOD `run_flag_scan` above is the IDENTIFICATION layer — it knows
# which stocks have tight bases + persists `base_high` and `base_low`
# per ticker. But classifying TRIGGERED at 5:25 PM ET means we observe
# the breakout AFTER intraday move has played out. Per #92 evidence,
# entering at next-day open shows -2.66% avg 10d returns + -2.03%
# overnight fade — the EOD measurement is structurally post-hoc.
#
# This detector adds the EXECUTION layer: real-time 5-min scan during
# market hours that fires when price tags base_high with volume
# confirmation. Telemetry-only first ship (shadow phase). Forward-
# return analysis at N>=10 settled (filed via data_gated_reviews YAML
# in Commit 2).

# Volume gate thresholds (per Gemini 2026-05-23 review):
_INTRADAY_BREAK_OPENING_MIN_VOL_FRAC = 0.15  # before 10:00 AM ET, today_vol >= 15% ADV
_INTRADAY_BREAK_OPENING_WINDOW_MIN = 30      # apply opening guard for first 30 min


async def run_intraday_flag_break_scan(scan_time):
    """Intraday range-break detection on TIGHTENING/COILED/TRIGGERED tickers.

    Reads the most-recent flag-classification (MAX(scan_date) WHERE
    scan_date < CURRENT_DATE — trading-session-aware), filters to
    stage IN (TIGHTENING, COILED, TRIGGERED). For each candidate
    ticker, checks if current price > base_high AND volume-pace
    projection clears ADV (with opening-30min raw-volume floor to
    prevent block-trade false positives). New breaks are inserted
    into mi_flag_breaks (UNIQUE on ticker+break_date) and the
    consolidated Telegram alert fires.

    Args:
        scan_time: datetime in ET timezone

    Returns:
        int: count of new breaks inserted this scan
    """
    from agents.market_intelligence import db
    from agents.market_intelligence.collector import get_snapshot_all

    # Time gate (the cron is */5; we don't want pre-9:35 or post-3:55)
    if not (_dt_time(9, 35) <= scan_time.time() <= _dt_time(15, 55)):
        return 0

    minutes_since_open = (scan_time.hour - 9) * 60 + scan_time.minute - 30
    if minutes_since_open <= 0:
        return 0

    pool = await db.get_pool()
    async with pool.acquire() as conn:
        # 1. Load latest pre-today flag classification for TIGHTENING/COILED/TRIGGERED.
        # MAX(scan_date) WHERE < CURRENT_DATE handles Memorial Day Monday correctly
        # (Tuesday morning reads Friday's scan, not Monday calendar-day).
        # Idempotency guard (#145, 2026-05-28): exclude candidates whose prior
        # bar already closed above base_high. ADTN/IREN 2026-05-27 broke from
        # TIGHTENING with no intervening COILED stage; flag_detector's TRIGGERED
        # branch requires COILED prerequisite (line 635) so they stayed
        # TIGHTENING despite close > base_high_close. Without this guard,
        # the next day's intraday detector treats them as still-pre-break and
        # false-fires. Per user principle 2026-05-28: "if it breaks the range,
        # it's a flag break" — a break already realized yesterday isn't a
        # fresh break today.
        candidates = await conn.fetch("""
            WITH latest AS (
                SELECT MAX(scan_date) AS d FROM mi_flag_candidates
                WHERE scan_date < CURRENT_DATE
            )
            SELECT DISTINCT ON (c.ticker)
                   c.ticker, c.scan_date, c.stage, c.base_high, c.base_low, c.base_age
            FROM mi_flag_candidates c
            LEFT JOIN mi_daily_closes dc
                   ON dc.ticker = c.ticker
                  AND dc.trade_date = c.scan_date
            WHERE c.scan_date = (SELECT d FROM latest)
              AND c.stage IN ('TIGHTENING', 'COILED', 'TRIGGERED')
              AND c.base_high IS NOT NULL
              AND c.base_high > 0
              AND (dc.close IS NULL OR dc.close <= c.base_high)
            ORDER BY c.ticker, c.scan_date DESC
        """)
        if not candidates:
            return 0

        watchlist = {r["ticker"]: dict(r) for r in candidates}

        # 2. Sugar Baby cohort membership (read-side decoration only, NOT filter)
        cohort_rows = await conn.fetch("""
            SELECT ticker, count_9m_alerts_180d
            FROM mi_sugar_babies_cohort
            WHERE cohort_date = (SELECT MAX(cohort_date) FROM mi_sugar_babies_cohort)
        """)
        cohort_map = {r["ticker"]: r["count_9m_alerts_180d"] for r in cohort_rows}

        # 3. Pre-fetch ADV-20 for the watchlist tickers (single batch query).
        # PERCENTILE_CONT(0.5) median, matching db.get_adv_from_daily_closes
        # SSoT — median is spike-immune (a single 5x-volume day distorts
        # mean but not median). Mean ADV would silently let block-trade
        # gappers fail the volume gate during normal sessions.
        adv_rows = await conn.fetch("""
            SELECT ticker,
                   PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY volume) AS adv_20
            FROM (
                SELECT ticker, volume,
                       ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY trade_date DESC) AS rn
                FROM mi_daily_closes
                WHERE ticker = ANY($1::text[])
                  AND trade_date >= CURRENT_DATE - INTERVAL '40 days'
                  AND volume > 0
            ) sub
            WHERE rn <= 20
            GROUP BY ticker
        """, list(watchlist.keys()))
        adv_map = {r["ticker"]: int(r["adv_20"] or 0) for r in adv_rows}

        # 4. Tickers already broken today (skip — UNIQUE-constraint dedup)
        already_broken = await conn.fetch("""
            SELECT ticker FROM mi_flag_breaks WHERE break_date = CURRENT_DATE
        """)
        already_set = {r["ticker"] for r in already_broken}

    # 5. Batch snapshot fetch (single Polygon API call).
    snapshots = await get_snapshot_all()
    if not snapshots:
        logger.warning("intraday_flag_break_scan: empty snapshot fetch; skipping")
        return 0

    # 6. Per-ticker detection
    new_breaks: list[dict] = []
    for ticker, cand in watchlist.items():
        if ticker in already_set:
            continue
        snap = snapshots.get(ticker)
        if not snap:
            continue
        # Same price fallback chain as 9M scan
        current_price = (
            snap.get("day", {}).get("c")
            or snap.get("min", {}).get("c")
            or snap.get("lastTrade", {}).get("p")
            or 0
        )
        if current_price <= 0:
            continue

        base_high = float(cand["base_high"])
        if current_price <= base_high:
            continue  # no break

        today_volume = int(snap.get("day", {}).get("v") or 0)
        adv_20 = adv_map.get(ticker, 0)
        if adv_20 <= 0 or today_volume <= 0:
            continue  # need volume context

        # Volume-pace projection: full-day pace must meet ADV
        projected_full_day = int(today_volume * (390.0 / minutes_since_open))
        if projected_full_day < adv_20:
            continue

        # Opening-30min block-trade guard (per Gemini 2026-05-23):
        # before 10:00 AM ET, additionally require raw absolute floor
        # to prevent single-print institutional blocks forging false projections.
        if minutes_since_open < _INTRADAY_BREAK_OPENING_WINDOW_MIN:
            if today_volume < adv_20 * _INTRADAY_BREAK_OPENING_MIN_VOL_FRAC:
                continue

        pct_above = (current_price - base_high) / base_high * 100.0
        volume_pct = today_volume / adv_20 * 100.0
        in_cohort = ticker in cohort_map

        new_breaks.append({
            "ticker": ticker,
            "minutes_since_open": minutes_since_open,
            "parent_stage": cand["stage"],
            "parent_scan_date": cand["scan_date"],
            "base_high": base_high,
            "base_low": float(cand["base_low"]) if cand["base_low"] else None,
            "base_age": cand["base_age"],
            "break_price": current_price,
            "pct_above_base_high": pct_above,
            "today_volume": today_volume,
            "adv_20": adv_20,
            "volume_pct_of_adv": volume_pct,
            "projected_full_day_volume": projected_full_day,
            "in_sugar_baby_cohort": in_cohort,
            "cohort_count_180d": cohort_map.get(ticker),
        })

    if not new_breaks:
        return 0

    # 7. Persist + audit + Telegram (consolidated single message)
    async with pool.acquire() as conn:
        for b in new_breaks:
            await conn.execute("""
                INSERT INTO mi_flag_breaks (
                    ticker, break_date, break_time, minutes_since_open,
                    parent_stage, parent_scan_date, base_high, base_low, base_age,
                    break_price, pct_above_base_high,
                    today_volume, adv_20, volume_pct_of_adv, projected_full_day_volume,
                    in_sugar_baby_cohort, cohort_count_180d
                ) VALUES (
                    $1, CURRENT_DATE, NOW(), $2,
                    $3, $4, $5, $6, $7,
                    $8, $9,
                    $10, $11, $12, $13,
                    $14, $15
                )
                ON CONFLICT (ticker, break_date) DO NOTHING
            """,
                b["ticker"], b["minutes_since_open"],
                b["parent_stage"], b["parent_scan_date"],
                b["base_high"], b["base_low"], b["base_age"],
                b["break_price"], b["pct_above_base_high"],
                b["today_volume"], b["adv_20"], b["volume_pct_of_adv"],
                b["projected_full_day_volume"],
                b["in_sugar_baby_cohort"], b["cohort_count_180d"],
            )
            # Audit event — contract per ADR 0005 §discipline:
            #   {TICKER} stage={stage} pct_above={X.X}% vol_pct_adv={Y}%
            try:
                await db.log_audit_event(
                    "intraday_flag_break",
                    f"{b['ticker']} stage={b['parent_stage']} "
                    f"pct_above={b['pct_above_base_high']:+.1f}% "
                    f"vol_pct_adv={b['volume_pct_of_adv']:.0f}%"
                )
            except Exception as e:
                logger.debug(f"intraday_flag_break audit failed (non-critical): {e}")

    # Per-tick Telegram OFF by default for this shadow detector (#168 noise fix,
    # 2026-06-07). DB writes + audit still fire; the day's breaks are surfaced in
    # ONE 16:00 ET consolidated digest (run_intraday_signals_eod_digest) instead
    # of ~7 per-tick pings. Toggle SHADOW_DETECTOR_TELEGRAM_ENABLED=true to
    # re-enable per-tick (e.g. a #168 graduation experiment) — DEFAULT FALSE so a
    # DR restore / fresh env can't silently bring the noise back (code is SoT).
    if os.environ.get("SHADOW_DETECTOR_TELEGRAM_ENABLED", "false").lower() == "true":
        try:
            from agents.market_intelligence.briefing import send_telegram_message
            clock = scan_time.strftime("%H:%M")
            lines = [
                f"🎯 *Intraday Flag-Breaks ({len(new_breaks)} new)*",
                f"_5-min scan at {clock} ET — telemetry only, no entries submitted._",
                "",
            ]
            for b in new_breaks:
                cohort_marker = "🍬 " if b["in_sugar_baby_cohort"] else ""
                lines.append(
                    f"• {cohort_marker}`{b['ticker']}` — broke ${b['base_high']:.2f} "
                    f"at {b['pct_above_base_high']:+.1f}% "
                    f"(base {b['base_age']}d {b['parent_stage']}, "
                    f"vol {b['volume_pct_of_adv']:.0f}% ADV)"
                )
            lines.append("")
            lines.append("_Drill-down: `/detectors` for today's full list + recent history_")
            await send_telegram_message("\n".join(lines))
        except Exception as e:
            logger.error(f"intraday_flag_break Telegram failed (non-critical): {e}")

    logger.info(f"intraday_flag_break_scan: {len(new_breaks)} new breaks detected")
    return len(new_breaks)


# ────────────────────────────────────────────────────────────────────────
# Intraday support-test detector (#95, entry-technique #2)
# ────────────────────────────────────────────────────────────────────────
#
# Counter-trend mechanic within established range. Detects when price
# intraday tags base_low (or undercuts within tolerance) AND bounces
# back above it — the classic Wyckoff/Livermore/Morales "Spring" /
# "Shakeout" / "Springboard" pattern.
#
# Per memory/user_tight_range_entry_techniques.md Entry #2:
#   "Tightest stop placement (just below `base_low`); BEST R:R if it
#    works; low signal/noise"
# Per Morales: "Volume is generally not a factor" — design departure
# from #94 (breakout requires volume confirmation).
#
# Stateless within-snapshot detection — uses day.l (intraday low so
# far) + day.c (current close) instead of multi-tick state.

# Support-test thresholds
_SUPPORT_TEST_TAG_TOL_PCT       = 1.0  # day_low within ±1% of base_low counts as a tag
_SUPPORT_TEST_MAX_UNDERCUT_PCT  = 2.0  # day_low no more than 2% BELOW base_low (else falling knife)
_SUPPORT_TEST_BOUNCE_FLOOR_PCT  = 0.5  # current_price at least 0.5% above day_low
_SUPPORT_TEST_HOLD_FLOOR_PCT    = 0.5  # current_price at least 0.5% above base_low (currently holding)

# U&R (Undercut & Rally) — #98, entry-technique #5 (Morales / OWL). The depth band
# is ADJACENT to (deeper than) the support-test ≤2% band above, so the two detectors
# never fire on the same bar — the DEPTH of the probe is what distinguishes a U&R
# (a real stop-run that reclaims) from a support-test (a shallow touch that holds).
_UR_MIN_UNDERCUT_PCT  = 2.0   # must undercut base_low by MORE than this (else it's a support-test)
_UR_MAX_UNDERCUT_PCT  = 8.0   # ...but no deeper than this — beyond is a breakdown, not a shakeout
_UR_RECLAIM_FLOOR_PCT = 0.0   # current price back at/above base_low (reclaimed the undercut level)


def is_undercut_rally(
    base_low: float,
    undercut_low: float,
    current_price: float,
    *,
    min_undercut_pct: float = _UR_MIN_UNDERCUT_PCT,
    max_undercut_pct: float = _UR_MAX_UNDERCUT_PCT,
    reclaim_floor_pct: float = _UR_RECLAIM_FLOOR_PCT,
) -> bool:
    """U&R (Undercut & Rally) — Morales/OWL, entry-technique #5. Pure predicate.

    A SHALLOW stop-run BELOW a prior low (`base_low`) that then RECLAIMS back above
    it. The undercut depth band is adjacent to — and deeper than — the support-test
    detector's ≤2% touch, so the two never double-count the same bar:
      - undercut depth in (min_undercut_pct, max_undercut_pct]  → a real probe, not a
        shallow tag (support-test territory) and not a breakdown
      - current_price reclaimed at/above base_low × (1 + reclaim_floor_pct/100)

    `undercut_low` is the day's low (the deepest point of the shakeout) and doubles as
    the STOP / Morales "selling guide". NO volume input — per Morales, "volume is
    generally not a factor". Returns True iff the shape matches.
    """
    if base_low <= 0 or undercut_low <= 0 or current_price <= 0:
        return False
    undercut_pct = (base_low - undercut_low) / base_low * 100.0  # +ve = below base_low
    if not (min_undercut_pct < undercut_pct <= max_undercut_pct):
        return False
    reclaim_target = base_low * (1.0 + reclaim_floor_pct / 100.0)
    return current_price >= reclaim_target


async def run_intraday_support_test_scan(scan_time):
    """Intraday support-test detection on TIGHTENING/COILED/TRIGGERED tickers.

    Reads the most-recent flag-classification (MAX(scan_date) WHERE
    scan_date < CURRENT_DATE — trading-session-aware), filters to
    stage IN (TIGHTENING, COILED, TRIGGERED). For each candidate
    ticker, evaluates whether the day's intraday low tested base_low
    AND price has bounced back above it. NO volume gate (per Morales
    methodology). New tests inserted into mi_flag_support_tests
    (UNIQUE on ticker+test_date) and a consolidated Telegram digest
    fires.

    Gates (stateless within-snapshot):
      1. day.l ≤ base_low × 1.01 — tested low (within tolerance)
      2. day.l ≥ base_low × 0.98 — clean test, not falling knife
      3. day.c ≥ base_low × 1.005 — currently holding above base_low
      4. (day.c − day.l) / day.l ≥ 0.005 — minimum bounce magnitude

    Args:
        scan_time: datetime in ET timezone

    Returns:
        int: count of new support tests inserted this scan
    """
    from agents.market_intelligence import db
    from agents.market_intelligence.collector import get_snapshot_all

    if not (_dt_time(9, 35) <= scan_time.time() <= _dt_time(15, 55)):
        return 0

    minutes_since_open = (scan_time.hour - 9) * 60 + scan_time.minute - 30
    if minutes_since_open <= 0:
        return 0

    pool = await db.get_pool()
    async with pool.acquire() as conn:
        # Idempotency guard (#145, 2026-05-28) — see flag-break loader for context.
        candidates = await conn.fetch("""
            WITH latest AS (
                SELECT MAX(scan_date) AS d FROM mi_flag_candidates
                WHERE scan_date < CURRENT_DATE
            )
            SELECT DISTINCT ON (c.ticker)
                   c.ticker, c.scan_date, c.stage, c.base_high, c.base_low, c.base_age
            FROM mi_flag_candidates c
            LEFT JOIN mi_daily_closes dc
                   ON dc.ticker = c.ticker
                  AND dc.trade_date = c.scan_date
            WHERE c.scan_date = (SELECT d FROM latest)
              AND c.stage IN ('TIGHTENING', 'COILED', 'TRIGGERED')
              AND c.base_low IS NOT NULL
              AND c.base_low > 0
              AND (c.base_high IS NULL OR dc.close IS NULL OR dc.close <= c.base_high)
            ORDER BY c.ticker, c.scan_date DESC
        """)
        if not candidates:
            return 0

        watchlist = {r["ticker"]: dict(r) for r in candidates}

        cohort_rows = await conn.fetch("""
            SELECT ticker, count_9m_alerts_180d
            FROM mi_sugar_babies_cohort
            WHERE cohort_date = (SELECT MAX(cohort_date) FROM mi_sugar_babies_cohort)
        """)
        cohort_map = {r["ticker"]: r["count_9m_alerts_180d"] for r in cohort_rows}

        adv_rows = await conn.fetch("""
            SELECT ticker,
                   PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY volume) AS adv_20
            FROM (
                SELECT ticker, volume,
                       ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY trade_date DESC) AS rn
                FROM mi_daily_closes
                WHERE ticker = ANY($1::text[])
                  AND trade_date >= CURRENT_DATE - INTERVAL '40 days'
                  AND volume > 0
            ) sub
            WHERE rn <= 20
            GROUP BY ticker
        """, list(watchlist.keys()))
        adv_map = {r["ticker"]: int(r["adv_20"] or 0) for r in adv_rows}

        already_tested = await conn.fetch("""
            SELECT ticker FROM mi_flag_support_tests WHERE test_date = CURRENT_DATE
        """)
        already_set = {r["ticker"] for r in already_tested}

    snapshots = await get_snapshot_all()
    if not snapshots:
        logger.warning("intraday_support_test_scan: empty snapshot fetch; skipping")
        return 0

    new_tests: list[dict] = []
    for ticker, cand in watchlist.items():
        if ticker in already_set:
            continue
        snap = snapshots.get(ticker)
        if not snap:
            continue

        day = snap.get("day") or {}
        day_low = day.get("l")
        current_price = (
            day.get("c")
            or snap.get("min", {}).get("c")
            or snap.get("lastTrade", {}).get("p")
            or 0
        )
        if not day_low or day_low <= 0 or current_price <= 0:
            continue

        base_low = float(cand["base_low"])

        # Cheap snapshot-based pre-screen on day_low — if even the day's low
        # didn't touch base_low, skip without the Polygon recency fetch.
        tag_upper = base_low * (1.0 + _SUPPORT_TEST_TAG_TOL_PCT / 100.0)
        if day_low > tag_upper:
            continue  # never tested today at all

        # Recency check — replace day_low with min(low) over last K minutes.
        # day_low is cumulative-state; once a ticker touches base_low at 10:00
        # AM, day_low gates fire all afternoon. recent_low gates fire only
        # while the test is still LIVE (advisor 2026-05-26 + #124 data).
        recent_low, recent_low_time = await _recent_low_in_window(ticker, scan_time)
        if recent_low is None:
            continue  # fetch failed or no bars — skip rather than fall back

        # Gate 1: recent_low tested base_low within tolerance
        if recent_low > tag_upper:
            continue  # touch was too far back, recent action above tolerance

        # Gate 2: no falling-knife — recent_low not too far below base_low
        undercut_floor = base_low * (1.0 - _SUPPORT_TEST_MAX_UNDERCUT_PCT / 100.0)
        if recent_low < undercut_floor:
            continue  # too deep an undercut to be a clean test

        # Gate 3: currently holding above base_low (not still under it)
        hold_target = base_low * (1.0 + _SUPPORT_TEST_HOLD_FLOOR_PCT / 100.0)
        if current_price < hold_target:
            continue

        # Gate 4: minimum bounce magnitude from the RECENT low
        bounce_pct = (current_price - recent_low) / recent_low * 100.0
        if bounce_pct < _SUPPORT_TEST_BOUNCE_FLOOR_PCT:
            continue

        today_volume = int(day.get("v") or 0)
        adv_20 = adv_map.get(ticker, 0)
        volume_pct = (today_volume / adv_20 * 100.0) if adv_20 > 0 else None
        # pct_below_base_low now reports the RECENT low's depth (state-current),
        # not day_low (cumulative). User sees the touch the alert is actually about.
        pct_below_base_low = (recent_low - base_low) / base_low * 100.0
        # current state above MA (positive when bouncing) — for the new alert wording
        pct_current_above_base = (current_price - base_low) / base_low * 100.0
        in_cohort = ticker in cohort_map

        new_tests.append({
            "ticker": ticker,
            "minutes_since_open": minutes_since_open,
            "parent_stage": cand["stage"],
            "parent_scan_date": cand["scan_date"],
            "base_high": float(cand["base_high"]) if cand["base_high"] else None,
            "base_low": base_low,
            "base_age": cand["base_age"],
            "day_low": float(recent_low),  # column kept for back-compat, now holds recent_low
            "recent_low_time": recent_low_time,
            "current_price": float(current_price),
            "pct_below_base_low": pct_below_base_low,
            "pct_current_above_base": pct_current_above_base,
            "bounce_pct_from_low": bounce_pct,
            "today_volume": today_volume or None,
            "adv_20": adv_20 or None,
            "volume_pct_of_adv": volume_pct,
            "in_sugar_baby_cohort": in_cohort,
            "cohort_count_180d": cohort_map.get(ticker),
        })

    if not new_tests:
        return 0

    async with pool.acquire() as conn:
        for t in new_tests:
            await conn.execute("""
                INSERT INTO mi_flag_support_tests (
                    ticker, test_date, test_time, minutes_since_open,
                    parent_stage, parent_scan_date, base_high, base_low, base_age,
                    day_low, current_price, pct_below_base_low, bounce_pct_from_low,
                    today_volume, adv_20, volume_pct_of_adv,
                    in_sugar_baby_cohort, cohort_count_180d
                ) VALUES (
                    $1, CURRENT_DATE, NOW(), $2,
                    $3, $4, $5, $6, $7,
                    $8, $9, $10, $11,
                    $12, $13, $14,
                    $15, $16
                )
                ON CONFLICT (ticker, test_date) DO NOTHING
            """,
                t["ticker"], t["minutes_since_open"],
                t["parent_stage"], t["parent_scan_date"],
                t["base_high"], t["base_low"], t["base_age"],
                t["day_low"], t["current_price"],
                t["pct_below_base_low"], t["bounce_pct_from_low"],
                t["today_volume"], t["adv_20"], t["volume_pct_of_adv"],
                t["in_sugar_baby_cohort"], t["cohort_count_180d"],
            )
            try:
                undercut_note = (
                    f"undercut={t['pct_below_base_low']:+.2f}%"
                    if t["pct_below_base_low"] < 0
                    else f"tag={t['pct_below_base_low']:+.2f}%"
                )
                await db.log_audit_event(
                    "intraday_support_test",
                    f"{t['ticker']} stage={t['parent_stage']} "
                    f"{undercut_note} bounce={t['bounce_pct_from_low']:+.2f}%"
                )
            except Exception as e:
                logger.debug(f"intraday_support_test audit failed (non-critical): {e}")

    # Per-tick Telegram OFF by default (#168 noise fix, 2026-06-07 — DEFAULT
    # FALSE so a DR restore / fresh env can't bring the noise back; code is SoT).
    # DB writes + audit still fire; the day's tests surface in the 16:00 ET
    # consolidated digest (run_intraday_signals_eod_digest). Toggle
    # SHADOW_DETECTOR_TELEGRAM_ENABLED=true to re-enable per-tick.
    if os.environ.get("SHADOW_DETECTOR_TELEGRAM_ENABLED", "false").lower() == "true":
        try:
            from agents.market_intelligence.briefing import send_telegram_message
            clock = scan_time.strftime("%H:%M")
            lines = [
                f"🛡 *Intraday Support-Tests ({len(new_tests)} new)*",
                f"_5-min scan at {clock} ET — telemetry only, no entries submitted._",
                "",
            ]
            for t in new_tests:
                cohort_marker = "🍬 " if t["in_sugar_baby_cohort"] else ""
                touch_clock = (
                    t["recent_low_time"].strftime("%H:%M")
                    if t.get("recent_low_time") else "?"
                )
                # Current-state wording: where price IS now relative to base_low,
                # plus when the recent test happened. Replaces cumulative-state
                # "day_low undercut X%" which was stale by hours (advisor 2026-05-26).
                lines.append(
                    f"• {cohort_marker}`{t['ticker']}` — tested ${t['base_low']:.2f} "
                    f"at {touch_clock} ({t['pct_below_base_low']:+.2f}% deep), "
                    f"now {t['pct_current_above_base']:+.2f}% above base "
                    f"(${t['current_price']:.2f}; "
                    f"base {t['base_age']}d {t['parent_stage']})"
                )
            lines.append("")
            lines.append("_Drill-down: `/supporttests` for today's full list + recent history_")
            await send_telegram_message("\n".join(lines))
        except Exception as e:
            logger.error(f"intraday_support_test Telegram failed (non-critical): {e}")

    logger.info(f"intraday_support_test_scan: {len(new_tests)} new tests detected")
    return len(new_tests)


async def run_intraday_undercut_rally_scan(scan_time):
    """Intraday U&R (Undercut & Rally) detection on TIGHTENING/COILED/TRIGGERED tickers.

    Sibling of run_intraday_support_test_scan (same Morales/OWL no-volume lineage).
    For each flag candidate, fires when the day's low UNDERCUT base_low by more than
    the support-test band (2%) but not so deep it's a breakdown (≤ _UR_MAX_UNDERCUT_PCT),
    AND price has RECLAIMED back above base_low. The undercut low is the stop / selling
    guide. NO volume gate (per Morales). One row per ticker/day (UNIQUE ticker+ur_date).

    Gates (stateless within-snapshot — `is_undercut_rally` predicate):
      1. (base_low - day_low) / base_low ∈ (_UR_MIN_UNDERCUT_PCT, _UR_MAX_UNDERCUT_PCT]
      2. current_price ≥ base_low × (1 + _UR_RECLAIM_FLOOR_PCT/100)   — reclaimed

    Args:
        scan_time: datetime in ET timezone

    Returns:
        int: count of new U&Rs inserted this scan
    """
    from agents.market_intelligence import db
    from agents.market_intelligence.collector import get_snapshot_all

    if not (_dt_time(9, 35) <= scan_time.time() <= _dt_time(15, 55)):
        return 0

    minutes_since_open = (scan_time.hour - 9) * 60 + scan_time.minute - 30
    if minutes_since_open <= 0:
        return 0

    pool = await db.get_pool()
    async with pool.acquire() as conn:
        # Same universe + idempotency shape as the support-test scan (#145).
        candidates = await conn.fetch("""
            WITH latest AS (
                SELECT MAX(scan_date) AS d FROM mi_flag_candidates
                WHERE scan_date < CURRENT_DATE
            )
            SELECT DISTINCT ON (c.ticker)
                   c.ticker, c.scan_date, c.stage, c.base_high, c.base_low, c.base_age
            FROM mi_flag_candidates c
            LEFT JOIN mi_daily_closes dc
                   ON dc.ticker = c.ticker
                  AND dc.trade_date = c.scan_date
            WHERE c.scan_date = (SELECT d FROM latest)
              AND c.stage IN ('TIGHTENING', 'COILED', 'TRIGGERED')
              AND c.base_low IS NOT NULL
              AND c.base_low > 0
              AND (c.base_high IS NULL OR dc.close IS NULL OR dc.close <= c.base_high)
            ORDER BY c.ticker, c.scan_date DESC
        """)
        if not candidates:
            return 0

        watchlist = {r["ticker"]: dict(r) for r in candidates}

        cohort_rows = await conn.fetch("""
            SELECT ticker, count_9m_alerts_180d
            FROM mi_sugar_babies_cohort
            WHERE cohort_date = (SELECT MAX(cohort_date) FROM mi_sugar_babies_cohort)
        """)
        cohort_map = {r["ticker"]: r["count_9m_alerts_180d"] for r in cohort_rows}

        adv_rows = await conn.fetch("""
            SELECT ticker,
                   PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY volume) AS adv_20
            FROM (
                SELECT ticker, volume,
                       ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY trade_date DESC) AS rn
                FROM mi_daily_closes
                WHERE ticker = ANY($1::text[])
                  AND trade_date >= CURRENT_DATE - INTERVAL '40 days'
                  AND volume > 0
            ) sub
            WHERE rn <= 20
            GROUP BY ticker
        """, list(watchlist.keys()))
        adv_map = {r["ticker"]: int(r["adv_20"] or 0) for r in adv_rows}

        already = await conn.fetch("""
            SELECT ticker FROM mi_flag_undercut_rally WHERE ur_date = CURRENT_DATE
        """)
        already_set = {r["ticker"] for r in already}

    snapshots = await get_snapshot_all()
    if not snapshots:
        logger.warning("intraday_undercut_rally_scan: empty snapshot fetch; skipping")
        return 0

    new_urs: list[dict] = []
    for ticker, cand in watchlist.items():
        if ticker in already_set:
            continue
        snap = snapshots.get(ticker)
        if not snap:
            continue

        day = snap.get("day") or {}
        day_low = day.get("l")
        current_price = (
            day.get("c")
            or snap.get("min", {}).get("c")
            or snap.get("lastTrade", {}).get("p")
            or 0
        )
        if not day_low or day_low <= 0 or current_price <= 0:
            continue

        base_low = float(cand["base_low"])

        # The day's low is the undercut probe (per advisor 2026-05-31 same-day trigger).
        # Predicate enforces the depth band + reclaim; one row per ticker/day handles
        # the cumulative-state staleness (we record the U&R once, when first detected).
        if not is_undercut_rally(base_low, float(day_low), float(current_price)):
            continue

        undercut_pct = (base_low - day_low) / base_low * 100.0
        reclaim_pct = (current_price - base_low) / base_low * 100.0
        today_volume = int(day.get("v") or 0)
        adv_20 = adv_map.get(ticker, 0)
        volume_pct = (today_volume / adv_20 * 100.0) if adv_20 > 0 else None

        new_urs.append({
            "ticker": ticker,
            "minutes_since_open": minutes_since_open,
            "parent_stage": cand["stage"],
            "parent_scan_date": cand["scan_date"],
            "base_high": float(cand["base_high"]) if cand["base_high"] else None,
            "base_low": base_low,
            "base_age": cand["base_age"],
            "undercut_low": float(day_low),
            "undercut_pct": undercut_pct,
            "current_price": float(current_price),
            "reclaim_pct_above_base": reclaim_pct,
            "today_volume": today_volume or None,
            "adv_20": adv_20 or None,
            "volume_pct_of_adv": volume_pct,
            "in_sugar_baby_cohort": ticker in cohort_map,
            "cohort_count_180d": cohort_map.get(ticker),
        })

    if not new_urs:
        return 0

    async with pool.acquire() as conn:
        for u in new_urs:
            await conn.execute("""
                INSERT INTO mi_flag_undercut_rally (
                    ticker, ur_date, ur_time, minutes_since_open,
                    parent_stage, parent_scan_date, base_high, base_low, base_age,
                    undercut_low, undercut_pct, current_price, reclaim_pct_above_base,
                    today_volume, adv_20, volume_pct_of_adv,
                    in_sugar_baby_cohort, cohort_count_180d
                ) VALUES (
                    $1, CURRENT_DATE, NOW(), $2,
                    $3, $4, $5, $6, $7,
                    $8, $9, $10, $11,
                    $12, $13, $14,
                    $15, $16
                )
                ON CONFLICT (ticker, ur_date) DO NOTHING
            """,
                u["ticker"], u["minutes_since_open"],
                u["parent_stage"], u["parent_scan_date"],
                u["base_high"], u["base_low"], u["base_age"],
                u["undercut_low"], u["undercut_pct"],
                u["current_price"], u["reclaim_pct_above_base"],
                u["today_volume"], u["adv_20"], u["volume_pct_of_adv"],
                u["in_sugar_baby_cohort"], u["cohort_count_180d"],
            )
            try:
                await db.log_audit_event(
                    "intraday_undercut_rally",
                    f"{u['ticker']} stage={u['parent_stage']} "
                    f"undercut=-{u['undercut_pct']:.2f}% reclaim=+{u['reclaim_pct_above_base']:.2f}% "
                    f"stop=${u['undercut_low']:.2f}"
                )
            except Exception as e:
                logger.debug(f"intraday_undercut_rally audit failed (non-critical): {e}")

    # Intraday FYI is OFF by default (operator 2026-05-31): during the shadow phase
    # U&R surfaces in the QUIET evening-brief roundup (get_undercut_rallies), not as
    # intraday pings. DB writes + audit always fire regardless. Flip
    # UNDERCUT_RALLY_INTRADAY_FYI=true to also ping live (e.g. once U&R graduates to a
    # tradeable, real-time setup where the moment-of-reclaim matters for entry).
    if os.environ.get("UNDERCUT_RALLY_INTRADAY_FYI", "false").lower() == "true":
        try:
            from agents.market_intelligence.briefing import send_telegram_message
            clock = scan_time.strftime("%H:%M")
            lines = [
                f"🪤 *Intraday U&R — Undercut & Rally ({len(new_urs)} new)*",
                f"_5-min scan at {clock} ET — telemetry only, no entries submitted._",
                "",
            ]
            for u in new_urs:
                cohort_marker = "🍬 " if u["in_sugar_baby_cohort"] else ""
                lines.append(
                    f"• {cohort_marker}`{u['ticker']}` — undercut ${u['base_low']:.2f} "
                    f"to ${u['undercut_low']:.2f} (-{u['undercut_pct']:.2f}%), "
                    f"reclaimed +{u['reclaim_pct_above_base']:.2f}% above base "
                    f"(${u['current_price']:.2f}; stop ${u['undercut_low']:.2f}; "
                    f"base {u['base_age']}d {u['parent_stage']})"
                )
            lines.append("")
            lines.append("_Drill-down: `/undercutrally` for today's full list + recent history_")
            await send_telegram_message("\n".join(lines))
        except Exception as e:
            logger.error(f"intraday_undercut_rally Telegram failed (non-critical): {e}")

    logger.info(f"intraday_undercut_rally_scan: {len(new_urs)} new U&Rs detected")
    return len(new_urs)


# ────────────────────────────────────────────────────────────────────────
# Intraday MA-pullback detector (#96, entry-technique #3)
# ────────────────────────────────────────────────────────────────────────
#
# Classic VCP/Minervini pullback: price retraces inside the range to
# SMA10 or SMA20, tags the MA, bounces back above. KEY differentiator
# from #94/#95: LIGHT-VOLUME gate (today_pace ≤ ADV) — pullbacks should
# NOT happen on heavy volume. Heavy volume on a pullback = distribution,
# not the desired institutional-pause signal.
#
# Stateless within-snapshot using day.l + day.c, same shape as #95.

_MA_PULLBACK_TAG_TOL_PCT       = 1.0   # day_low within ±1% of MA counts as a tag
_MA_PULLBACK_MAX_UNDERCUT_PCT  = 2.0   # day_low no more than 2% BELOW MA
_MA_PULLBACK_BOUNCE_FLOOR_PCT  = 0.5   # day_close at least 0.5% above day_low
_MA_PULLBACK_HOLD_FLOOR_PCT    = 0.5   # day_close at least 0.5% above MA
_MA_PULLBACK_VOL_CEIL_PCT      = 100.0 # full-day projected pace must be ≤ 100% ADV


async def run_intraday_ma_pullback_scan(scan_time):
    """Intraday MA-pullback detection on TIGHTENING/COILED/TRIGGERED tickers.

    Reads the most-recent flag-classification (MAX(scan_date) WHERE
    scan_date < CURRENT_DATE), filters to stage IN (TIGHTENING, COILED,
    TRIGGERED) with non-null sma_10/sma_20. For each candidate ticker,
    evaluates whether the day's intraday low tested SMA10 or SMA20
    (preferring SMA10 if both fire), AND price has bounced back above
    it, AND the day's volume is LIGHT (pace ≤ ADV).

    Args:
        scan_time: datetime in ET timezone

    Returns:
        int: count of new MA pullbacks inserted this scan
    """
    from agents.market_intelligence import db
    from agents.market_intelligence.collector import get_snapshot_all

    if not (_dt_time(9, 35) <= scan_time.time() <= _dt_time(15, 55)):
        return 0

    minutes_since_open = (scan_time.hour - 9) * 60 + scan_time.minute - 30
    if minutes_since_open <= 0:
        return 0

    pool = await db.get_pool()
    async with pool.acquire() as conn:
        # Universe: at least one of sma_10 / sma_20 populated.
        # Idempotency guard (#145, 2026-05-28) — see flag-break loader for context.
        candidates = await conn.fetch("""
            WITH latest AS (
                SELECT MAX(scan_date) AS d FROM mi_flag_candidates
                WHERE scan_date < CURRENT_DATE
            )
            SELECT DISTINCT ON (c.ticker)
                   c.ticker, c.scan_date, c.stage,
                   c.base_high, c.base_low, c.base_age
            FROM mi_flag_candidates c
            LEFT JOIN mi_daily_closes dc
                   ON dc.ticker = c.ticker
                  AND dc.trade_date = c.scan_date
            WHERE c.scan_date = (SELECT d FROM latest)
              AND c.stage IN ('TIGHTENING', 'COILED', 'TRIGGERED')
              AND c.base_low IS NOT NULL AND c.base_low > 0
              AND c.base_high IS NOT NULL AND c.base_high > 0
              AND (dc.close IS NULL OR dc.close <= c.base_high)
            ORDER BY c.ticker, c.scan_date DESC
        """)
        if not candidates:
            return 0

        watchlist = {r["ticker"]: dict(r) for r in candidates}

        cohort_rows = await conn.fetch("""
            SELECT ticker, count_9m_alerts_180d
            FROM mi_sugar_babies_cohort
            WHERE cohort_date = (SELECT MAX(cohort_date) FROM mi_sugar_babies_cohort)
        """)
        cohort_map = {r["ticker"]: r["count_9m_alerts_180d"] for r in cohort_rows}

        adv_rows = await conn.fetch("""
            SELECT ticker,
                   PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY volume) AS adv_20
            FROM (
                SELECT ticker, volume,
                       ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY trade_date DESC) AS rn
                FROM mi_daily_closes
                WHERE ticker = ANY($1::text[])
                  AND trade_date >= CURRENT_DATE - INTERVAL '40 days'
                  AND volume > 0
            ) sub
            WHERE rn <= 20
            GROUP BY ticker
        """, list(watchlist.keys()))
        adv_map = {r["ticker"]: int(r["adv_20"] or 0) for r in adv_rows}

        # Fetch last 19 prior-day closes per ticker for fresh SMA computation
        # at scan time. Stored sma_10/sma_20 on mi_flag_candidates comes from
        # the 5:25 PM ET flag scan on the prior business day — that's a SMA
        # that doesn't include today's intraday price action. Chart platforms
        # (TradingView etc.) compute SMA10 over the rolling last-10-bar
        # window INCLUDING today's running close. The divergence makes our
        # reported "pct_below_ma" mismatch the chart visibly. Caught
        # 2026-05-26 (GLW: stored SMA10=$193.32 vs chart-style ~$192.39).
        # Drop the oldest of 10, append current_price.
        closes_rows = await conn.fetch("""
            SELECT ticker, array_agg(close ORDER BY trade_date DESC) AS closes
            FROM (
                SELECT ticker, trade_date, close,
                       ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY trade_date DESC) AS rn
                FROM mi_daily_closes
                WHERE ticker = ANY($1::text[])
                  AND trade_date >= CURRENT_DATE - INTERVAL '40 days'
            ) sub
            WHERE rn <= 19
            GROUP BY ticker
        """, list(watchlist.keys()))
        prior_closes_map = {r["ticker"]: list(r["closes"]) for r in closes_rows}

        already_pulled = await conn.fetch("""
            SELECT ticker FROM mi_flag_ma_pullbacks WHERE pullback_date = CURRENT_DATE
        """)
        already_set = {r["ticker"] for r in already_pulled}

    snapshots = await get_snapshot_all()
    if not snapshots:
        logger.warning("intraday_ma_pullback_scan: empty snapshot fetch; skipping")
        return 0

    new_pullbacks: list[dict] = []
    for ticker, cand in watchlist.items():
        if ticker in already_set:
            continue
        snap = snapshots.get(ticker)
        if not snap:
            continue

        day = snap.get("day") or {}
        day_low = day.get("l")
        current_price = (
            day.get("c")
            or snap.get("min", {}).get("c")
            or snap.get("lastTrade", {}).get("p")
            or 0
        )
        if not day_low or day_low <= 0 or current_price <= 0:
            continue

        adv_20 = adv_map.get(ticker, 0)
        if adv_20 <= 0:
            continue
        today_volume = int(day.get("v") or 0)
        if today_volume <= 0:
            continue

        # Light-volume gate — defining characteristic of pullback pattern
        projected_full_day = int(today_volume * (390.0 / minutes_since_open))
        if projected_full_day > adv_20 * (_MA_PULLBACK_VOL_CEIL_PCT / 100.0):
            continue

        base_low = float(cand["base_low"])
        base_high = float(cand["base_high"])

        # Fresh SMA10 / SMA20 at scan time — drop oldest prior close, append
        # today's current_price as the running close (matches chart-style
        # rolling SMA). Falls back to None if insufficient history; the
        # ma_value loop skips None entries.
        prior_closes = prior_closes_map.get(ticker, [])
        fresh_sma10 = (
            (sum(prior_closes[:9]) + current_price) / 10.0
            if len(prior_closes) >= 9 else None
        )
        fresh_sma20 = (
            (sum(prior_closes[:19]) + current_price) / 20.0
            if len(prior_closes) >= 19 else None
        )

        # Cheap snapshot-based pre-screen: if neither MA could conceivably
        # be tagged today (day_low > both MAs' upper tolerances), skip the
        # recency fetch entirely. The MA range gate already filters to
        # ma INSIDE base range, so MAs span ~base_low to ~base_high; if
        # day_low is above max(MA) × (1+tol), no MA can be tagged today.
        if all(
            (ma is None or ma <= 0
             or day_low > ma * (1.0 + _MA_PULLBACK_TAG_TOL_PCT / 100.0))
            for ma in (fresh_sma10, fresh_sma20)
        ):
            continue

        # Recency check — replace day_low with min(low) over last K minutes
        # (advisor 2026-05-26 + #124 backward-check data). day_low is
        # cumulative-state; recent_low fires only while the pullback is
        # LIVE. Fetch once per ticker, reuse across MA loop iterations.
        recent_low, recent_low_time = await _recent_low_in_window(ticker, scan_time)
        if recent_low is None:
            continue  # fetch failed or no bars

        # Try SMA10 first, then SMA20. First MA that passes all gates wins.
        chosen_ma = None
        chosen_label = None
        for ma_label, ma_value in (("SMA10", fresh_sma10),
                                    ("SMA20", fresh_sma20)):
            if ma_value is None or ma_value <= 0:
                continue
            ma_value = float(ma_value)

            # MA must be INSIDE the range — otherwise it's not a within-range pullback
            if not (base_low < ma_value < base_high):
                continue

            tag_upper = ma_value * (1.0 + _MA_PULLBACK_TAG_TOL_PCT / 100.0)
            if recent_low > tag_upper:
                continue  # touch was too far back, recent action above tolerance
            undercut_floor = ma_value * (1.0 - _MA_PULLBACK_MAX_UNDERCUT_PCT / 100.0)
            if recent_low < undercut_floor:
                continue  # too-deep undercut
            hold_target = ma_value * (1.0 + _MA_PULLBACK_HOLD_FLOOR_PCT / 100.0)
            if current_price < hold_target:
                continue  # not currently holding above
            bounce_pct = (current_price - recent_low) / recent_low * 100.0
            if bounce_pct < _MA_PULLBACK_BOUNCE_FLOOR_PCT:
                continue

            chosen_ma = ma_value
            chosen_label = ma_label
            break

        if chosen_ma is None:
            continue

        # State-current metrics for the alert: recent_low's depth + where
        # price IS now relative to the MA.
        pct_below_ma = (recent_low - chosen_ma) / chosen_ma * 100.0
        pct_current_above_ma = (current_price - chosen_ma) / chosen_ma * 100.0
        bounce_pct = (current_price - recent_low) / recent_low * 100.0
        volume_pct = today_volume / adv_20 * 100.0
        in_cohort = ticker in cohort_map

        new_pullbacks.append({
            "ticker": ticker,
            "minutes_since_open": minutes_since_open,
            "parent_stage": cand["stage"],
            "parent_scan_date": cand["scan_date"],
            "base_high": base_high,
            "base_low": base_low,
            "base_age": cand["base_age"],
            "ma_label": chosen_label,
            "ma_value": chosen_ma,
            "day_low": float(recent_low),  # column kept for back-compat, now holds recent_low
            "recent_low_time": recent_low_time,
            "current_price": float(current_price),
            "pct_below_ma": pct_below_ma,
            "pct_current_above_ma": pct_current_above_ma,
            "bounce_pct_from_low": bounce_pct,
            "today_volume": today_volume,
            "adv_20": adv_20,
            "volume_pct_of_adv": volume_pct,
            "projected_full_day_volume": projected_full_day,
            "in_sugar_baby_cohort": in_cohort,
            "cohort_count_180d": cohort_map.get(ticker),
        })

    if not new_pullbacks:
        return 0

    async with pool.acquire() as conn:
        for p in new_pullbacks:
            await conn.execute("""
                INSERT INTO mi_flag_ma_pullbacks (
                    ticker, pullback_date, pullback_time, minutes_since_open,
                    parent_stage, parent_scan_date,
                    base_high, base_low, base_age,
                    ma_label, ma_value,
                    day_low, current_price, pct_below_ma, bounce_pct_from_low,
                    today_volume, adv_20, volume_pct_of_adv, projected_full_day_volume,
                    in_sugar_baby_cohort, cohort_count_180d
                ) VALUES (
                    $1, CURRENT_DATE, NOW(), $2,
                    $3, $4,
                    $5, $6, $7,
                    $8, $9,
                    $10, $11, $12, $13,
                    $14, $15, $16, $17,
                    $18, $19
                )
                ON CONFLICT (ticker, pullback_date) DO NOTHING
            """,
                p["ticker"], p["minutes_since_open"],
                p["parent_stage"], p["parent_scan_date"],
                p["base_high"], p["base_low"], p["base_age"],
                p["ma_label"], p["ma_value"],
                p["day_low"], p["current_price"],
                p["pct_below_ma"], p["bounce_pct_from_low"],
                p["today_volume"], p["adv_20"], p["volume_pct_of_adv"],
                p["projected_full_day_volume"],
                p["in_sugar_baby_cohort"], p["cohort_count_180d"],
            )
            try:
                undercut_note = (
                    f"undercut={p['pct_below_ma']:+.2f}%"
                    if p["pct_below_ma"] < 0
                    else f"tag={p['pct_below_ma']:+.2f}%"
                )
                await db.log_audit_event(
                    "intraday_ma_pullback",
                    f"{p['ticker']} stage={p['parent_stage']} "
                    f"ma={p['ma_label']} {undercut_note} "
                    f"bounce={p['bounce_pct_from_low']:+.2f}% "
                    f"vol_pct_adv={p['volume_pct_of_adv']:.0f}%"
                )
            except Exception as e:
                logger.debug(f"intraday_ma_pullback audit failed (non-critical): {e}")

    # Per-tick Telegram OFF by default (#168, see support_test equivalent above).
    # Day's pullbacks surface in the 16:00 ET consolidated digest.
    if os.environ.get("SHADOW_DETECTOR_TELEGRAM_ENABLED", "false").lower() == "true":
        try:
            from agents.market_intelligence.briefing import send_telegram_message
            clock = scan_time.strftime("%H:%M")
            lines = [
                f"📉 *Intraday MA-Pullbacks ({len(new_pullbacks)} new)*",
                f"_5-min scan at {clock} ET — telemetry only, no entries submitted._",
                "",
            ]
            for p in new_pullbacks:
                cohort_marker = "🍬 " if p["in_sugar_baby_cohort"] else ""
                touch_clock = (
                    p["recent_low_time"].strftime("%H:%M")
                    if p.get("recent_low_time") else "?"
                )
                # Current-state wording: where price IS now vs MA, plus when
                # the recent test happened. Replaces cumulative-state "day_low
                # undercut X%" which could be hours old (advisor 2026-05-26).
                lines.append(
                    f"• {cohort_marker}`{p['ticker']}` — {p['ma_label']} ${p['ma_value']:.2f} "
                    f"tested at {touch_clock} ({p['pct_below_ma']:+.2f}% deep), "
                    f"now {p['pct_current_above_ma']:+.2f}% above MA "
                    f"(${p['current_price']:.2f}; vol {p['volume_pct_of_adv']:.0f}% ADV)"
                )
            lines.append("")
            lines.append("_Drill-down: `/mapullbacks` for today's full list + recent history_")
            await send_telegram_message("\n".join(lines))
        except Exception as e:
            logger.error(f"intraday_ma_pullback Telegram failed (non-critical): {e}")

    logger.info(f"intraday_ma_pullback_scan: {len(new_pullbacks)} new pullbacks detected")
    return len(new_pullbacks)


# ── Low-volume rest (#97, tight-range entry-technique #4) ─────────────────────
# A quiet, tight coil INSIDE the base on LIGHT volume — no test/bounce; the
# defining feature is the calm (Qullamaggie/Morales "rest"). Distinct from the
# support-test (tests base_low + bounces) and MA-pullback (tests an MA): here
# price just sits still on dried-up volume, the classic pre-expansion pause.
# memory/user_tight_range_entry_techniques.md. Telemetry-only shadow phase.
_LOW_VOL_REST_VOL_CEIL_PCT   = 60.0  # projected full-day volume ≤ 60% ADV (dried-up = the signal)
_LOW_VOL_REST_RANGE_CEIL_PCT = 3.0   # intraday (high-low)/prev_close ≤ 3% (tight/quiet)
_LOW_VOL_REST_HOLD_FLOOR_PCT = 0.5   # current ≥ 0.5% above base_low (holding, not breaking down)
_LOW_VOL_REST_MIN_MINUTES    = 60    # ≥60 min elapsed — a rest must establish over time


def evaluate_low_vol_rest(
    *, base_low: float, base_high: float, day_high: float, day_low: float,
    current_price: float, prev_close: float, projected_full_day: int, adv_20: int,
) -> dict | None:
    """Pure decision for the low-volume-rest pattern. Returns metrics dict if the
    ticker is RESTING (quiet+tight+light, holding inside the base), else None.

    Gates: (1) light volume — projected_full_day ≤ ceil% ADV; (2) tight range —
    intraday spread ≤ ceil% of prev_close; (3) holding inside the base, above
    base_low with margin and not above base_high (a break-out is the flag-break
    detector's job, not a rest)."""
    if min(base_low, base_high, day_high, day_low, current_price, prev_close) <= 0:
        return None
    if adv_20 <= 0 or projected_full_day <= 0:
        return None
    # (1) light volume
    vol_pct_of_adv = projected_full_day / adv_20 * 100.0
    if vol_pct_of_adv > _LOW_VOL_REST_VOL_CEIL_PCT:
        return None
    # (2) tight intraday range
    range_pct = (day_high - day_low) / prev_close * 100.0
    if range_pct > _LOW_VOL_REST_RANGE_CEIL_PCT:
        return None
    # (3) holding INSIDE the base (resting, not broken out/down)
    if current_price > base_high:
        return None  # broken out — flag-break's job
    if current_price < base_low * (1.0 + _LOW_VOL_REST_HOLD_FLOOR_PCT / 100.0):
        return None  # below/at base_low — breaking down, not resting
    pos_in_base = ((current_price - base_low) / (base_high - base_low) * 100.0
                   if base_high > base_low else 0.0)
    return {
        "range_pct": range_pct,
        "vol_pct_of_adv": vol_pct_of_adv,
        "pos_in_base_pct": pos_in_base,
    }


async def run_intraday_low_vol_rest_scan(scan_time):
    """Intraday low-volume-rest detection on TIGHTENING/COILED/TRIGGERED tickers.

    Mirrors the support-test / MA-pullback shadow detectors (#95/#96): same flag
    universe + ADV map + per-day idempotency, telemetry-only. The signal is the
    calm — see evaluate_low_vol_rest. Returns count of new rests inserted.
    """
    from agents.market_intelligence import db
    from agents.market_intelligence.collector import get_snapshot_all

    if not (_dt_time(9, 35) <= scan_time.time() <= _dt_time(15, 55)):
        return 0
    minutes_since_open = (scan_time.hour - 9) * 60 + scan_time.minute - 30
    if minutes_since_open < _LOW_VOL_REST_MIN_MINUTES:
        return 0

    pool = await db.get_pool()
    async with pool.acquire() as conn:
        candidates = await conn.fetch("""
            WITH latest AS (
                SELECT MAX(scan_date) AS d FROM mi_flag_candidates
                WHERE scan_date < CURRENT_DATE
            )
            SELECT DISTINCT ON (c.ticker)
                   c.ticker, c.scan_date, c.stage, c.base_high, c.base_low, c.base_age
            FROM mi_flag_candidates c
            WHERE c.scan_date = (SELECT d FROM latest)
              AND c.stage IN ('TIGHTENING', 'COILED', 'TRIGGERED')
              AND c.base_low IS NOT NULL AND c.base_low > 0
              AND c.base_high IS NOT NULL AND c.base_high > 0
            ORDER BY c.ticker, c.scan_date DESC
        """)
        if not candidates:
            return 0
        watchlist = {r["ticker"]: dict(r) for r in candidates}

        cohort_rows = await conn.fetch("""
            SELECT ticker, count_9m_alerts_180d FROM mi_sugar_babies_cohort
            WHERE cohort_date = (SELECT MAX(cohort_date) FROM mi_sugar_babies_cohort)
        """)
        cohort_map = {r["ticker"]: r["count_9m_alerts_180d"] for r in cohort_rows}

        adv_rows = await conn.fetch("""
            SELECT ticker, PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY volume) AS adv_20
            FROM (
                SELECT ticker, volume,
                       ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY trade_date DESC) AS rn
                FROM mi_daily_closes
                WHERE ticker = ANY($1::text[])
                  AND trade_date >= CURRENT_DATE - INTERVAL '40 days' AND volume > 0
            ) sub WHERE rn <= 20 GROUP BY ticker
        """, list(watchlist.keys()))
        adv_map = {r["ticker"]: int(r["adv_20"] or 0) for r in adv_rows}

        already = await conn.fetch(
            "SELECT ticker FROM mi_flag_low_vol_rests WHERE rest_date = CURRENT_DATE")
        already_set = {r["ticker"] for r in already}

    snapshots = await get_snapshot_all()
    if not snapshots:
        logger.warning("intraday_low_vol_rest_scan: empty snapshot fetch; skipping")
        return 0

    new_rests: list[dict] = []
    for ticker, cand in watchlist.items():
        if ticker in already_set:
            continue
        snap = snapshots.get(ticker)
        if not snap:
            continue
        day = snap.get("day") or {}
        day_low, day_high = day.get("l"), day.get("h")
        current_price = (day.get("c") or snap.get("min", {}).get("c")
                         or snap.get("lastTrade", {}).get("p") or 0)
        prev_close = (snap.get("prevDay") or {}).get("c")
        adv_20 = adv_map.get(ticker, 0)
        today_volume = int(day.get("v") or 0)
        if not (day_low and day_high and prev_close) or today_volume <= 0 or adv_20 <= 0:
            continue
        projected_full_day = int(today_volume * (390.0 / minutes_since_open))
        m = evaluate_low_vol_rest(
            base_low=float(cand["base_low"]), base_high=float(cand["base_high"]),
            day_high=float(day_high), day_low=float(day_low),
            current_price=float(current_price), prev_close=float(prev_close),
            projected_full_day=projected_full_day, adv_20=adv_20,
        )
        if m is None:
            continue
        new_rests.append({
            "ticker": ticker, "minutes_since_open": minutes_since_open,
            "parent_stage": cand["stage"], "parent_scan_date": cand["scan_date"],
            "base_high": float(cand["base_high"]), "base_low": float(cand["base_low"]),
            "base_age": cand["base_age"], "current_price": float(current_price),
            "range_pct": m["range_pct"], "pos_in_base_pct": m["pos_in_base_pct"],
            "today_volume": today_volume, "adv_20": adv_20,
            "volume_pct_of_adv": m["vol_pct_of_adv"],
            "projected_full_day_volume": projected_full_day,
            "in_sugar_baby_cohort": ticker in cohort_map,
            "cohort_count_180d": cohort_map.get(ticker),
        })

    if not new_rests:
        return 0

    async with pool.acquire() as conn:
        for r in new_rests:
            await conn.execute("""
                INSERT INTO mi_flag_low_vol_rests (
                    ticker, rest_date, rest_time, minutes_since_open,
                    parent_stage, parent_scan_date, base_high, base_low, base_age,
                    current_price, range_pct, pos_in_base_pct,
                    today_volume, adv_20, volume_pct_of_adv, projected_full_day_volume,
                    in_sugar_baby_cohort, cohort_count_180d
                ) VALUES (
                    $1, CURRENT_DATE, NOW(), $2, $3, $4, $5, $6, $7,
                    $8, $9, $10, $11, $12, $13, $14, $15, $16
                ) ON CONFLICT (ticker, rest_date) DO NOTHING
            """,
                r["ticker"], r["minutes_since_open"], r["parent_stage"],
                r["parent_scan_date"], r["base_high"], r["base_low"], r["base_age"],
                r["current_price"], r["range_pct"], r["pos_in_base_pct"],
                r["today_volume"], r["adv_20"], r["volume_pct_of_adv"],
                r["projected_full_day_volume"], r["in_sugar_baby_cohort"],
                r["cohort_count_180d"],
            )
            try:
                await db.log_audit_event(
                    "intraday_low_vol_rest",
                    f"{r['ticker']} stage={r['parent_stage']} "
                    f"range={r['range_pct']:.2f}% vol_pct_adv={r['volume_pct_of_adv']:.0f}% "
                    f"pos_in_base={r['pos_in_base_pct']:.0f}%")
            except Exception as e:
                logger.debug(f"intraday_low_vol_rest audit failed (non-critical): {e}")

    # Per-tick Telegram OFF by default (#168). Day's rests surface in the 16:00 ET digest.
    if os.environ.get("SHADOW_DETECTOR_TELEGRAM_ENABLED", "false").lower() == "true":
        try:
            from agents.market_intelligence.briefing import send_telegram_message
            clock = scan_time.strftime("%H:%M")
            lines = [f"😴 *Intraday Low-Vol Rests ({len(new_rests)} new)*",
                     f"_5-min scan at {clock} ET — telemetry only, no entries submitted._", ""]
            for r in new_rests:
                marker = "🍬 " if r["in_sugar_baby_cohort"] else ""
                lines.append(
                    f"• {marker}`{r['ticker']}` — resting {r['pos_in_base_pct']:.0f}% up in base "
                    f"(${r['current_price']:.2f}; range {r['range_pct']:.1f}%, "
                    f"vol {r['volume_pct_of_adv']:.0f}% ADV)")
            lines += ["", "_Drill-down: `/lowvolrests` for today's list + recent history_"]
            await send_telegram_message("\n".join(lines))
        except Exception as e:
            logger.error(f"intraday_low_vol_rest Telegram failed (non-critical): {e}")

    logger.info(f"intraday_low_vol_rest_scan: {len(new_rests)} new rests detected")
    return len(new_rests)


# ────────────────────────────────────────────────────────────────────────
# Entry-technique annotation (#93, 2026-05-23 ship)
# ────────────────────────────────────────────────────────────────────────
#
# For each TIGHTENING/COILED watchlist ticker, compute which of the 5
# tight-range entry techniques are currently eligible based on real-time
# price + the EOD candidate row. Pure compute — no DB calls. Caller
# provides snapshot + candidate; helper returns annotation list.
#
# See memory/user_tight_range_entry_techniques.md for the 5-row taxonomy.
# Only 4 of 5 implemented in this first ship:
#   1. Breakout-near    🎯  price within 3% of base_high
#   2. Support-test     🛡  price within 3% of base_low
#   3. MA-pullback      📉  price within 2% of sma_10 OR sma_20
#   4. Low-vol-rest     💤  today's vol <50% ADV AND price mid-range
#   5. U&R-recent       (deferred — needs swing-low logic not in current schema)

# Annotation thresholds (proximity gates; small enough that "near" means
# "actionable today" but loose enough that operator has 1-2 days to chart-review)
_BREAKOUT_NEAR_PCT     = 3.0   # price within 3% below base_high
_SUPPORT_TEST_NEAR_PCT = 3.0   # price within 3% above base_low
_MA_PULLBACK_NEAR_PCT  = 2.0   # price within 2% of MA
_LOWVOL_REST_VOL_PCT   = 50.0  # today's vol < 50% of ADV
_LOWVOL_REST_MID_BAND  = 0.25  # price within middle 50% of [base_low, base_high]


def compute_entry_technique_annotations(snap, candidate, adv_20=None):
    """Pure compute. Returns list of (technique, emoji, detail) tuples
    indicating which entry techniques are currently eligible for this ticker.

    Args:
        snap: Polygon snapshot dict (from get_snapshot_all)
        candidate: mi_flag_candidates row (must have base_high, base_low,
                   sma_10, sma_20; sma values may be None)
        adv_20: optional pre-fetched ADV; if None, low-vol-rest is skipped

    Returns:
        list[tuple[technique_name, emoji, detail_str]]
    """
    if not snap or not candidate:
        return []

    current_price = (
        snap.get("day", {}).get("c")
        or snap.get("min", {}).get("c")
        or snap.get("lastTrade", {}).get("p")
    )
    if not current_price or current_price <= 0:
        return []

    base_high = candidate.get("base_high")
    base_low = candidate.get("base_low")
    if not base_high or not base_low or base_high <= base_low:
        return []

    annotations: list[tuple[str, str, str]] = []

    # Entry #1 — Breakout-near (price near top of range, eligible for break alert)
    dist_to_high = (base_high - current_price) / current_price * 100.0
    if 0 < dist_to_high <= _BREAKOUT_NEAR_PCT:
        annotations.append((
            "breakout_near", "🎯",
            f"{dist_to_high:.1f}% below ${base_high:.2f}"
        ))

    # Entry #2 — Support-test (price near bottom; tightest stop)
    dist_above_low = (current_price - base_low) / current_price * 100.0
    if 0 < dist_above_low <= _SUPPORT_TEST_NEAR_PCT:
        annotations.append((
            "support_test", "🛡",
            f"{dist_above_low:.1f}% above ${base_low:.2f}"
        ))

    # Entry #3 — MA-pullback (price near MA10 or MA20 inside range)
    for ma_label, ma_value in (("MA10", candidate.get("sma_10")),
                                ("MA20", candidate.get("sma_20"))):
        if ma_value and ma_value > 0:
            # Only eligible if price is INSIDE the base (MA within range)
            if base_low < ma_value < base_high:
                dist_pct = abs(current_price - ma_value) / current_price * 100.0
                if dist_pct <= _MA_PULLBACK_NEAR_PCT:
                    side = "at" if abs(current_price - ma_value) < 0.01 else (
                        "above" if current_price > ma_value else "below"
                    )
                    annotations.append((
                        f"ma_pullback_{ma_label.lower()}", "📉",
                        f"{dist_pct:.1f}% {side} {ma_label} ${ma_value:.2f}"
                    ))
                    break  # one MA-pullback callout per ticker

    # Entry #4 — Low-volume rest (mid-range drift, contracting volume)
    if adv_20 and adv_20 > 0:
        today_volume = snap.get("day", {}).get("v") or 0
        vol_pct = today_volume / adv_20 * 100.0
        range_size = base_high - base_low
        if range_size > 0:
            position_in_range = (current_price - base_low) / range_size
            mid_band_low = 0.5 - _LOWVOL_REST_MID_BAND  # 0.25
            mid_band_high = 0.5 + _LOWVOL_REST_MID_BAND  # 0.75
            if (vol_pct < _LOWVOL_REST_VOL_PCT and
                mid_band_low <= position_in_range <= mid_band_high):
                annotations.append((
                    "lowvol_rest", "💤",
                    f"vol {vol_pct:.0f}% ADV, mid-range"
                ))

    # Entry #5 — U&R deferred (needs swing-low logic + recent undercut
    # tracking that isn't in current schema — see memory file + task #98)

    return annotations


async def get_flag_watchlist(scan_date=None):
    """Return current TIGHTENING/COILED watchlist with entry-technique
    annotations per ticker.

    Reads MAX(scan_date) WHERE < CURRENT_DATE from mi_flag_candidates
    (trading-session-aware per ADR 0004 Gemini contract). Calls
    get_snapshot_all() for live prices. Computes annotations via
    compute_entry_technique_annotations.

    Args:
        scan_date: optional override; defaults to latest pre-today
                   scan_date in mi_flag_candidates

    Returns:
        list[dict] — one per watchlist ticker, with annotations list
    """
    from agents.market_intelligence import db
    from agents.market_intelligence.collector import get_snapshot_all

    pool = await db.get_pool()
    async with pool.acquire() as conn:
        if scan_date is None:
            scan_date = await conn.fetchval("""
                SELECT MAX(scan_date) FROM mi_flag_candidates
                WHERE scan_date < CURRENT_DATE
            """)
        if not scan_date:
            return []

        candidates = await conn.fetch("""
            SELECT ticker, stage, base_age, base_high, base_low,
                   sma_10, sma_20, runup_pct, range_contraction_ratio,
                   vol_contraction_ratio
            FROM mi_flag_candidates
            WHERE scan_date = $1
              AND stage IN ('TIGHTENING', 'COILED', 'TRIGGERED')
              AND base_high IS NOT NULL
            ORDER BY
                CASE stage WHEN 'TRIGGERED' THEN 1 WHEN 'COILED' THEN 2
                           WHEN 'TIGHTENING' THEN 3 END,
                base_age DESC
        """, scan_date)

        if not candidates:
            return []

        ticker_list = [c["ticker"] for c in candidates]
        # PERCENTILE_CONT(0.5) — see ADV-20 SSoT note in run_intraday_flag_break_scan.
        adv_rows = await conn.fetch("""
            SELECT ticker,
                   PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY volume) AS adv_20
            FROM (
                SELECT ticker, volume,
                       ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY trade_date DESC) AS rn
                FROM mi_daily_closes
                WHERE ticker = ANY($1::text[])
                  AND trade_date >= CURRENT_DATE - INTERVAL '40 days'
                  AND volume > 0
            ) sub
            WHERE rn <= 20
            GROUP BY ticker
        """, ticker_list)
        adv_map = {r["ticker"]: int(r["adv_20"] or 0) for r in adv_rows}

    # Single Polygon batch call
    snapshots = await get_snapshot_all()

    watchlist: list[dict] = []
    for cand in candidates:
        ticker = cand["ticker"]
        snap = snapshots.get(ticker)
        if not snap:
            continue
        current_price = (
            snap.get("day", {}).get("c")
            or snap.get("min", {}).get("c")
            or snap.get("lastTrade", {}).get("p")
        )
        if not current_price or current_price <= 0:
            continue
        annotations = compute_entry_technique_annotations(
            snap, dict(cand), adv_20=adv_map.get(ticker)
        )
        watchlist.append({
            "ticker": ticker,
            "stage": cand["stage"],
            "base_age": cand["base_age"],
            "base_high": float(cand["base_high"]),
            "base_low": float(cand["base_low"]) if cand["base_low"] else None,
            "current_price": float(current_price),
            "annotations": annotations,
            "scan_date": scan_date,
        })

    return watchlist


async def reconcile_flag_state_post_eod(scan_date):
    """Post-EOD reconciliation per Gemini contract 2026-05-23.

    After run_flag_scan commits its EOD classification (5:25 PM ET), flip
    parent_invalidated_eod = TRUE for any same-day break whose parent ticker
    is now classified INVALIDATED. Backward-check evidence script filters
    via parent_invalidated_eod = FALSE to evaluate structurally-surviving
    breakouts only.

    Also reconciles support-test rows (#95) by the same rule — a tested
    support that immediately invalidates structurally isn't worth counting
    in forward-return analysis.

    Args:
        scan_date: the date being classified (today in ET)

    Returns:
        tuple[int, int]: (breaks_invalidated, support_tests_invalidated)
    """
    from agents.market_intelligence import db
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        breaks_result = await conn.execute("""
            UPDATE mi_flag_breaks
               SET parent_invalidated_eod = TRUE,
                   invalidated_at = NOW()
             WHERE break_date = $1
               AND parent_invalidated_eod = FALSE
               AND ticker IN (
                   SELECT ticker FROM mi_flag_candidates
                    WHERE scan_date = $1
                      AND stage = 'INVALIDATED'
               )
        """, scan_date)
        tests_result = await conn.execute("""
            UPDATE mi_flag_support_tests
               SET parent_invalidated_eod = TRUE,
                   invalidated_at = NOW()
             WHERE test_date = $1
               AND parent_invalidated_eod = FALSE
               AND ticker IN (
                   SELECT ticker FROM mi_flag_candidates
                    WHERE scan_date = $1
                      AND stage = 'INVALIDATED'
               )
        """, scan_date)
        pullbacks_result = await conn.execute("""
            UPDATE mi_flag_ma_pullbacks
               SET parent_invalidated_eod = TRUE,
                   invalidated_at = NOW()
             WHERE pullback_date = $1
               AND parent_invalidated_eod = FALSE
               AND ticker IN (
                   SELECT ticker FROM mi_flag_candidates
                    WHERE scan_date = $1
                      AND stage = 'INVALIDATED'
               )
        """, scan_date)
        urs_result = await conn.execute("""
            UPDATE mi_flag_undercut_rally
               SET parent_invalidated_eod = TRUE,
                   invalidated_at = NOW()
             WHERE ur_date = $1
               AND parent_invalidated_eod = FALSE
               AND ticker IN (
                   SELECT ticker FROM mi_flag_candidates
                    WHERE scan_date = $1
                      AND stage = 'INVALIDATED'
               )
        """, scan_date)
        rests_result = await conn.execute("""
            UPDATE mi_flag_low_vol_rests
               SET parent_invalidated_eod = TRUE,
                   invalidated_at = NOW()
             WHERE rest_date = $1
               AND parent_invalidated_eod = FALSE
               AND ticker IN (
                   SELECT ticker FROM mi_flag_candidates
                    WHERE scan_date = $1
                      AND stage = 'INVALIDATED'
               )
        """, scan_date)
    breaks_count = int(breaks_result.split()[-1]) if breaks_result else 0
    tests_count = int(tests_result.split()[-1]) if tests_result else 0
    pullbacks_count = int(pullbacks_result.split()[-1]) if pullbacks_result else 0
    urs_count = int(urs_result.split()[-1]) if urs_result else 0
    rests_count = int(rests_result.split()[-1]) if rests_result else 0
    if rests_count:
        logger.info(f"reconcile_flag_state_post_eod: invalidated {rests_count} low-vol-rest rows")
        try:
            await db.log_audit_event(
                "flag_low_vol_rests_reconciled",
                f"{rests_count} intraday low-vol-rests marked parent_invalidated_eod=TRUE for {scan_date}",
            )
        except Exception:
            pass
    if breaks_count:
        logger.info(f"reconcile_flag_state_post_eod: invalidated {breaks_count} break rows")
        try:
            await db.log_audit_event(
                "flag_breaks_reconciled",
                f"{breaks_count} intraday breaks marked parent_invalidated_eod=TRUE for {scan_date}",
            )
        except Exception:
            pass
    if tests_count:
        logger.info(f"reconcile_flag_state_post_eod: invalidated {tests_count} support-test rows")
        try:
            await db.log_audit_event(
                "flag_support_tests_reconciled",
                f"{tests_count} intraday support-tests marked parent_invalidated_eod=TRUE for {scan_date}",
            )
        except Exception:
            pass
    if pullbacks_count:
        logger.info(f"reconcile_flag_state_post_eod: invalidated {pullbacks_count} ma-pullback rows")
        try:
            await db.log_audit_event(
                "flag_ma_pullbacks_reconciled",
                f"{pullbacks_count} intraday ma-pullbacks marked parent_invalidated_eod=TRUE for {scan_date}",
            )
        except Exception:
            pass
    if urs_count:
        logger.info(f"reconcile_flag_state_post_eod: invalidated {urs_count} undercut-rally rows")
        try:
            await db.log_audit_event(
                "flag_undercut_rally_reconciled",
                f"{urs_count} intraday U&Rs marked parent_invalidated_eod=TRUE for {scan_date}",
            )
        except Exception:
            pass
    return (breaks_count, tests_count, pullbacks_count, urs_count, rests_count)
