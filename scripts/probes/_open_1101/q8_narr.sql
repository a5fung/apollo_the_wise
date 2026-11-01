SET default_transaction_read_only = on;
SELECT COUNT(*) FROM mi_theme_candidates_shadow WHERE source = 'narrative_cogap' AND run_date > (CURRENT_DATE - 30);
SELECT MAX(run_date), COUNT(*) FROM mi_theme_candidates_shadow WHERE source = 'narrative_cogap';
