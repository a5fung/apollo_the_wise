-- READ-ONLY. State of the HTF breakout shadow and the consolidation (Family A) entry shadow, 2026-10-17.
SELECT 'HTF breakout shadow' k, count(*) rows, count(DISTINCT ticker) tickers, count(*) FILTER (WHERE outcome IS NOT NULL) settled,
  round(avg(realized_r) FILTER (WHERE outcome IS NOT NULL)::numeric,2) avg_r, round(sum(realized_r) FILTER (WHERE outcome IS NOT NULL)::numeric,2) sum_r,
  count(*) FILTER (WHERE realized_r>0) wins, count(*) FILTER (WHERE realized_r>=3) ge3r, min(break_date) first, max(break_date) last,
  count(*) FILTER (WHERE would_reject_reason IS NOT NULL) would_reject
FROM mi_htf_breakout_shadow;
SELECT outcome, count(*), round(avg(realized_r)::numeric,2) FROM mi_htf_breakout_shadow GROUP BY 1 ORDER BY 2 DESC;
SELECT entry_mode, count(*) rows, count(*) FILTER (WHERE outcome IS NOT NULL) settled, round(avg(realized_r) FILTER (WHERE outcome IS NOT NULL)::numeric,2) avg_r,
  round(sum(realized_r) FILTER (WHERE outcome IS NOT NULL)::numeric,1) sum_r, count(*) FILTER (WHERE realized_r>0) wins, count(*) FILTER (WHERE realized_r>=3) ge3r,
  percentile_disc(0.5) WITHIN GROUP (ORDER BY realized_r) FILTER (WHERE outcome IS NOT NULL) median_r, min(entry_date), max(entry_date)
FROM mi_consolidation_entry_shadow GROUP BY 1;
SELECT date_trunc('month', entry_date)::date m, entry_mode, count(*) n, round(avg(realized_r)::numeric,2) avg_r, count(*) FILTER (WHERE realized_r>=3) ge3r
FROM mi_consolidation_entry_shadow WHERE outcome IS NOT NULL GROUP BY 1,2 ORDER BY 1,2;
SELECT state, count(*) FROM mi_anticipation_consolidation WHERE last_eval=(SELECT max(last_eval) FROM mi_anticipation_consolidation) GROUP BY 1;
SELECT stage, count(*) FROM mi_flag_candidates WHERE scan_date=(SELECT max(scan_date) FROM mi_flag_candidates) GROUP BY 1 ORDER BY 2 DESC;
SELECT strategy_id, phase, enabled FROM mi_strategies WHERE strategy_id ILIKE '%flag%' OR strategy_id ILIKE '%htf%' OR strategy_id ILIKE '%consol%' OR strategy_id ILIKE '%anticip%' OR strategy_id ILIKE '%family%';
