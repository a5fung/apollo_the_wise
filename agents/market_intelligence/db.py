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

# Security types considered "common stock" for RS scoring, breadth, and themes.
# CS = Common Stock, ADRC = ADR Common (foreign stocks traded on US exchanges).
COMMON_STOCK_TYPES = ('CS', 'ADRC')

_pool: Optional[asyncpg.Pool] = None


def _json_encoder(value):
    import json
    return json.dumps(value)


def _json_decoder(value):
    import json
    return json.loads(value)


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

        async def _init_conn(conn):
            await conn.set_type_codec(
                'jsonb', encoder=_json_encoder, decoder=_json_decoder,
                schema='pg_catalog',
            )

        _pool = await asyncpg.create_pool(
            host=host, port=port, database=db, user=user, password=password,
            min_size=1, max_size=5,
            init=_init_conn,
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
            ALTER TABLE mi_stock_scores ADD COLUMN IF NOT EXISTS sma_40 FLOAT;
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
                pct4_ratio_10d FLOAT,
                description TEXT,
                ep_threshold INT DEFAULT 70,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            ALTER TABLE mi_market_regime ADD COLUMN IF NOT EXISTS qqq_vs_50ma FLOAT;
            ALTER TABLE mi_market_regime ADD COLUMN IF NOT EXISTS pct4_ratio_10d FLOAT;
            ALTER TABLE mi_market_regime ADD COLUMN IF NOT EXISTS t2108 FLOAT;
            ALTER TABLE mi_market_regime ADD COLUMN IF NOT EXISTS pradeep_1m_50 INT;
            ALTER TABLE mi_market_regime ADD COLUMN IF NOT EXISTS pradeep_3m_25 INT;
            ALTER TABLE mi_market_regime ADD COLUMN IF NOT EXISTS full_up4_count INT;
            ALTER TABLE mi_market_regime ADD COLUMN IF NOT EXISTS full_down4_count INT;
            ALTER TABLE mi_market_regime ADD COLUMN IF NOT EXISTS consec_breakdown_days INT;
            ALTER TABLE mi_market_regime ADD COLUMN IF NOT EXISTS breadth_monitor JSONB;

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
                active BOOLEAN DEFAULT TRUE,
                quote_type TEXT DEFAULT NULL
            );

            CREATE TABLE IF NOT EXISTS mi_security_types (
                ticker TEXT PRIMARY KEY,
                security_type TEXT NOT NULL,
                exchange TEXT DEFAULT '',
                updated_at TIMESTAMPTZ DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS mi_job_log (
                job_name TEXT NOT NULL,
                run_date DATE NOT NULL,
                ran_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (job_name, run_date)
            );

            CREATE TABLE IF NOT EXISTS mi_overnight_watchlist (
                symbol TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                threshold_pct FLOAT NOT NULL DEFAULT 0.5,
                category TEXT NOT NULL DEFAULT 'index',
                notes TEXT DEFAULT '',
                active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );

            -- Seed defaults if empty
            INSERT INTO mi_overnight_watchlist (symbol, display_name, threshold_pct, category, notes)
            VALUES
                ('SPY', 'SPY', 0.5, 'index', 'always on'),
                ('QQQ', 'QQQ', 0.5, 'index', 'always on'),
                ('^VIX', 'VIX', 10.0, 'volatility', 'always on'),
                ('CL=F', 'Crude Oil', 3.0, 'commodity', 'Iran war — Strait of Hormuz risk')
            ON CONFLICT (symbol) DO NOTHING;

            -- Migration: replace futures symbols (ES=F, NQ=F) with ETFs (SPY, QQQ)
            DELETE FROM mi_overnight_watchlist WHERE symbol IN ('ES=F', 'NQ=F');
            INSERT INTO mi_overnight_watchlist (symbol, display_name, threshold_pct, category, notes)
            VALUES
                ('SPY', 'SPY', 0.5, 'index', 'always on'),
                ('QQQ', 'QQQ', 0.5, 'index', 'always on')
            ON CONFLICT (symbol) DO NOTHING;

            CREATE INDEX IF NOT EXISTS idx_stock_scores_score_date ON mi_stock_scores(score_date);
            CREATE INDEX IF NOT EXISTS idx_stock_scores_ticker ON mi_stock_scores(ticker);
            CREATE INDEX IF NOT EXISTS idx_ep_alerts_alert_date ON mi_ep_alerts(alert_date);
            CREATE INDEX IF NOT EXISTS idx_themes_theme_date ON mi_themes(theme_date);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_themes_date_name ON mi_themes(theme_date, name);

            CREATE TABLE IF NOT EXISTS mi_fundamental_flags (
                ticker TEXT NOT NULL,
                flag_date DATE NOT NULL,
                eps_yoy_latest FLOAT,
                eps_yoy_prior FLOAT,
                eps_accelerating BOOLEAN,
                eps_streak_25pct INT DEFAULT 0,
                sales_yoy_latest FLOAT,
                next_earnings_date DATE,
                PRIMARY KEY (ticker, flag_date)
            );
            CREATE INDEX IF NOT EXISTS idx_fund_flags_date ON mi_fundamental_flags(flag_date);

            CREATE TABLE IF NOT EXISTS mi_ticker_overrides (
                ticker TEXT PRIMARY KEY,
                description TEXT,
                notes TEXT,
                updated_at TIMESTAMPTZ DEFAULT NOW()
            );


            CREATE TABLE IF NOT EXISTS mi_daily_closes (
                trade_date DATE NOT NULL,
                ticker TEXT NOT NULL,
                close FLOAT NOT NULL,
                volume BIGINT,
                PRIMARY KEY (trade_date, ticker)
            );
            CREATE INDEX IF NOT EXISTS idx_daily_closes_ticker ON mi_daily_closes(ticker);

            CREATE TABLE IF NOT EXISTS mi_data_quality (
                run_date DATE NOT NULL,
                step TEXT NOT NULL,
                metric TEXT NOT NULL,
                value FLOAT,
                expected FLOAT,
                passed BOOLEAN DEFAULT TRUE,
                PRIMARY KEY (run_date, step, metric)
            );

            CREATE TABLE IF NOT EXISTS mi_signal_outcomes (
                id SERIAL PRIMARY KEY,
                signal_type TEXT NOT NULL,
                signal_date DATE NOT NULL,
                identifier TEXT NOT NULL,
                detail JSONB,
                fwd_1d_pct FLOAT,
                fwd_1w_pct FLOAT,
                fwd_1m_pct FLOAT,
                fwd_3m_pct FLOAT,
                spy_fwd_1m_pct FLOAT,
                spy_fwd_3m_pct FLOAT,
                computed_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE (signal_type, signal_date, identifier)
            );
            CREATE INDEX IF NOT EXISTS idx_signal_outcomes_type
                ON mi_signal_outcomes(signal_type, signal_date);

            CREATE TABLE IF NOT EXISTS mi_intraday_bars (
                ticker TEXT NOT NULL,
                bar_time TIMESTAMPTZ NOT NULL,
                open FLOAT NOT NULL,
                high FLOAT NOT NULL,
                low FLOAT NOT NULL,
                close FLOAT NOT NULL,
                volume BIGINT NOT NULL,
                vwap FLOAT,
                PRIMARY KEY (ticker, bar_time)
            );
            CREATE INDEX IF NOT EXISTS idx_intraday_bars_ticker
                ON mi_intraday_bars(ticker);

            CREATE TABLE IF NOT EXISTS mi_paper_trades (
                id SERIAL PRIMARY KEY,
                ticker TEXT NOT NULL,
                alert_date DATE NOT NULL,
                ep_score FLOAT NOT NULL,
                catalyst_quality TEXT,
                gap_pct FLOAT,
                regime TEXT,
                status TEXT NOT NULL DEFAULT 'open',
                entries JSONB NOT NULL DEFAULT '[]',
                exits JSONB NOT NULL DEFAULT '[]',
                remaining_shares FLOAT NOT NULL DEFAULT 0,
                stop_price FLOAT,
                last_entry_price FLOAT,
                total_pnl FLOAT NOT NULL DEFAULT 0,
                hold_days INT NOT NULL DEFAULT 0,
                skip_reason TEXT,
                orb_high FLOAT,
                orb_low FLOAT,
                atr_14 FLOAT,
                day1_low FLOAT,
                partial_taken BOOLEAN NOT NULL DEFAULT FALSE,
                breakeven_active BOOLEAN NOT NULL DEFAULT FALSE,
                running_closes JSONB NOT NULL DEFAULT '[]',
                created_at TIMESTAMPTZ DEFAULT NOW(),
                closed_at TIMESTAMPTZ,
                UNIQUE (ticker, alert_date)
            );
            CREATE INDEX IF NOT EXISTS idx_paper_trades_status
                ON mi_paper_trades(status);
        """)
        # ── Live trading tables ───────────────────────────────────────────
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mi_live_trades (
                id SERIAL PRIMARY KEY,
                ticker TEXT NOT NULL,
                alert_date DATE NOT NULL,
                ep_score FLOAT,
                catalyst_quality TEXT,
                gap_pct FLOAT,
                regime TEXT,
                status TEXT NOT NULL DEFAULT 'pending_confirmation',
                orb_high FLOAT,
                orb_low FLOAT,
                atr_14 FLOAT,
                entry_price FLOAT,
                entry_shares FLOAT,
                stop_price FLOAT,
                hard_stop FLOAT,
                position_size FLOAT,
                risk_dollars FLOAT,
                entry_order_id TEXT,
                stop_order_id TEXT,
                exits JSONB DEFAULT '[]',
                remaining_shares FLOAT DEFAULT 0,
                total_pnl FLOAT DEFAULT 0,
                hold_days INT DEFAULT 0,
                partial_taken BOOLEAN DEFAULT FALSE,
                breakeven_active BOOLEAN DEFAULT FALSE,
                running_closes JSONB DEFAULT '[]',
                proposed_at TIMESTAMPTZ,
                confirmed_at TIMESTAMPTZ,
                skip_reason TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                filled_at TIMESTAMPTZ,
                closed_at TIMESTAMPTZ,
                UNIQUE (ticker, alert_date)
            );
            CREATE INDEX IF NOT EXISTS idx_live_trades_status
                ON mi_live_trades(status);

            CREATE TABLE IF NOT EXISTS mi_live_orders (
                id SERIAL PRIMARY KEY,
                trade_id INT REFERENCES mi_live_trades(id),
                alpaca_order_id TEXT UNIQUE,
                ticker TEXT NOT NULL,
                side TEXT NOT NULL,
                order_type TEXT NOT NULL,
                qty FLOAT NOT NULL,
                stop_price FLOAT,
                limit_price FLOAT,
                status TEXT NOT NULL,
                filled_qty FLOAT,
                filled_avg_price FLOAT,
                submitted_at TIMESTAMPTZ DEFAULT NOW(),
                filled_at TIMESTAMPTZ,
                cancelled_at TIMESTAMPTZ,
                raw_response JSONB
            );
        """)

        # Migrations — add columns to existing tables
        await conn.execute("""
            ALTER TABLE mi_tracked_stocks
                ADD COLUMN IF NOT EXISTS quote_type TEXT DEFAULT NULL;
        """)
        # ── Delete protection for trade tables ──────────────────────────────
        # Prevent accidental DELETE/TRUNCATE on trade tables via DB trigger.
        # To intentionally delete: SET LOCAL mi.allow_trade_delete = 'yes';
        await conn.execute("""
            CREATE OR REPLACE FUNCTION protect_trade_tables() RETURNS TRIGGER AS $$
            BEGIN
                IF current_setting('mi.allow_trade_delete', true) = 'yes' THEN
                    RETURN OLD;
                END IF;
                RAISE EXCEPTION 'DELETE on % is blocked. SET LOCAL mi.allow_trade_delete = ''yes'' first.',
                    TG_TABLE_NAME;
            END;
            $$ LANGUAGE plpgsql;
        """)
        for tbl in ("mi_paper_trades", "mi_live_trades", "mi_live_orders"):
            await conn.execute(f"""
                DROP TRIGGER IF EXISTS prevent_delete_{tbl} ON {tbl};
                CREATE TRIGGER prevent_delete_{tbl}
                    BEFORE DELETE ON {tbl}
                    FOR EACH ROW EXECUTE FUNCTION protect_trade_tables();
            """)

        # ── Theme exclusions table ────────────────────────────────────────
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mi_theme_exclusions (
                id SERIAL PRIMARY KEY,
                ticker TEXT NOT NULL,
                theme_name TEXT NOT NULL,
                reason TEXT,
                excluded_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE (ticker, theme_name)
            );
            CREATE INDEX IF NOT EXISTS idx_theme_exclusions_theme
                ON mi_theme_exclusions(theme_name);
        """)

        # ── EP scan log — every gap candidate + filter outcome ───────────
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mi_ep_scan_log (
                id SERIAL PRIMARY KEY,
                scan_date DATE NOT NULL,
                ticker TEXT NOT NULL,
                gap_pct FLOAT,
                prev_close FLOAT,
                rel_volume FLOAT,
                filter_reason TEXT,
                ep_score FLOAT,
                score_tier TEXT,
                catalyst_quality TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE (scan_date, ticker)
            );
            CREATE INDEX IF NOT EXISTS idx_ep_scan_log_date
                ON mi_ep_scan_log(scan_date DESC);
        """)

        # ── Audit log — critical events queryable from Telegram ──────────
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mi_audit_log (
                id SERIAL PRIMARY KEY,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                event_type TEXT NOT NULL,
                summary TEXT NOT NULL,
                detail TEXT DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_audit_log_created_at
                ON mi_audit_log(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_audit_log_event_type
                ON mi_audit_log(event_type);
        """)

        # ── Migrations ───────────────────────────────────────────────────
        await conn.execute("""
            ALTER TABLE mi_live_trades
                ADD COLUMN IF NOT EXISTS entry_attempt INT NOT NULL DEFAULT 1;
            ALTER TABLE mi_themes
                ADD COLUMN IF NOT EXISTS rs_avg FLOAT;
            ALTER TABLE mi_ticker_overrides
                ADD COLUMN IF NOT EXISTS sector TEXT;
            ALTER TABLE mi_ticker_overrides
                ADD COLUMN IF NOT EXISTS industry TEXT;
        """)

        # ── One-time cleanup: delete auto-generated descriptions for tickers ──
        # that now have authoritative static entries in universe.py.
        # These corrupted rows were created by _ensure_descriptions when
        # Perplexity was down — yfinance summaries for e.g. Avis Budget Group
        # mention "connected vehicles / digital platform", causing Haiku to
        # generate tech-adjacent descriptions that landed them in data-center themes.
        # After this migration, _ensure_descriptions skips _STATIC_BASELINE tickers
        # so the bad rows can never be re-created.
        static_tickers_to_clean = [
            "CAR",   # Avis Budget Group — was getting tech-adjacent description
        ]
        await conn.execute(
            "DELETE FROM mi_ticker_overrides WHERE ticker = ANY($1)",
            static_tickers_to_clean,
        )
        logger.info(f"Migration: cleared bad auto-generated descriptions for {static_tickers_to_clean}")

        # ── Log row counts on startup for early data-loss detection ───────
        for tbl in ("mi_paper_trades", "mi_live_trades"):
            count = await conn.fetchval(f"SELECT COUNT(*) FROM {tbl}")
            logger.info(f"Startup row count: {tbl} = {count}")

    logger.info("Market Intelligence DB schema initialized")


async def upsert_stock_score(record: dict[str, Any]) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO mi_stock_scores
                (ticker, score_date, rs_1m, rs_3m, rs_6m, rs_composite, rs_rank,
                 sector, adv_20, market_cap, sma_10, sma_20, sma_40, sma_50, close,
                 raw_1m, raw_3m, raw_6m)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18)
            ON CONFLICT (ticker, score_date) DO UPDATE SET
                rs_1m=EXCLUDED.rs_1m, rs_3m=EXCLUDED.rs_3m, rs_6m=EXCLUDED.rs_6m,
                rs_composite=EXCLUDED.rs_composite, rs_rank=EXCLUDED.rs_rank,
                sector=EXCLUDED.sector, adv_20=EXCLUDED.adv_20, market_cap=EXCLUDED.market_cap,
                sma_10=EXCLUDED.sma_10, sma_20=EXCLUDED.sma_20, sma_40=EXCLUDED.sma_40,
                sma_50=EXCLUDED.sma_50, close=EXCLUDED.close, raw_1m=EXCLUDED.raw_1m,
                raw_3m=EXCLUDED.raw_3m, raw_6m=EXCLUDED.raw_6m
        """,
            record["ticker"], record["score_date"], record.get("rs_1m"), record.get("rs_3m"),
            record.get("rs_6m"), record.get("rs_composite"), record.get("rs_rank"),
            record.get("sector"), record.get("adv_20"), record.get("market_cap"),
            record.get("sma_10"), record.get("sma_20"), record.get("sma_40"), record.get("sma_50"),
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
                 sector, adv_20, market_cap, sma_10, sma_20, sma_40, sma_50, close,
                 raw_1m, raw_3m, raw_6m)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18)
            ON CONFLICT (ticker, score_date) DO UPDATE SET
                rs_1m=EXCLUDED.rs_1m, rs_3m=EXCLUDED.rs_3m, rs_6m=EXCLUDED.rs_6m,
                rs_composite=EXCLUDED.rs_composite, rs_rank=EXCLUDED.rs_rank,
                sector=EXCLUDED.sector, adv_20=EXCLUDED.adv_20, market_cap=EXCLUDED.market_cap,
                sma_10=EXCLUDED.sma_10, sma_20=EXCLUDED.sma_20, sma_40=EXCLUDED.sma_40,
                sma_50=EXCLUDED.sma_50, close=EXCLUDED.close, raw_1m=EXCLUDED.raw_1m,
                raw_3m=EXCLUDED.raw_3m, raw_6m=EXCLUDED.raw_6m
        """, [
            (r["ticker"], r["score_date"], r.get("rs_1m"), r.get("rs_3m"),
             r.get("rs_6m"), r.get("rs_composite"), r.get("rs_rank"),
             r.get("sector"), r.get("adv_20"), r.get("market_cap"),
             r.get("sma_10"), r.get("sma_20"), r.get("sma_40"), r.get("sma_50"),
             r.get("close"), r.get("raw_1m"), r.get("raw_3m"), r.get("raw_6m"))
            for r in records
        ])


async def update_sectors_batch(score_date: date, sector_map: dict[str, str]) -> int:
    """Update sector column for stocks on a given score_date. Returns count updated."""
    if not sector_map:
        return 0
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.executemany(
            "UPDATE mi_stock_scores SET sector = $1 WHERE score_date = $2 AND ticker = $3",
            [(sector, score_date, ticker) for ticker, sector in sector_map.items()],
        )
        return len(sector_map)


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


async def update_quote_types_batch(updates: dict[str, str]) -> int:
    """Set quote_type for tracked stocks. Returns count updated."""
    if not updates:
        return 0
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.executemany("""
            UPDATE mi_tracked_stocks SET quote_type = $2
            WHERE ticker = $1 AND (quote_type IS NULL OR quote_type != $2)
        """, [(ticker, qt) for ticker, qt in updates.items()])
    return len(updates)


async def get_tracked_tickers_missing_quote_type(limit: int = 100) -> list[str]:
    """Get active tracked tickers that don't have quote_type set yet."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT ticker FROM mi_tracked_stocks
            WHERE active = TRUE AND quote_type IS NULL
            LIMIT $1
        """, limit)
        return [r["ticker"] for r in rows]


async def insert_ep_alert(record: dict[str, Any]) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Ensure source column exists (idempotent)
        await conn.execute(
            "ALTER TABLE mi_ep_alerts ADD COLUMN IF NOT EXISTS source TEXT DEFAULT 'live'"
        )
        await conn.execute("""
            INSERT INTO mi_ep_alerts
                (ticker, alert_date, gap_pct, rel_volume, ep_score, score_tier,
                 catalyst, catalyst_quality, claude_analysis, gemini_validation,
                 confidence_multiplier, vol_percentile, source)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
        """,
            record["ticker"], record["alert_date"], record["gap_pct"],
            record.get("rel_volume"), record["ep_score"], record["score_tier"],
            record.get("catalyst"), record.get("catalyst_quality"),
            record.get("claude_analysis"), record.get("gemini_validation"),
            record.get("confidence_multiplier", 1.0),
            record.get("vol_percentile"),
            record.get("source", "live"),
        )


async def delete_historical_alerts(from_date: date, to_date: date) -> int:
    """Delete historical_scan alerts in date range (for idempotent re-runs)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Ensure source column exists before querying it
        await conn.execute(
            "ALTER TABLE mi_ep_alerts ADD COLUMN IF NOT EXISTS source TEXT DEFAULT 'live'"
        )
        result = await conn.execute("""
            DELETE FROM mi_ep_alerts
            WHERE source = 'historical_scan'
              AND alert_date >= $1 AND alert_date <= $2
        """, from_date, to_date)
        return int(result.split()[-1])  # "DELETE N"


