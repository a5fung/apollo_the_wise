"""
Database layer for Market Intelligence Agent.
Uses the same Postgres instance as Apollo, separate tables prefixed with mi_.
"""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from typing import Any, Optional

import asyncpg

from shared.secrets import get_secrets

logger = logging.getLogger(__name__)

# Security types considered "common stock" for RS scoring, breadth, and themes.
# CS = Common Stock, ADRC = ADR Common (foreign stocks traded on US exchanges).
COMMON_STOCK_TYPES = ('CS', 'ADRC')

# Shared CTE block for 9M-context EOD selection queries. Both
# get_eod_9m_sugar_babies (close ≥ 75% range) and get_eod_9m_wick_candidates
# (close ∈ [0.50, 0.75)) build their context (ADV, prev_close, prior closes,
# SMAs, slope, prior_sessions) from this same CTE so the two cohorts are
# defined off identical going-in metrics. Parameter $1 = trade_date.
_NINEM_CONTEXT_CTE = """
WITH adv AS (
    SELECT ticker,
           PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY volume) AS adv_20
    FROM mi_daily_closes
    WHERE trade_date < $1
      AND trade_date >= $1 - INTERVAL '30 days'
      AND volume > 0
    GROUP BY ticker
    HAVING COUNT(*) >= 10
),
ranked AS (
    SELECT ticker, close, trade_date,
           ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY trade_date DESC) AS rn
    FROM mi_daily_closes
    WHERE trade_date < $1
      AND trade_date >= $1 - INTERVAL '90 days'
),
ctx AS (
    SELECT ticker,
           COUNT(*) AS prior_sessions,
           MAX(close) FILTER (WHERE rn = 1)  AS prev_close,
           MAX(close) FILTER (WHERE rn = 6)  AS close_5d_ago,
           MAX(close) FILTER (WHERE rn = 21) AS close_20d_ago,
           AVG(close) FILTER (WHERE rn <= 10) AS sma_10,
           AVG(close) FILTER (WHERE rn <= 50) AS sma_50,
           CASE WHEN COUNT(*) >= 55
                THEN AVG(close) FILTER (WHERE rn BETWEEN 6 AND 55)
                ELSE NULL END AS sma_50_5d_ago
    FROM ranked
    GROUP BY ticker
    HAVING COUNT(*) >= 10
)
"""

_pool: Optional[asyncpg.Pool] = None


def _json_encoder(value):
    import json
    return json.dumps(value)


def _json_decoder(value):
    import json
    return json.loads(value)


def _jsonb_param(value):
    """Prepare a dict for a jsonb column written through the registered jsonb codec.

    The codec's encoder (_json_encoder) is plain json.dumps and runs AUTOMATICALLY
    on every jsonb param, so a caller must NOT pre-json.dumps() — that double-encodes
    (the value lands as jsonb_typeof='string': "{\\"k\\":...}"). That was the
    #177/#179 mi_orb_extension_shadow.state bug. Round-tripping through
    json.dumps(default=str)+loads returns a plain, fully JSON-serializable dict
    (datetimes→str, which the bare codec can't do) that the codec then encodes
    EXACTLY ONCE. Use this for any jsonb dict that may contain dates.
    """
    import json
    return json.loads(json.dumps(value or {}, default=str))


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


