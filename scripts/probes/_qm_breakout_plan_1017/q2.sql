-- READ-ONLY, cheap (index lookups + planner estimates), statement_timeout 30s. Data inventory for the Consolidation Breakout plan.
SET statement_timeout = '30s';
SELECT 'daily SPY first/last' k, min(trade_date)::text a, max(trade_date)::text b FROM mi_daily_closes WHERE ticker='SPY';
SELECT 'daily AAPL first' k, min(trade_date)::text FROM mi_daily_closes WHERE ticker='AAPL';
SELECT 'daily tickers on 2024-06-03' k, count(*)::text FROM mi_daily_closes WHERE trade_date='2024-06-03';
SELECT 'daily tickers on 2026-10-16' k, count(*)::text FROM mi_daily_closes WHERE trade_date='2026-10-16';
SELECT 'scores first/last' k, min(score_date)::text, max(score_date)::text FROM mi_stock_scores WHERE ticker='AAPL';
SELECT 'themes first/last' k, min(theme_date)::text, max(theme_date)::text FROM mi_themes;
SELECT 'regime first/last' k, min(regime_date)::text, max(regime_date)::text FROM mi_market_regime;
SELECT relname, reltuples::bigint FROM pg_class WHERE relname IN ('mi_daily_closes','mi_intraday_bars','mi_stock_scores','mi_themes','mi_market_regime');
