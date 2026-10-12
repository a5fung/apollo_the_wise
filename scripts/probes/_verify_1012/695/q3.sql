\echo == SELECT-only emulation of the dead-column sweep as of now (numeric cols, tables >=30 rows, zero non-null)
DO $$
DECLARE t text; c text; n bigint; nn bigint; scanned int := 0;
BEGIN
  FOR t IN SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE' AND (table_name LIKE 'mi\_%' OR table_name LIKE 'crypto\_%') ORDER BY table_name LOOP
    EXECUTE format('SELECT count(*) FROM %I', t) INTO n;
    IF n < 30 THEN CONTINUE; END IF;
    scanned := scanned + 1;
    FOR c IN SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=t AND data_type IN ('double precision','numeric','real','integer','bigint','smallint') LOOP
      EXECUTE format('SELECT count(%I) FROM %I', c, t) INTO nn;
      IF nn = 0 THEN RAISE NOTICE 'ALL-NULL: %.% (% rows)', t, c, n; END IF;
    END LOOP;
  END LOOP;
  RAISE NOTICE 'tables scanned: %', scanned;
END $$;
\echo == event-gated predicates now
SELECT 'live_fill.mark_r horizon rows' k, count(*) FROM mi_live_fill_counterfactuals WHERE outcome='horizon'
UNION ALL SELECT 'gap_near_miss open/horizon', count(*) FROM mi_gap_near_miss_replays WHERE outcome IN ('open','horizon')
UNION ALL SELECT 'gap_near_miss mark_r nonnull', count(mark_r) FROM mi_gap_near_miss_replays;
\echo == which arms of the oldest in-flight fills are unwritten
SELECT t.id, t.ticker, (t.filled_at AT TIME ZONE 'America/New_York')::date fill_day, t.status, string_agg(c.arm, ',' ORDER BY c.arm) written FROM mi_live_trades t LEFT JOIN mi_live_fill_counterfactuals c ON c.trade_id=t.id WHERE t.id IN (382,396,400,404,409,414,419) GROUP BY 1,2,3,4 ORDER BY 3;
\echo == mi_live_trades closed_at / exits for the in-flight fills
SELECT id, ticker, status, closed_at AT TIME ZONE 'America/New_York' closed_et, exit_rule FROM mi_live_trades WHERE id IN (382,396,400,404,409,414,419) ORDER BY id;
