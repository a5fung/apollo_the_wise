\echo === TRADES ===
SELECT id, ticker, alert_date, account_mode, signal_type, status, entry_attempt,
       orb_high, orb_low, atr_14, entry_price, entry_shares, stop_price, hard_stop,
       risk_dollars, risk_dollars_actual, total_pnl, remaining_shares,
       partial_taken, breakeven_active, pnl_attribution,
       filled_at AT TIME ZONE 'America/New_York' AS filled_at_et,
       closed_at AT TIME ZONE 'America/New_York' AS closed_at_et,
       exits::text AS exits_json
FROM mi_live_trades
WHERE signal_type='magna53' AND status='closed'
ORDER BY alert_date, ticker;
\echo === ALERTS ===
SELECT id, ticker, alert_date, gap_pct, rel_volume, ep_score, score_tier,
       catalyst_quality, vol_percentile, in_active_theme, pm_rvol,
       judge_tier, grade_engine_authority,
       detected_at AT TIME ZONE 'America/New_York' AS detected_at_et
FROM mi_ep_alerts WHERE COALESCE(source,'live')='live'
ORDER BY alert_date, ticker;
\echo === REGIME ===
SELECT regime_date, regime, ep_threshold FROM mi_market_regime ORDER BY regime_date;
\echo === DAILY ===
WITH cohort AS (
  SELECT DISTINCT ticker FROM mi_ep_alerts WHERE COALESCE(source,'live')='live'
  UNION SELECT DISTINCT ticker FROM mi_live_trades WHERE signal_type='magna53' AND status='closed'
)
SELECT d.ticker, d.trade_date, d.open_price, d.high_price, d.low_price, d.close, d.volume
FROM mi_daily_closes d JOIN cohort c USING (ticker)
WHERE d.trade_date >= '2026-01-01'
ORDER BY d.ticker, d.trade_date;
