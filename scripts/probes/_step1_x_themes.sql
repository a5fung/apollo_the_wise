\pset format unaligned
\pset fieldsep '\t'
\pset footer off

SELECT id, theme_date, name, stage, score, rs_avg, parent_theme, days_active, source, array_to_string(tickers, ',') AS tickers, CASE WHEN stage='Retired' THEN regexp_replace(coalesce(description,''), E'[\\n\\r\\t]+', ' ', 'g') ELSE '' END AS retired_note FROM mi_themes ORDER BY theme_date, id;
