-- READ-ONLY. MRNA tonight (10-15): stage + reason only, recorded. Nothing else.
SET default_transaction_read_only = on;
SET statement_timeout = '60s';
SELECT ticker, scan_date, stage, held_from_stage, reason FROM mi_flag_candidates WHERE ticker='MRNA' AND scan_date = DATE '2026-10-15';
