"""
Database layer for Market Intelligence Agent.
Uses the same Postgres instance as Apollo, separate tables prefixed with mi_.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
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
                sma_10 FLOAT,
                sma_20 FLOAT,
                sma_50 FLOAT,
                close FLOAT,
                raw_1m FLOAT,
                raw_3m FLOAT,
                raw_6m FLOAT,
                PRIMARY KEY (ticker, score_date)
            );
            ALTER TABLE mi_stock_scores ADD COLUMN IF NOT EXISTS sma_10 FLOAT;
            ALTER TABLE mi_stock_scores ADD COLUMN IF NOT EXISTS sma_20 FLOAT;
            ALTER TABLE mi_stock_scores ADD COLUMN IF NOT EXISTS sma_50 FLOAT;
            ALTER TABLE mi_stock_scores ADD COLUMN IF NOT EXISTS close FLOAT;
            ALTER TABLE mi_stock_scores ADD COLUMN IF NOT EXISTS raw_1m FLOAT;
            ALTER TABLE mi_stock_scores ADD COLUMN IF NOT EXISTS raw_3m FLOAT;
            ALTER TABLE mi_stock_scores ADD COLUMN IF NOT EXISTS raw_6m FLOAT;

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
                vol_percentile FLOAT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            ALTER TABLE mi_ep_alerts ADD COLUMN IF NOT EXISTS vol_percentile FLOAT;

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

            CREATE TABLE IF NOT EXISTS mi_tracked_stocks (
                ticker TEXT PRIMARY KEY,
                first_seen DATE NOT NULL,
                last_seen DATE NOT NULL,
                peak_rs_score FLOAT DEFAULT 0,
                consecutive_weak_days INT DEFAULT 0,
                active BOOLEAN DEFAULT TRUE
            );

            CREATE INDEX IF NOT EXISTS idx_stock_scores_score_date ON mi_stock_scores(score_date);
            CREATE INDEX IF NOT EXISTS idx_stock_scores_ticker ON mi_stock_scores(ticker);
            CREATE INDEX IF NOT EXISTS idx_ep_alerts_alert_date ON mi_ep_alerts(alert_date);
            CREATE INDEX IF NOT EXISTS idx_themes_theme_date ON mi_themes(theme_date);
        """)
    logger.info("Market Intelligence DB schema initialized")


