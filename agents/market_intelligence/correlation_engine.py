"""
Correlation clustering engine for theme discovery pre-pass.

Computes beta-adjusted (SPY-residual) Pearson correlations across the liquid
universe over a 20-day window, finds connected components with pairwise
correlation >= 0.85, and returns tight clusters (mean_corr >= 0.80) that are
not already covered by active themes.

These clusters are passed to the theme engine's discovery prompt as early
statistical signals — stocks moving together before any narrative crystallizes.

Two artifact classes are removed at this source before any correlation is
computed (#486, 2026-09-09; rationale at the constants below): multiple share
classes of one issuer collapse to one representative, and cash-like series
(takeover targets: one jump, then flat) are dropped. Parameters and the
measurements behind them: docs/architecture/theme_engine.md
§"Correlation cluster engine".
"""
from __future__ import annotations

import asyncio
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

# ── Two artifact classes removed at the SOURCE (#486, 2026-09-09) ──────────────
# Both were sitting in the 12 clusters handed to discovery on 2026-09-08, the first
# night the shown/declined recorder ran. Neither is a group; both taught the model
# the cluster list is untrustworthy, and one of them BECAME a live theme once.
#
# (1) SHARE CLASSES OF ONE ISSUER. GOOG/GOOGL/GOOGM/GOOGN (all typed CS, so the
#     security-type filter passes them) formed a 4-member cluster at corr 0.98-0.99
#     on 25 consecutive stored days (08-03 → 09-04) and were named
#     'Alphabet (Google) Platform Re-Rating' as a live theme 08-03 → 08-12.
#     Statistics alone cannot separate this class: on real closes the family's
#     raw-return correlation dips to 0.96 in some 20-day windows while DISTINCT
#     issuers reach 0.99 (NSA/PSA, two self-storage REITs, 14 windows; RIG/VAL,
#     two drillers, 24 windows) — a pure threshold would collapse real groups.
#     So the rule is BOTH a ticker-root match (GOOGL = GOOG + one class letter;
#     BELFA/BELFB share a 4-char root; BRK.A/BRK.B share the pre-dot root) AND a
#     raw-return identity check at _SHARE_CLASS_MIN_RAW_CORR. Root-only matches
#     (ALM/ALMS, PAM/PAMT — different companies, corr ≈ 0.3) never collapse;
#     tight distinct pairs with different roots never collapse. One
#     representative per issuer (shortest ticker, then alphabetical) survives
#     into clustering; the siblings are dropped from the matrix entirely.
# (2) CASH-LIKE SERIES (pending-takeover targets). BWMN/HZO/VREX each jumped
#     +46-56% on 2026-08-10 and then traded flat to the deal price (ex-spike
#     daily std 0.19-0.26%). One shared spike day dominates a 20-day Pearson
#     window, so five unrelated names clustered at corr 0.92 on 09-08. A stock
#     whose returns, with its single largest day removed, move less than
#     _MIN_EX_SPIKE_DAILY_STD a day is trading like cash and is not a theme
#     candidate. Measured: the universe's 0.5th percentile of that statistic was
#     0.20-0.43% across three windows; real cluster members sit at 1.3-4.2%.
# Both are theme-infrastructure filters: they change what reaches the discovery
# prompt, never a trading criterion, and nothing under broker/ reads them.
_SHARE_CLASS_MIN_RAW_CORR = 0.90   # GOOG family min over 24 windows = 0.961; margin below it
_MIN_EX_SPIKE_DAILY_STD = 0.003    # 0.3%/day with the largest |return| day removed


def _issuer_root(ticker: str) -> str:
    """The part of a ticker that names the ISSUER for root-matching purposes:
    'BRK.A' → 'BRK'; anything else is returned as-is (the class-letter rules
    live in _issuer_sibling_pairs, which needs the whole ticker set)."""
    return ticker.split(".")[0] if "." in ticker else ticker


