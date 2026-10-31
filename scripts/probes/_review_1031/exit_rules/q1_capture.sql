SET default_transaction_read_only = on;
\echo == population: closed magna53 LIVE trades, by exit era (09-06 flip; 10-12 depth exit)
WITH t AS (
  SELECT lt.id, lt.ticker, lt.alert_date, lt.exit_rule, lt.partial_taken,
         s.realized_r, s.peak_r, s.peak_source, s.peak_bars_n, s.capture_pct, s.realized_pnl,
         CASE WHEN lt.alert_date < '2026-09-06' THEN 'a_pre_0906' WHEN lt.alert_date < '2026-10-12' THEN 'b_0906_1011' ELSE 'c_depth_1012+' END AS era
  FROM mi_live_trades lt LEFT JOIN mi_sell_discipline_records s ON s.trade_id = lt.id
  WHERE lt.status = 'closed' AND lt.account_mode = 'live' AND lt.signal_type = 'magna53'
)
SELECT era, count(*) AS n, count(realized_r) AS with_r,
       count(*) FILTER (WHERE peak_r IS NOT NULL AND peak_source <> 'none') AS readable_peak,
       round(avg(realized_r)::numeric, 2) AS exp_r,
       round(100.0 * avg((realized_r > 0)::int)::numeric, 0) AS win_pct,
       round(100.0 * avg((realized_r <= -0.9)::int)::numeric, 0) AS stopped_pct,
       round(avg(peak_r) FILTER (WHERE peak_source <> 'none')::numeric, 2) AS avg_peak_r,
       round(sum(realized_r) FILTER (WHERE peak_r > 0 AND peak_source <> 'none')::numeric / NULLIF(sum(peak_r) FILTER (WHERE peak_r > 0 AND peak_source <> 'none'), 0)::numeric, 2) AS kept_vs_peak,
       round(max(peak_r)::numeric, 2) AS best_peak, round(max(realized_r)::numeric, 2) AS best_kept
FROM t GROUP BY era ORDER BY era;
\echo == the post-09-06 trades one by one
SELECT lt.id, lt.ticker, lt.alert_date, lt.exit_rule, lt.partial_taken, round(s.realized_r::numeric,2) AS r, round(s.peak_r::numeric,2) AS peak, s.peak_source, s.peak_bars_n
FROM mi_live_trades lt LEFT JOIN mi_sell_discipline_records s ON s.trade_id = lt.id
WHERE lt.status='closed' AND lt.account_mode='live' AND lt.signal_type='magna53' AND lt.alert_date >= '2026-09-06' ORDER BY lt.alert_date;