async def upsert_stock_score(record: dict[str, Any]) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO mi_stock_scores
                (ticker, score_date, rs_1m, rs_3m, rs_6m, rs_composite, rs_rank,
                 sector, adv_20, market_cap, sma_10, sma_20, sma_50, close,
                 raw_1m, raw_3m, raw_6m)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17)
            ON CONFLICT (ticker, score_date) DO UPDATE SET
                rs_1m=EXCLUDED.rs_1m, rs_3m=EXCLUDED.rs_3m, rs_6m=EXCLUDED.rs_6m,
                rs_composite=EXCLUDED.rs_composite, rs_rank=EXCLUDED.rs_rank,
                sector=EXCLUDED.sector, adv_20=EXCLUDED.adv_20, market_cap=EXCLUDED.market_cap,
                sma_10=EXCLUDED.sma_10, sma_20=EXCLUDED.sma_20, sma_50=EXCLUDED.sma_50,
                close=EXCLUDED.close, raw_1m=EXCLUDED.raw_1m,
                raw_3m=EXCLUDED.raw_3m, raw_6m=EXCLUDED.raw_6m
        """,
            record["ticker"], record["score_date"], record.get("rs_1m"), record.get("rs_3m"),
            record.get("rs_6m"), record.get("rs_composite"), record.get("rs_rank"),
            record.get("sector"), record.get("adv_20"), record.get("market_cap"),
            record.get("sma_10"), record.get("sma_20"), record.get("sma_50"),
            record.get("close"), record.get("raw_1m"), record.get("raw_3m"), record.get("raw_6m"),
        )


async def upsert_stock_scores_batch(records: list[dict[str, Any]]) -> None:
    """Batch upsert for RS stock scores — single round-trip instead of N."""
    if not records:
        return
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.executemany("""
            INSERT INTO mi_stock_scores
                (ticker, score_date, rs_1m, rs_3m, rs_6m, rs_composite, rs_rank,
                 sector, adv_20, market_cap, sma_10, sma_20, sma_50, close,
                 raw_1m, raw_3m, raw_6m)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17)
            ON CONFLICT (ticker, score_date) DO UPDATE SET
                rs_1m=EXCLUDED.rs_1m, rs_3m=EXCLUDED.rs_3m, rs_6m=EXCLUDED.rs_6m,
                rs_composite=EXCLUDED.rs_composite, rs_rank=EXCLUDED.rs_rank,
                sector=EXCLUDED.sector, adv_20=EXCLUDED.adv_20, market_cap=EXCLUDED.market_cap,
                sma_10=EXCLUDED.sma_10, sma_20=EXCLUDED.sma_20, sma_50=EXCLUDED.sma_50,
                close=EXCLUDED.close, raw_1m=EXCLUDED.raw_1m,
                raw_3m=EXCLUDED.raw_3m, raw_6m=EXCLUDED.raw_6m
        """, [
            (r["ticker"], r["score_date"], r.get("rs_1m"), r.get("rs_3m"),
             r.get("rs_6m"), r.get("rs_composite"), r.get("rs_rank"),
             r.get("sector"), r.get("adv_20"), r.get("market_cap"),
             r.get("sma_10"), r.get("sma_20"), r.get("sma_50"),
             r.get("close"), r.get("raw_1m"), r.get("raw_3m"), r.get("raw_6m"))
            for r in records
        ])


async def upsert_tracked_stocks_batch(
    records: list[tuple[str, "date", float]],
) -> None:
    """Batch upsert leader stocks — single round-trip instead of N."""
    if not records:
        return
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.executemany("""
            INSERT INTO mi_tracked_stocks
                (ticker, first_seen, last_seen, peak_rs_score, consecutive_weak_days, active)
            VALUES ($1, $2, $2, $3, 0, TRUE)
            ON CONFLICT (ticker) DO UPDATE SET
                last_seen = $2,
                peak_rs_score = GREATEST(mi_tracked_stocks.peak_rs_score, $3),
                consecutive_weak_days = 0,
                active = TRUE
        """, records)


async def mark_tracked_stocks_weak_batch(
    records: list[tuple[str, "date"]],
    retire_after: int = 7,
) -> None:
    """Batch mark-weak — single round-trip instead of N."""
    if not records:
        return
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.executemany("""
            UPDATE mi_tracked_stocks
            SET consecutive_weak_days = consecutive_weak_days + 1,
                last_seen = $2,
                active = CASE WHEN consecutive_weak_days + 1 >= $3 THEN FALSE ELSE active END
            WHERE ticker = $1
        """, [(ticker, today, retire_after) for ticker, today in records])


async def insert_ep_alert(record: dict[str, Any]) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO mi_ep_alerts
                (ticker, alert_date, gap_pct, rel_volume, ep_score, score_tier,
                 catalyst, catalyst_quality, claude_analysis, gemini_validation,
                 confidence_multiplier, vol_percentile)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
        """,
            record["ticker"], record["alert_date"], record["gap_pct"],
            record.get("rel_volume"), record["ep_score"], record["score_tier"],
            record.get("catalyst"), record.get("catalyst_quality"),
            record.get("claude_analysis"), record.get("gemini_validation"),
            record.get("confidence_multiplier", 1.0),
            record.get("vol_percentile"),
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


async def _resolve_score_date(conn: Any, requested: "date") -> "date":
    """
    Return requested date if mi_stock_scores has rows for it,
    otherwise fall back to the most recent date that has data.
    This ensures queries work before the nightly RS run has populated today.
    """
    count = await conn.fetchval(
        "SELECT COUNT(*) FROM mi_stock_scores WHERE score_date = $1", requested
    )
    if count:
        return requested
    latest = await conn.fetchval("SELECT MAX(score_date) FROM mi_stock_scores")
    return latest if latest is not None else requested


async def get_rs_leaders(d: "str | date", limit: int = 30) -> list[dict[str, Any]]:
    """Top RS stocks for a given date, falling back to most recent if no data for requested date."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        score_date = await _resolve_score_date(conn, _to_date(d))
        rows = await conn.fetch("""
            SELECT * FROM mi_stock_scores
            WHERE score_date = $1
            ORDER BY rs_composite DESC NULLS LAST
            LIMIT $2
        """, score_date, limit)
        return [dict(r) for r in rows]


async def get_today_ep_alerts(d: "str | date") -> list[dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT a.*,
                   s.rs_composite
            FROM mi_ep_alerts a
            LEFT JOIN LATERAL (
                SELECT rs_composite
                FROM mi_stock_scores
                WHERE ticker = a.ticker
                ORDER BY score_date DESC
                LIMIT 1
            ) s ON TRUE
            WHERE a.alert_date = $1
            ORDER BY a.ep_score DESC
            """,
            _to_date(d),
        )
        return [dict(r) for r in rows]


