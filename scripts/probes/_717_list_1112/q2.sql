SET default_transaction_read_only = on;
SELECT min(adr20), percentile_cont(0.5) WITHIN GROUP (ORDER BY adr20), count(*) FILTER (WHERE adr20 < 0.04) FROM mi_breakout_v1_list WHERE scan_date='2026-11-12';
SELECT count(*) FILTER (WHERE gates->'level' IS NOT NULL) , count(*) FILTER (WHERE (gates->>'level_source') = 'wick' OR gates::text ILIKE '%settled%') FROM mi_breakout_v1_list WHERE scan_date='2026-11-12';
SELECT count(*) FROM mi_trade_entries WHERE signal_type='breakout_v1' AND created_at::date >= '2026-11-12';
SELECT left(summary,160), created_at FROM mi_audit_log WHERE created_at > now() - interval '4 hours' AND summary ILIKE '%breakout v1%' ORDER BY created_at DESC LIMIT 3;
