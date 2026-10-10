CREATE TEMP TABLE d AS SELECT DISTINCT scan_date FROM mi_ep_scan_log WHERE scan_date < '2026-10-10' ORDER BY scan_date DESC LIMIT 30;
\echo === score-ladder ADV$ (adv x prev_close) : sub-500M mcap-rejected
SELECT CASE WHEN a IS NULL THEN 'null' WHEN a < 5e7 THEN 'under 50M (0 liquidity pts)' WHEN a < 1e8 THEN '50-100M' ELSE '>=100M' END bucket, count(*) FROM (
 SELECT scan_date, ticker, max(adv*prev_close) a FROM mi_ep_scan_log WHERE scan_date IN (SELECT scan_date FROM d) AND reject_stage='quality_filter' AND filter_reason ILIKE '%mcap_too_small%' GROUP BY 1,2) t GROUP BY 1 ORDER BY 1;
\echo === score-ladder ADV$ : live graded, with HIGH count and score stats
SELECT CASE WHEN a IS NULL THEN 'null' WHEN a < 5e7 THEN 'under 50M (0 liquidity pts)' WHEN a < 1e8 THEN '50-100M' ELSE '>=100M' END bucket, count(*), count(*) FILTER (WHERE hi) high, round(avg(sc)::numeric,1) avg_best_score, max(sc) max_score FROM (
 SELECT s.scan_date, s.ticker, max(s.adv*s.prev_close) a, bool_or(s.score_tier='HIGH') hi, max(s.ep_score) sc FROM mi_ep_scan_log s WHERE s.scan_date IN (SELECT scan_date FROM d) GROUP BY 1,2 HAVING bool_or(s.llm_catalyst_quality IS NOT NULL)) t GROUP BY 1 ORDER BY 1;
\echo === live HIGH alerts (90d) whose prior-day market cap < 1B, for context
SELECT count(*) FROM mi_ep_scan_log s WHERE s.scan_date >= '2026-07-01' AND s.score_tier='HIGH' AND s.market_cap < 1e9;
