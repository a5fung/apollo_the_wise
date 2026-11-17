SET default_transaction_read_only = on;
SELECT market, comm, lspec, sspec FROM mi_cot_index_weekly WHERE report_date='2026-11-10' ORDER BY 1;
