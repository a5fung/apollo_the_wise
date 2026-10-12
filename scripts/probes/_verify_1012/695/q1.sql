\echo == market_cap column on mi_stock_scores (expect 0 rows)
SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='mi_stock_scores' AND column_name='market_cap';
\echo == mi_stock_scores row counts by score_date (last 5)
SELECT score_date, count(*) FROM mi_stock_scores GROUP BY 1 ORDER BY 1 DESC LIMIT 5;
\echo == live-fill counterfactuals: shape
SELECT count(*) AS rows, count(mark_r) AS mark_r_nonnull, count(*) FILTER (WHERE outcome='horizon') AS horizon_rows, min(created_at)::date AS first_row, max(created_at)::date AS last_row FROM mi_live_fill_counterfactuals;
\echo == live-fill counterfactuals: outcome distribution
SELECT outcome, count(*) FROM mi_live_fill_counterfactuals GROUP BY 1 ORDER BY 2 DESC;
\echo == live-fill counterfactuals: columns
SELECT column_name, data_type FROM information_schema.columns WHERE table_schema='public' AND table_name='mi_live_fill_counterfactuals' ORDER BY ordinal_position;
\echo == the three mark_r tables
SELECT 'mi_gap_near_miss_replays' t, count(*) n, count(mark_r) nn, count(*) FILTER (WHERE outcome IN ('open','horizon')) ev FROM mi_gap_near_miss_replays
UNION ALL SELECT 'mi_sustain_reject_replays', count(*), count(mark_r), count(*) FILTER (WHERE outcome IN ('open','horizon')) FROM mi_sustain_reject_replays
UNION ALL SELECT 'mi_lowcap_lane_replays', count(*), count(mark_r), count(*) FILTER (WHERE outcome IN ('open','horizon')) FROM mi_lowcap_lane_replays
UNION ALL SELECT 'mi_lowcap_paper_lane_replays', count(*), count(mark_r), count(*) FILTER (WHERE outcome IN ('open','horizon')) FROM mi_lowcap_paper_lane_replays;
\echo == dead_column audit rows since 10-05
SELECT created_at AT TIME ZONE 'America/New_York' AS t_et, event_type, left(summary,120) FROM mi_audit_log WHERE event_type LIKE 'dead_column%' AND created_at >= '2026-10-05' ORDER BY created_at;
