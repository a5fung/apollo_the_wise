-- #490 sustain-rule COST (2026-08-24) — ONE read-only prod capture. Never re-run to re-read.
-- Run: ssh apollo@87.99.134.162 "docker exec -i apollo-postgres psql -U apollo -d apollo -A -F '|~|' -P pager=off" \
--        < scripts/probes/_sustain_cost_capture.sql > scripts/probes/_sustain_cost_capture_out.psv
-- READ-ONLY: every statement is a SELECT. No writes, no temp tables, no mutation.

\echo ===Q1_TOGGLES===
SELECT safeguard, account_mode, state,
       to_char(last_transition_at AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI') AS transition_et,
       to_char(updated_at AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI') AS updated_et
FROM mi_safeguard_state
WHERE safeguard LIKE 'ep_rt%' OR safeguard LIKE '%sustain%' OR safeguard LIKE '%authorit%'
ORDER BY safeguard, account_mode;

\echo ===Q2_SUSTAIN_REJECT===
SELECT (created_at AT TIME ZONE 'America/New_York')::date          AS d_et,
       to_char(created_at AT TIME ZONE 'America/New_York','HH24:MI:SS') AS t_et,
       detail::jsonb->>'ticker'        AS ticker,
       detail::jsonb->>'rt_gap'        AS rt_gap,
       detail::jsonb->>'bars_required' AS bars_required,
       detail::jsonb->>'reason'        AS reason,
       replace(detail, '|~|', '/')     AS detail_json
FROM mi_audit_log
WHERE event_type = 'ep_rt_sustain_reject'
ORDER BY created_at;

\echo ===Q3_SUSTAIN_UNDECIDABLE===
SELECT (created_at AT TIME ZONE 'America/New_York')::date          AS d_et,
       to_char(created_at AT TIME ZONE 'America/New_York','HH24:MI:SS') AS t_et,
       detail::jsonb->>'ticker' AS ticker,
       detail::jsonb->>'rt_gap' AS rt_gap,
       detail::jsonb->>'reason' AS reason
FROM mi_audit_log
WHERE event_type = 'ep_rt_sustain_undecidable'
ORDER BY created_at;

\echo ===Q4_UNIVERSE_CATCH===
SELECT (created_at AT TIME ZONE 'America/New_York')::date          AS d_et,
       to_char(created_at AT TIME ZONE 'America/New_York','HH24:MI:SS') AS t_et,
       detail::jsonb->>'ticker'        AS ticker,
       detail::jsonb->>'rt_gap'        AS rt_gap,
       detail::jsonb->>'delayed_gap'   AS delayed_gap,
       detail::jsonb->>'authoritative' AS authoritative,
       detail::jsonb->>'basis'         AS basis
FROM mi_audit_log
WHERE event_type = 'ep_rt_universe_catch'
ORDER BY created_at;

\echo ===Q5_ALERTS===
SELECT alert_date, ticker, ep_score, score_tier, gap_pct, catalyst_quality,
       coalesce(source,'live') AS src,
       to_char(created_at AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI') AS created_et
FROM mi_ep_alerts
WHERE alert_date BETWEEN '2026-08-01' AND '2026-08-24'
ORDER BY alert_date, ticker, created_at;

\echo ===Q6_SCANLOG_DEDUPED===
SELECT DISTINCT ON (scan_date, ticker)
       scan_date, ticker, gap_pct, prev_close, rel_volume, ep_score, score_tier,
       catalyst_quality, adv, pm_rvol, rank_by_gap, price_source,
       gap_pct_rt, gap_pct_delayed,
       replace(coalesce(filter_reason,'<none>'), '|~|', '/') AS filter_reason
FROM mi_ep_scan_log
WHERE scan_date BETWEEN '2026-08-01' AND '2026-08-24'
ORDER BY scan_date, ticker, scan_time_et DESC NULLS LAST, id DESC;

\echo ===Q7_DAILY_CLOSES===
WITH universe AS (
  SELECT DISTINCT detail::jsonb->>'ticker' AS ticker
  FROM mi_audit_log
  WHERE event_type IN ('ep_rt_sustain_reject','ep_rt_sustain_undecidable','ep_rt_universe_catch')
    AND detail::jsonb->>'ticker' IS NOT NULL
)
SELECT c.trade_date, c.ticker, c.open_price, c.high_price, c.low_price, c.close, c.volume
FROM mi_daily_closes c
JOIN universe u ON u.ticker = c.ticker
WHERE c.trade_date BETWEEN '2026-06-20' AND '2026-08-24'
ORDER BY c.ticker, c.trade_date;

\echo ===Q8_MISSED_OUTCOMES===
SELECT alert_date, ticker, source, skip_category,
       replace(coalesce(skip_reason,''), '|~|', '/') AS skip_reason,
       ep_score, gap_pct, catalyst_quality,
       open_d0, close_d0, ret_1d, ret_5d, ret_20d, max_high_5d, max_high_20d,
       to_char(last_refreshed_at AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI:SS') AS refreshed_et
FROM mi_ep_missed_outcomes
WHERE alert_date BETWEEN '2026-08-01' AND '2026-08-24'
ORDER BY alert_date, ticker;

\echo ===Q9_NOW===
SELECT to_char(now() AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI:SS') AS now_et;
