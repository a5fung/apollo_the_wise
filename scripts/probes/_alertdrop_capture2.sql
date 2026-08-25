-- Alert-volume collapse — capture 2 (READ-ONLY): per-TICK scan rows. The deduped
-- last state hides the funnel (an alerted ticker's LAST row is "already scored earlier
-- today"), so the furthest-stage-reached funnel needs every tick.
\echo ===R1_SCANLOG_TICKS===
SELECT scan_date, ticker,
       to_char(scan_time_et AT TIME ZONE 'America/New_York','HH24:MI') AS tick_et,
       minutes_since_open, gap_pct, prev_close, rel_volume, adv, adv_source,
       ep_score, score_tier, catalyst_quality, rank_by_gap, pm_rvol,
       replace(coalesce(filter_reason,'<none>'),'|~|','/') AS filter_reason
FROM mi_ep_scan_log
WHERE scan_date BETWEEN '2026-07-06' AND '2026-08-24'
ORDER BY scan_date, ticker, scan_time_et, id;
