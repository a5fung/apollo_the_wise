-- #700: the inputs of the sections the review computes at RENDER time (not stored in
-- mi_system_reviews.metrics) — bands / early-window drift / replay-regression cohort, the
-- setup-review rows, the judge 2nd-opinion counts, the MTD spend. Read-only, captured once.
\echo === LIVE_CLOSED
SELECT id, ticker, alert_date, signal_type, total_pnl, risk_dollars_actual, entry_shares, entry_price, hard_stop,
       exits->0->>'reason' AS exit_reason, (closed_at AT TIME ZONE 'America/New_York')::date AS closed_et
FROM mi_live_trades
WHERE status = 'closed' AND account_mode = 'live' AND pnl_attribution IS NULL
ORDER BY alert_date ASC, id ASC;
\echo === OPEN_LIVE
SELECT ticker, COALESCE(hold_days, 0) AS hold_days, status FROM mi_live_trades
WHERE status IN ('open','filled','partial','order_placed','pending_new') AND account_mode = 'live' ORDER BY alert_date;
\echo === SAFEGUARD
SELECT safeguard, account_mode, state FROM mi_safeguard_state WHERE safeguard = 'drawdown_breaker';
\echo === EQUITY
SELECT account_mode,
       (SELECT equity FROM mi_account_equity_snapshots s2 WHERE s2.account_mode = s.account_mode ORDER BY snapshot_date ASC LIMIT 1) AS first_eq,
       (SELECT equity FROM mi_account_equity_snapshots s2 WHERE s2.account_mode = s.account_mode ORDER BY snapshot_date DESC LIMIT 1) AS last_eq
FROM (SELECT DISTINCT account_mode FROM mi_account_equity_snapshots) s;
\echo === SETUP_REVIEW_90D
SELECT t.signal_type, t.account_mode, COUNT(*) AS n, COUNT(*) FILTER (WHERE t.total_pnl > 0) AS wins,
       ROUND(SUM(t.total_pnl)::numeric, 2) AS total_pnl,
       MODE() WITHIN GROUP (ORDER BY t.exits->0->>'reason') AS top_exit,
       COUNT(*) FILTER (WHERE t.exits->0->>'reason' = 'stop_hit') AS n_stop_hit,
       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY r.peak_r) AS med_peak_r,
       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY r.realized_r) AS med_realized_r,
       COUNT(*) FILTER (WHERE r.peak_r >= 2 AND r.realized_r < 0) AS ran_then_lost,
       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY r.stop_per_adr) AS med_stop_per_adr,
       COUNT(*) FILTER (WHERE r.peak_source = 'extremes' AND r.peak_r = 0) AS blind_peaks,
       MAX(s.phase) AS phase
FROM mi_live_trades t
LEFT JOIN mi_sell_discipline_records r ON r.trade_id = t.id
LEFT JOIN mi_strategies s ON s.signal_type = t.signal_type
WHERE t.status = 'closed' AND t.alert_date >= CURRENT_DATE - 90
GROUP BY t.signal_type, t.account_mode, s.phase HAVING COUNT(*) > 0 ORDER BY COUNT(*) DESC;
\echo === JUDGE_DIV_SINCE_1004
SELECT COUNT(*) FILTER (WHERE primary_tier = 'HIGH') AS n,
       COUNT(*) FILTER (WHERE NOT agree AND primary_tier = 'HIGH') AS n_disagree,
       COUNT(*) FILTER (WHERE NOT agree AND primary_tier = 'HIGH' AND secondary_tier <> 'HIGH') AS n_stricter,
       COUNT(*) FILTER (WHERE NOT agree AND primary_tier <> 'HIGH' AND secondary_tier = 'HIGH') AS n_looser,
       MAX(secondary_model) AS secondary_model
FROM mi_judge_divergence WHERE alert_date >= '2026-10-04';
\echo === API_USAGE_MTD
SELECT 'total' AS caller, COUNT(*) AS calls, ROUND(COALESCE(SUM(cost_usd),0)::numeric, 4) AS cost
FROM api_usage WHERE created_at >= date_trunc('month', now())
UNION ALL
(SELECT caller, COUNT(*), ROUND(COALESCE(SUM(cost_usd),0)::numeric, 4) FROM api_usage
 WHERE created_at >= date_trunc('month', now()) GROUP BY caller ORDER BY 3 DESC LIMIT 3);
\echo === MISSED_GAPS_PRIOR_KEYS
SELECT review_date, g->>'ticker' AS ticker, g->>'alert_date' AS alert_date, g->>'skip_category' AS cat
FROM mi_system_reviews, jsonb_array_elements(metrics->'missed_opportunities'->'gaps') g
WHERE review_date IN ('2026-10-04','2026-10-11') ORDER BY review_date, 3;
