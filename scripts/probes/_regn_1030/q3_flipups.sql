SET default_transaction_read_only = on;
-- names admitted on the real-time flip-up (the opening gap under the floor, the live gap over it) since #490 went on, and what happened to their HIGH alerts
WITH f AS (
  SELECT DISTINCT (created_at AT TIME ZONE 'America/New_York')::date AS d, substring(summary from '^([A-Z.]{1,6}) ') AS t
  FROM mi_audit_log WHERE event_type = 'ep_rt_floor_flip_up' AND created_at >= '2026-08-02'
)
SELECT count(*) AS flip_ups,
       count(a.ticker) AS became_high,
       count(lt.id) FILTER (WHERE lt.skip_reason ILIKE 'setup:chase_cap%') AS chase_cap_skips,
       count(lt.id) FILTER (WHERE lt.status IN ('filled','closed','partial')) AS filled
FROM f
LEFT JOIN (SELECT DISTINCT ticker, alert_date FROM mi_ep_alerts WHERE score_tier='HIGH') a ON a.ticker = f.t AND a.alert_date = f.d
LEFT JOIN mi_live_trades lt ON lt.ticker = f.t AND lt.alert_date = f.d AND lt.signal_type='magna53';
SELECT count(*) AS all_chase_cap_skips_since_0723 FROM mi_live_trades WHERE skip_reason ILIKE 'setup:chase_cap%';
