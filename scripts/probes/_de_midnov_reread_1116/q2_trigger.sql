SET default_transaction_read_only = on;
SELECT * FROM mi_delayed_entry_trigger WHERE ep_date >= DATE '2026-08-22' ORDER BY ep_date, ticker, fire_date, rung, id;
