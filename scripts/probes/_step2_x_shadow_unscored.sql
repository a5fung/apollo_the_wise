\pset format unaligned
\pset fieldsep '\t'
\pset footer off
-- Run ONCE after step 4's recorder + backfill are deployed (source/reject_stage columns exist on prod).
-- Feeds: python3 scripts/probes/_step2_theme_recall.py --control-source shadow
SELECT ticker, alert_date, source, coalesce(reject_stage,'') AS reject_stage, ep_score, themeless_flag, theme_name, theme_name_7d, theme_stage_7d FROM mi_theme_axis_shadow WHERE source = 'eod_unscored' ORDER BY alert_date, ticker;
