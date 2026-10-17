-- READ-ONLY. Data inventory for planning the Qullamaggie breakout test (2026-10-17).
SELECT 'mi_daily_closes' t, min(trade_date) first, max(trade_date) last, count(DISTINCT ticker) tickers, count(*) rows FROM mi_daily_closes
UNION ALL SELECT 'mi_stock_scores', min(score_date), max(score_date), count(DISTINCT ticker), count(*) FROM mi_stock_scores
UNION ALL SELECT 'mi_themes', min(theme_date), max(theme_date), count(DISTINCT name), count(*) FROM mi_themes
UNION ALL SELECT 'mi_market_regime', min(regime_date), max(regime_date), count(DISTINCT regime), count(*) FROM mi_market_regime
UNION ALL SELECT 'mi_intraday_bars', min(bar_time)::date, max(bar_time)::date, count(DISTINCT ticker), count(*) FROM mi_intraday_bars;
SELECT extract(year from trade_date)::int y, count(DISTINCT ticker) tickers, count(*) rows FROM mi_daily_closes GROUP BY 1 ORDER BY 1;
SELECT regime, count(*) FROM mi_market_regime GROUP BY 1 ORDER BY 2 DESC;
