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
from datetime import date
from statistics import median as _median_stat
from typing import Any, Optional

from agents.market_intelligence.parabolic_detector import _sma

logger = logging.getLogger(__name__)

_SCAN_CONCURRENCY = 8       # bound per-ticker history fetches
_HISTORY_DAYS     = 90      # 60d runup window + 25d base + buffer

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
_RUNUP_LOOKBACK_DAYS = 60       # Window for pre-pivot low (runup magnitude)
_RUNUP_MIN_RATIO     = 1.50     # pivot_high / 60d_low ≥ 1.5×  (runup ≥ 50%)
_PROXIMITY_BAND      = 0.20     # |close - pivot_high| / pivot_high ≤ 20%

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

_STAGE_ORDER = ("unqualified", "WATCH", "TIGHTENING", "COILED", "TRIGGERED")


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
        "breakout_close": None,
        "breakout_volume_ratio": None,
        "fresh_tight_fires": False,
        "fresh_2bar_tr_pct": None,
        "atr14_pct": None,
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
        base["reason"] = f"runup_{runup_pct*100:.0f}%_below_50%"
        return base

    # ── INVALIDATED checks (override everything except actual breakout) ─
    sma_10 = _sma(rows, today_idx, _SMA10_WINDOW)
    sma_20 = _sma(rows, today_idx, _SMA20_WINDOW)
    base["sma_10"] = sma_10
    base["sma_20"] = sma_20

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

    # ── Proximity gate: close within ±20% of pivot_close ────────────────
    # Anchor on pivot_close (not pivot_high) so shooting-star pivots whose
    # intraday high is 15-25% above the close don't structurally fail this
    # gate forever. The base typically forms beneath the wick high but
    # around the pivot's close.
    if abs(close_today - pivot_close) / pivot_close > _PROXIMITY_BAND:
        base["reason"] = (
            f"close_{close_today:.2f}_off_pivot_close_{pivot_close:.2f}_>20%"
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

    universe = await db.get_flag_universe(scan_date)
    by_stage: dict[str, list[dict]] = {
        "TRIGGERED": [], "COILED": [], "TIGHTENING": [],
        "WATCH": [], "INVALIDATED": [], "unqualified": [],
    }
    if not universe:
        logger.info(f"flag_scan {scan_date}: empty universe")
        return by_stage

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
                    await db.log_audit_event(
                        "mna_filter_fired",
                        f"{r['ticker']} via {(meta or {}).get('source', 'unknown')} (flag)",
                        detail=str({"detector": "flag", "stage": r['original_stage'], **(meta or {})})[:500],
                    )
            except Exception as e:
                logger.warning(f"flag_scan: M&A check failed for {r['ticker']}: {e}")

        await asyncio.gather(*(_mna_check(r) for r in actionable))

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
    return by_stage


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
        f"🚩 *Flag Scanner — {date_str}*",
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
