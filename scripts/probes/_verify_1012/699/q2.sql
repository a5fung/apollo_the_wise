\echo == audit telegram rows since 2026-10-11 21:50 ET (deploy)
select event_type, count(*), min(created_at at time zone 'America/New_York') first_et, max(created_at at time zone 'America/New_York') last_et
from mi_audit_log
where created_at >= timestamptz '2026-10-11 21:50:00-04' and (event_type ilike 'telegram%' or event_type in ('skip_row_write_error','strategy_mode_resolve_error'))
group by 1 order by 1;
\echo == audit telegram rows last 7d by day
select (created_at at time zone 'America/New_York')::date d, event_type, count(*) from mi_audit_log
where created_at >= now()-interval '7 days' and event_type ilike 'telegram%' group by 1,2 order by 1,2;
\echo == live/paper trades touched today (ET)
select id, ticker, strategy_id, account_mode, status, skip_reason, created_at at time zone 'America/New_York' as created_et
from mi_live_trades where created_at >= timestamptz '2026-10-12 00:00:00-04' order by created_at;
\echo == ep alerts today
select count(*) from mi_ep_alerts where detected_at >= timestamptz '2026-10-12 00:00:00-04';
