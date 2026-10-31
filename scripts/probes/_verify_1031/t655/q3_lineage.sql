SET default_transaction_read_only = on;
\echo == renames touching the 177 target or its successor
SELECT * FROM mi_theme_renames WHERE old_name ILIKE '%Digital Credit%' OR new_name ILIKE '%Digital Credit%' OR old_name ILIKE '%Re-rating on Fed Easing%' OR new_name ILIKE '%Re-rating on Fed Easing%' ORDER BY 1;
\echo == members on the last target day vs the successor's first day
SELECT theme_date, name, tickers FROM mi_themes WHERE (name = 'Consumer Fintech & Digital Credit Platforms' AND theme_date = '2026-09-16') OR (name = 'Fintech & Digital Finance Sector Re-rating on Fed Easing' AND theme_date = '2026-09-17');
