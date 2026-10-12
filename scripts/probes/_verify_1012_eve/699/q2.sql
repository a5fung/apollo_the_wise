\echo == A. stop_update_retry_succeeded by day + mode (last 14d)
select (a.created_at at time zone 'America/New_York')::date d, t.account_mode, count(*) n, string_agg(distinct (a.detail::json->>'ticker'), ',') tickers
from mi_audit_log a left join mi_live_trades t on t.id = (a.detail::json->>'trade_id')::int
where a.event_type='stop_update_retry_succeeded' and a.created_at >= now()-interval '14 days'
group by 1,2 order by 1,2;
\echo == B. digests that ever carried BOOK
select count(*) as digests_with_book, min(created_at at time zone 'America/New_York') first_et, max(created_at at time zone 'America/New_York') last_et
from mi_audit_log where event_type='market_close_digest_sent' and detail like '%BOOK%';
\echo == C. earliest and total digests
select count(*), min(created_at at time zone 'America/New_York')::date from mi_audit_log where event_type='market_close_digest_sent';