async def upsert_regime(record: dict[str, Any]) -> None:
    import json
    pool = await get_pool()
    bm = record.get("breadth_monitor")
    bm_json = json.dumps(bm) if bm else None
    async with pool.acquire() as conn:
        # Ensure QQQ EMA columns exist (idempotent)
        for col, typ in [("qqq_ema_10", "FLOAT"), ("qqq_ema_20", "FLOAT"), ("qqq_ema_bullish", "BOOLEAN")]:
            await conn.execute(f"ALTER TABLE mi_market_regime ADD COLUMN IF NOT EXISTS {col} {typ}")
        await conn.execute("""
            INSERT INTO mi_market_regime
                (regime_date, regime, spy_vs_50ma, spy_vs_200ma, qqq_vs_50ma, vix,
                 breadth_pct_above_40ma, bo_bd_ratio_5d, pct4_ratio_10d, description, ep_threshold,
                 t2108, pradeep_1m_50, pradeep_3m_25, full_up4_count, full_down4_count,
                 consec_breakdown_days, breadth_monitor,
                 qqq_ema_10, qqq_ema_20, qqq_ema_bullish)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18::jsonb,
                    $19,$20,$21)
            ON CONFLICT (regime_date) DO UPDATE SET
                regime=EXCLUDED.regime, spy_vs_50ma=EXCLUDED.spy_vs_50ma,
                spy_vs_200ma=EXCLUDED.spy_vs_200ma, qqq_vs_50ma=EXCLUDED.qqq_vs_50ma,
                vix=EXCLUDED.vix, breadth_pct_above_40ma=EXCLUDED.breadth_pct_above_40ma,
                bo_bd_ratio_5d=EXCLUDED.bo_bd_ratio_5d, pct4_ratio_10d=EXCLUDED.pct4_ratio_10d,
                description=EXCLUDED.description, ep_threshold=EXCLUDED.ep_threshold,
                t2108=EXCLUDED.t2108, pradeep_1m_50=EXCLUDED.pradeep_1m_50,
                pradeep_3m_25=EXCLUDED.pradeep_3m_25, full_up4_count=EXCLUDED.full_up4_count,
                full_down4_count=EXCLUDED.full_down4_count,
                consec_breakdown_days=EXCLUDED.consec_breakdown_days,
                breadth_monitor=EXCLUDED.breadth_monitor,
                qqq_ema_10=EXCLUDED.qqq_ema_10, qqq_ema_20=EXCLUDED.qqq_ema_20,
                qqq_ema_bullish=EXCLUDED.qqq_ema_bullish
        """,
            record["regime_date"], record["regime"], record.get("spy_vs_50ma"),
            record.get("spy_vs_200ma"), record.get("qqq_vs_50ma"), record.get("vix"),
            record.get("breadth_pct_above_40ma"), record.get("bo_bd_ratio_5d"),
            record.get("pct4_ratio_10d"),
            record.get("description"), record.get("ep_threshold", 70),
            record.get("t2108"), record.get("pradeep_1m_50"), record.get("pradeep_3m_25"),
            record.get("full_up4_count"), record.get("full_down4_count"),
            record.get("consec_breakdown_days"), bm_json,
            record.get("qqq_ema_10"), record.get("qqq_ema_20"), record.get("qqq_ema_bullish"),
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


async def get_rs_leaders(
    d: "str | date",
    limit: int = 30,
    min_adv: float = 500_000,
    min_price: float = 10.0,
) -> list[dict[str, Any]]:
    """Top RS stocks for a given date, filtered to liquid names (min ADV + min price).
    Excludes leveraged/inverse ETFs, broad index ETFs, and small-cap biotech/pharma.
    Set min_adv=0 to get all stocks unfiltered."""
    from agents.market_intelligence.constants import SKIP_TICKERS_LIST, is_sector_filtered
    pool = await get_pool()
    async with pool.acquire() as conn:
        score_date = await _resolve_score_date(conn, _to_date(d))
        if min_adv > 0:
            # Fetch extra rows to allow post-filter for sector
            rows = await conn.fetch("""
                SELECT s.* FROM mi_stock_scores s
                WHERE s.score_date = $1
                  AND s.adv_20 IS NOT NULL AND s.adv_20 >= $3
                  AND s.ticker != ALL($4)
                  AND s.close IS NOT NULL AND s.close >= $5
                  AND NOT EXISTS (
                      SELECT 1 FROM mi_tracked_stocks t
                      WHERE t.ticker = s.ticker AND t.quote_type IS NOT NULL AND t.quote_type != 'EQUITY'
                  )
                ORDER BY s.rs_composite DESC NULLS LAST
                LIMIT $2
            """, score_date, limit * 2, min_adv, SKIP_TICKERS_LIST, min_price)
            filtered = []
            for r in rows:
                row = dict(r)
                if is_sector_filtered(row.get("sector"), row.get("close")):
                    continue
                filtered.append(row)
                if len(filtered) >= limit:
                    break
            return filtered
        else:
            rows = await conn.fetch("""
                SELECT * FROM mi_stock_scores
                WHERE score_date = $1
                  AND ticker != ALL($3)
                ORDER BY rs_composite DESC NULLS LAST
                LIMIT $2
            """, score_date, limit, SKIP_TICKERS_LIST)
            return [dict(r) for r in rows]


async def get_rs_for_tickers(
    d: "str | date", tickers: list[str],
) -> dict[str, dict[str, Any]]:
    """Get RS scores for a specific list of tickers, keyed by ticker."""
    if not tickers:
        return {}
    pool = await get_pool()
    async with pool.acquire() as conn:
        score_date = await _resolve_score_date(conn, _to_date(d))
        rows = await conn.fetch("""
            SELECT ticker, rs_composite, rs_1m, rs_3m, rs_6m
            FROM mi_stock_scores
            WHERE score_date = $1 AND ticker = ANY($2)
        """, score_date, tickers)
        return {r["ticker"]: dict(r) for r in rows}


async def get_recent_rs_batch(
    tickers: list[str], d: "str | date", days: int = 3,
) -> dict[str, list[float]]:
    """Return last N days of rs_composite for multiple tickers.

    Keyed by ticker, most recent first. Missing days are omitted (not filled).
    """
    if not tickers:
        return {}
    pool = await get_pool()
    target = _to_date(d)
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT ticker, rs_composite, score_date
            FROM mi_stock_scores
            WHERE ticker = ANY($1)
              AND score_date <= $2
              AND rs_composite IS NOT NULL
            ORDER BY ticker, score_date DESC
        """, tickers, target)

        result: dict[str, list[float]] = {}
        for r in rows:
            tk = r["ticker"]
            if tk not in result:
                result[tk] = []
            if len(result[tk]) < days:
                result[tk].append(float(r["rs_composite"]))
        return result


async def get_prior_theme_scores(d: "str | date") -> dict[str, float]:
    """Get the most recent theme RS averages BEFORE the given date, keyed by theme name."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        target = _to_date(d)
        rows = await conn.fetch("""
            SELECT name, rs_avg FROM mi_themes
            WHERE theme_date = (
                SELECT MAX(theme_date) FROM mi_themes WHERE theme_date < $1
            ) AND rs_avg IS NOT NULL
        """, target)
        return {r["name"]: r["rs_avg"] for r in rows}


async def get_rs_history(
    tickers: list[str],
    from_date: "str | date",
    to_date: "str | date",
    interval: str = "weekly",
) -> dict[str, list[dict[str, Any]]]:
    """
    Return RS time series for given tickers over a date range.

    interval: 'daily' or 'weekly' (weekly = one row per ticker per week, using latest available date)
    Returns: {ticker: [{date, rs_composite, rs_1m, rs_3m, rs_6m, close}, ...]}
    """
    pool = await get_pool()
    fd, td = _to_date(from_date), _to_date(to_date)
    tickers_upper = [t.upper() for t in tickers]
    async with pool.acquire() as conn:
        if interval == "weekly":
            # Pick one row per week per ticker (latest score_date in each ISO week)
            rows = await conn.fetch("""
                SELECT DISTINCT ON (ticker, date_trunc('week', score_date))
                    ticker, score_date, rs_composite, rs_1m, rs_3m, rs_6m, close
                FROM mi_stock_scores
                WHERE ticker = ANY($1)
                  AND score_date >= $2
                  AND score_date <= $3
                ORDER BY ticker, date_trunc('week', score_date), score_date DESC
            """, tickers_upper, fd, td)
        else:
            rows = await conn.fetch("""
                SELECT ticker, score_date, rs_composite, rs_1m, rs_3m, rs_6m, close
                FROM mi_stock_scores
                WHERE ticker = ANY($1)
                  AND score_date >= $2
                  AND score_date <= $3
                ORDER BY ticker, score_date
            """, tickers_upper, fd, td)

    result: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        tk = r["ticker"]
        if tk not in result:
            result[tk] = []
        result[tk].append({
            "date": r["score_date"].isoformat(),
            "rs_composite": r["rs_composite"],
            "rs_1m": r["rs_1m"],
            "rs_3m": r["rs_3m"],
            "rs_6m": r["rs_6m"],
            "close": r["close"],
        })
    return result


async def get_theme_history(
    theme_name: str,
    from_date: "str | date | None" = None,
    to_date: "str | date | None" = None,
) -> list[dict[str, Any]]:
    """
    Return all daily snapshots for a theme across a date range.
    If from_date is None, returns all available history.
    Matches theme name case-insensitively (ILIKE).
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        if from_date and to_date:
            rows = await conn.fetch("""
                SELECT theme_date, name, stage, score, description, tickers
                FROM mi_themes
                WHERE name ILIKE $1
                  AND theme_date >= $2
                  AND theme_date <= $3
                ORDER BY theme_date
            """, f"%{theme_name}%", _to_date(from_date), _to_date(to_date))
        else:
            rows = await conn.fetch("""
                SELECT theme_date, name, stage, score, description, tickers
                FROM mi_themes
                WHERE name ILIKE $1
                ORDER BY theme_date
            """, f"%{theme_name}%")

    return [{
        "date": r["theme_date"].isoformat(),
        "name": r["name"],
        "stage": r["stage"],
        "score": r["score"],
        "description": r["description"],
        "tickers": r["tickers"],
    } for r in rows]


async def _resolve_weekly_snapshots(conn: Any, base_date: "date") -> list:
    """
    Find actual score_dates closest to base_date - 7/14/21/28 days.
    Returns [d0, d7, d14, d21, d28] where each is the nearest score_date
    within ±2 days of the target, or None if no data exists.
    """
    targets = [
        base_date,
        base_date - timedelta(days=7),
        base_date - timedelta(days=14),
        base_date - timedelta(days=21),
        base_date - timedelta(days=28),
    ]
    # Single query: get all distinct score_dates in the ±2 day range of any target
    window_start = min(targets) - timedelta(days=2)
    window_end = max(targets) + timedelta(days=2)
    rows = await conn.fetch(
        "SELECT DISTINCT score_date FROM mi_stock_scores WHERE score_date BETWEEN $1 AND $2",
        window_start, window_end,
    )
    all_dates = {r["score_date"] for r in rows}

    resolved = []
    for t in targets:
        # Find closest date within ±2 days
        best = None
        best_dist = 999
        for sd in all_dates:
            dist = abs((sd - t).days)
            if dist <= 2 and dist < best_dist:
                best = sd
                best_dist = dist
        resolved.append(best)
    return resolved


# Sentinel date that can't match any real data — used for NULL snapshot placeholders in SQL
_SENTINEL_DATE = date(2000, 1, 1)


async def _prepare_weekly_snapshots(
    conn: Any, d: "str | date",
) -> tuple["date", list, "date", "date", "date | None", "date | None", "date | None"] | None:
    """
    Resolve score_date and weekly snapshots. Returns None if insufficient data.
    Otherwise returns (d0, available, d0, d7, d14_or_sentinel, d21_or_sentinel, d28_or_sentinel).
    """
    score_date = await _resolve_score_date(conn, _to_date(d))
    dates = await _resolve_weekly_snapshots(conn, score_date)
    d0, d7, d14, d21, d28 = dates

    if not d0 or not d7:
        return None

    available = [x for x in dates if x is not None]
    return (d0, available, d0, d7,
            d14 or _SENTINEL_DATE, d21 or _SENTINEL_DATE, d28 or _SENTINEL_DATE)


async def get_rs_velocity(
    d: "str | date",
    min_rs: float = 40.0,
    limit: int = 30,
) -> list[dict[str, Any]]:
    """
    Return stocks ranked by sustained multi-week RS acceleration.

    Velocity composite (front-weighted like IBD RS rating):
        v1w = rs_today  - rs_7d_ago
        v2w = rs_7d_ago - rs_14d_ago
        v3w = rs_14d_ago - rs_21d_ago
        v4w = rs_21d_ago - rs_28d_ago
        score = 0.40*v1w + 0.30*v2w + 0.20*v3w + 0.10*v4w
        × 1.2 consistency bonus if all non-NULL weekly deltas are positive

    Only includes stocks that:
    - Have data for today AND at least 2 of the 4 prior week snapshots
    - Have current rs_composite >= min_rs (filters out weak stocks "recovering")
    - Have a positive velocity score (net rising RS over the window)
    - Most recent week (v1w) must be positive (still accelerating, not stalled)
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        prep = await _prepare_weekly_snapshots(conn, d)
        if not prep:
            return []
        d0, available, d0_, d7, d14, d21, d28 = prep

        rows = await conn.fetch("""
            WITH snapshots AS (
                SELECT ticker, score_date, rs_composite, sector
                FROM mi_stock_scores
                WHERE score_date = ANY($1) AND rs_composite IS NOT NULL
            ),
            pivoted AS (
                SELECT
                    ticker,
                    MAX(CASE WHEN score_date = $2 THEN rs_composite END) AS rs_now,
                    MAX(CASE WHEN score_date = $3 THEN rs_composite END) AS rs_7d,
                    MAX(CASE WHEN score_date = $4 THEN rs_composite END) AS rs_14d,
                    MAX(CASE WHEN score_date = $5 THEN rs_composite END) AS rs_21d,
                    MAX(CASE WHEN score_date = $6 THEN rs_composite END) AS rs_28d,
                    MAX(CASE WHEN score_date = $2 THEN sector END)       AS sector
                FROM snapshots
                GROUP BY ticker
            ),
            velocity AS (
                SELECT
                    ticker, sector, rs_now, rs_7d, rs_14d, rs_21d, rs_28d,
                    (rs_now  - rs_7d)  AS v1w,
                    (rs_7d   - rs_14d) AS v2w,
                    (rs_14d  - rs_21d) AS v3w,
                    (rs_21d  - rs_28d) AS v4w,
                    (
                        COALESCE(0.40 * (rs_now  - rs_7d),  0) +
                        COALESCE(0.30 * (rs_7d   - rs_14d), 0) +
                        COALESCE(0.20 * (rs_14d  - rs_21d), 0) +
                        COALESCE(0.10 * (rs_21d  - rs_28d), 0)
                    ) *
                    CASE
                        WHEN (rs_now  - rs_7d  > 0)
                         AND (rs_7d  - rs_14d > 0 OR rs_14d IS NULL)
                         AND (rs_14d - rs_21d > 0 OR rs_21d IS NULL)
                         AND (rs_21d - rs_28d > 0 OR rs_28d IS NULL)
                         AND (CASE WHEN rs_14d IS NOT NULL AND rs_7d - rs_14d > 0 THEN 1 ELSE 0 END +
                              CASE WHEN rs_21d IS NOT NULL AND rs_14d - rs_21d > 0 THEN 1 ELSE 0 END +
                              CASE WHEN rs_28d IS NOT NULL AND rs_21d - rs_28d > 0 THEN 1 ELSE 0 END) >= 1
                        THEN 1.2 ELSE 1.0
                    END AS velocity_score,
                    (CASE WHEN rs_7d  IS NOT NULL THEN 1 ELSE 0 END +
                     CASE WHEN rs_14d IS NOT NULL THEN 1 ELSE 0 END +
                     CASE WHEN rs_21d IS NOT NULL THEN 1 ELSE 0 END +
                     CASE WHEN rs_28d IS NOT NULL THEN 1 ELSE 0 END) AS weeks_of_data
                FROM pivoted
                WHERE rs_now IS NOT NULL
            )
            SELECT *
            FROM velocity
            WHERE rs_now >= $7 AND weeks_of_data >= 2
              AND velocity_score > 0 AND (rs_now - rs_7d) > 0
            ORDER BY velocity_score DESC
            LIMIT $8
        """, available, d0, d7, d14, d21, d28, min_rs, limit)

        return [dict(r) for r in rows]


async def get_rs_turners(
    d: "str | date",
    max_rs_4w_ago: float = 30.0,
    min_consecutive_weeks: int = 3,
    limit: int = 40,
) -> list[dict[str, Any]]:
    """
    Find stocks turning from weak to strengthening — the early rotation signal.

    Criteria:
    - RS was <= max_rs_4w_ago at the earliest available snapshot (was weak)
    - RS improved for min_consecutive_weeks in a row (sustained turn)
    - Current RS > earliest RS by at least 10 points (meaningful improvement)
    - Stocks must have sector data (NULL sectors excluded)

    Returns rows with: ticker, sector, rs_now, rs_7d..rs_28d, v1w..v4w,
    consecutive_up_weeks, rs_gain (total improvement).
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        prep = await _prepare_weekly_snapshots(conn, d)
        if not prep:
            return []
        d0, available, d0_, d7, d14, d21, d28 = prep

        rows = await conn.fetch("""
            WITH snapshots AS (
                SELECT ticker, score_date, rs_composite, sector
                FROM mi_stock_scores
                WHERE score_date = ANY($1) AND rs_composite IS NOT NULL
            ),
            pivoted AS (
                SELECT
                    ticker,
                    MAX(CASE WHEN score_date = $2 THEN rs_composite END) AS rs_now,
                    MAX(CASE WHEN score_date = $3 THEN rs_composite END) AS rs_7d,
                    MAX(CASE WHEN score_date = $4 THEN rs_composite END) AS rs_14d,
                    MAX(CASE WHEN score_date = $5 THEN rs_composite END) AS rs_21d,
                    MAX(CASE WHEN score_date = $6 THEN rs_composite END) AS rs_28d,
                    MAX(CASE WHEN score_date = $2 THEN sector END)       AS sector
                FROM snapshots
                GROUP BY ticker
            ),
            deltas AS (
                SELECT *,
                    (rs_now  - rs_7d)  AS v1w,
                    (rs_7d   - rs_14d) AS v2w,
                    (rs_14d  - rs_21d) AS v3w,
                    (rs_21d  - rs_28d) AS v4w,
                    CASE WHEN rs_now > rs_7d THEN 1 ELSE 0 END +
                    CASE WHEN rs_now > rs_7d AND rs_7d > rs_14d THEN 1 ELSE 0 END +
                    CASE WHEN rs_now > rs_7d AND rs_7d > rs_14d AND rs_14d > rs_21d THEN 1 ELSE 0 END +
                    CASE WHEN rs_now > rs_7d AND rs_7d > rs_14d AND rs_14d > rs_21d AND rs_21d > rs_28d THEN 1 ELSE 0 END
                    AS consecutive_up_weeks,
                    COALESCE(rs_28d, rs_21d, rs_14d, rs_7d) AS rs_earliest
                FROM pivoted
                WHERE rs_now IS NOT NULL AND sector IS NOT NULL
            )
            SELECT *, rs_now - rs_earliest AS rs_gain
            FROM deltas
            WHERE rs_earliest IS NOT NULL
              AND rs_earliest <= $7
              AND consecutive_up_weeks >= $8
              AND rs_now > rs_earliest + 10
            ORDER BY consecutive_up_weeks DESC, rs_now - rs_earliest DESC
            LIMIT $9
        """, available, d0, d7, d14, d21, d28,
             max_rs_4w_ago, min_consecutive_weeks, limit)

        return [dict(r) for r in rows]


async def get_ep_history(days: int = 14) -> list[dict[str, Any]]:
    """Return EP alerts from the past N days, sorted by date desc then score desc."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT a.ticker, a.alert_date, a.ep_score, a.score_tier,
                   a.gap_pct, a.catalyst_quality, a.claude_analysis,
                   s.rs_composite
            FROM mi_ep_alerts a
            LEFT JOIN LATERAL (
                SELECT rs_composite FROM mi_stock_scores
                WHERE ticker = a.ticker
                ORDER BY score_date DESC LIMIT 1
            ) s ON TRUE
            WHERE a.alert_date >= CURRENT_DATE - $1::int
            ORDER BY a.alert_date DESC, a.ep_score DESC
            """,
            days,
        )
    return [dict(r) for r in rows]


async def log_ep_scan_candidates(records: list[dict]) -> None:
    """
    Batch-upsert EP scan candidates for a given scan date.
    Each record: {scan_date, ticker, gap_pct, prev_close, rel_volume,
                  filter_reason (or None if scored), ep_score, score_tier, catalyst_quality}
    Never raises — scan must not be blocked by logging failures.
    """
    if not records:
        return
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            await conn.executemany("""
                INSERT INTO mi_ep_scan_log
                    (scan_date, ticker, gap_pct, prev_close, rel_volume,
                     filter_reason, ep_score, score_tier, catalyst_quality)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (scan_date, ticker) DO UPDATE SET
                    filter_reason    = EXCLUDED.filter_reason,
                    ep_score         = EXCLUDED.ep_score,
                    score_tier       = EXCLUDED.score_tier,
                    catalyst_quality = EXCLUDED.catalyst_quality
            """, [
                (
                    r["scan_date"], r["ticker"], r.get("gap_pct"),
                    r.get("prev_close"), r.get("rel_volume"),
                    r.get("filter_reason"), r.get("ep_score"),
                    r.get("score_tier"), r.get("catalyst_quality"),
                )
                for r in records
            ])
    except Exception as e:
        import logging as _logging
        _logging.getLogger(__name__).warning(f"EP scan log write failed: {e}")


async def get_ep_scan_log(d: "str | date") -> list[dict[str, Any]]:
    """Return all gap candidates evaluated on a given date, scored + filtered."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT ticker, gap_pct, prev_close, rel_volume,
                      filter_reason, ep_score, score_tier, catalyst_quality
               FROM mi_ep_scan_log
               WHERE scan_date = $1
               ORDER BY ep_score DESC NULLS LAST, gap_pct DESC""",
            _to_date(d),
        )
    return [dict(r) for r in rows]


async def get_ep_scan_log_history(days: int = 14) -> dict[str, list[dict]]:
    """Return scan log grouped by date for the past N days."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT scan_date, ticker, gap_pct, prev_close, rel_volume,
                      filter_reason, ep_score, score_tier, catalyst_quality
               FROM mi_ep_scan_log
               WHERE scan_date >= CURRENT_DATE - $1::int
               ORDER BY scan_date DESC, ep_score DESC NULLS LAST, gap_pct DESC""",
            days,
        )
    result: dict[str, list] = {}
    for r in rows:
        key = str(r["scan_date"])
        result.setdefault(key, []).append(dict(r))
    return result


async def get_today_ep_alerts(d: "str | date") -> list[dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT ON (a.ticker)
                   a.*,
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
            ORDER BY a.ticker, a.ep_score DESC
            """,
            _to_date(d),
        )
        # Re-sort by score after DISTINCT ON (which requires ORDER BY ticker first)
        results = [dict(r) for r in rows]
        results.sort(key=lambda r: r.get("ep_score", 0), reverse=True)
        return results


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


