SELECT DISTINCT ON (a.ticker, a.alert_date)
  a.ticker, a.alert_date,
  round(COALESCE(a.gap_pct,0)::numeric,2),
  round(COALESCE(a.ep_score,0)::numeric,1),
  COALESCE(a.score_tier,''), COALESCE(a.judge_tier,''),
  COALESCE(a.catalyst_quality,''), COALESCE(a.catalyst_type,''),
  COALESCE(a.grade_engine_authority,''), COALESCE(a.source,'live'),
  left(translate(COALESCE(a.catalyst,''), chr(9)||chr(10)||chr(13)||chr(124), '    '),1200),
  left(translate(COALESCE(a.catalyst_type_rationale,''), chr(9)||chr(10)||chr(13)||chr(124), '    '),400),
  left(translate(COALESCE(a.judge_rationale,''), chr(9)||chr(10)||chr(13)||chr(124), '    '),1000),
  left(translate(COALESCE(a.grounded_text,''), chr(9)||chr(10)||chr(13)||chr(124), '    '),3000),
  COALESCE(m.q_revenue_yoy_pct::text,''),
  COALESCE(m.extraction_quality,'')
FROM mi_ep_alerts a
LEFT JOIN mi_ep_catalyst_metrics m
  ON m.ticker=a.ticker AND m.alert_date=a.alert_date
ORDER BY a.ticker, a.alert_date, COALESCE(a.detected_at, a.created_at)
