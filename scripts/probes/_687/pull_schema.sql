-- #687 read-only prod pull 1: mi_daily_closes schema + coverage (captured once).
\echo === COLS ===
SELECT column_name, data_type FROM information_schema.columns WHERE table_name='mi_daily_closes' ORDER BY ordinal_position;
\echo === COVERAGE ===
SELECT date_trunc('month', trade_date)::date AS m, count(*) AS rows, count(DISTINCT ticker) AS tickers,
       count(open_price) AS with_open, count(high_price) AS with_high, count(volume) AS with_vol
FROM mi_daily_closes WHERE trade_date >= '2023-10-01' AND trade_date <= '2026-06-30'
GROUP BY 1 ORDER BY 1;
\echo === IDX ===
SELECT indexname, indexdef FROM pg_indexes WHERE tablename='mi_daily_closes';
\echo === INTRADAY_COV ===
SELECT date_trunc('month', bar_time AT TIME ZONE 'America/New_York')::date AS m, count(*) AS bars, count(DISTINCT ticker) AS tickers
FROM mi_intraday_bars GROUP BY 1 ORDER BY 1;
