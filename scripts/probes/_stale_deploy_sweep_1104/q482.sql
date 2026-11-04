SET default_transaction_read_only = on;
-- Q1 every MAGNA53 fill through yesterday ET has recorder rows (the discriminator)
SELECT t.account_mode, COUNT(*) AS fills,
       COUNT(*) FILTER (WHERE EXISTS (SELECT 1 FROM mi_live_fill_counterfactuals c WHERE c.trade_id = t.id)) AS recorded,
       string_agg(t.id::text || ':' || t.ticker, ',') FILTER (WHERE NOT EXISTS (SELECT 1 FROM mi_live_fill_counterfactuals c WHERE c.trade_id = t.id)) AS unrecorded,
       MAX((t.filled_at AT TIME ZONE 'America/New_York')::date) AS last_fill_et
FROM mi_live_trades t
WHERE t.signal_type = 'magna53' AND t.filled_at IS NOT NULL
  AND (t.filled_at AT TIME ZONE 'America/New_York')::date >= DATE '2026-08-16'
  AND (t.filled_at AT TIME ZONE 'America/New_York')::date < (now() AT TIME ZONE 'America/New_York')::date
GROUP BY t.account_mode;
-- Q2 CLOSED trades missing rows that must exist: no live_actual row, or past the 40-session horizon (~60 cal days) with < 12 original arms
SELECT t.id, t.ticker, (t.filled_at AT TIME ZONE 'America/New_York')::date AS fill_et,
       COUNT(DISTINCT c.arm) FILTER (WHERE c.arm NOT IN ('entry_first_hour_bar','stop_low_of_day','book_first_hour_low_of_day','fill_facts')) AS orig_arms,
       COALESCE(BOOL_OR(c.arm = 'live_actual'), false) AS has_live_actual
FROM mi_live_trades t
LEFT JOIN mi_live_fill_counterfactuals c ON c.trade_id = t.id
WHERE t.signal_type = 'magna53' AND t.status = 'closed' AND t.filled_at IS NOT NULL
  AND (t.filled_at AT TIME ZONE 'America/New_York')::date >= DATE '2026-08-16'
  AND (t.closed_at AT TIME ZONE 'America/New_York')::date < (now() AT TIME ZONE 'America/New_York')::date
GROUP BY t.id, t.ticker, t.filled_at
HAVING NOT COALESCE(BOOL_OR(c.arm = 'live_actual'), false)
    OR (t.filled_at < now() - interval '60 days'
        AND COUNT(DISTINCT c.arm) FILTER (WHERE c.arm NOT IN ('entry_first_hour_bar','stop_low_of_day','book_first_hour_low_of_day','fill_facts')) < 12)
ORDER BY t.id LIMIT 20;
-- Q3 the DONE-WHEN count (distinct trades) split by exit era; the NULL row is the total
SELECT exit_era, COUNT(DISTINCT trade_id) AS trades,
       COUNT(DISTINCT trade_id) FILTER (WHERE arm = 'live_actual' AND outcome = 'settled') AS live_actual_settled
FROM mi_live_fill_counterfactuals
WHERE signal_type = 'magna53'
GROUP BY ROLLUP (exit_era) ORDER BY exit_era NULLS LAST;
-- Q4 the entry-geometry re-run gate (bracket_geometry_variants_parked predicate, verbatim)
SELECT COUNT(*) AS closed_live_magna53_since_0817 FROM mi_live_trades
WHERE account_mode = 'live' AND signal_type = 'magna53' AND status = 'closed' AND alert_date >= DATE '2026-08-17';