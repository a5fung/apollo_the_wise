"""
Cohort/metric-separation explorer (originally TI3 Fishhook Stage 0).

Pulls a HIGH-EP cohort over a trailing window, computes three candidate
consolidation metrics on a fixed hourly base window (T+3..T+4), labels by
forward 5d return >= threshold, emits a CSV + median-separation summary.
Read-only against prod data; no new tables, no production code edits.

== TI3 Fishhook outcome (2026-04-29) ==
Pass 1 (90d, broad cohort): 216 unique candidates, only `range_over_atr14`
showed any separation (pos median 1.275 vs neg 1.697); threshold sweep
maxed at 2x precision lift over base rate, dropping back to base rate at
recall >= 50%. Pass 2 (180d, strict cohort = closed AND total_pnl<0)
collapsed: only 2 unique tuples — Apollo's pre-trade filter (catalyst
quality + ATR stop sizing + 10:00 ET unfilled-cancel) leaves ~1 real
Day-1 stop-out per quarter, so the cohort TI3 needs doesn't exist in
this system. TI3 deferred — see `project_trading_ideas_backlog.md`.

This script is kept as a reusable feasibility tool. CLI flags
(`--days`, `--strict-cohort`, `--min-price`, `--label-threshold`) make
it usable for future "is this idea cardinality-feasible?" checks before
investing detector-build effort.

Run on prod after 16:00 ET or before 07:00 ET (the global `_polygon_lock`
is shared with live EP scans):
    docker exec apollo-market python -m scripts.fishhook_explorer
    docker exec apollo-market python -m scripts.fishhook_explorer --days 180 \\
        --strict-cohort --min-price 10 --label-threshold 0.15
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import logging
from datetime import date, datetime
from statistics import mean, stdev
from zoneinfo import ZoneInfo

from agents.market_intelligence.collector import _polygon_get
from agents.market_intelligence.db import get_pool

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")

CSV_COLS = [
    "ticker", "alert_date", "score_tier", "gap_pct", "d1_status", "d1_pnl",
    "base_start", "base_end", "n_hourly_bars",
    "range_pct", "daily_atr14_pct", "range_over_atr14",
    "atr_5h", "atr_20h", "atr5h_over_atr20h",
    "sma20_h", "std20_h", "bb_width_pct",
    "trigger_close", "fwd_max_close_5d", "fwd_5d_return",
    "label", "drop_reason",
]


async def fetch_cohort(window_days: int, strict_cohort: bool,
                       moderate_band_eval: bool = False) -> list[dict]:
    """`strict_cohort=True` restricts to real Day-1 failures only — the
    alert had to enter via ORB and be stopped out (`closed AND total_pnl<0`).
    Excludes `no_entry` (Apollo's quality gate already rejected) and
    `cancelled` (never filled). Pass-2 uses strict; Pass-1 (broad) does not.

    `moderate_band_eval=True` swaps the cohort for the conviction-floor
    extension question: would lifting MODERATE alerts in the gap∈[10,15)
    + strong-catalyst cell to a conviction floor produce edge? Pulls all
    HIGH+MODERATE alerts in that cell regardless of Day-1 outcome (we want
    forward-return distribution, not failure-conditional). Mutually
    exclusive with `strict_cohort`.

    The query also dedupes per (ticker, alert_date) — a single candidate
    spawns multiple `mi_ep_alerts` rows (one per scan tick), but only ONE
    downstream measurement can form.
    """
    pool = await get_pool()
    if moderate_band_eval:
        sql = """
            SELECT DISTINCT ON (a.ticker, a.alert_date)
                   a.ticker, a.alert_date, a.score_tier, a.gap_pct,
                   lt.status AS d1_status, lt.total_pnl AS d1_pnl
            FROM mi_ep_alerts a
            LEFT JOIN mi_live_trades lt
              ON lt.ticker = a.ticker AND lt.alert_date = a.alert_date
            WHERE a.alert_date >= CURRENT_DATE - $1::int
              AND a.score_tier IN ('HIGH','MODERATE')
              AND a.gap_pct >= 10 AND a.gap_pct < 15
              AND a.catalyst_quality = 'strong'
            ORDER BY a.ticker, a.alert_date, a.id ASC
        """
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, window_days)
        return [dict(r) for r in rows]
    if strict_cohort:
        sql = """
            SELECT DISTINCT ON (a.ticker, a.alert_date)
                   a.ticker, a.alert_date, a.score_tier, a.gap_pct,
                   lt.status AS d1_status, lt.total_pnl AS d1_pnl
            FROM mi_ep_alerts a
            JOIN mi_live_trades lt
              ON lt.ticker = a.ticker AND lt.alert_date = a.alert_date
            WHERE a.alert_date >= CURRENT_DATE - $1::int
              AND a.score_tier = 'HIGH'
              AND lt.status = 'closed'
              AND COALESCE(lt.total_pnl, 0) < 0
            ORDER BY a.ticker, a.alert_date, a.id ASC
        """
    else:
        sql = """
            SELECT DISTINCT ON (a.ticker, a.alert_date)
                   a.ticker, a.alert_date, a.score_tier, a.gap_pct,
                   lt.status AS d1_status, lt.total_pnl AS d1_pnl
            FROM mi_ep_alerts a
            LEFT JOIN mi_live_trades lt
              ON lt.ticker = a.ticker AND lt.alert_date = a.alert_date
            WHERE a.alert_date >= CURRENT_DATE - $1::int
              AND a.score_tier = 'HIGH'
              AND (
                    lt.id IS NULL
                 OR lt.status = 'cancelled'
                 OR (lt.status = 'closed' AND COALESCE(lt.total_pnl, 0) < 0)
              )
            ORDER BY a.ticker, a.alert_date, a.id ASC
        """
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, window_days)
    return [dict(r) for r in rows]


async def fetch_trading_axis(ticker: str, t0: date) -> tuple[list[dict], list[dict]]:
    """Returns (before, after).
    before: T-15..T-1 ascending (15 daily rows for 14-TR ATR_14).
    after:  T+1..T+10 ascending (10 rows: 2 base + 1 trigger + ≤6 fwd).
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        before = await conn.fetch(
            """
            SELECT trade_date, open_price, high_price, low_price, close
            FROM mi_daily_closes
            WHERE ticker = $1 AND trade_date < $2
            ORDER BY trade_date DESC
            LIMIT 15
            """,
            ticker, t0,
        )
        after = await conn.fetch(
            """
            SELECT trade_date, open_price, high_price, low_price, close
            FROM mi_daily_closes
            WHERE ticker = $1 AND trade_date > $2
            ORDER BY trade_date ASC
            LIMIT 10
            """,
            ticker, t0,
        )
    return list(reversed([dict(r) for r in before])), [dict(r) for r in after]


def compute_pre_gap_atr14(before: list[dict]) -> float | None:
    """ATR_14 anchored to T-1: simple-mean of 14 TRs over T-15..T-1.
    Returns None if any pre-gap OHLC row is missing — caller maps to insufficient_data.
    The Day-1 gap candle is excluded by construction (lookback ends at T-1).
    """
    if len(before) < 15:
        return None
    for r in before:
        if r["open_price"] is None or r["high_price"] is None or r["low_price"] is None:
            return None
    trs: list[float] = []
    for i in range(1, 15):
        h = float(before[i]["high_price"])
        l = float(before[i]["low_price"])
        prev_c = float(before[i - 1]["close"])
        trs.append(max(h - l, abs(h - prev_c), abs(l - prev_c)))
    return mean(trs)


def _et_midnight_ms(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, 0, 0, tzinfo=_ET).timestamp() * 1000)


