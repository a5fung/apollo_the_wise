-- Silent-days verification (2026-08-25) — ONE read-only prod capture. Never re-run to re-read.
-- Run: ssh apollo@87.99.134.162 "docker exec -i apollo-postgres psql -U apollo -d apollo -A -F '|~|' -P pager=off" \
--        < scripts/probes/_silentdays_capture.sql > scripts/probes/_silentdays_capture_out.txt
-- READ-ONLY: every statement is a SELECT. Free-text columns are emitted via row_to_json so
-- embedded newlines/pipes cannot shred the delimiter (advisor 2026-08-25).

\echo ===Q1_ALL_TICKS_2DAY===
SELECT scan_date, ticker,
       to_char(scan_time_et AT TIME ZONE 'America/New_York','HH24:MI:SS') AS tick_et,
       gap_pct, gap_pct_rt, gap_pct_delayed, prev_close, prev_close_alpaca, rel_volume,
       ep_score, score_tier, catalyst_quality, adv, adv_source, pm_rvol, rank_by_gap,
       projected_vol_multiple, minutes_since_open, price_source, rt_price_age_s,
       replace(coalesce(filter_reason,'<none>'), '|~|', '/') AS filter_reason
FROM mi_ep_scan_log
WHERE scan_date IN ('2026-08-24','2026-08-25')
ORDER BY scan_date, ticker, scan_time_et NULLS FIRST, id;

\echo ===Q2_LAST_STATE_2DAY===
SELECT DISTINCT ON (scan_date, ticker)
       scan_date, ticker,
       to_char(scan_time_et AT TIME ZONE 'America/New_York','HH24:MI') AS last_tick_et,
       gap_pct, prev_close, rel_volume, ep_score, score_tier, catalyst_quality, adv,
       adv_source, pm_rvol, rank_by_gap, projected_vol_multiple, minutes_since_open,
       price_source,
       replace(coalesce(filter_reason,'<none>'), '|~|', '/') AS filter_reason
FROM mi_ep_scan_log
WHERE scan_date IN ('2026-08-24','2026-08-25')
ORDER BY scan_date, ticker, scan_time_et DESC NULLS LAST, id DESC;

\echo ===Q3_SCAN_HEALTH===
SELECT scan_date, count(*) rows_all, count(DISTINCT ticker) tickers,
       count(DISTINCT scan_time_et) ticks,
       to_char(min(scan_time_et) AT TIME ZONE 'America/New_York','HH24:MI') first_tick,
       to_char(max(scan_time_et) AT TIME ZONE 'America/New_York','HH24:MI') last_tick,
       count(*) FILTER (WHERE scan_time_et IS NULL) null_tick
FROM mi_ep_scan_log WHERE scan_date BETWEEN '2026-08-17' AND '2026-08-25'
GROUP BY scan_date ORDER BY scan_date;

\echo ===Q4_ALERTS_RECENT===
SELECT alert_date, ticker, gap_pct, ep_score, score_tier, catalyst_quality, catalyst_type,
       coalesce(source,'live') AS src, fire_status, materiality_tier, setup_class,
       to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI') AS created_et
FROM mi_ep_alerts WHERE alert_date BETWEEN '2026-08-11' AND '2026-08-25'
ORDER BY alert_date, ticker;

\echo ===Q5_PRIOR_ALERTS_COOLDOWN===
-- every prior EP alert in the last 200 days for any ticker that appears in the 2-day scan log
SELECT a.ticker, a.alert_date, a.score_tier, a.ep_score, a.gap_pct, a.catalyst_quality,
       coalesce(a.source,'live') AS src,
       (DATE '2026-08-25' - a.alert_date) AS days_ago
FROM mi_ep_alerts a
WHERE a.alert_date >= '2026-02-01'
  AND a.ticker IN (SELECT DISTINCT ticker FROM mi_ep_scan_log
                   WHERE scan_date IN ('2026-08-24','2026-08-25'))
ORDER BY a.ticker, a.alert_date;

\echo ===Q6_CATALYST_SHADOW_JSON===
SELECT row_to_json(t) FROM (
  SELECT * FROM mi_catalyst_tier_shadow
  WHERE scan_date BETWEEN '2026-08-20' AND '2026-08-25'
  ORDER BY scan_date, ticker) t;

\echo ===Q7_AUDIT_JSON===
SELECT row_to_json(t) FROM (
  SELECT id, to_char(created_at AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI:SS') AS et,
         event_type, summary, detail
  FROM mi_audit_log
  WHERE (created_at AT TIME ZONE 'America/New_York')::date IN ('2026-08-24','2026-08-25')
  ORDER BY created_at, id) t;

\echo ===Q8_AUDIT_TYPE_COUNTS===
SELECT (created_at AT TIME ZONE 'America/New_York')::date AS et_date, event_type, count(*)
FROM mi_audit_log
WHERE (created_at AT TIME ZONE 'America/New_York')::date BETWEEN '2026-08-19' AND '2026-08-25'
GROUP BY 1,2 ORDER BY 1,3 DESC;

\echo ===Q9_DAILY_CLOSES===
-- 60 sessions of OHLCV for every ticker seen in the 2-day scan log (re-derive ADV$/ATR%/vol
-- ourselves; do NOT trust the numbers baked into the reason string) + forward bars as they accrue
SELECT trade_date, ticker, open_price, high_price, low_price, close, volume
FROM mi_daily_closes
WHERE ticker IN (SELECT DISTINCT ticker FROM mi_ep_scan_log
                 WHERE scan_date IN ('2026-08-24','2026-08-25'))
  AND trade_date >= '2026-06-01'
ORDER BY ticker, trade_date;

\echo ===Q10_MISSED_OUTCOMES===
SELECT ticker, alert_date, source, skip_category, ep_score, gap_pct, catalyst_quality,
       open_d0, close_d0, ret_1d, ret_5d, ret_20d, max_high_5d, max_high_20d,
       to_char(last_refreshed_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI') AS refreshed_et,
       replace(coalesce(skip_reason,'<none>'), '|~|', '/') AS skip_reason
FROM mi_ep_missed_outcomes WHERE alert_date BETWEEN '2026-08-18' AND '2026-08-25'
ORDER BY alert_date, ticker;

\echo ===Q11_SCAN_OUTCOMES===
SELECT ticker, scan_date, baseline_close, fwd_5d_pct, fwd_10d_pct, n_sessions_5d, n_sessions_10d,
       to_char(computed_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI') AS computed_et
FROM mi_ep_scan_outcomes WHERE scan_date BETWEEN '2026-08-18' AND '2026-08-25'
ORDER BY scan_date, ticker;

\echo ===Q12_GROUND_TRUTH===
SELECT ticker, event_date, kind, verdict, operator_grade, system_tier, root_cause, source
FROM mi_ep_ground_truth ORDER BY event_date DESC LIMIT 60;

\echo ===Q13_SHORTLIST_SHADOW===
SELECT * FROM mi_ep_shortlist_shadow WHERE scan_date BETWEEN '2026-08-22' AND '2026-08-25'
ORDER BY scan_date, ticker LIMIT 200;

\echo ===Q14_SCORE_SHADOW===
SELECT * FROM mi_ep_score_shadow WHERE scan_date BETWEEN '2026-08-22' AND '2026-08-25'
ORDER BY scan_date, ticker LIMIT 200;

\echo ===Q15_TOGGLES===
SELECT * FROM mi_safeguard_state ORDER BY 1 LIMIT 200;
