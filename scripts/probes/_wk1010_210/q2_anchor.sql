-- #210 read 2026-10-10, pull 2 — SELECT only. Captured ONCE to q2_anchor.out.
\echo '### A1 grade time (provenance row) vs alert time for the 10 shadow rows'
SELECT s.ticker, s.alert_date, a.detected_at AT TIME ZONE 'America/New_York' AS alert_detected_et, a.created_at AT TIME ZONE 'America/New_York' AS alert_created_et, a.catalyst_quality AS alert_cq, a.ep_score, a.gap_pct, left(a.catalyst, 160) AS catalyst, (SELECT min(l.created_at) AT TIME ZONE 'America/New_York' FROM mi_audit_log l WHERE l.event_type='ep_catalyst_provenance' AND l.detail LIKE '%"ticker": "' || s.ticker || '"%' AND l.detail LIKE '%' || s.alert_date::text || '%') AS graded_et FROM mi_tv_news_shadow s JOIN mi_ep_alerts a ON a.ticker=s.ticker AND a.alert_date=s.alert_date ORDER BY s.alert_date;

\echo '### A2 BFLY 2026-06-18 stored corpus (true-miss fixture source)'
SELECT ticker, alert_date, extracted_at AT TIME ZONE 'America/New_York' AS extracted_et, raw_polygon_news_json::text AS polygon, raw_alpaca_news_json::text AS alpaca, raw_fmp_news_json::text AS fmp, left(raw_perplexity_text, 600) AS pplx FROM mi_ep_catalyst_metrics WHERE ticker='BFLY' AND alert_date='2026-06-18';

\echo '### A3 BFLY 2026-06-18 alert row (catalyst text + grounded_text head)'
SELECT ticker, alert_date, detected_at AT TIME ZONE 'America/New_York' AS detected_et, catalyst_quality, left(catalyst, 300) AS catalyst, left(grounded_text, 400) AS grounded_head FROM mi_ep_alerts WHERE ticker='BFLY' AND alert_date='2026-06-18';

\echo '### A4 alerts since 09-01: how many have a provenance (grade) row at all — the anchor every alert would need'
SELECT count(*) AS alerts, count(*) FILTER (WHERE EXISTS (SELECT 1 FROM mi_audit_log l WHERE l.event_type='ep_catalyst_provenance' AND l.detail LIKE '%"ticker": "' || a.ticker || '"%' AND l.detail LIKE '%' || a.alert_date::text || '%')) AS with_provenance FROM mi_ep_alerts a WHERE a.alert_date >= '2026-09-01';

\echo '### A5 alerts since 09-01 by catalyst_quality (how much the population would widen if every alert were a candidate)'
SELECT catalyst_quality, count(*) FROM mi_ep_alerts WHERE alert_date >= '2026-09-01' GROUP BY 1 ORDER BY 2 DESC;
