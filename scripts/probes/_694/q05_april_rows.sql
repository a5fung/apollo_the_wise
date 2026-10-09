-- #694 April 13-30 rows carry no scan_time_et and no rank_by_gap: pull them with created_at to see if a tick can be placed
SELECT scan_date, ticker, to_char(created_at AT TIME ZONE 'America/New_York','HH24:MI:SS.MS') AS created_et,
       gap_pct, prev_close, rel_volume, adv, adv_source, pm_rvol,
       replace(left(coalesce(filter_reason,''),100),'|','/') AS filter_reason, ep_score, score_tier
  FROM mi_ep_scan_log WHERE scan_date BETWEEN '2026-04-13' AND '2026-04-30'
 ORDER BY scan_date, created_at, ticker;
