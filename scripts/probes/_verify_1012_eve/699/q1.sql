\echo == A. stop-update retry audit rows today (16:30-17:15 ET)
select created_at at time zone 'America/New_York' as et, event_type, summary, left(detail,400) as detail
from mi_audit_log
where created_at >= timestamptz '2026-10-12 16:30:00-04' and created_at < timestamptz '2026-10-12 17:15:00-04'
and (event_type like 'stop_update%' or event_type like 'stop_order%' or event_type like 'telegram%' or event_type like 'market_close_digest%' or event_type like '%retry%' or event_type like 'live_position%')
order by created_at;
\echo == B. trades 404 / 414 / 419 mode + status
select id, ticker, account_mode, status, stop_price, entry_price, remaining_shares from mi_live_trades where id in (404,414,419) order by id;
\echo == C. ANY telegram_* audit rows since deploy 10-11 21:50 ET
select event_type, count(*), min(created_at at time zone 'America/New_York') first_et, max(created_at at time zone 'America/New_York') last_et
from mi_audit_log where created_at >= timestamptz '2026-10-11 21:50:00-04' and event_type ilike 'telegram%' group by 1;
\echo == D. market_close_digest_sent per day, last 21 days
select (created_at at time zone 'America/New_York')::date d, count(*), max(detail) from mi_audit_log
where event_type='market_close_digest_sent' and created_at >= now()-interval '21 days' group by 1 order by 1;
\echo == E. live_position_update audit_wrap rows last 10 days (which job rows exist)
select (created_at at time zone 'America/New_York')::date d, event_type, count(*) from mi_audit_log
where created_at >= now()-interval '10 days' and (event_type ilike '%live_position%' or event_type ilike 'job_%close_digest%' or summary ilike '%close_digest%') group by 1,2 order by 1,2;
