SET default_transaction_read_only = on;
\echo == live MAGNA53 closed trades by regime (as stamped at entry) and stop era (08-16 = the R unit changed)
SELECT CASE WHEN lt.alert_date < '2026-08-16' THEN 'a_orb_low_stop' ELSE 'b_2R_stop' END AS stop_era, coalesce(lt.regime,'(none)') AS regime,
       count(*) AS n, count(*) FILTER (WHERE s.peak_r >= 1.5) AS reached_1_5r,
       round(avg(s.peak_r) FILTER (WHERE s.peak_r >= 1.5)::numeric, 2) AS avg_peak_of_those,
       round(avg(s.peak_r) FILTER (WHERE s.peak_r < 1.5)::numeric, 2) AS avg_peak_rest,
       round(avg(s.realized_r)::numeric, 2) AS avg_kept, round(max(s.peak_r)::numeric, 2) AS best_peak
FROM mi_live_trades lt JOIN mi_sell_discipline_records s ON s.trade_id = lt.id
WHERE lt.status = 'closed' AND lt.account_mode = 'live' AND lt.signal_type = 'magna53'
GROUP BY 1, 2 ORDER BY 1, 2;
\echo == regime by day since 2026-08-01
SELECT regime_date, regime FROM mi_market_regime WHERE regime_date >= '2026-08-01' ORDER BY regime_date;
