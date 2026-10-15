\set QUIET on
\pset format unaligned
\pset fieldsep '|'
\pset footer off
\pset null ''
SELECT 'M1_cols' AS chk, string_agg(column_name, ',' ORDER BY ordinal_position) FROM information_schema.columns WHERE table_name='mi_daily_closes';
SELECT 'M2_provenance_daily' AS chk, created_at AT TIME ZONE 'America/New_York' AS at_et, left(summary,400) AS summary FROM mi_audit_log WHERE created_at >= TIMESTAMPTZ '2026-10-15 00:00-04' AND event_type='ep_provenance_daily';
SELECT 'M3_catalyst_prov' AS chk, created_at AT TIME ZONE 'America/New_York' AS at_et, left(summary,200) AS summary FROM mi_audit_log WHERE created_at >= TIMESTAMPTZ '2026-10-15 00:00-04' AND event_type='ep_catalyst_provenance' ORDER BY created_at;
SELECT 'M4_bars' AS chk, ticker, trade_date, open_price, high_price, low_price FROM mi_daily_closes WHERE ticker IN ('VICR','GNRC') AND trade_date >= DATE '2026-09-17' ORDER BY ticker, trade_date;
