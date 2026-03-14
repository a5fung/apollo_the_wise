"""
Database layer for Market Intelligence Agent.
Uses the same Postgres instance as Apollo, separate tables prefixed with mi_.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import asyncpg

from shared.secrets import get_secrets

logger = logging.getLogger(__name__)

_pool: Optional[asyncpg.Pool] = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        secrets = get_secrets()
        dsn = secrets.postgres_dsn_sync
        # Parse DSN: postgresql://user:pass@host:port/db
        after_scheme = dsn.split("://")[1]
        user_pass, host_db = after_scheme.split("@")
        user = user_pass.split(":")[0]
        password = user_pass.split(":")[1] if ":" in user_pass else ""
        host_port, db = host_db.split("/")
        host = host_port.split(":")[0]
        port = int(host_port.split(":")[1]) if ":" in host_port else 5432

        _pool = await asyncpg.create_pool(
            host=host, port=port, database=db, user=user, password=password,
            min_size=1, max_size=5,
        )
    return _pool


async def initialize_schema() -> None:
    """Create MI tables if they don't exist. Called at agent startup."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mi_stock_scores (
                ticker TEXT NOT NULL,
                score_date DATE NOT NULL,
                rs_1m FLOAT,
                rs_3m FLOAT,
                rs_6m FLOAT,
                rs_composite FLOAT,
                rs_rank INT,
                sector TEXT,
                adv_20 FLOAT,
                market_cap FLOAT,
                PRIMARY KEY (ticker, score_date)
            );

            CREATE TABLE IF NOT EXISTS mi_ep_alerts (
                id SERIAL PRIMARY KEY,
                ticker TEXT NOT NULL,
                alert_date DATE NOT NULL,
                gap_pct FLOAT NOT NULL,
                rel_volume FLOAT,
                ep_score FLOAT NOT NULL,
                score_tier TEXT NOT NULL,
                catalyst TEXT,
                catalyst_quality TEXT,
                claude_analysis TEXT,
                gemini_validation TEXT,
                confidence_multiplier FLOAT DEFAULT 1.0,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS mi_market_regime (
                regime_date DATE PRIMARY KEY,
                regime TEXT NOT NULL,
                spy_vs_50ma FLOAT,
                spy_vs_200ma FLOAT,
                qqq_vs_50ma FLOAT,
                vix FLOAT,
                breadth_pct_above_40ma FLOAT,
                bo_bd_ratio_5d FLOAT,
                description TEXT,
                ep_threshold INT DEFAULT 70,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            ALTER TABLE mi_market_regime ADD COLUMN IF NOT EXISTS qqq_vs_50ma FLOAT;

            CREATE TABLE IF NOT EXISTS mi_themes (
                id SERIAL PRIMARY KEY,
                theme_date DATE NOT NULL,
                name TEXT NOT NULL,
                stage TEXT NOT NULL,
                score FLOAT,
                description TEXT,
                tickers TEXT[],
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
        """)
    logger.info("Market Intelligence DB schema initialized")


async def upsert_stock_score(record: dict[str, Any]) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO mi_stock_scores
                (ticker, score_date, rs_1m, rs_3m, rs_6m, rs_composite, rs_rank, sector, adv_20, market_cap)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
            ON CONFLICT (ticker, score_date) DO UPDATE SET
                rs_1m=EXCLUDED.rs_1m, rs_3m=EXCLUDED.rs_3m, rs_6m=EXCLUDED.rs_6m,
                rs_composite=EXCLUDED.rs_composite, rs_rank=EXCLUDED.rs_rank,
                sector=EXCLUDED.sector, adv_20=EXCLUDED.adv_20, market_cap=EXCLUDED.market_cap
        """,
            record["ticker"], record["score_date"], record.get("rs_1m"), record.get("rs_3m"),
            record.get("rs_6m"), record.get("rs_composite"), record.get("rs_rank"),
            record.get("sector"), record.get("adv_20"), record.get("market_cap"),
        )


async def insert_ep_alert(record: dict[str, Any]) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO mi_ep_alerts
                (ticker, alert_date, gap_pct, rel_volume, ep_score, score_tier,
                 catalyst, catalyst_quality, claude_analysis, gemini_validation, confidence_multiplier)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
        """,
            record["ticker"], record["alert_date"], record["gap_pct"],
            record.get("rel_volume"), record["ep_score"], record["score_tier"],
            record.get("catalyst"), record.get("catalyst_quality"),
            record.get("claude_analysis"), record.get("gemini_validation"),
            record.get("confidence_multiplier", 1.0),
        )


async def upsert_regime(record: dict[str, Any]) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO mi_market_regime
                (regime_date, regime, spy_vs_50ma, spy_vs_200ma, qqq_vs_50ma, vix,
                 breadth_pct_above_40ma, bo_bd_ratio_5d, description, ep_threshold)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
            ON CONFLICT (regime_date) DO UPDATE SET
                regime=EXCLUDED.regime, spy_vs_50ma=EXCLUDED.spy_vs_50ma,
                spy_vs_200ma=EXCLUDED.spy_vs_200ma, qqq_vs_50ma=EXCLUDED.qqq_vs_50ma,
                vix=EXCLUDED.vix, breadth_pct_above_40ma=EXCLUDED.breadth_pct_above_40ma,
                bo_bd_ratio_5d=EXCLUDED.bo_bd_ratio_5d,
                description=EXCLUDED.description, ep_threshold=EXCLUDED.ep_threshold
        """,
            record["regime_date"], record["regime"], record.get("spy_vs_50ma"),
            record.get("spy_vs_200ma"), record.get("qqq_vs_50ma"), record.get("vix"),
            record.get("breadth_pct_above_40ma"), record.get("bo_bd_ratio_5d"),
            record.get("description"), record.get("ep_threshold", 70),
        )


async def get_latest_regime() -> Optional[dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM mi_market_regime ORDER BY regime_date DESC LIMIT 1"
        )
        return dict(row) if row else None


def _to_date(d: "str | date") -> "date":
    from datetime import date as date_type
    if isinstance(d, date_type):
        return d
    return date_type.fromisoformat(str(d))


async def get_rs_leaders(d: "str | date", limit: int = 30) -> list[dict[str, Any]]:
    """Top RS stocks for a given date, optionally by sector."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT * FROM mi_stock_scores
            WHERE score_date = $1
            ORDER BY rs_composite DESC NULLS LAST
            LIMIT $2
        """, _to_date(d), limit)
        return [dict(r) for r in rows]


async def get_today_ep_alerts(d: "str | date") -> list[dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM mi_ep_alerts WHERE alert_date = $1 ORDER BY ep_score DESC",
            _to_date(d),
        )
        return [dict(r) for r in rows]


async def get_adv_map(d: "str | date") -> dict[str, float]:
    """Get stored ADV (avg daily volume) for all tickers as of a date."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT ticker, adv_20 FROM mi_stock_scores WHERE score_date = $1",
            _to_date(d),
        )
        return {r["ticker"]: r["adv_20"] for r in rows if r["adv_20"]}
