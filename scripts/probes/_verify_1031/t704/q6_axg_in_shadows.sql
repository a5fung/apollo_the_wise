SET default_transaction_read_only = on;
SELECT 'mi_consolidation_breakout_entry' AS tbl, count(*) FROM mi_consolidation_breakout_entry WHERE ticker='AXG';
SELECT 'mi_consolidation_breakout_watch' AS tbl, count(*) FROM mi_consolidation_breakout_watch WHERE ticker='AXG';
SELECT 'mi_consolidation_entry_shadow' AS tbl, count(*) FROM mi_consolidation_entry_shadow WHERE ticker='AXG';
SELECT 'mi_htf_breakout_shadow' AS tbl, count(*) FROM mi_htf_breakout_shadow WHERE ticker='AXG';
SELECT 'mi_htf_management_shadow' AS tbl, count(*) FROM mi_htf_management_shadow WHERE ticker='AXG';
SELECT 'mi_parabolic_short_shadow' AS tbl, count(*) FROM mi_parabolic_short_shadow WHERE ticker='AXG';
