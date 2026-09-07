\pset format unaligned
\pset fieldsep '\t'
\pset footer off
SELECT id, scan_date, ticker, gap_pct, regexp_replace(coalesce(filter_reason,''), E'[\\n\\r\\t]+', ' ', 'g') AS filter_reason, coalesce(score_tier,'') AS score_tier, ep_score, coalesce(reject_stage,'') AS reject_stage, scan_time_et, in_active_theme FROM mi_ep_scan_log ORDER BY scan_date, ticker, scan_time_et, id;