def _et_eod_ms(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, 23, 59, tzinfo=_ET).timestamp() * 1000)


async def fetch_hourly_bars_rth(ticker: str, from_d: date, to_d: date) -> list[dict]:
    """Polygon hourly bars over [from_d, to_d], filtered to RTH session bars
    (ET hour 9..15 — the 9 bar covers 9:00–10:00 ET so 9:30 RTH start is
    inside it; the 16 bar is after-close).
    Each bar dict: {t, o, h, l, c, v}.
    """
    from_ms = _et_midnight_ms(from_d)
    to_ms = _et_eod_ms(to_d)
    try:
        data = await _polygon_get(
            f"/v2/aggs/ticker/{ticker}/range/1/hour/{from_ms}/{to_ms}",
            {"adjusted": "true", "sort": "asc", "limit": 50000},
        )
        bars = data.get("results", []) or []
    except Exception as e:
        logger.warning(f"Hourly bars failed for {ticker} {from_d}..{to_d}: {e}")
        return []
    rth: list[dict] = []
    for b in bars:
        bt = datetime.fromtimestamp(b["t"] / 1000, tz=_ET)
        if bt.weekday() >= 5:
            continue
        if 9 <= bt.hour <= 15:
            rth.append(b)
    return rth


def _bars_in_dates(bars: list[dict], dates: set[date]) -> list[dict]:
    out = []
    for b in bars:
        bt = datetime.fromtimestamp(b["t"] / 1000, tz=_ET)
        if bt.date() in dates:
            out.append(b)
    return out


def compute_atr_h(bars: list[dict], n: int) -> float | None:
    """Simple-mean hourly ATR over the last n TRs (Wilder approx)."""
    if len(bars) < n + 1:
        return None
    sub = bars[-(n + 1):]
    trs: list[float] = []
    for i in range(1, len(sub)):
        h = sub[i]["h"]
        l = sub[i]["l"]
        prev_c = sub[i - 1]["c"]
        trs.append(max(h - l, abs(h - prev_c), abs(l - prev_c)))
    return mean(trs)


