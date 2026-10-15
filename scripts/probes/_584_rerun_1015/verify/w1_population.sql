-- ADVERSARIAL VERIFY 2026-10-15 (read-only). Population integrity checks on mi_universe_floor_shadow + mi_daily_closes.
BEGIN READ ONLY;
\echo === W1a: base counts (scan_date <= 10-14), NULL-safe side split
SELECT count(*) rows_, count(DISTINCT ticker) names, count(DISTINCT scan_date) dates,
  count(*) FILTER (WHERE failed_price_floor IS NULL OR failed_volume_floor IS NULL) null_flags,
  count(*) FILTER (WHERE COALESCE(failed_price_floor,false) OR COALESCE(failed_volume_floor,false)) rej_rows,
  count(DISTINCT ticker) FILTER (WHERE COALESCE(failed_price_floor,false) OR COALESCE(failed_volume_floor,false)) rej_names,
  count(*) FILTER (WHERE failed_price_floor AND failed_volume_floor) pv, count(*) FILTER (WHERE failed_price_floor AND NOT failed_volume_floor) p_only,
  count(*) FILTER (WHERE failed_volume_floor AND NOT failed_price_floor) v_only
FROM mi_universe_floor_shadow WHERE scan_date <= '2026-10-14';
\echo === W1b: rows whose created_at / first_seen / last_seen ET date differs from scan_date (backfill / test / replay rows)
SELECT count(*) FILTER (WHERE (created_at AT TIME ZONE 'America/New_York')::date <> scan_date) created_mismatch,
  count(*) FILTER (WHERE (first_seen_et AT TIME ZONE 'America/New_York')::date <> scan_date) first_mismatch,
  count(*) FILTER (WHERE (last_seen_et AT TIME ZONE 'America/New_York')::date <> scan_date) last_mismatch,
  count(*) FILTER (WHERE created_at IS NULL) created_null,
  min((created_at AT TIME ZONE 'America/New_York')::time) min_created_time, max((created_at AT TIME ZONE 'America/New_York')::time) max_created_time,
  max((last_seen_et AT TIME ZONE 'America/New_York')::time) max_last_seen_time
FROM mi_universe_floor_shadow WHERE scan_date <= '2026-10-14';
\echo === W1c: suspicious tickers (test-like / non-standard symbols)
SELECT ticker, count(*) FROM mi_universe_floor_shadow WHERE scan_date <= '2026-10-14'
  AND (ticker !~ '^[A-Z]{1,5}$' OR ticker ILIKE '%TEST%' OR ticker IN ('ZZZZ','XXXX','AAAA','FAKE','DUMMY')) GROUP BY 1 ORDER BY 2 DESC LIMIT 40;
\echo === W1d: slot consistency
SELECT count(*) FILTER (WHERE today_dollar_volume_at_open IS NOT NULL AND minutes_since_open_at_open IS NULL) dv_without_min,
  count(*) FILTER (WHERE minutes_since_open_at_open IS NOT NULL AND today_dollar_volume_at_open IS NULL) min_without_dv,
  count(*) FILTER (WHERE today_dollar_volume_at_open IS NOT NULL AND abs(today_dollar_volume_at_open - today_volume_at_open*today_price_at_open) > 1) dv_ne_pxv,
  count(*) FILTER (WHERE today_dollar_volume_at_open IS NULL AND minutes_since_open_last <= 15) fallback_eligible,
  count(*) FILTER (WHERE minutes_since_open_at_open < 0 OR minutes_since_open_at_open > 390) bad_minutes
FROM mi_universe_floor_shadow WHERE scan_date <= '2026-10-14';
\echo === W1e: at_open minute mix x side
SELECT (COALESCE(failed_price_floor,false) OR COALESCE(failed_volume_floor,false)) rej, minutes_since_open_at_open m, count(*)
FROM mi_universe_floor_shadow WHERE scan_date <= '2026-10-14' GROUP BY 1,2 ORDER BY 1,2;
\echo === W1f: acting floors in window
SELECT acting_price_floor, acting_volume_floor, count(*) FROM mi_universe_floor_shadow WHERE scan_date <= '2026-10-14' GROUP BY 1,2;
\echo === W1g: mi_daily_closes duplicate (ticker,trade_date) among shadow tickers 06-01..10-14
SELECT count(*) dup_keys FROM (SELECT ticker, trade_date FROM mi_daily_closes WHERE trade_date BETWEEN '2026-06-01' AND '2026-10-14'
  AND ticker IN (SELECT DISTINCT ticker FROM mi_universe_floor_shadow WHERE scan_date <= '2026-10-14') GROUP BY 1,2 HAVING count(*)>1) d;
\echo === W1h: calendar dates with thin coverage (<5000 rows) 06-01..10-14
SELECT trade_date, count(*) FROM mi_daily_closes WHERE trade_date BETWEEN '2026-06-01' AND '2026-10-14' GROUP BY 1 HAVING count(*) < 5000 ORDER BY 1;
\echo === W1i: splits for shadow tickers 09-01..10-15 NOT applied
SELECT ticker, execution_date, split_from, split_to, adjustment_applied, applied_at FROM mi_splits
WHERE execution_date BETWEEN '2026-09-01' AND '2026-10-15' AND NOT COALESCE(adjustment_applied,false)
  AND ticker IN (SELECT DISTINCT ticker FROM mi_universe_floor_shadow WHERE scan_date <= '2026-10-14') ORDER BY 2,1;
\echo === W1j: mi_daily_closes last date + now
SELECT max(trade_date) last_close, now() AT TIME ZONE 'America/New_York' now_et FROM mi_daily_closes;
ROLLBACK;
