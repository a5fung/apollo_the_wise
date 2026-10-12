\echo == trades touched since 10-11 20:00 ET
select id, ticker, account_mode, status, skip_reason, signal_type, created_at at time zone 'America/New_York' created_et, filled_at at time zone 'America/New_York' filled_et, closed_at at time zone 'America/New_York' closed_et
from mi_live_trades where created_at >= timestamptz '2026-10-11 20:00:00-04' or filled_at >= timestamptz '2026-10-11 20:00:00-04' or closed_at >= timestamptz '2026-10-11 20:00:00-04' order by coalesce(closed_at,filled_at,created_at);
\echo == ep alerts today
select id, ticker, ep_score, score_tier, source, created_at at time zone 'America/New_York' created_et from mi_ep_alerts where created_at >= timestamptz '2026-10-12 00:00:00-04' order by created_at;
\echo == audit rows mentioning paper chat / 699 / stop restore since deploy
select event_type, count(*), max(created_at at time zone 'America/New_York') last_et from mi_audit_log where created_at >= timestamptz '2026-10-11 21:50:00-04' group by 1 order by 3 desc limit 40;
