SET default_transaction_read_only = on;
\echo == A live themes holding RIOT / SECZ / CSQR on 11-12 and 11-13
SELECT theme_date, source, name, stage, round(score::numeric,1) AS score, cardinality(tickers) AS members, tickers FROM mi_themes WHERE theme_date >= '2026-11-12' AND tickers && ARRAY['RIOT','SECZ','CSQR'] ORDER BY theme_date, name;
\echo == B sectors of the Home Pest Control members
SELECT ticker, sector FROM mi_ticker_overrides WHERE ticker IN ('ROL','RTO','SMG');
\echo == C exempt read as the engine would run it tonight (promos in lookback + night dates)
SELECT (created_at AT TIME ZONE 'America/New_York')::date AS d, summary FROM mi_audit_log WHERE event_type='theme_operator_promoted' AND (created_at AT TIME ZONE 'America/New_York')::date >= DATE '2026-11-16' - 30 ORDER BY 1;
