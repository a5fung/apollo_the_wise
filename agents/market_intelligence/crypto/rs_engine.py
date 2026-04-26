"""Crypto RS engine — composite percentile rank vs Bitcoin.

Mirrors equity RS methodology (40% × 1m + 30% × 3m + 30% × 6m percentile rank)
with one critical change: numerator is the BTC-denominated price ratio
(close_usd / btc_close_usd), NOT raw USD.

A coin up 5% in USD while BTC is up 8% has negative RS-vs-BTC; that's the
entire point. USD-denominated RS would obscure alt-season rotation.

Two ranking surfaces produced per coin:
- rs_overall:   percentile rank across the full universe + watchlist
- rs_in_bucket: percentile rank within the coin's mcap bucket (mega/large/mid/micro)

Bucket-rank surfaces early micro-cap rotation that overall-rank dilutes.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional

from agents.market_intelligence.rs_engine import _percentile_ranks, _pct_return

logger = logging.getLogger(__name__)


# Mcap bucket boundaries (USD)
BUCKET_MEGA = 50_000_000_000      # >$50B
BUCKET_LARGE = 5_000_000_000      # $5B - $50B
BUCKET_MID = 500_000_000          # $500M - $5B
BUCKET_MICRO = 50_000_000         # $50M - $500M
# Below $50M: only watchlist coins, tracked but flagged "below floor".
BUCKET_FLOOR = 15_000_000         # Universe floor; below = watchlist-only.


def assign_mcap_bucket(mcap_usd: Optional[float]) -> str:
    if mcap_usd is None:
        return "unknown"
    if mcap_usd >= BUCKET_MEGA:
        return "mega"
    if mcap_usd >= BUCKET_LARGE:
        return "large"
    if mcap_usd >= BUCKET_MID:
        return "mid"
    if mcap_usd >= BUCKET_MICRO:
        return "micro"
    if mcap_usd >= BUCKET_FLOOR:
        return "below_floor"
    return "tiny"


def _btc_ratio_series(
    coin_closes: list[dict], btc_closes: dict[date, float]
) -> dict[date, float]:
    """Convert a coin's USD close series into BTC-denominated ratio series.

    coin_closes is the upstream `crypto_daily_closes` rows (with `close_usd` and
    `date`); btc_closes is a {date: usd_close} map for BTC over the same window.
    Returns {date: ratio} where ratio = coin_close_usd / btc_close_usd.
    Days where either side is missing are dropped.
    """
    out: dict[date, float] = {}
    for row in coin_closes:
        d = row.get("date")
        usd = row.get("close_usd")
        btc_usd = btc_closes.get(d) if d else None
        if not d or not usd or not btc_usd or btc_usd <= 0:
            continue
        out[d] = float(usd) / float(btc_usd)
    return out


def _ratio_at_or_before(series: dict[date, float], target: date, slack_days: int = 5) -> Optional[float]:
    """Pull the ratio for `target` or fall back up to `slack_days` earlier.

    Crypto trades 24/7 so missing-bar fallback is mostly defensive (data hiccups,
    DEX-only coins with sparse history).
    """
    if target in series:
        return series[target]
    cur = target
    for _ in range(slack_days):
        cur -= timedelta(days=1)
        if cur in series:
            return series[cur]
    return None


def _coin_raw_returns(
    series: dict[date, float], score_date: date
) -> tuple[Optional[float], Optional[float], Optional[float]]:
    """Return (1m, 3m, 6m) raw % returns of the BTC-ratio series.

    Approximates calendar months as 30/90/180 days — crypto's continuous market
    makes this cleaner than equity's "trading days" approximation.
    """
    current = _ratio_at_or_before(series, score_date)
    past_1m = _ratio_at_or_before(series, score_date - timedelta(days=30))
    past_3m = _ratio_at_or_before(series, score_date - timedelta(days=90))
    past_6m = _ratio_at_or_before(series, score_date - timedelta(days=180))

    return (
        _pct_return(current, past_1m) if current is not None else None,
        _pct_return(current, past_3m) if current is not None else None,
        _pct_return(current, past_6m) if current is not None else None,
    )


def compute_rs_scores(
    coins_data: list[dict],
    btc_closes: dict[date, float],
    score_date: date,
) -> list[dict]:
    """Compute crypto RS scores for one universe snapshot.

    Args:
        coins_data: list of dicts each with:
            - coin_id, symbol, mcap_usd
            - daily_closes: list of {date, close_usd, ...} (sufficient depth for 6m)
        btc_closes: {date: usd_close} for BTC, ≥ 180 days deep.
        score_date: the date we're scoring for.

    Returns: list of dicts ready for `crypto_rs_scores` upsert:
        coin_id, score_date, rs_1m, rs_3m, rs_6m, rs_composite,
        mcap_bucket, rs_in_bucket, rs_overall.

    Coins with insufficient history (e.g., DEX-only, < 30 days accumulated)
    appear in the output with None scores — preserves the row for diagnostics
    but excludes them from percentile-rank calculation.
    """
    raw_rows: list[dict] = []
    for coin in coins_data:
        ratio_series = _btc_ratio_series(coin.get("daily_closes") or [], btc_closes)
        ret_1m, ret_3m, ret_6m = _coin_raw_returns(ratio_series, score_date)
        raw_rows.append({
            "coin_id": coin["coin_id"],
            "symbol": coin.get("symbol"),
            "mcap_usd": coin.get("mcap_usd"),
            "mcap_bucket": assign_mcap_bucket(coin.get("mcap_usd")),
            "raw_1m": ret_1m,
            "raw_3m": ret_3m,
            "raw_6m": ret_6m,
        })

    # Overall percentile ranks across the full set (None values stay None).
    rs_1m_all = _percentile_ranks([r["raw_1m"] for r in raw_rows])
    rs_3m_all = _percentile_ranks([r["raw_3m"] for r in raw_rows])
    rs_6m_all = _percentile_ranks([r["raw_6m"] for r in raw_rows])

    # Composite weighted with safe-skip on any missing component.
    def _composite(a, b, c):
        if a is None or b is None or c is None:
            return None
        return round(0.4 * a + 0.3 * b + 0.3 * c, 1)

    rs_composite_all = [
        _composite(rs_1m_all[i], rs_3m_all[i], rs_6m_all[i])
        for i in range(len(raw_rows))
    ]

    # Per-bucket overall rank: rank composite WITHIN each mcap bucket.
    by_bucket: dict[str, list[int]] = {}
    for i, r in enumerate(raw_rows):
        by_bucket.setdefault(r["mcap_bucket"], []).append(i)

    rs_in_bucket: list[Optional[float]] = [None] * len(raw_rows)
    for bucket, indices in by_bucket.items():
        bucket_composites = [rs_composite_all[i] for i in indices]
        bucket_ranks = _percentile_ranks(bucket_composites)
        for slot, original_i in enumerate(indices):
            rs_in_bucket[original_i] = bucket_ranks[slot]

    # rs_overall = percentile rank of composite across whole set.
    rs_overall = _percentile_ranks(rs_composite_all)

    return [
        {
            "coin_id": raw_rows[i]["coin_id"],
            "score_date": score_date,
            "rs_1m": rs_1m_all[i],
            "rs_3m": rs_3m_all[i],
            "rs_6m": rs_6m_all[i],
            "rs_composite": rs_composite_all[i],
            "mcap_bucket": raw_rows[i]["mcap_bucket"],
            "rs_in_bucket": rs_in_bucket[i],
            "rs_overall": rs_overall[i],
        }
        for i in range(len(raw_rows))
    ]
