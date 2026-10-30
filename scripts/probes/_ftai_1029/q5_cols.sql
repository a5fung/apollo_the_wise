SET default_transaction_read_only = on;
SELECT table_name, string_agg(column_name, ',' ORDER BY column_name) FROM information_schema.columns
WHERE (table_name='mi_ep_scan_log' AND column_name IN ('scan_time_et','ep_score','score_tier','score_breakdown','score_side','ep_bar','catalyst_quality','gap_pct','adv','prev_close','projected_vol_multiple','rel_volume','float_shares','vol_percentile','scan_date','ticker','id'))
   OR (table_name='mi_ep_theme_belonging_shadow' AND column_name IN ('listed','best_theme','best_stage','best_corr','shortlist','fit_status','fit_theme','fit_stage','fit_rationale','belongs_paying','reason','acting_in_theme','shortlist_bar','ticker','scan_date'))
GROUP BY 1;
