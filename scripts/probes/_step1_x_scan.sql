\pset format unaligned
\pset fieldsep '\t'
\pset footer off

SELECT scan_date, ticker, gap_pct, filter_reason, score_tier, ep_score, reject_stage FROM mi_ep_scan_log ORDER BY scan_date, ticker;
