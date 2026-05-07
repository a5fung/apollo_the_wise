"""
Per-minute Relative Volume at Time (RVOL@T) baselines for EP entry gating.

Background
----------
The legacy `rel_volume = today_volume / 20d_daily_ADV` ratio is structurally
tiny pre-9:30 and at 9:31 because the numerator samples a thin slice of the
intraday volume curve while the denominator is the full-session total. This
mismatch let INTC enter at `rel_volume = 0.09` on 2026-04-24 (later flagged
in the weekly self-audit as a filter gap).

The fix is the canonical RVOL@T primitive used by TradingView, MarketChameleon,
and institutional VWAP execution algos: compare today's cumulative volume at
the current clock-time against the 20-day mean cumulative volume *at that same
clock-time*. Because the comparison is anchored to time-of-day, the U-shaped
intraday volume distribution is automatically baked into the denominator —
so a 9:31 reading of 2.0× means "twice as many shares traded by 9:31 as a
typical day's 9:31", directly interpretable.

Two anchors are stored per ticker in `mi_minute_volume_curves`:
- `pm`      : cumulative volume from 4:00 ET to clock-time, baseline for
              pre-market alerts (4:00 ≤ now < 9:30 ET).
- `session` : cumulative volume from 9:30 ET to clock-time, baseline for
              early regular-session alerts (9:30 ≤ now < 9:45 ET). Past 9:45,
              the existing `projected_vol_multiple` gate (in ep_detector)
              has enough session data to project full-day RVOL reliably, so
              this gate is intentionally not applied past that.

Universe is top ~500 by 20d dollar volume from `mi_stock_scores` — the
realistic gap-candidate set. Tickers outside the universe (small caps,
brand-new listings, halt-suspended) fall through to the existing absolute
share floor at gate time.
"""
from __future__ import annotations

import asyncio
import logging
import math
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Optional

import pytz

from agents.market_intelligence.collector import get_minute_bars
from agents.market_intelligence.db import (
    get_top_dollar_volume_universe,
    get_minute_volume_baseline,
    upsert_minute_volume_curves,
)

logger = logging.getLogger(__name__)

_ET = pytz.timezone("US/Eastern")

# Anchors
ANCHOR_PM = "pm"
ANCHOR_SESSION = "session"

# ET clock-minute bounds — minutes from midnight
PM_START_MIN = 4 * 60        # 240  → 4:00 ET
SESSION_START_MIN = 9 * 60 + 30  # 570  → 9:30 ET
SESSION_END_MIN = 16 * 60    # 960  → 16:00 ET

# Universe + lookback
# $5M trailing 20d $-vol floor ≈ 1500–2000 tickers. Earlier top-500 cap silently
# skipped the pm_rvol gate for ~85% of HIGH EP candidates (most pre-market
# gappers are mid/small caps outside top-500). max_tickers is a safety cap, not
# the operative knob — adjust UNIVERSE_MIN_DOLLAR_VOLUME to widen/narrow.
UNIVERSE_MIN_DOLLAR_VOLUME = 5_000_000.0
UNIVERSE_MAX_TICKERS = 5000
LOOKBACK_DAYS = 30        # calendar days; ~21 trading days
MIN_SAMPLE_N = 5          # require ≥5 days of history before publishing a baseline

# Gate thresholds (used by ep_detector)
MIN_PM_RVOL = 1.0         # pre-market pace ≥ normal
MIN_SESSION_RVOL = 1.0    # early-session pace ≥ normal
MIN_BASELINE_N_FOR_GATE = 10  # don't gate against shaky baselines

# Refresh concurrency — Polygon Starter is unlimited but the global lock in
# `_polygon_get` already serializes calls. Outer concurrency just queues
# faster — keep modest to avoid memory pressure.
_REFRESH_CONCURRENCY = 8


def _epoch_ms_to_et_minute(t_ms: int) -> tuple[date, int]:
    """Return (et_date, et_clock_minute) for a Polygon bar timestamp."""
    dt_utc = datetime.fromtimestamp(t_ms / 1000.0, tz=pytz.UTC)
    dt_et = dt_utc.astimezone(_ET)
    return dt_et.date(), dt_et.hour * 60 + dt_et.minute


