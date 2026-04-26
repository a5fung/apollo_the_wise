"""Crypto RS database layer — schema + CRUD.

Tables prefixed `crypto_` to avoid collision with `mi_*` equity tables.
Reuses the shared asyncpg pool from agents.market_intelligence.db.get_pool().
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from agents.market_intelligence.db import get_pool
from agents.market_intelligence.crypto.watchlist_seed import WATCHLIST_SEED

logger = logging.getLogger(__name__)


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS crypto_universe (
    coin_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    name TEXT,
    mcap_rank INT,
    mcap_usd NUMERIC,
    last_seen DATE
);
CREATE INDEX IF NOT EXISTS idx_crypto_universe_rank ON crypto_universe(mcap_rank);

CREATE TABLE IF NOT EXISTS crypto_token_address (
    coin_id TEXT NOT NULL,
    chain TEXT NOT NULL,
    contract_address TEXT NOT NULL,
    PRIMARY KEY (chain, contract_address)
);
CREATE INDEX IF NOT EXISTS idx_crypto_token_address_coin ON crypto_token_address(coin_id);

CREATE TABLE IF NOT EXISTS crypto_daily_closes (
    coin_id TEXT NOT NULL,
    date DATE NOT NULL,
    close_usd NUMERIC,
    close_btc NUMERIC,
    volume_usd NUMERIC,
    mcap_usd NUMERIC,
    source TEXT,
    PRIMARY KEY (coin_id, date)
);
CREATE INDEX IF NOT EXISTS idx_crypto_daily_closes_date ON crypto_daily_closes(date);

CREATE TABLE IF NOT EXISTS crypto_rs_scores (
    coin_id TEXT NOT NULL,
    score_date DATE NOT NULL,
    rs_1m REAL,
    rs_3m REAL,
    rs_6m REAL,
    rs_composite REAL,
    mcap_bucket TEXT,
    rs_in_bucket REAL,
    rs_overall REAL,
    PRIMARY KEY (coin_id, score_date)
);
CREATE INDEX IF NOT EXISTS idx_crypto_rs_scores_date ON crypto_rs_scores(score_date);

CREATE TABLE IF NOT EXISTS crypto_categories (
    coin_id TEXT NOT NULL,
    category_slug TEXT NOT NULL,
    PRIMARY KEY (coin_id, category_slug)
);
CREATE INDEX IF NOT EXISTS idx_crypto_categories_slug ON crypto_categories(category_slug);

CREATE TABLE IF NOT EXISTS crypto_category_strength (
    category_slug TEXT NOT NULL,
    score_date DATE NOT NULL,
    member_count INT,
    median_rs REAL,
    top3_coins TEXT,
    PRIMARY KEY (category_slug, score_date)
);

CREATE TABLE IF NOT EXISTS crypto_btc_dominance (
    date DATE PRIMARY KEY,
    dominance_pct NUMERIC,
    btc_price NUMERIC,
    total_mcap_usd NUMERIC,
    slope_30d NUMERIC
);

CREATE TABLE IF NOT EXISTS crypto_total3 (
    date DATE PRIMARY KEY,
    total3_mcap_usd NUMERIC,
    slope_30d NUMERIC,
    sma_90d NUMERIC
);

CREATE TABLE IF NOT EXISTS crypto_stablecoin_flows (
    date DATE PRIMARY KEY,
    total_stable_mcap NUMERIC,
    usdt_mcap NUMERIC,
    usdc_mcap NUMERIC,
    slope_30d NUMERIC
);

CREATE TABLE IF NOT EXISTS crypto_dominance_alerts (
    id SERIAL PRIMARY KEY,
    triggered_at TIMESTAMPTZ DEFAULT NOW(),
    btc_d_pct NUMERIC,
    total3_breakout BOOLEAN,
    stable_slope_30d NUMERIC,
    alert_type TEXT,
    cooldown_until TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_crypto_dominance_alerts_triggered ON crypto_dominance_alerts(triggered_at DESC);

CREATE TABLE IF NOT EXISTS crypto_watchlist (
    coin_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    chain TEXT,
    contract_address TEXT,
    added_at TIMESTAMPTZ DEFAULT NOW(),
    source TEXT,
    notes TEXT
);
"""


async def initialize_crypto_schema() -> None:
    """Create crypto_* tables and seed the watchlist on first run.

    Called from agents.market_intelligence.db.initialize_schema() at agent startup.
    Idempotent — safe to invoke on every boot.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(SCHEMA_SQL)
        await _seed_watchlist_if_empty(conn)


async def _seed_watchlist_if_empty(conn) -> None:
    existing = await conn.fetchval("SELECT COUNT(*) FROM crypto_watchlist")
    if existing and existing > 0:
        return

    for entry in WATCHLIST_SEED:
        # coin_id is the unverified hint at seed time; resolver will update on first
        # ingest if the hint is wrong or the entry is None (dex-only fallback).
        coin_id = entry.coin_id_hint or f"_unresolved_{entry.symbol.lower()}"
        await conn.execute(
            """
            INSERT INTO crypto_watchlist (coin_id, symbol, source, notes)
            VALUES ($1, $2, 'seed', $3)
            ON CONFLICT (coin_id) DO NOTHING
            """,
            coin_id, entry.symbol, entry.notes,
        )
    logger.info("crypto_watchlist seeded with %d entries", len(WATCHLIST_SEED))


async def upsert_daily_close(
    coin_id: str,
    bar_date: date,
    close_usd: Optional[float],
    close_btc: Optional[float],
    volume_usd: Optional[float],
    mcap_usd: Optional[float],
    source: str,
) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO crypto_daily_closes
                (coin_id, date, close_usd, close_btc, volume_usd, mcap_usd, source)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (coin_id, date) DO UPDATE SET
                close_usd = COALESCE(EXCLUDED.close_usd, crypto_daily_closes.close_usd),
                close_btc = COALESCE(EXCLUDED.close_btc, crypto_daily_closes.close_btc),
                volume_usd = COALESCE(EXCLUDED.volume_usd, crypto_daily_closes.volume_usd),
                mcap_usd = COALESCE(EXCLUDED.mcap_usd, crypto_daily_closes.mcap_usd),
                source = EXCLUDED.source
            """,
            coin_id, bar_date, close_usd, close_btc, volume_usd, mcap_usd, source,
        )


async def get_recent_closes(coin_id: str, limit_days: int = 200) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT date, close_usd, close_btc, volume_usd, mcap_usd
            FROM crypto_daily_closes
            WHERE coin_id = $1
            ORDER BY date DESC
            LIMIT $2
            """,
            coin_id, limit_days,
        )
    return [dict(r) for r in rows]


async def get_watchlist() -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT coin_id, symbol, chain, contract_address, notes FROM crypto_watchlist ORDER BY symbol"
        )
    return [dict(r) for r in rows]
