SET default_transaction_read_only = on;
-- #720 §6 + §3: the missed-by-slots records, the hold notes (the absence observable), the fill-stop decisions, the session-third events.
\copy (SELECT id, created_at, event_type, summary, detail FROM mi_audit_log WHERE created_at >= TIMESTAMPTZ '2026-10-29 00:00-04' AND (event_type IN ('breakout_v1_missed_by_slots', 'breakout_v1_entry_hold', 'breakout_v1_fill_stop_checked', 'breakout_v1_missed_unreadable') OR event_type LIKE 'breakout_pp_session_third%' OR event_type LIKE 'breakout_pp_third%') ORDER BY created_at, id) TO STDOUT WITH CSV HEADER
