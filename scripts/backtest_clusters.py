"""
Backtest correlation clustering signal quality against historical theme data.

Usage:
    python scripts/backtest_clusters.py --from 2024-10-01 --to 2025-02-01

Metrics:
    Precision: % of clusters found on day D where those tickers appeared in
               the same mi_themes row 2–6 weeks later.
    Recall:    For each theme that emerged in the window, did the engine flag
               those tickers as a cluster 2+ weeks before the theme appeared?

Target: Precision >= 30% before treating clusters as production signal.
        Recall >= 60% means the engine genuinely front-runs semantic discovery.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import os
from collections import defaultdict
from datetime import date, timedelta

# Make project importable when run from repo root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def _get_trading_days(from_date: date, to_date: date) -> list[date]:
    """Return trading days in range from mi_daily_closes."""
    from agents.market_intelligence.db import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT DISTINCT trade_date FROM mi_daily_closes "
            "WHERE trade_date >= $1 AND trade_date <= $2 ORDER BY trade_date",
            from_date, to_date,
        )
    return [r["trade_date"] for r in rows]


async def _get_themes_between(after: date, before: date) -> list[dict]:
    """Return all theme rows in the given date range."""
    from agents.market_intelligence.db import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT theme_date, name, tickers FROM mi_themes "
            "WHERE theme_date >= $1 AND theme_date <= $2",
            after, before,
        )
    return [dict(r) for r in rows]


def _cluster_became_theme(
    cluster_tickers: list[str],
    themes: list[dict],
    match_threshold: float = 0.5,
) -> bool:
    """
    Return True if >= match_threshold of cluster tickers appeared in the
    same theme row within the look-ahead window.
    """
    cluster_set = set(cluster_tickers)
    for t in themes:
        theme_tickers = set(t.get("tickers") or [])
        if not theme_tickers:
            continue
        overlap = len(cluster_set & theme_tickers) / len(cluster_set)
        if overlap >= match_threshold:
            return True
    return False


def _theme_was_flagged_early(
    theme_tickers: list[str],
    earlier_clusters: list[tuple[date, list[dict]]],
    match_threshold: float = 0.5,
) -> tuple[bool, int | None]:
    """
    Return (found, days_ahead) if theme_tickers appear in any cluster
    from earlier_clusters at match_threshold.
    """
    theme_set = set(theme_tickers)
    for cluster_date, clusters in earlier_clusters:
        for c in clusters:
            cluster_set = set(c["tickers"])
            if not cluster_set:
                continue
            overlap = len(theme_set & cluster_set) / len(theme_set)
            if overlap >= match_threshold:
                return True, None  # found
    return False, None


async def run_backtest(from_date: date, to_date: date) -> None:
    from agents.market_intelligence.db import initialize_schema
    from agents.market_intelligence.correlation_engine import run_correlation_clustering

    print(f"Backtest: {from_date} → {to_date}")
    await initialize_schema()

    trading_days = await _get_trading_days(from_date, to_date)
    if not trading_days:
        print("No trading days found in mi_daily_closes for this range.")
        return

    print(f"Found {len(trading_days)} trading days. Running correlation clustering per day...")

    # Collect clusters per day (expensive — runs on historical data)
    clusters_by_day: dict[date, list[dict]] = {}
    for i, day in enumerate(trading_days):
        try:
            clusters = await run_correlation_clustering(day)
            clusters_by_day[day] = clusters
            if (i + 1) % 10 == 0:
                print(f"  {i + 1}/{len(trading_days)} — {day}: {len(clusters)} clusters")
        except Exception as e:
            print(f"  {day}: ERROR — {e}")
            clusters_by_day[day] = []

    print(f"\nCluster generation complete. Computing metrics...")

    # Precision: for each cluster on day D, check themes 2–6 weeks later
    lookahead_min = timedelta(days=14)
    lookahead_max = timedelta(days=42)
    lookback_min = timedelta(days=14)

    precision_hits = 0
    precision_total = 0

    for day, clusters in clusters_by_day.items():
        if not clusters:
            continue
        after = day + lookahead_min
        before = day + lookahead_max
        # Look-ahead deliberately extends past to_date — themes may emerge after the clustering window.
        future_themes = await _get_themes_between(after, before)
        for c in clusters:
            precision_total += 1
            if _cluster_became_theme(c["tickers"], future_themes):
                precision_hits += 1

    precision = precision_hits / precision_total if precision_total else 0.0

    # Recall: for each theme that emerged in the look-ahead window after the clustering period
    all_themes = await _get_themes_between(from_date + lookahead_min, to_date + lookahead_max)
    # Deduplicate themes by name (keep first occurrence)
    seen_themes: dict[str, dict] = {}
    for t in sorted(all_themes, key=lambda x: x["theme_date"]):
        if t["name"] not in seen_themes:
            seen_themes[t["name"]] = t

    recall_found = 0
    recall_total = 0

    for theme in seen_themes.values():
        theme_day = theme["theme_date"]
        tickers = theme.get("tickers") or []
        if not tickers:
            continue
        recall_total += 1

        # Collect clusters from [theme_day - 6w, theme_day - 2w]
        prior_start = theme_day - timedelta(days=42)
        prior_end = theme_day - timedelta(days=14)
        earlier = [
            (d, cs) for d, cs in clusters_by_day.items()
            if prior_start <= d <= prior_end
        ]
        found, _ = _theme_was_flagged_early(tickers, earlier)
        if found:
            recall_found += 1

    recall = recall_found / recall_total if recall_total else 0.0

    print(f"\n{'='*55}")
    print(f"  Correlation Clustering Backtest Results")
    print(f"  Period: {from_date} → {to_date}")
    print(f"{'='*55}")
    print(f"  Days processed:  {len(trading_days)}")
    print(f"  Total clusters:  {sum(len(cs) for cs in clusters_by_day.values())}")
    print(f"  Avg per day:     {sum(len(cs) for cs in clusters_by_day.values()) / len(trading_days):.1f}")
    print(f"")
    print(f"  PRECISION:  {precision:.1%}  ({precision_hits}/{precision_total} clusters → real theme)")
    print(f"  RECALL:     {recall:.1%}  ({recall_found}/{recall_total} themes pre-flagged)")
    print(f"{'='*55}")

    if precision >= 0.30 and recall >= 0.60:
        print(f"  ✅ Signal is real — ship it to production")
    elif precision >= 0.30:
        print(f"  ⚠️  Precision ok but low recall — clusters may find orthogonal patterns")
    else:
        print(f"  ❌ Precision < 30% — raise threshold to 0.90 or extend window to 25 days")


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest correlation clustering signal quality")
    parser.add_argument("--from", dest="from_date", required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--to", dest="to_date", required=True, help="End date YYYY-MM-DD")
    args = parser.parse_args()

    from_date = date.fromisoformat(args.from_date)
    to_date = date.fromisoformat(args.to_date)

    asyncio.run(run_backtest(from_date, to_date))


if __name__ == "__main__":
    main()