async def _seed_strategies_registry(conn) -> None:
    """Insert one row per strategy if not already present.

    Re-runs are safe — `ON CONFLICT (strategy_id) DO NOTHING`. To change a
    strategy's phase or thresholds after seed, edit `mi_strategies` directly
    or via `/strategy <id> {enable|disable|promote|demote}`.
    """
    import json as _json

    seeds = [
        {
            "strategy_id": "magna53",
            "name": "MAGNA53 EP",
            "family": "orb_long",
            # 2026-05-13 incident: ALL trades failed because phase='live'
            # routed through the LIVE TradingClient even with ENABLE_LIVE_MODE=false
            # (live env vars unset → KeyError). Pre-dual-account, phase='live'
            # meant "submit to the single Alpaca account configured via
            # ALPACA_PAPER env var" — implicitly paper. Post-dual-account
            # (#66, 2026-05-10) phase='live' literally means the LIVE Alpaca
            # account. New seed default is 'paper'; promotion to 'live'
            # happens explicitly via /strategy or DB update, gated on the
            # cutover composite gate (#64).
            "phase": "paper",
            "signal_type": "magna53",
            "outcomes_table": "mi_live_trades",
            "promotion_model": "unpaired_r",
            "promotion_thresholds": {
                "shadow_to_paper": {
                    "min_closed": 30, "min_median_r": 0.0,
                    "max_drawdown_pct": 0.30,
                },
                "paper_to_live": {
                    "min_closed": 30, "min_median_r": 0.5,
                    "min_win_rate": 0.40, "max_drawdown_dollars": 5000,
                },
            },
        },
        {
            "strategy_id": "9m_day2",
            "name": "9M Day 2 ORB",
            "family": "orb_long",
            # Seed at 'paper' per 2026-05-13 incident — see magna53 comment above.
            "phase": "paper",
            "signal_type": "9m_day2",
            "outcomes_table": "mi_live_trades",
            "promotion_model": "unpaired_r",
            "promotion_thresholds": {
                "shadow_to_paper": {
                    "min_closed": 30, "min_median_r": 0.0,
                    "max_drawdown_pct": 0.30,
                },
                "paper_to_live": {
                    "min_closed": 30, "min_median_r": 0.5,
                    "min_win_rate": 0.40, "max_drawdown_dollars": 5000,
                },
            },
        },
        {
            "strategy_id": "shadow_orb_5m",
            "name": "Shadow ORB 5-min",
            "family": "orb_long",
            "phase": "shadow",
            "signal_type": "shadow_orb_5m",
            "outcomes_table": "mi_orb_shadow_trades",
            # 2026-05-10 (#57): switched paired_r → unpaired_r. The 5-min
            # shadow and 1-min live ORB cohorts diverge by design (different
            # bar-size-sensitive gates), so paired matching never converged
            # (10 days, 1 shadow closed vs 3 live closed, zero overlap).
            # unpaired_r evaluates 5-min on its own R-distribution — actually
            # informative. Per-strategy R-multiple is the methodology metric.
            "promotion_model": "unpaired_r",
            "promotion_thresholds": {
                "shadow_to_paper": {
                    "min_closed": 30,
                    "min_median_r": 0.0,
                    "max_drawdown_pct": 0.3,
                },
                "paper_to_live": {
                    "min_closed": 30,
                    "min_median_r": 0.5,
                    "min_win_rate": 0.30,
                    "max_drawdown_dollars": 5000,
                },
            },
        },
        {
            "strategy_id": "parabolic_short",
            "name": "Parabolic Short",
            "family": "short",
            "phase": "shadow",
            "signal_type": "parabolic_short",
            "outcomes_table": "mi_parabolic_candidates",
            "promotion_model": "telemetry_review",
            "promotion_thresholds": {
                "shadow_to_paper": {
                    "min_climax_alerts": 20,
                    "min_review_passed_pct": 0.60,
                    "min_forward_5d_neg_rate": 0.50,
                },
            },
        },
        {
            "strategy_id": "wick_fill",
            "name": "Wick-Fill (Negated Shooting Star)",
            "family": "orb_long",
            "phase": "shadow",
            "signal_type": "wick_fill",
            "outcomes_table": "mi_wick_candidates",
            "promotion_model": "telemetry_review",
            "promotion_thresholds": {
                "shadow_to_paper": {
                    "metric_key": "n_candidates",
                    "min_count": 30,
                    "min_fill_rate": 0.50,
                    "review_required": False,
                },
            },
        },
        {
            "strategy_id": "flag_continuation",
            "name": "Continuation Flag (post-runup tightening)",
            "family": "long_setup",
            "phase": "shadow",
            "signal_type": "flag_continuation",
            "outcomes_table": "mi_flag_candidates",
            "promotion_model": "telemetry_review",
            "promotion_thresholds": {
                "shadow_to_paper": {
                    "metric_key": "n_triggers",
                    "min_count": 30,
                    "min_fwd_5d_pos_rate": 0.50,
                    "review_required": False,
                },
            },
        },
        {
            "strategy_id": "fishhook_v3",
            "name": "Fishhook (Gap-Up Undercut & Reclaim)",
            "family": "long",
            "phase": "shadow",
            "signal_type": "fishhook_v3",
            "outcomes_table": "mi_fishhook_anchors",
            "promotion_model": "telemetry_review",
            "promotion_thresholds": {
                "shadow_to_paper": {
                    "metric_key": "n_settled",
                    "min_count": 60,
                    "min_median_r": 1.0,
                    "min_hit_rate": 0.13,
                    "review_required": False,
                },
            },
        },
    ]
    await conn.executemany(
        """
        INSERT INTO mi_strategies
            (strategy_id, name, family, phase, signal_type,
             outcomes_table, promotion_model, promotion_thresholds)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb)
        ON CONFLICT (strategy_id) DO NOTHING
        """,
        [
            (s["strategy_id"], s["name"], s["family"], s["phase"],
             s["signal_type"], s["outcomes_table"], s["promotion_model"],
             _json.dumps(s["promotion_thresholds"]))
            for s in seeds
        ],
    )


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
                gemini_validation TEXT,   -- MISNOMER (#186A): holds PERPLEXITY cross-validation
                                          -- (pplx_quality), NOT Gemini. Name kept for back-compat
                                          -- (live column with data); a rename is a deferred migration.
                confidence_multiplier FLOAT DEFAULT 1.0,
                vol_percentile FLOAT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            ALTER TABLE mi_ep_alerts ADD COLUMN IF NOT EXISTS vol_percentile FLOAT;
            ALTER TABLE mi_ep_alerts ADD COLUMN IF NOT EXISTS pm_rvol FLOAT;
            ALTER TABLE mi_ep_alerts ADD COLUMN IF NOT EXISTS pm_rvol_baseline_n INT;
            -- detected_at: actual moment the EP detector emitted the alert.
            -- Distinct from created_at so future migrations can backfill rows
            -- without poisoning the timeline (FLY/YSS migration artifact set
            -- created_at=2026-03-28 13:26 on every pre-2026-03-20 row).
            ALTER TABLE mi_ep_alerts ADD COLUMN IF NOT EXISTS detected_at TIMESTAMPTZ;

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

            -- Fresh earnings-catalyst structured metrics (2026-05-19).
            -- Populated by catalyst_metrics_extractor on every earnings-day
            -- HIGH alert with catalyst_quality in (strong, game_changer).
            -- Solves the yfinance-lag problem: yfinance quarterly_financials
            -- doesn't update for 24-72h post-announcement, so the gate read
            -- stale Q-1 data on catalyst-day EPs (AGYS 2026-05-19 trigger).
            -- Multi-source extraction (Polygon + FMP + Perplexity + Claude
            -- analysis) → Sonnet → structured JSON. Denormalized fields for
            -- gate query; raw_json for /why TICKER deep dive.
            CREATE TABLE IF NOT EXISTS mi_ep_catalyst_metrics (
                ticker TEXT NOT NULL,
                alert_date DATE NOT NULL,
                q_revenue_yoy_pct DOUBLE PRECISION,
                extraction_quality TEXT,
                raw_json JSONB NOT NULL,
                extracted_at TIMESTAMPTZ DEFAULT NOW(),
                PRIMARY KEY (ticker, alert_date)
            );
            CREATE INDEX IF NOT EXISTS idx_ep_catalyst_metrics_date
                ON mi_ep_catalyst_metrics(alert_date DESC);
            -- Carry-forward raw input persistence (2026-05-19 — see B6 plan).
            -- Per-source columns so we can SELECT raw_alpaca_news_json IS NOT NULL
            -- to track when each source started populating.
            ALTER TABLE mi_ep_catalyst_metrics
                ADD COLUMN IF NOT EXISTS raw_polygon_news_json JSONB;
            ALTER TABLE mi_ep_catalyst_metrics
                ADD COLUMN IF NOT EXISTS raw_alpaca_news_json JSONB;
            ALTER TABLE mi_ep_catalyst_metrics
                ADD COLUMN IF NOT EXISTS raw_fmp_news_json JSONB;
            ALTER TABLE mi_ep_catalyst_metrics
                ADD COLUMN IF NOT EXISTS raw_perplexity_text TEXT;
            ALTER TABLE mi_ep_catalyst_metrics
                ADD COLUMN IF NOT EXISTS raw_claude_analysis_text TEXT;

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
            ALTER TABLE mi_daily_closes ADD COLUMN IF NOT EXISTS open_price FLOAT;
            ALTER TABLE mi_daily_closes ADD COLUMN IF NOT EXISTS high_price FLOAT;
            ALTER TABLE mi_daily_closes ADD COLUMN IF NOT EXISTS low_price FLOAT;
            CREATE INDEX IF NOT EXISTS idx_daily_closes_ticker ON mi_daily_closes(ticker);

            CREATE TABLE IF NOT EXISTS mi_9m_ep_alerts (
                id SERIAL PRIMARY KEY,
                ticker TEXT NOT NULL,
                alert_date DATE NOT NULL,
                detection_time TIMESTAMPTZ NOT NULL,
                today_volume BIGINT NOT NULL,
                projected_vol BIGINT,
                current_price FLOAT NOT NULL,
                gap_pct FLOAT NOT NULL,
                is_anticipation BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE (ticker, alert_date)
            );
            CREATE INDEX IF NOT EXISTS idx_9m_ep_alerts_date ON mi_9m_ep_alerts(alert_date);

            -- Idempotent rename: mi_9m_sugar_babies → mi_9m_day2_candidates
            -- (#82, 2026-05-23). Original name was misleading per CLAUDE.md:
            -- this table holds single-day Day 2 ORB candidates (close > open
            -- + top 25% of range + net up ≥3%), DISTINCT from the persistent
            -- Pradeep Sugar Babies cohort in mi_sugar_babies_cohort. The
            -- ALTERs below are IF EXISTS so they no-op on fresh installs
            -- (where the CREATE IF NOT EXISTS below makes the new name
            -- directly); on existing prod they atomically rename the table,
            -- indexes, constraint, and sequence to the new identifiers.
            ALTER TABLE IF EXISTS mi_9m_sugar_babies RENAME TO mi_9m_day2_candidates;
            ALTER INDEX IF EXISTS idx_9m_sugar_babies_date RENAME TO idx_9m_day2_candidates_date;
            ALTER INDEX IF EXISTS mi_9m_sugar_babies_pkey RENAME TO mi_9m_day2_candidates_pkey;
            ALTER INDEX IF EXISTS mi_9m_sugar_babies_ticker_alert_date_key RENAME TO mi_9m_day2_candidates_ticker_alert_date_key;
            ALTER SEQUENCE IF EXISTS mi_9m_sugar_babies_id_seq RENAME TO mi_9m_day2_candidates_id_seq;

            CREATE TABLE IF NOT EXISTS mi_9m_day2_candidates (
                id SERIAL PRIMARY KEY,
                ticker TEXT NOT NULL,
                alert_date DATE NOT NULL,
                open_price FLOAT NOT NULL,
                close_price FLOAT NOT NULL,
                high_price FLOAT NOT NULL,
                low_price FLOAT NOT NULL,
                volume BIGINT NOT NULL,
                close_in_range_pct FLOAT NOT NULL,
                day2_status TEXT NOT NULL DEFAULT 'pending',
                created_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE (ticker, alert_date)
            );
            CREATE INDEX IF NOT EXISTS idx_9m_day2_candidates_date ON mi_9m_day2_candidates(alert_date);
            -- Going-in shape: captured at EOD sweep so weekly review can slice
            -- outcomes by setup geometry (quiet breakout vs pullback reversal
            -- vs falling knife vs extended continuation). Bucketing is derived
            -- at query time from raw metrics so definitions can evolve.
            ALTER TABLE mi_9m_day2_candidates ADD COLUMN IF NOT EXISTS prev_5d_pct FLOAT;
            ALTER TABLE mi_9m_day2_candidates ADD COLUMN IF NOT EXISTS prev_20d_pct FLOAT;
            ALTER TABLE mi_9m_day2_candidates ADD COLUMN IF NOT EXISTS prev_vs_sma10 FLOAT;
            ALTER TABLE mi_9m_day2_candidates ADD COLUMN IF NOT EXISTS prev_vs_sma50 FLOAT;
            ALTER TABLE mi_9m_day2_candidates ADD COLUMN IF NOT EXISTS sma50_slope_pct FLOAT;
            ALTER TABLE mi_9m_day2_candidates ADD COLUMN IF NOT EXISTS prior_sessions INT;

            -- Persistent Sugar Babies cohort (Pradeep-class watchlist):
            -- tickers that printed 9M+ EOD volume ≥3 times in trailing 180d.
            -- Different concept from mi_9m_day2_candidates (single-day Day 2
            -- candidate). Pure observability — no trade impact.
            CREATE TABLE IF NOT EXISTS mi_sugar_babies_cohort (
                id SERIAL PRIMARY KEY,
                ticker TEXT NOT NULL,
                cohort_date DATE NOT NULL,
                count_9m_alerts_180d INT NOT NULL,
                first_9m_alert_in_window DATE,
                last_9m_alert DATE,
                latest_volume BIGINT,
                latest_gap_pct FLOAT,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE (ticker, cohort_date)
            );
            CREATE INDEX IF NOT EXISTS idx_sugar_babies_cohort_date
                ON mi_sugar_babies_cohort(cohort_date DESC);
            CREATE INDEX IF NOT EXISTS idx_sugar_babies_cohort_ticker
                ON mi_sugar_babies_cohort(ticker, cohort_date DESC);

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

            CREATE TABLE IF NOT EXISTS mi_orb_shadow_trades (
                id               SERIAL PRIMARY KEY,
                ticker           TEXT NOT NULL,
                alert_date       DATE NOT NULL,
                bar_size_minutes INT NOT NULL,
                signal_type      TEXT NOT NULL,
                shape_tag        TEXT,
                score_tier       TEXT,

                orb_high         NUMERIC,
                orb_low          NUMERIC,
                atr_14           NUMERIC,

                trigger_minute_et TIME,
                entry_price      NUMERIC,
                stop_price       NUMERIC,
                hard_stop        NUMERIC,
                risk_dollars     NUMERIC,
                entry_shares     NUMERIC,

                status           TEXT NOT NULL,
                skip_reason      TEXT,
                exits            JSONB DEFAULT '[]'::jsonb,
                remaining_shares NUMERIC DEFAULT 0,
                partial_taken    BOOLEAN DEFAULT FALSE,
                breakeven_active BOOLEAN DEFAULT FALSE,
                running_closes   JSONB DEFAULT '[]'::jsonb,
                total_pnl        NUMERIC,
                hold_days        INT,

                created_at       TIMESTAMPTZ DEFAULT NOW(),
                closed_at        TIMESTAMPTZ,
                UNIQUE (ticker, alert_date, bar_size_minutes)
            );
            CREATE INDEX IF NOT EXISTS idx_shadow_status
                ON mi_orb_shadow_trades(status);
            CREATE INDEX IF NOT EXISTS idx_shadow_alert_date
                ON mi_orb_shadow_trades(alert_date);

            -- Daily account-equity history (per account_mode) for the
            -- drawdown-based circuit breaker (#39, shadow shipped 2026-05-08).
            -- Generically reusable for analytics, /status enrichment, and
            -- future cross-strategy ranking allocator track-record dim —
            -- do NOT couple readers exclusively to drawdown-breaker semantics.
            CREATE TABLE IF NOT EXISTS mi_account_equity_snapshots (
                id              SERIAL PRIMARY KEY,
                snapshot_date   DATE NOT NULL,
                account_mode    TEXT NOT NULL,
                equity          NUMERIC NOT NULL,
                cash            NUMERIC,
                portfolio_value NUMERIC,
                source          TEXT NOT NULL DEFAULT 'eod',
                created_at      TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE (snapshot_date, account_mode)
            );
            CREATE INDEX IF NOT EXISTS idx_equity_snap_mode_date
                ON mi_account_equity_snapshots(account_mode, snapshot_date DESC);

            -- Safeguard state machine (1 row per (safeguard, account_mode)).
            -- Currently used by drawdown_breaker; extensible to other future
            -- safeguards. Read by _check_safeguards via PK lookup; written
            -- only by the daily 16:10 cron's recompute_drawdown_state.
            CREATE TABLE IF NOT EXISTS mi_safeguard_state (
                safeguard           TEXT NOT NULL,
                account_mode        TEXT NOT NULL,
                state               TEXT NOT NULL,
                last_transition_at  TIMESTAMPTZ,
                last_evaluation_at  TIMESTAMPTZ,
                last_drawdown_pct   NUMERIC,
                last_peak           NUMERIC,
                last_peak_date      DATE,
                updated_at          TIMESTAMPTZ DEFAULT NOW(),
                PRIMARY KEY (safeguard, account_mode)
            );

            -- Data-gated-review escalation state (#54 RMV-miss mitigation, Prong B).
            -- A review that's been READY (or whose predicate has been ERRORING) beyond a
            -- grace window gets its own deterministic Telegram instead of rotting in the
            -- LLM-narrated Sunday digest. This carries the per-review first-seen dates +
            -- last-escalated date so escalation has grace + dedup (check_pending_reviews
            -- is stateless). Rows are deleted once a review resolves (no longer ready/erroring).
            CREATE TABLE IF NOT EXISTS mi_review_escalation_state (
                review_id           TEXT PRIMARY KEY,
                first_ready_date    DATE,
                first_error_date    DATE,
                last_escalated_date DATE,
                updated_at          TIMESTAMPTZ DEFAULT NOW()
            );

            -- Cross-strategy allocator (#31) candidate queue. Strategies
            -- enqueue RankableCandidate rows during their normal scan; the
            -- 9:28 AM allocator job drains, scores, and selects top-N.
            -- Phase 1A (shadow): legacy submission paths run unchanged
            -- alongside the queue; allocator emits audit-only telemetry.
            -- raw_dimensions JSONB carries setup/catalyst/volume/regime
            -- breakdown for offline scoring tune.
            CREATE TABLE IF NOT EXISTS mi_pending_allocations (
                id                  SERIAL PRIMARY KEY,
                ticker              TEXT NOT NULL,
                alert_date          DATE NOT NULL,
                strategy            TEXT NOT NULL,
                composite_score     NUMERIC NOT NULL,
                raw_dimensions      JSONB NOT NULL DEFAULT '{}',
                status              TEXT NOT NULL DEFAULT 'pending',
                shadow_rank         INTEGER,
                shadow_allocated    BOOLEAN DEFAULT FALSE,
                created_at          TIMESTAMPTZ DEFAULT NOW(),
                evaluated_at        TIMESTAMPTZ,
                UNIQUE (ticker, alert_date, strategy)
            );
            CREATE INDEX IF NOT EXISTS idx_pending_alloc_date
                ON mi_pending_allocations(alert_date DESC);
            CREATE INDEX IF NOT EXISTS idx_pending_alloc_strategy
                ON mi_pending_allocations(strategy, alert_date DESC);
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
        for tbl in ("mi_paper_trades", "mi_live_trades", "mi_live_orders",
                    "mi_orb_shadow_trades"):
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
        # Every scan invocation appends a fresh row per ticker (no UPSERT) so
        # the trajectory across the day is preserved. Last-seen reads use
        # SELECT DISTINCT ON (ticker) ORDER BY scan_time_et DESC.
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
            -- Drop the (scan_date, ticker) UNIQUE constraint by name-agnostic
            -- lookup — auto-generated names can drift across migrations.
            DO $$
            DECLARE c TEXT;
            BEGIN
                FOR c IN
                    SELECT conname FROM pg_constraint
                    WHERE conrelid = 'mi_ep_scan_log'::regclass AND contype = 'u'
                LOOP
                    EXECUTE format('ALTER TABLE mi_ep_scan_log DROP CONSTRAINT %I', c);
                END LOOP;
            END $$;
            ALTER TABLE mi_ep_scan_log ADD COLUMN IF NOT EXISTS scan_time_et TIMESTAMPTZ;
            ALTER TABLE mi_ep_scan_log ADD COLUMN IF NOT EXISTS rank_by_gap INT;
            ALTER TABLE mi_ep_scan_log ADD COLUMN IF NOT EXISTS projected_vol_multiple FLOAT;
            ALTER TABLE mi_ep_scan_log ADD COLUMN IF NOT EXISTS pm_rvol FLOAT;
            ALTER TABLE mi_ep_scan_log ADD COLUMN IF NOT EXISTS adv FLOAT;
            ALTER TABLE mi_ep_scan_log ADD COLUMN IF NOT EXISTS adv_source TEXT;
            ALTER TABLE mi_ep_scan_log ADD COLUMN IF NOT EXISTS minutes_since_open INT;
            CREATE INDEX IF NOT EXISTS idx_ep_scan_log_scan_time
                ON mi_ep_scan_log(scan_time_et DESC);
        """)

        # ── EP scan outcomes — forward returns on every scan candidate ────
        # One row per (ticker, scan_date). Recomputed nightly as forward
        # sessions accrue. Lets us answer "did the filter throw away winners?"
        # by joining mi_ep_scan_log → mi_ep_scan_outcomes on (ticker, scan_date).
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mi_ep_scan_outcomes (
                id SERIAL PRIMARY KEY,
                ticker TEXT NOT NULL,
                scan_date DATE NOT NULL,
                baseline_close FLOAT,
                fwd_5d_pct FLOAT,
                fwd_10d_pct FLOAT,
                n_sessions_5d INT,
                n_sessions_10d INT,
                computed_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE (ticker, scan_date)
            );
            CREATE INDEX IF NOT EXISTS idx_ep_scan_outcomes_scan_date
                ON mi_ep_scan_outcomes(scan_date DESC);
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

        # ── Trading journal — user observations with auto-enriched context ─
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mi_journal_entries (
                id SERIAL PRIMARY KEY,
                entry_text TEXT NOT NULL,
                regime TEXT,
                ep_context JSONB,
                theme_context TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_journal_created
                ON mi_journal_entries(created_at DESC);
        """)

        # ── Theme-discovery SHADOW lane (ADR 0007) — proposed themes from the new
        # nascent-discovery logic (rank-accel + recovery-slope selectors + ignition
        # prompt), written WITHOUT touching live mi_themes / the brief. Diffed against
        # the live engine for N nights before any vector is promoted to live.
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mi_theme_candidates_shadow (
                id SERIAL PRIMARY KEY,
                run_date DATE NOT NULL,
                name TEXT NOT NULL,
                thesis TEXT,
                tickers TEXT[] NOT NULL,
                source TEXT NOT NULL DEFAULT 'shadow_v2',
                would_revive BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE (run_date, name)
            );
            CREATE INDEX IF NOT EXISTS idx_theme_shadow_run_date
                ON mi_theme_candidates_shadow(run_date DESC);
        """)

        # ── Correlation clusters — statistical pre-pass for theme discovery ──────────
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mi_correlation_clusters (
                id SERIAL PRIMARY KEY,
                cluster_date DATE NOT NULL,
                cluster_hash TEXT NOT NULL,
                ticker TEXT NOT NULL,
                member_count INT NOT NULL,
                mean_corr FLOAT NOT NULL,
                avg_rs FLOAT DEFAULT 0,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE (cluster_date, cluster_hash, ticker)
            );
            CREATE INDEX IF NOT EXISTS idx_corr_clusters_date
                ON mi_correlation_clusters(cluster_date DESC);
        """)

        # ── Validation cooldowns — prevent re-assignment of recently removed tickers ──
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mi_validation_cooldowns (
                id SERIAL PRIMARY KEY,
                ticker TEXT NOT NULL,
                theme_name TEXT NOT NULL,
                removed_at TIMESTAMPTZ DEFAULT NOW(),
                cooldown_until TIMESTAMPTZ NOT NULL,
                removal_reason TEXT,
                removal_count INT DEFAULT 1,
                bypassed BOOLEAN DEFAULT FALSE,
                bypassed_at TIMESTAMPTZ,
                bypassed_reason TEXT,
                UNIQUE (ticker, theme_name)
            );
            CREATE INDEX IF NOT EXISTS idx_cooldowns_active
                ON mi_validation_cooldowns(cooldown_until)
                WHERE NOT bypassed;
        """)

        # ── HUD state — pinned message IDs for auto-refresh ──────────────
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mi_hud_state (
                key        TEXT PRIMARY KEY,
                value      TEXT NOT NULL,
                updated_at TIMESTAMPTZ DEFAULT NOW()
            );
        """)

        # ── System self-audit reviews (weekly + future monthly/quarterly) ─
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mi_system_reviews (
                id           SERIAL PRIMARY KEY,
                review_date  DATE NOT NULL,
                window_days  INT NOT NULL DEFAULT 7,
                regime       TEXT,
                summary      TEXT NOT NULL,
                metrics      JSONB,
                suggestions  JSONB,
                created_at   TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE (review_date, window_days)
            );
            CREATE INDEX IF NOT EXISTS idx_system_reviews_date
                ON mi_system_reviews(review_date DESC);
        """)

        # ── Audit metric baselines (system_audit.py L2 anomaly detection) ─
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mi_metric_baselines (
                metric_name  TEXT NOT NULL,
                as_of_date   DATE NOT NULL,
                p50          DOUBLE PRECISION,
                p95          DOUBLE PRECISION,
                mad          DOUBLE PRECISION,
                sample_n     INT NOT NULL DEFAULT 0,
                updated_at   TIMESTAMPTZ DEFAULT NOW(),
                PRIMARY KEY (metric_name, as_of_date)
            );
            CREATE INDEX IF NOT EXISTS idx_metric_baselines_name_date
                ON mi_metric_baselines(metric_name, as_of_date DESC);
        """)

        # Manual epoch markers — a fix that changes a metric's distribution
        # writes one row here so the baseline refresh job ignores history
        # older than the reset.
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mi_baseline_resets (
                id           SERIAL PRIMARY KEY,
                metric_name  TEXT NOT NULL,
                reset_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                reason       TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_baseline_resets_name
                ON mi_baseline_resets(metric_name, reset_at DESC);
        """)

        # ── Job-run telemetry (core.job_audit context manager) ─
        # One row per scheduled-job invocation. Catches degraded-but-not-broken
        # runs that notify_job_failure misses: slow runs, silent zero-rows.
        # status: 'success' | 'failed' | 'empty_result'
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mi_job_runs (
                id BIGSERIAL PRIMARY KEY,
                job_id TEXT NOT NULL,
                started_at TIMESTAMPTZ NOT NULL,
                finished_at TIMESTAMPTZ,
                duration_s NUMERIC,
                status TEXT NOT NULL,
                rows_written INTEGER,
                expected_min_rows INTEGER,
                error_message TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_job_runs_job_started
                ON mi_job_runs(job_id, started_at DESC);
            CREATE INDEX IF NOT EXISTS idx_job_runs_status
                ON mi_job_runs(status, started_at DESC);
        """)

        # Market cap cache for parabolic-short detector cap-tier classification.
        # Stable enough that we refresh once per ticker every 30d via FMP.
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mi_market_caps (
                ticker      TEXT PRIMARY KEY,
                market_cap  BIGINT,
                fetched_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
        """)

        # ── Per-minute cumulative volume curves (RVOL@T baselines) ──────────
        # Stores 20-day mean cumulative volume at each ET clock-minute, anchored
        # either to pre-market open (4:00) or regular session open (9:30). Used
        # by ep_detector to gate pre-9:45 entries against a like-for-like
        # baseline ("is today's pace above normal at THIS minute?") instead of
        # the apples-to-oranges raw_vol/daily_ADV ratio that's structurally
        # tiny pre-open. See agents/market_intelligence/minute_volume.py.
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mi_minute_volume_curves (
                ticker          TEXT NOT NULL,
                anchor          TEXT NOT NULL,         -- 'pm' or 'session'
                et_clock_minute SMALLINT NOT NULL,     -- 0..1439, ET minutes from 00:00
                mean_cum_vol    DOUBLE PRECISION NOT NULL,
                stddev_cum_vol  DOUBLE PRECISION,
                sample_n        INT NOT NULL,
                refreshed_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (ticker, anchor, et_clock_minute)
            );
            CREATE INDEX IF NOT EXISTS idx_minute_vol_curves_ticker_anchor
                ON mi_minute_volume_curves(ticker, anchor);
        """)

        # Parabolic-short candidate scan results. Persists EVERY metric, not
        # just the boolean stage, so thresholds can be re-tuned against
        # historical scans without re-running.
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mi_parabolic_candidates (
                id                          SERIAL PRIMARY KEY,
                ticker                      TEXT NOT NULL,
                scan_date                   DATE NOT NULL,
                market_cap                  BIGINT,
                cap_tier                    TEXT,
                prior_move_pct              FLOAT,
                base_date                   DATE,
                ext_vs_sma20                FLOAT,
                ext_vs_sma50                FLOAT,
                roc_5d                      FLOAT,
                roc_20d                     FLOAT,
                pullback_count_20d          INT,
                days_up_streak              INT,
                gap_count_3d                INT,
                range_expansion_count_3d    INT,
                vol_expansion_count_3d      INT,
                gapped_today                BOOLEAN,
                climax_volume_flag          BOOLEAN,
                score                       INT,
                stage                       TEXT NOT NULL,
                is_earnings_today           BOOLEAN,
                created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE (ticker, scan_date)
            );
            ALTER TABLE mi_parabolic_candidates
                ADD COLUMN IF NOT EXISTS is_earnings_today BOOLEAN;
            CREATE INDEX IF NOT EXISTS idx_parabolic_candidates_date
                ON mi_parabolic_candidates(scan_date);
            CREATE INDEX IF NOT EXISTS idx_parabolic_candidates_stage
                ON mi_parabolic_candidates(stage, scan_date DESC);
        """)

        # Parabolic exclusions — manual operator overrides + auto LLM news verdicts.
        # Composite PK on (ticker, source) lets a manual permanent ban coexist
        # with an auto news_check verdict for the same ticker (different concerns).
        # `excluded_until = NULL` means permanent (manual only); auto-verdicts
        # carry a TTL so they re-check after deals fall through / news ages out.
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mi_parabolic_exclusions (
                ticker          TEXT NOT NULL,
                source          TEXT NOT NULL,
                reason          TEXT NOT NULL,
                detail          TEXT,
                excluded_until  DATE,
                created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (ticker, source)
            );
            CREATE INDEX IF NOT EXISTS idx_parabolic_exclusions_ticker
                ON mi_parabolic_exclusions(ticker);
        """)

        # Wick-fill candidates (P22, telemetry-only). 9M days closing mid-range
        # ([0.50, 0.75)) with green body and ≥3× ADV — Bonde / Kristjan
        # "negated shooting star": Day 1 traps shorts on the upper-wick close,
        # Day 2 break of prior_high covers them. Forward returns are measured
        # from TWO anchors so the weekly review can disambiguate filled vs
        # not-filled cohorts:
        #   from_high_pct  → measured from prior_high; NULL when filled_wick=false
        #   from_close_pct → measured from Day 1 close; unconditional drift baseline
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mi_wick_candidates (
                id                       SERIAL PRIMARY KEY,
                ticker                   TEXT NOT NULL,
                alert_date               DATE NOT NULL,
                open_price               FLOAT NOT NULL,
                close_price              FLOAT NOT NULL,
                high_price               FLOAT NOT NULL,
                low_price                FLOAT NOT NULL,
                volume                   BIGINT NOT NULL,
                close_in_range_pct       FLOAT NOT NULL,
                prior_high               FLOAT NOT NULL,
                prev_5d_pct              FLOAT,
                prev_20d_pct             FLOAT,
                prev_vs_sma10            FLOAT,
                prev_vs_sma50            FLOAT,
                sma50_slope_pct          FLOAT,
                prior_sessions           INT,
                filled_wick              BOOLEAN,
                fill_date                DATE,
                fwd_1d_from_high_pct     FLOAT,
                fwd_3d_from_high_pct     FLOAT,
                fwd_10d_from_high_pct    FLOAT,
                fwd_1d_from_close_pct    FLOAT,
                fwd_3d_from_close_pct    FLOAT,
                fwd_10d_from_close_pct   FLOAT,
                created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE (ticker, alert_date)
            );
            CREATE INDEX IF NOT EXISTS idx_wick_candidates_date
                ON mi_wick_candidates(alert_date);
        """)

        # Fishhook V3 anchors (gap-up undercut & reclaim, base-rate harvester).
        # Stage-0 explorer (scripts/fishhook_v3_explorer.py) measured median
        # R_5d ~1.1 across 240 threshold permutations — the original V3
        # "deeper drift = bigger reclaim" thesis was disproven by the data.
        # Reframed as a high-frequency / low-R fade-to-anchor setup. One row
        # per anchor; `state` tracks the full lifecycle so the table is the
        # single source of truth for both watchlist (in-flight) and outcome
        # (settled) views. State transitions:
        #   pending              — anchor recorded; trap window not yet elapsed
        #   promoted             — close < anchor_open in T+3..T+10
        #   reclaimed            — high >= anchor_open in T+25 from promotion
        #   settled              — 5 sessions post-reclaim; R_5d computed
        #   expired_no_promotion — T+10 elapsed without ever drifting
        #   expired_no_reclaim   — T+25 elapsed without crossing back
        #   invalidated          — close < washout_low post-reclaim (trap re-traps)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mi_fishhook_anchors (
                id                          SERIAL PRIMARY KEY,
                ticker                      TEXT NOT NULL,
                anchor_date                 DATE NOT NULL,
                prev_close                  FLOAT NOT NULL,
                anchor_open                 FLOAT NOT NULL,
                anchor_close                FLOAT NOT NULL,
                gap_pct                     FLOAT NOT NULL,
                in_top2000                  BOOLEAN NOT NULL,
                in_ep_alerts                BOOLEAN NOT NULL,
                state                       TEXT NOT NULL,
                washout_low                 FLOAT,
                washout_session_offset      INT,
                drift_pct_max               FLOAT,
                promoted_session_offset     INT,
                reclaim_session_offset      INT,
                reclaim_open                FLOAT,
                reclaim_close               FLOAT,
                reclaim_open_vs_anchor_pct  FLOAT,
                actual_entry_price          FLOAT,
                fwd_1d_high_pct             FLOAT,
                fwd_3d_high_pct             FLOAT,
                fwd_5d_high_pct             FLOAT,
                fwd_10d_high_pct            FLOAT,
                fwd_5d_close_pct            FLOAT,
                r_5d                        FLOAT,
                invalidated_within_5d       BOOLEAN,
                n_fwd_sessions_available    INT,
                created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE (ticker, anchor_date),
                CHECK (state IN (
                    'pending','promoted','reclaimed','settled',
                    'expired_no_promotion','expired_no_reclaim','invalidated'
                ))
            );
            CREATE INDEX IF NOT EXISTS idx_fishhook_state
                ON mi_fishhook_anchors(state, anchor_date DESC);
            CREATE INDEX IF NOT EXISTS idx_fishhook_anchor_date
                ON mi_fishhook_anchors(anchor_date);
        """)

        # Continuation-flag detector candidates (post-runup VCP / Qullamaggie
        # tightening flag). One row per (ticker, scan_date), persists every
        # stage including `unqualified` so thresholds re-tune offline. Mirrors
        # mi_parabolic_candidates' flat-table architecture.
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mi_flag_candidates (
                id                          SERIAL PRIMARY KEY,
                ticker                      TEXT NOT NULL,
                scan_date                   DATE NOT NULL,
                pivot_high_date             DATE,
                pivot_high_price            FLOAT,
                base_age                    INT,
                base_high                   FLOAT,
                base_low                    FLOAT,
                runup_pct                   FLOAT,
                runup_start_date            DATE,
                range_contraction_ratio     FLOAT,
                vol_contraction_ratio       FLOAT,
                last_body_pct               FLOAT,
                prev_body_pct               FLOAT,
                atr_14                      FLOAT,
                sma_10                      FLOAT,
                sma_20                      FLOAT,
                breakout_close              FLOAT,
                breakout_volume_ratio       FLOAT,
                rs_rank                     INT,
                rs_composite                FLOAT,
                sector                      TEXT,
                stage                       TEXT NOT NULL,
                reason                      TEXT,
                score                       INT,
                held_from_stage             TEXT,
                created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE (ticker, scan_date)
            );
            CREATE INDEX IF NOT EXISTS idx_flag_candidates_scan_date
                ON mi_flag_candidates(scan_date DESC);
            CREATE INDEX IF NOT EXISTS idx_flag_candidates_stage
                ON mi_flag_candidates(stage, scan_date DESC);
            CREATE INDEX IF NOT EXISTS idx_flag_candidates_ticker
                ON mi_flag_candidates(ticker, scan_date DESC);
            ALTER TABLE mi_flag_candidates ADD COLUMN IF NOT EXISTS fresh_tight_fires BOOLEAN;
            ALTER TABLE mi_flag_candidates ADD COLUMN IF NOT EXISTS fresh_2bar_tr_pct FLOAT;
            ALTER TABLE mi_flag_candidates ADD COLUMN IF NOT EXISTS atr14_pct         FLOAT;
            -- RMV Phase 1 (TI #54, 2026-05-09): telemetry-only persistence.
            -- 0-100 contraction index per DeepVue; both windows persisted for
            -- offline Phase 2 divergence analysis vs _compute_fresh_tightening.
            ALTER TABLE mi_flag_candidates ADD COLUMN IF NOT EXISTS rmv_5d  FLOAT;
            ALTER TABLE mi_flag_candidates ADD COLUMN IF NOT EXISTS rmv_15d FLOAT;
            -- P7.2 audit trail (2026-05-17): records which universe pattern(s)
            -- admitted this ticker for the scan. Possible tags:
            --   'rs_top200'           — top-200 RS leader (organic)
            --   'rs_1m_80'            — rs_1m percentile ≥ 80 (organic burst)
            --   'momentum_25pct'      — +25% off 10d min close (organic burst)
            --   'magna53_failed_r3'   — R3-stopped MAGNA53 within last 7d
            --   'ninem_universe_watch'— 9M EP within last 14d (P7.3b, Pradeep
            --                            methodology: 9M = watchlist trigger)
            -- A ticker admitted by multiple patterns captures all tags. Phase 5
            -- calibration uses this to answer "did carryforward admit names
            -- organic patterns wouldn't have caught?"
            ALTER TABLE mi_flag_candidates ADD COLUMN IF NOT EXISTS
                universe_sources TEXT[] DEFAULT '{}';

            -- Intraday flag-break detections (#94, ADR 0005, 2026-05-23).
            -- EOD flag_candidates is the IDENTIFICATION layer (which stocks
            -- have tight bases + base_high boundary); mi_flag_breaks is the
            -- EXECUTION layer (catches the intraday MOMENT price breaks
            -- base_high with volume confirmation). The two together replace
            -- the broken EOD TRIGGERED entry (entered after the move had
            -- already played out — see #92 evidence, -2.66% realistic 10d
            -- with -2.03% overnight fade).
            --
            -- First ship is telemetry-only (shadow phase): rows accumulate,
            -- no entry execution. Forward-return analysis at N>=10 settled
            -- via _b94_intraday_flag_break_evidence.py (filed separately
            -- in Commit 2).
            CREATE TABLE IF NOT EXISTS mi_flag_breaks (
                id SERIAL PRIMARY KEY,
                ticker TEXT NOT NULL,
                break_date DATE NOT NULL,                 -- ET date of break
                break_time TIMESTAMPTZ NOT NULL,          -- moment of detection (UTC)
                minutes_since_open INT NOT NULL,          -- 0 at 9:30 ET, 390 at 16:00 ET
                -- Snapshot of flag-detector state at moment of break
                parent_stage TEXT NOT NULL,               -- TIGHTENING | COILED | TRIGGERED
                parent_scan_date DATE NOT NULL,           -- MAX(scan_date) WHERE < CURRENT_DATE
                base_high FLOAT NOT NULL,                 -- the boundary that was broken
                base_low FLOAT,                           -- for future stop placement
                base_age INT,                             -- days since pivot
                -- Break event data
                break_price FLOAT NOT NULL,               -- current_price at detection
                pct_above_base_high FLOAT NOT NULL,       -- (break_price - base_high) / base_high * 100
                today_volume BIGINT,                      -- cumulative day volume at detection
                adv_20 BIGINT,                            -- 20d avg daily volume (context)
                volume_pct_of_adv FLOAT,                  -- today_volume / adv_20 * 100
                projected_full_day_volume BIGINT,         -- volume-pace projection
                -- Cohort context (read-side display only — NOT detector coupling)
                in_sugar_baby_cohort BOOLEAN DEFAULT FALSE,
                cohort_count_180d INT,
                -- Post-EOD reconciliation (Gemini contract 2026-05-23):
                -- run_flag_scan flips this TRUE for any same-day break
                -- whose parent ticker classified INVALIDATED at 5:25 PM.
                -- Backward-check filters via parent_invalidated_eod = FALSE.
                parent_invalidated_eod BOOLEAN DEFAULT FALSE,
                invalidated_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE (ticker, break_date)
            );
            CREATE INDEX IF NOT EXISTS idx_flag_breaks_date
                ON mi_flag_breaks(break_date DESC);
            CREATE INDEX IF NOT EXISTS idx_flag_breaks_ticker
                ON mi_flag_breaks(ticker, break_date DESC);

            -- #270 anticipation re-entry lifecycle (Step 3 SHADOW, 2026-06-16). Composes the
            -- already-firing fragments (EP gap → gap-low undercut → reclaim → coil → entry →
            -- harvest) into ONE observed-but-not-traded lifecycle (MNTS template). One row per
            -- (ticker, gap_day). SHADOW = no submit; alert-only.
            --
            -- STATE (the replay-label → lifecycle-state mapping lives in the JOB layer, never
            -- inside the ported replay() — see anticipation.py):
            --   watched   gap day seeded (close>=1.4*prev_close, vol>=3*ADV20, close>SMA200, $>=5)
            --   armed     undercut of gap_day_low in the arm window (the U&R the flag detector
            --             wrongly INVALIDATES on — the bug this setup turns into the signal)
            --   coiled    reclaimed pivot + tight range + quiet volume (the anticipation coil)
            --   ready     the replay's terminal RECLAIM (daily volume-expansion reclaim) = a
            --             SET-UP, NOT an entry; carries NO entry/stop price
            --   triggered an ENTRY actually fired (anticipation coil-close OR 3b first5/gdl) —
            --             the ONLY state with entry_price/stop_price + the ONLY one realized_r
            --             settles against. Writing the reclaim as 'triggered' would count set-ups
            --             as entries (the MFE-vs-realized conflation this whole arc closed).
            --   expired   no undercut within the arm window
            --
            -- realized_r = HARVESTED R (Layer-3 ladder + stop-fills, via _270_harvest), NOT MFE.
            -- fwd_mfe_pct = the perfect-foresight ceiling only. The graduation predicate
            -- (data_gated_reviews anticipation_270_shadow_graduation) gates on realized_r IS NOT NULL.
            -- rmv_5d/rmv_15d/tight_close_pct are recorded TELEMETRY (NOT gates — #54 verdict +
            -- STEP 0: RMV inverts under a too-tight stop; the COILED gate stays range+base_run).
            -- #296 rename migration: move the shadow table off the old "delayed_ep" name.
            -- Idempotent — only fires when the old table exists and the new one doesn't, so it
            -- preserves the shadow rows on prod and is a no-op on fresh DBs + reruns.
            DO $$ BEGIN
                IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'mi_delayed_ep_lifecycle')
                   AND NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'mi_anticipation_lifecycle') THEN
                    ALTER TABLE mi_delayed_ep_lifecycle RENAME TO mi_anticipation_lifecycle;
                END IF;
            END $$;
            CREATE TABLE IF NOT EXISTS mi_anticipation_lifecycle (
                ticker          TEXT NOT NULL,
                gap_day         DATE NOT NULL,           -- the EP/9M gap day = the cohort seed
                state           TEXT NOT NULL,
                gap_day_low     FLOAT,                   -- the U&R reference
                gap_day_vol     FLOAT,
                sma200_at_gap   FLOAT,
                armed_date      DATE,
                coiled_date     DATE,
                ready_date      DATE,                    -- replay TRIGGERED (reclaim) lands here
                triggered_date  DATE,                    -- entry-fired only
                entry_tactic    TEXT,                    -- anticipation | first5_break | gdl_reclaim
                entry_price     FLOAT,
                stop_price      FLOAT,
                reenter_count   INT DEFAULT 0,           -- Pradeep stop-and-reenter attempts
                base_run        INT,                     -- developed-base maturity proxy at coil
                rmv_5d          FLOAT,                   -- telemetry (see header)
                rmv_15d         FLOAT,
                tight_close_pct FLOAT,                   -- Pradeep |close %change| secondary cross-check
                fwd_mfe_pct     FLOAT,                   -- MFE ceiling (upper bound only)
                realized_r      FLOAT,                   -- HARVESTED R; the graduation gate column
                day0_fills      JSONB,                   -- 3b/execution-persisted day-0 minute fills
                                                         -- [{price,fraction,day_idx}]; first5/gdl realized_r
                                                         -- derives from THESE. Absent → settlement ABSTAINS
                                                         -- (never a daily-bar fallback for a minute tactic).
                settled         BOOLEAN NOT NULL DEFAULT FALSE,
                last_eval       DATE,
                created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (ticker, gap_day),
                CHECK (state IN ('watched','armed','coiled','ready','triggered','expired'))
            );
            CREATE INDEX IF NOT EXISTS idx_anticipation_state
                ON mi_anticipation_lifecycle(state, gap_day DESC);
            -- the settlement re-eval set: entries awaiting their forward window
            CREATE INDEX IF NOT EXISTS idx_anticipation_unsettled
                ON mi_anticipation_lifecycle(triggered_date)
                WHERE state = 'triggered' AND settled = FALSE;

            -- Intraday support-test detections (#95, entry-technique #2 from
            -- user_tight_range_entry_techniques.md). Counter-trend mechanic:
            -- price tags base_low within tolerance and bounces. Per Morales
            -- methodology, volume is NOT a required factor — this is the
            -- design departure from #94 (breakout requires volume confirmation).
            -- Telemetry-only shadow phase; N>=10 settled before paper.
            CREATE TABLE IF NOT EXISTS mi_flag_support_tests (
                id SERIAL PRIMARY KEY,
                ticker TEXT NOT NULL,
                test_date DATE NOT NULL,                  -- ET date of support test
                test_time TIMESTAMPTZ NOT NULL,           -- moment of detection (UTC)
                minutes_since_open INT NOT NULL,
                -- Snapshot of flag-detector state at moment of test
                parent_stage TEXT NOT NULL,               -- TIGHTENING | COILED | TRIGGERED
                parent_scan_date DATE NOT NULL,
                base_high FLOAT,                          -- context
                base_low FLOAT NOT NULL,                  -- the boundary being tested
                base_age INT,
                -- Test event data
                day_low FLOAT NOT NULL,                   -- intraday low (the actual tag)
                current_price FLOAT NOT NULL,             -- price at detection (the bounce)
                pct_below_base_low FLOAT NOT NULL,        -- (day_low - base_low) / base_low * 100; negative = undercut
                bounce_pct_from_low FLOAT NOT NULL,       -- (current_price - day_low) / day_low * 100
                today_volume BIGINT,                      -- context only — no volume gate
                adv_20 BIGINT,
                volume_pct_of_adv FLOAT,
                -- Cohort context (display only)
                in_sugar_baby_cohort BOOLEAN DEFAULT FALSE,
                cohort_count_180d INT,
                -- Post-EOD reconciliation (same pattern as mi_flag_breaks):
                -- run_flag_scan flips this TRUE if parent ticker classified
                -- INVALIDATED at 5:25 PM. Backward-check filters via
                -- parent_invalidated_eod = FALSE.
                parent_invalidated_eod BOOLEAN DEFAULT FALSE,
                invalidated_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE (ticker, test_date)
            );
            CREATE INDEX IF NOT EXISTS idx_support_tests_date
                ON mi_flag_support_tests(test_date DESC);
            CREATE INDEX IF NOT EXISTS idx_support_tests_ticker
                ON mi_flag_support_tests(ticker, test_date DESC);

            -- Intraday U&R (Undercut & Rally) detections (#98, entry-technique #5
            -- from user_tight_range_entry_techniques.md — Morales/OWL methodology).
            -- A SHALLOW stop-run BELOW base_low (deeper than the support-test ≤2%
            -- band, so the two never double-count) that then RECLAIMS back above it.
            -- Stop / "selling guide" = the undercut low. NO volume gate (Morales:
            -- "volume is generally not a factor"). Telemetry-only shadow phase;
            -- N>=10 settled before paper.
            CREATE TABLE IF NOT EXISTS mi_flag_undercut_rally (
                id SERIAL PRIMARY KEY,
                ticker TEXT NOT NULL,
                ur_date DATE NOT NULL,                    -- ET date of the U&R
                ur_time TIMESTAMPTZ NOT NULL,             -- moment of detection (UTC)
                minutes_since_open INT NOT NULL,
                -- Flag-detector state at the moment of detection
                parent_stage TEXT NOT NULL,               -- TIGHTENING | COILED | TRIGGERED
                parent_scan_date DATE NOT NULL,
                base_high FLOAT,                          -- context
                base_low FLOAT NOT NULL,                  -- the prior low that was undercut
                base_age INT,
                -- U&R event data
                undercut_low FLOAT NOT NULL,              -- day's low = deepest probe = STOP / selling guide
                undercut_pct FLOAT NOT NULL,              -- (base_low - undercut_low) / base_low * 100; +ve = depth below base_low
                current_price FLOAT NOT NULL,             -- reclaim price at detection
                reclaim_pct_above_base FLOAT NOT NULL,    -- (current_price - base_low) / base_low * 100
                today_volume BIGINT,                      -- context only — NO volume gate
                adv_20 BIGINT,
                volume_pct_of_adv FLOAT,
                -- Cohort context (display only)
                in_sugar_baby_cohort BOOLEAN DEFAULT FALSE,
                cohort_count_180d INT,
                -- Post-EOD reconciliation (same pattern as mi_flag_support_tests):
                -- reconcile_flag_state_post_eod flips this TRUE if the parent ticker
                -- classified INVALIDATED at the 5:25 PM scan. Backward-check filters
                -- via parent_invalidated_eod = FALSE.
                parent_invalidated_eod BOOLEAN DEFAULT FALSE,
                invalidated_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE (ticker, ur_date)
            );
            CREATE INDEX IF NOT EXISTS idx_undercut_rally_date
                ON mi_flag_undercut_rally(ur_date DESC);
            CREATE INDEX IF NOT EXISTS idx_undercut_rally_ticker
                ON mi_flag_undercut_rally(ticker, ur_date DESC);

            -- Intraday MA-pullback detections (#96, entry-technique #3 from
            -- user_tight_range_entry_techniques.md). Classic VCP/Minervini
            -- mechanic: price retraces to SMA10 or SMA20 inside the range and
            -- bounces. KEY differentiator from #94/#95: light-volume gate
            -- (today_pace ≤ ADV) — pullbacks should NOT happen on heavy volume.
            -- Telemetry-only shadow phase; N>=10 settled before paper.
            CREATE TABLE IF NOT EXISTS mi_flag_ma_pullbacks (
                id SERIAL PRIMARY KEY,
                ticker TEXT NOT NULL,
                pullback_date DATE NOT NULL,
                pullback_time TIMESTAMPTZ NOT NULL,
                minutes_since_open INT NOT NULL,
                parent_stage TEXT NOT NULL,
                parent_scan_date DATE NOT NULL,
                base_high FLOAT,
                base_low FLOAT,
                base_age INT,
                -- MA being tested (SMA10 preferred over SMA20 when both fire)
                ma_label TEXT NOT NULL CHECK (ma_label IN ('SMA10', 'SMA20')),
                ma_value FLOAT NOT NULL,
                -- Test event data
                day_low FLOAT NOT NULL,                   -- intraday low (the actual tag)
                current_price FLOAT NOT NULL,             -- price at detection (the bounce)
                pct_below_ma FLOAT NOT NULL,              -- (day_low - ma) / ma * 100; negative = undercut
                bounce_pct_from_low FLOAT NOT NULL,
                today_volume BIGINT,
                adv_20 BIGINT,
                volume_pct_of_adv FLOAT,                  -- gate enforces ≤100% (light volume)
                projected_full_day_volume BIGINT,
                in_sugar_baby_cohort BOOLEAN DEFAULT FALSE,
                cohort_count_180d INT,
                parent_invalidated_eod BOOLEAN DEFAULT FALSE,
                invalidated_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE (ticker, pullback_date)
            );
            CREATE INDEX IF NOT EXISTS idx_ma_pullbacks_date
                ON mi_flag_ma_pullbacks(pullback_date DESC);
            CREATE INDEX IF NOT EXISTS idx_ma_pullbacks_ticker
                ON mi_flag_ma_pullbacks(ticker, pullback_date DESC);

            -- Low-volume rest (#97, entry-technique #4): a quiet tight coil INSIDE
            -- the base on dried-up volume (no test/bounce — the calm IS the signal).
            CREATE TABLE IF NOT EXISTS mi_flag_low_vol_rests (
                id SERIAL PRIMARY KEY,
                ticker TEXT NOT NULL,
                rest_date DATE NOT NULL,
                rest_time TIMESTAMPTZ NOT NULL,
                minutes_since_open INT NOT NULL,
                parent_stage TEXT NOT NULL,
                parent_scan_date DATE NOT NULL,
                base_high FLOAT,
                base_low FLOAT,
                base_age INT,
                current_price FLOAT NOT NULL,
                range_pct FLOAT NOT NULL,             -- intraday (high-low)/prev_close; gate ≤ ceil
                pos_in_base_pct FLOAT NOT NULL,        -- where price sits in the base, 0=low 100=high
                today_volume BIGINT,
                adv_20 BIGINT,
                volume_pct_of_adv FLOAT,
                projected_full_day_volume BIGINT,
                in_sugar_baby_cohort BOOLEAN DEFAULT FALSE,
                cohort_count_180d INT,
                parent_invalidated_eod BOOLEAN DEFAULT FALSE,
                invalidated_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE (ticker, rest_date)
            );
            CREATE INDEX IF NOT EXISTS idx_low_vol_rests_date
                ON mi_flag_low_vol_rests(rest_date DESC);
            CREATE INDEX IF NOT EXISTS idx_low_vol_rests_ticker
                ON mi_flag_low_vol_rests(ticker, rest_date DESC);

            -- Idempotent: add CHECK constraint on existing mi_flag_ma_pullbacks
            -- tables that pre-date the constraint (table was created
            -- 2026-05-24; constraint added same day post-/simplify review).
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.table_constraints
                    WHERE table_name = 'mi_flag_ma_pullbacks'
                      AND constraint_name = 'mi_flag_ma_pullbacks_ma_label_check'
                ) THEN
                    BEGIN
                        ALTER TABLE mi_flag_ma_pullbacks
                            ADD CONSTRAINT mi_flag_ma_pullbacks_ma_label_check
                            CHECK (ma_label IN ('SMA10', 'SMA20'));
                    EXCEPTION WHEN check_violation THEN
                        RAISE NOTICE 'mi_flag_ma_pullbacks has rows violating ma_label check; constraint not added';
                    END;
                END IF;
            END $$;

            -- Stocks-in-Play unified watchlist (#99 / ADR 0004 Phase 1,
            -- 2026-05-23). Three-axis maturity model captured here:
            --   1. Per-strategy phase: mi_strategies.phase (separate table)
            --   2. Per-stock maturity: stage = ready (this table is the
            --      "ready" state — earlier stages stay in detector-internal
            --      tables: mi_flag_candidates, mi_sugar_babies_cohort, etc.)
            --   3. Per-entry automation_class: column on this row
            -- See docs/decisions/0004-stocks-in-play-unified-watchlist.md
            -- + memory/project_stocks_in_play_architecture.md for full
            -- framing. source_detector / automation_class enums + validators
            -- live in agents/market_intelligence/stocks_in_play_sources.py
            -- (constants module — drift prevention pattern).
            CREATE TABLE IF NOT EXISTS mi_stocks_in_play (
                id SERIAL PRIMARY KEY,
                ticker TEXT NOT NULL,
                entry_date DATE NOT NULL,         -- ET date when ticker entered ready state
                source_detector TEXT NOT NULL,    -- VALID_SOURCES enum value
                automation_class TEXT NOT NULL,   -- informational | operator_only | apollo_eligible
                reason TEXT NOT NULL,             -- one-line human-readable
                readiness_signal JSONB,           -- detector-specific structured detail
                source_phase TEXT,                -- 'paper' | 'live' | 'shadow' at entry time
                expires_at TIMESTAMPTZ NOT NULL,  -- NOT NULL by design (Gemini contract)
                promoted_at TIMESTAMPTZ,          -- automation_class flip operator_only → apollo_eligible
                promoted_to_trade_at TIMESTAMPTZ, -- when this row became a real trade
                created_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE (ticker, entry_date, source_detector)
            );
            CREATE INDEX IF NOT EXISTS idx_stocks_in_play_date
                ON mi_stocks_in_play(entry_date DESC);
            CREATE INDEX IF NOT EXISTS idx_stocks_in_play_ticker
                ON mi_stocks_in_play(ticker, entry_date DESC);
            CREATE INDEX IF NOT EXISTS idx_stocks_in_play_class
                ON mi_stocks_in_play(automation_class, entry_date DESC);
            CREATE INDEX IF NOT EXISTS idx_stocks_in_play_expires
                ON mi_stocks_in_play(expires_at);
        """)

        # ── Strategy maturity registry ───────────────────────────────────
        # One row per strategy. `phase` controls whether entries are allowed
        # via the global gate; `enabled` is the user-facing on/off toggle.
        # `promotion_model` discriminates the verdict shape: paired_r (shadow
        # vs live counterpart), unpaired_r (R-based on own outcomes),
        # telemetry_review (no PnL — false-positive review).
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mi_strategies (
                strategy_id              TEXT PRIMARY KEY,
                name                     TEXT NOT NULL,
                family                   TEXT NOT NULL,
                phase                    TEXT NOT NULL,
                enabled                  BOOLEAN NOT NULL DEFAULT TRUE,
                live_real_enabled        BOOLEAN NOT NULL DEFAULT FALSE,
                signal_type              TEXT NOT NULL,
                outcomes_table           TEXT NOT NULL,
                promotion_model          TEXT NOT NULL,
                promotion_thresholds     JSONB NOT NULL,
                position_size_multiplier NUMERIC NOT NULL DEFAULT 1.0,
                max_concurrent_positions INT,
                notes                    TEXT,
                created_at               TIMESTAMPTZ DEFAULT NOW(),
                updated_at               TIMESTAMPTZ DEFAULT NOW(),
                CHECK (phase IN ('shadow','paper','live')),
                CHECK (promotion_model IN ('paired_r','unpaired_r','telemetry_review'))
            );

            CREATE TABLE IF NOT EXISTS mi_splits (
                ticker              TEXT NOT NULL,
                execution_date      DATE NOT NULL,
                split_from          INT  NOT NULL,
                split_to            INT  NOT NULL,
                polygon_id          TEXT,
                fetched_at          TIMESTAMPTZ DEFAULT NOW(),
                applied_at          TIMESTAMPTZ,
                adjustment_applied  BOOLEAN NOT NULL DEFAULT FALSE,
                PRIMARY KEY (ticker, execution_date)
            );
            CREATE INDEX IF NOT EXISTS idx_splits_unapplied
                ON mi_splits (execution_date DESC) WHERE adjustment_applied = FALSE;

            CREATE TABLE IF NOT EXISTS mi_weekly_watchlists (
                week_ending          DATE NOT NULL,
                ticker               TEXT NOT NULL,
                sources              JSONB NOT NULL,
                composite_priority   INT NOT NULL,
                reason_chip          TEXT NOT NULL,
                generated_at         TIMESTAMPTZ DEFAULT NOW(),
                PRIMARY KEY (week_ending, ticker)
            );
            CREATE INDEX IF NOT EXISTS idx_weekly_watchlists_ticker
                ON mi_weekly_watchlists (ticker, week_ending DESC);

            CREATE TABLE IF NOT EXISTS mi_orb_extension_shadow (
                id                   BIGSERIAL PRIMARY KEY,
                trade_id             INT NOT NULL,
                ticker               TEXT NOT NULL,
                alert_date           DATE NOT NULL,
                cutoff_minute        INT  NOT NULL,
                limit_price          NUMERIC,
                stop_price           NUMERIC,
                shares               INT,
                cancelled_at         TIMESTAMPTZ,
                would_fill           BOOLEAN,
                fill_at              TIMESTAMPTZ,
                fill_price           NUMERIC,
                entry_attempts       INT,
                state                JSONB,
                final_status         TEXT,
                closed_at            DATE,
                total_pnl            NUMERIC,
                hold_days            INT,
                last_close           NUMERIC,
                last_evaluated_date  DATE,
                created_at           TIMESTAMPTZ DEFAULT NOW(),
                updated_at           TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE (trade_id, cutoff_minute)
            );
            CREATE INDEX IF NOT EXISTS idx_orb_ext_shadow_open
                ON mi_orb_extension_shadow (final_status)
                WHERE final_status = 'still_open';
            CREATE INDEX IF NOT EXISTS idx_orb_ext_shadow_ticker
                ON mi_orb_extension_shadow (ticker, alert_date);
        """)

        # ── Migrations ───────────────────────────────────────────────────
        await conn.execute("""
            ALTER TABLE mi_live_trades
                ADD COLUMN IF NOT EXISTS entry_attempt INT NOT NULL DEFAULT 1;
            ALTER TABLE mi_live_trades
                ADD COLUMN IF NOT EXISTS signal_type TEXT;
            CREATE INDEX IF NOT EXISTS idx_live_trades_signal_type
                ON mi_live_trades(signal_type);
            ALTER TABLE mi_live_trades
                ADD COLUMN IF NOT EXISTS account_mode TEXT NOT NULL DEFAULT 'paper';
            CREATE INDEX IF NOT EXISTS idx_live_trades_account_mode
                ON mi_live_trades(account_mode);
            -- Per-strategy real-$ promotion gate. Independent from `phase`
            -- (which controls paper-vs-live routing). When account_mode=live
            -- AND live_real_enabled=False, proposals fire with a STAGED-PAPER
            -- header so the user can distinguish "ramping" strategies from
            -- promoted ones at confirmation time.
            ALTER TABLE mi_strategies
                ADD COLUMN IF NOT EXISTS live_real_enabled BOOLEAN NOT NULL DEFAULT FALSE;
            -- Per-strategy sizing + position cap (#65, 2026-05-10).
            -- position_size_multiplier: 1.0 = full Apollo sizing; 0.5 = half-size
            -- (e.g. for newly-promoted 9M Day 2 ramp). Applied in entry_pipeline
            -- post-spec-builder so it covers both prepare_orb_order and
            -- prepare_9m_day2_orb_order paths uniformly.
            -- max_concurrent_positions: NULL = share global MAX_CONCURRENT_LIVE_POSITIONS;
            -- integer = per-strategy slot cap on top of the global envelope.
            ALTER TABLE mi_strategies
                ADD COLUMN IF NOT EXISTS position_size_multiplier NUMERIC NOT NULL DEFAULT 1.0;
            ALTER TABLE mi_strategies
                ADD COLUMN IF NOT EXISTS max_concurrent_positions INT;
            -- Worst-price-vs-you / best-price-in-your-favor tracking
            -- (2026-05-10). Captures the lowest and highest market prices
            -- observed during a trade's open life. Populated at fill time
            -- (initialized to entry price) and updated every 5 min during
            -- market hours by track_open_position_extremes. Backfilled
            -- for historical closed trades via scripts/backfill_position_extremes.py.
            -- Use case: setup-quality analytics — does this setup
            -- consistently let trades run high before exit (good edge) or
            -- consistently drag near stop (tighten stop / drop setup)?
            ALTER TABLE mi_live_trades
                ADD COLUMN IF NOT EXISTS lowest_price_seen NUMERIC;
            ALTER TABLE mi_live_trades
                ADD COLUMN IF NOT EXISTS highest_price_seen NUMERIC;
            -- pnl_attribution: NULL = methodology (default). Non-NULL means
            -- the P&L on this row was distorted by a system bug, not the
            -- methodology being evaluated. Methodology-evaluation queries
            -- (Gate 3 R-expectancy, weekly review, future setup analytics)
            -- should filter `WHERE pnl_attribution IS NULL`. Account-safety
            -- queries (daily_loss_limit, drawdown breaker) should NOT filter
            -- — the actual P&L still hit the account. First use:
            -- 'incident_2026_05_14_naked_position' on CRMD #137.
            ALTER TABLE mi_live_trades
                ADD COLUMN IF NOT EXISTS pnl_attribution TEXT;
            ALTER TABLE mi_themes
                ADD COLUMN IF NOT EXISTS rs_avg FLOAT;
            ALTER TABLE mi_themes
                ADD COLUMN IF NOT EXISTS parent_theme TEXT;
            ALTER TABLE mi_themes
                ADD COLUMN IF NOT EXISTS days_active INT NOT NULL DEFAULT 0;
            ALTER TABLE mi_themes
                ADD COLUMN IF NOT EXISTS consecutive_accelerating INT NOT NULL DEFAULT 0;
            ALTER TABLE mi_themes
                ADD COLUMN IF NOT EXISTS pct_above_20sma REAL;
            ALTER TABLE mi_ticker_overrides
                ADD COLUMN IF NOT EXISTS sector TEXT;
            ALTER TABLE mi_ticker_overrides
                ADD COLUMN IF NOT EXISTS industry TEXT;
            ALTER TABLE mi_parabolic_candidates
                ADD COLUMN IF NOT EXISTS excluded_reason TEXT;
            ALTER TABLE mi_parabolic_candidates
                ADD COLUMN IF NOT EXISTS excluded_source TEXT;
            ALTER TABLE mi_parabolic_candidates
                ADD COLUMN IF NOT EXISTS excluded_detail TEXT;
            ALTER TABLE mi_live_orders
                ADD COLUMN IF NOT EXISTS purpose TEXT;
            ALTER TABLE mi_live_orders
                ADD COLUMN IF NOT EXISTS exit_reason TEXT;
            CREATE INDEX IF NOT EXISTS idx_live_orders_purpose
                ON mi_live_orders(purpose);
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

        # ── Backfill mi_live_trades.signal_type (one-shot; idempotent) ────
        # Pre-framework rows lack signal_type. Classify by alert provenance:
        # row appearing in mi_9m_day2_candidates for the same (ticker, date) is
        # 9M Day 2; everything else is MAGNA53. After this runs once, new
        # inserts via entry_pipeline.submit_trade_entry write signal_type
        # directly — no further backfill needed.
        await conn.execute("""
            UPDATE mi_live_trades lt
            SET signal_type = CASE
                WHEN EXISTS (
                    SELECT 1 FROM mi_9m_day2_candidates sb
                    WHERE sb.ticker = lt.ticker
                      AND sb.alert_date = lt.alert_date
                ) THEN '9m_day2'
                ELSE 'magna53'
            END
            WHERE signal_type IS NULL
        """)

        # ── Seed mi_strategies registry (idempotent on strategy_id) ───────
        await _seed_strategies_registry(conn)

        # ── Log row counts on startup for early data-loss detection ───────
        for tbl in ("mi_paper_trades", "mi_live_trades"):
            count = await conn.fetchval(f"SELECT COUNT(*) FROM {tbl}")
            logger.info(f"Startup row count: {tbl} = {count}")

    logger.info("Market Intelligence DB schema initialized")

    # Crypto RS module owns its own schema (crypto_* tables) — kept isolated
    # from mi_* equity tables. Idempotent.
    try:
        from agents.market_intelligence.crypto.db import initialize_crypto_schema
        await initialize_crypto_schema()
        logger.info("Crypto RS schema initialized")
    except Exception:
        logger.exception("Crypto RS schema init failed (non-fatal)")

    # Missed-EP opportunity-cost telemetry (forward returns on filtered /
    # MODERATE / HIGH-unentered alerts). Own schema for isolation.
    try:
        from agents.market_intelligence.missed_outcomes import ensure_missed_outcomes_schema
        await ensure_missed_outcomes_schema()
        logger.info("Missed-outcomes schema initialized")
    except Exception:
        logger.exception("Missed-outcomes schema init failed (non-fatal)")


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


_EP_ALERT_COLUMNS_ENSURED = False


async def _ensure_ep_alert_columns(conn) -> None:
    """Idempotent mi_ep_alerts column adds, ONCE per process (#247 — these ran
    on EVERY insert_ep_alert call: ~14 DDL round-trips per alerted candidate per
    5-min scan tick, all no-ops after the first). First insert after a deploy
    still creates new columns turnkey (no boot-order dependency); the module
    flag skips the DDL afterward. Restart-safe — the flag resets with the
    process and the ALTERs are IF NOT EXISTS.

    Column provenance: `source`/catalyst_type (#155/C1 advisory) ·
    in_active_theme/in_narrative_cohort (judge theme/narrative inputs) ·
    fire_status FROZEN historical + fire_axes judge-written (#249) ·
    grounded_text/baseline_floor_tier/judge_*/grade_engine_authority
    (#240/#243 holistic judge: corpus, floor counterfactual, verdict columns,
    and which engine drove the tier). Materiality shadow columns (#189/ADR
    0010) retired #249 — historical rows keep them, frozen."""
    global _EP_ALERT_COLUMNS_ENSURED
    if _EP_ALERT_COLUMNS_ENSURED:
        return
    # One ALTER, many ADD COLUMN clauses — a single round-trip instead of 14.
    await conn.execute("ALTER TABLE mi_ep_alerts " + ", ".join(
        f"ADD COLUMN IF NOT EXISTS {col}" for col in (
            "source TEXT DEFAULT 'live'",
            "catalyst_type TEXT",
            "catalyst_type_rationale TEXT",
            "in_active_theme BOOLEAN",
            "in_narrative_cohort BOOLEAN",
            "fire_status TEXT",
            "fire_axes TEXT[]",
            "grounded_text TEXT",
            "baseline_floor_tier TEXT",
            "judge_tier TEXT",
            "judge_direction TEXT",
            "judge_rationale TEXT",
            "judge_materiality_tier TEXT",
            "grade_engine_authority TEXT",
            "rubric_version TEXT",
        )))
    _EP_ALERT_COLUMNS_ENSURED = True


async def insert_ep_alert(record: dict[str, Any]) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await _ensure_ep_alert_columns(conn)
        await conn.execute("""
            INSERT INTO mi_ep_alerts
                (ticker, alert_date, gap_pct, rel_volume, ep_score, score_tier,
                 catalyst, catalyst_quality, claude_analysis, gemini_validation,
                 confidence_multiplier, vol_percentile, source,
                 pm_rvol, pm_rvol_baseline_n, detected_at,
                 catalyst_type, catalyst_type_rationale,
                 in_active_theme, in_narrative_cohort,
                 grounded_text, baseline_floor_tier, grade_engine_authority)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,
                    COALESCE($16::TIMESTAMPTZ, NOW()), $17, $18, $19,
                    $20, $21, $22, $23)
        """,
            record["ticker"], record["alert_date"], record["gap_pct"],
            record.get("rel_volume"), record["ep_score"], record["score_tier"],
            record.get("catalyst"), record.get("catalyst_quality"),
            record.get("claude_analysis"), record.get("gemini_validation"),
            record.get("confidence_multiplier", 1.0),
            record.get("vol_percentile"),
            record.get("source", "live"),
            record.get("pm_rvol"),
            record.get("pm_rvol_baseline_n"),
            record.get("detected_at"),
            record.get("catalyst_type"),
            record.get("catalyst_type_rationale"),
            record.get("in_active_theme"),
            record.get("in_narrative_cohort"),
            record.get("grounded_text"),
            record.get("baseline_floor_tier"),
            record.get("grade_engine_authority", "floor"),
        )


# SSoT for the judge-result statement (#265): executed by
# update_ep_alert_judge_result below AND prepared verbatim by the [5b/7]
# deploy gate (scripts/preflight_db_updates.py imports THIS constant), so the
# gate provably validates the SQL production runs — a copy can't go stale.
EP_ALERT_JUDGE_RESULT_UPDATE_SQL = """
    UPDATE mi_ep_alerts SET
        judge_tier = COALESCE($3, judge_tier),
        judge_direction = COALESCE($4, judge_direction),
        judge_rationale = COALESCE($5, judge_rationale),
        judge_materiality_tier = COALESCE($6, judge_materiality_tier),
        fire_axes = COALESCE($7, fire_axes),
        score_tier = COALESCE($8, score_tier),
        grade_engine_authority = COALESCE($9, grade_engine_authority),
        rubric_version = COALESCE($10, rubric_version)
    WHERE ticker = $1 AND alert_date = $2
"""


async def update_ep_alert_judge_result(
    ticker: str, alert_date: "date", *, judge_tier: str | None,
    judge_direction: str | None, judge_rationale: str | None,
    judge_materiality_tier: str | None,
    fire_axes: "list[str] | None" = None,
    score_tier: str | None = None,
    grade_engine_authority: str | None = None,
    rubric_version: str | None = None,
) -> None:
    """ONE atomic post-scan patch with the Holistic Grade Judge result (#240 /
    ADR 0011; merged from update_ep_alert_judge_shadow + the separate
    update_ep_alert_grade_override in #247, 2026-06-10 — two non-atomic UPDATEs
    to the same row left a partial-write window once the judge went
    load-bearing). Every column uses COALESCE: None = leave untouched, so the
    shadow case (verdict, no override), the override case (verdict +
    score_tier/authority), and the fail-open case (no verdict,
    authority='fallback' only) are all the same single statement. The judge
    call is the sole writer of the judge_* columns for a given alert, so
    COALESCE == SET in practice; fire_axes is judge-owned since #249.
    score_tier here is the LOAD-BEARING override (the field alert/entry/
    briefing read) — pass it ONLY from _resolve_grade_authority."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            EP_ALERT_JUDGE_RESULT_UPDATE_SQL,
            ticker, alert_date, judge_tier, judge_direction, judge_rationale,
            judge_materiality_tier, fire_axes, score_tier, grade_engine_authority,
            rubric_version)


_JUDGE_TOGGLE = ("holistic_judge_enabled", "paper")  # (safeguard, account_mode) PK


async def get_holistic_judge_enabled() -> bool:
    """W2b (#243 / ADR 0011): DB-backed kill switch for the Holistic Grade Judge's grade
    AUTHORITY. Durable across restarts (mi_safeguard_state), instant revert with NO redeploy.
    FAIL-CLOSED: any error or missing row → False (the conviction floor drives the grade). A
    toggle-read exception must NEVER default to judge — that is the load-bearing safety."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT state FROM mi_safeguard_state "
                "WHERE safeguard = $1 AND account_mode = $2", *_JUDGE_TOGGLE)
        return bool(row) and row["state"] == "on"
    except Exception as e:  # noqa: BLE001 — fail-closed to floor is the contract
        logger.warning(f"holistic_judge_enabled read failed → floor (fail-closed): {e}")
        return False


async def set_holistic_judge_enabled(enabled: bool) -> None:
    """Flip the Holistic Grade Judge authority toggle (OPERATOR-gated — the W2 go-live gate).
    Upserts the mi_safeguard_state row. Paper-only (the judge never touches real money)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO mi_safeguard_state (safeguard, account_mode, state,
                                            last_transition_at, updated_at)
            VALUES ($1, $2, $3, NOW(), NOW())
            ON CONFLICT (safeguard, account_mode) DO UPDATE
              SET state = EXCLUDED.state, last_transition_at = NOW(), updated_at = NOW()
        """, *_JUDGE_TOGGLE, "on" if enabled else "off")


# update_ep_alert_grade_override merged into update_ep_alert_judge_result
# (#247, 2026-06-10) — the judge_*-write + score_tier override are one atomic
# UPDATE now; the two-statement window is gone.


async def get_latest_ep_alert_judge(ticker: str) -> "dict | None":
    """Latest holistic-judge decision trace for a ticker (W2a/c #243 / ADR 0011 logging
    clause — the /setup + /why per-ticker surface). Returns floor vs judge tier, the engine
    that drove the grade, materiality, and the load-bearing rationale, or None if no graded
    alert / no judge row. Read-only; callers wrap fail-open so it never breaks /setup."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow("""
            SELECT alert_date, score_tier, baseline_floor_tier, grade_engine_authority,
                   judge_tier, judge_direction, judge_materiality_tier, judge_rationale
            FROM mi_ep_alerts
            WHERE ticker = $1 AND judge_tier IS NOT NULL
              AND COALESCE(source, 'live') = 'live'  -- #268: never present a replay verdict as the judge's last word
            ORDER BY alert_date DESC LIMIT 1
        """, ticker)


# LIVE-rows-only predicate for mi_ep_alerts (#268, 2026-06-11). Replay/backtest
# rows (source='historical_scan') share the table across a 12-month span with
# synthetic HIGH tiers — EVERY live read (cooldowns, KPIs, outcomes, history)
# must carry this filter or replay batches contaminate it. The 6/11 review
# found the live EP cooldown reading replay rows = real alerts suppressed.
LIVE_SOURCE_SQL = "COALESCE(source, 'live') = 'live'"

# Two-era "unknown catalyst" predicates over mi_ep_alerts (#211/#249) — the
# SINGLE composition consumed by /unknownrate (agent.py) and the weekly
# source-gap finder (source_gap_finder.py); edit HERE, never inline a copy.
# Era 1: fire_status = the retired heuristic's frozen historical rows
# (2026-06-08..10). Era 2: fire_axes = '{}' means the judge SAW NO fire on any
# axis (judge-written; NULL = judge fail-open / not adjudicated — deliberately
# excluded). Column names are unqualified — usable only where mi_ep_alerts
# columns resolve unambiguously.
EP_UNKNOWN_NONFIRE_SQL = (
    "(fire_status IN "
    "('unknown','pre_catalyst_anticipation','no_fire_confirmed','real_unknown')"
    " OR fire_axes = '{}')")
EP_UNKNOWN_MISS_SQL = (
    "(catalyst ILIKE '%no clear%catalyst%' OR catalyst ILIKE '%not clearly identified%' "
    "OR catalyst ILIKE '%no specific news%' OR catalyst ILIKE '%no fresh%catalyst%')")
EP_UNKNOWN_ANY_SQL = (
    f"(catalyst_type = 'unknown' OR {EP_UNKNOWN_NONFIRE_SQL} OR {EP_UNKNOWN_MISS_SQL})")


async def update_ep_alert_advisory(
    ticker: str, alert_date: "date", catalyst_type: str | None,
    rationale: str | None = None,
) -> None:
    """Post-scan ADVISORY patch on an EP alert row: catalyst_type (#155, Pradeep
    hierarchy). ADVISORY only — never gates entries. Called post-scan (decoupled
    from the gating path). COALESCE keeps the existing value when a field is
    NULL, so a None catalyst_type (classifier fail-open) never clobbers a prior
    value. Columns are guaranteed by insert_ep_alert (runs earlier in the same
    scan) — no ADD COLUMN here. The fire-panel params (#201) were retired
    2026-06-10 (#249): fire_axes is judge-written (update_ep_alert_judge_result).
    """
    if not catalyst_type:
        return
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE mi_ep_alerts SET
                catalyst_type = COALESCE($3, catalyst_type),
                catalyst_type_rationale = COALESCE($4, catalyst_type_rationale)
            WHERE ticker = $1 AND alert_date = $2
        """, ticker, alert_date, catalyst_type, rationale)


# ── Operator ground-truth corpus (#254) ─────────────────────────────────────────
# Unified telemetry table: operator review-labels (kind='review') + externally-spotted
# EP injections (kind='injected', e.g. an FSLR tweet). READ-ONLY re trade state — pure
# annotation, never a trade trigger. kind IS in the unique key so hindsight-selected
# injected rows stay PHYSICALLY SEPARATE from point-in-time-clean review rows (#167);
# Phase-2 grade-precedent retrieval must filter kind='review' only.
GROUND_TRUTH_GRADES = frozenset(
    {"game_changer", "strong", "routine", "mna", "none", "not_ep"})
GROUND_TRUTH_VERDICTS = frozenset({"agree", "toohigh", "toolow", "notep"})
GROUND_TRUTH_ROOT_CAUSES = frozenset({
    "judge_correct", "sourcing_gap", "theme_axis_blank", "detection_bug",
    "materiality_noise", "model_divergence", "gap_data_error", "other",
})


async def ensure_ep_ground_truth_table() -> None:
    """Idempotently create mi_ep_ground_truth (turnkey first-use, no migration step).
    Called at the top of every writer/reader so the table exists on first command."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mi_ep_ground_truth (
                id             SERIAL PRIMARY KEY,
                ticker         TEXT NOT NULL,
                event_date     DATE NOT NULL,
                kind           TEXT NOT NULL,        -- 'review' | 'injected'
                verdict        TEXT,                 -- review rows: agree|toohigh|toolow|notep
                operator_grade TEXT,                 -- game_changer|strong|routine|mna|none|not_ep
                system_tier    TEXT,                 -- what the system graded (NULL = uncaught/pre-judge)
                root_cause     TEXT,                 -- judge_correct|sourcing_gap|... (review rows)
                narrative      TEXT,                 -- catalyst story (load-bearing for injected)
                source         TEXT,                 -- 'review'|'tweet:@handle'|'operator'|'system'
                reviewed_by    TEXT,
                created_at     TIMESTAMPTZ DEFAULT now(),
                updated_at     TIMESTAMPTZ DEFAULT now(),
                UNIQUE (ticker, event_date, kind)
            )
        """)


async def snapshot_system_tier(ticker: str, event_date: "date") -> str | None:
    """What tier did the system grade this ticker on this date? Prefers the holistic
    judge tier, falls back to the floor/score tier. NULL if no alert that day (uncaught
    — the recall-gap signal that makes an injected EP a coverage miss)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # judge_tier is post-W1; COALESCE tolerates its absence on old rows.
        # LIVE rows only (2026-06-11): replay/backtest rows (source=
        # 'historical_scan', #268) carry synthetic tiers — without this filter
        # an injected ground-truth case would snapshot the REPLAY verdict and
        # mask a real live coverage miss (found on MNTS 5/26: live filtered it,
        # replay row said judge=none — the snapshot must say NULL/uncaught).
        row = await conn.fetchrow("""
            SELECT COALESCE(judge_tier, score_tier) AS tier
            FROM mi_ep_alerts
            WHERE ticker = $1 AND alert_date = $2
              AND COALESCE(source, 'live') = 'live'
            ORDER BY detected_at DESC NULLS LAST
            LIMIT 1
        """, ticker, event_date)
    return row["tier"] if row else None


async def upsert_ep_ground_truth(
    *, ticker: str, event_date: "date", kind: str,
    verdict: str | None = None, operator_grade: str | None = None,
    system_tier: str | None = None, root_cause: str | None = None,
    narrative: str | None = None, source: str | None = None,
    reviewed_by: str | None = None,
) -> dict:
    """UPSERT one operator judgment on (ticker, event_date, kind). Re-review / re-inject
    updates in place (operator ask #1 'correct poor decisions'). Returns the stored row.
    READ-ONLY re trade state (annotation table, no trade effect).

    Two update disciplines, deliberately split:
    - verdict + root_cause are a COUPLED 'current statement', recomputed on EVERY review
      (verdict is always supplied) → plain SET. COALESCE here would strand a contradictory
      row: an agree→judge_correct row re-reviewed as toohigh (root_cause=None) would KEEP
      judge_correct forever, since no later non-agree verdict ever supplies a cause.
    - operator_grade / system_tier / narrative / source / reviewed_by CAN be legitimately
      omitted on a re-review → COALESCE keeps the prior value."""
    await ensure_ep_ground_truth_table()
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO mi_ep_ground_truth
                (ticker, event_date, kind, verdict, operator_grade, system_tier,
                 root_cause, narrative, source, reviewed_by, updated_at)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10, now())
            ON CONFLICT (ticker, event_date, kind) DO UPDATE SET
                verdict        = EXCLUDED.verdict,
                root_cause     = EXCLUDED.root_cause,
                operator_grade = COALESCE(EXCLUDED.operator_grade, mi_ep_ground_truth.operator_grade),
                system_tier    = COALESCE(EXCLUDED.system_tier, mi_ep_ground_truth.system_tier),
                narrative      = COALESCE(EXCLUDED.narrative, mi_ep_ground_truth.narrative),
                source         = COALESCE(EXCLUDED.source, mi_ep_ground_truth.source),
                reviewed_by    = COALESCE(EXCLUDED.reviewed_by, mi_ep_ground_truth.reviewed_by),
                updated_at     = now()
            RETURNING ticker, event_date, kind, verdict, operator_grade, system_tier,
                      root_cause, narrative, source, reviewed_by, created_at, updated_at
        """, ticker, event_date, kind, verdict, operator_grade, system_tier,
            root_cause, narrative, source, reviewed_by)
    return dict(row)


async def get_recent_ground_truth(limit: int = 15) -> list[dict]:
    """Recent ground-truth rows, newest-updated first (read surface for /reviews)."""
    await ensure_ep_ground_truth_table()
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT ticker, event_date, kind, verdict, operator_grade, system_tier,
                   root_cause, narrative, source, reviewed_by, updated_at
            FROM mi_ep_ground_truth
            ORDER BY updated_at DESC
            LIMIT $1
        """, limit)
    return [dict(r) for r in rows]


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


# ── 9M EP System ───────────────────────────────────────────────────────────────


async def insert_9m_ep_alert(record: dict[str, Any]) -> bool:
    """
    Insert intraday 9M EP detection.
    Returns True if newly inserted, False if ticker already alerted today (UNIQUE constraint).
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute("""
            INSERT INTO mi_9m_ep_alerts
                (ticker, alert_date, detection_time, today_volume, projected_vol,
                 current_price, gap_pct, is_anticipation)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (ticker, alert_date) DO NOTHING
        """,
            record["ticker"],
            record["alert_date"] if isinstance(record["alert_date"], date) else date.fromisoformat(record["alert_date"]),
            record["detection_time"],
            record["today_volume"],
            record.get("projected_vol"),
            record["current_price"],
            record["gap_pct"],
            record.get("is_anticipation", False),
        )
    return result.split()[-1] != "0"  # "INSERT 0 0" vs "INSERT 0 1"


async def get_today_9m_ep_alerts(d: "str | date") -> list[dict]:
    """Fetch all 9M EP alerts for a given date, ordered by volume desc."""
    pool = await get_pool()
    if isinstance(d, str):
        d = date.fromisoformat(d)
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT ticker, alert_date, detection_time, today_volume, projected_vol,
                   current_price, gap_pct, is_anticipation, created_at
            FROM mi_9m_ep_alerts
            WHERE alert_date = $1
            ORDER BY today_volume DESC
        """, d)
    return [dict(r) for r in rows]


async def insert_9m_sugar_baby(record: dict[str, Any]) -> None:
    """Upsert a confirmed 9M sugar baby (EOD sweep result).

    Going-in shape metrics (prev_5d_pct … prior_sessions) are optional — legacy
    callers that only pass the 8 base fields get NULLs. get_eod_9m_sugar_babies
    populates them from the SQL CTEs.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO mi_9m_day2_candidates
                (ticker, alert_date, open_price, close_price, high_price, low_price,
                 volume, close_in_range_pct,
                 prev_5d_pct, prev_20d_pct, prev_vs_sma10, prev_vs_sma50,
                 sma50_slope_pct, prior_sessions)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
            ON CONFLICT (ticker, alert_date) DO UPDATE SET
                open_price         = EXCLUDED.open_price,
                close_price        = EXCLUDED.close_price,
                high_price         = EXCLUDED.high_price,
                low_price          = EXCLUDED.low_price,
                volume             = EXCLUDED.volume,
                close_in_range_pct = EXCLUDED.close_in_range_pct,
                prev_5d_pct        = EXCLUDED.prev_5d_pct,
                prev_20d_pct       = EXCLUDED.prev_20d_pct,
                prev_vs_sma10      = EXCLUDED.prev_vs_sma10,
                prev_vs_sma50      = EXCLUDED.prev_vs_sma50,
                sma50_slope_pct    = EXCLUDED.sma50_slope_pct,
                prior_sessions     = EXCLUDED.prior_sessions
        """,
            record["ticker"],
            record["alert_date"] if isinstance(record["alert_date"], date) else date.fromisoformat(record["alert_date"]),
            record["open_price"],
            record["close_price"],
            record["high_price"],
            record["low_price"],
            record["volume"],
            record["close_in_range_pct"],
            record.get("prev_5d_pct"),
            record.get("prev_20d_pct"),
            record.get("prev_vs_sma10"),
            record.get("prev_vs_sma50"),
            record.get("sma50_slope_pct"),
            record.get("prior_sessions"),
        )


async def get_eod_9m_sugar_babies(trade_date: "str | date") -> list[dict]:
    """
    Fetch stocks from mi_daily_closes that qualify as 9M sugar babies for a given date.
    Criteria mirror intraday ninem_detector gates so both paths agree:
      volume >= 9M, close >= $5, dollar_volume >= $50M, open/high/low present,
      close > open, (close - low) / (high - low) >= 0.75, volume >= 3× ADV,
      intraday range >= 2% of close (rejects merger-arb pins like DBRG),
      prev_close <= 1.20× prior 10d SMA (rejects day-N+ chase runners like BB;
        measured at yesterday's close, not today's, so fresh breakouts like VELO
        still qualify — going-into-the-9M-day extension, not today's move).
    Requires at least 10 prior sessions of history — rejects Day-1 IPOs
    (NHP case 2026-04-22) where there is no ADV reference, no 10d SMA for the
    extension gate, and no stable prior-day low to anchor a Day 2 ORB stop.
    Unknown security type still passes conservatively (ticker not yet ingested
    into mi_security_types but otherwise has ≥10 sessions of price history).
    Returns up to 20, ordered by volume desc.
    """
    pool = await get_pool()
    if isinstance(trade_date, str):
        trade_date = date.fromisoformat(trade_date)
    async with pool.acquire() as conn:
        rows = await conn.fetch(_NINEM_CONTEXT_CTE + """
            SELECT d.ticker, d.close AS close_price, d.open_price, d.high_price, d.low_price, d.volume,
                   m.prev_close,
                   CASE WHEN (d.high_price - d.low_price) > 0
                        THEN (d.close - d.low_price) / (d.high_price - d.low_price)
                        ELSE NULL END AS close_in_range_pct,
                   -- Going-in shape metrics (prev_close vs prior windows)
                   CASE WHEN m.close_5d_ago IS NOT NULL AND m.close_5d_ago > 0
                        THEN (m.prev_close - m.close_5d_ago) / m.close_5d_ago * 100.0
                        ELSE NULL END AS prev_5d_pct,
                   CASE WHEN m.close_20d_ago IS NOT NULL AND m.close_20d_ago > 0
                        THEN (m.prev_close - m.close_20d_ago) / m.close_20d_ago * 100.0
                        ELSE NULL END AS prev_20d_pct,
                   CASE WHEN m.sma_10 > 0 THEN m.prev_close / m.sma_10 ELSE NULL END AS prev_vs_sma10,
                   CASE WHEN m.sma_50 > 0 THEN m.prev_close / m.sma_50 ELSE NULL END AS prev_vs_sma50,
                   CASE WHEN m.sma_50_5d_ago IS NOT NULL AND m.sma_50_5d_ago > 0
                        THEN (m.sma_50 - m.sma_50_5d_ago) / m.sma_50_5d_ago * 100.0
                        ELSE NULL END AS sma50_slope_pct,
                   m.prior_sessions
            FROM mi_daily_closes d
            LEFT JOIN mi_security_types st ON st.ticker = d.ticker
            LEFT JOIN adv a ON a.ticker = d.ticker
            LEFT JOIN ctx m ON m.ticker = d.ticker
            WHERE d.trade_date = $1
              AND (st.security_type IN ('CS', 'ADRC') OR st.ticker IS NULL)
              AND d.volume >= 9000000
              AND d.close >= 5.0
              AND (d.volume * d.close) >= 50000000
              AND d.open_price IS NOT NULL
              AND d.high_price IS NOT NULL
              AND d.low_price IS NOT NULL
              AND d.close > d.open_price
              -- Directional gates (`is_9m_directional`, `is_green_close`) applied
              -- in Python after fetch — do NOT inline them here. Single source of
              -- truth lives in ninem_detector.py.
              AND (d.high_price - d.low_price) > 0
              AND (d.close - d.low_price) / (d.high_price - d.low_price) >= 0.75
              -- Require ≥10 prior sessions — rejects Day-1 IPOs (NHP 2026-04-22).
              -- Without 10+ sessions, the ADV ratio is meaningless and the 10d SMA
              -- for extension doesn't exist. The prior-day low (Day 2 ORB stop
              -- anchor) is also the IPO-day low, which is structurally unstable.
              AND a.adv_20 IS NOT NULL
              AND m.sma_10 IS NOT NULL
              AND m.prev_close IS NOT NULL
              AND d.volume >= (a.adv_20 * 3)
              -- Intraday range must be ≥ 2% of close (rejects merger-arb pins)
              AND (d.high_price - d.low_price) >= (d.close * 0.02)
              -- Extension gate: prev_close ≤ 1.20× prior 10d SMA (measures how extended
              -- the stock was going INTO the 9M day, not after it). Fresh breakouts pass.
              AND m.prev_close <= m.sma_10 * 1.20
            ORDER BY d.volume DESC
            LIMIT 20
        """, trade_date)
    # Apply canonical directional gates from ninem_detector — single source of
    # truth shared with the intraday alerter. Imported lazily to avoid circular
    # imports (ninem_detector imports from db).
    from agents.market_intelligence.ninem_detector import is_9m_directional, is_green_close
    return [
        dict(r) for r in rows
        if is_9m_directional(float(r["prev_close"]), float(r["open_price"]), float(r["close_price"]))
        and is_green_close(float(r["prev_close"]), float(r["close_price"]))
    ]


async def get_sugar_babies_cohort_latest(limit: int = 30) -> list[dict]:
    """Return current persistent Sugar Babies cohort (Pradeep-class watchlist).
    Tickers that printed 9M+ EOD vol ≥3 times in trailing 180d, LEFT JOINed
    to mi_flag_candidates for each ticker's most-recent flag stage in last
    5 calendar days (Memorial Day weekend compresses this to 2 trading
    scans — acceptable for prototype; ADR will harden to trading-session
    subquery when generalizing to mi_stocks_in_play).

    Sort order (ripeness-first, info-overload reduction):
      TRIGGERED (3) > COILED (2) > TIGHTENING (1) > no-flag (0)
      tiebreaker: count_9m_alerts_180d DESC, then last_9m_alert DESC

    Returned dict gains 3 new fields: current_flag_stage, flag_stage_scan_date,
    flag_base_age (all None for cohort members without recent flag activity).
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            WITH latest_cohort AS (
                SELECT MAX(cohort_date) AS d FROM mi_sugar_babies_cohort
            ),
            latest_flag AS (
                SELECT DISTINCT ON (ticker)
                       ticker, scan_date, stage, base_age
                FROM mi_flag_candidates
                WHERE scan_date >= CURRENT_DATE - INTERVAL '5 days'
                  AND stage IN ('COILED', 'TIGHTENING', 'TRIGGERED')
                ORDER BY ticker, scan_date DESC
            )
            SELECT c.ticker,
                   c.count_9m_alerts_180d AS n,
                   c.first_9m_alert_in_window,
                   c.last_9m_alert,
                   c.latest_volume,
                   c.latest_gap_pct,
                   f.stage     AS current_flag_stage,
                   f.scan_date AS flag_stage_scan_date,
                   f.base_age  AS flag_base_age,
                   CASE f.stage WHEN 'TRIGGERED'  THEN 3
                                WHEN 'COILED'     THEN 2
                                WHEN 'TIGHTENING' THEN 1
                                ELSE 0 END AS ripeness
            FROM mi_sugar_babies_cohort c
            LEFT JOIN latest_flag f ON f.ticker = c.ticker
            WHERE c.cohort_date = (SELECT d FROM latest_cohort)
            ORDER BY ripeness DESC,
                     c.count_9m_alerts_180d DESC,
                     c.last_9m_alert DESC
            LIMIT $1
        """, limit)
    return [dict(r) for r in rows]


async def upsert_stocks_in_play(
    *,
    ticker: str,
    source_detector: str,
    automation_class: str,
    reason: str,
    readiness_signal: dict | None = None,
    source_phase: str | None = None,
    expires_at,  # timezone-aware datetime
    entry_date=None,  # defaults to ET today
) -> None:
    """Upsert a row into mi_stocks_in_play (ADR 0004 Phase 1).

    Per source_detector enum: validates source + class via constants module
    (drift prevention). Per ADR 0004 §3: expires_at NOT NULL by design;
    every caller MUST set it explicitly with a detector-appropriate TTL.

    UPSERT semantics: re-firing within the same (ticker, entry_date,
    source_detector) replaces expires_at + readiness_signal + reason
    (latest detection's state wins; never re-fires automation_class).
    """
    from agents.market_intelligence.stocks_in_play_sources import (
        validate_source, validate_class,
    )
    from agents.market_intelligence.collector import et_today
    validate_source(source_detector)
    validate_class(automation_class)
    if entry_date is None:
        entry_date = et_today()
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO mi_stocks_in_play (
                ticker, entry_date, source_detector, automation_class,
                reason, readiness_signal, source_phase, expires_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (ticker, entry_date, source_detector) DO UPDATE
                SET reason = EXCLUDED.reason,
                    readiness_signal = EXCLUDED.readiness_signal,
                    expires_at = EXCLUDED.expires_at,
                    source_phase = COALESCE(EXCLUDED.source_phase, mi_stocks_in_play.source_phase)
        """, ticker, entry_date, source_detector, automation_class,
            reason, readiness_signal, source_phase, expires_at)


async def get_stocks_in_play(
    *,
    automation_class: str | None = None,
    source_detector: str | None = None,
    active_only: bool = True,
) -> list[dict]:
    """Return mi_stocks_in_play rows (ADR 0004 Phase 1 read helper).

    active_only=True (default): only rows where expires_at > NOW().
    automation_class: filter by 'informational' / 'operator_only' /
                     'apollo_eligible'. None = all classes.
    source_detector: filter by single source_detector value. None = all.

    Rows are ordered by automation_class (apollo_eligible first), then
    entry_date DESC. Multi-detector entries on same ticker render as
    multiple rows; caller aggregates per-ticker if needed.
    """
    where = []
    args: list = []
    if active_only:
        where.append("expires_at > NOW()")
    if automation_class:
        args.append(automation_class)
        where.append(f"automation_class = ${len(args)}")
    if source_detector:
        args.append(source_detector)
        where.append(f"source_detector = ${len(args)}")
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(f"""
            SELECT ticker, entry_date, source_detector, automation_class,
                   reason, readiness_signal, source_phase, expires_at,
                   promoted_at, promoted_to_trade_at, created_at
            FROM mi_stocks_in_play
            {where_sql}
            ORDER BY
                CASE automation_class
                    WHEN 'apollo_eligible' THEN 1
                    WHEN 'operator_only' THEN 2
                    ELSE 3
                END,
                entry_date DESC,
                ticker
        """, *args)
    return [dict(r) for r in rows]


async def check_sugar_baby_convergence(ticker: str) -> dict | None:
    """Return Sugar Baby Convergence dict if ticker is in latest persistent
    Sugar Babies cohort AND has been in COILED/TIGHTENING/TRIGGERED stage
    within last 5 calendar days. Else None.

    Returned dict shape:
        cohort_n            INT  — count_9m_alerts_180d for this ticker
        flag_stage          TEXT — TRIGGERED | COILED | TIGHTENING
        stage_scan_date     DATE — most-recent qualifying scan_date
        days_since_stage    INT  — CURRENT_DATE - stage_scan_date
        convergence_class   TEXT — 'breakout' if TRIGGERED else 'anticipatory'

    Caller MUST wrap in try/except — telemetry failure (pool exhaustion,
    asyncpg transient) cannot break the underlying EP/9M alert (the
    trading signal). Helper itself only raises on DB-level errors; missing
    cohort or missing recent flag stage both return None cleanly.

    Note: 5 *calendar* days via `INTERVAL '5 days'`. Memorial Day weekend
    compresses this to ~2 trading scans — acceptable for prototype scope.
    ADR will harden to trading-session subquery when generalizing to
    mi_stocks_in_play.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            WITH latest_cohort_date AS (
                SELECT MAX(cohort_date) AS d FROM mi_sugar_babies_cohort
            ),
            in_cohort AS (
                SELECT count_9m_alerts_180d
                FROM mi_sugar_babies_cohort
                WHERE ticker = $1
                  AND cohort_date = (SELECT d FROM latest_cohort_date)
            ),
            recent_flag AS (
                SELECT stage, scan_date,
                       (CURRENT_DATE - scan_date)::int AS days_since
                FROM mi_flag_candidates
                WHERE ticker = $1
                  AND scan_date >= CURRENT_DATE - INTERVAL '5 days'
                  AND stage IN ('COILED', 'TIGHTENING', 'TRIGGERED')
                ORDER BY scan_date DESC
                LIMIT 1
            )
            SELECT c.count_9m_alerts_180d AS cohort_n,
                   f.stage                AS flag_stage,
                   f.scan_date            AS stage_scan_date,
                   f.days_since           AS days_since_stage,
                   CASE WHEN f.stage = 'TRIGGERED' THEN 'breakout'
                        ELSE 'anticipatory' END AS convergence_class
            FROM in_cohort c
            CROSS JOIN recent_flag f
        """, ticker)
    return dict(row) if row else None


async def get_eod_9m_wick_candidates(trade_date: "str | date") -> list[dict]:
    """Wick-fill candidates (P22): 9M day, green body, close in [0.50, 0.75)
    of intraday range. Same gates as sugar babies — only the range-position
    branch differs. Telemetry-only; Day 2 break of prior_high is the
    canonical short-trap fill (Bonde / Kristjan negated shooting star).
    Returns up to 20, ordered by volume desc.
    """
    pool = await get_pool()
    if isinstance(trade_date, str):
        trade_date = date.fromisoformat(trade_date)
    async with pool.acquire() as conn:
        rows = await conn.fetch(_NINEM_CONTEXT_CTE + """
            SELECT d.ticker, d.close AS close_price, d.open_price,
                   d.high_price, d.low_price, d.volume,
                   d.high_price AS prior_high,
                   m.prev_close,
                   CASE WHEN (d.high_price - d.low_price) > 0
                        THEN (d.close - d.low_price) / (d.high_price - d.low_price)
                        ELSE NULL END AS close_in_range_pct,
                   CASE WHEN m.close_5d_ago IS NOT NULL AND m.close_5d_ago > 0
                        THEN (m.prev_close - m.close_5d_ago) / m.close_5d_ago * 100.0
                        ELSE NULL END AS prev_5d_pct,
                   CASE WHEN m.close_20d_ago IS NOT NULL AND m.close_20d_ago > 0
                        THEN (m.prev_close - m.close_20d_ago) / m.close_20d_ago * 100.0
                        ELSE NULL END AS prev_20d_pct,
                   CASE WHEN m.sma_10 > 0 THEN m.prev_close / m.sma_10 ELSE NULL END AS prev_vs_sma10,
                   CASE WHEN m.sma_50 > 0 THEN m.prev_close / m.sma_50 ELSE NULL END AS prev_vs_sma50,
                   CASE WHEN m.sma_50_5d_ago IS NOT NULL AND m.sma_50_5d_ago > 0
                        THEN (m.sma_50 - m.sma_50_5d_ago) / m.sma_50_5d_ago * 100.0
                        ELSE NULL END AS sma50_slope_pct,
                   m.prior_sessions
            FROM mi_daily_closes d
            LEFT JOIN mi_security_types st ON st.ticker = d.ticker
            LEFT JOIN adv a ON a.ticker = d.ticker
            LEFT JOIN ctx m ON m.ticker = d.ticker
            WHERE d.trade_date = $1
              AND (st.security_type IN ('CS', 'ADRC') OR st.ticker IS NULL)
              AND d.volume >= 9000000
              AND d.close >= 5.0
              AND (d.volume * d.close) >= 50000000
              AND d.open_price IS NOT NULL
              AND d.high_price IS NOT NULL
              AND d.low_price IS NOT NULL
              AND d.close > d.open_price
              AND (d.high_price - d.low_price) > 0
              -- Mid-range upper-wick close. Three-way EOD branch:
              --   ≥ 0.75 → sugar baby; [0.50, 0.75) → wick; < 0.50 → distribution.
              AND (d.close - d.low_price) / (d.high_price - d.low_price) >= 0.50
              AND (d.close - d.low_price) / (d.high_price - d.low_price) <  0.75
              AND a.adv_20 IS NOT NULL
              AND m.sma_10 IS NOT NULL
              AND m.sma_50 IS NOT NULL
              AND m.prev_close IS NOT NULL
              AND d.volume >= (a.adv_20 * 3)
              AND (d.high_price - d.low_price) >= (d.close * 0.02)
              AND m.prev_close <= m.sma_10 * 1.20
              -- Trend floor: reject crash-recovery candidates. A wick-trap
              -- needs a structurally intact uptrend so shorts entered on the
              -- upper wick are actually trapped. VISN 4/29 (post -50% gap)
              -- passed every single-bar gate but had prev_vs_sma50=0.55.
              AND m.prev_close >= m.sma_50 * 0.85
            ORDER BY d.volume DESC
            LIMIT 20
        """, trade_date)
    from agents.market_intelligence.ninem_detector import is_9m_directional, is_green_close
    return [
        dict(r) for r in rows
        if is_9m_directional(float(r["prev_close"]), float(r["open_price"]), float(r["close_price"]))
        and is_green_close(float(r["prev_close"]), float(r["close_price"]))
    ]


async def insert_wick_candidate(record: dict[str, Any]) -> None:
    """Upsert a wick candidate from EOD sweep. Forward-return fields stay
    NULL — populated later by wick_tracker.update_forward_returns once
    the 10d horizon has settled.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO mi_wick_candidates
                (ticker, alert_date, open_price, close_price, high_price, low_price,
                 volume, close_in_range_pct, prior_high,
                 prev_5d_pct, prev_20d_pct, prev_vs_sma10, prev_vs_sma50,
                 sma50_slope_pct, prior_sessions)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
            ON CONFLICT (ticker, alert_date) DO UPDATE SET
                open_price         = EXCLUDED.open_price,
                close_price        = EXCLUDED.close_price,
                high_price         = EXCLUDED.high_price,
                low_price          = EXCLUDED.low_price,
                volume             = EXCLUDED.volume,
                close_in_range_pct = EXCLUDED.close_in_range_pct,
                prior_high         = EXCLUDED.prior_high,
                prev_5d_pct        = EXCLUDED.prev_5d_pct,
                prev_20d_pct       = EXCLUDED.prev_20d_pct,
                prev_vs_sma10      = EXCLUDED.prev_vs_sma10,
                prev_vs_sma50      = EXCLUDED.prev_vs_sma50,
                sma50_slope_pct    = EXCLUDED.sma50_slope_pct,
                prior_sessions     = EXCLUDED.prior_sessions
        """,
            record["ticker"],
            record["alert_date"] if isinstance(record["alert_date"], date) else date.fromisoformat(record["alert_date"]),
            record["open_price"],
            record["close_price"],
            record["high_price"],
            record["low_price"],
            record["volume"],
            record["close_in_range_pct"],
            record["prior_high"],
            record.get("prev_5d_pct"),
            record.get("prev_20d_pct"),
            record.get("prev_vs_sma10"),
            record.get("prev_vs_sma50"),
            record.get("sma50_slope_pct"),
            record.get("prior_sessions"),
        )


