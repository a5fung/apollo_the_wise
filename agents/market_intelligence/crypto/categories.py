"""CoinGecko category taxonomy sync + per-category RS aggregation.

CG ships a pre-tagged ecosystem taxonomy ("AI & Big Data", "Privacy Coins",
"DePIN", "Meme", "Layer 1", "Solana Ecosystem", etc.) — replaces the LLM
theme-discovery layer used on the equity side.

Refresh cadence: weekly. Categories are very low-churn — daily refresh would
burn the 30/min CG budget for no benefit.
"""
from __future__ import annotations

import logging
import statistics
from datetime import date
from typing import Optional

from agents.market_intelligence.db import get_pool
from agents.market_intelligence.crypto import coingecko_client as cg

logger = logging.getLogger(__name__)


async def refresh_category_membership(coin_ids: list[str]) -> int:
    """Pull category membership for the given coins; refresh `crypto_categories`.

    Hits CG `/coins/{id}` per coin (heavy — only call from the weekly job).
    Returns total (coin, category) pairs written.
    """
    if not coin_ids:
        return 0

    pool = await get_pool()
    pairs_written = 0
    async with pool.acquire() as conn:
        for coin_id in coin_ids:
            try:
                detail = await cg.get_coin_detail(coin_id)
            except Exception:
                logger.exception("CG /coins/%s failed; skipping category sync", coin_id)
                continue
            cats = detail.get("categories") or []
            slugs = [
                _slugify(c) for c in cats
                if isinstance(c, str) and c.strip()
            ]
            if not slugs:
                continue
            # Replace this coin's category set atomically so removed tags get pruned.
            async with conn.transaction():
                await conn.execute(
                    "DELETE FROM crypto_categories WHERE coin_id = $1", coin_id
                )
                await conn.executemany(
                    "INSERT INTO crypto_categories (coin_id, category_slug) "
                    "VALUES ($1, $2) ON CONFLICT DO NOTHING",
                    [(coin_id, slug) for slug in slugs],
                )
            pairs_written += len(slugs)
    logger.info("Category membership refresh: %d (coin, category) pairs", pairs_written)
    return pairs_written


async def compute_category_strength(score_date: date) -> int:
    """For each category with ≥3 members scored today, write median RS + top-3
    coins to `crypto_category_strength`. Returns number of category rows written.
    """
    pool = await get_pool()
    written = 0
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT cc.category_slug,
                   cu.symbol,
                   crs.rs_overall
            FROM crypto_categories cc
            JOIN crypto_rs_scores crs
              ON crs.coin_id = cc.coin_id AND crs.score_date = $1
            LEFT JOIN crypto_universe cu ON cu.coin_id = cc.coin_id
            WHERE crs.rs_overall IS NOT NULL
            """,
            score_date,
        )

        by_cat: dict[str, list[tuple[str, float]]] = {}
        for r in rows:
            slug = r["category_slug"]
            by_cat.setdefault(slug, []).append((r["symbol"] or "?", float(r["rs_overall"])))

        for slug, members in by_cat.items():
            if len(members) < 3:
                continue
            members.sort(key=lambda x: x[1], reverse=True)
            top3 = ",".join(sym for sym, _ in members[:3])
            median_rs = round(statistics.median(rs for _, rs in members), 1)
            await conn.execute(
                """
                INSERT INTO crypto_category_strength
                    (category_slug, score_date, member_count, median_rs, top3_coins)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (category_slug, score_date) DO UPDATE SET
                    member_count = EXCLUDED.member_count,
                    median_rs = EXCLUDED.median_rs,
                    top3_coins = EXCLUDED.top3_coins
                """,
                slug, score_date, len(members), median_rs, top3,
            )
            written += 1
    logger.info("Category strength: %d categories scored", written)
    return written


async def get_top_categories(score_date: date, limit: int = 5) -> list[dict]:
    """Top categories by median RS (≥ 5 members), most-recent score_date."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT category_slug, member_count, median_rs, top3_coins
            FROM crypto_category_strength
            WHERE score_date = $1 AND member_count >= 5
            ORDER BY median_rs DESC
            LIMIT $2
            """,
            score_date, limit,
        )
    return [dict(r) for r in rows]


def _slugify(name: str) -> str:
    """Stable slug for category names — lowercase, dash-separated."""
    return (
        name.lower()
        .replace("&", "and")
        .replace("/", "-")
        .replace(" ", "-")
        .strip("-")
    )
