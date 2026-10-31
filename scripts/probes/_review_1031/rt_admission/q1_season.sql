SET default_transaction_read_only = on;
\echo == (A) raw real-time events per day (same filter as the 10-10 EVCOUNT), 10-12..10-30
SELECT (created_at AT TIME ZONE 'America/New_York')::date AS d, count(*) AS raw_events,
       count(DISTINCT detail::json->>'ticker') AS tickers,
       count(*) FILTER (WHERE event_type = 'ep_rt_admit') AS admits,
       count(*) FILTER (WHERE event_type = 'ep_rt_floor_flip_up') AS flips,
       count(*) FILTER (WHERE event_type = 'ep_rt_universe_catch') AS catches
FROM mi_audit_log
WHERE event_type LIKE 'ep_rt_%' AND event_type <> 'ep_rt_universe_coverage'
  AND (created_at AT TIME ZONE 'America/New_York')::date BETWEEN '2026-10-12' AND '2026-10-30'
GROUP BY 1 ORDER BY 1;
\echo == (B) the 09:45 budget: alerts by detection time, and the real-time first read before each (ticker-day)
WITH rt AS (
  SELECT (created_at AT TIME ZONE 'America/New_York')::date AS d, detail::json->>'ticker' AS ticker,
         min(created_at AT TIME ZONE 'America/New_York')::time AS first_rt
  FROM mi_audit_log WHERE event_type LIKE 'ep_rt_%' AND event_type <> 'ep_rt_universe_coverage'
    AND (created_at AT TIME ZONE 'America/New_York')::date BETWEEN '2026-10-12' AND '2026-10-30' GROUP BY 1, 2)
SELECT a.alert_date, a.ticker, a.score_tier, to_char(a.detected_at AT TIME ZONE 'America/New_York', 'HH24:MI:SS') AS detected_et,
       to_char(rt.first_rt, 'HH24:MI:SS') AS first_rt_et,
       round(extract(epoch FROM ((a.detected_at AT TIME ZONE 'America/New_York')::time - rt.first_rt))::numeric / 60, 1) AS rt_to_alert_min
FROM mi_ep_alerts a LEFT JOIN rt ON rt.d = a.alert_date AND rt.ticker = a.ticker
WHERE a.alert_date BETWEEN '2026-10-12' AND '2026-10-30' ORDER BY a.alert_date, a.detected_at;
\echo == (C) slots: every live/paper MAGNA53 row 10-12..10-30 with its fate
SELECT alert_date, ticker, account_mode, status, coalesce(skip_reason, '') AS skip_reason,
       to_char(filled_at AT TIME ZONE 'America/New_York', 'HH24:MI') AS filled_et
FROM mi_live_trades WHERE signal_type = 'magna53' AND alert_date BETWEEN '2026-10-12' AND '2026-10-30' ORDER BY alert_date, account_mode, ticker;
\echo == (D) the comparison windows' raw daily average (the 10-10 baselines): 09-08..10-09 and 07-21..08-10
SELECT CASE WHEN d BETWEEN '2026-09-08' AND '2026-10-09' THEN 'quiet_0908_1009' ELSE 'busy_0721_0810' END AS w, round(avg(n), 1) AS raw_per_day, count(*) AS days
FROM (SELECT (created_at AT TIME ZONE 'America/New_York')::date AS d, count(*) AS n FROM mi_audit_log
      WHERE event_type LIKE 'ep_rt_%' AND event_type <> 'ep_rt_universe_coverage'
        AND ((created_at AT TIME ZONE 'America/New_York')::date BETWEEN '2026-09-08' AND '2026-10-09'
          OR (created_at AT TIME ZONE 'America/New_York')::date BETWEEN '2026-07-21' AND '2026-08-10') GROUP BY 1) x GROUP BY 1;
