SET default_transaction_read_only = on;
\echo == per window, daily average of (a) all ep_rt_ events (b) the four classes the 10-10 re-cut read (c) deduped ticker-days of those classes
WITH e AS (
  SELECT (created_at AT TIME ZONE 'America/New_York')::date AS d, event_type, detail::json->>'ticker' AS ticker
  FROM mi_audit_log WHERE event_type LIKE 'ep_rt_%' AND event_type <> 'ep_rt_universe_coverage'
    AND (created_at AT TIME ZONE 'America/New_York')::date BETWEEN '2026-07-21' AND '2026-10-30'),
w AS (SELECT *, CASE WHEN d BETWEEN '2026-07-21' AND '2026-08-10' THEN '1_busy_0721_0810'
                      WHEN d BETWEEN '2026-09-08' AND '2026-10-09' THEN '2_quiet_0908_1009'
                      WHEN d BETWEEN '2026-10-12' AND '2026-10-30' THEN '3_season_1012_1030' END AS win FROM e)
SELECT win, count(DISTINCT d) AS days,
       round(count(*)::numeric / count(DISTINCT d), 1) AS all_per_day,
       round(count(*) FILTER (WHERE event_type IN ('ep_rt_universe_catch','ep_rt_floor_flip_up','ep_rt_admit','ep_rt_live_miss'))::numeric / count(DISTINCT d), 1) AS four_class_per_day,
       round(count(DISTINCT (d, ticker)) FILTER (WHERE event_type IN ('ep_rt_universe_catch','ep_rt_floor_flip_up','ep_rt_admit','ep_rt_live_miss'))::numeric / count(DISTINCT d), 1) AS tickerdays_per_day
FROM w WHERE win IS NOT NULL GROUP BY win ORDER BY win;
\echo == event types in the season window
SELECT event_type, count(*) FROM mi_audit_log WHERE event_type LIKE 'ep_rt_%' AND (created_at AT TIME ZONE 'America/New_York')::date BETWEEN '2026-10-12' AND '2026-10-30' GROUP BY 1 ORDER BY 2 DESC;
