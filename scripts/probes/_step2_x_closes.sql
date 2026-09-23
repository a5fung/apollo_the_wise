\pset format unaligned
\pset fieldsep '\t'
\pset footer off
SELECT trade_date, ticker, close, open_price FROM mi_daily_closes WHERE trade_date >= '2026-02-01' AND (ticker='SPY' OR ticker IN (SELECT ticker FROM mi_ticker_overrides) OR ticker IN (SELECT DISTINCT ticker FROM mi_theme_axis_shadow) OR ticker IN (SELECT DISTINCT ticker FROM mi_ep_scan_log) OR ticker IN (SELECT DISTINCT ticker FROM mi_stock_scores WHERE sector IS NOT NULL AND score_date >= '2026-02-01')) ORDER BY ticker, trade_date;
