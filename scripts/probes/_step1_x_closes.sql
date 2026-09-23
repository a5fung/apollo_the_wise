\pset format unaligned
\pset fieldsep '\t'
\pset footer off

SELECT trade_date, ticker, close, open_price FROM mi_daily_closes WHERE trade_date >= '2026-01-15' AND (ticker='SPY' OR ticker IN (SELECT DISTINCT unnest(tickers) FROM mi_themes)) ORDER BY ticker, trade_date;
