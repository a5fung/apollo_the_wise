SET default_transaction_read_only = on;
\echo == scan log rows for FTAI in the last 3 days (latest first)
SELECT scan_date, (scan_time_et AT TIME ZONE 'America/New_York')::time(0) AS t, ep_score, score_tier, catalyst_quality, llm_catalyst_quality, gap_pct, filter_reason
FROM mi_ep_scan_log WHERE ticker = 'FTAI' AND scan_date >= DATE '2026-10-27' ORDER BY scan_time_et DESC LIMIT 12;
\echo == the breakdown of the best-scoring row
SELECT scan_date, (scan_time_et AT TIME ZONE 'America/New_York')::time(0) AS t, ep_score, jsonb_pretty(score_breakdown)
FROM mi_ep_scan_log WHERE ticker = 'FTAI' AND scan_date >= DATE '2026-10-27' ORDER BY ep_score DESC NULLS LAST, scan_time_et DESC LIMIT 1;
\echo == the alert row, if any
SELECT alert_date, ep_score, score_tier, catalyst_quality, gap_pct, left(coalesce(judge_rationale,''),400) FROM mi_ep_alerts WHERE ticker = 'FTAI' AND alert_date >= DATE '2026-10-27';
