SET default_transaction_read_only = on;
SELECT scan_date, listed, best_theme, best_stage, round(best_corr::numeric,2) corr, n_sessions, shortlist, nascent_shortlist, fit_status, fit_theme, left(coalesce(fit_rationale,''),300) rationale, belongs_paying, reason, acting_in_theme
FROM mi_ep_theme_belonging_shadow WHERE ticker='FTAI' AND scan_date >= DATE '2026-10-27' ORDER BY scan_date DESC;
