-- Tue 2026-10-27 evening verifies, READ-ONLY. Run after 18:10 ET.
SET default_transaction_read_only = on;
\echo '== A. #482 night two: audit rows since the noon deploy'
SELECT id, created_at AT TIME ZONE 'America/New_York' et, event_type, left(summary,260) FROM mi_audit_log
 WHERE event_type IN ('book_geometry_arms_recorded','book_geometry_arm_error','live_fill_counterfactual_error','live_fill_counterfactual_recorded')
   AND created_at >= '2026-10-27 12:00-04' ORDER BY id;
\echo '== A2. fill_facts rows per fill (expect exactly 1 each — no second row on night two)'
SELECT t.trade_id, t.ticker, count(f.*) n_facts FROM (SELECT DISTINCT trade_id, ticker FROM mi_live_fill_counterfactuals) t
LEFT JOIN mi_live_fill_counterfactuals f ON f.trade_id=t.trade_id AND f.arm='fill_facts' GROUP BY 1,2 HAVING count(f.*) <> 1 ORDER BY 1;
SELECT count(*) fills, sum(CASE WHEN arm='fill_facts' THEN 1 ELSE 0 END) facts_rows FROM mi_live_fill_counterfactuals;
\echo '== A3. dead-column flags tonight on the new columns (expect none after night one wrote them)'
SELECT created_at AT TIME ZONE 'America/New_York' et, left(summary,120) FROM mi_audit_log WHERE event_type='dead_column_suspect' AND created_at >= '2026-10-27 12:00-04' ORDER BY id;
\echo '== A4. walked book arms settled since night one'
SELECT arm, outcome, count(*) FROM mi_live_fill_counterfactuals WHERE arm IN ('entry_first_hour_bar','stop_low_of_day','book_first_hour_low_of_day') GROUP BY 1,2 ORDER BY 1,2;
\echo '== B. #491 night 2: bounces since the U2 deploy (expect 0), skip rows, failures'
SELECT m.detail::jsonb->>'ticker' tk, m.detail::jsonb->>'from' frm, t.theme_date FROM mi_audit_log m JOIN mi_themes t ON t.source='shadow_promoted'
 AND t.name = m.detail::jsonb->>'from' AND (m.detail::jsonb->>'ticker') = ANY(t.tickers)
 AND t.theme_date > (m.created_at AT TIME ZONE 'America/New_York')::date AND t.theme_date <= (m.created_at AT TIME ZONE 'America/New_York')::date + 14
WHERE m.event_type='theme_member_rehomed' AND m.created_at >= '2026-10-24';
SELECT created_at AT TIME ZONE 'America/New_York' et, left(detail,260) FROM mi_audit_log WHERE event_type='promote_member_skipped' AND created_at >= '2026-10-27 12:00-04' ORDER BY id;
SELECT event_type, count(*) FROM mi_audit_log WHERE event_type IN ('shadow_themes_promoted','shadow_promotion_failed','theme_member_rehomed','theme_rehome_pass_ran') AND created_at >= '2026-10-27 12:00-04' GROUP BY 1;
SELECT created_at AT TIME ZONE 'America/New_York' et, left(detail,400) FROM mi_audit_log WHERE event_type='theme_member_rehomed' AND created_at >= '2026-10-27 12:00-04' ORDER BY id;
\echo '== C. the pp recorder night two: run row, walked pp rows (n_fwd >= 1, not stopped_day0), mature by a daily walk'
SELECT id, created_at AT TIME ZONE 'America/New_York' et FROM mi_audit_log WHERE event_type='consolidation_breakout_shadow_run' AND created_at >= '2026-10-27 12:00-04';
SELECT x.arm, x.status, x.mature, count(*), max(x.n_fwd) FROM mi_consolidation_breakout_exit x WHERE x.arm IN ('A','pp') GROUP BY 1,2,3 ORDER BY 1,2,3;
SELECT x.entry_id, e.ticker, x.arm, x.status, x.n_fwd, x.sessions_held, x.realized_r, left(x.events::text,300) FROM mi_consolidation_breakout_exit x
 JOIN mi_consolidation_breakout_entry e ON e.id=x.entry_id WHERE x.arm='pp' AND x.status <> 'stopped_day0' AND x.n_fwd >= 1 ORDER BY x.entry_id LIMIT 8;