def _issuer_sibling_pairs(tickers: list[str]) -> list[tuple[int, int]]:
    """Candidate share-class pairs by ticker shape (pure). A pair qualifies when
    (a) both share the same pre-dot root (BRK.A / BRK.B), or
    (b) one is the other plus exactly one trailing letter (GOOG→GOOGL, UA→UAA,
        NWS→NWSA), or
    (c) both are ≥5 characters and share their first four (BELFA / BELFB,
        LBTYA / LBTYK, GOOGM / GOOGN).
    This is only the CANDIDATE test — a candidate collapses only if its returns
    are near-identical (see _collapse_share_classes). Never called on SPY."""
    idx = {t: i for i, t in enumerate(tickers)}
    pairs: set[tuple[int, int]] = set()
    by_root: dict[str, list[int]] = {}
    by_first4: dict[str, list[int]] = {}
    for t, i in idx.items():
        base = _issuer_root(t)
        by_root.setdefault(base, []).append(i)
        if len(base) >= 5:
            by_first4.setdefault(base[:4], []).append(i)
        # (b): the ticker minus its last letter is itself a listed ticker
        if len(base) >= 3 and base[:-1] in idx and base[:-1] != t:
            j = idx[base[:-1]]
            pairs.add((min(i, j), max(i, j)))
    for group in list(by_root.values()) + list(by_first4.values()):
        for a in range(len(group)):
            for b in range(a + 1, len(group)):
                i, j = group[a], group[b]
                pairs.add((min(i, j), max(i, j)))
    return sorted(pairs)


def _collapse_share_classes(
    r_matrix: np.ndarray, tickers: list[str],
) -> tuple[np.ndarray, list[str], dict[str, list[str]]]:
    """Collapse multiple share classes of one issuer to ONE representative row
    before any correlation is computed (pure). A candidate pair (ticker shape,
    _issuer_sibling_pairs) is confirmed as the same instrument only when its
    RAW daily returns correlate at ≥ _SHARE_CLASS_MIN_RAW_CORR over the window
    — raw, not beta-residual, because residualising amplifies the tiny
    class-specific noise (the GOOG family's residual corr fell to 0.93 in some
    windows while its raw corr never fell below 0.96). Union-find over confirmed
    pairs; the survivor is the shortest ticker, then alphabetical.

    Returns (reduced r_matrix, reduced tickers, {survivor: [dropped siblings]}).
    """
    n = len(tickers)
    if n < 2:
        return r_matrix, list(tickers), {}
    cand = _issuer_sibling_pairs(tickers)
    if not cand:
        return r_matrix, list(tickers), {}

    parent = list(range(n))

    def _find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, j in cand:
        a, b = r_matrix[i], r_matrix[j]
        if np.std(a) < 1e-12 or np.std(b) < 1e-12:
            continue
        corr = float(np.corrcoef(a, b)[0, 1])
        if np.isfinite(corr) and corr >= _SHARE_CLASS_MIN_RAW_CORR:
            ra, rb = _find(i), _find(j)
            if ra != rb:
                parent[rb] = ra

    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(_find(i), []).append(i)

    keep: list[int] = []
    collapsed: dict[str, list[str]] = {}
    for members in groups.values():
        if len(members) == 1:
            keep.append(members[0])
            continue
        survivor = min(members, key=lambda k: (len(tickers[k]), tickers[k]))
        keep.append(survivor)
        collapsed[tickers[survivor]] = sorted(
            tickers[k] for k in members if k != survivor)
    keep.sort()
    return r_matrix[keep], [tickers[k] for k in keep], collapsed


def _drop_cash_like_series(
    r_matrix: np.ndarray, tickers: list[str],
) -> tuple[np.ndarray, list[str], list[str]]:
    """Drop rows whose daily-return std, with the single largest |return| day
    removed, is below _MIN_EX_SPIKE_DAILY_STD (pure). That shape — one jump,
    then flat — is a takeover target trading at its deal price; its beta
    residual is ∝ the market's return and correlates spuriously with every
    other such name (five of them clustered at 0.92 on 2026-09-08).

    Returns (reduced r_matrix, reduced tickers, dropped tickers)."""
    if r_matrix.size == 0:
        return r_matrix, list(tickers), []
    keep_mask = np.ones(len(tickers), dtype=bool)
    for i in range(len(tickers)):
        r = r_matrix[i]
        if r.shape[0] < 3:
            continue
        r_ex = np.delete(r, int(np.argmax(np.abs(r))))
        if float(np.std(r_ex, ddof=1)) < _MIN_EX_SPIKE_DAILY_STD:
            keep_mask[i] = False
    dropped = [t for t, k in zip(tickers, keep_mask) if not k]
    if not dropped:
        return r_matrix, list(tickers), []
    return (r_matrix[keep_mask],
            [t for t, k in zip(tickers, keep_mask) if k],
            dropped)


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
    """Attach avg_rs AND per-member RS (`member_rs`, in-memory only — the
    persisted table keeps its shape). The discovery prompt renders each
    cluster member with its own RS from this map (#486); a cluster read back
    from the DB has no `member_rs` and the renderer falls back to the pool
    lookup, so nothing downstream requires it."""
    for c in clusters:
        scores = [rs_by_ticker[t] for t in c["tickers"] if t in rs_by_ticker]
        c["avg_rs"] = round(float(np.mean(scores)), 1) if scores else 0.0
        c["member_rs"] = {
            t: round(float(rs_by_ticker[t]), 1)
            for t in c["tickers"] if t in rs_by_ticker
        }
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


