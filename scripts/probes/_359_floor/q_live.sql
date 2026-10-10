\echo === lane signals + replays (live shadow, all to date)
SELECT s.scan_date, s.ticker, round(s.market_cap/1e6) cap_m, round(s.gap_pct::numeric,1) gap, round(s.quoted_spread_bps::numeric) spread_bps,
       round((s.quality_adv_dollar/1e6)::numeric,2) adv_m, s.blocking_filters::text, r.entry_status, r.outcome, round(r.realized_r::numeric,2) r, round(r.mark_r::numeric,2) mark, r.replay_exit_era, r.target_r
FROM mi_lowcap_lane_signals s LEFT JOIN mi_lowcap_lane_replays r ON r.signal_id = s.id ORDER BY s.scan_date, s.ticker;
\echo === tables carrying a spread / bid-ask column
SELECT table_name, string_agg(column_name, ',') FROM information_schema.columns WHERE table_schema='public' AND (column_name ILIKE '%spread%' OR column_name ILIKE 'bid_px' OR column_name ILIKE 'ask_px') GROUP BY table_name;
