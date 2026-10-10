CREATE TEMP TABLE d AS SELECT DISTINCT scan_date FROM mi_ep_scan_log WHERE scan_date < '2026-10-10' ORDER BY scan_date DESC LIMIT 30;
\echo === ADV$ of mcap-rejected ticker-days (median ADV$ used by the score ladder)
SELECT width_bucket(max(quality_adv_dollar), ARRAY[1e6,5e6,1e7,5e7,1e8]) b, count(*) FROM (
 SELECT scan_date, ticker, max(quality_adv_dollar) quality_adv_dollar FROM mi_ep_scan_log WHERE scan_date IN (SELECT scan_date FROM d) AND reject_stage='quality_filter' AND filter_reason ILIKE '%mcap_too_small%' GROUP BY 1,2) t GROUP BY scan_date, ticker HAVING true LIMIT 0;
SELECT CASE WHEN a < 5e6 THEN 'a <5M' WHEN a < 1e7 THEN 'b 5-10M' WHEN a < 5e7 THEN 'c 10-50M' ELSE 'd >=50M' END bucket, count(*) FROM (
 SELECT scan_date, ticker, max(quality_adv_dollar) a FROM mi_ep_scan_log WHERE scan_date IN (SELECT scan_date FROM d) AND reject_stage='quality_filter' AND filter_reason ILIKE '%mcap_too_small%' GROUP BY 1,2) t GROUP BY 1 ORDER BY 1;
\echo === same for live graded names
SELECT CASE WHEN a IS NULL THEN 'null' WHEN a < 5e6 THEN 'a <5M' WHEN a < 1e7 THEN 'b 5-10M' WHEN a < 5e7 THEN 'c 10-50M' ELSE 'd >=50M' END bucket, count(*), count(*) FILTER (WHERE hi) high FROM (
 SELECT s.scan_date, s.ticker, max(s.quality_adv_dollar) a, bool_or(s.score_tier='HIGH') hi FROM mi_ep_scan_log s WHERE s.scan_date IN (SELECT scan_date FROM d) GROUP BY 1,2 HAVING bool_or(s.llm_catalyst_quality IS NOT NULL)) t GROUP BY 1 ORDER BY 1;
