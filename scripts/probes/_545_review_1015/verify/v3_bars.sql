SET default_transaction_read_only = on;
\set QUIET 1
\pset pager off
\pset format csv
SELECT d.ticker, d.trade_date, d.high_price, d.low_price, d.close
FROM mi_daily_closes d
WHERE d.ticker IN (SELECT DISTINCT ticker FROM mi_delayed_entry_trigger WHERE rung='ep_low_reclaim' AND reentry_shape='first' AND fire_date >= DATE '2026-09-02')
  AND d.trade_date BETWEEN DATE '2026-06-25' AND DATE '2026-10-14'
ORDER BY d.ticker, d.trade_date;