async def get_unsettled_wick_candidates(today: "str | date") -> list[dict]:
    """Wick rows whose 10d forward return isn't measured yet. Sweep job
    retries each day until the horizon settles. Bounded 20-day lookback
    so we don't re-scan ancient rows that never got their fwd window
    (early-table data, manual deletions).
    """
    pool = await get_pool()
    if isinstance(today, str):
        today = date.fromisoformat(today)
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, ticker, alert_date, prior_high, close_price
            FROM mi_wick_candidates
            WHERE alert_date < $1
              AND fwd_10d_from_close_pct IS NULL
              AND alert_date >= $1 - INTERVAL '20 days'
            ORDER BY alert_date ASC
        """, today)
    return [dict(r) for r in rows]


async def update_wick_forward_returns(
    candidate_id: int,
    *,
    filled_wick: bool | None,
    fill_date: "date | None",
    fwd_1d_from_high_pct: float | None,
    fwd_3d_from_high_pct: float | None,
    fwd_10d_from_high_pct: float | None,
    fwd_1d_from_close_pct: float | None,
    fwd_3d_from_close_pct: float | None,
    fwd_10d_from_close_pct: float | None,
) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE mi_wick_candidates
               SET filled_wick            = $1,
                   fill_date              = $2,
                   fwd_1d_from_high_pct   = $3,
                   fwd_3d_from_high_pct   = $4,
                   fwd_10d_from_high_pct  = $5,
                   fwd_1d_from_close_pct  = $6,
                   fwd_3d_from_close_pct  = $7,
                   fwd_10d_from_close_pct = $8
             WHERE id = $9
        """, filled_wick, fill_date,
             fwd_1d_from_high_pct, fwd_3d_from_high_pct, fwd_10d_from_high_pct,
             fwd_1d_from_close_pct, fwd_3d_from_close_pct, fwd_10d_from_close_pct,
             candidate_id)


