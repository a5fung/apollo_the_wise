SET default_transaction_read_only = on;
\set QUIET 1
\pset pager off
\pset format csv
\echo ==BARS==
SELECT ticker, trade_date, high_price, low_price, close FROM mi_daily_closes
WHERE ticker IN ('AGX','IONQ','PHVS','ALAB','HOOD','QCOM','CRWD') AND trade_date BETWEEN DATE '2026-07-25' AND DATE '2026-10-14' ORDER BY ticker, trade_date;
\echo ==STORED==
SELECT id, ticker, fire_date, fire_minute_et, entry_price, stop_price, stop_price_025, stop_price_075, day_high, day_low, day_close, day0_resolved, day0_post_low, day0_post_high,
       outcome_025, realized_r_025, outcome_trail_025, realized_r_trail_025, mfe_r_025, reached_4r_025,
       outcome_075, realized_r_075, outcome_trail_075, realized_r_trail_075,
       outcome, realized_r, outcome_trail, realized_r_trail, stop_width_pct_075
FROM mi_delayed_entry_trigger WHERE id IN (2670,3230,3233,3234,3303,3304,3305) ORDER BY id;