async def _refresh_one_ticker(
    ticker: str, from_date: str, to_date: str
) -> list[dict]:
    """Fetch minute bars for `ticker`, build cumulative-volume tables for
    pm and session anchors per trading-day, then return one record per
    (anchor, et_clock_minute) with mean/stddev/sample_n across all days.

    Returns [] if not enough history was retrieved — the caller skips the
    ticker silently.
    """
    bars = await get_minute_bars(ticker, from_date, to_date)
    if not bars:
        return []

    # Bucket bars by (date, anchor, et_clock_minute) → volume sum.
    # A single ET clock-minute may receive multiple bars only across days;
    # within a day, Polygon emits one bar per minute when there's trade flow.
    per_day_minute_vol: dict[date, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for b in bars:
        try:
            t_ms = b.get("t")
            v = b.get("v") or 0
            if t_ms is None or v <= 0:
                continue
            d, m = _epoch_ms_to_et_minute(int(t_ms))
            if m < PM_START_MIN or m >= SESSION_END_MIN:
                continue
            per_day_minute_vol[d][m] += int(v)
        except Exception:
            continue

    if len(per_day_minute_vol) < MIN_SAMPLE_N:
        return []

    # For each day, build cumulative-from-anchor at every minute in the
    # anchor's window, then aggregate across days at each minute.
    pm_samples: dict[int, list[int]] = defaultdict(list)
    session_samples: dict[int, list[int]] = defaultdict(list)

    for d, minute_vol in per_day_minute_vol.items():
        # PM anchor: cumulate from 4:00 → 9:29 (PM_START_MIN..SESSION_START_MIN-1)
        cum = 0
        for m in range(PM_START_MIN, SESSION_START_MIN):
            cum += minute_vol.get(m, 0)
            if cum > 0:
                pm_samples[m].append(cum)
        # SESSION anchor: cumulate from 9:30 → 15:59 (SESSION_START_MIN..SESSION_END_MIN-1)
        cum = 0
        for m in range(SESSION_START_MIN, SESSION_END_MIN):
            cum += minute_vol.get(m, 0)
            if cum > 0:
                session_samples[m].append(cum)

    records: list[dict] = []
    for anchor, samples_by_minute in (
        (ANCHOR_PM, pm_samples),
        (ANCHOR_SESSION, session_samples),
    ):
        for minute, samples in samples_by_minute.items():
            if len(samples) < MIN_SAMPLE_N:
                continue
            mean = sum(samples) / len(samples)
            if mean <= 0:
                continue
            variance = sum((x - mean) ** 2 for x in samples) / len(samples)
            stddev = math.sqrt(variance)
            records.append({
                "ticker": ticker,
                "anchor": anchor,
                "et_clock_minute": minute,
                "mean_cum_vol": mean,
                "stddev_cum_vol": stddev,
                "sample_n": len(samples),
            })

    return records


async def refresh_curves(
    today: Optional[date] = None,
    min_dollar_volume: float = UNIVERSE_MIN_DOLLAR_VOLUME,
    max_tickers: int = UNIVERSE_MAX_TICKERS,
    lookback_days: int = LOOKBACK_DAYS,
) -> dict:
    """Rebuild minute-volume baselines for the dollar-volume-floor universe.

    Called nightly from the scheduler (~18:30 ET). Returns a summary dict for
    logging / job-success notifications:
      {tickers_attempted, tickers_succeeded, rows_written}.
    """
    et_today = today or datetime.now(_ET).date()
    # Use yesterday as the right edge — today's bars settle by EOD but we
    # want the curve to reflect closed sessions only.
    to_d = et_today - timedelta(days=1)
    from_d = to_d - timedelta(days=lookback_days)
    from_str, to_str = from_d.strftime("%Y-%m-%d"), to_d.strftime("%Y-%m-%d")

    universe = await get_top_dollar_volume_universe(
        min_dollar_volume=min_dollar_volume, max_tickers=max_tickers
    )
    if not universe:
        logger.warning("Minute volume curves: empty universe (no mi_stock_scores yet?)")
        return {"tickers_attempted": 0, "tickers_succeeded": 0, "rows_written": 0}

    sem = asyncio.Semaphore(_REFRESH_CONCURRENCY)
    succeeded = 0
    rows_written = 0

    async def _do_one(ticker: str):
        nonlocal succeeded, rows_written
        async with sem:
            try:
                recs = await _refresh_one_ticker(ticker, from_str, to_str)
                if recs:
                    written = await upsert_minute_volume_curves(recs)
                    succeeded += 1
                    rows_written += written
            except Exception as e:
                logger.warning(f"Curve refresh failed for {ticker}: {e}")

    await asyncio.gather(*[_do_one(t) for t in universe])

    summary = {
        "tickers_attempted": len(universe),
        "tickers_succeeded": succeeded,
        "rows_written": rows_written,
        "lookback_days": lookback_days,
        "window": f"{from_str}..{to_str}",
    }
    logger.info(f"Minute volume curves refreshed: {summary}")
    return summary


async def compute_rvol_at_time(
    ticker: str,
    now_et: datetime,
    today_premkt_vol: int,
    today_session_vol: int,
) -> Optional[dict]:
    """Compute today's RVOL@T for `ticker` given the clock-time `now_et`.

    Returns a dict with the gate inputs and metadata:
        {
          "anchor": "pm" | "session",
          "et_clock_minute": int,
          "today_cum_vol": int,
          "baseline_mean": float,
          "baseline_n": int,
          "rvol_at_time": float,
        }

    Returns None if:
      - now_et is outside the gating window (before 4:00 ET or at/past 16:00 ET),
      - or there's no baseline row for this ticker at this minute (caller
        should fall back to existing absolute floors).

    Pre-9:30 uses the `pm` anchor (cumulative from 4:00 ET); 9:30 onward uses
    the `session` anchor (cumulative from 9:30). Both anchors are populated
    by the nightly refresh for the entire 4:00-16:00 ET window.
    """
    et_minute = now_et.hour * 60 + now_et.minute

    if et_minute < PM_START_MIN:
        return None  # before pre-market open
    if et_minute >= SESSION_END_MIN:
        return None  # at/past 16:00 ET — outside gating window

    if et_minute < SESSION_START_MIN:
        anchor = ANCHOR_PM
        today_cum = max(0, int(today_premkt_vol or 0))
    else:
        anchor = ANCHOR_SESSION
        today_cum = max(0, int(today_session_vol or 0))

    baseline = await get_minute_volume_baseline(ticker, anchor, et_minute)
    if not baseline:
        return None
    mean = float(baseline["mean_cum_vol"] or 0.0)
    n = int(baseline["sample_n"] or 0)
    if mean <= 0 or n < MIN_SAMPLE_N:
        return None

    rvol = today_cum / mean if mean > 0 else 0.0
    return {
        "anchor": anchor,
        "et_clock_minute": et_minute,
        "today_cum_vol": today_cum,
        "baseline_mean": mean,
        "baseline_n": n,
        "rvol_at_time": round(rvol, 3),
    }
