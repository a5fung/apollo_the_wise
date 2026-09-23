-- #652 READ-ONLY prod capture — run ONCE on 2026-09-18 PT (capture once, read many).
--   ssh apollo@87.99.134.162 'docker exec -i apollo-postgres psql -U apollo -d apollo' \
--       < scripts/probes/_652_capture.sql > /tmp/652_capture_out.tsv
--   python scripts/probes/_652_build_prod_corpus.py /tmp/652_capture_out.tsv scripts/probes/_652_corpus_prod.jsonl
-- SELECTs only. Real newlines/tabs come out as the 3-char sequence backslash-backslash-n/t
-- (a '...' literal keeps backslashes under standard_conforming_strings); the builder undoes it.
\pset format unaligned
\pset fieldsep '\t'
\pset tuples_only on
\o /dev/stdout
\echo ===FALLBACK_ROWS===
SELECT id, created_at, replace(replace(detail, E'\n', '\\n'), E'\t', '\\t') FROM mi_audit_log WHERE event_type IN ('telegram_markdown_fallback','telegram_send_failed') AND created_at > now() - interval '60 days' ORDER BY created_at;
\echo ===SYSREV===
SELECT id, created_at, replace(replace(summary, E'\n', '\\n'), E'\t', '\\t') FROM mi_system_reviews ORDER BY created_at;
\echo ===EPALERT_COLS===
SELECT column_name, data_type FROM information_schema.columns WHERE table_name='mi_ep_alerts' ORDER BY ordinal_position;
\echo ===GRADE_DECISION===
SELECT id, created_at, replace(replace(detail, E'\n', '\\n'), E'\t', '\\t') FROM mi_audit_log WHERE event_type='ep_grade_decision' AND created_at > now() - interval '60 days' ORDER BY created_at DESC LIMIT 60;
\echo ===ANOMALY===
SELECT id, created_at, replace(replace(detail, E'\n', '\\n'), E'\t', '\\t') FROM mi_audit_log WHERE event_type='anomaly_detected' AND created_at > now() - interval '60 days' ORDER BY created_at DESC LIMIT 40;
\echo ===GROUNDED===
SELECT id, ticker, replace(replace(left(grounded_text, 6000), E'\n', '\\n'), E'\t', '\\t') FROM mi_ep_alerts WHERE grounded_text IS NOT NULL ORDER BY id DESC LIMIT 25;
\echo ===THEME_DESC===
SELECT id, created_at, replace(replace(left(detail, 3000), E'\n', '\\n'), E'\t', '\\t') FROM mi_audit_log WHERE event_type IN ('theme_discovered','theme_auto_retired','shadow_themes_promoted','theme_merge_pairs_proposed') AND created_at > now() - interval '30 days' ORDER BY created_at DESC LIMIT 40;