async def restore_recently_retired_themes(since_date: "date") -> dict:
    """
    Full recovery from one-night mass theme collapse caused by bad validation run.

    Root cause: upsert_ticker_sectors_batch wrote NULL descriptions → old
    get_ticker_overrides returned them → TICKER_DESC overwritten with None for
    hundreds of stocks → _ensure_descriptions mass-regenerated bad descriptions →
    validation with aggressive prompt stripped RS 99 stocks from correct themes →
    themes went Fading in one run.

    Three-step cleanup:
    1. Clear auto-generated exclusions (reason 'description inconsistent').
    2. For themes that went from non-Fading to Fading on/after since_date,
       DELETE today's depleted rows — get_active_themes() then returns the prior
       valid snapshot (DISTINCT ON name ORDER BY theme_date DESC).
    3. Retire-only rows: also delete Retired rows from since_date.

    Returns {"themes_restored": N, "exclusions_cleared": M}.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Step 1: clear auto-generated exclusions
        excl_result = await conn.execute("""
            DELETE FROM mi_theme_exclusions
            WHERE reason LIKE '%description inconsistent%'
        """)
        exclusions_cleared = int(excl_result.split()[-1])

        # Step 2: find themes that collapsed (Fading) since since_date
        # but had a non-Fading snapshot before that — one-night drop is suspicious
        collapsed = await conn.fetch("""
            SELECT DISTINCT t.name
            FROM mi_themes t
            WHERE t.theme_date >= $1
              AND t.stage = 'Fading'
              AND EXISTS (
                  SELECT 1 FROM mi_themes p
                  WHERE p.name = t.name
                    AND p.theme_date < $1
                    AND p.stage NOT IN ('Fading', 'Retired')
              )
        """, since_date)

        retired = await conn.fetch("""
            SELECT DISTINCT name FROM mi_themes
            WHERE stage = 'Retired' AND theme_date >= $1
              AND name IN (
                  SELECT DISTINCT name FROM mi_themes
                  WHERE stage != 'Retired' AND theme_date < $1
              )
        """, since_date)

        names_to_restore = list({r["name"] for r in collapsed} | {r["name"] for r in retired})
        if not names_to_restore:
            logger.info(f"restore_recently_retired_themes: cleared {exclusions_cleared} exclusions, no collapsed themes found")
            return {"themes_restored": 0, "exclusions_cleared": exclusions_cleared}

        # Delete the damaged rows — exposes the prior valid snapshot
        result = await conn.execute("""
            DELETE FROM mi_themes
            WHERE theme_date >= $1
              AND name = ANY($2)
        """, since_date, names_to_restore)
        themes_restored = int(result.split()[-1])
        logger.info(
            f"restore_recently_retired_themes: cleared {exclusions_cleared} auto-exclusions, "
            f"deleted {themes_restored} damaged rows for {len(names_to_restore)} themes: {names_to_restore}"
        )
        return {"themes_restored": len(names_to_restore), "exclusions_cleared": exclusions_cleared}


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
    If theme already exists today (by exact name), merges tickers.
    Also checks for similar existing theme names (case-insensitive)
    and merges into the existing one to prevent near-duplicates.
    """
    pool = await get_pool()
    tickers_upper = [t.upper() for t in tickers]
    async with pool.acquire() as conn:
        # Check for exact match first
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
            return

        # Check for case-insensitive similar name (prevent "AI Memory" vs "AI memory")
        similar = await conn.fetchrow(
            "SELECT id, tickers FROM mi_themes WHERE LOWER(name) = LOWER($1) AND theme_date = $2",
            name, today,
        )
        if similar:
            merged = list(set(list(similar["tickers"] or [])) | set(tickers_upper))
            await conn.execute(
                "UPDATE mi_themes SET tickers = $1, description = COALESCE(NULLIF($2,''), description) WHERE id = $3",
                merged, thesis, similar["id"],
            )
            return

        await conn.execute("""
            INSERT INTO mi_themes (theme_date, name, stage, score, description, tickers)
            VALUES ($1, $2, 'Nascent', 0, $3, $4)
        """, today, name, thesis, tickers_upper)


