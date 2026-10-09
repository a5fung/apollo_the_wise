-- #694 POOL: every candidate that reached the shortlist sort (rank_by_gap IS NOT NULL) at each
-- day's LAST pre-open tick (max scan_time_et < 09:30 ET among ranked rows). One row per (day, ticker).
WITH ranked AS (
  SELECT * FROM mi_ep_scan_log
   WHERE scan_date BETWEEN '2026-04-13' AND '2026-10-08'
     AND rank_by_gap IS NOT NULL
     AND (scan_time_et AT TIME ZONE 'America/New_York')::time < '09:30'
), last_tick AS (
  SELECT scan_date, max(scan_time_et) t FROM ranked GROUP BY scan_date
)
SELECT r.scan_date, r.ticker,
       to_char(r.scan_time_et AT TIME ZONE 'America/New_York','HH24:MI:SS') AS tick_et,
       r.rank_by_gap, r.rank_by_prescore, r.gap_pct, r.gap_pct_rt, r.gap_pct_delayed, r.prev_close,
       r.current_price, r.today_volume, r.rel_volume, r.adv, r.adv_source, r.pm_rvol, r.pm_rvol_baseline_n,
       r.in_active_theme, r.price_source, r.reject_stage,
       replace(left(coalesce(r.filter_reason,''),120),'|','/') AS filter_reason,
       r.ep_score, r.score_tier, r.quality_adv_dollar, r.market_cap, r.minutes_since_open
  FROM ranked r JOIN last_tick lt ON lt.scan_date = r.scan_date AND lt.t = r.scan_time_et
 ORDER BY r.scan_date, r.rank_by_gap;
