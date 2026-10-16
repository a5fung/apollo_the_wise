-- #598 close verifier 10-16 (read-only). Re-derive from raw tables.
SELECT '=== A: flag_stage_transition (+error) since 10-03 ===' AS x;
SELECT created_at AT TIME ZONE 'America/New_York' AS et, event_type, summary, LEFT(detail,700) AS detail
FROM mi_audit_log
WHERE event_type IN ('flag_stage_transition','flag_stage_transition_error') AND created_at >= '2026-10-03'
ORDER BY created_at;
SELECT '=== B: flag_digest_sent (+error) since 10-03 ===' AS x;
SELECT created_at AT TIME ZONE 'America/New_York' AS et, event_type, summary, LEFT(detail,500) AS detail
FROM mi_audit_log
WHERE event_type IN ('flag_digest_sent','flag_digest_sent_error') AND created_at >= '2026-10-03'
ORDER BY created_at;
SELECT '=== C: scan dates + stage counts since 10-03 ===' AS x;
SELECT scan_date, stage, count(*) n FROM mi_flag_candidates WHERE scan_date >= '2026-10-03' GROUP BY 1,2 ORDER BY 1,2;
SELECT '=== D: TIGHTENING/COILED/TRIGGERED rows since 10-03 ===' AS x;
SELECT scan_date, ticker, stage, base_age, round(runup_pct::numeric,3) runup, pivot_high_price pivot,
       round(range_contraction_ratio::numeric,2) rng, round(vol_contraction_ratio::numeric,2) vol, held_from_stage
FROM mi_flag_candidates WHERE scan_date >= '2026-10-03' AND stage IN ('TIGHTENING','COILED','TRIGGERED')
ORDER BY scan_date, stage, ticker;
SELECT '=== E: flag-detector mna_filter_fired since 10-04 (summary carries (flag)) ===' AS x;
SELECT created_at AT TIME ZONE 'America/New_York' AS et, summary, LEFT(detail,500) AS detail
FROM mi_audit_log WHERE event_type='mna_filter_fired' AND created_at >= '2026-10-04' AND summary LIKE '%(flag)%'
ORDER BY created_at;
SELECT '=== F: all mna_filter_fired since 10-04 by detector tag (control) ===' AS x;
SELECT substring(summary from '\(([a-z_]+)\)') tag, count(*) n, max(created_at AT TIME ZONE 'America/New_York') last_et
FROM mi_audit_log WHERE event_type='mna_filter_fired' AND created_at >= '2026-10-04' GROUP BY 1 ORDER BY 1;
SELECT '=== G: flag rows demoted by the screen since 10-04 (persisted side) ===' AS x;
SELECT scan_date, ticker, stage, reason FROM mi_flag_candidates
WHERE scan_date >= '2026-10-04' AND reason LIKE 'mna_filter:%' ORDER BY scan_date, ticker;
SELECT '=== H: latest scan date + now ===' AS x;
SELECT max(scan_date) last_scan, now() AT TIME ZONE 'America/New_York' now_et FROM mi_flag_candidates;
