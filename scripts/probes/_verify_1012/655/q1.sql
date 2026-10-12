\echo == safeguard theme rows
select safeguard, account_mode, state, updated_at at time zone 'America/New_York' as upd_et from mi_safeguard_state where safeguard ilike '%theme%' order by safeguard;
\echo == theme-ish audit events by ET date, since 10-05
select (created_at at time zone 'America/New_York')::date as d, event_type, count(*) from mi_audit_log
 where created_at > '2026-10-05' and (event_type ilike '%theme_small%' or event_type ilike '%cap_kept%' or event_type ilike '%correctness%' or event_type ilike '%retired_small%' or event_type ilike '%theme_birth_gate%' or event_type ilike '%sector_cap%')
 group by 1,2 order by 1,2;
\echo == latest theme_correctness_check rows
select id, created_at at time zone 'America/New_York' as t_et, left(summary,400) as s from mi_audit_log where event_type='theme_correctness_check' order by id desc limit 8;
\echo == most recent theme engine run markers (any theme event) last 40h
select created_at at time zone 'America/New_York' as t_et, event_type, left(summary,160) from mi_audit_log where created_at > now() - interval '40 hours' and event_type ilike '%theme%' order by id desc limit 60;
