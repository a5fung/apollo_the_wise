\pset pager off
\pset null '-'
-- V1 POPULATION (independent verifier). Schema of the three tables, then every trade that could have held
-- shares in the window regardless of account_mode / status, then a check for test/voided markers.
SELECT table_name, string_agg(column_name||':'||data_type, ', ' ORDER BY ordinal_position) AS cols
FROM information_schema.columns WHERE table_name IN ('mi_live_trades','mi_audit_log','mi_job_runs','mi_live_orders')
GROUP BY 1 ORDER BY 1;

-- every mi_live_trades row touched since 2026-09-01 (any status/mode), with fill/close and exit info
SELECT id, ticker, account_mode, status, signal_type, alert_date,
       filled_at AT TIME ZONE 'America/New_York' AS filled_et, closed_at AT TIME ZONE 'America/New_York' AS closed_et,
       entry_shares, remaining_shares, stop_price, orb_low, exit_reason
FROM mi_live_trades
WHERE created_at >= '2026-09-01' OR closed_at >= '2026-09-01' OR closed_at IS NULL AND filled_at IS NOT NULL
ORDER BY id;

-- max id overall, and id gaps since 395 (deleted rows show as gaps)
SELECT max(id) AS max_id, count(*) AS n_rows FROM mi_live_trades;
SELECT g AS missing_id FROM generate_series(395,(SELECT max(id) FROM mi_live_trades)) g
WHERE NOT EXISTS (SELECT 1 FROM mi_live_trades t WHERE t.id=g);

-- live account: positions held at each slot instant of each ET weekday 09-14..10-12, from filled_at/closed_at
WITH days AS (SELECT d::date AS d FROM generate_series('2026-09-14'::date,'2026-10-12'::date,'1 day') g(d) WHERE extract(isodow FROM d)<6),
slots AS (SELECT d, nm, ((d + t) AT TIME ZONE 'America/New_York') AS ts FROM days,
          (VALUES ('a1700', time '17:00'),('b1900', time '19:00'),('c2110', time '21:10')) s(nm,t))
SELECT s.d, s.nm, count(t.id) FILTER (WHERE t.account_mode='live') AS live_held,
       count(t.id) FILTER (WHERE t.account_mode<>'live') AS other_held,
       string_agg(t.ticker||'#'||t.id, ',' ORDER BY t.id) AS held
FROM slots s LEFT JOIN mi_live_trades t ON t.filled_at < s.ts AND (t.closed_at IS NULL OR t.closed_at > s.ts)
GROUP BY s.d, s.nm ORDER BY s.d, s.nm;
