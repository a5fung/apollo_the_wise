\echo == STRATEGIES
SELECT strategy_id, name, signal_type, phase, enabled, live_real_enabled, position_size_multiplier, profit_trigger_r, breakeven_arm_r FROM mi_strategies ORDER BY strategy_id;

\echo == FILLS BY SIGNAL TYPE / MODE / STATUS
SELECT signal_type, account_mode, status, count(*) AS n
FROM mi_live_trades WHERE filled_at IS NOT NULL
GROUP BY 1,2,3 ORDER BY 1,2,3;

\echo == EVERY FILLED MAGNA53-family TRADE (live + paper)
SELECT id, ticker, signal_type, account_mode, status, filled_at::date AS filled, entry_shares, remaining_shares,
       entry_price, orb_low, hard_stop, stop_price, highest_price_seen,
       round((entry_price + 8*(entry_price - orb_low))::numeric, 4) AS tgt8r,
       (highest_price_seen >= entry_price + 8*(entry_price - orb_low)) AS reached_8r,
       partial_taken, breakeven_active, jsonb_array_length(COALESCE(exits::jsonb,'[]'::jsonb)) AS n_exits
FROM mi_live_trades
WHERE filled_at IS NOT NULL AND signal_type LIKE 'magna53%'
ORDER BY filled_at;

\echo == SHARE-COUNT DISTRIBUTION (entry_shares) FOR MAGNA53-family FILLS
SELECT account_mode, entry_shares, count(*) AS n,
       count(*) FILTER (WHERE highest_price_seen >= entry_price + 8*(entry_price - orb_low)) AS reached_8r
FROM mi_live_trades
WHERE filled_at IS NOT NULL AND signal_type LIKE 'magna53%'
GROUP BY 1,2 ORDER BY 1,2;

\echo == ALL-STRATEGY SHARE-COUNT DISTRIBUTION (any signal type) 1/2 shares
SELECT signal_type, account_mode, entry_shares, count(*) FROM mi_live_trades
WHERE filled_at IS NOT NULL AND entry_shares <= 2 GROUP BY 1,2,3 ORDER BY 1,2,3;

\echo == AUDIT EVENTS: profit trigger / partial exit / too_small
SELECT event_type, count(*) FROM mi_audit_log
WHERE event_type IN ('profit_trigger_fired','profit_trigger_failed','partial_exit_started','partial_exit_committed','partial_exit_aborted','partial_exit_paused')
GROUP BY 1 ORDER BY 1;
SELECT count(*) AS rows_mentioning_too_small FROM mi_audit_log WHERE event_type ILIKE '%too_small%' OR details::text ILIKE '%too_small_to_split%' OR message ILIKE '%too_small_to_split%';
