-- Find every row written on a given day carrying a date stamp from BEFORE that day.
--
-- WHY. A recovery that re-runs a missed job with the clock pinned to the missed date writes rows
-- stamped with that date, which is the whole point. But it is ALSO how fabricated history gets in,
-- and on 2026-09-20 it did: re-running `analyst_estimates_snapshot` for Friday wrote 78 rows whose
-- `as_of_date` said 2026-09-18 while `created_at` said 2026-09-20 11:02. That column is documented
-- `-- when this value was READ`, so the stamp claimed a Friday reading that never happened; the
-- values came from live vendor APIs on Sunday. Removed (exported first).
--
-- THE RULE THIS QUERY EXISTS TO APPLY, because the query finds candidates and a human decides:
--   * SUBJECT dates — `scan_date`, `session_date`, `entry_date`, `cohort_date`, `alert_date` —
--     say WHICH TRADING SESSION the row is about. Backdating them is CORRECT; it is what the date
--     pin is for. Saturday's recovery wrote ~150 such rows and every one of them is right.
--   * PROVENANCE dates — `as_of_date` on mi_analyst_estimates — say WHEN WE READ IT. Backdating
--     one is a lie, however convenient.
-- Read the column's own comment in db.py before deciding. The two look identical in a row count.
--
-- Change the two 2026-09-20 literals to the day you are auditing.
-- Run:  ssh apollo@<host> 'docker exec -i apollo-postgres psql -U apollo -d apollo -t -A -F"|"' < this_file

DO $$
DECLARE r RECORD; n BIGINT; mind DATE; maxd DATE;
BEGIN
  CREATE TEMP TABLE IF NOT EXISTS _backdated(tbl TEXT, col TEXT, rows BIGINT, min_stamp DATE, max_stamp DATE);
  FOR r IN
    SELECT c1.table_name AS t, c2.column_name AS c
    FROM information_schema.columns c1
    JOIN information_schema.columns c2 ON c2.table_name = c1.table_name
    WHERE c1.table_name LIKE 'mi\_%' AND c1.column_name='created_at' AND c2.data_type='date'
  LOOP
    BEGIN
      EXECUTE format(
        'SELECT count(*), min(%I), max(%I) FROM %I
         WHERE (created_at AT TIME ZONE ''America/New_York'')::date = DATE ''2026-09-20''
           AND %I < DATE ''2026-09-20''', r.c, r.c, r.t, r.c)
      INTO n, mind, maxd;
      IF n > 0 THEN
        INSERT INTO _backdated VALUES (r.t, r.c, n, mind, maxd);
      END IF;
    EXCEPTION WHEN OTHERS THEN NULL;
    END;
  END LOOP;
END $$;
SELECT tbl, col, rows, min_stamp, max_stamp FROM _backdated ORDER BY rows DESC;
