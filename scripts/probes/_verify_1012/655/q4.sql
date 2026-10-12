\echo == rule B rows per night: count, and min/max/null prior_members (detail json)
select (created_at at time zone 'America/New_York')::date d, count(*) n,
  count(*) filter (where (detail::jsonb->>'prior_members') is null) null_prior,
  min((detail::jsonb->>'prior_members')::int) min_prior, max((detail::jsonb->>'prior_members')::int) max_prior
from mi_audit_log where event_type='theme_retired_small_fading' and created_at > '2026-10-06' group by 1 order by 1;
\echo == detail sample
select left(detail,300) from mi_audit_log where event_type='theme_retired_small_fading' order by id desc limit 2;
