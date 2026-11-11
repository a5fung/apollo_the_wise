-- #717 DoD (3): the inputs of the bought-names sheet. READ-ONLY. The newest night's breakout v1 list and the daily
-- bars (<= that night, the last 504 sessions) of every name on it. Main loop runs it on prod and saves the output:
--   psql ... -A -F'|' -f 10_sheet_latest_list.sql > scripts/probes/_717_shape_gates_1111/10_sheet_latest_list.out
-- then: python3 scripts/probes/_717_shape_gates_1111/11_render_bought_sheet.py
SET default_transaction_read_only = on;
\echo == LIST
SELECT scan_date, ticker, list_rank, level, order_score, adr20, runup6m_adr, spread10_adr
FROM mi_breakout_v1_list
WHERE scan_date = (SELECT max(scan_date) FROM mi_breakout_v1_list)
ORDER BY list_rank;
\echo == BARS
SELECT ticker, trade_date, open_price, high_price, low_price, close_price, volume FROM (
  SELECT c.ticker, c.trade_date, c.open_price, c.high_price, c.low_price, c.close AS close_price, c.volume,
         row_number() OVER (PARTITION BY c.ticker ORDER BY c.trade_date DESC) AS rn
  FROM mi_daily_closes c
  JOIN mi_breakout_v1_list l
    ON l.ticker = c.ticker AND l.scan_date = (SELECT max(scan_date) FROM mi_breakout_v1_list)
  WHERE c.trade_date <= l.scan_date
) x WHERE rn <= 504 ORDER BY ticker, trade_date;
