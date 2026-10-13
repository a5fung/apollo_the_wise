\set QUIET on
\pset format unaligned
\pset fieldsep '|'
\pset footer off
\pset null ''
SELECT '6_ep_alerts_by_date' AS chk, alert_date, count(*) AS n_alerts, count(*) FILTER (WHERE score_tier='HIGH') AS n_high FROM mi_ep_alerts WHERE alert_date >= DATE '2026-10-05' GROUP BY alert_date ORDER BY alert_date;
SELECT '7_shadow_by_date' AS chk, alert_date, count(*) AS n_shadow FROM mi_alert_rank_shadow WHERE alert_date >= DATE '2026-10-05' GROUP BY alert_date ORDER BY alert_date;
SELECT '8_closes_per_day' AS chk, trade_date, count(*) FROM mi_daily_closes WHERE trade_date >= DATE '2026-10-05' GROUP BY trade_date ORDER BY trade_date;
SELECT '9_audit_rank' AS chk, event_type, left(summary,120) AS summary, created_at AT TIME ZONE 'America/New_York' AS at_et FROM mi_audit_log WHERE event_type ILIKE '%rank_shadow%' ORDER BY created_at DESC LIMIT 4;
