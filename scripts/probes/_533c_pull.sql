-- #533 Change 6 — catalyst tier shadow evaluation capture (2026-08-22). READ-ONLY.
-- One pull, read many (COST EFFICIENCY rule). All text fields newline/pipe-flattened.
\echo ===ALERTS_TEXT
SELECT a.id, a.ticker, a.alert_date, COALESCE(a.source,'live') src, a.score_tier,
  round(a.ep_score::numeric,1) ep_score, round(a.gap_pct::numeric,2) gap_pct,
  COALESCE(a.catalyst_quality,'') quality, COALESCE(a.judge_tier,'') judge_tier,
  COALESCE(a.grade_engine_authority,'') authority, COALESCE(a.catalyst_type,'') ctype,
  round(COALESCE(a.confidence_multiplier,1.0)::numeric,2) conf_mult,
  to_char(a.detected_at AT TIME ZONE 'America/New_York','HH24:MI') det_et,
  substr(regexp_replace(COALESCE(a.catalyst,''), E'[\\n\\r|]+', ' ', 'g'),1,400) catalyst,
  substr(regexp_replace(COALESCE(a.catalyst_type_rationale,''), E'[\\n\\r|]+', ' ', 'g'),1,300) ctype_rat,
  substr(regexp_replace(COALESCE(a.judge_rationale,''), E'[\\n\\r|]+', ' ', 'g'),1,600) judge_rat,
  substr(regexp_replace(COALESCE(a.claude_analysis,''), E'[\\n\\r|]+', ' ', 'g'),1,1500) analysis,
  substr(regexp_replace(COALESCE(a.grounded_text,''), E'[\\n\\r|]+', ' ', 'g'),1,3000) gtext
FROM mi_ep_alerts a ORDER BY a.alert_date, a.id;
\echo ===EXPCT
SELECT s.alert_id, s.ticker, s.alert_date, COALESCE(s.expct_scheduled,'') sched,
  COALESCE(s.expct_scheduled_src,'') sched_src, COALESCE(s.expct_looking,'') looking,
  s.expct_beat, s.expct_growth_yoy_pct, COALESCE(s.expct_combined_class,'') combined,
  s.expct_classifiable_frac
FROM mi_alert_rank_shadow s ORDER BY s.alert_date, s.alert_id;
\echo ===BOARD
SELECT s.scan_date, s.ticker, round(max(s.gap_pct)::numeric,2) max_gap,
  COALESCE(max(o.sector),'') sector,
  bool_or(s.catalyst_quality IS NOT NULL) graded
FROM mi_ep_scan_log s LEFT JOIN mi_ticker_overrides o ON o.ticker = s.ticker
WHERE s.scan_date IN (SELECT DISTINCT alert_date FROM mi_ep_alerts)
GROUP BY 1,2;
\echo ===REGIME
SELECT regime_date, regime, ep_threshold FROM mi_market_regime
WHERE regime_date IN (SELECT DISTINCT alert_date FROM mi_ep_alerts) ORDER BY 1;
\echo ===MEMBER_AUDIT
SELECT to_char(l.created_at AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI') ts_et,
  l.event_type, substr(regexp_replace(l.summary, E'[\\n\\r|]+', ' ', 'g'),1,300) summary,
  substr(regexp_replace(COALESCE(l.detail,''), E'[\\n\\r|]+', ' ', 'g'),1,1500) detail
FROM mi_audit_log l
WHERE ((l.created_at AT TIME ZONE 'America/New_York')::date, 1) IN
      ((DATE '2026-04-17',1),(DATE '2026-04-24',1),(DATE '2026-05-06',1),(DATE '2026-05-29',1),(DATE '2026-08-19',1))
  AND (l.summary ~ '\y(ARM|UMC|QCOM|AMD|QURE|INTC|MRNA)\y' OR l.detail ~ '\y(ARM|UMC|QCOM|AMD|QURE|INTC|MRNA)\y')
ORDER BY l.created_at;
\echo ===MRNA_FULL
SELECT a.id, a.ticker, a.alert_date,
  regexp_replace(COALESCE(a.claude_analysis,''), E'[\\n\\r|]+', ' ', 'g') analysis_full,
  substr(regexp_replace(COALESCE(a.grounded_text,''), E'[\\n\\r|]+', ' ', 'g'),1,8000) gtext_full
FROM mi_ep_alerts a WHERE a.ticker='MRNA' AND a.alert_date=DATE '2026-08-19';
