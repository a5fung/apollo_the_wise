-- READ-ONLY. TEAM is on the long-carry list tonight (last TIGHTENING+ label 2026-09-24, session lag 13) but was NOT on 10-12's (lag 12).
-- Was it a bar gap on 10-12 (excused by design) or a missed carry?
SET default_transaction_read_only = on;
SET statement_timeout = '30s';
\echo '== 1. TEAM flag rows 2026-09-22 .. 2026-10-13'
SELECT scan_date, stage, held_from_stage, universe_sources, left(reason,60) reason FROM mi_flag_candidates WHERE ticker='TEAM' AND scan_date >= DATE '2026-09-22' ORDER BY scan_date;
\echo '== 2. TEAM bars in mi_daily_closes 2026-10-05 .. 2026-10-13'
SELECT trade_date FROM mi_daily_closes WHERE ticker='TEAM' AND trade_date >= DATE '2026-10-05' ORDER BY 1;
\echo '== 3. bars count TEAM total'
SELECT count(*) FROM mi_daily_closes WHERE ticker='TEAM';
