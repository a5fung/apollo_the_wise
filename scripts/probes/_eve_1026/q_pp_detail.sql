SET default_transaction_read_only = on;
SELECT k, v FROM mi_audit_log, jsonb_each_text(detail::jsonb) AS j(k, v)
 WHERE id = 61839 AND (k LIKE '%pp%' OR k IN ('exit_errors','wall_s','timed_out','step_errors','exit_rows','feed','minutes_feed'));
