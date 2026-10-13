-- #697 item 2 VERIFY-LIVE (htf.md change log 2026-10-11). READ-ONLY. One scan date D per run:
--   ssh apollo@87.99.134.162 "docker exec -i apollo-postgres psql -U apollo -d apollo -A -F \$'\t' -v d=2026-10-12" \
--       < scripts/probes/_697/verify_carry_live.sql > <out>
-- Session definition = the SHIPPED one (db.get_flag_universe path (e)): scan dates with bars in mi_daily_closes, the
-- 5 most recent before D, inside a 60-calendar-day cap. NOT calendar days (that was the bug).
--   a_long_tag_rows     (a) rows whose universe_sources hold `flag_pivot_window_carryforward`. The OLD code never wrote
--                       that tag, so >= 1 is a positive observable of the NEW code (replay: 6-20 a night, ~10 predicted).
--                       The old `flag_stage_carryforward` tag does NOT tell new from old (old code: 0-4 carry-only rows
--                       on 36 of 48 nights), so it is not the pass criterion.
--   c_carry_only_rows   (c) rows kept ONLY by a carry (carry tag, no organic / R3 / 9M tag). ALARM above 30 (replay 7-19 a night;
--                       26 would be every carried name on 10-12, where no stored rows exist yet).
--   c_carry_only_stage  the same rows by stage - expect a few INVALIDATED / unqualified (the telemetry #654 needs).
--   b_violator          (b) tickers with a stored WATCH / TIGHTENING / COILED / TRIGGERED row in the last 5 sessions and
--                       NO row on D. Must be EMPTY - after dropping names with NO BAR on D (not scored by design) and with
--                       < 60 bars total (the scan skips them). A logged `flag_scan: <T> failed` (container log) also
--                       excuses a name: `docker logs apollo-market-agent 2>&1 | grep "flag_scan: <T> failed"`.
--   An EMPTY violator set on ONE night is NOT proof: the OLD code's set was empty on 8 of 48 nights (08-04 -> 10-09).
--   Read it with (a): a night passes only when (a) >= 1 AND (b) is empty AND (c) <= 30.
SET default_transaction_read_only = on;
\pset footer off
WITH sess AS (
  SELECT DISTINCT c.scan_date FROM mi_flag_candidates c
  WHERE c.scan_date < :'d'::date AND c.scan_date >= :'d'::date - 60
    AND EXISTS (SELECT 1 FROM mi_daily_closes dc WHERE dc.trade_date = c.scan_date)
),
last5 AS (SELECT scan_date FROM sess ORDER BY scan_date DESC LIMIT 5),
stored AS (
  SELECT DISTINCT ON (c.ticker) c.ticker, c.stage, c.scan_date
  FROM mi_flag_candidates c JOIN last5 l ON l.scan_date = c.scan_date
  WHERE c.stage IN ('WATCH', 'TIGHTENING', 'COILED', 'TRIGGERED')
  ORDER BY c.ticker, c.scan_date DESC
),
today AS (
  SELECT ticker, stage, universe_sources AS us FROM mi_flag_candidates WHERE scan_date = :'d'::date
),
org AS (
  SELECT ARRAY['rs_top200', 'rs_1m_80', 'momentum_25pct', 'magna53_failed_r3', 'ninem_universe_watch']::text[] AS a,
         ARRAY['flag_stage_carryforward', 'flag_pivot_window_carryforward']::text[] AS carry
)
SELECT 'rows_on_d' k, COUNT(*)::text a, NULL::text b, NULL::text c FROM today
UNION ALL
SELECT 'a_long_tag_rows', COUNT(*)::text, NULL, NULL
FROM today WHERE us @> ARRAY['flag_pivot_window_carryforward']::text[]
UNION ALL
SELECT 'c_carry_only_rows', COUNT(*)::text, NULL, NULL
FROM today, org WHERE us && org.carry AND NOT us && org.a
UNION ALL
SELECT 'c_carry_only_stage', stage, COUNT(*)::text, NULL
FROM today, org WHERE us && org.carry AND NOT us && org.a GROUP BY stage
UNION ALL
SELECT 'b_violator', s.ticker, s.stage || '@' || s.scan_date::text,
       (SELECT COUNT(*)::text FROM mi_daily_closes d WHERE d.ticker = s.ticker AND d.trade_date <= :'d'::date)
FROM stored s
WHERE NOT EXISTS (SELECT 1 FROM today t WHERE t.ticker = s.ticker)
  AND EXISTS (SELECT 1 FROM mi_daily_closes dc WHERE dc.ticker = s.ticker AND dc.trade_date = :'d'::date)
  AND (SELECT COUNT(*) FROM mi_daily_closes d WHERE d.ticker = s.ticker AND d.trade_date <= :'d'::date) >= 60
ORDER BY 1, 2;