async def get_wick_candidates_window(window_days: int) -> list[dict]:
    """Wick candidates with all stored fields, used by the strategy adapter
    and `/wick` Telegram surface."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT ticker, alert_date, open_price, close_price, high_price,
                   low_price, volume, close_in_range_pct, prior_high,
                   prev_5d_pct, prev_20d_pct, prev_vs_sma10, prev_vs_sma50,
                   sma50_slope_pct, prior_sessions,
                   filled_wick, fill_date,
                   fwd_1d_from_high_pct, fwd_3d_from_high_pct, fwd_10d_from_high_pct,
                   fwd_1d_from_close_pct, fwd_3d_from_close_pct, fwd_10d_from_close_pct
            FROM mi_wick_candidates
            WHERE alert_date >= CURRENT_DATE - $1::int
            ORDER BY alert_date DESC, volume DESC
        """, window_days)
    return [dict(r) for r in rows]


async def get_wick_pending_candidates(lookback_sessions: int = 3) -> list[dict]:
    """Forward-looking wick candidates: `filled_wick IS NULL` (sweep hasn't
    closed the row — the 10-session forward window isn't complete yet) AND
    price hasn't already broken `prior_high` (so the setup is still
    actionable for next-session entry).

    Lookback is in trading sessions, not calendar days — `recent_sessions`
    CTE selects DISTINCT trade_date from `mi_daily_closes` so prior-Friday
    wicks remain visible Mon/Tue/Wed without weekend off-by-one.

    The `NOT EXISTS` clause closes the already-filled blind spot: between
    the day a wick fires and the day the 5:45 PM sweep marks it filled,
    intraday breaks of `prior_high` would otherwise still surface here as
    "pending."
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            WITH recent_sessions AS (
                SELECT DISTINCT trade_date FROM mi_daily_closes
                WHERE trade_date <= CURRENT_DATE
                ORDER BY trade_date DESC
                LIMIT $1
            ),
            cutoff AS (SELECT MIN(trade_date) AS cutoff_date FROM recent_sessions)
            SELECT w.ticker, w.alert_date, w.close_price, w.high_price,
                   w.prior_high, w.close_in_range_pct, w.prev_5d_pct, w.volume
            FROM mi_wick_candidates w
            CROSS JOIN cutoff
            WHERE w.alert_date >= cutoff.cutoff_date
              AND w.filled_wick IS NULL
              AND NOT EXISTS (
                  SELECT 1 FROM mi_daily_closes d
                  WHERE d.ticker = w.ticker
                    AND d.trade_date > w.alert_date
                    AND d.high_price >= w.prior_high
              )
            ORDER BY w.alert_date DESC, w.volume DESC
        """, lookback_sessions)
    return [dict(r) for r in rows]


async def insert_fishhook_anchor(record: dict[str, Any]) -> None:
    """Idempotent insert of a freshly-detected fishhook anchor (state='pending').

    UNIQUE (ticker, anchor_date) — repeat EOD passes for the same date are
    safe; existing rows are not touched (state-machine transitions go
    through `update_fishhook_anchor`, not this function).
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO mi_fishhook_anchors
                (ticker, anchor_date, prev_close, anchor_open, anchor_close,
                 gap_pct, in_top2000, in_ep_alerts, state)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'pending')
            ON CONFLICT (ticker, anchor_date) DO NOTHING
        """,
            record["ticker"],
            record["anchor_date"] if isinstance(record["anchor_date"], date)
                else date.fromisoformat(record["anchor_date"]),
            record["prev_close"],
            record["anchor_open"],
            record["anchor_close"],
            record["gap_pct"],
            record["in_top2000"],
            record["in_ep_alerts"],
        )


async def get_open_fishhook_anchors(today: "str | date") -> list[dict]:
    """Anchors in non-terminal states (pending/promoted/reclaimed) — the
    EOD pass walks each forward to advance state. Bounded lookback prevents
    sweeping ancient orphans that never settled (early-table noise).
    """
    pool = await get_pool()
    if isinstance(today, str):
        today = date.fromisoformat(today)
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, ticker, anchor_date, prev_close, anchor_open,
                   anchor_close, gap_pct, in_top2000, in_ep_alerts, state,
                   washout_low, washout_session_offset, drift_pct_max,
                   promoted_session_offset, reclaim_session_offset,
                   reclaim_open, reclaim_close, reclaim_open_vs_anchor_pct,
                   actual_entry_price
            FROM mi_fishhook_anchors
            WHERE state IN ('pending', 'promoted', 'reclaimed')
              AND anchor_date >= $1::date - INTERVAL '60 days'
            ORDER BY anchor_date ASC
        """, today)
    return [dict(r) for r in rows]


_FISHHOOK_UPDATE_ALLOWED = {
    "state",
    "washout_low", "washout_session_offset", "drift_pct_max",
    "promoted_session_offset",
    "reclaim_session_offset", "reclaim_open", "reclaim_close",
    "reclaim_open_vs_anchor_pct", "actual_entry_price",
    "fwd_1d_high_pct", "fwd_3d_high_pct", "fwd_5d_high_pct",
    "fwd_10d_high_pct", "fwd_5d_close_pct",
    "r_5d", "invalidated_within_5d", "n_fwd_sessions_available",
}


async def update_fishhook_anchor(anchor_id: int, **fields) -> None:
    """Partial update on an anchor row. Keys must be in the allow-list."""
    if not fields:
        return
    sets = []
    args: list[Any] = []
    for k, v in fields.items():
        if k not in _FISHHOOK_UPDATE_ALLOWED:
            continue
        args.append(v)
        sets.append(f"{k} = ${len(args)}")
    if not sets:
        return
    args.append(anchor_id)
    sql = (
        f"UPDATE mi_fishhook_anchors SET {', '.join(sets)}, updated_at = NOW() "
        f"WHERE id = ${len(args)}"
    )
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(sql, *args)


async def get_fishhook_outcomes_window(window_days: int) -> list[dict]:
    """All anchors within the trailing window — used by the strategy adapter
    and `/fishhook` Telegram surface. Includes every state so the adapter
    can map terminal-vs-pending; downstream slices by state itself.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, ticker, anchor_date, prev_close, anchor_open,
                   anchor_close, gap_pct, in_top2000, in_ep_alerts, state,
                   washout_low, washout_session_offset, drift_pct_max,
                   promoted_session_offset, reclaim_session_offset,
                   reclaim_open, reclaim_close, reclaim_open_vs_anchor_pct,
                   actual_entry_price,
                   fwd_1d_high_pct, fwd_3d_high_pct, fwd_5d_high_pct,
                   fwd_10d_high_pct, fwd_5d_close_pct,
                   r_5d, invalidated_within_5d, n_fwd_sessions_available,
                   created_at, updated_at
            FROM mi_fishhook_anchors
            WHERE anchor_date >= CURRENT_DATE - $1::int
            ORDER BY anchor_date DESC, ticker
        """, window_days)
    return [dict(r) for r in rows]


async def get_pending_9m_sugar_babies(trade_date: "str | date") -> list[dict]:
    """
    Fetch confirmed sugar babies from a given date with day2_status='pending'.
    Used at 9:31 AM to populate the Day 2 ORB watchlist.
    Returns ticker, low_price (= stop for Day 2 entry), and all OHLCV fields.
    """
    pool = await get_pool()
    if isinstance(trade_date, str):
        trade_date = date.fromisoformat(trade_date)
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, ticker, alert_date, open_price, close_price, high_price,
                   low_price, volume, close_in_range_pct,
                   prev_5d_pct, prev_20d_pct, prev_vs_sma10, prev_vs_sma50,
                   sma50_slope_pct, prior_sessions
            FROM mi_9m_day2_candidates
            WHERE alert_date = $1 AND day2_status = 'pending'
            ORDER BY volume DESC
        """, trade_date)
    return [dict(r) for r in rows]


async def get_all_9m_sugar_babies(trade_date: "str | date") -> list[dict]:
    """
    All sugar babies from a given date regardless of day2_status — used by
    /9m and /pregame so Day 2 candidates remain visible after their ORB orders
    fire (status flips pending→traded and they'd otherwise vanish).
    """
    pool = await get_pool()
    if isinstance(trade_date, str):
        trade_date = date.fromisoformat(trade_date)
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, ticker, alert_date, open_price, close_price, high_price,
                   low_price, volume, close_in_range_pct, day2_status,
                   prev_5d_pct, prev_20d_pct, prev_vs_sma10, prev_vs_sma50,
                   sma50_slope_pct, prior_sessions
            FROM mi_9m_day2_candidates
            WHERE alert_date = $1
            ORDER BY volume DESC
        """, trade_date)
    return [dict(r) for r in rows]


async def update_9m_sugar_baby_status(ticker: str, alert_date: "str | date", status: str) -> None:
    """Update day2_status for a sugar baby ('traded' or 'skipped')."""
    pool = await get_pool()
    if isinstance(alert_date, str):
        alert_date = date.fromisoformat(alert_date)
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE mi_9m_day2_candidates SET day2_status = $1
            WHERE ticker = $2 AND alert_date = $3
        """, status, ticker, alert_date)


async def get_9m_ep_history(days: int = 14) -> list[dict]:
    """
    Recent 9M sugar baby records for the agent query handler.
    Returns alert + sugar baby data joined, ordered by date desc then volume desc.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT sb.ticker, sb.alert_date, sb.volume, sb.close_price,
                   sb.low_price, sb.close_in_range_pct, sb.day2_status,
                   sb.prev_5d_pct, sb.prev_20d_pct, sb.prev_vs_sma10,
                   sb.prev_vs_sma50, sb.sma50_slope_pct, sb.prior_sessions,
                   a.today_volume AS intraday_volume, a.gap_pct
            FROM mi_9m_day2_candidates sb
            LEFT JOIN mi_9m_ep_alerts a
                ON a.ticker = sb.ticker AND a.alert_date = sb.alert_date
            WHERE sb.alert_date >= (now() AT TIME ZONE 'America/New_York')::date - $1::int
            ORDER BY sb.alert_date DESC, sb.volume DESC
        """, days)
    return [dict(r) for r in rows]


