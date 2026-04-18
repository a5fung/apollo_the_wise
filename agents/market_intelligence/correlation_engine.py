"""
Correlation clustering engine for theme discovery pre-pass.

Computes beta-adjusted (SPY-residual) Pearson correlations across the liquid
universe over a 20-day window, finds connected components with pairwise
correlation >= 0.85, and returns tight clusters (mean_corr >= 0.80) that are
not already covered by active themes.

These clusters are passed to the theme engine's discovery prompt as early
statistical signals — stocks moving together before any narrative crystallizes.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import date, timedelta
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

_LOOKBACK_DAYS = 35       # calendar days to query (gets ~21+ trading days even in holiday months)
_MIN_TRADING_DAYS = 21    # need 21 closes → 20 daily returns
_CORR_THRESHOLD = 0.85    # edge threshold for BFS adjacency
_MIN_CLUSTER_SIZE = 4     # minimum stocks per cluster
_MEAN_CORR_MIN = 0.80     # secondary filter — drop chaining artifacts


def _compute_residual_correlations(
    r_matrix: np.ndarray,
    r_spy: np.ndarray,
    tickers: list[str],
) -> tuple[np.ndarray, list[str]]:
    """
    Beta-adjust each stock's returns against SPY, then compute Pearson
    correlations on the residuals.

    Returns (corr_matrix, filtered_tickers) — zero-variance stocks are
    stripped before computation to prevent NaN poisoning.

    ddof=1 is used consistently for both np.var and np.cov to avoid the
    population/sample mismatch that produces invalid betas.
    """
    # Strip zero-variance stocks (halted, flat, buyout targets) before beta calc.
    # np.corrcoef divides by stddev — variance=0 → NaN rows that corrupt mean_corr.
    variances = np.var(r_matrix, axis=1, ddof=1)
    valid_mask = variances > 1e-8
    r_matrix = r_matrix[valid_mask]
    tickers = [t for t, v in zip(tickers, valid_mask) if v]

    if r_matrix.shape[0] < _MIN_CLUSTER_SIZE:
        return np.empty((0, 0)), []

    # Compute covariance of every stock with SPY simultaneously (vectorized).
    # np.cov(r_matrix, r_spy) → shape (N+1, N+1); slice [:-1, -1] for stock-SPY covs.
    var_spy = np.var(r_spy, ddof=1)
    if var_spy < 1e-10:
        logger.warning("SPY variance near zero — skipping beta adjustment")
        corr_matrix = np.corrcoef(r_matrix)
        return corr_matrix, tickers

    cov_matrix = np.cov(r_matrix, r_spy)      # ddof=1 by default
    cov_with_spy = cov_matrix[:-1, -1]        # shape (N_tickers,)
    betas = cov_with_spy / var_spy            # shape (N_tickers,)

    residuals = r_matrix - (betas[:, np.newaxis] * r_spy)
    corr_matrix = np.corrcoef(residuals)      # shape (N_tickers, N_tickers)
    return corr_matrix, tickers


def _extract_clusters(
    corr_matrix: np.ndarray,
    tickers: list[str],
) -> list[dict]:
    """
    BFS connected components on the correlation adjacency graph.
    Returns raw clusters (before chaining filter and dedup).
    """
    N = len(tickers)
    adj = corr_matrix >= _CORR_THRESHOLD
    np.fill_diagonal(adj, False)

    visited: set[int] = set()
    clusters: list[dict] = []

    for i in range(N):
        if i in visited:
            continue
        queue = [i]
        component: set[int] = set()
        while queue:
            node = queue.pop(0)
            if node in visited:
                continue
            visited.add(node)
            component.add(node)
            neighbors = np.where(adj[node])[0]
            queue.extend(n for n in neighbors if n not in visited)

        if len(component) < _MIN_CLUSTER_SIZE:
            continue

        cluster_tickers = sorted(tickers[idx] for idx in component)
        idx_list = list(component)
        sub = corr_matrix[np.ix_(idx_list, idx_list)]
        upper = np.triu_indices_from(sub, k=1)
        mean_corr = float(np.mean(sub[upper]))
        cluster_hash = hashlib.sha256("".join(cluster_tickers).encode()).hexdigest()[:8]

        clusters.append({
            "cluster_hash": cluster_hash,
            "tickers": cluster_tickers,
            "member_count": len(cluster_tickers),
            "mean_corr": round(mean_corr, 3),
            "avg_rs": 0.0,
        })

    return clusters


def _enrich_avg_rs(
    clusters: list[dict], rs_by_ticker: dict[str, float]
) -> list[dict]:
    for c in clusters:
        scores = [rs_by_ticker[t] for t in c["tickers"] if t in rs_by_ticker]
        c["avg_rs"] = round(float(np.mean(scores)), 1) if scores else 0.0
    return clusters


def _dedup_against_themes(
    clusters: list[dict], active_themes: list[dict]
) -> list[dict]:
    """
    Drop clusters where >= 50% of members already share the same single
    active theme. Cross-theme overlap is allowed through.
    """
    # Build ticker → theme name map
    ticker_theme: dict[str, str] = {}
    for t in active_themes:
        if t.get("stage") == "Fading":
            continue
        for tk in (t.get("tickers") or []):
            ticker_theme[tk] = t["name"]

    result = []
    for c in clusters:
        tickers = c["tickers"]
        # Count how many members share the same theme
        from collections import Counter
        theme_counts = Counter(ticker_theme[t] for t in tickers if t in ticker_theme)
        if not theme_counts:
            result.append(c)
            continue
        most_common_count = theme_counts.most_common(1)[0][1]
        coverage = most_common_count / len(tickers)
        if coverage >= 0.5:
            logger.debug(
                f"Cluster {c['cluster_hash']} skipped — "
                f"{most_common_count}/{len(tickers)} members already in same theme"
            )
        else:
            result.append(c)

    return result


async def run_correlation_clustering(today: date) -> list[dict]:
    """
    Main entry point. Returns filtered clusters ready for theme engine injection
    and DB persistence.
    """
    from agents.market_intelligence.db import (
        get_closes_for_correlation,
        upsert_correlation_clusters,
        get_active_themes,
        get_rs_leaders,
    )

    from_date = today - timedelta(days=_LOOKBACK_DAYS)
    logger.info(f"Correlation clustering: loading closes {from_date} → {today}")

    closes = await get_closes_for_correlation(from_date, today)
    if not closes:
        logger.warning("Correlation clustering: no close data returned — skipping")
        return []

    if "SPY" not in closes:
        logger.warning("Correlation clustering: SPY not in closes — cannot beta-adjust, skipping")
        return []

    tickers = [t for t in closes if t != "SPY"]
    n_days = len(next(iter(closes.values())))

    if n_days < _MIN_TRADING_DAYS:
        logger.warning(f"Correlation clustering: only {n_days} trading days — need {_MIN_TRADING_DAYS}")
        return []

    logger.info(f"Correlation clustering: {len(tickers)} tickers, {n_days} days")

    # Build return matrices (slice off first close to get n_days-1 returns)
    all_tickers = tickers
    close_matrix = np.array([closes[t] for t in all_tickers], dtype=np.float64)
    spy_closes = np.array(closes["SPY"], dtype=np.float64)

    # Daily returns: r_t = close_t / close_{t-1} - 1
    r_matrix = close_matrix[:, 1:] / close_matrix[:, :-1] - 1.0
    r_spy = spy_closes[1:] / spy_closes[:-1] - 1.0

    corr_matrix, filtered_tickers = _compute_residual_correlations(r_matrix, r_spy, all_tickers)

    if corr_matrix.size == 0:
        logger.warning("Correlation clustering: empty correlation matrix after filtering")
        return []

    raw_clusters = _extract_clusters(corr_matrix, filtered_tickers)
    logger.info(f"Correlation clustering: {len(raw_clusters)} raw clusters before filtering")

    # Chaining filter: drop clusters where mean pairwise corr < 0.80
    tight = [c for c in raw_clusters if c["mean_corr"] >= _MEAN_CORR_MIN]
    logger.info(f"Correlation clustering: {len(tight)} tight clusters after chaining filter")

    # Theme dedup
    active_themes = await get_active_themes()
    clean = _dedup_against_themes(tight, active_themes)
    logger.info(f"Correlation clustering: {len(clean)} clusters after theme dedup")

    # avg_rs enrichment from today's RS scores
    today_str = today.strftime("%Y-%m-%d")
    leaders = await get_rs_leaders(today_str, limit=500)
    rs_by_ticker = {s["ticker"]: s.get("rs_composite", 0.0) for s in leaders}
    clean = _enrich_avg_rs(clean, rs_by_ticker)

    # Persist
    await upsert_correlation_clusters(today, clean)
    logger.info(f"Correlation clustering: persisted {len(clean)} clusters for {today}")

    return clean
