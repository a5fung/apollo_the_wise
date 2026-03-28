"""
Historical EP Scanner — retroactively identifies gap-up candidates from Polygon
daily data and inserts them as alerts into mi_ep_alerts for backtest validation.

Usage (on Hetzner server, inside apollo-market container):
    python -m agents.market_intelligence.backtester.historical_scan \
        --from 2025-03-01 --to 2026-03-20

All candidates get a fixed score (80, HIGH) — we're testing trading rules,
not the scoring model.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from collections import defaultdict
from datetime import date, timedelta
from typing import Optional

from agents.market_intelligence.collector import (
    get_grouped_daily,
    get_index_history,
    et_today,
    prev_trading_days,
)
from agents.market_intelligence.constants import SKIP_TICKERS
from agents.market_intelligence.db import (
    delete_historical_alerts,
    get_daily_closes_count,
    get_pool,
    ingest_daily_closes,
    insert_ep_alert,
    upsert_regime,
)
from agents.market_intelligence.regime import _determine_regime, _moving_average, _ema

logger = logging.getLogger(__name__)

# Scan thresholds
DEFAULT_MIN_GAP_PCT = 10.0
DEFAULT_MIN_RVOL = 2.0
MIN_PRICE = 5.0
MAX_TICKER_LEN = 5
QUICK_VOL_MULTIPLIER = 2.0  # Pre-filter: today volume >= 2x prev day volume
MIN_MEDIAN_DOLLAR_VOL = 5_000_000  # $5M median daily dollar volume — mcap proxy for historical scans


# ── Orchestrator ──────────────────────────────────────────────────────────────

async def run_historical_scan(
    from_date: date,
    to_date: date,
    min_gap_pct: float = DEFAULT_MIN_GAP_PCT,
    min_rvol: float = DEFAULT_MIN_RVOL,
) -> dict:
    """
    Scan historical Polygon data for EP gap-up candidates and insert into mi_ep_alerts.

    Steps:
        1. Backfill mi_daily_closes for range + 30-day warmup
        2. Backfill regime data (SPY/QQQ/UVXY only)
        3. Scan each trading date for gap-up candidates
        4. Print summary

    Idempotent: deletes prior historical alerts in range before re-scanning.
    """
    logger.info(f"Historical EP scan: {from_date} to {to_date} "
                f"(min_gap={min_gap_pct}%, min_rvol={min_rvol}x)")

    # Step 0: Clean prior historical alerts for idempotent re-runs
    deleted = await delete_historical_alerts(from_date, to_date)
    if deleted:
        logger.info(f"Deleted {deleted} prior historical alerts in range")

    # Step 1: Backfill daily closes (includes warmup period for rvol calc)
    await _backfill_daily_closes(from_date, to_date)

    # Step 2: Backfill regime data
    await _backfill_regimes(from_date, to_date)

    # Step 3: Scan each trading date
    # Build list of trading dates (weekdays) in range
    trading_dates = _get_trading_dates(from_date, to_date)
    logger.info(f"Scanning {len(trading_dates)} trading dates")

    # We need 1 warmup day before the first scan date for prev_grouped
    warmup_date = _prev_weekday(trading_dates[0])

    total_alerts = 0
    monthly_counts: dict[str, int] = defaultdict(int)
    dates_scanned = 0

    prev_grouped = await get_grouped_daily(warmup_date.strftime("%Y-%m-%d"))
    if not prev_grouped:
        # Try one more day back
        warmup_date = _prev_weekday(warmup_date)
        prev_grouped = await get_grouped_daily(warmup_date.strftime("%Y-%m-%d"))

    for trade_date in trading_dates:
        curr_grouped = await get_grouped_daily(trade_date.strftime("%Y-%m-%d"))
        if not curr_grouped:
            logger.debug(f"No data for {trade_date} (holiday?), skipping")
            continue

        candidates = await _scan_date(
            trade_date, curr_grouped, prev_grouped,
            min_gap_pct=min_gap_pct, min_rvol=min_rvol,
        )

        for c in candidates:
            await insert_ep_alert({
                "ticker": c["ticker"],
                "alert_date": trade_date,
                "gap_pct": c["gap_pct"],
                "rel_volume": c["rel_volume"],
                "ep_score": 80,
                "score_tier": "HIGH",
                "catalyst_quality": "unknown",
                "catalyst": f"Historical scan: {c['gap_pct']:.1f}% gap, {c['rel_volume']:.1f}x rvol",
                "source": "historical_scan",
            })

        month_key = trade_date.strftime("%Y-%m")
        monthly_counts[month_key] += len(candidates)
        total_alerts += len(candidates)
        dates_scanned += 1

        if candidates:
            logger.info(f"{trade_date}: {len(candidates)} candidates "
                        f"(e.g. {candidates[0]['ticker']} +{candidates[0]['gap_pct']:.1f}%)")

        prev_grouped = curr_grouped  # slide window

    # Step 4: Summary
    summary = {
        "from_date": str(from_date),
        "to_date": str(to_date),
        "dates_scanned": dates_scanned,
        "total_alerts": total_alerts,
        "monthly_counts": dict(monthly_counts),
    }

    print("\n" + "=" * 60)
    print("HISTORICAL EP SCAN COMPLETE")
    print("=" * 60)
    print(f"  Date range:    {from_date} to {to_date}")
    print(f"  Dates scanned: {dates_scanned}")
    print(f"  Total alerts:  {total_alerts}")
    print(f"  Avg per day:   {total_alerts / max(dates_scanned, 1):.1f}")
    print()
    print("  Monthly breakdown:")
    for month in sorted(monthly_counts):
        print(f"    {month}: {monthly_counts[month]} alerts")
    print("=" * 60)

    return summary


# ── Step 1: Backfill daily closes ─────────────────────────────────────────────

async def _backfill_daily_closes(from_date: date, to_date: date) -> int:
    """
    Ensure mi_daily_closes covers from_date - 30 days through to_date.
    Follows bootstrap_daily_closes pattern: skip dates with >1000 rows.
    """
    warmup_start = from_date - timedelta(days=45)  # 45 cal days ~ 30 trading days
    trading_dates = _get_trading_dates(warmup_start, to_date)

    total_ingested = 0
    for td in trading_dates:
        existing = await get_daily_closes_count(td)
        if existing > 1000:
            continue  # already have this day

        td_str = td.strftime("%Y-%m-%d")
        bars = await get_grouped_daily(td_str)
        if not bars:
            continue

        count = await ingest_daily_closes(td, bars)
        total_ingested += count
        if count > 0:
            logger.debug(f"Backfill daily closes: {td_str} — {count} tickers")

    logger.info(f"Daily closes backfill complete: {total_ingested} rows ingested")
    return total_ingested


# ── Step 2: Backfill regimes ──────────────────────────────────────────────────

async def _backfill_regimes(from_date: date, to_date: date) -> int:
    """
    Backfill mi_market_regime for the scan range.
    Uses SPY, QQQ, UVXY daily bars only (3 API calls total).
    No breadth data (mi_stock_scores not available historically).
    """
    # Fetch full history with warmup for moving averages (200 days)
    warmup_start = from_date - timedelta(days=300)  # ~200 trading days
    warmup_str = warmup_start.strftime("%Y-%m-%d")
    to_str = to_date.strftime("%Y-%m-%d")

    logger.info(f"Fetching index history for regime backfill ({warmup_str} to {to_str})")
    spy_bars, qqq_bars, uvxy_bars = await asyncio.gather(
        get_index_history("SPY", warmup_str, to_str),
        get_index_history("QQQ", warmup_str, to_str),
        get_index_history("I:VIX", warmup_str, to_str),
    )

    # Build date-indexed close maps
    spy_closes = _bars_to_date_closes(spy_bars)
    qqq_closes = _bars_to_date_closes(qqq_bars)
    vix_closes = _bars_to_date_closes(uvxy_bars)

    # Get ordered list of all SPY trading dates
    all_spy_dates = sorted(spy_closes.keys())

    trading_dates = _get_trading_dates(from_date, to_date)
    regimes_upserted = 0

    for td in trading_dates:
        # Get SPY closes up to this date for MA calculations
        spy_closes_to_date = [spy_closes[d] for d in all_spy_dates if d <= td]
        qqq_closes_to_date = [qqq_closes[d] for d in sorted(qqq_closes.keys()) if d <= td]

        if len(spy_closes_to_date) < 50:
            continue  # not enough data for 50MA

        # Compute regime inputs
        spy_50ma = _moving_average(spy_closes_to_date, 50)
        spy_200ma = _moving_average(spy_closes_to_date, 200)
        qqq_50ma = _moving_average(qqq_closes_to_date, 50) if len(qqq_closes_to_date) >= 50 else None

        spy_close = spy_closes_to_date[-1]
        qqq_close = qqq_closes_to_date[-1] if qqq_closes_to_date else None
        vix = vix_closes.get(td)

        spy_vs_50 = ((spy_close / spy_50ma) - 1) * 100 if spy_50ma else None
        spy_vs_200 = ((spy_close / spy_200ma) - 1) * 100 if spy_200ma else None
        qqq_vs_50 = ((qqq_close / qqq_50ma) - 1) * 100 if (qqq_close and qqq_50ma) else None

        # QQQ EMAs
        qqq_ema_10 = _ema(qqq_closes_to_date, 10) if len(qqq_closes_to_date) >= 10 else None
        qqq_ema_20 = _ema(qqq_closes_to_date, 20) if len(qqq_closes_to_date) >= 20 else None
        qqq_ema_bullish = (qqq_ema_10 > qqq_ema_20) if (qqq_ema_10 and qqq_ema_20) else None

        # Determine regime (no breadth data for historical)
        regime, description, ep_threshold = _determine_regime(
            spy_vs_50ma=spy_vs_50,
            spy_vs_200ma=spy_vs_200,
            qqq_vs_50ma=qqq_vs_50,
            vix=vix,
            breadth_pct=None,
            pct4_ratio_5d=None,
            pct4_ratio_10d=None,
        )

        await upsert_regime({
            "regime_date": td,
            "regime": regime,
            "spy_vs_50ma": spy_vs_50,
            "spy_vs_200ma": spy_vs_200,
            "qqq_vs_50ma": qqq_vs_50,
            "vix": vix,
            "description": description,
            "ep_threshold": ep_threshold,
            "qqq_ema_10": qqq_ema_10,
            "qqq_ema_20": qqq_ema_20,
            "qqq_ema_bullish": qqq_ema_bullish,
        })
        regimes_upserted += 1

    logger.info(f"Regime backfill complete: {regimes_upserted} dates")
    return regimes_upserted


# ── Step 3: Per-date scanner ──────────────────────────────────────────────────

async def _scan_date(
    trade_date: date,
    curr_grouped: dict[str, dict],
    prev_grouped: dict[str, dict],
    min_gap_pct: float = DEFAULT_MIN_GAP_PCT,
    min_rvol: float = DEFAULT_MIN_RVOL,
) -> list[dict]:
    """
    Scan a single date for EP gap-up candidates.

    Quick filter (from grouped daily data):
        - gap% >= threshold
        - today volume >= 2x prev day volume
        - price >= $5
        - ticker length <= 5, not in SKIP_TICKERS

    Then batch-query mi_daily_closes for proper 20-day median rvol.
    """
    quick_candidates = []

    for ticker, curr in curr_grouped.items():
        # Basic ticker filter
        if len(ticker) > MAX_TICKER_LEN or "." in ticker:
            continue
        if ticker in SKIP_TICKERS:
            continue

        prev = prev_grouped.get(ticker)
        if not prev:
            continue

        prev_close = prev.get("c")
        curr_open = curr.get("o")
        curr_volume = curr.get("v", 0)
        prev_volume = prev.get("v", 0)

        if not prev_close or not curr_open or prev_close <= 0:
            continue
        if curr_open < MIN_PRICE:
            continue

        # Gap percentage
        gap_pct = ((curr_open - prev_close) / prev_close) * 100
        if gap_pct < min_gap_pct:
            continue

        # Quick volume filter: today vol >= 2x prev day vol
        if prev_volume <= 0 or curr_volume < prev_volume * QUICK_VOL_MULTIPLIER:
            continue

        quick_candidates.append({
            "ticker": ticker,
            "gap_pct": gap_pct,
            "curr_volume": curr_volume,
        })

    if not quick_candidates:
        return []

    # Batch compute proper rvol + dollar volume from mi_daily_closes
    tickers = [c["ticker"] for c in quick_candidates]
    median_volumes, median_dollar_vols = await _compute_batch_rvol(tickers, trade_date)

    results = []
    for c in quick_candidates:
        ticker = c["ticker"]
        median_vol = median_volumes.get(ticker)

        # Dollar volume filter — historical mcap proxy ($5M median daily)
        median_dv = median_dollar_vols.get(ticker, 0)
        if median_dv < MIN_MEDIAN_DOLLAR_VOL:
            continue

        if median_vol and median_vol > 0:
            rel_volume = c["curr_volume"] / median_vol
        else:
            continue  # no volume history = skip

        if rel_volume < min_rvol:
            continue

        results.append({
            "ticker": ticker,
            "gap_pct": c["gap_pct"],
            "rel_volume": rel_volume,
        })

    # Sort by gap% descending
    results.sort(key=lambda x: -x["gap_pct"])
    return results


async def _compute_batch_rvol(
    tickers: list[str], trade_date: date,
) -> tuple[dict[str, float], dict[str, float]]:
    """
    Single SQL query: 20-day median volume AND median dollar volume for all candidate tickers.
    Returns (median_volumes, median_dollar_volumes).
    """
    if not tickers:
        return {}, {}

    pool = await get_pool()
    lookback_start = trade_date - timedelta(days=35)  # ~20 trading days

    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT ticker,
                   PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY volume) as median_vol,
                   PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY close * volume) as median_dollar_vol
            FROM mi_daily_closes
            WHERE ticker = ANY($1)
              AND trade_date >= $2
              AND trade_date < $3
              AND volume > 0
            GROUP BY ticker
            HAVING COUNT(*) >= 10
        """, tickers, lookback_start, trade_date)

    median_vols = {r["ticker"]: float(r["median_vol"]) for r in rows}
    median_dollar_vols = {r["ticker"]: float(r["median_dollar_vol"]) for r in rows}
    return median_vols, median_dollar_vols


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_trading_dates(from_date: date, to_date: date) -> list[date]:
    """Return list of weekdays (Mon-Fri) between from_date and to_date inclusive."""
    dates = []
    d = from_date
    while d <= to_date:
        if d.weekday() < 5:  # Mon-Fri
            dates.append(d)
        d += timedelta(days=1)
    return dates


