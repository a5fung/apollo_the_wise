\echo == mi_stock_scores
SELECT count(*) AS rows, count(market_cap) AS nonnull_market_cap, max(score_date) AS last_score_date FROM mi_stock_scores;
\echo == mi_live_fill_counterfactuals
SELECT count(*) AS rows, count(mark_r) AS nonnull_mark_r, max(created_at) AS last_created FROM mi_live_fill_counterfactuals;
SELECT outcome, count(*) FROM mi_live_fill_counterfactuals GROUP BY 1 ORDER BY 1;
SELECT min(session_date), max(session_date) FROM mi_live_fill_counterfactuals;
\echo == mi_gap_near_miss_replays
SELECT count(*) AS rows, count(mark_r) AS nonnull_mark_r FROM mi_gap_near_miss_replays;
SELECT outcome, count(*), count(mark_r) AS with_mark FROM mi_gap_near_miss_replays GROUP BY 1 ORDER BY 1;
\echo == tables with a mark_r column
SELECT table_name, column_name FROM information_schema.columns WHERE column_name='mark_r' ORDER BY 1;
\echo == sustain replays
SELECT outcome, count(*), count(mark_r) FROM mi_sustain_reject_replays GROUP BY 1 ORDER BY 1;
\echo == dead column audit rows
SELECT event_type, summary, min(created_at) FROM mi_audit_log WHERE summary IN ('mi_stock_scores.market_cap','mi_live_fill_counterfactuals.mark_r','mi_gap_near_miss_replays.mark_r') GROUP BY 1,2 ORDER BY 2,1;
