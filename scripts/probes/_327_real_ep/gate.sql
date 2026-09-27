-- STEP 0 population gate (2026-09-26 rerun): live-source EP alerts 2026-05-01..2026-09-11, one campaign
-- per (ticker, alert_date), split into two ERAS by alert_date (the EP rules changed 2026-08-22: #533).
WITH a AS (
  SELECT DISTINCT ON (ticker, alert_date) ticker, alert_date, score_tier, gap_pct, ep_score, created_at
  FROM mi_ep_alerts
  WHERE alert_date BETWEEN DATE '2026-05-01' AND DATE '2026-09-11'
    AND COALESCE(source,'live')='live'
  ORDER BY ticker, alert_date, created_at
), pc AS (
  SELECT a.ticker, a.alert_date, a.score_tier, a.gap_pct, a.ep_score,
         CASE WHEN a.alert_date < DATE '2026-08-22' THEN 'A' ELSE 'B' END AS era,
         (SELECT d.close FROM mi_daily_closes d WHERE d.ticker=a.ticker AND d.trade_date < a.alert_date
            ORDER BY d.trade_date DESC LIMIT 1) AS prior_close
  FROM a
)
SELECT era, 'campaigns' AS k, count(*)::text AS v FROM pc GROUP BY era
UNION ALL SELECT era, 'names', count(DISTINCT ticker)::text FROM pc GROUP BY era
UNION ALL SELECT era, 'tier_'||COALESCE(score_tier,'none'), count(*)::text FROM pc GROUP BY era, score_tier
UNION ALL SELECT era, 'first_alert_date', min(alert_date)::text FROM pc GROUP BY era
UNION ALL SELECT era, 'last_alert_date', max(alert_date)::text FROM pc GROUP BY era
UNION ALL SELECT era, 'prior_close_lt5', count(*)::text FROM pc WHERE prior_close < 5 GROUP BY era
UNION ALL SELECT era, 'prior_close_null', count(*)::text FROM pc WHERE prior_close IS NULL GROUP BY era
UNION ALL SELECT era, 'median_prior_close', round(percentile_cont(0.5) WITHIN GROUP (ORDER BY prior_close)::numeric,2)::text FROM pc GROUP BY era
UNION ALL SELECT era, 'median_gap_pct', round(percentile_cont(0.5) WITHIN GROUP (ORDER BY gap_pct)::numeric,2)::text FROM pc GROUP BY era
UNION ALL SELECT era, 'has_'||ticker||'_'||alert_date, '1' FROM pc WHERE (ticker,alert_date) IN (('TEAM',DATE '2026-08-07'),('MRNA',DATE '2026-08-19'),('PLTR',DATE '2026-08-04'),('HTFL',DATE '2026-08-14'))
UNION ALL SELECT era, 'month_'||to_char(alert_date,'YYYY-MM'), count(*)::text FROM pc GROUP BY era, to_char(alert_date,'YYYY-MM')
UNION ALL SELECT 'ALL', 'campaigns', count(*)::text FROM pc
UNION ALL SELECT 'ALL', 'names', count(DISTINCT ticker)::text FROM pc
ORDER BY 1, 2;