def _prev_weekday(d: date) -> date:
    """Return the previous weekday before d."""
    d = d - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def _bars_to_date_closes(bars: list[dict]) -> dict[date, float]:
    """Convert Polygon bars (with 't' timestamp in ms) to {date: close}."""
    result = {}
    for bar in bars:
        ts = bar.get("t")
        close = bar.get("c")
        if ts and close:
            d = date.fromtimestamp(ts / 1000)
            result[d] = close
    return result


# ── CLI entry point ───────────────────────────────────────────────────────────

async def main(args: argparse.Namespace) -> None:
    from_date = date.fromisoformat(args.from_date)
    to_date = date.fromisoformat(args.to_date)

    summary = await run_historical_scan(
        from_date=from_date,
        to_date=to_date,
        min_gap_pct=args.min_gap,
        min_rvol=args.min_rvol,
    )

    if args.run_backtest:
        from agents.market_intelligence.backtester.engine import run_backtest
        from agents.market_intelligence.backtester.report import export_csv, generate_report

        print("\nRunning backtest on historical alerts...")
        result = await run_backtest(
            from_date=from_date,
            to_date=to_date,
            min_score=70,
            source_filter="historical_scan",
        )
        report = generate_report(result)
        print(report)

        if args.csv:
            from pathlib import Path
            csv_data = export_csv(result)
            Path(args.csv).write_text(csv_data)
            print(f"\nTrade log exported to {args.csv}")


def cli() -> None:
    parser = argparse.ArgumentParser(
        description="Historical EP Scanner — backfill gap-up candidates for backtest validation",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--from", dest="from_date", type=str, required=True,
                        help="Start date (YYYY-MM-DD)")
    parser.add_argument("--to", dest="to_date", type=str, required=True,
                        help="End date (YYYY-MM-DD)")
    parser.add_argument("--min-gap", type=float, default=DEFAULT_MIN_GAP_PCT,
                        help="Minimum gap percentage")
    parser.add_argument("--min-rvol", type=float, default=DEFAULT_MIN_RVOL,
                        help="Minimum relative volume")
    parser.add_argument("--run-backtest", action="store_true",
                        help="Run backtest after scan completes")
    parser.add_argument("--csv", type=str, default=None,
                        help="Export backtest results to CSV file")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Verbose logging")

    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    asyncio.run(main(args))


if __name__ == "__main__":
    cli()
