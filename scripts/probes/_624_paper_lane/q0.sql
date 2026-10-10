SELECT table_name, column_name FROM information_schema.columns WHERE column_name IN ('market_cap','marketcap','mcap') ORDER BY 1;
SELECT column_name, data_type FROM information_schema.columns WHERE table_name='mi_ep_scan_log' ORDER BY ordinal_position;
SELECT column_name FROM information_schema.columns WHERE table_name='mi_strategies' ORDER BY ordinal_position;
SELECT * FROM mi_strategies WHERE strategy_id IN ('magna53','magna53_lowcap');
SELECT caller, model, count(*), round(sum(cost_usd)::numeric,2) cost, round(avg(input_tokens)) in_t, round(avg(output_tokens)) out_t, round(avg(cache_read)) cr FROM api_usage WHERE created_at >= now() - interval '45 days' GROUP BY 1,2 ORDER BY cost DESC;