async def get_ma_pullbacks(
    d: "str | date",
    tickers: list[str] | None = None,
    rs_min: float = 50.0,
    pct_tolerance: float = 4.0,
    min_adv: float = 500_000,
    min_price: float = 10.0,
) -> list[dict[str, Any]]:
    """
    Return stocks near their 10/20/50 SMAs (pulling back to key MAs).

    A stock is "near" an MA if:
      - It was above the MA (uptrend)
      - Current price is within pct_tolerance% of the MA

    Applies same liquidity/quality filters as RS leaders (ADV, price, skip list, sector).
    """
    from agents.market_intelligence.constants import SKIP_TICKERS_LIST, is_sector_filtered
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
                AND close IS NOT NULL AND close >= $3
                AND ticker != ALL($4)
                AND (adv_20 IS NULL OR adv_20 >= $5)
                ORDER BY rs_composite DESC
            """, score_date, rs_min, min_price, SKIP_TICKERS_LIST, min_adv)

    results = []
    tol = pct_tolerance / 100.0

    for row in rows:
        r = dict(row)
        close = r.get("close")
        if not close:
            continue

        if is_sector_filtered(r.get("sector"), close):
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
    from agents.market_intelligence.collector import et_today
    pool = await get_pool()
    cutoff = et_today() - timedelta(days=7)
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
    from agents.market_intelligence.collector import et_today
    pool = await get_pool()
    cutoff = et_today() - timedelta(days=days)
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
    - mi_ep_alerts:    90 days  (EP alert history for outcome tracking)
    - mi_stock_scores: 365 days (RS history — needed for historical queries + outcome tracking)
    - mi_themes:       365 days (theme lifecycle history — stage transitions over months)
    - mi_market_regime: kept forever (1 row/day, ~260 rows/year — negligible)
    - mi_tracked_stocks: kept forever (state table, not time-series)

    Returns dict with row counts deleted per table.
    """
    from agents.market_intelligence.collector import et_today
    pool = await get_pool()
    today = et_today()
    deleted: dict[str, int] = {}

    async with pool.acquire() as conn:
        cutoffs = {
            "mi_ep_alerts":    today - timedelta(days=90),
            "mi_stock_scores": today - timedelta(days=365),
            "mi_themes":       today - timedelta(days=365),
            "mi_fundamental_flags": today - timedelta(days=30),
            "mi_daily_closes": today - timedelta(days=400),  # 13M — feeds 12M RS lookback
            "mi_data_quality": today - timedelta(days=90),
            "mi_signal_outcomes": today - timedelta(days=365),
            "mi_intraday_bars": today - timedelta(days=120),
        }
        date_cols = {
            "mi_ep_alerts":    "alert_date",
            "mi_stock_scores": "score_date",
            "mi_themes":       "theme_date",
            "mi_fundamental_flags": "flag_date",
            "mi_daily_closes": "trade_date",
            "mi_data_quality": "run_date",
            "mi_signal_outcomes": "signal_date",
            "mi_intraday_bars": "bar_time",
        }
        _valid_tables = frozenset(cutoffs.keys())
        _valid_cols = frozenset(date_cols.values())
        for table, cutoff in cutoffs.items():
            col = date_cols[table]
            if table not in _valid_tables or col not in _valid_cols:
                raise ValueError(f"Unexpected table/col in purge: {table}/{col}")
            result = await conn.execute(
                f"DELETE FROM {table} WHERE {col} < $1", cutoff  # noqa: S608 — identifiers validated above
            )
            # asyncpg returns "DELETE N" as a string
            count = int(result.split()[-1]) if result else 0
            deleted[table] = count
            if count:
                logger.info(f"Purged {count} rows from {table} (older than {cutoff})")

    return deleted


