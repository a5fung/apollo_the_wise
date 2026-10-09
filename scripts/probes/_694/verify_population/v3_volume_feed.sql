-- verify #694 (c): is pre-market volume as-of the tick, and from which feed. Read-only.
\echo '### V3a 2026-10-05 per pre-open tick 09:00-09:25: today_volume, pm_rvol, price_source, rank_by_prescore per ticker'
SELECT ticker, to_char(scan_time_et AT TIME ZONE 'America/New_York','HH24:MI:SS.MS') tick, rank_by_prescore, rank_by_gap,
       today_volume, prev_day_volume, pm_rvol, price_source, current_price, reject_stage
  FROM mi_ep_scan_log
 WHERE scan_date='2026-10-05' AND rank_by_gap IS NOT NULL
   AND (scan_time_et AT TIME ZONE 'America/New_York')::time BETWEEN '08:50' AND '09:29:59'
 ORDER BY ticker, scan_time_et;
\echo '### V3b last-pre-open-tick pool rows since 2026-08-29: today_volume == prev_day_volume (stale yesterday carry?) and minutes_since_open'
WITH pre AS (SELECT * FROM mi_ep_scan_log WHERE scan_date >= '2026-08-29' AND rank_by_gap IS NOT NULL
               AND (scan_time_et AT TIME ZONE 'America/New_York')::time < '09:30'),
lt AS (SELECT scan_date, max(scan_time_et) t FROM pre GROUP BY 1)
SELECT count(*) n, count(*) FILTER (WHERE p.today_volume = p.prev_day_volume) eq_prevday,
       count(*) FILTER (WHERE p.today_volume > p.prev_day_volume) gt_prevday,
       count(*) FILTER (WHERE p.pm_rvol IS NULL) no_pm_rvol,
       count(*) FILTER (WHERE p.rank_by_prescore > 20) beyond_20,
       min(p.minutes_since_open) min_mso, max(p.minutes_since_open) max_mso
  FROM pre p JOIN lt ON lt.scan_date=p.scan_date AND lt.t=p.scan_time_et;
\echo '### V3c rt-volume shadow audit events (delayed vs real-time pre-market volume), if any, 08-01..08-27: ratio rt/delayed'
SELECT count(*) n,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY (details->>'rt_pm_vol')::float / NULLIF((details->>'delayed_vol')::float,0)) med_ratio
  FROM mi_audit_log WHERE event_type='ep_rt_volume_shadow' AND created_at >= '2026-07-27';
\echo '### V3d one sample of that event payload'
SELECT details FROM mi_audit_log WHERE event_type='ep_rt_volume_shadow' ORDER BY created_at DESC LIMIT 2;
