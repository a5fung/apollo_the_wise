\echo === ADVSCHEMA ===
SELECT column_name FROM information_schema.columns WHERE table_name='mi_stock_scores' AND column_name IN ('ticker','score_date','adv_20');
\echo === ADVRET ===
SELECT MIN(score_date), MAX(score_date), COUNT(DISTINCT score_date) FROM mi_stock_scores;
\echo === ADV ===
WITH cohort AS (
  SELECT DISTINCT ticker FROM mi_ep_alerts WHERE COALESCE(source,'live')='live'
  UNION SELECT DISTINCT ticker FROM mi_live_trades WHERE signal_type='magna53' AND status='closed'
)
SELECT s.ticker, s.score_date, s.adv_20 FROM mi_stock_scores s JOIN cohort c USING (ticker)
WHERE s.adv_20 IS NOT NULL ORDER BY s.ticker, s.score_date;
\echo === MINCOV ===
WITH cohort AS (
  SELECT DISTINCT ticker FROM mi_ep_alerts WHERE COALESCE(source,'live')='live'
  UNION SELECT DISTINCT ticker FROM mi_live_trades WHERE signal_type='magna53' AND status='closed'
)
SELECT b.ticker, (b.bar_time AT TIME ZONE 'America/New_York')::date AS d, COUNT(*) AS n
FROM mi_intraday_bars b JOIN cohort c USING (ticker)
GROUP BY 1,2 ORDER BY 1,2;
