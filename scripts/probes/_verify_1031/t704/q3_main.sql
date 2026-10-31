SET default_transaction_read_only = on;
\echo == (1) every split row handled since the 10-18 deploy, by outcome
SELECT adjustment_outcome, count(*), min(applied_at AT TIME ZONE 'America/New_York')::date AS first_et, max(applied_at AT TIME ZONE 'America/New_York')::date AS last_et
FROM mi_splits WHERE applied_at >= '2026-10-18' GROUP BY 1 ORDER BY 1;
\echo == (2) WOULD-FAIL-IF: applied TRUE with outcome NULL after the deploy
SELECT count(*) FROM mi_splits WHERE adjustment_applied AND adjustment_outcome IS NULL AND applied_at >= '2026-10-18';
\echo == (3) any phantom row ever, and rows since 10-21 with their factor
SELECT ticker, execution_date, adjustment_outcome, applied_factor, (applied_at AT TIME ZONE 'America/New_York') AS applied_et
FROM mi_splits WHERE adjustment_outcome = 'phantom' OR applied_at >= '2026-10-21' ORDER BY applied_at;