async def get_market_cap(ticker: str) -> Optional[dict[str, Any]]:
    """Read cached market cap. Returns {market_cap, fetched_at} or None."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT market_cap, fetched_at FROM mi_market_caps WHERE ticker = $1",
            ticker,
        )
    return dict(row) if row else None


async def upsert_market_cap(ticker: str, market_cap: Optional[int]) -> None:
    """Write/refresh cached market cap. NULL is a valid value (FMP didn't return one)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO mi_market_caps (ticker, market_cap, fetched_at)
            VALUES ($1, $2, NOW())
            ON CONFLICT (ticker) DO UPDATE SET
                market_cap = EXCLUDED.market_cap,
                fetched_at = EXCLUDED.fetched_at
        """, ticker, market_cap)


async def get_recent_daily_history(
    ticker: str, days: int, end_date: "date | None" = None,
) -> list[dict]:
    """Last N calendar days of OHLCV for one ticker, oldest first.

    `end_date` defaults to today ET — pass a historical date to replay the
    scan against an earlier snapshot (essential for backfill validation).
    Returns [] if ticker has no rows.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        if end_date is None:
            rows = await conn.fetch("""
                SELECT trade_date, open_price, high_price, low_price, close, volume
                FROM mi_daily_closes
                WHERE ticker = $1
                  AND trade_date >= (now() AT TIME ZONE 'America/New_York')::date - $2::int
                ORDER BY trade_date ASC
            """, ticker, days)
        else:
            rows = await conn.fetch("""
                SELECT trade_date, open_price, high_price, low_price, close, volume
                FROM mi_daily_closes
                WHERE ticker = $1
                  AND trade_date <= $2
                  AND trade_date >= $2 - $3::int
                ORDER BY trade_date ASC
            """, ticker, end_date, days)
    return [dict(r) for r in rows]


async def get_parabolic_universe(trade_date: "str | date") -> list[str]:
    """Cheap pre-filter for the parabolic-short scan: returns tickers that COULD
    pass the full compute. Real gating happens per-ticker in Python.

    Filters applied in SQL (intentionally permissive — false positives are fine,
    they hit the per-ticker compute and resolve to `unqualified`):
      - CS/ADRC only (or unknown — rejects ETFs/funds via mi_security_types)
      - close ≥ $5, dollar_vol ≥ $10M today (matches detector Gate 1)
      - close ≥ 1.5 × SMA-50 (matches detector Gate 3 exactly)
      - close ≥ 1.5 × MIN(low) over last 60d (loose proxy for Gate 2 — even
        large-cap 50% threshold passes; small-cap 200% will be rejected per-ticker)
      - prior_sessions ≥ 60 (need history for SMA-50 + base anchor walk)

    Returns ticker list. Typical day: ~50-200 candidates from ~9000 universe.
    """
    pool = await get_pool()
    if isinstance(trade_date, str):
        trade_date = date.fromisoformat(trade_date)
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            WITH ranked AS (
                SELECT ticker, close, low_price,
                       ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY trade_date DESC) AS rn
                FROM mi_daily_closes
                WHERE trade_date <= $1
                  AND trade_date >= $1 - INTERVAL '120 days'
            ),
            ctx AS (
                SELECT ticker,
                       AVG(close)      FILTER (WHERE rn <= 50) AS sma_50,
                       MIN(low_price)  FILTER (WHERE rn <= 60) AS low_60d,
                       COUNT(*)        AS prior_sessions
                FROM ranked
                GROUP BY ticker
                HAVING COUNT(*) >= 60
            )
            SELECT d.ticker
            FROM mi_daily_closes d
            LEFT JOIN mi_security_types st ON st.ticker = d.ticker
            INNER JOIN ctx m ON m.ticker = d.ticker
            WHERE d.trade_date = $1
              AND (st.security_type IN ('CS', 'ADRC') OR st.ticker IS NULL)
              AND d.close >= 5.0
              AND (d.volume * d.close) >= 10000000
              AND m.sma_50 > 0
              AND d.close / m.sma_50 >= 1.5
              AND m.low_60d > 0
              AND d.close / m.low_60d >= 1.5
            ORDER BY d.close / m.sma_50 DESC
        """, trade_date)
    return [r["ticker"] for r in rows]


async def insert_parabolic_candidate(record: dict[str, Any]) -> None:
    """Upsert a parabolic-short scan result. Persists every metric (not just the
    boolean stage) so thresholds can be re-tuned against historical scans.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO mi_parabolic_candidates
                (ticker, scan_date, market_cap, cap_tier, prior_move_pct, base_date,
                 ext_vs_sma20, ext_vs_sma50, roc_5d, roc_20d, pullback_count_20d,
                 days_up_streak, gap_count_3d, range_expansion_count_3d,
                 vol_expansion_count_3d, gapped_today, climax_volume_flag,
                 score, stage, is_earnings_today)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14,
                    $15, $16, $17, $18, $19, $20)
            ON CONFLICT (ticker, scan_date) DO UPDATE SET
                market_cap                = EXCLUDED.market_cap,
                cap_tier                  = EXCLUDED.cap_tier,
                prior_move_pct            = EXCLUDED.prior_move_pct,
                base_date                 = EXCLUDED.base_date,
                ext_vs_sma20              = EXCLUDED.ext_vs_sma20,
                ext_vs_sma50              = EXCLUDED.ext_vs_sma50,
                roc_5d                    = EXCLUDED.roc_5d,
                roc_20d                   = EXCLUDED.roc_20d,
                pullback_count_20d        = EXCLUDED.pullback_count_20d,
                days_up_streak            = EXCLUDED.days_up_streak,
                gap_count_3d              = EXCLUDED.gap_count_3d,
                range_expansion_count_3d  = EXCLUDED.range_expansion_count_3d,
                vol_expansion_count_3d    = EXCLUDED.vol_expansion_count_3d,
                gapped_today              = EXCLUDED.gapped_today,
                climax_volume_flag        = EXCLUDED.climax_volume_flag,
                score                     = EXCLUDED.score,
                stage                     = EXCLUDED.stage,
                is_earnings_today         = EXCLUDED.is_earnings_today
        """,
            record["ticker"],
            record["scan_date"] if isinstance(record["scan_date"], date) else date.fromisoformat(record["scan_date"]),
            record.get("market_cap"),
            record.get("cap_tier"),
            record.get("prior_move_pct"),
            record.get("base_date"),
            record.get("ext_vs_sma20"),
            record.get("ext_vs_sma50"),
            record.get("roc_5d"),
            record.get("roc_20d"),
            record.get("pullback_count_20d"),
            record.get("days_up_streak"),
            record.get("gap_count_3d"),
            record.get("range_expansion_count_3d"),
            record.get("vol_expansion_count_3d"),
            record.get("gapped_today"),
            record.get("climax_volume_flag"),
            record.get("score"),
            record["stage"],
            record.get("is_earnings_today"),
        )


async def get_flag_universe(scan_date: "str | date") -> dict[str, list[str]]:
    """Pre-filter for the continuation-flag scan: top-RS common stock OR
    burst-class names, with usable liquidity and ≥60 sessions of history.
    Per-ticker pivot walk + state machine runs in Python on the survivors.

    Returns: {ticker: [universe_source_tags]} so the caller can record
    which patterns admitted each ticker (P7.2 audit trail 2026-05-17).
    Multi-source admission preserved — a ticker in top-200 RS AND R3-
    stopped captures both tags.

    Inclusion paths (UNION, OR-style):
      (a) **Top-200 RS** — Qullamaggie thesis is trading leaders. Tag: `rs_top200`
      (b) **Burst inclusion** — rs_1m percentile ≥ 80 OR last_close ≥ 25%
          above trailing 10-session **min close** (i.e. +25% off the lowest
          close in the last 10 sessions, NOT a trailing-10 return). Catches
          names like OKLO that have a violent recent runup but get dragged
          out of top-200 by 6M underperformance (OKLO 2026-05-04: rank 981
          because raw_6m=-7.4%, but rs_1m=94.3). In practice rs_1m≥80 is
          the dominant burst path; the low-anchored 25% gate fires rarely
          on top of that and is near-inert as a coverage extender. The flag
          detector's pivot anchor handles burst names well — gating them
          out at the universe layer was structurally inverting coverage.
          Tags: `rs_1m_80`, `momentum_25pct`
      (c) **MAGNA53 carryforward** (P7.2 2026-05-17) — R3-stopped MAGNA53
          names in last 7d. Stopped-out names that recently had a +25%
          intraday move get fed into the flag detector's tightness state
          machine to catch the eventual anticipation breakout. Tag:
          `magna53_failed_r3`. Env flag `MAGNA53_FLAG_CARRYFORWARD_ENABLED`.
      (d) **9M universe-watch** (P7.3b 2026-05-17, Pradeep methodology) —
          ALL 9M EPs (sugar baby + failed-Day-2 + intraday-only) in last
          14d. Per Pradeep, 9M volume = ~1% of stocks; the event itself
          is a watchlist trigger, not a directional signal. Entry comes
          from the tightness→expansion lifecycle (flag detector's
          domain). Tag: `ninem_universe_watch`. Env flag
          `NINEM_FLAG_CARRYFORWARD_ENABLED`. 14-day window for multi-
          week tightness observation.
      (e) **Flag-stage carryforward** (2026-05-19 RVMD-class fix) —
          tickers in active setup stages (COILED, TIGHTENING) in last
          5 trading days stay in universe even if RS gates fail today.
          The flag detector's purpose is catching consolidating leaders
          BEFORE breakout; knocking out RVMD-class names (3 consecutive
          COILED days, rs_3m=94 elite) on a one-day rs_1m percentile
          dip (85.6→70.3 from rotation) is structurally inverted. Tag:
          `flag_stage_carryforward`. Env flag
          `FLAG_STAGE_CARRYFORWARD_ENABLED`. 5-day window bridges
          multi-day RS dips while aging out genuinely-broken setups
          (state machine handles correctness — carryforward either
          re-establishes COILED/TIGHTENING or progresses to INVALIDATED).

    Common gates (organic paths a+b share):
      - CS/ADRC only (rejects ETFs/funds via mi_security_types)
      - close ≥ $5 (avoid microcaps where bar noise dominates)
      - 20d dollar volume ≥ $5M
      - prior_sessions ≥ 60 (need history for runup math)

    Carryforward paths (c+) bypass dollar_vol/close gates only insofar as
    they're added to the universe — the flag detector's compute_flag_metrics
    runs the same per-ticker eligibility checks regardless of source.
    """
    import os

    pool = await get_pool()
    if isinstance(scan_date, str):
        scan_date = date.fromisoformat(scan_date)

    # Per-ticker source tags. We collect from each path, then merge.
    source_map: dict[str, list[str]] = {}

    async with pool.acquire() as conn:
        # ── Paths (a) + (b): organic top-RS / burst inclusion ─────────
        organic_rows = await conn.fetch("""
            WITH ranked AS (
                SELECT ticker, close, volume,
                       ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY trade_date DESC) AS rn
                FROM mi_daily_closes
                WHERE trade_date <= $1
                  AND trade_date >= $1 - INTERVAL '90 days'
            ),
            ctx AS (
                SELECT ticker,
                       AVG(close * volume) FILTER (WHERE rn <= 20) AS dollar_vol_20d,
                       MAX(close)          FILTER (WHERE rn = 1)  AS last_close,
                       MIN(close)          FILTER (WHERE rn <= 10) AS trailing10_min,
                       COUNT(*)            AS prior_sessions
                FROM ranked
                GROUP BY ticker
                HAVING COUNT(*) >= 60
            ),
            scored AS (
                SELECT s.ticker, s.rs_rank, s.rs_1m
                FROM mi_stock_scores s
                WHERE s.score_date = (
                        SELECT MAX(score_date) FROM mi_stock_scores WHERE score_date <= $1
                      )
                  AND s.rs_1m IS NOT NULL
            )
            SELECT scored.ticker,
                   -- Source tags as booleans (Python collapses to TEXT[] below)
                   (scored.rs_rank IS NOT NULL AND scored.rs_rank <= 200) AS is_rs_top200,
                   (scored.rs_1m >= 80) AS is_rs_1m_80,
                   (m.trailing10_min > 0 AND (m.last_close / m.trailing10_min - 1) >= 0.25) AS is_momentum_25pct
            FROM scored
            LEFT JOIN mi_security_types st ON st.ticker = scored.ticker
            INNER JOIN ctx m ON m.ticker = scored.ticker
            INNER JOIN mi_daily_closes d ON d.ticker = scored.ticker AND d.trade_date = $1
            WHERE (st.security_type IN ('CS', 'ADRC') OR st.ticker IS NULL)
              AND d.close >= 5.0
              AND m.dollar_vol_20d >= 5000000
              AND (
                    (scored.rs_rank IS NOT NULL AND scored.rs_rank <= 200)
                    OR scored.rs_1m >= 80
                    OR (m.trailing10_min > 0
                        AND (m.last_close / m.trailing10_min - 1) >= 0.25)
                  )
            ORDER BY COALESCE(scored.rs_rank, 99999) ASC
        """, scan_date)
        for r in organic_rows:
            sources = []
            if r["is_rs_top200"]:
                sources.append("rs_top200")
            if r["is_rs_1m_80"]:
                sources.append("rs_1m_80")
            if r["is_momentum_25pct"]:
                sources.append("momentum_25pct")
            source_map[r["ticker"]] = sources

        # ── Path (c): MAGNA53 carryforward (P7.2 2026-05-17) ───────────
        r3_enabled = os.environ.get(
            "MAGNA53_FLAG_CARRYFORWARD_ENABLED", "true"
        ).lower() == "true"
        if r3_enabled:
            r3_rows = await conn.fetch("""
                SELECT DISTINCT ticker
                FROM mi_live_trades
                WHERE alert_date >= ($1::date - INTERVAL '7 days')
                  AND alert_date < $1::date
                  AND status = 'closed'
                  AND skip_reason = 'block:r3_reentry_disabled'
                  AND account_mode = 'paper'
            """, scan_date)
            for r in r3_rows:
                source_map.setdefault(r["ticker"], []).append("magna53_failed_r3")

        # ── Path (d): 9M universe-watch (P7.3b 2026-05-17) ─────────────
        # Per Pradeep methodology (memory:
        # user_pradeep_9m_universe_methodology.md): 9M EP = universe-to-
        # watch trigger, NOT directional signal. Entry comes from
        # tightness→expansion (flag-class pattern). ALL 9M EPs (intraday
        # alerts + EOD sugar babies + failed-Day-2 + skipped) get fed
        # into the flag detector's universe. The flag detector's state
        # machine handles the tightness→expansion lifecycle that
        # produces the eventual entry.
        # 14-day rolling window — multi-week tightness observation.
        # Source: mi_9m_ep_alerts (NOT mi_9m_day2_candidates; Day-2-candidate
        # filter is unrelated to the watchlist decision).
        ninem_enabled = os.environ.get(
            "NINEM_FLAG_CARRYFORWARD_ENABLED", "true"
        ).lower() == "true"
        if ninem_enabled:
            ninem_rows = await conn.fetch("""
                SELECT DISTINCT ticker
                FROM mi_9m_ep_alerts
                WHERE alert_date >= ($1::date - INTERVAL '14 days')
                  AND alert_date <= $1::date
            """, scan_date)
            for r in ninem_rows:
                source_map.setdefault(r["ticker"], []).append("ninem_universe_watch")

        # ── Path (e): flag-stage carryforward (2026-05-19 RVMD-class fix) ──
        # Tickers that were in active setup stages (COILED, TIGHTENING) in
        # the last 5 trading days stay in the universe even if their RS
        # gates fail today. The flag detector's whole purpose is catching
        # consolidating leaders before breakout — knocking RVMD-class names
        # (3 consecutive COILED days, tight $141-$151 range, rs_3m=94 still
        # elite) out of the universe when their rs_1m percentile dipped
        # below 80 on a one-day rotation is structurally inverted.
        #
        # 5-day window: long enough to bridge multi-day RS dips, short
        # enough to age out stale setups that genuinely broke down.
        # State machine handles correctness — carried-forward tickers
        # either re-establish COILED/TIGHTENING (consolidation continued)
        # or progress to INVALIDATED (base broke). Universe expansion
        # alone doesn't change detection rules.
        #
        # Env flag for safety / quick revert. Trigger: RVMD 2026-05-19
        # dropped from universe (rs_rank 321→499, rs_1m 85.6→70.3 in one
        # day) despite 3 consecutive COILED scans.
        flag_carry_enabled = os.environ.get(
            "FLAG_STAGE_CARRYFORWARD_ENABLED", "true"
        ).lower() == "true"
        if flag_carry_enabled:
            stage_carry_rows = await conn.fetch("""
                SELECT DISTINCT ticker
                FROM mi_flag_candidates
                WHERE scan_date < $1::date
                  AND scan_date >= ($1::date - INTERVAL '5 days')
                  AND stage IN ('COILED', 'TIGHTENING')
            """, scan_date)
            for r in stage_carry_rows:
                source_map.setdefault(r["ticker"], []).append("flag_stage_carryforward")

    return source_map


async def insert_flag_candidate(record: dict[str, Any]) -> None:
    """Upsert a continuation-flag scan result. Persists every metric
    (including unqualified rows) so thresholds re-tune offline against
    historical scans without re-running."""
    pool = await get_pool()
    scan_date = record["scan_date"]
    if isinstance(scan_date, str):
        scan_date = date.fromisoformat(scan_date)
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO mi_flag_candidates
                (ticker, scan_date, pivot_high_date, pivot_high_price, base_age,
                 base_high, base_low, runup_pct, runup_start_date,
                 range_contraction_ratio, vol_contraction_ratio,
                 last_body_pct, prev_body_pct, atr_14, sma_10, sma_20,
                 breakout_close, breakout_volume_ratio,
                 rs_rank, rs_composite, sector,
                 stage, reason, score, held_from_stage,
                 fresh_tight_fires, fresh_2bar_tr_pct, atr14_pct,
                 rmv_5d, rmv_15d, universe_sources)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
                    $13, $14, $15, $16, $17, $18, $19, $20, $21, $22,
                    $23, $24, $25, $26, $27, $28, $29, $30, $31)
            ON CONFLICT (ticker, scan_date) DO UPDATE SET
                pivot_high_date         = EXCLUDED.pivot_high_date,
                pivot_high_price        = EXCLUDED.pivot_high_price,
                base_age                = EXCLUDED.base_age,
                base_high               = EXCLUDED.base_high,
                base_low                = EXCLUDED.base_low,
                runup_pct               = EXCLUDED.runup_pct,
                runup_start_date        = EXCLUDED.runup_start_date,
                range_contraction_ratio = EXCLUDED.range_contraction_ratio,
                vol_contraction_ratio   = EXCLUDED.vol_contraction_ratio,
                last_body_pct           = EXCLUDED.last_body_pct,
                prev_body_pct           = EXCLUDED.prev_body_pct,
                atr_14                  = EXCLUDED.atr_14,
                sma_10                  = EXCLUDED.sma_10,
                sma_20                  = EXCLUDED.sma_20,
                breakout_close          = EXCLUDED.breakout_close,
                breakout_volume_ratio   = EXCLUDED.breakout_volume_ratio,
                rs_rank                 = EXCLUDED.rs_rank,
                rs_composite            = EXCLUDED.rs_composite,
                sector                  = EXCLUDED.sector,
                stage                   = EXCLUDED.stage,
                reason                  = EXCLUDED.reason,
                score                   = EXCLUDED.score,
                held_from_stage         = EXCLUDED.held_from_stage,
                fresh_tight_fires       = EXCLUDED.fresh_tight_fires,
                fresh_2bar_tr_pct       = EXCLUDED.fresh_2bar_tr_pct,
                atr14_pct               = EXCLUDED.atr14_pct,
                rmv_5d                  = EXCLUDED.rmv_5d,
                rmv_15d                 = EXCLUDED.rmv_15d,
                universe_sources        = EXCLUDED.universe_sources
        """,
            record["ticker"],
            scan_date,
            record.get("pivot_high_date"),
            record.get("pivot_high_price"),
            record.get("base_age"),
            record.get("base_high"),
            record.get("base_low"),
            record.get("runup_pct"),
            record.get("runup_start_date"),
            record.get("range_contraction_ratio"),
            record.get("vol_contraction_ratio"),
            record.get("last_body_pct"),
            record.get("prev_body_pct"),
            record.get("atr_14"),
            record.get("sma_10"),
            record.get("sma_20"),
            record.get("breakout_close"),
            record.get("breakout_volume_ratio"),
            record.get("rs_rank"),
            record.get("rs_composite"),
            record.get("sector"),
            record["stage"],
            record.get("reason"),
            record.get("score"),
            record.get("held_from_stage"),
            record.get("fresh_tight_fires"),
            record.get("fresh_2bar_tr_pct"),
            record.get("atr14_pct"),
            record.get("rmv_5d"),
            record.get("rmv_15d"),
            record.get("universe_sources") or [],
        )


async def enqueue_pending_allocation(
    ticker: str,
    alert_date: "str | date",
    strategy: str,
    composite_score: float,
    raw_dimensions: dict[str, Any],
) -> None:
    """Cross-strategy allocator (#31) — strategies emit RankableCandidate rows
    during their daily scan. Shadow phase: legacy submission still runs;
    allocator reads this queue at 9:28 AM ET and emits audit-only telemetry.
    UPSERT — same (ticker, alert_date, strategy) on a re-scan refreshes
    the score without exploding row count. `raw_dimensions` JSONB carries
    setup/catalyst/volume/regime breakdown for offline tune.
    """
    if isinstance(alert_date, str):
        alert_date = date.fromisoformat(alert_date)
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO mi_pending_allocations
                (ticker, alert_date, strategy, composite_score, raw_dimensions)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (ticker, alert_date, strategy)
            DO UPDATE SET
                composite_score = EXCLUDED.composite_score,
                raw_dimensions  = EXCLUDED.raw_dimensions,
                created_at      = NOW()
        """, ticker, alert_date, strategy, composite_score,
             json.dumps(raw_dimensions))


async def get_pending_allocations_for_date(
    alert_date: "str | date",
) -> list[dict[str, Any]]:
    """Drain queue for the allocator pre-market job. Returns all candidates
    enqueued for `alert_date` with status='pending', most-recent enqueue
    first within each strategy."""
    if isinstance(alert_date, str):
        alert_date = date.fromisoformat(alert_date)
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, ticker, alert_date, strategy, composite_score,
                   raw_dimensions, status, created_at
            FROM mi_pending_allocations
            WHERE alert_date = $1 AND status = 'pending'
            ORDER BY strategy, composite_score DESC
        """, alert_date)
    return [dict(r) for r in rows]


async def mark_pending_allocations_evaluated(
    ids: list[int],
    selected_ids: list[int],
) -> None:
    """Stamp rows post-evaluation: shadow_rank set per scoring order,
    shadow_allocated=True for the top-N picks. Status stays 'pending' in
    Phase 1A (shadow) so legacy submission paths still see fresh rows;
    will flip to 'allocated'/'rejected' in Phase 1B (active)."""
    if not ids:
        return
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Rank: order in `ids` is the scored order (best first).
            for rank, row_id in enumerate(ids, start=1):
                await conn.execute("""
                    UPDATE mi_pending_allocations
                    SET shadow_rank = $2,
                        shadow_allocated = $3,
                        evaluated_at = NOW()
                    WHERE id = $1
                """, row_id, rank, row_id in selected_ids)


async def get_open_position_count() -> int:
    """Count of currently-open live positions (filled or in-flight orders).
    Mirrors the count `_check_safeguards` uses for MAX_CONCURRENT_LIVE_POSITIONS,
    so the cross-strategy allocator's slot math matches the live safeguard.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT COUNT(*) AS n FROM mi_live_trades
            WHERE status IN ('filled', 'order_placed', 'pending_confirmation', 'confirmed')
        """)
    return int(row["n"] or 0) if row else 0


async def get_yesterday_flag_stages(scan_date: "str | date") -> dict[str, str]:
    """Map ticker → most recent prior stage, for hysteresis carry-forward.
    Looks back up to 5 sessions so weekend/holiday gaps don't reset stage
    state. Returns {} if no prior rows."""
    pool = await get_pool()
    if isinstance(scan_date, str):
        scan_date = date.fromisoformat(scan_date)
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT DISTINCT ON (ticker) ticker, stage
            FROM mi_flag_candidates
            WHERE scan_date < $1
              AND scan_date >= $1 - INTERVAL '5 days'
            ORDER BY ticker, scan_date DESC
        """, scan_date)
    return {r["ticker"]: r["stage"] for r in rows}


async def get_yesterday_flag_pivots(
    scan_date: "str | date",
) -> dict[str, tuple[date, float]]:
    """Map ticker → (pivot_high_date, pivot_high_price) from the most recent
    prior scan that had a real pivot anchor. Mirrors get_yesterday_flag_stages
    shape (5-day lookback so Mon picks up Fri's row across weekends/holidays).
    Filters NULL pivot fields — `unqualified` rows from the no_pivot_in_lookback
    branch persist without anchors and must NOT seed stable-anchor logic.
    Returns {} if no prior rows.
    """
    pool = await get_pool()
    if isinstance(scan_date, str):
        scan_date = date.fromisoformat(scan_date)
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT DISTINCT ON (ticker) ticker, pivot_high_date, pivot_high_price
            FROM mi_flag_candidates
            WHERE scan_date < $1
              AND scan_date >= $1 - INTERVAL '5 days'
              AND pivot_high_date IS NOT NULL
              AND pivot_high_price IS NOT NULL
            ORDER BY ticker, scan_date DESC
        """, scan_date)
    return {r["ticker"]: (r["pivot_high_date"], float(r["pivot_high_price"])) for r in rows}


async def get_recent_flag_stages(scan_date: "str | date", lookback_days: int = 5) -> dict[str, list[str]]:
    """Per-ticker stage history (most recent last) over the last
    `lookback_days` scans before `scan_date`. Used for the TRIGGERED gate
    ("was COILED in the last 5 days") so a 1-day relapse to TIGHTENING
    doesn't disqualify a clean breakout."""
    pool = await get_pool()
    if isinstance(scan_date, str):
        scan_date = date.fromisoformat(scan_date)
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT ticker, stage, scan_date
            FROM mi_flag_candidates
            WHERE scan_date < $1
              AND scan_date >= $1 - ($2::int || ' days')::interval
            ORDER BY ticker, scan_date ASC
        """, scan_date, lookback_days)
    out: dict[str, list[str]] = {}
    for r in rows:
        out.setdefault(r["ticker"], []).append(r["stage"])
    return out


async def get_flag_candidates_window(
    scan_date: "str | date",
    stages: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Fetch all flag rows for `scan_date`, optionally filtered by stage.
    Used by the Telegram digest + on-demand `/flags` query."""
    pool = await get_pool()
    if isinstance(scan_date, str):
        scan_date = date.fromisoformat(scan_date)
    async with pool.acquire() as conn:
        if stages:
            rows = await conn.fetch("""
                SELECT * FROM mi_flag_candidates
                WHERE scan_date = $1 AND stage = ANY($2)
                ORDER BY rs_rank NULLS LAST, ticker
            """, scan_date, stages)
        else:
            rows = await conn.fetch("""
                SELECT * FROM mi_flag_candidates
                WHERE scan_date = $1
                ORDER BY rs_rank NULLS LAST, ticker
            """, scan_date)
    return [dict(r) for r in rows]


async def get_ticker_flag_history(ticker: str, days: int = 14) -> list[dict[str, Any]]:
    """Stage history for one ticker over the last `days` scans. Powers
    `/flags TICKER` ("is XNDU still in the system?")."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT scan_date, stage, base_age, range_contraction_ratio,
                   vol_contraction_ratio, reason, held_from_stage
            FROM mi_flag_candidates
            WHERE ticker = $1
              AND scan_date >= CURRENT_DATE - ($2::int || ' days')::interval
            ORDER BY scan_date DESC
        """, ticker.upper(), days)
    return [dict(r) for r in rows]


