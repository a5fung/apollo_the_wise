-- verify #694: does any logged field record the live theme membership on May/Jun/Jul/Aug crowded boards (before in_active_theme was logged 08-29)? Read-only.
\echo '### V6a score_breakdown keys present on graded pool-day rows before 2026-08-29 (sample counts)'
SELECT k, count(*) FROM mi_ep_scan_log, jsonb_object_keys(score_breakdown) k
 WHERE scan_date BETWEEN '2026-05-01' AND '2026-08-28' AND score_breakdown IS NOT NULL GROUP BY k ORDER BY 2 DESC LIMIT 40;
\echo '### V6b theme-ish fields in score_breakdown on 2026-05-05..2026-08-07 crowded-day graded rows, one per ticker-day'
SELECT DISTINCT ON (scan_date, ticker) scan_date, ticker,
       score_breakdown->'theme_bonus' tb, score_breakdown->'in_active_theme' iat, score_breakdown->'R4' r4, score_breakdown->'theme' th
  FROM mi_ep_scan_log
 WHERE scan_date IN ('2026-05-05','2026-05-06','2026-05-07','2026-05-08','2026-05-11','2026-05-13','2026-05-14','2026-05-26','2026-05-28','2026-07-30','2026-08-04','2026-08-05','2026-08-07')
   AND score_breakdown IS NOT NULL
 ORDER BY scan_date, ticker, scan_time_et DESC;
\echo '### V6c mi_ep_alerts in_active_theme on those days (alerts carry the flag)'
SELECT column_name FROM information_schema.columns WHERE table_name='mi_ep_alerts' AND column_name ILIKE '%theme%';
