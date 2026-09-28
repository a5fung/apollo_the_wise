-- #684 STEP 0 follow-up — three alarms from gate_out.txt, investigated BEFORE any outcome is computed.
--  (1) five 2026-05-20 alerts (ALAB ARM DYN GH TATT) have NO scored scan-log row;
--  (2) 44 (ticker, scan_date) pairs carry a PASS tick (filter_reason NULL, tier set) but no live alert row;
--  (3) 2 alerted pairs whose scan-log rows never show a pass tick.
\pset format unaligned
\pset fieldsep '|'
WITH sess AS (
  SELECT trade_date FROM mi_daily_closes GROUP BY trade_date HAVING count(*) >= 500
), last_ok AS (
  SELECT max(s.trade_date) AS d FROM sess s
  WHERE (SELECT count(*) FROM sess s2 WHERE s2.trade_date > s.trade_date) >= 15
), raw AS (
  SELECT l.* FROM mi_ep_scan_log l
  WHERE l.scan_date BETWEEN DATE '2026-05-01' AND (SELECT d FROM last_ok) AND l.ep_score IS NOT NULL
), ticks AS (
  SELECT ticker, scan_date, count(*) AS n_ticks,
         bool_or(filter_reason IS NULL AND score_tier IS NOT NULL) AS any_pass_tick,
         max(ep_score) AS max_score,
         max(score_tier) FILTER (WHERE filter_reason IS NULL) AS pass_tier,
         min(scan_time_et) FILTER (WHERE filter_reason IS NULL) AS first_pass_time,
         string_agg(DISTINCT left(COALESCE(filter_reason,'pass'),34), ';') AS reasons
  FROM raw GROUP BY ticker, scan_date
), live_alert AS (
  SELECT DISTINCT ON (ticker, alert_date) ticker, alert_date FROM mi_ep_alerts
  WHERE COALESCE(source,'live')='live' ORDER BY ticker, alert_date
), any_alert AS (
  SELECT ticker, alert_date, string_agg(DISTINCT COALESCE(source,'live'), ';') AS sources, count(*) AS n
  FROM mi_ep_alerts GROUP BY ticker, alert_date
)
SELECT 'a1_0520_scanlog_rows_total' AS k, count(*)::text AS v FROM mi_ep_scan_log WHERE scan_date = DATE '2026-05-20'
UNION ALL SELECT 'a1_0520_scanlog_rows_scored', count(ep_score)::text FROM mi_ep_scan_log WHERE scan_date = DATE '2026-05-20'
UNION ALL SELECT 'a1_0520_scanlog_prefix_'||COALESCE(left(filter_reason,26),'pass'), count(*)::text FROM mi_ep_scan_log WHERE scan_date = DATE '2026-05-20' GROUP BY left(filter_reason,26)
UNION ALL SELECT 'a1_0520_live_alerts', string_agg(ticker||'/'||COALESCE(score_tier,'?')||'/'||COALESCE(ep_score::text,'?')||'/'||to_char(COALESCE(detected_at, created_at) AT TIME ZONE 'America/New_York','HH24:MI'), ' ') FROM mi_ep_alerts WHERE alert_date = DATE '2026-05-20' AND COALESCE(source,'live')='live'
UNION ALL SELECT 'a1_scanlog_rows_by_date_0518_0522_'||scan_date::text, count(*)::text||' scored='||count(ep_score)::text FROM mi_ep_scan_log WHERE scan_date BETWEEN DATE '2026-05-18' AND DATE '2026-05-22' GROUP BY scan_date
UNION ALL SELECT 'a1_dates_with_live_alert_but_zero_scored_scanlog_rows', string_agg(DISTINCT a.alert_date::text, ' ') FROM live_alert a WHERE a.alert_date BETWEEN DATE '2026-05-01' AND (SELECT d FROM last_ok) AND NOT EXISTS (SELECT 1 FROM raw r WHERE r.scan_date = a.alert_date)
UNION ALL SELECT 'a2_pass_no_live_alert_'||t.ticker||'_'||t.scan_date::text, 'tier='||COALESCE(t.pass_tier,'?')||' max_score='||t.max_score::text||' n_ticks='||t.n_ticks::text||' first_pass='||to_char(t.first_pass_time AT TIME ZONE 'America/New_York','HH24:MI')||' any_alert_sources='||COALESCE(aa.sources,'NONE')||' reasons='||t.reasons
  FROM ticks t LEFT JOIN any_alert aa ON aa.ticker=t.ticker AND aa.alert_date=t.scan_date
  WHERE t.any_pass_tick AND NOT EXISTS (SELECT 1 FROM live_alert la WHERE la.ticker=t.ticker AND la.alert_date=t.scan_date)
UNION ALL SELECT 'a3_alert_no_pass_tick_'||t.ticker||'_'||t.scan_date::text, 'max_score='||t.max_score::text||' n_ticks='||t.n_ticks::text||' reasons='||t.reasons||' alert='||(SELECT COALESCE(score_tier,'?')||'/'||COALESCE(ep_score::text,'?')||'/'||COALESCE(source,'live')||'/'||to_char(COALESCE(detected_at, created_at) AT TIME ZONE 'America/New_York','HH24:MI') FROM mi_ep_alerts a WHERE a.ticker=t.ticker AND a.alert_date=t.scan_date AND COALESCE(source,'live')='live' ORDER BY created_at LIMIT 1)
  FROM ticks t WHERE NOT t.any_pass_tick AND EXISTS (SELECT 1 FROM live_alert la WHERE la.ticker=t.ticker AND la.alert_date=t.scan_date)
ORDER BY 1;