async def get_ticker_setup_timeline(ticker: str, days: int = 180) -> dict[str, Any]:
    """Reverse-lookup chronology — every detector hit for one ticker.

    Powers `/setup TICKER`. Fans out 10 small per-table SELECTs in parallel
    via `asyncio.gather`. Each subquery acquires its own pool connection
    (asyncpg refuses concurrent queries on a single Connection), so total
    roundtrip ≈ slowest subquery.

    Tables covered: mi_ep_alerts, mi_9m_ep_alerts, mi_9m_day2_candidates,
    mi_wick_candidates, mi_parabolic_candidates, mi_flag_candidates,
    mi_themes (array containment), mi_live_trades, mi_paper_trades,
    mi_weekly_watchlists. Plus latest mi_stock_scores row for context.

    Returns:
        {"ticker", "rs_context": {...}|None, "events": [{date, source, summary,
        priority}, ...], "raw_count": int, "cap": 60}
    """
    import asyncio

    t = ticker.upper()
    pool = await get_pool()

    # Source priority for tie-breaking when multiple events land on the same
    # date. TRADE > FLAG > EP > 9M > WICK > PARABOLIC > THEME > WATCHLIST.
    PRIO = {
        "TRADE-LIVE": 0, "TRADE-PAPER": 1, "FLAG": 2, "EP-MAGNA": 3,
        "9M-INTRADAY": 4, "9M-SUGAR": 5, "WICK": 6, "PARABOLIC": 7,
        "THEME": 8, "WATCHLIST": 9, "RS": 10,
    }
    POST_MERGE_CAP = 60

    async def _q(sql: str, *args):
        async with pool.acquire() as conn:
            return await conn.fetch(sql, *args)

    async def _qrow(sql: str, *args):
        async with pool.acquire() as conn:
            return await conn.fetchrow(sql, *args)

    # Per-table coroutines — all return list[Record] except rs_context (single row).
    coros = {
        "ep": _q("""
            SELECT alert_date, score_tier, ep_score, gap_pct,
                   catalyst_quality, catalyst
            FROM mi_ep_alerts
            WHERE ticker = $1
              AND COALESCE(source, 'live') = 'live'
              AND alert_date >= CURRENT_DATE - ($2::int || ' days')::interval
            ORDER BY alert_date DESC LIMIT 50
        """, t, days),
        "9m_intra": _q("""
            SELECT alert_date, gap_pct, projected_vol, is_anticipation,
                   current_price
            FROM mi_9m_ep_alerts
            WHERE ticker = $1
              AND alert_date >= CURRENT_DATE - ($2::int || ' days')::interval
            ORDER BY alert_date DESC LIMIT 50
        """, t, days),
        "9m_sugar": _q("""
            SELECT alert_date, day2_status, close_in_range_pct, prev_5d_pct,
                   prev_20d_pct, volume
            FROM mi_9m_day2_candidates
            WHERE ticker = $1
              AND alert_date >= CURRENT_DATE - ($2::int || ' days')::interval
            ORDER BY alert_date DESC LIMIT 50
        """, t, days),
        "wick": _q("""
            SELECT alert_date, filled_wick, fill_date, close_in_range_pct,
                   fwd_3d_from_high_pct
            FROM mi_wick_candidates
            WHERE ticker = $1
              AND alert_date >= CURRENT_DATE - ($2::int || ' days')::interval
            ORDER BY alert_date DESC LIMIT 50
        """, t, days),
        "parabolic": _q("""
            SELECT scan_date, stage, score, prior_move_pct
            FROM mi_parabolic_candidates
            WHERE ticker = $1 AND stage <> 'unqualified'
              AND scan_date >= CURRENT_DATE - ($2::int || ' days')::interval
            ORDER BY scan_date DESC LIMIT 50
        """, t, days),
        "flag": _q("""
            SELECT scan_date, stage, base_age, range_contraction_ratio,
                   vol_contraction_ratio, breakout_volume_ratio,
                   breakout_close, base_high, held_from_stage
            FROM mi_flag_candidates
            WHERE ticker = $1 AND stage <> 'unqualified'
              AND scan_date >= CURRENT_DATE - ($2::int || ' days')::interval
            ORDER BY scan_date DESC LIMIT 50
        """, t, days),
        "theme": _q("""
            SELECT theme_date, name, stage
            FROM mi_themes
            WHERE $1 = ANY(tickers)
              AND theme_date >= CURRENT_DATE - ($2::int || ' days')::interval
            ORDER BY theme_date DESC LIMIT 50
        """, t, days),
        "live": _q("""
            SELECT alert_date, status, entry_price, stop_price, total_pnl,
                   skip_reason, closed_at
            FROM mi_live_trades
            WHERE ticker = $1
              AND alert_date >= CURRENT_DATE - ($2::int || ' days')::interval
            ORDER BY alert_date DESC LIMIT 50
        """, t, days),
        "paper": _q("""
            SELECT alert_date, status, total_pnl
            FROM mi_paper_trades
            WHERE ticker = $1
              AND alert_date >= CURRENT_DATE - ($2::int || ' days')::interval
            ORDER BY alert_date DESC LIMIT 50
        """, t, days),
        "watchlist": _q("""
            SELECT week_ending, composite_priority, sources, reason_chip
            FROM mi_weekly_watchlists
            WHERE ticker = $1
              AND week_ending >= CURRENT_DATE - ($2::int || ' days')::interval
            ORDER BY week_ending DESC LIMIT 50
        """, t, days),
        "rs_ctx": _qrow("""
            SELECT score_date, rs_rank, rs_composite, sector
            FROM mi_stock_scores
            WHERE ticker = $1
            ORDER BY score_date DESC LIMIT 1
        """, t),
    }

    keys = list(coros.keys())
    results = await asyncio.gather(*coros.values(), return_exceptions=True)
    by_key = {k: r for k, r in zip(keys, results)}

    events: list[dict[str, Any]] = []

    def _push(d, source, summary):
        events.append({"date": d, "source": source, "summary": summary,
                        "priority": PRIO.get(source, 99)})

    def _rows(key):
        v = by_key.get(key)
        if isinstance(v, Exception):
            logger.warning(f"setup_timeline {key} failed for {t}: {v}")
            return []
        return v or []

    for r in _rows("ep"):
        cat_full = r["catalyst"] or ""
        # Word-break truncation — 40 was cutting mid-word ("due to a s").
        if len(cat_full) > 120:
            cut = cat_full[:120].rsplit(" ", 1)[0]
            cat = cut + "…"
        else:
            cat = cat_full
        cat_s = f", {cat}" if cat else ""
        _push(r["alert_date"], "EP-MAGNA",
              f"{r['score_tier']} score {int(r['ep_score'] or 0)} "
              f"(gap {float(r['gap_pct'] or 0):+.1f}%, "
              f"cat={r['catalyst_quality'] or 'n/a'}{cat_s})")

    for r in _rows("9m_intra"):
        proj = r["projected_vol"]
        proj_s = f", proj {proj/1_000_000:.0f}M" if proj else ""
        ant = " · anticipation" if r["is_anticipation"] else ""
        _push(r["alert_date"], "9M-INTRADAY",
              f"gap {float(r['gap_pct'] or 0):+.1f}%{proj_s}{ant}")

    for r in _rows("9m_sugar"):
        # close_in_range_pct stored as fraction (0.94 = 94%); prev_5d_pct
        # stored as a true percentage (-4.13 = -4.13%) — different units in
        # the same row, no shared multiplier.
        rp = int((r["close_in_range_pct"] or 0) * 100)
        p5 = r["prev_5d_pct"]
        p5_s = f", prev_5d {float(p5):+.1f}%" if p5 is not None else ""
        _push(r["alert_date"], "9M-SUGAR",
              f"day2={r['day2_status']}, close top {rp}%{p5_s}")

    for r in _rows("wick"):
        fwd = r["fwd_3d_from_high_pct"]
        fwd_s = f", fwd3d {float(fwd)*100:+.1f}%" if fwd is not None else ""
        fill_s = "filled" if r["filled_wick"] else "unfilled"
        _push(r["alert_date"], "WICK", f"{fill_s}{fwd_s}")

    for r in _rows("parabolic"):
        pm = r["prior_move_pct"]
        pm_s = f", prior {float(pm)*100:+.0f}%" if pm is not None else ""
        _push(r["scan_date"], "PARABOLIC",
              f"{r['stage']} score {r['score']}{pm_s}")

    for r in _rows("flag"):
        bvr = r["breakout_volume_ratio"]
        rcr = r["range_contraction_ratio"]
        vcr = r["vol_contraction_ratio"]
        if r["stage"] == "TRIGGERED" and bvr is not None and r["breakout_close"]:
            _push(r["scan_date"], "FLAG",
                  f"TRIGGERED — base {r['base_age']}d, vol {float(bvr):.2f}× "
                  f"close ${float(r['breakout_close']):.2f}")
        else:
            rs_s = f"r{float(rcr):.2f}" if rcr is not None else "r—"
            vs_s = f"v{float(vcr):.2f}" if vcr is not None else "v—"
            held = f" (held {r['held_from_stage']})" if r["held_from_stage"] else ""
            _push(r["scan_date"], "FLAG",
                  f"{r['stage']} — base {r['base_age']}d {rs_s} {vs_s}{held}")

    # Theme rows repeat daily — collapse runs of identical (name, stage) into
    # a date-range span so 30 consecutive "AI Infrastructure (Accelerating)"
    # snapshots don't dominate the post-merge cap.
    theme_rows = sorted(
        _rows("theme"),
        key=lambda r: (r["name"], r["stage"], r["theme_date"]),
    )
    spans: list[tuple[str, str, Any, Any]] = []  # (name, stage, first, last)
    for r in theme_rows:
        if spans and spans[-1][0] == r["name"] and spans[-1][1] == r["stage"]:
            spans[-1] = (spans[-1][0], spans[-1][1], spans[-1][2], r["theme_date"])
        else:
            spans.append((r["name"], r["stage"], r["theme_date"], r["theme_date"]))
    for name, stage, first, last in spans:
        if first == last:
            _push(last, "THEME", f"\"{name}\" ({stage})")
        else:
            _push(last, "THEME",
                  f"\"{name}\" ({stage}) — span {first}→{last}")

    for r in _rows("live"):
        ep = r["entry_price"]; sp = r["stop_price"]; pnl = r["total_pnl"]
        bits = [f"status={r['status']}"]
        if ep: bits.append(f"entry ${float(ep):.2f}")
        if sp: bits.append(f"stop ${float(sp):.2f}")
        if pnl: bits.append(f"P&L ${float(pnl):+,.0f}")
        # Show the reason on any non-fill terminal state, not just 'skipped'.
        # Cancelled rows (10:00 ET ORB cleanup, 4:05 PM EOD cleanup, mid-day
        # broker reject) carry the same skip_reason column — without rendering
        # it the user can't tell why a placed order didn't fill.
        if r["status"] in ("skipped", "cancelled", "rejected") and r["skip_reason"]:
            from agents.market_intelligence.broker.skip_reasons import humanize
            label = humanize(r["skip_reason"])
            if "(" in label:
                label = label[:label.find("(")].rstrip()
            bits.append(label)
        _push(r["alert_date"], "TRADE-LIVE", " · ".join(bits))

    for r in _rows("paper"):
        pnl = r["total_pnl"]
        pnl_s = f", P&L ${float(pnl):+,.0f}" if pnl else ""
        _push(r["alert_date"], "TRADE-PAPER", f"status={r['status']}{pnl_s}")

    for r in _rows("watchlist"):
        # composite_priority is an internal source-precedence integer
        # (1=EP_HIGH, 2=THEME, 3=9M_SUGAR, 4=WICK, 5=PARABOLIC, 6=RS) — not
        # meaningful to humans. The source list tells the actual story.
        srcs = r["sources"]
        if isinstance(srcs, str):
            import json as _json
            try:
                srcs = _json.loads(srcs)
            except (ValueError, TypeError):
                srcs = []
        srcs_s = ", ".join(srcs) if srcs else "?"
        _push(r["week_ending"], "WATCHLIST", f"sources: {srcs_s}")

    # Sort: date DESC, then priority ASC (TRADE first within a day).
    events.sort(key=lambda e: (e["date"], -e["priority"]), reverse=True)
    raw_count = len(events)
    events = events[:POST_MERGE_CAP]

    rs_row = by_key.get("rs_ctx")
    rs_ctx: dict[str, Any] | None = None
    if rs_row is not None and not isinstance(rs_row, Exception):
        rs_ctx = dict(rs_row)

    return {
        "ticker": t,
        "rs_context": rs_ctx,
        "events": events,
        "raw_count": raw_count,
        "cap": POST_MERGE_CAP,
    }


async def update_parabolic_exclusion(
    ticker: str,
    scan_date: "date",
    *,
    excluded_reason: str,
    excluded_source: str,
    excluded_detail: str | None = None,
) -> None:
    """Mark today's parabolic candidate as excluded — preserves the price-action
    stage so the row remains queryable as historical evidence (e.g. for review:
    'OGN climax 2026-04-27 was filtered out because of M&A')."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE mi_parabolic_candidates
            SET excluded_reason = $3,
                excluded_source = $4,
                excluded_detail = $5
            WHERE ticker = $1 AND scan_date = $2
            """,
            ticker, scan_date, excluded_reason, excluded_source, excluded_detail,
        )


async def add_parabolic_exclusion(
    ticker: str,
    *,
    source: str,
    reason: str,
    detail: str | None = None,
    excluded_until: "date | None" = None,
) -> None:
    """Upsert a parabolic exclusion. Manual exclusions use source='manual'
    with `excluded_until=None` (permanent). Auto news verdicts use
    source='news_check' with a TTL so the verdict re-checks after news ages."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO mi_parabolic_exclusions
                (ticker, source, reason, detail, excluded_until)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (ticker, source) DO UPDATE SET
                reason = EXCLUDED.reason,
                detail = EXCLUDED.detail,
                excluded_until = EXCLUDED.excluded_until,
                created_at = NOW()
            """,
            ticker.upper(), source, reason, detail, excluded_until,
        )


async def remove_parabolic_exclusion(ticker: str, source: str | None = None) -> int:
    """Delete exclusion rows for `ticker`. If `source` is given, only that
    source's row is removed (so removing a manual exclusion doesn't drop a
    still-valid news_check verdict)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        if source:
            res = await conn.execute(
                "DELETE FROM mi_parabolic_exclusions WHERE ticker = $1 AND source = $2",
                ticker.upper(), source,
            )
        else:
            res = await conn.execute(
                "DELETE FROM mi_parabolic_exclusions WHERE ticker = $1",
                ticker.upper(),
            )
        try:
            return int(res.split()[-1])
        except Exception:
            return 0


async def get_active_parabolic_exclusions() -> dict[str, dict[str, Any]]:
    """Return active exclusion entries keyed by ticker. Three sources, in
    precedence order:
      - 'manual_keep' — sticky allowlist; ticker is NEVER auto-excluded.
        Written by `/parabolic include` so the next news_check skips the
        ticker entirely instead of re-running Perplexity.
      - 'manual'      — operator-set permanent ban.
      - 'news_check'  — auto LLM verdict with TTL.
    Higher-precedence rows shadow lower ones for the same ticker. Expired
    auto-verdicts (`excluded_until < today`) are filtered out by the SQL.
    Callers interpret `source == 'manual_keep'` as "no exclusion, skip the
    Perplexity call too" — see `_apply_exclusions` in parabolic_detector.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT ticker, source, reason, detail, excluded_until, created_at
            FROM mi_parabolic_exclusions
            WHERE excluded_until IS NULL
               OR excluded_until >= CURRENT_DATE
            """
        )
    _PRECEDENCE = {"manual_keep": 2, "manual": 1, "news_check": 0}
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        ticker = r["ticker"]
        existing = out.get(ticker)
        new_rank = _PRECEDENCE.get(r["source"], -1)
        old_rank = _PRECEDENCE.get((existing or {}).get("source"), -1)
        if existing is None or new_rank > old_rank:
            out[ticker] = dict(r)
    return out


async def list_parabolic_exclusions() -> list[dict[str, Any]]:
    """List ALL parabolic exclusions (active + expired) for `/parabolic exclusions`."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT ticker, source, reason, detail, excluded_until, created_at
            FROM mi_parabolic_exclusions
            ORDER BY created_at DESC
            """
        )
    return [dict(r) for r in rows]


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


async def get_latest_regime(
    include_breadth_history: bool = False,
) -> Optional[dict[str, Any]]:
    """Most-recent regime row. Set `include_breadth_history=True` to also
    attach `breadth_history_5d` (last CLUSTER_WINDOW days of parsed
    breadth_monitor) — only the briefing composer needs this; defaulting
    False avoids an extra fetch on every EP-scan/regime-handler tick."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM mi_market_regime ORDER BY regime_date DESC LIMIT 1"
        )
        if not row:
            return None
        result = dict(row)
        if include_breadth_history:
            result["breadth_history_5d"] = await _fetch_breadth_history(conn)
        return result


async def _fetch_breadth_history(conn: Any, limit: Optional[int] = None) -> list[dict]:
    """Last N days of breadth_monitor JSONB parsed into dicts. Each row carries
    a `date` key (regime_date) plus all JSONB fields. Returned newest-first."""
    from agents.market_intelligence.breadth_color_rules import (
        CLUSTER_WINDOW, coerce_breadth_monitor,
    )
    rows = await conn.fetch(
        """
        SELECT regime_date, breadth_monitor
        FROM mi_market_regime
        WHERE breadth_monitor IS NOT NULL
        ORDER BY regime_date DESC
        LIMIT $1
        """,
        limit or CLUSTER_WINDOW,
    )
    return [
        {"date": r["regime_date"], **coerce_breadth_monitor(r["breadth_monitor"])}
        for r in rows
    ]


async def get_breadth_history(limit: int) -> list[dict]:
    """Public history fetcher for the /regime breadth matrix + other consumers."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await _fetch_breadth_history(conn, limit=limit)


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
            SELECT ticker, rs_composite, rs_1m, rs_3m, rs_6m, rs_rank
            FROM mi_stock_scores
            WHERE score_date = $1 AND ticker = ANY($2)
        """, score_date, tickers)
        return {r["ticker"]: dict(r) for r in rows}


# ── ADR 0007 nascent-discovery selectors (pure predicates + DB queries) ──────────
# These add discovery candidate pools the top-40 RS gate structurally misses. The
# PREDICATES are pure + unit-tested; the DB wrappers are verified Monday on the server
# (no local DB). Defaults are seeded from the 2026-05-31 replay; tune on shadow data.

def _is_rank_accelerator(
    rank_now, rank_prior, rs_now, rs_prior,
    *, min_rank_improve: int = 800, min_rs_delta: float = 25.0, min_rs_now: float = 50.0,
) -> bool:
    """ADR 0007 (a): an igniting candidate — sharp rank improvement OR rs jump over the
    lookback, at a meaningful current RS. OR-combined (not AND) per the 5/31 replay:
    RCAT cleared the rank arm at rs_composite 59.4, which an rs-floor >= 60 would have
    wrongly dropped — so min_rs_now stays a LOW floor (<= 50)."""
    if rs_now is None or rs_now < min_rs_now:
        return False
    rank_ok = (rank_prior is not None and rank_now is not None
               and (rank_prior - rank_now) >= min_rank_improve)
    rs_ok = (rs_prior is not None and (rs_now - rs_prior) >= min_rs_delta)
    return bool(rank_ok or rs_ok)


def _is_recovery_slope(
    rs_1m, rs_6m, *, min_rs_1m: float = 90.0, max_rs_6m: float = 30.0,
) -> bool:
    """ADR 0007 (a2): a re-rating off a low base — strong short-term RS while medium-term
    is still weak (rs_1m >> rs_6m). Catches the recovering software-AI cohort (NOW/ESTC/
    TEAM/MDB) that rank-acceleration misses. Established names (high rs_6m) are intentionally
    NOT caught here — they need the narrative layer (e)."""
    return bool(rs_1m is not None and rs_6m is not None
                and rs_1m >= min_rs_1m and rs_6m <= max_rs_6m)


async def get_rs_accelerators(
    d: "str | date", lookback_days: int = 2, min_rank_improve: int = 800,
    min_rs_delta: float = 25.0, min_rs_now: float = 50.0,
    min_adv: float = 500_000, min_price: float = 10.0, limit: int = 30,
) -> list[dict[str, Any]]:
    """ADR 0007 (a): liquid names igniting fast over `lookback_days` trading days
    (rank-acceleration OR rs jump), at meaningful current RS. Defaults seeded from the
    5/31 replay (impr>=800 ∨ rs_delta>=25, rs_now>=50); tune on shadow flood-count
    before promoting to live."""
    from agents.market_intelligence.constants import SKIP_TICKERS_LIST, is_sector_filtered
    pool = await get_pool()
    async with pool.acquire() as conn:
        score_date = await _resolve_score_date(conn, _to_date(d))
        prior = await conn.fetchval("""
            SELECT score_date FROM mi_stock_scores
            WHERE score_date < $1 GROUP BY score_date
            ORDER BY score_date DESC OFFSET $2 LIMIT 1
        """, score_date, max(0, lookback_days - 1))
        if prior is None:
            return []
        rows = await conn.fetch("""
            SELECT t.*, p.rs_rank AS prior_rank, p.rs_composite AS prior_rs
            FROM mi_stock_scores t
            JOIN mi_stock_scores p ON p.ticker = t.ticker AND p.score_date = $2
            WHERE t.score_date = $1
              AND t.adv_20 IS NOT NULL AND t.adv_20 >= $3
              AND t.close IS NOT NULL AND t.close >= $4
              AND t.ticker != ALL($5)
              AND t.rs_composite IS NOT NULL AND t.rs_composite >= $6
              AND NOT EXISTS (
                  SELECT 1 FROM mi_tracked_stocks ts
                  WHERE ts.ticker = t.ticker AND ts.quote_type IS NOT NULL AND ts.quote_type != 'EQUITY'
              )
        """, score_date, prior, min_adv, min_price, SKIP_TICKERS_LIST, min_rs_now)
        out: list[dict[str, Any]] = []
        for r in rows:
            row = dict(r)
            if is_sector_filtered(row.get("sector"), row.get("close")):
                continue
            if _is_rank_accelerator(
                row.get("rs_rank"), row.get("prior_rank"),
                row.get("rs_composite"), row.get("prior_rs"),
                min_rank_improve=min_rank_improve, min_rs_delta=min_rs_delta, min_rs_now=min_rs_now,
            ):
                rk, prk = row.get("rs_rank"), row.get("prior_rank")
                row["rank_improve"] = (prk - rk) if (rk is not None and prk is not None) else None
                out.append(row)
        out.sort(key=lambda x: (x.get("rank_improve") or 0), reverse=True)
        return out[:limit]


async def get_rs_recovery_slope(
    d: "str | date", min_rs_1m: float = 90.0, max_rs_6m: float = 30.0,
    min_adv: float = 500_000, min_price: float = 10.0, limit: int = 30,
) -> list[dict[str, Any]]:
    """ADR 0007 (a2): liquid names re-rating off a low base (rs_1m high, rs_6m low) —
    the recovering-cohort signal rank-acceleration misses. Defaults seeded from the 5/31
    replay (rs_1m>=90 ∧ rs_6m<=30); tune on shadow flood-count before promoting to live."""
    from agents.market_intelligence.constants import SKIP_TICKERS_LIST, is_sector_filtered
    pool = await get_pool()
    async with pool.acquire() as conn:
        score_date = await _resolve_score_date(conn, _to_date(d))
        rows = await conn.fetch("""
            SELECT * FROM mi_stock_scores
            WHERE score_date = $1
              AND adv_20 IS NOT NULL AND adv_20 >= $2
              AND close IS NOT NULL AND close >= $3
              AND ticker != ALL($4)
              AND rs_1m IS NOT NULL AND rs_6m IS NOT NULL
              AND rs_1m >= $5 AND rs_6m <= $6
              AND NOT EXISTS (
                  SELECT 1 FROM mi_tracked_stocks ts
                  WHERE ts.ticker = mi_stock_scores.ticker AND ts.quote_type IS NOT NULL AND ts.quote_type != 'EQUITY'
              )
            ORDER BY rs_1m DESC NULLS LAST
            LIMIT $7
        """, score_date, min_adv, min_price, SKIP_TICKERS_LIST, min_rs_1m, max_rs_6m, limit * 2)
        out: list[dict[str, Any]] = []
        for r in rows:
            row = dict(r)
            if is_sector_filtered(row.get("sector"), row.get("close")):
                continue
            out.append(row)
            if len(out) >= limit:
                break
        return out


async def persist_theme_candidates_shadow(
    run_date: "str | date", themes: list[dict], would_revive: "dict | None" = None,
) -> int:
    """ADR 0007 shadow lane — write PROPOSED themes to mi_theme_candidates_shadow (NOT
    mi_themes / the brief). Re-runnable: clears prior shadow_v2 rows for run_date first.
    SOURCE-SCOPED delete — must NOT clobber the source='narrative_cogap' rows that
    persist_narrative_theme_candidates writes to the same table (#167). Returns rows
    written. `would_revive` maps existing-theme-name -> bool flag (computed, not applied)."""
    if not themes:
        return 0
    would_revive = would_revive or {}
    pool = await get_pool()
    async with pool.acquire() as conn:
        rd = _to_date(run_date)
        await conn.execute(
            "DELETE FROM mi_theme_candidates_shadow WHERE run_date = $1 AND source = 'shadow_v2'", rd)
        n = 0
        for t in themes:
            name = t.get("name")
            tickers = t.get("tickers") or []
            if not name or not tickers:
                continue
            await conn.execute("""
                INSERT INTO mi_theme_candidates_shadow
                    (run_date, name, thesis, tickers, source, would_revive)
                VALUES ($1, $2, $3, $4, 'shadow_v2', $5)
                ON CONFLICT (run_date, name) DO UPDATE
                  SET thesis = EXCLUDED.thesis, tickers = EXCLUDED.tickers,
                      would_revive = EXCLUDED.would_revive
            """, rd, name, t.get("thesis") or t.get("rationale"),
                 list(tickers), bool(would_revive.get(name, False)))
            n += 1
        return n


async def persist_narrative_theme_candidates(
    run_date: "str | date", themes: list[dict], backfilled: bool = False,
) -> int:
    """#167 narrative-cogap shadow lane. SOURCE-SCOPED — clears/writes only its own
    source rows, so it does NOT clobber the correlation-shadow ('shadow_v2') rows
    that persist_theme_candidates_shadow writes to the same mi_theme_candidates_shadow
    table. Re-runnable. Returns rows written.

    #167 hindsight-segregation (2026-06-06): forward (scheduled, same-day) writes
    source='narrative_cogap'; a hindsight BACKFILL writes source='narrative_cogap_backfill'.
    The distinct source makes the forward-only precision read forward BY CONSTRUCTION
    (no created_at arithmetic), while the promote-gate read can include both populations
    SPLIT + LABELLED — recall (live_unified, scored vs TODAY's themes) is the
    hindsight-exposed signal on backfill, so the operator applies the trust judgment
    at the 6/23 gate; the harness surfaces both, nulls neither."""
    src = "narrative_cogap_backfill" if backfilled else "narrative_cogap"
    # FORWARD ALWAYS WINS (PK is (run_date, name); backfill window overlaps the
    # forward era). Forward path: DO UPDATE → a real scheduled run flips a same-day
    # backfill row to forward (correct). Backfill path: DO NOTHING → must NOT clobber
    # a real forward row, else a backfill RE-RUN would relabel forward rows to backfill
    # and silently UNDER-COUNT the forward-only promote-gate predicate. The source-
    # scoped DELETE already cleared backfill's own rows for this run_date, so the only
    # surviving conflict on the backfill path is a forward row we must keep.
    conflict = ("DO UPDATE SET thesis = EXCLUDED.thesis, tickers = EXCLUDED.tickers, "
                "source = EXCLUDED.source") if not backfilled else "DO NOTHING"
    pool = await get_pool()
    async with pool.acquire() as conn:
        rd = _to_date(run_date)
        await conn.execute(
            "DELETE FROM mi_theme_candidates_shadow WHERE run_date = $1 AND source = $2", rd, src)
        n = 0
        for t in (themes or []):
            name = t.get("name")
            tickers = t.get("tickers") or []
            if not name or not tickers:
                continue
            # RETURNING → n counts rows ACTUALLY written (DO NOTHING conflicts that
            # protect a forward row return no row and are correctly not counted).
            row = await conn.fetchrow(f"""
                INSERT INTO mi_theme_candidates_shadow
                    (run_date, name, thesis, tickers, source, would_revive)
                VALUES ($1, $2, $3, $4, $5, FALSE)
                ON CONFLICT (run_date, name) {conflict}
                RETURNING 1
            """, rd, name, t.get("thesis"), list(tickers), src)
            if row is not None:
                n += 1
        return n


async def persist_synthesis_theme_candidates(
    run_date: "str | date", cohorts: list[dict],
) -> int:
    """#240 cross-ticker synthesis lane — write emerging-cohort proposals to
    mi_theme_candidates_shadow under source='rs_slope_synthesis'. SOURCE-SCOPED
    (same discipline as the other two writers sharing this table): clears/writes
    only its own source rows. Forward-only by construction — the pass runs
    nightly over current RS snapshots; there is no backfill variant. Returns
    rows written."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rd = _to_date(run_date)
        await conn.execute(
            "DELETE FROM mi_theme_candidates_shadow WHERE run_date = $1 AND source = 'rs_slope_synthesis'",
            rd)
        n = 0
        for c in (cohorts or []):
            name = c.get("name")
            tickers = c.get("tickers") or []
            if not name or not tickers:
                continue
            # ON CONFLICT guard: the table's unique key is (run_date, name)
            # ACROSS sources — without the WHERE, a same-named cohort from
            # another lane (narrative_cogap) would be silently hijacked into
            # this lane. Cross-lane collision → leave the other lane's row.
            await conn.execute("""
                INSERT INTO mi_theme_candidates_shadow
                    (run_date, name, thesis, tickers, source, would_revive)
                VALUES ($1, $2, $3, $4, 'rs_slope_synthesis', FALSE)
                ON CONFLICT (run_date, name) DO UPDATE
                    SET thesis = EXCLUDED.thesis, tickers = EXCLUDED.tickers
                    WHERE mi_theme_candidates_shadow.source = 'rs_slope_synthesis'
            """, rd, name, c.get("thesis"), tickers)
            n += 1
        return n


async def get_narrative_theme_candidates(
    days: int = 5, include_backfill: bool = False, as_of: "date | None" = None,
) -> list[dict]:
    """#167 — recent narrative-cogap shadow theme proposals (advisory/shadow; NOT live).
    Surfaced (clearly labeled experimental) in /themes so the operator can evaluate
    the accruing proposals toward a promote-gate.

    Forward-only by default: source='narrative_cogap' (#167 co-gap lane) +
    source='rs_slope_synthesis' (#240 cross-ticker synthesis lane — both are
    forward-written nightly, so both are judge-feedable). include_backfill=True
    also returns the hindsight backfill population (source=
    'narrative_cogap_backfill'), each row tagged `backfilled` so the
    promote-gate read can split + label them (#167 hindsight-segregation).

    `as_of` (lane2-judge-theme-axis replay): point-in-time view for date D — PRIOR
    days only (`D - days <= run_date < D`; same-day rows are lookahead, the lane is
    EOD while alerts are premarket). None = the live view (window anchored on
    CURRENT_DATE, inclusive of today). One helper for both so live and replay can
    never select cohorts differently."""
    pool = await get_pool()
    src_clause = (
        "source IN ('narrative_cogap', 'rs_slope_synthesis', 'narrative_cogap_backfill')"
        if include_backfill
        else "source IN ('narrative_cogap', 'rs_slope_synthesis')")
    async with pool.acquire() as conn:
        if as_of is None:
            rows = await conn.fetch(f"""
                SELECT run_date, name, tickers, thesis,
                       (source = 'narrative_cogap_backfill') AS backfilled
                FROM mi_theme_candidates_shadow
                WHERE {src_clause}
                  AND run_date >= (CURRENT_DATE - $1::int)
                ORDER BY run_date DESC, name
            """, days)
        else:
            rows = await conn.fetch(f"""
                SELECT run_date, name, tickers, thesis,
                       (source = 'narrative_cogap_backfill') AS backfilled
                FROM mi_theme_candidates_shadow
                WHERE {src_clause}
                  AND run_date >= ($2::date - $1::int)
                  AND run_date < $2::date
                ORDER BY run_date DESC, name
            """, days, as_of)
        return [dict(r) for r in rows]


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
              AND COALESCE(a.source, 'live') = 'live'
            ORDER BY a.alert_date DESC, a.ep_score DESC
            """,
            days,
        )
    return [dict(r) for r in rows]


async def log_ep_scan_candidates(records: list[dict]) -> None:
    """
    Append EP scan candidates — one row per (scan invocation, ticker).
    Each record: {scan_date, ticker, gap_pct, prev_close, rel_volume,
                  filter_reason, ep_score, score_tier, catalyst_quality,
                  scan_time_et, rank_by_gap, projected_vol_multiple, pm_rvol,
                  adv, adv_source, minutes_since_open}.
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
                     filter_reason, ep_score, score_tier, catalyst_quality,
                     scan_time_et, rank_by_gap, projected_vol_multiple,
                     pm_rvol, adv, adv_source, minutes_since_open)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9,
                        $10, $11, $12, $13, $14, $15, $16)
            """, [
                (
                    r["scan_date"], r["ticker"], r.get("gap_pct"),
                    r.get("prev_close"), r.get("rel_volume"),
                    r.get("filter_reason"), r.get("ep_score"),
                    r.get("score_tier"), r.get("catalyst_quality"),
                    r.get("scan_time_et"), r.get("rank_by_gap"),
                    r.get("projected_vol_multiple"), r.get("pm_rvol"),
                    r.get("adv"), r.get("adv_source"),
                    r.get("minutes_since_open"),
                )
                for r in records
            ])
    except Exception as e:
        import logging as _logging
        _logging.getLogger(__name__).warning(f"EP scan log write failed: {e}")


async def get_ep_scan_log(d: "str | date") -> list[dict[str, Any]]:
    """Return all gap candidates evaluated on a given date — last-seen state per ticker.

    Multiple rows per (scan_date, ticker) exist after C1 (one per scan
    invocation). Use DISTINCT ON to collapse to the most recent state.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT ticker, gap_pct, prev_close, rel_volume,
                      filter_reason, ep_score, score_tier, catalyst_quality
               FROM (
                   SELECT DISTINCT ON (ticker)
                          ticker, gap_pct, prev_close, rel_volume,
                          filter_reason, ep_score, score_tier, catalyst_quality,
                          scan_time_et
                   FROM mi_ep_scan_log
                   WHERE scan_date = $1
                   ORDER BY ticker, scan_time_et DESC NULLS LAST, id DESC
               ) latest
               ORDER BY ep_score DESC NULLS LAST, gap_pct DESC""",
            _to_date(d),
        )
    return [dict(r) for r in rows]


async def get_ep_scan_log_for_ticker(ticker: str, limit: int = 6) -> list[dict[str, Any]]:
    """Recent EP-scan outcomes for ONE ticker — most-recent state per scan_date,
    newest first. Surfaces WHY a ticker did/didn't alert (filter_reason, incl.
    cooldown drops) for /setup + /why observability (#171) — the detector-hit
    timeline can't show this because a dropped ticker leaves no hit."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT scan_date, filter_reason, ep_score, score_tier, gap_pct
               FROM (
                   SELECT DISTINCT ON (scan_date)
                          scan_date, filter_reason, ep_score, score_tier, gap_pct,
                          scan_time_et, id
                   FROM mi_ep_scan_log
                   WHERE ticker = $1
                   ORDER BY scan_date, scan_time_et DESC NULLS LAST, id DESC
               ) latest
               ORDER BY scan_date DESC
               LIMIT $2""",
            ticker.upper(), limit,
        )
    return [dict(r) for r in rows]


