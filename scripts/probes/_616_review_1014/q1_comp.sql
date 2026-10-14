\set QUIET 1
\echo == A. live-EP invariant: rows in live table with NO live mi_ep_alerts row (health_checks._DE_NON_EP_WHERE), split by ep_date vs 2026-09-01
SELECT (t.ep_date >= DATE '2026-09-01') AS ep_on_or_after_0901, COUNT(*) AS non_ep_rows
FROM mi_delayed_entry_trigger t
WHERE NOT EXISTS (SELECT 1 FROM mi_ep_alerts a WHERE a.ticker=t.ticker AND a.alert_date=t.ep_date AND COALESCE(a.source,'live')='live')
GROUP BY 1 ORDER BY 1;
\echo == A2. whole live table size and fire_date range
SELECT COUNT(*) AS rows_total, MIN(fire_date) AS min_fire, MAX(fire_date) AS max_fire,
       COUNT(*) FILTER (WHERE fire_date >= DATE '2026-09-02') AS rows_since_0902
FROM mi_delayed_entry_trigger;
\echo == B. voided table: what the 09-19 predicate (160) was counting
SELECT to_regclass('mi_delayed_entry_trigger_voided_0901') IS NOT NULL AS voided_table_exists;
SELECT reentry_shape, COUNT(*) AS voided_rows_fire_since_0902_ep_low_reclaim_075_settled
FROM mi_delayed_entry_trigger_voided_0901
WHERE rung='ep_low_reclaim' AND fire_date >= DATE '2026-09-02' AND realized_r_trail_075 IS NOT NULL
GROUP BY 1 ORDER BY 1;
SELECT COUNT(*) AS voided_total_ep_low_reclaim_since_0902 FROM mi_delayed_entry_trigger_voided_0901 WHERE rung='ep_low_reclaim' AND fire_date >= DATE '2026-09-02';
\echo == B2. live table: the YAML predicate as written (all shapes) vs first-only
SELECT reentry_shape, COUNT(*) AS predicate_rows
FROM mi_delayed_entry_trigger WHERE rung='ep_low_reclaim' AND fire_date >= DATE '2026-09-02' AND realized_r_trail_075 IS NOT NULL
GROUP BY 1 ORDER BY 1;
\echo == C. composition by rung x shape x fire month (live table, fire_date >= 2026-09-02)
WITH cal AS (SELECT trade_date FROM mi_daily_closes WHERE ticker='SPY' AND trade_date >= DATE '2026-08-20'),
lastd AS (SELECT MAX(trade_date) AS d FROM cal),
t AS (
  SELECT t.*, (SELECT COUNT(*) FROM cal c, lastd WHERE c.trade_date > t.fire_date AND c.trade_date <= lastd.d) AS sess_after_fire
  FROM mi_delayed_entry_trigger t WHERE t.fire_date >= DATE '2026-09-02'
)
SELECT rung, reentry_shape, to_char(fire_date,'YYYY-MM') AS fire_month,
       COUNT(*) AS n_rows,
       COUNT(*) FILTER (WHERE ep_adr20_n IS NOT NULL) AS has_adr,
       COUNT(*) FILTER (WHERE sess_after_fire >= 20) AS mature_20,
       COUNT(*) FILTER (WHERE realized_r_trail IS NOT NULL) AS inc_settled,
       COUNT(*) FILTER (WHERE realized_r_trail_075 IS NOT NULL) AS v075_settled,
       COUNT(*) FILTER (WHERE outcome_075='unscoreable') AS v075_unscor,
       COUNT(*) FILTER (WHERE realized_r_trail_100 IS NOT NULL) AS v100_settled,
       COUNT(*) FILTER (WHERE outcome_100='unscoreable') AS v100_unscor,
       COUNT(*) FILTER (WHERE sess_after_fire >= 20 AND realized_r_trail_075 IS NOT NULL AND realized_r_trail_100 IS NOT NULL AND realized_r_trail IS NOT NULL) AS mature_all3_settled,
       COUNT(*) FILTER (WHERE sess_after_fire >= 20 AND (realized_r_trail_075 IS NULL OR realized_r_trail_100 IS NULL OR realized_r_trail IS NULL)) AS mature_but_open_or_unscor,
       COUNT(*) FILTER (WHERE sess_after_fire < 20 AND realized_r_trail_075 IS NOT NULL) AS immature_but_settled_075
FROM t GROUP BY 1,2,3 ORDER BY 1,2,3;
\echo == D. ep_low_reclaim first attempts: every fire, newest first
WITH cal AS (SELECT trade_date FROM mi_daily_closes WHERE ticker='SPY' AND trade_date >= DATE '2026-08-20'),
lastd AS (SELECT MAX(trade_date) AS d FROM cal)
SELECT t.id, t.ticker, t.ep_date, t.fire_date, t.fire_minute_et,
       (SELECT COUNT(*) FROM cal c, lastd WHERE c.trade_date > t.fire_date AND c.trade_date <= lastd.d) AS sess_after_fire,
       t.outcome_trail AS inc, t.outcome_trail_075 AS o075, t.outcome_trail_100 AS o100
FROM mi_delayed_entry_trigger t WHERE t.rung='ep_low_reclaim' AND t.reentry_shape='first' AND t.fire_date >= DATE '2026-09-02'
ORDER BY t.fire_date DESC, t.id;
\echo == E. all-rung first-attempt fires per fire_date week (accrual rate for the next-read estimate)
SELECT date_trunc('week', fire_date)::date AS wk, rung, COUNT(*) AS first_fires
FROM mi_delayed_entry_trigger WHERE reentry_shape='first' AND fire_date >= DATE '2026-09-02'
GROUP BY 1,2 ORDER BY 1,2;
\echo == F. ep_low_reclaim first-attempt fires BEFORE 09-02 left in the live table (not prospective; excluded)
SELECT COUNT(*) AS n_before_0902, MIN(fire_date), MAX(fire_date) FROM mi_delayed_entry_trigger WHERE rung='ep_low_reclaim' AND reentry_shape='first' AND fire_date < DATE '2026-09-02';
