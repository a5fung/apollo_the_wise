\pset pager off
\echo === Q4-1 NULL-cap gappers stamped quality_filter: the reason text (could a sub-cap name hide here?)
SELECT scan_date, ticker, left(max(filter_reason),110) reason, round(max(gap_pct)::numeric,1) max_gap, round(max(prev_close)::numeric,2) pc, count(*) rows FROM mi_ep_scan_log WHERE scan_date >= '2026-10-12' AND gap_pct >= 10 AND prev_close >= 5 AND market_cap IS NULL AND reject_stage='quality_filter' GROUP BY 1,2 ORDER BY 1,2;
\echo === Q4-2 judge fallback event baseline: per ISO week, 09-14 .. 10-23
SELECT date_trunc('week', created_at AT TIME ZONE 'America/New_York')::date wk, event_type, count(*) FROM mi_audit_log WHERE created_at >= '2026-09-14 04:00+00' AND event_type IN ('judge_verdict_truncated','judge_divergence_check_failed') GROUP BY 1,2 ORDER BY 1,2;
\echo === Q4-3 live alerts per ISO week 09-14..10-23 by tier (baseline volume of the live path)
SELECT date_trunc('week', alert_date)::date wk, score_tier, count(*) FROM mi_ep_alerts WHERE alert_date >= '2026-09-14' GROUP BY 1,2 ORDER BY 1,2;
\echo === Q4-4 heartbeat id gaps: any weekday 10-12..10-23 without a heartbeat row?
SELECT d::date, (SELECT count(*) FROM mi_audit_log a WHERE a.event_type='lowcap_paper_lane_heartbeat' AND (a.detail::jsonb->>'date')::date = d::date) hb_rows FROM generate_series('2026-10-12'::date, '2026-10-23'::date, '1 day') d WHERE extract(dow from d) BETWEEN 1 AND 5 ORDER BY 1;