async def upsert_minute_volume_curves(records: list[dict]) -> int:
    """Batch-upsert per-minute cumulative-volume baselines.

    Each record: {ticker, anchor ('pm'|'session'), et_clock_minute,
                  mean_cum_vol, stddev_cum_vol, sample_n}.
    Returns the number of rows written. Never raises — refresh job tolerates
    partial writes.
    """
    if not records:
        return 0
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            await conn.executemany("""
                INSERT INTO mi_minute_volume_curves
                    (ticker, anchor, et_clock_minute,
                     mean_cum_vol, stddev_cum_vol, sample_n, refreshed_at)
                VALUES ($1, $2, $3, $4, $5, $6, NOW())
                ON CONFLICT (ticker, anchor, et_clock_minute) DO UPDATE SET
                    mean_cum_vol   = EXCLUDED.mean_cum_vol,
                    stddev_cum_vol = EXCLUDED.stddev_cum_vol,
                    sample_n       = EXCLUDED.sample_n,
                    refreshed_at   = NOW()
            """, [
                (
                    r["ticker"], r["anchor"], int(r["et_clock_minute"]),
                    float(r["mean_cum_vol"]),
                    float(r["stddev_cum_vol"]) if r.get("stddev_cum_vol") is not None else None,
                    int(r["sample_n"]),
                )
                for r in records
            ])
        return len(records)
    except Exception as e:
        logger.warning(f"minute volume curves upsert failed: {e}")
        return 0


async def get_minute_volume_baseline(
    ticker: str, anchor: str, et_clock_minute: int
) -> dict | None:
    """Look up the (mean, stddev, sample_n) baseline for a single
    (ticker, anchor, minute). Returns None if no row.
    """
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT mean_cum_vol, stddev_cum_vol, sample_n, refreshed_at
                   FROM mi_minute_volume_curves
                   WHERE ticker = $1 AND anchor = $2 AND et_clock_minute = $3""",
                ticker, anchor, et_clock_minute,
            )
        return dict(row) if row else None
    except Exception as e:
        logger.warning(f"minute volume baseline lookup failed ({ticker}, {anchor}, {et_clock_minute}): {e}")
        return None


async def get_top_dollar_volume_universe(
    min_dollar_volume: float = 5_000_000.0,
    max_tickers: int = 5000,
) -> list[str]:
    """Return tickers with 20d dollar volume ≥ `min_dollar_volume` from the most
    recent score date, capped at `max_tickers` for safety.

    Used by the minute-volume curves refresh job to scope the universe. The
    earlier top-500 cap silently skipped the pm_rvol gate for ~85% of HIGH EP
    candidates (most pre-market gappers are mid/small caps outside top-500 by
    trailing $-vol). $5M floor ≈ 1500–2000 tickers — covers the realistic gap
    universe, including the OMCL-class names that the gate exists to catch.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        latest = await conn.fetchval(
            "SELECT MAX(score_date) FROM mi_stock_scores"
        )
        if latest is None:
            return []
        rows = await conn.fetch(
            """SELECT ticker
               FROM mi_stock_scores
               WHERE score_date = $1
                 AND adv_20 IS NOT NULL
                 AND close IS NOT NULL
                 AND (adv_20 * close) >= $2
               ORDER BY (adv_20 * close) DESC NULLS LAST
               LIMIT $3""",
            latest, min_dollar_volume, max_tickers,
        )
    return [r["ticker"] for r in rows]


async def get_ep_scan_log_history(days: int = 14) -> dict[str, list[dict]]:
    """Return scan log grouped by date for the past N days — last-seen per ticker per day."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT scan_date, ticker, gap_pct, prev_close, rel_volume,
                      filter_reason, ep_score, score_tier, catalyst_quality
               FROM (
                   SELECT DISTINCT ON (scan_date, ticker)
                          scan_date, ticker, gap_pct, prev_close, rel_volume,
                          filter_reason, ep_score, score_tier, catalyst_quality,
                          scan_time_et
                   FROM mi_ep_scan_log
                   WHERE scan_date >= CURRENT_DATE - $1::int
                   ORDER BY scan_date, ticker, scan_time_et DESC NULLS LAST, id DESC
               ) latest
               ORDER BY scan_date DESC, ep_score DESC NULLS LAST, gap_pct DESC""",
            days,
        )
    result: dict[str, list] = {}
    for r in rows:
        key = str(r["scan_date"])
        result.setdefault(key, []).append(dict(r))
    return result


async def latest_market_data_date(as_of: date) -> date | None:
    """Return the most recent date ≤ as_of where EP or 9M scan data exists.

    Use case: pre-market / pre-scan windows (after midnight ET, before the 7 AM
    EP scan starts) and weekends/holidays where strict "today" returns empty.
    Generalizes the existing weekend-rollback pattern in last_trading_day() —
    weekends-only doesn't catch the post-midnight pre-scan window on weekdays
    (today is a trading day per the calendar, but no scan has run yet).

    Returns the actual date with data, or None if no scan data exists in the
    last 14 days (caller should fall back to last_trading_day).

    Cheap query: indexed alert_date columns, single MAX over each table.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT MAX(d) AS d FROM (
                SELECT MAX(alert_date) AS d FROM mi_ep_alerts
                  WHERE alert_date <= $1 AND alert_date >= $1 - INTERVAL '14 days'
                    AND COALESCE(source, 'live') = 'live'
                UNION ALL
                SELECT MAX(alert_date) FROM mi_9m_ep_alerts
                  WHERE alert_date <= $1 AND alert_date >= $1 - INTERVAL '14 days'
            ) t
            """,
            as_of,
        )
        return row["d"] if row else None


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
              AND COALESCE(a.source, 'live') = 'live'
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


async def get_active_themes(stale_after_days: int = 7) -> list[dict]:
    """
    Get the most recent snapshot of each active theme (stage != 'Retired')
    seen within the last `stale_after_days` calendar days.

    The recency cap is the de-facto retirement mechanism: when a theme stops
    appearing in daily snapshots (merged away during dedup, dropped during
    discovery, renamed, etc.) it falls out of "active" once the window passes.
    Without this, zombie themes from weeks ago keep getting re-validated every
    Mon/Wed/Fri against stale ticker lists and generate spurious cooldowns
    (135 cooldowns on 2026-04-24 traced to ~60 zombies last seen 2-4 weeks
    prior). 7 days covers normal weekend/holiday gaps with margin.

    RETIRED-GAP FIX (2026-06-09, #214 night-one root cause): the stage filter
    must apply to each name's LATEST row, not pre-filter the scan. The old
    shape (`WHERE stage != 'Retired'` inside the DISTINCT ON) skipped Retired
    rows and picked an OLDER non-Retired snapshot still inside the window —
    resurrecting freshly-retired themes with stale memberships ('Pure-Play
    Hydraulic Fracturing' came back 6/9 from its 6/3 row after validation
    emptied it 6/8; 'U.S. Shale & Onshore E&P' would have resurrected 6/10
    from its 6/8 row). It also silently defeated the synthetic-Retired-row
    mechanism (theme_auto_retired). Now: latest row per name first, THEN drop
    names whose latest row is Retired. restore_recently_retired_themes stays
    compatible — it DELETES bad rows, so the prior snapshot becomes latest.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT * FROM (
                SELECT DISTINCT ON (name) *
                FROM mi_themes
                WHERE theme_date >= CURRENT_DATE - ($1 || ' days')::INTERVAL
                ORDER BY name, theme_date DESC
            ) latest
            WHERE stage != 'Retired'
        """, str(stale_after_days))
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


async def get_undercut_rallies(d: "str | date") -> list[dict[str, Any]]:
    """Today's U&R (Undercut & Rally) detections (#98) for the evening-brief roundup.

    Reads the mi_flag_undercut_rally detector table for ur_date = d (ET date),
    excluding EOD-invalidated rows (parent_invalidated_eod=TRUE). Shadow telemetry —
    surfaced as a quiet daily digest, NOT intraday pings.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT ticker, parent_stage, base_low, undercut_low, undercut_pct,
                   current_price, reclaim_pct_above_base, in_sugar_baby_cohort
            FROM mi_flag_undercut_rally
            WHERE ur_date = $1
              AND parent_invalidated_eod = FALSE
            ORDER BY ur_time
        """, _to_date(d))
        return [dict(r) for r in rows]


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
    - mi_ep_catalyst_metrics: 180 days (covers B6 backtests against
      methodology changes; raw corpus columns ~50KB/row, ~15MB/month
      ingest — 6mo window holds ~90MB which is trivial on Hetzner)

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
            "mi_9m_ep_alerts":   today - timedelta(days=90),
            "mi_9m_day2_candidates": today - timedelta(days=90),
            "mi_sugar_babies_cohort": today - timedelta(days=365),
            "mi_flag_breaks": today - timedelta(days=365),
            "mi_stocks_in_play": today - timedelta(days=180),
            "mi_ep_catalyst_metrics": today - timedelta(days=180),
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
            "mi_9m_ep_alerts":   "alert_date",
            "mi_9m_day2_candidates": "alert_date",
            "mi_sugar_babies_cohort": "cohort_date",
            "mi_flag_breaks": "break_date",
            "mi_stocks_in_play": "entry_date",
            "mi_ep_catalyst_metrics": "alert_date",
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


# ── Splits (authoritative source — supersedes the rs_engine heuristics) ──


async def upsert_split(
    ticker: str,
    execution_date: date,
    split_from: int,
    split_to: int,
    polygon_id: str | None = None,
) -> bool:
    """Insert a Polygon split record. Returns True if newly inserted (re-fetch
    needed), False if already known. Idempotent — does not flip adjustment_applied."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            INSERT INTO mi_splits (ticker, execution_date, split_from, split_to, polygon_id)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (ticker, execution_date) DO NOTHING
            """,
            ticker, execution_date, split_from, split_to, polygon_id,
        )
        return result.endswith(" 1")


async def get_unapplied_splits(since: date | None = None) -> list[dict]:
    """All split rows where adjustment_applied = FALSE AND execution_date <= today.

    Future-dated splits are skipped: Polygon's adjusted=true feed only adjusts
    history for splits that have ALREADY executed. Applying a not-yet-executed
    split fetches un-adjusted history, marks the row applied, and never re-runs
    once the split actually executes — leaving mi_daily_closes with mismatched
    pre/post-split bars (ERNA 5/04 incident, 2026-05-07).

    Ordered by execution_date asc so multiple splits on one ticker apply in
    chronological order.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        if since is None:
            rows = await conn.fetch(
                """
                SELECT ticker, execution_date, split_from, split_to
                FROM mi_splits
                WHERE adjustment_applied = FALSE
                  AND execution_date <= CURRENT_DATE
                ORDER BY execution_date ASC, ticker ASC
                """
            )
        else:
            rows = await conn.fetch(
                """
                SELECT ticker, execution_date, split_from, split_to
                FROM mi_splits
                WHERE adjustment_applied = FALSE
                  AND execution_date >= $1
                  AND execution_date <= CURRENT_DATE
                ORDER BY execution_date ASC, ticker ASC
                """,
                since,
            )
        return [dict(r) for r in rows]


async def mark_split_applied(ticker: str, execution_date: date) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE mi_splits
            SET adjustment_applied = TRUE, applied_at = NOW()
            WHERE ticker = $1 AND execution_date = $2
            """,
            ticker, execution_date,
        )


async def reset_split_applied(ticker: str, execution_date: date) -> None:
    """Used by backfill_splits.py to force a re-apply of an already-applied row."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE mi_splits
            SET adjustment_applied = FALSE, applied_at = NULL
            WHERE ticker = $1 AND execution_date = $2
            """,
            ticker, execution_date,
        )


async def upsert_ticker_history(
    ticker: str,
    bars: list[dict],
) -> int:
    """Overwrite a ticker's daily history with split-adjusted bars from Polygon.

    Unlike `ingest_daily_closes`, this DOES update close + volume on conflict —
    it's the SSoT writer for split adjustments. `bars` items are Polygon
    `/v2/aggs/.../range/1/day` results (keys: t [epoch ms], o, h, l, c, v).
    """
    if not bars:
        return 0
    from datetime import datetime, timezone
    records = []
    for b in bars:
        if "c" not in b or "t" not in b:
            continue
        ts = datetime.fromtimestamp(b["t"] / 1000, tz=timezone.utc).date()
        records.append((
            ts, ticker,
            b["c"], int(b.get("v", 0)),
            b.get("o"), b.get("h"), b.get("l"),
        ))
    if not records:
        return 0
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO mi_daily_closes (trade_date, ticker, close, volume, open_price, high_price, low_price)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (trade_date, ticker) DO UPDATE SET
                close      = EXCLUDED.close,
                volume     = EXCLUDED.volume,
                open_price = COALESCE(EXCLUDED.open_price, mi_daily_closes.open_price),
                high_price = COALESCE(EXCLUDED.high_price, mi_daily_closes.high_price),
                low_price  = COALESCE(EXCLUDED.low_price,  mi_daily_closes.low_price)
            """,
            records,
        )
    return len(records)


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
        (
            trade_date, ticker,
            b["c"], int(b.get("v", 0)),
            b.get("o"), b.get("h"), b.get("l"),
        )
        for ticker, b in bars.items()
        if "c" in b and len(ticker) <= 5 and "." not in ticker
    ]
    async with pool.acquire() as conn:
        await conn.executemany("""
            INSERT INTO mi_daily_closes (trade_date, ticker, close, volume, open_price, high_price, low_price)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (trade_date, ticker) DO UPDATE SET
                open_price = COALESCE(EXCLUDED.open_price, mi_daily_closes.open_price),
                high_price = COALESCE(EXCLUDED.high_price, mi_daily_closes.high_price),
                low_price  = COALESCE(EXCLUDED.low_price,  mi_daily_closes.low_price)
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


# ── #270 anticipation re-entry lifecycle (Step 3 SHADOW) ────────────────────────


async def get_anticipation_gap_seeds(scan_date: date, seed_window_days: int = 25) -> list[dict]:
    """Coarse (ticker, gap_day) seeds in the recent window meeting the cohort predicate
    (close ≥ 1.4·prev_close AND vol ≥ 3·ADV20 AND close ≥ $5 AND vol·close ≥ $20M). The
    readiness job CONFIRMS each via replay() over full bars — this is just the cheap proposer
    (ADV is a window-median approximation; replay re-validates with its own ADV20)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            WITH adv AS (
                SELECT ticker, PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY volume) AS adv20
                FROM mi_daily_closes
                WHERE trade_date <= $1 AND trade_date >= $1 - INTERVAL '45 days' AND volume > 0
                GROUP BY ticker HAVING COUNT(*) >= 10
            ),
            seq AS (
                SELECT ticker, trade_date, low_price, volume, close,
                       LAG(close) OVER (PARTITION BY ticker ORDER BY trade_date) AS prev_close
                FROM mi_daily_closes
                WHERE trade_date <= $1 AND trade_date >= $1 - INTERVAL '45 days'
            )
            SELECT s.ticker, s.trade_date AS gap_day, s.low_price AS gap_day_low,
                   s.volume AS gap_day_vol
            FROM seq s JOIN adv a USING (ticker)
            WHERE s.prev_close IS NOT NULL
              AND s.close >= 1.40 * s.prev_close
              AND s.volume >= 3.0 * a.adv20
              AND s.close >= 5.0
              AND s.volume * s.close >= 20000000
              AND s.trade_date >= $1 - ($2::int * INTERVAL '1 day')
            ORDER BY s.ticker, s.trade_date
        """, scan_date, seed_window_days)
    return [dict(r) for r in rows]


async def get_anticipation_ohlcv(ticker: str, to_date: date, lookback_days: int = 340) -> list[dict]:
    """Ascending OHLCV bars for one ticker over [to_date − lookback_days, to_date] — enough
    history for the SMA200 gate before a recent gap + the forward settlement window."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT trade_date, open_price, high_price, low_price, close, volume
            FROM mi_daily_closes
            WHERE ticker = $1 AND trade_date <= $2
              AND trade_date >= $2 - ($3::int * INTERVAL '1 day')
            ORDER BY trade_date
        """, ticker, to_date, lookback_days)
    return [dict(r) for r in rows]


async def get_anticipation_state_map() -> dict[tuple, dict]:
    """{(ticker, gap_day): {state, entry_tactic, settled}} for every lifecycle row — the job's
    prior-state lookup for transition-dedup + minute-tactic-entry preservation. One query."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT ticker, gap_day, state, entry_tactic, settled FROM mi_anticipation_lifecycle"
        )
    return {(r["ticker"], r["gap_day"]): {"state": r["state"],
            "entry_tactic": r["entry_tactic"], "settled": r["settled"]} for r in rows}


async def upsert_anticipation_lifecycle(ticker: str, gap_day: date, *, state, gap_day_low,
        gap_day_vol, sma200_at_gap, armed_date, coiled_date, ready_date, triggered_date,
        entry_tactic, entry_price, stop_price, reenter_count, base_run, rmv_5d, rmv_15d,
        tight_close_pct, fwd_mfe_pct, realized_r, settled, last_eval) -> None:
    """UPSERT a derived lifecycle row. day0_fills is intentionally OMITTED — the 3b/execution
    watch owns it, and leaving it out of the SET clause preserves it on update."""
    def _dd(v):
        return date.fromisoformat(v) if isinstance(v, str) else v
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO mi_anticipation_lifecycle
                (ticker, gap_day, state, gap_day_low, gap_day_vol, sma200_at_gap,
                 armed_date, coiled_date, ready_date, triggered_date, entry_tactic,
                 entry_price, stop_price, reenter_count, base_run, rmv_5d, rmv_15d,
                 tight_close_pct, fwd_mfe_pct, realized_r, settled, last_eval, updated_at)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,NOW())
            ON CONFLICT (ticker, gap_day) DO UPDATE SET
                state=EXCLUDED.state, gap_day_low=EXCLUDED.gap_day_low,
                gap_day_vol=EXCLUDED.gap_day_vol, sma200_at_gap=EXCLUDED.sma200_at_gap,
                armed_date=EXCLUDED.armed_date, coiled_date=EXCLUDED.coiled_date,
                ready_date=EXCLUDED.ready_date, triggered_date=EXCLUDED.triggered_date,
                entry_tactic=EXCLUDED.entry_tactic, entry_price=EXCLUDED.entry_price,
                stop_price=EXCLUDED.stop_price, reenter_count=EXCLUDED.reenter_count,
                base_run=EXCLUDED.base_run, rmv_5d=EXCLUDED.rmv_5d, rmv_15d=EXCLUDED.rmv_15d,
                tight_close_pct=EXCLUDED.tight_close_pct, fwd_mfe_pct=EXCLUDED.fwd_mfe_pct,
                realized_r=EXCLUDED.realized_r, settled=EXCLUDED.settled,
                last_eval=EXCLUDED.last_eval, updated_at=NOW()
        """, ticker, gap_day, state, gap_day_low, gap_day_vol, sma200_at_gap,
             _dd(armed_date), _dd(coiled_date), _dd(ready_date), _dd(triggered_date), entry_tactic,
             entry_price, stop_price, reenter_count, base_run, rmv_5d, rmv_15d,
             tight_close_pct, fwd_mfe_pct, realized_r, settled, last_eval)


async def get_anticipation_lifecycle_board(limit: int = 40) -> list[dict]:
    """Lifecycle board for /sip — open rows first (recency), then recently settled."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT ticker, gap_day, state, entry_tactic, base_run, rmv_5d,
                   armed_date, coiled_date, ready_date, triggered_date,
                   realized_r, fwd_mfe_pct, settled, updated_at
            FROM mi_anticipation_lifecycle
            ORDER BY (state <> 'expired') DESC, updated_at DESC
            LIMIT $1
        """, limit)
    return [dict(r) for r in rows]


async def get_anticipation_watch_set() -> list[dict]:
    """The 3b watch set: armed/ready/coiled rows + the gap_day_low reference (the GDL/reclaim
    level for intraday FIRST5/gdl break detection). Anticipation-entered rows are already
    state='triggered' (excluded), so 3b only sees not-yet-entered set-ups. Read-only."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT ticker, gap_day, gap_day_low, state
            FROM mi_anticipation_lifecycle
            WHERE state IN ('armed', 'ready', 'coiled') AND settled = FALSE
        """)
    return [dict(r) for r in rows]


async def record_anticipation_3b_entry(ticker: str, gap_day: date, *, entry_tactic,
        entry_price, stop_price, triggered_date) -> bool:
    """Record a 3b FIRST5/gdl intraday entry: flip the row to state='triggered' with the entry,
    ONLY if it has not already entered (entry_tactic IS NULL — dedupe per name/day). Returns
    True iff a NEW entry was written."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        res = await conn.execute("""
            UPDATE mi_anticipation_lifecycle
            SET state='triggered', entry_tactic=$3, entry_price=$4, stop_price=$5,
                triggered_date=$6, updated_at=NOW()
            WHERE ticker=$1 AND gap_day=$2 AND entry_tactic IS NULL
        """, ticker, gap_day, entry_tactic, entry_price, stop_price, triggered_date)
    return res.endswith(" 1")


async def get_anticipation_3b_unsettled() -> list[dict]:
    """first5/gdl entries awaiting fill-sim settlement (triggered, not settled) + the inputs to
    re-locate the break + harvest (gap_day_low, entry_tactic, entry/stop, triggered_date)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT ticker, gap_day, gap_day_low, entry_tactic, entry_price, stop_price, triggered_date
            FROM mi_anticipation_lifecycle
            WHERE state='triggered' AND settled=FALSE
              AND entry_tactic IN ('first5_break', 'gdl_reclaim')
        """)
    return [dict(r) for r in rows]


async def settle_anticipation_3b(ticker: str, gap_day: date, *, realized_r, fwd_mfe_pct,
                               day0_fills) -> None:
    """Persist the fill-sim result for a first5/gdl entry: realized_r + fwd_mfe + the day-0
    scale-out fill record (JSONB), settled=TRUE."""
    import json
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE mi_anticipation_lifecycle
            SET realized_r=$3, fwd_mfe_pct=$4, day0_fills=$5::jsonb, settled=TRUE, updated_at=NOW()
            WHERE ticker=$1 AND gap_day=$2
        """, ticker, gap_day, realized_r, fwd_mfe_pct, json.dumps(day0_fills))


# ── Data-gated-review escalation state (#54 Prong B) ──────────────────────────


async def get_review_escalation_state() -> dict[str, dict[str, Any]]:
    """All escalation-state rows keyed by review_id (first_ready_date / first_error_date /
    last_escalated_date). Stateless check_pending_reviews + this = grace + dedup."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT review_id, first_ready_date, first_error_date, last_escalated_date "
            "FROM mi_review_escalation_state"
        )
    return {r["review_id"]: dict(r) for r in rows}


async def upsert_review_escalation_state(
    review_id: str, first_ready_date, first_error_date, last_escalated_date
) -> None:
    """Write the FULL desired state for one review (direct SET, not COALESCE — the caller
    computes the complete row so a field can be cleared, e.g. ready→error transitions)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO mi_review_escalation_state
                (review_id, first_ready_date, first_error_date, last_escalated_date, updated_at)
            VALUES ($1, $2, $3, $4, NOW())
            ON CONFLICT (review_id) DO UPDATE SET
                first_ready_date    = EXCLUDED.first_ready_date,
                first_error_date    = EXCLUDED.first_error_date,
                last_escalated_date = EXCLUDED.last_escalated_date,
                updated_at          = NOW()
            """,
            review_id, first_ready_date, first_error_date, last_escalated_date,
        )


async def clear_review_escalation_state(review_ids: list[str]) -> None:
    """Drop state for reviews that have resolved (no longer ready/erroring)."""
    if not review_ids:
        return
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM mi_review_escalation_state WHERE review_id = ANY($1)", review_ids
        )


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


async def get_descriptions_batch(tickers: "list[str]") -> dict[str, str]:
    """Cached company descriptions (mi_ticker_overrides) for a ticker set —
    the ANY-scoped sibling of get_ticker_overrides (read-only; no Haiku
    backfill; empty/NULL descriptions are simply absent)."""
    if not tickers:
        return {}
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT ticker, description FROM mi_ticker_overrides "
            "WHERE ticker = ANY($1) AND description IS NOT NULL AND description != ''",
            tickers,
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


async def get_sectors_batch(tickers: list[str]) -> dict[str, str]:
    """Bulk lookup of cached sectors from mi_ticker_overrides. Returns {ticker: sector}."""
    if not tickers:
        return {}
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT ticker, sector FROM mi_ticker_overrides WHERE ticker = ANY($1) AND sector IS NOT NULL AND sector != ''",
            tickers,
        )
    return {r["ticker"]: r["sector"] for r in rows}


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


async def get_9m_live_trades(days: int = 90) -> list[dict[str, Any]]:
    """Fetch live trades placed via the 9M Day 2 ORB system (catalyst_quality='9m_volume')."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, ticker, alert_date, status, entry_price, entry_shares,
                   stop_price, orb_high, orb_low, total_pnl, gap_pct,
                   remaining_shares, filled_at, closed_at, created_at
            FROM mi_live_trades
            WHERE catalyst_quality = '9m_volume'
              AND created_at >= NOW() - ($1 || ' days')::interval
            ORDER BY created_at DESC
        """, str(days))
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


# ── Shadow ORB telemetry (mi_orb_shadow_trades) ───────────────────────────────


async def insert_shadow_trade(row: dict[str, Any]) -> int | None:
    """Insert one shadow row. Returns id, or None on UNIQUE conflict.

    Required keys: ticker, alert_date, bar_size_minutes, signal_type, status.
    Optional: shape_tag, score_tier, orb_high, orb_low, atr_14,
    trigger_minute_et, entry_price, stop_price, hard_stop, risk_dollars,
    entry_shares, skip_reason, remaining_shares.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        rec = await conn.fetchrow("""
            INSERT INTO mi_orb_shadow_trades (
                ticker, alert_date, bar_size_minutes, signal_type, shape_tag,
                score_tier, orb_high, orb_low, atr_14, trigger_minute_et,
                entry_price, stop_price, hard_stop, risk_dollars, entry_shares,
                status, skip_reason, remaining_shares
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                $11, $12, $13, $14, $15, $16, $17, $18
            )
            ON CONFLICT (ticker, alert_date, bar_size_minutes) DO NOTHING
            RETURNING id
        """,
            row["ticker"], row["alert_date"], row["bar_size_minutes"],
            row["signal_type"], row.get("shape_tag"), row.get("score_tier"),
            row.get("orb_high"), row.get("orb_low"), row.get("atr_14"),
            row.get("trigger_minute_et"),
            row.get("entry_price"), row.get("stop_price"),
            row.get("hard_stop"), row.get("risk_dollars"),
            row.get("entry_shares"), row["status"],
            row.get("skip_reason"), row.get("remaining_shares") or 0,
        )
    return rec["id"] if rec else None


async def get_open_shadow_trades(bar_size_minutes: int | None = None
                                ) -> list[dict[str, Any]]:
    """Open shadow trades, optionally filtered by bar size."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        if bar_size_minutes is None:
            rows = await conn.fetch("""
                SELECT * FROM mi_orb_shadow_trades
                WHERE status = 'open' AND remaining_shares > 0
                ORDER BY alert_date ASC
            """)
        else:
            rows = await conn.fetch("""
                SELECT * FROM mi_orb_shadow_trades
                WHERE status = 'open' AND remaining_shares > 0
                  AND bar_size_minutes = $1
                ORDER BY alert_date ASC
            """, bar_size_minutes)
    return [dict(r) for r in rows]


async def update_shadow_trade(trade_id: int, fields: dict[str, Any]) -> None:
    """Partial update on a shadow row. fields keys must be safe column names."""
    if not fields:
        return
    allowed = {
        "status", "exits", "remaining_shares", "stop_price", "total_pnl",
        "hold_days", "partial_taken", "breakeven_active", "running_closes",
        "closed_at", "skip_reason",
    }
    set_clauses, values = [], []
    for i, (key, val) in enumerate(fields.items(), start=2):
        if key not in allowed:
            continue
        if key in ("exits", "running_closes"):
            set_clauses.append(f"{key} = ${i}::jsonb")
            values.append(json.dumps(val) if not isinstance(val, str) else val)
        else:
            set_clauses.append(f"{key} = ${i}")
            values.append(val)
    if not set_clauses:
        return
    sql = f"UPDATE mi_orb_shadow_trades SET {', '.join(set_clauses)} WHERE id = $1"
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(sql, trade_id, *values)


async def get_shadow_outcomes_window(window_days: int = 30,
                                     bar_size_minutes: int = 5
                                    ) -> list[dict[str, Any]]:
    """Per-alert paired comparison: shadow vs live, joined on (ticker, alert_date).

    Returns rows for downstream weekly-review aggregation. R is computed
    inline as total_pnl / NULLIF(risk_dollars, 0); neither side stores it.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT
              shadow.ticker, shadow.alert_date,
              shadow.signal_type, shadow.shape_tag,
              live.total_pnl   / NULLIF(live.risk_dollars,   0) AS r_1m,
              shadow.total_pnl / NULLIF(shadow.risk_dollars, 0) AS r_5m,
              live.status   AS status_1m,
              shadow.status AS status_5m,
              live.total_pnl   AS pnl_1m,
              shadow.total_pnl AS pnl_5m
            FROM mi_orb_shadow_trades shadow
            LEFT JOIN mi_live_trades live
              ON live.ticker = shadow.ticker
             AND live.alert_date = shadow.alert_date
            WHERE shadow.bar_size_minutes = $1
              AND shadow.alert_date >= CURRENT_DATE - ($2 || ' days')::interval
              AND shadow.status IN ('closed', 'no_entry', 'gate_blocked')
            ORDER BY shadow.alert_date DESC
        """, bar_size_minutes, str(window_days))
    return [dict(r) for r in rows]


# ── Theme exclusions ──────────────────────────────────────────────────────────


async def assign_ticker_to_theme(
    ticker: str, theme_name: str, scan_date: "str | date" = None,
) -> dict[str, Any]:
    """Manual operator override: anchor `ticker` to today's `theme_name` row.

    Bypasses the assignment LLM + post-validation. Used when the automated
    pipeline misses obvious matches (e.g. MU → 'AI Memory & Storage'). Adds
    DISTINCT-merged ticker to today's mi_themes row, lifts the matching
    cooldown row if any, emits `theme_manual_assignment` audit event.

    Returns {"matched": bool, "before": list, "after": list, "lifted_cooldown": bool}.
    """
    if scan_date is None:
        from agents.market_intelligence.collector import et_today
        scan_date = et_today()
    elif isinstance(scan_date, str):
        scan_date = date.fromisoformat(scan_date)
    ticker = ticker.upper()
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow("""
                SELECT id, tickers FROM mi_themes
                WHERE name = $1 AND theme_date = $2
            """, theme_name, scan_date)
            if not row:
                return {"matched": False, "before": [], "after": [], "lifted_cooldown": False}
            before = list(row["tickers"] or [])
            if ticker in before:
                return {"matched": True, "before": before, "after": before, "lifted_cooldown": False}
            after = sorted(set(before) | {ticker})
            await conn.execute("""
                UPDATE mi_themes SET tickers = $2 WHERE id = $1
            """, row["id"], after)
            # Lift any active cooldown for (ticker, theme_name) — operator override
            # supersedes the automated cooldown.
            lifted = await conn.fetchval("""
                UPDATE mi_validation_cooldowns
                SET bypassed = TRUE, bypassed_at = NOW(),
                    bypassed_reason = 'manual /theme assign override'
                WHERE ticker = $1 AND theme_name = $2 AND bypassed = FALSE
                RETURNING id
            """, ticker, theme_name)
            await log_audit_event(
                "theme_manual_assignment",
                summary=f"{ticker} → '{theme_name}' (manual override)",
                detail=json.dumps({
                    "ticker": ticker, "theme_name": theme_name,
                    "scan_date": scan_date.isoformat(),
                    "before": before, "after": after,
                    "cooldown_lifted": bool(lifted),
                }),
            )
    return {"matched": True, "before": before, "after": after,
            "lifted_cooldown": bool(lifted)}


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
                event_type, summary[:500], detail[:8000],
            )
    except Exception as e:
        logger.warning(f"audit log write failed ({event_type}): {e}")


async def get_sip_feed_telemetry(trade_date: date) -> dict[str, int]:
    """Summarize today's bar-stream / REST-backfill feed events for SIP monitoring.

    Returns counts for `orb_bar_fetched`, zero-range bars, subscribe failures,
    and bar-stream disconnects in the trading-day window (ET). Used by the
    4:10 PM EOD recap to surface silent feed degradation — if the Alpaca
    subscription lapses or SIP endpoint rejects our creds on a slow EP day,
    we otherwise have no HIGH-tier row to signal the problem.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
              COUNT(*) FILTER (WHERE event_type = 'orb_bar_fetched') AS bars_fetched,
              COUNT(*) FILTER (WHERE event_type = 'orb_bar_fetched'
                               AND detail LIKE '%range=0.00%')       AS zero_range,
              COUNT(*) FILTER (WHERE event_type = 'orb_subscribe_failed') AS subscribe_failed,
              COUNT(*) FILTER (WHERE event_type = 'bar_stream_disconnect') AS stream_disconnect
            FROM mi_audit_log
            WHERE created_at >= ($1::date AT TIME ZONE 'America/New_York')
              AND created_at <  (($1::date + INTERVAL '1 day')::date AT TIME ZONE 'America/New_York')
            """,
            trade_date,
        )
    return {
        "bars_fetched":      int(row["bars_fetched"] or 0),
        "zero_range":        int(row["zero_range"] or 0),
        "subscribe_failed":  int(row["subscribe_failed"] or 0),
        "stream_disconnect": int(row["stream_disconnect"] or 0),
    }


# ── Audit metric baselines (L2 anomaly detection) ──────────────────────────────

async def upsert_metric_baseline(
    metric_name: str,
    as_of_date: date,
    *,
    p50: float | None,
    p95: float | None,
    mad: float | None,
    sample_n: int,
) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO mi_metric_baselines (metric_name, as_of_date, p50, p95, mad, sample_n)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (metric_name, as_of_date) DO UPDATE SET
                p50 = EXCLUDED.p50,
                p95 = EXCLUDED.p95,
                mad = EXCLUDED.mad,
                sample_n = EXCLUDED.sample_n,
                updated_at = NOW()
            """,
            metric_name, as_of_date, p50, p95, mad, sample_n,
        )


