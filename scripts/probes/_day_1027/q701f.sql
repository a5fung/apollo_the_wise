SET default_transaction_read_only = on;
SELECT scan_time_et, ep_score, score_tier, catalyst_quality, llm_catalyst_quality, filter_reason, reject_stage, ep_bar FROM mi_ep_scan_log WHERE ticker='MFIC' AND scan_date='2026-10-27' ORDER BY created_at;