async def get_active_tracked_stocks() -> list[str]:
    """Return tickers currently being tracked for RS."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT ticker FROM mi_tracked_stocks WHERE active = TRUE"
        )
        return [r["ticker"] for r in rows]


async def upsert_tracked_stock(ticker: str, today: "date", rs_score: float) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO mi_tracked_stocks (ticker, first_seen, last_seen, peak_rs_score, consecutive_weak_days, active)
            VALUES ($1, $2, $2, $3, 0, TRUE)
            ON CONFLICT (ticker) DO UPDATE SET
                last_seen = $2,
                peak_rs_score = GREATEST(mi_tracked_stocks.peak_rs_score, $3),
                consecutive_weak_days = 0,
                active = TRUE
        """, ticker, today, rs_score)


async def mark_tracked_stock_weak(ticker: str, today: "date", retire_after: int = 7) -> None:
    """Increment weak day counter; deactivate if threshold exceeded."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE mi_tracked_stocks
            SET consecutive_weak_days = consecutive_weak_days + 1,
                last_seen = $2,
                active = CASE WHEN consecutive_weak_days + 1 >= $3 THEN FALSE ELSE active END
            WHERE ticker = $1
        """, ticker, today, retire_after)


async def get_active_themes() -> list[dict]:
    """
    Get the most recent snapshot of each active theme (stage != 'Retired').
    Used by the theme engine as the base for daily re-scoring.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT DISTINCT ON (name) *
            FROM mi_themes
            WHERE stage != 'Retired'
            ORDER BY name, theme_date DESC
        """)
        return [dict(r) for r in rows]


async def bulk_track_stocks(tickers: list[str], today: "date") -> int:
    """Add tickers to tracked stocks immediately (bypasses universe cap). Returns count upserted."""
    if not tickers:
        return 0
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.executemany("""
            INSERT INTO mi_tracked_stocks
                (ticker, first_seen, last_seen, peak_rs_score, consecutive_weak_days, active)
            VALUES ($1, $2, $2, 0, 0, TRUE)
            ON CONFLICT (ticker) DO UPDATE SET
                last_seen = $2,
                consecutive_weak_days = 0,
                active = TRUE
        """, [(t.upper(), today) for t in tickers])
    return len(tickers)


async def seed_theme(name: str, thesis: str, tickers: list[str], today: "date") -> None:
    """
    Manually seed a theme into mi_themes.
    Score starts at 0 — will be properly scored on next data refresh.
    If theme already exists today, merges tickers.
    """
    pool = await get_pool()
    tickers_upper = [t.upper() for t in tickers]
    async with pool.acquire() as conn:
        existing = await conn.fetchrow(
            "SELECT id, tickers FROM mi_themes WHERE name = $1 AND theme_date = $2",
            name, today,
        )
        if existing:
            merged = list(set(list(existing["tickers"] or [])) | set(tickers_upper))
            await conn.execute(
                "UPDATE mi_themes SET tickers = $1, description = COALESCE(NULLIF($2,''), description) WHERE id = $3",
                merged, thesis, existing["id"],
            )
        else:
            await conn.execute("""
                INSERT INTO mi_themes (theme_date, name, stage, score, description, tickers)
                VALUES ($1, $2, 'Nascent', 0, $3, $4)
            """, today, name, thesis, tickers_upper)