async def get_metric_baseline(metric_name: str, as_of_date: date | None = None) -> dict | None:
    """Latest baseline ≤ as_of_date (defaults to today). None if none exists."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        if as_of_date is None:
            row = await conn.fetchrow(
                """
                SELECT metric_name, as_of_date, p50, p95, mad, sample_n
                FROM mi_metric_baselines
                WHERE metric_name = $1
                ORDER BY as_of_date DESC LIMIT 1
                """,
                metric_name,
            )
        else:
            row = await conn.fetchrow(
                """
                SELECT metric_name, as_of_date, p50, p95, mad, sample_n
                FROM mi_metric_baselines
                WHERE metric_name = $1 AND as_of_date <= $2
                ORDER BY as_of_date DESC LIMIT 1
                """,
                metric_name, as_of_date,
            )
    return dict(row) if row else None


async def get_baseline_reset(metric_name: str) -> datetime | None:
    """Most recent epoch reset for `metric_name`. Baseline computation must
    drop any history older than this timestamp."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT reset_at FROM mi_baseline_resets
            WHERE metric_name = $1 ORDER BY reset_at DESC LIMIT 1
            """,
            metric_name,
        )
    return row["reset_at"] if row else None


async def add_baseline_reset(metric_name: str, reason: str) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO mi_baseline_resets (metric_name, reason) VALUES ($1, $2)",
            metric_name, reason,
        )


async def count_today_anomalies(audit_key: str, on_date: date | None = None) -> int:
    """Dedup helper for L1/L2: have we already written an `anomaly_detected`
    row for this `(audit_key, date)` pair? `audit_key` is the invariant
    name or metric name, encoded into the detail JSON as `key`."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        if on_date is None:
            row = await conn.fetchrow(
                """
                SELECT COUNT(*) AS n FROM mi_audit_log
                WHERE event_type = 'anomaly_detected'
                  AND detail LIKE $1
                  AND (created_at AT TIME ZONE 'America/New_York')::date = (NOW() AT TIME ZONE 'America/New_York')::date
                """,
                f'%"key": "{audit_key}"%',
            )
        else:
            row = await conn.fetchrow(
                """
                SELECT COUNT(*) AS n FROM mi_audit_log
                WHERE event_type = 'anomaly_detected'
                  AND detail LIKE $1
                  AND (created_at AT TIME ZONE 'America/New_York')::date = $2
                """,
                f'%"key": "{audit_key}"%', on_date,
            )
    return int(row["n"] or 0)


# ── Validation cooldowns ───────────────────────────────────────────────────────

async def add_validation_cooldown(
    ticker: str, theme_name: str, reason: str = "", days: int = 14
) -> int:
    """
    Upsert a cooldown for ticker+theme. On conflict, increments removal_count and resets timer.
    Returns the new removal_count.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO mi_validation_cooldowns (ticker, theme_name, removal_reason, cooldown_until)
            VALUES ($1, $2, $3, NOW() + ($4 || ' days')::INTERVAL)
            ON CONFLICT (ticker, theme_name) DO UPDATE SET
                removed_at = NOW(),
                cooldown_until = NOW() + ($4 || ' days')::INTERVAL,
                removal_reason = $3,
                removal_count = mi_validation_cooldowns.removal_count + 1,
                bypassed = FALSE,
                bypassed_at = NULL,
                bypassed_reason = NULL
            RETURNING removal_count
        """, ticker, theme_name, reason[:500], str(days))
        return row["removal_count"] if row else 1


async def get_active_cooldowns() -> list[dict[str, Any]]:
    """Return all non-bypassed cooldowns that haven't expired yet."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT ticker, theme_name, removed_at, cooldown_until, removal_reason,
                   removal_count, bypassed
            FROM mi_validation_cooldowns
            WHERE NOT bypassed AND cooldown_until > NOW()
            ORDER BY removal_count DESC, cooldown_until ASC
        """)
    return [dict(r) for r in rows]


async def _get_validation_pair_set(bypassed: bool) -> set[tuple[str, str]]:
    """Shared fetch for the two (ticker, theme_name) pair sets kept in
    mi_validation_cooldowns (#217 — the two public wrappers differed only in
    the WHERE clause). bypassed=False → active NON-bypassed cooldowns, which
    expire with cooldown_until. bypassed=True → operator-protected pairs, no
    time bound — the operator's protection outlives the original 14d window."""
    where = "bypassed" if bypassed else "NOT bypassed AND cooldown_until > NOW()"
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"SELECT DISTINCT ticker, theme_name FROM mi_validation_cooldowns WHERE {where}"
        )
    return {(r["ticker"], r["theme_name"]) for r in rows}


async def get_cooldown_set() -> set[tuple[str, str]]:
    """Return {(ticker, theme_name)} for active cooldowns — O(1) lookup.
    Suppresses re-ASSIGNMENT of recently validation-removed pairs."""
    return await _get_validation_pair_set(bypassed=False)


async def get_operator_protected_set() -> set[tuple[str, str]]:
    """Return {(ticker, theme_name)} for OPERATOR-BYPASSED cooldowns.

    A bypassed cooldown means the operator explicitly said "this ticker belongs
    in this theme" (via /bypass or a manual mi_themes re-add + bypass_cooldown).
    That judgment is permanent: membership validation must NEVER re-remove a
    protected pair. This is the shield that survives image rebuilds — the
    decision lives in the DB row, not in process memory.

    Distinct from get_cooldown_set (active, NON-bypassed cooldowns suppress
    re-ASSIGNMENT); this set suppresses re-REMOVAL. No NOW() bound — the
    operator's protection does not expire when the original 14d cooldown would.
    """
    return await _get_validation_pair_set(bypassed=True)


async def get_globally_banned_tickers(
    min_distinct_themes: int = 3, lookback_days: int = 30
) -> dict[str, list[str]]:
    """Return {ticker: [theme names rejected from]} for tickers validation-removed
    from ≥ min_distinct_themes distinct themes within the last lookback_days.

    Per-(theme, ticker) cooldowns leak when a hallucinated ticker spreads across
    fragmented themes (DELL banned from "Satellite Imagery" can still land in
    "Satellite Mobile"). This is a global theme-assignment hard ban — once a
    ticker has been removed from N distinct themes, the theme engine treats
    its descriptions as untrusted for the lookback window.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT ticker, array_agg(DISTINCT theme_name) AS themes
            FROM mi_validation_cooldowns
            WHERE NOT bypassed
              AND removed_at >= NOW() - ($1 || ' days')::INTERVAL
            GROUP BY ticker
            HAVING COUNT(DISTINCT theme_name) >= $2
            """,
            str(lookback_days), min_distinct_themes,
        )
    return {r["ticker"]: list(r["themes"]) for r in rows}


async def bypass_cooldown(ticker: str, theme_name: str | None = None, reason: str = "") -> int:
    """
    Set bypassed=True for matching rows. theme_name=None bypasses all themes for ticker.
    Returns count of rows updated.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        if theme_name:
            result = await conn.execute("""
                UPDATE mi_validation_cooldowns
                SET bypassed = TRUE, bypassed_at = NOW(), bypassed_reason = $3
                WHERE ticker = $1 AND theme_name = $2
            """, ticker, theme_name, reason[:500])
        else:
            result = await conn.execute("""
                UPDATE mi_validation_cooldowns
                SET bypassed = TRUE, bypassed_at = NOW(), bypassed_reason = $2
                WHERE ticker = $1
            """, ticker, reason[:500])
        # asyncpg returns "UPDATE N" as status string
        try:
            return int(result.split()[-1])
        except (ValueError, IndexError):
            return 0


# ── Correlation clusters ───────────────────────────────────────────────────────

async def get_closes_for_correlation(
    from_date: date, to_date: date,
    min_avg_dollar_volume: float = 20_000_000.0,
) -> dict[str, list[float]]:
    """
    Return {ticker: [closes in ascending date order]} for the given window.
    Filters: close >= $5, common stock only (SPY exempted for beta adjustment),
    avg daily dollar volume >= min_avg_dollar_volume (default $20M keeps the
    downstream correlation matrix within the 512MB market-agent container).
    Only tickers with full coverage across all trading days are returned.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT dc.ticker, dc.trade_date, dc.close
            FROM mi_daily_closes dc
            LEFT JOIN mi_security_types st ON st.ticker = dc.ticker
            WHERE dc.trade_date >= $1
              AND dc.trade_date <= $2
              AND dc.close >= 5.0
              AND (
                  dc.ticker = 'SPY'
                  OR (st.security_type = ANY($4)
                      AND dc.ticker IN (
                          SELECT ticker
                          FROM mi_daily_closes
                          WHERE trade_date >= $1 AND trade_date <= $2 AND close >= 5.0
                            AND volume IS NOT NULL AND volume > 0
                          GROUP BY ticker
                          HAVING AVG(close * volume) >= $3
                      ))
              )
            ORDER BY dc.ticker, dc.trade_date
        """, from_date, to_date, min_avg_dollar_volume, list(COMMON_STOCK_TYPES))

    # Group by ticker
    from collections import defaultdict
    data: dict[str, list[tuple[date, float]]] = defaultdict(list)
    for r in rows:
        data[r["ticker"]].append((r["trade_date"], r["close"]))

    # Count trading days in window to know required length
    dates_in_window: set = {r["trade_date"] for r in rows}
    n_days = len(dates_in_window)
    if n_days < 21:  # need 21 closes to get 20 daily returns
        logger.warning(f"get_closes_for_correlation: only {n_days} trading days in window — need ≥ 21")
        return {}

    # Only keep tickers with full coverage
    result: dict[str, list[float]] = {}
    for ticker, pairs in data.items():
        if len(pairs) >= n_days:
            result[ticker] = [p[1] for p in pairs]

    return result


async def upsert_correlation_clusters(
    cluster_date: date, clusters: list[dict]
) -> None:
    """Replace today's cluster rows with fresh data."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM mi_correlation_clusters WHERE cluster_date = $1",
            cluster_date,
        )
        if not clusters:
            return
        rows = []
        for c in clusters:
            for ticker in c["tickers"]:
                rows.append((
                    cluster_date,
                    c["cluster_hash"],
                    ticker,
                    c["member_count"],
                    c["mean_corr"],
                    c.get("avg_rs", 0.0),
                ))
        await conn.executemany("""
            INSERT INTO mi_correlation_clusters
                (cluster_date, cluster_hash, ticker, member_count, mean_corr, avg_rs)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (cluster_date, cluster_hash, ticker) DO UPDATE SET
                member_count = EXCLUDED.member_count,
                mean_corr = EXCLUDED.mean_corr,
                avg_rs = EXCLUDED.avg_rs
        """, rows)


async def get_correlation_clusters(cluster_date: str | date) -> list[dict]:
    """Return clusters for the given date, grouped by cluster_hash."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT cluster_hash, ticker, member_count, mean_corr, avg_rs
            FROM mi_correlation_clusters
            WHERE cluster_date = $1
            ORDER BY mean_corr DESC, cluster_hash
        """, _to_date(cluster_date))

    from collections import defaultdict
    groups: dict[str, dict] = {}
    for r in rows:
        h = r["cluster_hash"]
        if h not in groups:
            groups[h] = {
                "cluster_hash": h,
                "tickers": [],
                "member_count": r["member_count"],
                "mean_corr": r["mean_corr"],
                "avg_rs": r["avg_rs"],
            }
        groups[h]["tickers"].append(r["ticker"])

    return list(groups.values())


async def get_audit_log(
    limit: int = 30,
    event_type: str | None = None,
    since_hours: int = 48,
    event_type_like: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch recent audit log entries, newest first.
    event_type: exact match. event_type_like: SQL LIKE pattern (e.g. '%error%').
    """
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
        elif event_type_like:
            rows = await conn.fetch("""
                SELECT id, created_at, event_type, summary, detail
                FROM mi_audit_log
                WHERE event_type LIKE $1
                  AND created_at >= NOW() - ($2 || ' hours')::INTERVAL
                ORDER BY created_at DESC
                LIMIT $3
            """, event_type_like, str(since_hours), limit)
        else:
            rows = await conn.fetch("""
                SELECT id, created_at, event_type, summary, detail
                FROM mi_audit_log
                WHERE created_at >= NOW() - ($1 || ' hours')::INTERVAL
                ORDER BY created_at DESC
                LIMIT $2
            """, str(since_hours), limit)
    return [dict(r) for r in rows]


# ── EP outcomes ───────────────────────────────────────────────────────────────


async def get_ep_outcomes(
    days_back: int = 90,
    tier: str | None = None,
    include_unknown: bool = False,
    use_live: bool | None = None,
) -> list[dict[str, Any]]:
    """
    Return each EP alert enriched with trade data and forward returns.

    Joins mi_live_trades when LIVE_TRADING_ENABLED (or use_live=True is passed);
    otherwise joins mi_paper_trades. `last_entry_price` is derived as entry_price
    for live mode (column is named differently in the two tables).

    Derives trade_status:
      'traded'    — row exists with no skip_reason (entry attempted/filled/closed)
      'filtered'  — skip_reason set (ORB too wide, ADV too low, infra, etc.)
      'no_attempt'— no trade row (pre-diagnostics era; should be zero post-deploy)

    Deduplicated via DISTINCT ON (ticker, alert_date). Excludes
    catalyst_quality='unknown' by default (pre-Claude early records).
    """
    if use_live is None:
        from agents.market_intelligence.constants import LIVE_TRADING_ENABLED
        use_live = LIVE_TRADING_ENABLED
    if use_live:
        trade_table = "mi_live_trades"
        entry_col = "entry_price"
    else:
        trade_table = "mi_paper_trades"
        entry_col = "last_entry_price"
    pool = await get_pool()
    async with pool.acquire() as conn:
        params: list[Any] = [days_back]
        filters = ["a.alert_date >= CURRENT_DATE - $1::int",
                   "COALESCE(a.source, 'live') = 'live'"]  # #268: replay rows out of outcome stats
        if not include_unknown:
            filters.append("a.catalyst_quality != 'unknown'")
        if tier:
            params.append(tier.upper())
            filters.append(f"a.score_tier = ${len(params)}")
        where = " AND ".join(filters)
        rows = await conn.fetch(f"""
            SELECT
                ticker, alert_date, score_tier, gap_pct, catalyst_quality, ep_score,
                fwd_1d_pct, fwd_1w_pct,
                pt_status, skip_reason, last_entry_price, total_pnl,
                CASE
                    WHEN pt_status IS NULL         THEN 'no_attempt'
                    WHEN skip_reason IS NOT NULL   THEN 'filtered'
                    ELSE 'traded'
                END AS trade_status
            FROM (
                SELECT DISTINCT ON (a.ticker, a.alert_date)
                    a.ticker, a.alert_date, a.score_tier, a.gap_pct,
                    a.catalyst_quality, a.ep_score,
                    o.fwd_1d_pct, o.fwd_1w_pct,
                    pt.status           AS pt_status,
                    pt.skip_reason      AS skip_reason,
                    pt.{entry_col}      AS last_entry_price,
                    pt.total_pnl        AS total_pnl
                FROM mi_ep_alerts a
                LEFT JOIN mi_signal_outcomes o
                    ON o.signal_type = 'ep_alert'
                   AND o.signal_date = a.alert_date
                   AND o.identifier = a.ticker
                LEFT JOIN {trade_table} pt
                    ON pt.ticker = a.ticker
                   AND pt.alert_date = a.alert_date
                WHERE {where}
                ORDER BY a.ticker, a.alert_date, a.ep_score DESC
            ) deduped
            ORDER BY alert_date DESC, ep_score DESC
        """, *params)
    return [dict(r) for r in rows]


# ── Trading journal ───────────────────────────────────────────────────────────


async def add_journal_entry(
    text: str,
    regime: str | None,
    ep_context: list[dict[str, Any]] | None,
    theme_context: str | None,
) -> int:
    """Insert a journal entry with auto-enriched context. Returns new row id."""
    import json as _json
    pool = await get_pool()
    ep_json = _json.dumps(ep_context) if ep_context else None
    async with pool.acquire() as conn:
        row_id = await conn.fetchval("""
            INSERT INTO mi_journal_entries (entry_text, regime, ep_context, theme_context)
            VALUES ($1, $2, $3::jsonb, $4)
            RETURNING id
        """, text, regime, ep_json, theme_context)
    return row_id


async def get_journal_entries(days_back: int = 7, limit: int = 20) -> list[dict[str, Any]]:
    """Return recent journal entries, newest first."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, entry_text, regime, ep_context, theme_context, created_at
            FROM mi_journal_entries
            WHERE created_at >= NOW() - ($1 || ' days')::INTERVAL
            ORDER BY created_at DESC
            LIMIT $2
        """, str(days_back), limit)
    return [dict(r) for r in rows]


async def get_paper_trade_stats() -> list[dict[str, Any]]:
    """
    Return all closed paper trades enriched with regime and forward returns.
    Used for the P3 validation report.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT
                t.ticker, t.total_pnl, t.hold_days, t.ep_score,
                t.gap_pct, t.catalyst_quality, t.alert_date,
                r.regime,
                o.fwd_1d_pct, o.fwd_1w_pct
            FROM mi_paper_trades t
            LEFT JOIN mi_market_regime r ON r.regime_date = t.alert_date
            LEFT JOIN mi_signal_outcomes o
                ON o.signal_type = 'ep_alert'
                AND o.signal_date = t.alert_date
                AND o.identifier = t.ticker
            WHERE t.status = 'closed'
            ORDER BY t.alert_date DESC
        """)
    return [dict(r) for r in rows]


# ── HUD state ──────────────────────────────────────────────────────────────────

async def get_hud_state(key: str) -> str | None:
    """Return a stored HUD state value, or None if not set."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        val = await conn.fetchval(
            "SELECT value FROM mi_hud_state WHERE key = $1", key
        )
    return val or None


async def set_hud_state(key: str, value: str) -> None:
    """Upsert a HUD state key/value pair."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO mi_hud_state (key, value, updated_at)
            VALUES ($1, $2, NOW())
            ON CONFLICT (key) DO UPDATE SET value = $2, updated_at = NOW()
        """, key, value)


async def insert_system_review(review: dict) -> bool:
    """
    Upsert a weekly/monthly system review row.
    Expected keys: review_date, window_days, regime, summary, metrics, suggestions.
    Same (review_date, window_days) replaces prior row (supports mid-week reruns).

    metrics + suggestions go into JSONB columns. asyncpg's default JSON
    encoder can't serialize date/datetime objects — and the metrics dict
    is built from 17+ aggregator functions, any one of which may leak a
    raw date. Pre-serialize with `default=str` at this boundary so we
    don't have to chase every aggregator. JSONB column accepts a string
    transparently (PostgreSQL parses it on insert). 2026-05-17 fix —
    weekly_system_review job failed Sunday morning with "Object of type
    date is not JSON serializable".
    """
    pool = await get_pool()
    metrics_json = json.dumps(review.get("metrics") or {}, default=str)
    suggestions_json = json.dumps(review.get("suggestions") or [], default=str)
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO mi_system_reviews
                (review_date, window_days, regime, summary, metrics, suggestions)
            VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb)
            ON CONFLICT (review_date, window_days) DO UPDATE SET
                regime      = EXCLUDED.regime,
                summary     = EXCLUDED.summary,
                metrics     = EXCLUDED.metrics,
                suggestions = EXCLUDED.suggestions,
                created_at  = NOW()
        """,
            _to_date(review["review_date"]),
            int(review.get("window_days", 7)),
            review.get("regime"),
            review["summary"],
            metrics_json,
            suggestions_json,
        )
    return True


async def get_latest_system_review(window_days: int = 7) -> Optional[dict]:
    """Return the most recent review for the given window, or None."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT review_date, window_days, regime, summary, metrics, suggestions, created_at
            FROM mi_system_reviews
            WHERE window_days = $1
            ORDER BY review_date DESC
            LIMIT 1
        """, window_days)
    if not row:
        return None
    return {
        "review_date": row["review_date"].isoformat(),
        "window_days": row["window_days"],
        "regime": row["regime"],
        "summary": row["summary"],
        "metrics": row["metrics"],
        "suggestions": row["suggestions"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
    }


async def insert_weekly_watchlist(week_ending: "date", rows: list[dict]) -> int:
    """Replace the watchlist for a given week-ending date.

    Each row: {ticker, sources (list), composite_priority (int), reason_chip (str)}.
    Atomic: deletes existing rows for the week, then inserts the new set.
    Returns the number of rows inserted.
    """
    if not rows:
        return 0
    import json
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "DELETE FROM mi_weekly_watchlists WHERE week_ending = $1",
                _to_date(week_ending),
            )
            await conn.executemany("""
                INSERT INTO mi_weekly_watchlists
                    (week_ending, ticker, sources, composite_priority, reason_chip)
                VALUES ($1, $2, $3::jsonb, $4, $5)
            """, [
                (
                    _to_date(week_ending),
                    r["ticker"],
                    json.dumps(r["sources"]),
                    int(r["composite_priority"]),
                    r["reason_chip"],
                )
                for r in rows
            ])
    return len(rows)


async def insert_orb_extension_shadow_row(row: dict) -> None:
    """Insert a single shadow-trade row.

    Idempotent on (trade_id, cutoff_minute) — re-running for the same
    cancellation overwrites the prior row's would_fill / state / final_status.
    """
    import json
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO mi_orb_extension_shadow
                (trade_id, ticker, alert_date, cutoff_minute,
                 limit_price, stop_price, shares, cancelled_at,
                 would_fill, fill_at, fill_price, entry_attempts,
                 state, final_status, closed_at, total_pnl, hold_days,
                 last_close, last_evaluated_date)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,
                    $13::jsonb,$14,$15,$16,$17,$18,$19)
            ON CONFLICT (trade_id, cutoff_minute) DO UPDATE SET
                would_fill = EXCLUDED.would_fill,
                fill_at = EXCLUDED.fill_at,
                fill_price = EXCLUDED.fill_price,
                entry_attempts = EXCLUDED.entry_attempts,
                state = EXCLUDED.state,
                final_status = EXCLUDED.final_status,
                closed_at = EXCLUDED.closed_at,
                total_pnl = EXCLUDED.total_pnl,
                hold_days = EXCLUDED.hold_days,
                last_close = EXCLUDED.last_close,
                last_evaluated_date = EXCLUDED.last_evaluated_date,
                updated_at = NOW()
        """,
            int(row["trade_id"]), row["ticker"], _to_date(row["alert_date"]),
            int(row["cutoff_minute"]),
            row.get("limit_price"), row.get("stop_price"), row.get("shares"),
            row.get("cancelled_at"),
            row.get("would_fill"), row.get("fill_at"), row.get("fill_price"),
            row.get("entry_attempts"),
            _jsonb_param(row.get("state")),  # #179: codec single-encodes; do NOT pre-dumps
            row.get("final_status"),
            _to_date(row["closed_at"]) if row.get("closed_at") else None,
            row.get("total_pnl"),
            row.get("hold_days"),
            row.get("last_close"),
            _to_date(row["last_evaluated_date"]) if row.get("last_evaluated_date") else None,
        )


async def get_open_orb_extension_shadows() -> list[dict]:
    """Rows still tracking an open hypothetical position.

    Settlement job re-evaluates these from last_evaluated_date+1 forward.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, trade_id, ticker, alert_date, cutoff_minute,
                   limit_price, stop_price, shares, fill_at, fill_price,
                   state, last_evaluated_date
            FROM mi_orb_extension_shadow
            WHERE final_status = 'still_open'
        """)
    # #177: state was double-encoded on write (insert/update call json.dumps()
    # AND the jsonb codec encoder runs json.dumps() again), so the codec decoder
    # json.loads() once yields the inner JSON *string*, not a dict. Normalize
    # here so the settle job gets a dict. (Write-side root fix tracked separately.)
    import json
    out = []
    for r in rows:
        d = dict(r)
        if isinstance(d.get("state"), str):
            try:
                d["state"] = json.loads(d["state"])
            except (ValueError, TypeError):
                d["state"] = {}
        out.append(d)
    return out


async def update_orb_extension_shadow_state(
    shadow_id: int,
    *,
    state: dict,
    final_status: str,
    closed_at: "date | None",
    total_pnl: float,
    hold_days: int,
    last_close: float | None,
    last_evaluated_date: "date",
) -> None:
    """Persist a settlement-job step's updated state for one shadow row."""
    import json
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE mi_orb_extension_shadow
               SET state = $2::jsonb,
                   final_status = $3,
                   closed_at = $4,
                   total_pnl = $5,
                   hold_days = $6,
                   last_close = $7,
                   last_evaluated_date = $8,
                   updated_at = NOW()
             WHERE id = $1
        """,
            int(shadow_id),
            _jsonb_param(state),  # #179: codec single-encodes; do NOT pre-dumps (was double-encoding)
            final_status,
            _to_date(closed_at) if closed_at else None,
            total_pnl,
            int(hold_days),
            last_close,
            _to_date(last_evaluated_date),
        )


async def get_security_exchange_map(tickers: list[str]) -> dict[str, str]:
    """Return {ticker: exchange (MIC code)} for the given tickers.

    Tickers without a row in mi_security_types map to ''.
    """
    if not tickers:
        return {}
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT ticker, exchange
            FROM mi_security_types
            WHERE ticker = ANY($1)
        """, list(tickers))
    return {r["ticker"]: (r["exchange"] or "") for r in rows}


async def get_weekly_theme_churn(days: int = 7) -> list[dict]:
    """
    Detect tickers entering/exiting a theme ≥2× in the last `days` days.
    Computes adds/removes from consecutive daily snapshots in `mi_themes.tickers`.
    Returns rows ordered by total event_count desc, LIMIT 20.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            WITH snapshots AS (
                SELECT theme_date, name, tickers
                FROM mi_themes
                WHERE theme_date >= CURRENT_DATE - ($1::int + 1)
            ),
            with_prev AS (
                SELECT theme_date, name, tickers,
                       LAG(tickers) OVER (PARTITION BY name ORDER BY theme_date) AS prev_tickers
                FROM snapshots
            ),
            adds AS (
                SELECT theme_date, name, unnest(tickers) AS ticker, 'added' AS event
                FROM with_prev
                WHERE prev_tickers IS NOT NULL
                  AND theme_date >= CURRENT_DATE - $1::int
            ),
            add_events AS (
                SELECT a.theme_date, a.name, a.ticker, a.event
                FROM adds a
                JOIN with_prev wp ON wp.theme_date = a.theme_date AND wp.name = a.name
                WHERE NOT (a.ticker = ANY(wp.prev_tickers))
            ),
            removes AS (
                SELECT theme_date, name, unnest(prev_tickers) AS ticker, 'removed' AS event
                FROM with_prev
                WHERE prev_tickers IS NOT NULL
                  AND theme_date >= CURRENT_DATE - $1::int
            ),
            remove_events AS (
                SELECT r.theme_date, r.name, r.ticker, r.event
                FROM removes r
                JOIN with_prev wp ON wp.theme_date = r.theme_date AND wp.name = r.name
                WHERE NOT (r.ticker = ANY(wp.tickers))
            ),
            all_events AS (
                SELECT * FROM add_events UNION ALL SELECT * FROM remove_events
            )
            SELECT ticker,
                   name AS theme_name,
                   COUNT(*) FILTER (WHERE event = 'added')   AS add_count,
                   COUNT(*) FILTER (WHERE event = 'removed') AS remove_count,
                   COUNT(*) AS event_count
            FROM all_events
            GROUP BY ticker, name
            HAVING COUNT(*) >= 2
            ORDER BY event_count DESC
            LIMIT 20
        """, days)
    return [dict(r) for r in rows]


async def get_ticker_breadth_above_sma20(
    tickers: list[str], trade_date: "str | date"
) -> float | None:
    """Fraction of tickers with close > sma_20 on trade_date. None if no data.

    Leading decay indicator for theme health — a theme can score well on RS
    while most members have rolled over below their 20-day trend. Reads from
    mi_stock_scores (populated nightly for all RS-universe tickers)."""
    if not tickers:
        return None
    pool = await get_pool()
    d = _to_date(trade_date)
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT
                COUNT(*) FILTER (WHERE close > sma_20) AS above,
                COUNT(*) FILTER (WHERE sma_20 IS NOT NULL AND close IS NOT NULL) AS total
            FROM mi_stock_scores
            WHERE ticker = ANY($1) AND score_date = $2
        """, tickers, d)
    if not row or not row["total"]:
        return None
    return round(row["above"] / row["total"], 3)
