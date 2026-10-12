\echo == live-fill counterfactuals: shape
SELECT count(*) AS rows, count(mark_r) AS mark_r_nonnull, count(*) FILTER (WHERE outcome='horizon') AS horizon_rows, min(recorded_at AT TIME ZONE 'America/New_York')::date AS first_row, max(recorded_at AT TIME ZONE 'America/New_York')::date AS last_row, min(fill_day) AS min_fill_day, max(fill_day) AS max_fill_day, max(sessions_walked) AS max_sessions_walked FROM mi_live_fill_counterfactuals;
\echo == fills still under 12 arms (the in-flight population the nightly walks)
SELECT t.id, t.ticker, t.account_mode, t.status, (t.filled_at AT TIME ZONE 'America/New_York')::date AS fill_day, (SELECT count(*) FROM mi_live_fill_counterfactuals c WHERE c.trade_id=t.id) AS arms_written FROM mi_live_trades t WHERE t.signal_type='magna53' AND t.filled_at IS NOT NULL AND (t.filled_at AT TIME ZONE 'America/New_York')::date >= '2026-08-16' AND (SELECT count(*) FROM mi_live_fill_counterfactuals c WHERE c.trade_id=t.id) < 12 ORDER BY t.filled_at;
\echo == fills per fill_day with arms written and max sessions walked
SELECT fill_day, count(DISTINCT trade_id) trades, count(*) arms, max(sessions_walked) max_walk FROM mi_live_fill_counterfactuals GROUP BY 1 ORDER BY 1 LIMIT 12;
\echo == oldest fills: arms by outcome
SELECT trade_id, ticker, fill_day, outcome, count(*), max(sessions_walked) FROM mi_live_fill_counterfactuals WHERE fill_day <= '2026-09-01' GROUP BY 1,2,3,4 ORDER BY fill_day, trade_id;
\echo == nightly counterfactual job events last 10 days
SELECT created_at AT TIME ZONE 'America/New_York' AS t_et, event_type, left(summary,260) FROM mi_audit_log WHERE event_type LIKE 'live_fill_counterfactual%' AND created_at >= now() - interval '10 days' ORDER BY created_at DESC LIMIT 12;
\echo == any dead_column_suspect/detected for market_cap or mark_r
SELECT created_at AT TIME ZONE 'America/New_York' AS t_et, event_type, summary FROM mi_audit_log WHERE event_type LIKE 'dead_column%' AND (summary LIKE '%market_cap%' OR summary LIKE '%mark_r%') ORDER BY created_at;
\echo == RS upsert / score errors since 10-09
SELECT created_at AT TIME ZONE 'America/New_York' AS t_et, event_type, left(summary,200) FROM mi_audit_log WHERE created_at >= '2026-10-09 12:00:00-04' AND (event_type ILIKE '%stock_score%' OR event_type ILIKE '%rs_run%' OR event_type ILIKE '%upsert%') ORDER BY created_at DESC LIMIT 10;
