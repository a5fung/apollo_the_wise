SET default_transaction_read_only = on;
SELECT scan_date, ticker, live_quality_last, shadow_tier_last, rule_last, regrade_count FROM mi_catalyst_tier_shadow
 WHERE scan_date BETWEEN DATE '2026-11-23' AND DATE '2026-11-27' ORDER BY scan_date, ticker;
