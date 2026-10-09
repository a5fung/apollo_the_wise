SELECT table_name, column_name, data_type FROM information_schema.columns
 WHERE table_name IN ('mi_ep_scan_log','mi_ep_shortlist_shadow','mi_stock_scores') ORDER BY table_name, ordinal_position;
