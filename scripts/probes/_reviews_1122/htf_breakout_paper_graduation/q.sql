SET default_transaction_read_only = on;
\echo === Q1 predicate (bar 5) + table census
SELECT COUNT(*) FILTER (WHERE outcome IS NOT NULL AND would_reject_reason IS NULL) AS takeable_settled,
       COUNT(*) AS rows_total, MIN(break_date) AS first_break, MAX(break_date) AS last_break,
       COUNT(*) FILTER (WHERE outcome IS NOT NULL) AS settled_all,
       COUNT(*) FILTER (WHERE outcome IS NULL AND settle_abstain_reason IS NULL) AS open_unsettled,
       COUNT(*) FILTER (WHERE settle_abstain_reason IS NOT NULL) AS abstained,
       COUNT(*) FILTER (WHERE would_reject_reason IS NOT NULL) AS would_reject
FROM mi_htf_breakout_shadow;
\echo === Q2 takeable settled cohort summary (the GO-bar population)
SELECT COUNT(*) AS n,
       COUNT(*) FILTER (WHERE outcome='capture') AS capture_n,
       COUNT(*) FILTER (WHERE outcome='stop') AS stop_n,
       COUNT(*) FILTER (WHERE outcome='open') AS timeout_n,
       ROUND(AVG(realized_r)::numeric,3) AS mean_r,
       ROUND((percentile_cont(0.5) WITHIN GROUP (ORDER BY realized_r))::numeric,3) AS median_r,
       COUNT(*) FILTER (WHERE realized_r > 0) AS winners,
       COUNT(*) FILTER (WHERE realized_r >= 3) AS ge_3r,
       ROUND(MAX(realized_r)::numeric,3) AS max_r,
       ROUND(AVG(fwd_mfe_r)::numeric,3) AS mean_mfe_r,
       ROUND(MAX(fwd_mfe_r)::numeric,3) AS max_mfe_r,
       ROUND(AVG(target_r)::numeric,2) AS avg_target_r
FROM mi_htf_breakout_shadow
WHERE outcome IS NOT NULL AND would_reject_reason IS NULL;
\echo === Q3 per-row takeable settled
SELECT id, ticker, break_date, parent_stage, stop_kind, ROUND((max_loss_pct*100)::numeric,2) AS stop_pct,
       outcome, ROUND(realized_r::numeric,3) AS r, ROUND(fwd_mfe_r::numeric,3) AS mfe_r, settled_at::date AS settled
FROM mi_htf_breakout_shadow
WHERE outcome IS NOT NULL AND would_reject_reason IS NULL ORDER BY break_date, id;
\echo === Q4 all rows by reject reason / outcome (population check)
SELECT COALESCE(would_reject_reason,'(takeable)') AS reject, COALESCE(outcome,'(unsettled)') AS outcome,
       COALESCE(settle_abstain_reason,'') AS abstain, COUNT(*) AS n
FROM mi_htf_breakout_shadow GROUP BY 1,2,3 ORDER BY 1,2,3;
\echo === Q5 unsettled / abstained rows
SELECT id, ticker, break_date, would_reject_reason, outcome, settle_abstain_reason,
       (CURRENT_DATE - break_date) AS age_days
FROM mi_htf_breakout_shadow WHERE outcome IS NULL ORDER BY break_date;
\echo === Q6 management-protocol shadow (#396) on the same takeable settled parents, excluding abstained
SELECT COUNT(*) AS n, COUNT(*) FILTER (WHERE m.status<>'open') AS closed,
       ROUND(AVG(m.realized_r) FILTER (WHERE m.status<>'open')::numeric,3) AS mean_r_closed,
       COUNT(*) FILTER (WHERE m.realized_r >= 3) AS ge_3r
FROM mi_htf_management_shadow m JOIN mi_htf_breakout_shadow b ON b.id=m.shadow_id
WHERE b.settle_abstain_reason IS NULL AND b.would_reject_reason IS NULL;
SELECT b.ticker, b.break_date, m.status, m.partial_taken, ROUND(m.realized_r::numeric,3) AS mgmt_r,
       b.outcome, ROUND(b.realized_r::numeric,3) AS fixed_r
FROM mi_htf_management_shadow m JOIN mi_htf_breakout_shadow b ON b.id=m.shadow_id
WHERE b.settle_abstain_reason IS NULL AND b.would_reject_reason IS NULL ORDER BY b.break_date;
\echo === Q7 since the 10-17 read: rows settled after 2026-10-17
SELECT COUNT(*) AS settled_since_1017,
       ROUND(AVG(realized_r) FILTER (WHERE would_reject_reason IS NULL)::numeric,3) AS takeable_mean_r
FROM mi_htf_breakout_shadow WHERE settled_at >= '2026-10-17' AND outcome IS NOT NULL;
