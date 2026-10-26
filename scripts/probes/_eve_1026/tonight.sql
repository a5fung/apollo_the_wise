-- Mon 2026-10-26 evening verifies, READ-ONLY. Run after 18:10 ET:
--   ssh apollo@87.99.134.162 "docker exec -i apollo-postgres psql -U apollo -d apollo -A -F '|'" < tonight.sql > tonight.out
SET default_transaction_read_only = on;
\echo '== A. #705 (c) pp recorder: tonight''s run rows'
SELECT id, created_at AT TIME ZONE 'America/New_York' et, left(summary,200), left(detail,1500) FROM mi_audit_log
 WHERE event_type LIKE 'consolidation_breakout_shadow%' AND created_at >= '2026-10-26 12:00-04' ORDER BY id;
\echo '== A2. filled entries since the deploy: day0_pp present, exit rows by kind'
SELECT e.id, e.ticker, e.break_date, e.fill_minute, e.feed, e.day0_pp IS NOT NULL has_pp, left(e.day0_pp::text,300) pp,
       count(x.*) FILTER (WHERE x.arm NOT IN ('A','pp')) n15, count(x.*) FILTER (WHERE x.arm IN ('A','pp')) n_app
FROM mi_consolidation_breakout_entry e LEFT JOIN mi_consolidation_breakout_exit x ON x.entry_id = e.id
WHERE e.status = 'filled' AND e.break_date >= '2026-10-25' GROUP BY e.id ORDER BY e.id;
\echo '== A3. day0_pp NULL on post-deploy fills (expect 0); A/pp rows ever (baseline 0); A/pp on pre-deploy fills (expect 0)'
SELECT (SELECT count(*) FROM mi_consolidation_breakout_entry WHERE status='filled' AND break_date >= '2026-10-25' AND day0_pp IS NULL) pp_null,
       (SELECT count(*) FROM mi_consolidation_breakout_exit WHERE arm IN ('A','pp')) app_rows,
       (SELECT count(*) FROM mi_consolidation_breakout_exit x JOIN mi_consolidation_breakout_entry e ON e.id=x.entry_id
         WHERE x.arm IN ('A','pp') AND e.break_date < '2026-10-25') app_on_old;
\echo '== A4. the A / pp rows'
SELECT x.entry_id, e.ticker, x.arm, x.status, x.realized_r, x.sessions_held, x.n_fwd, x.mature, left(x.events::text,400)
FROM mi_consolidation_breakout_exit x JOIN mi_consolidation_breakout_entry e ON e.id=x.entry_id WHERE x.arm IN ('A','pp') ORDER BY 1,3;
\echo '== B. #482 book arms: tonight''s audit rows'
SELECT id, created_at AT TIME ZONE 'America/New_York' et, event_type, left(summary,200), left(detail,1200) FROM mi_audit_log
 WHERE event_type IN ('book_geometry_arms_recorded','book_geometry_arm_error','live_fill_counterfactual_error','live_fill_counterfactual_recorded')
   AND created_at >= '2026-10-26 12:00-04' ORDER BY id;
