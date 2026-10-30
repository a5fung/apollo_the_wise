SET default_transaction_read_only = on;
\echo == themes listing FTAI, last 10 days
SELECT theme_date, name, stage, source FROM mi_themes WHERE 'FTAI' = ANY(tickers) AND theme_date >= DATE '2026-10-19' ORDER BY theme_date DESC, name LIMIT 20;
\echo == defense-named themes, last 3 days (stage, size, FTAI in?)
SELECT theme_date, name, stage, cardinality(tickers) n, 'FTAI' = ANY(tickers) AS has_ftai FROM mi_themes
WHERE theme_date >= DATE '2026-10-26' AND (name ILIKE '%defen%' OR name ILIKE '%aerospace%' OR name ILIKE '%military%' OR name ILIKE '%aviation%') ORDER BY theme_date DESC, name;
\echo == the scan log's recorded theme flag for FTAI today
SELECT (scan_time_et AT TIME ZONE 'America/New_York')::time(0) t, in_active_theme FROM mi_ep_scan_log WHERE ticker='FTAI' AND scan_date='2026-10-29' AND ep_score IS NOT NULL ORDER BY scan_time_et;