def compute_bb_width(bars: list[dict], n: int = 20) -> tuple[float | None, float | None, float | None]:
    """Returns (sma, std, bb_width_pct) on last n bar closes. width = 4σ / sma."""
    if len(bars) < n:
        return None, None, None
    closes = [b["c"] for b in bars[-n:]]
    sma = mean(closes)
    sd = stdev(closes) if n > 1 else 0.0
    width = (4 * sd) / sma if sma else None
    return sma, sd, width


def _drop(c: dict, reason: str) -> dict:
    row = {k: None for k in CSV_COLS}
    row["ticker"] = c["ticker"]
    row["alert_date"] = c["alert_date"]
    row["score_tier"] = c["score_tier"]
    row["gap_pct"] = float(c["gap_pct"]) if c["gap_pct"] is not None else None
    row["d1_status"] = c["d1_status"]
    row["d1_pnl"] = float(c["d1_pnl"]) if c["d1_pnl"] is not None else None
    row["label"] = "insufficient_data"
    row["drop_reason"] = reason
    return row


async def process_candidate(c: dict, min_price: float, label_threshold: float) -> dict:
    ticker = c["ticker"]
    t0 = c["alert_date"]

    before, after = await fetch_trading_axis(ticker, t0)

    # Need T+1..T+10 for base (T+3,T+4) + trigger (T+5) + fwd window (T+5..T+10)
    if len(after) < 10:
        return _drop(c, "fwd_window_short")

    atr14 = compute_pre_gap_atr14(before)
    if atr14 is None:
        return _drop(c, "ohlc_pre_gap_missing")

    # Price gate uses prior-day close (T-1) — institutional liquidity proxy
    prior_close = float(before[-1]["close"]) if before else 0.0
    if prior_close < min_price:
        return _drop(c, f"price_below_{min_price:g}")

    t_plus = {i + 1: after[i]["trade_date"] for i in range(len(after))}
    base_dates = {t_plus[3], t_plus[4]}
    bb_window_dates = {t_plus[2], t_plus[3], t_plus[4]}  # 3 sessions ≈ 21 RTH bars

    hourly = await fetch_hourly_bars_rth(ticker, t_plus[2], t_plus[4])
    if not hourly:
        return _drop(c, "hourly_bars_empty")

    base_bars = _bars_in_dates(hourly, base_dates)
    bb_bars = _bars_in_dates(hourly, bb_window_dates)

    if len(base_bars) < 6:
        return _drop(c, "base_bars_thin")

    base_high = max(b["h"] for b in base_bars)
    base_low = min(b["l"] for b in base_bars)
    range_dollars = base_high - base_low
    range_over_atr14 = range_dollars / atr14 if atr14 > 0 else None

    last_close_pre = float(before[-1]["close"]) if before else 0.0
    atr14_pct = atr14 / last_close_pre if last_close_pre else None
    range_pct = range_dollars / last_close_pre if last_close_pre else None

    atr5h = compute_atr_h(bb_bars, 5)
    atr20h = compute_atr_h(bb_bars, 20)
    atr_ratio = (atr5h / atr20h) if (atr5h is not None and atr20h not in (None, 0)) else None

    sma20, std20, bb_width = compute_bb_width(bb_bars, 20)

    trigger_close = float(after[4]["close"])  # T+5
    fwd_closes = [float(after[i]["close"]) for i in range(4, 10)]  # T+5..T+10
    fwd_max = max(fwd_closes)
    fwd_5d_return = (fwd_max / trigger_close) - 1 if trigger_close else None

    label = "positive" if (fwd_5d_return is not None and fwd_5d_return >= label_threshold) else "negative"

    return {
        "ticker": ticker,
        "alert_date": t0,
        "score_tier": c["score_tier"],
        "gap_pct": float(c["gap_pct"]) if c["gap_pct"] is not None else None,
        "d1_status": c["d1_status"],
        "d1_pnl": float(c["d1_pnl"]) if c["d1_pnl"] is not None else None,
        "base_start": t_plus[3],
        "base_end": t_plus[4],
        "n_hourly_bars": len(base_bars),
        "range_pct": range_pct,
        "daily_atr14_pct": atr14_pct,
        "range_over_atr14": range_over_atr14,
        "atr_5h": atr5h,
        "atr_20h": atr20h,
        "atr5h_over_atr20h": atr_ratio,
        "sma20_h": sma20,
        "std20_h": std20,
        "bb_width_pct": bb_width,
        "trigger_close": trigger_close,
        "fwd_max_close_5d": fwd_max,
        "fwd_5d_return": fwd_5d_return,
        "label": label,
        "drop_reason": "",
    }


