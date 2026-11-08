SET default_transaction_read_only = on;
-- #720 §1.4 (re-challenge finding 10): the #482 recorder's own heartbeat — one live_fill_counterfactual_recorded row per nightly run (18:04 ET, mon-fri) and every live_fill_counterfactual_error row, from the first window start. A month with no older closes can still show a dead recorder.
\copy (SELECT id, created_at, event_type, summary FROM mi_audit_log WHERE created_at >= TIMESTAMPTZ '2026-08-16 00:00-04' AND event_type IN ('live_fill_counterfactual_recorded', 'live_fill_counterfactual_error') ORDER BY created_at, id) TO STDOUT WITH CSV HEADER
