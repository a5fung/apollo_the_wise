SET default_transaction_read_only = on;
-- daily bars ONLY for the EP-alert campaign tickers of this review (the lane's own names), for the 15/40-session labels
SELECT d.ticker, d.trade_date, d.open_price, d.high_price, d.low_price, d.close, d.volume
FROM mi_daily_closes d
WHERE d.ticker IN (SELECT DISTINCT ticker FROM mi_ep_alerts WHERE alert_date >= DATE '2026-08-22')
  AND d.trade_date >= DATE '2026-04-01'
ORDER BY d.ticker, d.trade_date;
