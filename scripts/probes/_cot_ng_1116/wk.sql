SET default_transaction_read_only = on;
SELECT market, comm, lspec, sspec, setup, close_setup FROM mi_cot_index_weekly WHERE report_date='2026-11-10' AND (setup IS NOT NULL OR close_setup IS NOT NULL OR comm>=90 OR comm<=10) ORDER BY 1;