def _compute_tight_clusters_sync(
    closes: dict[str, list[float]], tickers: list[str]
) -> list[dict]:
    """Pure-CPU pipeline: returns → residual corrs → BFS → chaining filter. Runs in worker thread."""
    close_matrix = np.array([closes[t] for t in tickers], dtype=np.float64)
    spy_closes = np.array(closes["SPY"], dtype=np.float64)
    r_matrix = close_matrix[:, 1:] / close_matrix[:, :-1] - 1.0
    r_spy = spy_closes[1:] / spy_closes[:-1] - 1.0

    # #486 source-level artifact removal — BEFORE beta adjustment so the checks
    # run on raw returns (see the constants' header for why raw, and why both).
    r_matrix, tickers, collapsed = _collapse_share_classes(r_matrix, list(tickers))
    if collapsed:
        logger.info(
            "Correlation clustering: collapsed %d share-class group(s) to one "
            "representative each: %s",
            len(collapsed),
            "; ".join(f"{k}←{'/'.join(v)}" for k, v in sorted(collapsed.items())),
        )
    r_matrix, tickers, cash_like = _drop_cash_like_series(r_matrix, tickers)
    if cash_like:
        logger.info(
            "Correlation clustering: dropped %d cash-like series (ex-spike daily "
            "std < %.2f%%): %s",
            len(cash_like), _MIN_EX_SPIKE_DAILY_STD * 100, cash_like[:20],
        )

    corr_matrix, filtered_tickers = _compute_residual_correlations(r_matrix, r_spy, tickers)
    if corr_matrix.size == 0:
        return []

    raw = _extract_clusters(corr_matrix, filtered_tickers)
    logger.info(f"Correlation clustering: {len(raw)} raw clusters before chaining filter")
    return [c for c in raw if c["mean_corr"] >= _MEAN_CORR_MIN]


async def run_correlation_clustering(today: date) -> list[dict]:
    """
    Main entry point. Returns filtered clusters ready for theme engine injection
    and DB persistence.
    """
    from agents.market_intelligence.db import (
        get_closes_for_correlation,
        upsert_correlation_clusters,
        get_active_themes,
        get_rs_for_tickers,
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

    # Heavy numpy work — N×N corrcoef on ~2800 tickers blocks the event loop
    # for seconds. Push it onto a worker thread so Telegram commands, EP scans,
    # and paper-trade polls keep flowing.
    tight = await asyncio.to_thread(
        _compute_tight_clusters_sync, closes, tickers
    )
    logger.info(f"Correlation clustering: {len(tight)} tight clusters after chaining filter")

    # Theme dedup
    active_themes = await get_active_themes()
    clean = _dedup_against_themes(tight, active_themes)
    logger.info(f"Correlation clustering: {len(clean)} clusters after theme dedup")

    # avg_rs enrichment — targeted lookup on cluster members, not a truncated
    # leaders list. Defensive clusters (utilities, mortgage REITs, insurance)
    # fall outside the top 500 by RS but still have real scores in
    # mi_stock_scores; using get_rs_for_tickers avoids silently storing
    # avg_rs=0 for them and polluting the theme-discovery prompt.
    today_str = today.strftime("%Y-%m-%d")
    cluster_tickers = sorted({tk for c in clean for tk in c["tickers"]})
    rs_rows = await get_rs_for_tickers(today_str, cluster_tickers)
    rs_by_ticker = {tk: (r.get("rs_composite") or 0.0) for tk, r in rs_rows.items()}
    missing = [tk for tk in cluster_tickers if tk not in rs_by_ticker]
    if missing:
        logger.warning(
            "Correlation clustering: %d cluster tickers have no RS score for %s: %s",
            len(missing), today_str, missing[:10],
        )
    clean = _enrich_avg_rs(clean, rs_by_ticker)

    # Persist
    await upsert_correlation_clusters(today, clean)
    logger.info(f"Correlation clustering: persisted {len(clean)} clusters for {today}")

    return clean
