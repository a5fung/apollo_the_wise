SET default_transaction_read_only = on;
SELECT count(*) FROM mi_audit_log WHERE event_type = 'mna_release_merit_grade' AND created_at >= DATE '2026-10-03';
SELECT event_type, count(*) FROM mi_audit_log WHERE event_type IN ('mna_release_without_merit_grade','mna_pin_released','mna_filter_released') AND created_at >= DATE '2026-10-03' GROUP BY 1;