async def log_job_run(job_name: str) -> None:
    """Record that a scheduled job ran successfully today (ET date)."""
    from agents.market_intelligence.collector import et_today
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO mi_job_log (job_name, run_date, ran_at)
            VALUES ($1, $2, NOW())
            ON CONFLICT (job_name, run_date) DO UPDATE SET ran_at = NOW()
            """,
            job_name,
            et_today(),
        )


async def job_ran_today(job_name: str) -> bool:
    """Return True if this job already ran today (ET date)."""
    from agents.market_intelligence.collector import et_today
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT 1 FROM mi_job_log WHERE job_name = $1 AND run_date = $2",
            job_name,
            et_today(),
        )
        return row is not None


async def get_pipeline_status() -> dict[str, Any]:
    """Return market pipeline health: job run times, data freshness, regime, theme count."""
    from agents.market_intelligence.collector import et_today
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Most recent run per job (within last 7 days)
        job_rows = await conn.fetch("""
            SELECT DISTINCT ON (job_name) job_name, ran_at, run_date
            FROM mi_job_log
            WHERE run_date >= CURRENT_DATE - INTERVAL '7 days'
            ORDER BY job_name, ran_at DESC
        """)
        jobs = {
            row["job_name"]: {
                "last_ran": row["ran_at"].isoformat(),
                "ran_today": row["run_date"] == et_today(),
            }
            for row in job_rows
        }

        # Data freshness
        score_row = await conn.fetchrow("""
            SELECT score_date, COUNT(DISTINCT ticker) AS stock_count
            FROM mi_stock_scores
            WHERE score_date = (SELECT MAX(score_date) FROM mi_stock_scores)
            GROUP BY score_date
        """)

        # Active theme count (not retired)
        theme_count = await conn.fetchval(
            "SELECT COUNT(*) FROM mi_themes WHERE stage != 'Retired'"
        ) or 0

        # Current regime
        regime_row = await conn.fetchrow(
            "SELECT regime FROM mi_market_regime ORDER BY regime_date DESC LIMIT 1"
        )

        return {
            "jobs": jobs,
            "data": {
                "latest_score_date": score_row["score_date"].isoformat() if score_row else None,
                "stocks_scored": int(score_row["stock_count"]) if score_row else 0,
                "active_themes": int(theme_count),
                "regime": regime_row["regime"] if regime_row else "Unknown",
            },
        }


async def get_overnight_watchlist(active_only: bool = True) -> list[dict[str, Any]]:
    """Return the overnight watchlist instruments."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        where = "WHERE active = TRUE" if active_only else ""
        rows = await conn.fetch(
            f"SELECT * FROM mi_overnight_watchlist {where} ORDER BY category, symbol"
        )
        return [dict(r) for r in rows]


