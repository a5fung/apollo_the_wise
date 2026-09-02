\echo === SHADOW_ROWS ===
SELECT id, ticker, alert_date, signal_type, status, skip_reason,
       orb_high, orb_low, atr_14, entry_price, stop_price, hard_stop,
       risk_dollars, entry_shares, remaining_shares, partial_taken,
       total_pnl, hold_days, created_at, closed_at, quarantined,
       (replayed_at IS NOT NULL) AS was_replayed,
       exits::text AS exits_json
FROM mi_orb_shadow_trades
WHERE bar_size_minutes = 5
ORDER BY alert_date, ticker;
\echo === LIVE_ROWS ===
SELECT id, ticker, alert_date, status, account_mode, entry_attempt, signal_type,
       skip_reason, orb_high, orb_low, atr_14, entry_price, stop_price, hard_stop,
       risk_dollars, risk_dollars_actual, entry_shares, total_pnl, partial_taken,
       hold_days, filled_at, closed_at,
       exits::text AS exits_json
FROM mi_live_trades
WHERE signal_type = 'magna53'
ORDER BY alert_date, ticker;
\echo === FWD_CLOSES ===
WITH keys AS (
  SELECT DISTINCT ticker, alert_date FROM (
    SELECT ticker, alert_date FROM mi_orb_shadow_trades
      WHERE bar_size_minutes=5 AND status='closed' AND NOT quarantined
    UNION
    SELECT ticker, alert_date FROM mi_live_trades
      WHERE signal_type='magna53' AND status='closed'
  ) u
)
SELECT k.ticker, k.alert_date, d.trade_date, d.close, d.high_price, d.low_price
FROM keys k
JOIN LATERAL (
  SELECT trade_date, close, high_price, low_price
  FROM mi_daily_closes dc
  WHERE dc.ticker = k.ticker AND dc.trade_date >= k.alert_date
  ORDER BY trade_date
  LIMIT 8
) d ON true
ORDER BY k.ticker, k.alert_date, d.trade_date;
