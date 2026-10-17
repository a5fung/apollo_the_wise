-- READ-ONLY. Shape checks for three gated reviews reading zero past their date (2026-10-17).
SELECT 'bull closes (term 1)' k, COUNT(*) v FROM mi_live_trades WHERE account_mode='live' AND status='closed' AND signal_type='magna53' AND regime='Bull'
UNION ALL SELECT 'live magna53 closes entered since 10-13 (any regime)', COUNT(*) FROM mi_live_trades WHERE account_mode='live' AND status='closed' AND signal_type='magna53' AND created_at >= DATE '2026-10-13'
UNION ALL SELECT 'live magna53 opened since 10-13', COUNT(*) FROM mi_live_trades WHERE account_mode='live' AND signal_type='magna53' AND created_at >= DATE '2026-10-13'
UNION ALL SELECT 'counterfactual rows era_e (any outcome)', COUNT(*) FROM mi_live_fill_counterfactuals WHERE exit_era='era_e'
UNION ALL SELECT 'counterfactual rows era_e settled live_actual', COUNT(*) FROM mi_live_fill_counterfactuals WHERE exit_era='era_e' AND arm='live_actual' AND outcome='settled'
UNION ALL SELECT 'counterfactual rows any era settled pairs (shape)', COUNT(*) FROM mi_live_fill_counterfactuals WHERE arm='live_replay' AND outcome='settled'
UNION ALL SELECT 'lowcap replays total', COUNT(*) FROM mi_lowcap_lane_replays
UNION ALL SELECT 'lowcap replays settled', COUNT(*) FROM mi_lowcap_lane_replays WHERE outcome='settled'
UNION ALL SELECT 'lowcap replays settled distinct tickers', COUNT(DISTINCT ticker) FROM mi_lowcap_lane_replays WHERE outcome='settled'
UNION ALL SELECT 'lowcap lane signals total', COUNT(*) FROM mi_lowcap_lane_signals;
SELECT outcome, COUNT(*) FROM mi_lowcap_lane_replays GROUP BY 1 ORDER BY 2 DESC;