async def upsert_watchlist_item(
    symbol: str, display_name: str, threshold_pct: float,
    category: str = "other", notes: str = "",
) -> None:
    """Add or update an instrument on the overnight watchlist."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO mi_overnight_watchlist (symbol, display_name, threshold_pct, category, notes, active)
            VALUES ($1, $2, $3, $4, $5, TRUE)
            ON CONFLICT (symbol) DO UPDATE SET
                display_name = $2, threshold_pct = $3, category = $4, notes = $5, active = TRUE
        """, symbol, display_name, threshold_pct, category, notes)


async def deactivate_watchlist_item(symbol: str) -> bool:
    """Deactivate a watchlist instrument. Returns True if found."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE mi_overnight_watchlist SET active = FALSE WHERE symbol = $1", symbol
        )
        return result != "UPDATE 0"


async def get_adv_map(d: "str | date") -> dict[str, float]:
    """Get stored ADV (avg daily volume) for all tickers as of a date."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT ticker, adv_20 FROM mi_stock_scores WHERE score_date = $1",
            _to_date(d),
        )
        return {r["ticker"]: r["adv_20"] for r in rows if r["adv_20"]}


# ── Daily closes (full universe) ───────────────────────────────────────────────


async def ingest_daily_closes(trade_date: date, bars: dict[str, dict]) -> int:
    """
    Store daily closes + volumes from grouped daily data.
    bars: {ticker: {T, o, h, l, c, v, ...}} from Polygon grouped daily.
    Returns number of rows inserted.
    """
    if not bars:
        return 0
    pool = await get_pool()
    records = [
        (trade_date, ticker, b["c"], int(b.get("v", 0)))
        for ticker, b in bars.items()
        if "c" in b and len(ticker) <= 5 and "." not in ticker
    ]
    async with pool.acquire() as conn:
        await conn.executemany("""
            INSERT INTO mi_daily_closes (trade_date, ticker, close, volume)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (trade_date, ticker) DO NOTHING
        """, records)
    return len(records)