\echo '== B2. fill_facts rows per fill (expect exactly 1 each); PENG'
SELECT t.trade_id, t.ticker, t.fill_day, count(f.*) n_facts, max(f.fill_vs_trigger_pct) fvt, max(f.real_risk_vs_trigger_risk) rr_trig, max(f.real_risk_vs_budget) rr_bud
FROM (SELECT DISTINCT trade_id, ticker, fill_day FROM mi_live_fill_counterfactuals) t
LEFT JOIN mi_live_fill_counterfactuals f ON f.trade_id=t.trade_id AND f.arm='fill_facts' GROUP BY 1,2,3 ORDER BY 1;
\echo '== B3. walked book arms'
SELECT trade_id, ticker, arm, entry_rule, entry_minute, entry_price, stop_price, outcome, realized_r, exit_session, settled_session
FROM mi_live_fill_counterfactuals WHERE arm IN ('entry_first_hour_bar','stop_low_of_day','book_first_hour_low_of_day') ORDER BY 1,3;
\echo '== B4. stop_low_of_day vs stop_orb_low on each fill'
SELECT a.trade_id, a.ticker, a.entry_minute, a.stop_price low_of_day, b.stop_price orb_low FROM mi_live_fill_counterfactuals a
JOIN mi_live_fill_counterfactuals b ON b.trade_id=a.trade_id AND b.arm='stop_orb_low' WHERE a.arm='stop_low_of_day' ORDER BY 1;
\echo '== B5. old rows, old columns only, md5 (compare with step0_rows.psv)'
SELECT trade_id, arm, md5(row(id,trade_id,ticker,account_mode,signal_type,entry_attempt,alert_date,fill_day,arm,arm_kind,stop_rule,harvest_rule,entry_price,orb_high,orb_low,live_stop,target_price,target_r,adr20_pct,adr20_n,adr_dollar,stop_price,risk_per_share,stop_width_pct,stop_width_adr,outcome,final_reason,realized_r,realized_pct,pnl_adr,mark_r,partial_fired,gap_through,exit_session,sessions_walked,day0_bar_count,exits,pnl_attribution,regime,exit_era,exit_rules,admission_era,rubric_version,score_tier,ep_score,judge_grade,judge_tier,grade_engine_authority,setup_class,baseline_floor_tier,alert_source,settle_version,settled_session,recorded_at,breakeven_arm_r,trail_rule)::text) md5
FROM mi_live_fill_counterfactuals WHERE arm NOT IN ('entry_first_hour_bar','stop_low_of_day','book_first_hour_low_of_day','fill_facts') ORDER BY trade_id, arm;
\echo '== C. #491 U2: bounces since the deploy (expect 0)'
SELECT m.detail::jsonb->>'ticker' tk, m.detail::jsonb->>'from' frm, t.theme_date
FROM mi_audit_log m JOIN mi_themes t ON t.source='shadow_promoted'
 AND t.name = m.detail::jsonb->>'from' AND (m.detail::jsonb->>'ticker') = ANY(t.tickers)
 AND t.theme_date >  (m.created_at AT TIME ZONE 'America/New_York')::date
 AND t.theme_date <= (m.created_at AT TIME ZONE 'America/New_York')::date + 14
WHERE m.event_type='theme_member_rehomed' AND m.created_at >= '2026-10-24';
\echo '== C2. skip rows since the deploy'
SELECT detail::jsonb->>'path' path, count(DISTINCT (detail::jsonb->>'ticker', detail::jsonb->>'theme')) pairs,
       count(*) FILTER (WHERE (detail::jsonb->>'held_below_floor')::bool) held_rows, count(*) n
FROM mi_audit_log WHERE event_type='promote_member_skipped' AND created_at >= '2026-10-24' GROUP BY 1;
SELECT created_at AT TIME ZONE 'America/New_York' et, left(detail,300) FROM mi_audit_log WHERE event_type='promote_member_skipped' AND created_at >= '2026-10-24' ORDER BY id;
\echo '== C3. promotion runs / failures / rehome moves since the deploy'
SELECT event_type, count(*), max(created_at AT TIME ZONE 'America/New_York') FROM mi_audit_log
 WHERE event_type IN ('shadow_themes_promoted','shadow_promotion_failed','theme_member_rehomed','theme_rehome_pass_ran') AND created_at >= '2026-10-24' GROUP BY 1;
SELECT created_at AT TIME ZONE 'America/New_York' et, left(detail,400) FROM mi_audit_log WHERE event_type='theme_member_rehomed' AND created_at >= '2026-10-24' ORDER BY id;
SELECT created_at AT TIME ZONE 'America/New_York' et, left(summary,300), left(detail,600) FROM mi_audit_log WHERE event_type='shadow_themes_promoted' AND created_at >= '2026-10-24' ORDER BY id;
\echo '== D. #701 (b): SYNA tonight + the two never-fired branches, all time'
SELECT id, created_at AT TIME ZONE 'America/New_York' et, event_type, left(summary,250), left(detail,500) FROM mi_audit_log
 WHERE created_at >= '2026-10-26 17:00-04' AND (event_type IN ('anticipation_mna_pin_held','anticipation_mna_pin_released','mna_release_merit_grade') OR (event_type LIKE '%mna%' AND (summary ILIKE '%SYNA%' OR detail ILIKE '%SYNA%'))) ORDER BY id;
SELECT event_type, count(*), min(created_at AT TIME ZONE 'America/New_York'), max(created_at AT TIME ZONE 'America/New_York') FROM mi_audit_log
 WHERE event_type IN ('anticipation_mna_pin_held','mna_release_merit_grade','anticipation_mna_pin_released') GROUP BY 1;
