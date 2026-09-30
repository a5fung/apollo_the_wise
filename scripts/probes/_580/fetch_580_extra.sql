\pset tuples_only on
\pset format unaligned
\echo '## created_at (ET hour) of mi_themes rows by theme_date, last 6 dates'
SELECT theme_date, min(created_at AT TIME ZONE 'America/New_York') AS first_ET, max(created_at AT TIME ZONE 'America/New_York') AS last_ET, count(*) FROM mi_themes WHERE theme_date >= DATE '2026-09-23' GROUP BY 1 ORDER BY 1 DESC;
\echo '## Retired rows that still carry tickers (all history)'
SELECT count(*) FILTER (WHERE cardinality(tickers)>0) AS retired_with_tickers, count(*) AS retired_total FROM mi_themes WHERE stage='Retired';
\echo '## NULL pct_above_20sma on latest date, non-Retired'
SELECT name, stage, cardinality(tickers) n_tk, days_active, source, round(rs_avg::numeric,1) rs_avg, round(score::numeric,1) score FROM mi_themes WHERE theme_date=DATE '2026-09-29' AND stage<>'Retired' AND pct_above_20sma IS NULL ORDER BY score DESC;
\echo '## NULL breadth rate non-Retired, last 8 theme_dates'
SELECT theme_date, count(*) FILTER (WHERE stage<>'Retired') nonretired, count(*) FILTER (WHERE stage<>'Retired' AND pct_above_20sma IS NULL) null_breadth FROM mi_themes WHERE theme_date >= DATE '2026-09-17' GROUP BY 1 ORDER BY 1 DESC;
\echo '## source values on latest date'
SELECT source, stage, count(*), count(*) FILTER (WHERE pct_above_20sma IS NULL) null_brd FROM mi_themes WHERE theme_date=DATE '2026-09-29' GROUP BY 1,2 ORDER BY 1,2;
\echo '## n_tk distribution latest non-Retired non-Fading'
SELECT min(cardinality(tickers)), percentile_cont(0.5) WITHIN GROUP (ORDER BY cardinality(tickers)), max(cardinality(tickers)), count(*) FILTER (WHERE cardinality(tickers)<3) lt3, count(*) FROM mi_themes WHERE theme_date=DATE '2026-09-29' AND stage NOT IN ('Retired','Fading');