async def get_daily_closes_all(from_date: date, to_date: date) -> dict[str, dict[str, float]]:
    """
    Fetch daily closes in a date range, filtered to tradeable stocks.
    Only includes stocks with close >= $5 on the most recent date.
    Returns: {ticker: {date_str: close}}
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        # First get tickers that had a close >= $5 on the latest available date
        # This filters out penny stocks and reduces memory from ~11K to ~5K tickers
        latest_date = await conn.fetchval(
            "SELECT MAX(trade_date) FROM mi_daily_closes WHERE trade_date <= $1", to_date
        )
        if not latest_date:
            return {}
        qualifying = await conn.fetch("""
            SELECT ticker FROM mi_daily_closes
            WHERE trade_date = $1 AND close >= 5.0
              AND LENGTH(ticker) <= 5
        """, latest_date)
        tickers = {r["ticker"] for r in qualifying}

        if not tickers:
            return {}

        rows = await conn.fetch("""
            SELECT ticker, trade_date, close
            FROM mi_daily_closes
            WHERE trade_date >= $1 AND trade_date <= $2
              AND ticker = ANY($3)
            ORDER BY ticker, trade_date
        """, from_date, to_date, list(tickers))

    result: dict[str, dict[str, float]] = {}
    for r in rows:
        ticker = r["ticker"]
        if ticker not in result:
            result[ticker] = {}
        result[ticker][r["trade_date"].strftime("%Y-%m-%d")] = r["close"]
    return result


async def get_daily_closes_count(trade_date: date) -> int:
    """Check how many daily closes exist for a given date."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT COUNT(*) FROM mi_daily_closes WHERE trade_date = $1", trade_date
        )


async def get_adv_from_daily_closes(trade_date: date, days: int = 20) -> dict[str, float]:
    """
    Compute 20-day median daily volume from mi_daily_closes for all tickers.
    Uses median (PERCENTILE_CONT) instead of mean — immune to volume spikes.
    Calendar lookback: days * 1.5 to cover weekends/holidays for N trading days.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT ticker,
                   PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY volume) as adv
            FROM mi_daily_closes
            WHERE trade_date <= $1
              AND trade_date >= $1 - (($2 * 1.5)::int * INTERVAL '1 day')
              AND volume > 0
            GROUP BY ticker
            HAVING COUNT(*) >= 10
        """, trade_date, days)
    return {r["ticker"]: float(r["adv"]) for r in rows}


# ── Fundamental flags ─────────────────────────────────────────────────────────


async def upsert_fundamental_flags_batch(records: list[dict[str, Any]]) -> None:
    """Batch upsert fundamental flags — called during nightly data pull."""
    if not records:
        return
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.executemany("""
            INSERT INTO mi_fundamental_flags
                (ticker, flag_date, eps_yoy_latest, eps_yoy_prior,
                 eps_accelerating, eps_streak_25pct, sales_yoy_latest,
                 next_earnings_date)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
            ON CONFLICT (ticker, flag_date) DO UPDATE SET
                eps_yoy_latest=EXCLUDED.eps_yoy_latest,
                eps_yoy_prior=EXCLUDED.eps_yoy_prior,
                eps_accelerating=EXCLUDED.eps_accelerating,
                eps_streak_25pct=EXCLUDED.eps_streak_25pct,
                sales_yoy_latest=EXCLUDED.sales_yoy_latest,
                next_earnings_date=EXCLUDED.next_earnings_date
        """, [
            (
                r["ticker"], r["flag_date"], r.get("eps_yoy_latest"),
                r.get("eps_yoy_prior"), r.get("eps_accelerating"),
                r.get("eps_streak_25pct", 0), r.get("sales_yoy_latest"),
                r.get("next_earnings_date"),
            )
            for r in records
        ])


async def get_fundamental_flags(d: "str | date") -> dict[str, dict[str, Any]]:
    """Get cached fundamental flags for all tickers, keyed by ticker."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        score_date = await _resolve_score_date(conn, _to_date(d))
        rows = await conn.fetch(
            "SELECT * FROM mi_fundamental_flags WHERE flag_date = $1",
            score_date,
        )
        return {r["ticker"]: dict(r) for r in rows}


# ── Ticker description overrides ──────────────────────────────────────────────


async def upsert_ticker_override(
    ticker: str, description: str, notes: str | None = None,
) -> None:
    """Store a description override for a ticker. Overwrites static universe.py."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO mi_ticker_overrides (ticker, description, notes, updated_at)
            VALUES ($1, $2, $3, NOW())
            ON CONFLICT (ticker) DO UPDATE SET
                description = EXCLUDED.description,
                notes = EXCLUDED.notes,
                updated_at = NOW()
        """, ticker.upper(), description, notes)


async def upsert_ticker_overrides_batch(
    overrides: dict[str, str],
) -> int:
    """Batch-upsert description overrides. Returns count of rows upserted."""
    if not overrides:
        return 0
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.executemany("""
            INSERT INTO mi_ticker_overrides (ticker, description, updated_at)
            VALUES ($1, $2, NOW())
            ON CONFLICT (ticker) DO UPDATE SET
                description = EXCLUDED.description,
                updated_at = NOW()
        """, [(tk.upper(), desc) for tk, desc in overrides.items()])
    return len(overrides)


async def get_ticker_overrides() -> dict[str, str]:
    """Get all ticker description overrides, keyed by ticker.
    Only returns rows with non-null, non-empty descriptions to avoid
    overwriting the static TICKER_DESC baseline with NULL values from
    sector-only rows (created by upsert_ticker_sectors_batch)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT ticker, description FROM mi_ticker_overrides "
            "WHERE description IS NOT NULL AND description != ''"
        )
        return {r["ticker"]: r["description"] for r in rows}


async def upsert_ticker_sectors_batch(sectors: dict[str, dict]) -> int:
    """
    Batch-upsert sector/industry for tickers. Does NOT overwrite description.
    sectors: {ticker: {"sector": "Healthcare", "industry": "Biotechnology"}}
    Returns count upserted.
    """
    if not sectors:
        return 0
    pool = await get_pool()
    rows = [
        (tk.upper(), v.get("sector", ""), v.get("industry", ""))
        for tk, v in sectors.items()
    ]
    async with pool.acquire() as conn:
        await conn.executemany("""
            INSERT INTO mi_ticker_overrides (ticker, sector, industry, updated_at)
            VALUES ($1, $2, $3, NOW())
            ON CONFLICT (ticker) DO UPDATE SET
                sector   = EXCLUDED.sector,
                industry = EXCLUDED.industry,
                updated_at = NOW()
        """, rows)
    return len(rows)


async def get_ticker_sector(ticker: str) -> dict:
    """Return cached {sector, industry} for a ticker, or {} if not cached."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT sector, industry FROM mi_ticker_overrides WHERE ticker = $1",
            ticker.upper(),
        )
    if not row or not row["sector"]:
        return {}
    return {"sector": row["sector"] or "", "industry": row["industry"] or ""}


async def get_sector_rs_rank(
    ticker: str,
    industry: str,
    score_date,
    sector: str | None = None,
    min_peers: int = 10,
    ticker_rs: float | None = None,
) -> dict:
    """
    Compute a ticker's RS percentile within its industry peer group.

    ticker_rs: the ticker's already-known RS composite score. If provided,
    avoids a DB join that fails for on-demand-scored tickers not in mi_stock_scores.

    Returns {rank, total, pct, label, fallback} or {} if insufficient peers.
    Falls back to sector-level if industry has < min_peers tracked stocks.
    """
    pool = await get_pool()
    ticker_up = ticker.upper()

    async def _query(group_col: str, group_val: str) -> dict | None:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT s.ticker, s.rs_composite
                FROM mi_stock_scores s
                JOIN mi_ticker_overrides o ON s.ticker = o.ticker
                WHERE s.score_date = $1
                  AND o.{group_col} = $2
                  AND s.rs_composite IS NOT NULL
                """,
                score_date,
                group_val,
            )
        if not rows or len(rows) < min_peers:
            return None
        composites = {r["ticker"]: r["rs_composite"] for r in rows}
        # Use caller-supplied RS if available (on-demand scored tickers not in nightly table)
        known_rs = ticker_rs if ticker_rs is not None else composites.get(ticker_up)
        if known_rs is None:
            return None
        total = len(composites)
        rank = sum(1 for rs in composites.values() if rs > known_rs) + 1
        pct = round((total - rank + 1) / total * 100)
        return {"rank": rank, "total": total, "pct": pct}

    result = await _query("industry", industry)
    if result:
        return {**result, "label": industry, "fallback": False}

    # Fall back to sector if industry bucket is too thin
    if sector and sector != industry:
        result = await _query("sector", sector)
        if result:
            return {**result, "label": sector, "fallback": True}

    return {}


# ── Security types ───────────────────────────────────────────────────────────


async def upsert_security_types_batch(types: dict[str, dict]) -> int:
    """Batch-upsert security types from Polygon reference data.
    types: {ticker: {"type": "CS"|"ETF"|..., "exchange": "XNYS"|...}}
    """
    if not types:
        return 0
    pool = await get_pool()
    rows = [(tk, info["type"], info.get("exchange", ""))
            for tk, info in types.items() if info.get("type")]
    async with pool.acquire() as conn:
        await conn.executemany("""
            INSERT INTO mi_security_types (ticker, security_type, exchange, updated_at)
            VALUES ($1, $2, $3, NOW())
            ON CONFLICT (ticker) DO UPDATE SET
                security_type = EXCLUDED.security_type,
                exchange = EXCLUDED.exchange,
                updated_at = NOW()
        """, rows)
    return len(rows)


async def get_common_stock_tickers() -> set[str]:
    """Return set of tickers classified as Common Stock (CS, ADRC).
    Used to filter out ETFs, warrants, units, SPACs, etc."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT ticker FROM mi_security_types WHERE security_type = ANY($1)",
            list(COMMON_STOCK_TYPES),
        )
        return {r["ticker"] for r in rows}


async def get_security_types_count() -> int:
    """Return count of security types stored."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM mi_security_types") or 0


# ── Data quality ─────────────────────────────────────────────────────────────


async def upsert_data_quality(record: dict[str, Any]) -> None:
    """Insert or update a data quality check result."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO mi_data_quality (run_date, step, metric, value, expected, passed)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (run_date, step, metric) DO UPDATE SET
                value=EXCLUDED.value, expected=EXCLUDED.expected, passed=EXCLUDED.passed
        """,
            record["run_date"], record["step"], record["metric"],
            record["value"], record["expected"], record["passed"],
        )


