-- #697 item 1: (a) when did a FLAG-sourced row last land in a stored Friday watchlist, (b) the latest scan's
-- COILED / TIGHTENING rows with the columns the Friday renderer needs (the three fresh-tight columns), and
-- (c) the mi_strategies row the old gate read. READ-ONLY, captured once -> q3_friday_flag.out
SELECT 'flag_weeks' k, week_ending::text a, COUNT(*)::text b, string_agg(ticker, ' ' ORDER BY ticker) c, NULL d, NULL e, NULL f, NULL g, NULL h, NULL i
FROM mi_weekly_watchlists WHERE sources::text LIKE '%FLAG%' AND week_ending >= '2026-06-01' GROUP BY week_ending
UNION ALL
SELECT 'weeks_all', week_ending::text, COUNT(*)::text, NULL, NULL, NULL, NULL, NULL, NULL, NULL
FROM mi_weekly_watchlists WHERE week_ending >= '2026-07-10' GROUP BY week_ending
UNION ALL
SELECT 'strategy', strategy_id, phase, enabled::text, NULL, NULL, NULL, NULL, NULL, NULL
FROM mi_strategies WHERE strategy_id = 'flag_continuation'
UNION ALL
SELECT 'board', scan_date::text, ticker, stage, base_age::text, round(range_contraction_ratio::numeric,3)::text,
       round(vol_contraction_ratio::numeric,3)::text, fresh_tight_fires::text, round(fresh_2bar_tr_pct::numeric,3)::text, round(atr14_pct::numeric,3)::text
FROM mi_flag_candidates
WHERE scan_date = (SELECT MAX(scan_date) FROM mi_flag_candidates) AND stage IN ('COILED','TIGHTENING')
UNION ALL
SELECT 'board_count', scan_date::text, stage, COUNT(*)::text, NULL, NULL, NULL, NULL, NULL, NULL
FROM mi_flag_candidates
WHERE scan_date >= '2026-10-02' GROUP BY scan_date, stage
ORDER BY 1, 2, 3;