async def run(window_days: int, out_path: str, *, strict_cohort: bool,
              min_price: float, label_threshold: float,
              moderate_band_eval: bool = False) -> None:
    cohort = await fetch_cohort(window_days, strict_cohort, moderate_band_eval)
    if moderate_band_eval:
        cohort_kind = "moderate-band-eval (HIGH|MODERATE, gap[10,15), strong)"
    elif strict_cohort:
        cohort_kind = "strict (closed/pnl<0)"
    else:
        cohort_kind = "broad (no_entry|cancelled|closed_loss)"
    logger.info(
        f"Cohort: {len(cohort)} HIGH alerts, last {window_days}d, "
        f"kind={cohort_kind}, min_price=${min_price:g}, label≥{label_threshold:.0%}"
    )
    if not cohort:
        logger.warning("Empty cohort — nothing to write.")
        return

    # ATR sanity print on the first 2 candidates with valid pre-gap window
    sanity_emitted = 0
    rows: list[dict] = []
    label_counts: dict[str, int] = {"positive": 0, "negative": 0, "insufficient_data": 0}
    drop_reasons: dict[str, int] = {}

    for i, c in enumerate(cohort, 1):
        try:
            r = await process_candidate(c, min_price, label_threshold)
        except Exception as e:
            logger.exception(f"[{i}/{len(cohort)}] {c['ticker']} {c['alert_date']}: {e}")
            r = _drop(c, f"error:{type(e).__name__}")

        rows.append(r)
        label_counts[r["label"]] = label_counts.get(r["label"], 0) + 1
        if r["label"] == "insufficient_data":
            dr = r.get("drop_reason") or "unknown"
            drop_reasons[dr] = drop_reasons.get(dr, 0) + 1
        elif sanity_emitted < 2 and r.get("daily_atr14_pct") is not None:
            logger.info(
                f"ATR sanity: {r['ticker']} {r['alert_date']} "
                f"pre_gap_ATR14_pct={r['daily_atr14_pct']:.4f} "
                f"range_pct={r['range_pct']:.4f} "
                f"range_over_atr14={r['range_over_atr14']:.3f}"
            )
            sanity_emitted += 1
        if i % 10 == 0:
            logger.info(f"[{i}/{len(cohort)}] {label_counts}")

    with open(out_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in CSV_COLS})

    logger.info(f"Wrote {len(rows)} rows to {out_path}")
    logger.info(f"Label counts: {label_counts}")
    if drop_reasons:
        logger.info(f"insufficient_data breakdown: {drop_reasons}")

    # Median separation snapshot per metric (positive vs negative)
    pos = [r for r in rows if r["label"] == "positive"]
    neg = [r for r in rows if r["label"] == "negative"]
    logger.info(f"Eligible (non-insufficient): pos={len(pos)} neg={len(neg)}")
    for col in ("range_over_atr14", "atr5h_over_atr20h", "bb_width_pct"):
        pv = [r[col] for r in pos if r[col] is not None]
        nv = [r[col] for r in neg if r[col] is not None]
        if pv and nv:
            from statistics import median
            logger.info(f"  {col}: median_pos={median(pv):.4f} (n={len(pv)})  "
                        f"median_neg={median(nv):.4f} (n={len(nv)})")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    p.add_argument("--days", type=int, default=90, help="Trailing window for cohort (default 90)")
    p.add_argument("--out", default="/tmp/fishhook_explorer.csv", help="Output CSV path")
    p.add_argument("--strict-cohort", action="store_true",
                   help="Restrict to real Day-1 failures (closed AND total_pnl<0). "
                        "Excludes no_entry and cancelled.")
    p.add_argument("--moderate-band-eval", action="store_true",
                   help="Conviction-floor extension cohort: HIGH+MODERATE alerts in "
                        "gap[10,15) + catalyst='strong' cell, all Day-1 outcomes. "
                        "Mutually exclusive with --strict-cohort.")
    p.add_argument("--min-price", type=float, default=0.0,
                   help="Min prior-day close in dollars (drops penny-stock noise). Default 0.")
    p.add_argument("--label-threshold", type=float, default=0.10,
                   help="Forward 5d return required for positive label. Default 0.10 (10%%).")
    args = p.parse_args()
    if args.strict_cohort and args.moderate_band_eval:
        p.error("--strict-cohort and --moderate-band-eval are mutually exclusive")
    asyncio.run(run(
        args.days, args.out,
        strict_cohort=args.strict_cohort,
        min_price=args.min_price,
        label_threshold=args.label_threshold,
        moderate_band_eval=args.moderate_band_eval,
    ))


if __name__ == "__main__":
    main()