async def get_data_quality_expected(
    step: str, metric: str, lookback: int = 5,
) -> Optional[float]:
    """Average value of last N successful (passed=TRUE) quality checks for a step/metric."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT AVG(value) AS avg_val
            FROM (
                SELECT value FROM mi_data_quality
                WHERE step = $1 AND metric = $2 AND passed = TRUE
                ORDER BY run_date DESC
                LIMIT $3
            ) sub
        """, step, metric, lookback)
        return float(row["avg_val"]) if row and row["avg_val"] is not None else None


async def get_data_quality_issues(run_date: date) -> list[dict[str, Any]]:
    """Return rows where passed=FALSE for a given date."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM mi_data_quality WHERE run_date = $1 AND passed = FALSE",
            run_date,
        )
        return [dict(r) for r in rows]


# ── Signal outcomes ──────────────────────────────────────────────────────────


async def upsert_signal_outcome(record: dict[str, Any]) -> None:
    """Insert or update a signal outcome tracking row."""
    import json
    pool = await get_pool()
    detail = record.get("detail")
    detail_json = json.dumps(detail) if detail else None
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO mi_signal_outcomes
                (signal_type, signal_date, identifier, detail,
                 fwd_1d_pct, fwd_1w_pct, fwd_1m_pct, fwd_3m_pct,
                 spy_fwd_1m_pct, spy_fwd_3m_pct)
            VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7, $8, $9, $10)
            ON CONFLICT (signal_type, signal_date, identifier) DO UPDATE SET
                detail=EXCLUDED.detail,
                fwd_1d_pct=COALESCE(EXCLUDED.fwd_1d_pct, mi_signal_outcomes.fwd_1d_pct),
                fwd_1w_pct=COALESCE(EXCLUDED.fwd_1w_pct, mi_signal_outcomes.fwd_1w_pct),
                fwd_1m_pct=COALESCE(EXCLUDED.fwd_1m_pct, mi_signal_outcomes.fwd_1m_pct),
                fwd_3m_pct=COALESCE(EXCLUDED.fwd_3m_pct, mi_signal_outcomes.fwd_3m_pct),
                spy_fwd_1m_pct=COALESCE(EXCLUDED.spy_fwd_1m_pct, mi_signal_outcomes.spy_fwd_1m_pct),
                spy_fwd_3m_pct=COALESCE(EXCLUDED.spy_fwd_3m_pct, mi_signal_outcomes.spy_fwd_3m_pct),
                computed_at=NOW()
        """,
            record["signal_type"], record["signal_date"], record["identifier"],
            detail_json,
            record.get("fwd_1d_pct"), record.get("fwd_1w_pct"),
            record.get("fwd_1m_pct"), record.get("fwd_3m_pct"),
            record.get("spy_fwd_1m_pct"), record.get("spy_fwd_3m_pct"),
        )


async def get_signal_outcomes(
    signal_type: str,
    from_date: "date | None" = None,
    to_date: "date | None" = None,
) -> list[dict[str, Any]]:
    """Query signal outcomes for reporting."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        if from_date and to_date:
            rows = await conn.fetch("""
                SELECT * FROM mi_signal_outcomes
                WHERE signal_type = $1 AND signal_date >= $2 AND signal_date <= $3
                ORDER BY signal_date DESC
            """, signal_type, from_date, to_date)
        elif from_date:
            rows = await conn.fetch("""
                SELECT * FROM mi_signal_outcomes
                WHERE signal_type = $1 AND signal_date >= $2
                ORDER BY signal_date DESC
            """, signal_type, from_date)
        else:
            rows = await conn.fetch("""
                SELECT * FROM mi_signal_outcomes
                WHERE signal_type = $1
                ORDER BY signal_date DESC
                LIMIT 200
            """, signal_type)
        return [dict(r) for r in rows]


async def get_prior_consec_breakdown_days(before_date: date) -> int:
    """Get the most recent consec_breakdown_days value before a given date."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT consec_breakdown_days FROM mi_market_regime
            WHERE regime_date < $1 AND consec_breakdown_days IS NOT NULL
            ORDER BY regime_date DESC LIMIT 1
        """, before_date)
        return row["consec_breakdown_days"] if row else 0


# ── Live trading CRUD ────────────────────────────────────────────────────────


async def get_open_live_trades() -> list[dict[str, Any]]:
    """Get all open (filled) live trades."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT * FROM mi_live_trades
            WHERE status = 'filled' AND remaining_shares > 0
            ORDER BY alert_date ASC
        """)
    return [dict(r) for r in rows]


async def get_live_trading_summary() -> dict[str, Any]:
    """Get summary of all live trades for reporting."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        stats = await conn.fetchrow("""
            SELECT
                COUNT(*) FILTER (WHERE status NOT IN ('skipped', 'cancelled')) as total_trades,
                COUNT(*) FILTER (WHERE status = 'filled') as open_positions,
                COUNT(*) FILTER (WHERE status = 'closed' AND total_pnl > 0) as winners,
                COUNT(*) FILTER (WHERE status = 'closed' AND total_pnl <= 0) as losers,
                COALESCE(SUM(total_pnl) FILTER (WHERE status = 'closed'), 0) as realized_pnl,
                COUNT(*) FILTER (WHERE status IN ('skipped', 'cancelled')) as skipped
            FROM mi_live_trades
        """)

        open_positions = await conn.fetch("""
            SELECT ticker, alert_date, ep_score, remaining_shares,
                   stop_price, entry_price, total_pnl, hold_days
            FROM mi_live_trades WHERE status = 'filled'
            ORDER BY alert_date ASC
        """)

    total = stats["total_trades"] or 0
    closed = (stats["winners"] or 0) + (stats["losers"] or 0)
    win_rate = (stats["winners"] / closed * 100) if closed > 0 else 0

    return {
        "total_trades": total,
        "open_positions": stats["open_positions"] or 0,
        "closed_trades": closed,
        "winners": stats["winners"] or 0,
        "losers": stats["losers"] or 0,
        "win_rate": win_rate,
        "realized_pnl": float(stats["realized_pnl"] or 0),
        "skipped": stats["skipped"] or 0,
        "open_details": [dict(r) for r in open_positions],
    }


# ── Theme exclusions ──────────────────────────────────────────────────────────

async def add_theme_exclusion(ticker: str, theme_name: str, reason: str = "") -> None:
    """
    Permanently exclude a ticker from a specific theme.
    Once excluded, the ticker will never be assigned to that theme by the engine,
    regardless of RS score or Haiku validation decisions.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO mi_theme_exclusions (ticker, theme_name, reason)
            VALUES ($1, $2, $3)
            ON CONFLICT (ticker, theme_name) DO UPDATE SET
                reason = EXCLUDED.reason,
                excluded_at = NOW()
        """, ticker.upper(), theme_name, reason)
    logger.info(f"Theme exclusion added: {ticker} excluded from '{theme_name}'")
    await log_audit_event(
        "theme_excluded",
        summary=f"{ticker.upper()} excluded from '{theme_name}'",
        detail=reason,
    )


async def get_all_theme_exclusions() -> dict[str, set[str]]:
    """
    Load all theme exclusions.
    Returns dict mapping theme_name → set of excluded tickers.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT ticker, theme_name FROM mi_theme_exclusions")
    result: dict[str, set[str]] = {}
    for row in rows:
        theme = row["theme_name"]
        if theme not in result:
            result[theme] = set()
        result[theme].add(row["ticker"])
    return result


async def remove_theme_exclusion(ticker: str, theme_name: str) -> bool:
    """Remove a previously set exclusion. Returns True if a row was deleted."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM mi_theme_exclusions WHERE ticker = $1 AND theme_name = $2",
            ticker.upper(), theme_name,
        )
    deleted = result.split()[-1] != "0"
    if deleted:
        logger.info(f"Theme exclusion removed: {ticker} can now re-enter '{theme_name}'")
    return deleted


async def list_theme_exclusions() -> list[dict[str, Any]]:
    """Return all exclusions as a list of dicts (for display)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT ticker, theme_name, reason, excluded_at
            FROM mi_theme_exclusions
            ORDER BY excluded_at DESC
        """)
    return [dict(r) for r in rows]


# ── Audit log ─────────────────────────────────────────────────────────────────

async def log_audit_event(event_type: str, summary: str, detail: str = "") -> None:
    """
    Write a critical event to the audit log. Never raises — safe to call from anywhere.
    event_type: 'advisor_call' | 'theme_discovered' | 'theme_retired' |
                'stage_change' | 'theme_excluded' | 'ep_alert'
    """
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO mi_audit_log (event_type, summary, detail) VALUES ($1, $2, $3)",
                event_type, summary[:500], detail[:2000],
            )
    except Exception as e:
        logger.warning(f"audit log write failed ({event_type}): {e}")


async def get_audit_log(
    limit: int = 30,
    event_type: str | None = None,
    since_hours: int = 48,
) -> list[dict[str, Any]]:
    """Fetch recent audit log entries, newest first."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        if event_type:
            rows = await conn.fetch("""
                SELECT id, created_at, event_type, summary, detail
                FROM mi_audit_log
                WHERE event_type = $1
                  AND created_at >= NOW() - ($2 || ' hours')::INTERVAL
                ORDER BY created_at DESC
                LIMIT $3
            """, event_type, str(since_hours), limit)
        else:
            rows = await conn.fetch("""
                SELECT id, created_at, event_type, summary, detail
                FROM mi_audit_log
                WHERE created_at >= NOW() - ($1 || ' hours')::INTERVAL
                ORDER BY created_at DESC
                LIMIT $2
            """, str(since_hours), limit)
    return [dict(r) for r in rows]
