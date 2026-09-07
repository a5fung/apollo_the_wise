\pset format unaligned
\pset fieldsep '\t'
\pset footer off

SELECT ticker, alert_date, stratum, operator_label, regexp_replace(coalesce(operator_note,''), E'[\\n\\r\\t]+', ' ', 'g') AS operator_note FROM mi_theme_relevance_cohort ORDER BY alert_date, ticker;
