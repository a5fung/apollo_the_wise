\echo == latest theme_date and board size by size band (non-Retired, latest snapshot)
with latest as (select max(theme_date) d from mi_themes where stage <> 'Retired')
select (select d from latest) as latest_date,
  count(*) filter (where stage<>'Retired') as active,
  count(*) filter (where stage<>'Retired' and coalesce(array_length(tickers,1),0) between 2 and 3) as small_2_3,
  count(*) filter (where stage<>'Retired' and coalesce(array_length(tickers,1),0) >= 4) as homes_4plus,
  count(*) filter (where stage<>'Retired' and coalesce(array_length(tickers,1),0) < 2) as under2
from mi_themes where theme_date=(select d from latest);
\echo == small (2-3 member) active themes on latest snapshot
select name, stage, array_length(tickers,1) n, rs_avg, source from mi_themes where theme_date=(select max(theme_date) from mi_themes where stage<>'Retired') and stage<>'Retired' and array_length(tickers,1) between 2 and 3 order by name;
\echo == three named churners: recent rows
select theme_date, name, stage, array_length(tickers,1) n from mi_themes where name in ('Appalachian Natural Gas Producers','Offshore Drilling Rig Contractors','Regulated Natural Gas Distribution Utilities') order by name, theme_date desc limit 30;
\echo == 10-09 cap rows
select created_at at time zone 'America/New_York' t, event_type, left(summary,300) from mi_audit_log where event_type like 'theme_sector_cap%' and created_at > '2026-10-08' order by id;
\echo == fold/kept/error events ever
select event_type, count(*), min(created_at at time zone 'America/New_York') first_et, max(created_at at time zone 'America/New_York') last_et from mi_audit_log where event_type in ('theme_small_folded','theme_small_fold_ran','theme_small_fold_error','theme_sector_cap_kept_distinct') group by 1;