async def get_ma_pullbacks(
    d: "str | date",
    tickers: list[str] | None = None,
    rs_min: float = 50.0,
    pct_tolerance: float = 4.0,
) -> list[dict[str, Any]]:
    """
    Return stocks near their 10/20/50 SMAs (pulling back to key MAs).

    A stock is "near" an MA if:
      - It was above the MA (uptrend)
      - Current price is within pct_tolerance% of the MA

    Args:
        d: Score date to query
        tickers: Optional filter to specific tickers (e.g. a theme's stocks)
        rs_min: Minimum RS composite to include (filters out weak stocks)
        pct_tolerance: How close to the MA counts as a pullback (default ±4%)
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        score_date = await _resolve_score_date(conn, _to_date(d))
        if tickers:
            rows = await conn.fetch("""
                SELECT * FROM mi_stock_scores
                WHERE score_date = $1 AND ticker = ANY($2)
                AND rs_composite >= $3
                AND close IS NOT NULL
            """, score_date, tickers, rs_min)
        else:
            rows = await conn.fetch("""
                SELECT * FROM mi_stock_scores
                WHERE score_date = $1
                AND rs_composite >= $2
                AND close IS NOT NULL
                ORDER BY rs_composite DESC
            """, score_date, rs_min)

    results = []
    tol = pct_tolerance / 100.0

    for row in rows:
        r = dict(row)
        close = r.get("close")
        if not close:
            continue

        near = []
        for ma_col, label in [("sma_10", "10MA"), ("sma_20", "20MA"), ("sma_50", "50MA")]:
            sma = r.get(ma_col)
            if not sma:
                continue
            pct = (close / sma - 1.0)
            # Near MA and not broken below it hard (within tolerance, and at most 2x tolerance below)
            if -tol * 2 <= pct <= tol:
                near.append({
                    "ma": label,
                    "ma_value": round(sma, 2),
                    "pct_from_ma": round(pct * 100, 2),
                })

        if near:
            r["near_mas"] = near
            results.append(r)

    return results


async def get_ticker_extension_data(tickers: list[str]) -> list[dict]:
    """
    Return latest close, sma_20, and extension % from 20MA for specified tickers.
    Looks back up to 7 days in case today's data isn't scored yet.
    """
    pool = await get_pool()
    cutoff = date.today() - timedelta(days=7)
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT DISTINCT ON (ticker)
                ticker, close, sma_20, score_date
            FROM mi_stock_scores
            WHERE ticker = ANY($1)
              AND score_date >= $2
              AND close IS NOT NULL
              AND sma_20 IS NOT NULL
            ORDER BY ticker, score_date DESC
        """, tickers, cutoff)

    result = []
    for row in rows:
        close = row["close"]
        sma_20 = row["sma_20"]
        ext = ((close - sma_20) / sma_20 * 100) if sma_20 else None
        result.append({
            "ticker": row["ticker"],
            "close": close,
            "sma_20": sma_20,
            "extension_pct": round(ext, 1) if ext is not None else None,
            "score_date": str(row["score_date"]),
        })
    return result


async def get_volume_history(tickers: list[str], days: int = 60) -> dict[str, list[float]]:
    """
    Return historical adv_20 values per ticker for the last N days.
    Used to compute pre-market volume percentile in EP scoring — one batch
    query for all candidates rather than one query per ticker.
    """
    pool = await get_pool()
    cutoff = date.today() - timedelta(days=days)
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT ticker, adv_20
            FROM mi_stock_scores
            WHERE ticker = ANY($1)
              AND score_date >= $2
              AND adv_20 IS NOT NULL
            ORDER BY ticker, score_date
        """, tickers, cutoff)
    result: dict[str, list[float]] = {}
    for row in rows:
        result.setdefault(row["ticker"], []).append(row["adv_20"])
    return result


async def purge_old_data() -> dict[str, int]:
    """
    Delete rows older than retention limits to keep the DB lean.

    Retention policy:
    - mi_ep_alerts:    30 days  (daily scan history)
    - mi_stock_scores: 90 days  (RS engine — needs 90d for trend context)
    - mi_themes:       60 days  (daily theme snapshots)
    - mi_market_regime: kept forever (1 row/day, ~260 rows/year — negligible)
    - mi_tracked_stocks: kept forever (state table, not time-series)

    Returns dict with row counts deleted per table.
    """
    pool = await get_pool()
    today = date.today()
    deleted: dict[str, int] = {}

    async with pool.acquire() as conn:
        cutoffs = {
            "mi_ep_alerts":    today - timedelta(days=30),
            "mi_stock_scores": today - timedelta(days=90),
            "mi_themes":       today - timedelta(days=60),
        }
        date_cols = {
            "mi_ep_alerts":    "alert_date",
            "mi_stock_scores": "score_date",
            "mi_themes":       "theme_date",
        }
        for table, cutoff in cutoffs.items():
            col = date_cols[table]
            result = await conn.execute(
                f"DELETE FROM {table} WHERE {col} < $1", cutoff
            )
            # asyncpg returns "DELETE N" as a string
            count = int(result.split()[-1]) if result else 0
            deleted[table] = count
            if count:
                logger.info(f"Purged {count} rows from {table} (older than {cutoff})")

    return deleted


async def get_adv_map(d: "str | date") -> dict[str, float]:
    """Get stored ADV (avg daily volume) for all tickers as of a date."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT ticker, adv_20 FROM mi_stock_scores WHERE score_date = $1",
            _to_date(d),
        )
        return {r["ticker"]: r["adv_20"] for r in rows if r["adv_20"]}
