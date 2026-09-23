-- Alert-volume collapse (2026-08-24) — ONE read-only prod capture. Never re-run to re-read.
-- Run: ssh apollo@87.99.134.162 "docker exec -i apollo-postgres psql -U apollo -d apollo -A -F '|~|' -P pager=off" \
--        < scripts/probes/_alertdrop_capture.sql > scripts/probes/_alertdrop_capture_out.psv
-- READ-ONLY: every statement is a SELECT.

\echo ===Q1_SCANLOG_DEDUPED===
SELECT DISTINCT ON (scan_date, ticker)
       scan_date, ticker, gap_pct, prev_close, rel_volume, ep_score, score_tier,
       catalyst_quality, adv, adv_source, pm_rvol, rank_by_gap, projected_vol_multiple,
       minutes_since_open, price_source, gap_pct_rt, gap_pct_delayed,
       replace(coalesce(filter_reason,'<none>'), '|~|', '/') AS filter_reason
FROM mi_ep_scan_log
WHERE scan_date BETWEEN '2026-07-06' AND '2026-08-24'
ORDER BY scan_date, ticker, scan_time_et DESC NULLS LAST, id DESC;

\echo ===Q2_SCAN_HEALTH===
SELECT scan_date,
       count(*) AS rows_all,
       count(DISTINCT ticker) AS tickers,
       count(DISTINCT scan_time_et) AS ticks,
       to_char(min(scan_time_et) AT TIME ZONE 'America/New_York','HH24:MI') AS first_tick_et,
       to_char(max(scan_time_et) AT TIME ZONE 'America/New_York','HH24:MI') AS last_tick_et,
       min(minutes_since_open) AS min_mso,
       max(minutes_since_open) AS max_mso,
       count(*) FILTER (WHERE scan_time_et IS NULL) AS null_tick,
       string_agg(DISTINCT coalesce(price_source,'<null>'), ',') AS price_sources
FROM mi_ep_scan_log
WHERE scan_date BETWEEN '2026-07-06' AND '2026-08-24'
GROUP BY scan_date ORDER BY scan_date;

\echo ===Q3_ALERTS===
SELECT alert_date, ticker, ep_score, score_tier, gap_pct, catalyst_quality,
       coalesce(source,'live') AS src,
       to_char(created_at AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI') AS created_et
FROM mi_ep_alerts
WHERE alert_date BETWEEN '2026-07-06' AND '2026-08-24'
ORDER BY alert_date, created_at, ticker;

\echo ===Q4_REGIME===
SELECT regime_date, regime, ep_threshold, vix, qqq_ema_bullish,
       breadth_pct_above_40ma, spy_vs_50ma
FROM mi_market_regime WHERE regime_date >= '2026-07-01' ORDER BY regime_date;

\echo ===Q5_TAPE_BREADTH===
WITH b AS (
  SELECT ticker, trade_date, open_price, close, volume,
         lag(close)  OVER (PARTITION BY ticker ORDER BY trade_date) AS prev_close,
         lag(volume) OVER (PARTITION BY ticker ORDER BY trade_date) AS prev_volume
  FROM mi_daily_closes WHERE trade_date >= '2026-06-25'
)
SELECT trade_date,
       count(*) AS universe_rows,
       count(*) FILTER (WHERE open_price IS NOT NULL) AS rows_with_open,
       count(*) FILTER (WHERE prev_close >= 5 AND prev_volume >= 50000
                          AND open_price IS NOT NULL
                          AND (open_price - prev_close)/prev_close*100 >= 9) AS gap9,
       count(*) FILTER (WHERE prev_close >= 5 AND prev_volume >= 50000
                          AND open_price IS NOT NULL
                          AND (open_price - prev_close)/prev_close*100 >= 10) AS gap10,
       count(*) FILTER (WHERE prev_close >= 5 AND prev_volume >= 50000
                          AND open_price IS NOT NULL
                          AND (open_price - prev_close)/prev_close*100 >= 15) AS gap15,
       count(*) FILTER (WHERE prev_close >= 5 AND prev_volume >= 50000
                          AND open_price IS NOT NULL
                          AND (open_price - prev_close)/prev_close*100 >= 9
                          AND prev_close * prev_volume >= 20000000) AS gap9_liquid,
       count(*) FILTER (WHERE prev_close >= 5 AND prev_volume >= 50000
                          AND (close - prev_close)/prev_close*100 >= 9) AS c2c_gap9
FROM b WHERE trade_date >= '2026-07-06' GROUP BY trade_date ORDER BY trade_date;

\echo ===Q6_TIER_SHADOW_DAILY===
SELECT scan_date, count(*) AS rows_all,
       count(DISTINCT ticker) AS tickers,
       string_agg(DISTINCT coalesce(live_side,'<null>'), ',') AS live_sides,
       count(*) FILTER (WHERE live_quality_last='game_changing') AS q_gc,
       count(*) FILTER (WHERE live_quality_last='strong')        AS q_strong,
       count(*) FILTER (WHERE live_quality_last='moderate')      AS q_moderate,
       count(*) FILTER (WHERE live_quality_last='weak')          AS q_weak,
       count(*) FILTER (WHERE live_quality_last='routine')       AS q_routine,
       count(*) FILTER (WHERE live_quality_last IS NULL)         AS q_null,
       count(*) FILTER (WHERE shadow_tier_last='game_changing')  AS s_gc,
       count(*) FILTER (WHERE shadow_tier_last='strong')         AS s_strong,
       count(*) FILTER (WHERE shadow_tier_last='routine')        AS s_routine
FROM mi_catalyst_tier_shadow
WHERE scan_date BETWEEN '2026-07-06' AND '2026-08-24'
GROUP BY scan_date ORDER BY scan_date;

\echo ===Q7_SAFEGUARD_STATE===
SELECT safeguard, account_mode, state,
       to_char(last_transition_at AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI') AS last_transition_et,
       to_char(updated_at AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI') AS updated_et
FROM mi_safeguard_state ORDER BY safeguard, account_mode;

\echo ===Q8_AUDIT_DAILY===
SELECT (created_at AT TIME ZONE 'America/New_York')::date AS d, event_type, count(*) AS n
FROM mi_audit_log
WHERE created_at >= '2026-07-06'
GROUP BY 1,2 HAVING count(*) > 0 ORDER BY 2,1;

\echo ===Q9_SCANLOG_TABLE_MINMAX===
SELECT min(scan_date) AS min_d, max(scan_date) AS max_d, count(*) AS n FROM mi_ep_scan_log;

\echo ===Q10_ALERT_DAILY_TIER===
SELECT alert_date, score_tier, coalesce(source,'live') AS src, count(*) AS n
FROM mi_ep_alerts WHERE alert_date >= '2026-06-01'
GROUP BY 1,2,3 ORDER BY 1,2,3;

\echo ===Q11_TRADES===
SELECT alert_date, ticker, account_mode, status,
       replace(coalesce(skip_reason,'<none>'),'|~|','/') AS skip_reason
FROM mi_live_trades WHERE alert_date >= '2026-07-06' ORDER BY alert_date, ticker;

\echo ===Q12_SCANLOG_TICKS_BY_HOUR===
SELECT scan_date,
       to_char(scan_time_et AT TIME ZONE 'America/New_York','HH24:MI') AS tick_et,
       count(DISTINCT ticker) AS tickers
FROM mi_ep_scan_log
WHERE scan_date BETWEEN '2026-08-03' AND '2026-08-24'
GROUP BY 1,2 ORDER BY 1,2;
