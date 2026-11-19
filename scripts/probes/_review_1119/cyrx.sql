SET default_transaction_read_only = on;
SELECT min(low) lo, max(high) hi, count(*) n, min(bar_time AT TIME ZONE 'America/New_York') first, max(bar_time AT TIME ZONE 'America/New_York') last,
 min(bar_time AT TIME ZONE 'America/New_York') FILTER (WHERE high >= 20.37) first_cross
FROM mi_intraday_bars WHERE ticker='CYRX' AND (bar_time AT TIME ZONE 'America/New_York')::date='2026-11-17';
SELECT event_type, created_at AT TIME ZONE 'America/New_York', left(detail::text,300) FROM mi_audit_log WHERE detail LIKE '%CYRX%' AND created_at::date BETWEEN '2026-11-17' AND '2026-11-18' ORDER BY created_at;
