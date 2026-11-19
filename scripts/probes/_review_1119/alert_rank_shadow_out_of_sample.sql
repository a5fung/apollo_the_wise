SET default_transaction_read_only = on;
SELECT count(DISTINCT alert_date) FROM mi_alert_rank_shadow WHERE alert_date > DATE '2026-08-16';
