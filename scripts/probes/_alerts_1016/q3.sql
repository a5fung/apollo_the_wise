-- READ-ONLY. Why was SYNA's 10-09 confirm fire (seen in the replay) not recorded?
SELECT id, ticker, anchor_date, entry_date, entry_mode, status FROM mi_consolidation_entry_shadow WHERE ticker='SYNA' ORDER BY entry_date;
SELECT ticker, anchor_date, state, last_eval, mna_screened_on FROM mi_anticipation_consolidation WHERE ticker='SYNA' ORDER BY anchor_date;
SELECT created_at, event_type, left(summary,220) FROM mi_audit_log WHERE created_at BETWEEN '2026-10-09' AND '2026-10-11' AND summary ILIKE '%SYNA%' ORDER BY created_at;
