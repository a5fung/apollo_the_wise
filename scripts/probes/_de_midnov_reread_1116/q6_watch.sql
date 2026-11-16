SET default_transaction_read_only = on;
SELECT ticker, ep_date, COUNT(*) n, MIN(session_idx) s0, MAX(session_idx) smax, MAX(session_date) last_d,
       BOOL_OR(screen_member) FILTER (WHERE session_idx=0) screen_member,
       MAX(catalyst_grade) FILTER (WHERE session_idx=0) grade, MAX(extension_pct) FILTER (WHERE session_idx=0) ext
FROM mi_delayed_entry_watch WHERE ep_date >= DATE '2026-08-22' GROUP BY 1,2 ORDER BY 2,1;
