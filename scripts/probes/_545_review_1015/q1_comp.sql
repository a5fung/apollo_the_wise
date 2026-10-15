SET default_transaction_read_only = on;
\pset pager off
\echo == A. live-EP invariant: live-table rows with NO live mi_ep_alerts row
SELECT (t.ep_date >= DATE '2026-09-01') AS ep_on_or_after_0901, COUNT(*) AS non_ep_rows
FROM mi_delayed_entry_trigger t
WHERE NOT EXISTS (SELECT 1 FROM mi_ep_alerts a WHERE a.ticker=t.ticker AND a.alert_date=t.ep_date AND COALESCE(a.source,'live')='live')
GROUP BY 1 ORDER BY 1;
\echo == A2. whole live table
SELECT COUNT(*) AS rows_total, MIN(fire_date) AS min_fire, MAX(fire_date) AS max_fire, COUNT(*) FILTER (WHERE fire_date >= DATE '2026-09-02') AS rows_since_0902 FROM mi_delayed_entry_trigger;
\echo == C. composition by rung x shape x fire month (live table, fire_date >= 2026-09-02), 025 arm
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
       COUNT(*) FILTER (WHERE realized_r_trail_025 IS NOT NULL) AS v025_settled,
       COUNT(*) FILTER (WHERE outcome_025='unscoreable') AS v025_unscor,
       COUNT(*) FILTER (WHERE realized_r_trail_075 IS NOT NULL) AS v075_settled,
       COUNT(*) FILTER (WHERE outcome_075='unscoreable') AS v075_unscor,
       COUNT(*) FILTER (WHERE sess_after_fire >= 20 AND realized_r_trail IS NOT NULL AND realized_r_trail_025 IS NOT NULL AND realized_r_trail_075 IS NOT NULL) AS mature_3arms_settled,
       COUNT(*) FILTER (WHERE sess_after_fire >= 20 AND realized_r_trail IS NOT NULL AND realized_r_trail_025 IS NOT NULL) AS mature_inc_025_settled,
       COUNT(*) FILTER (WHERE sess_after_fire >= 20 AND (realized_r_trail_025 IS NULL OR realized_r_trail IS NULL OR realized_r_trail_075 IS NULL)) AS mature_but_open_or_unscor,
       COUNT(*) FILTER (WHERE sess_after_fire < 20 AND realized_r_trail_025 IS NOT NULL) AS immature_but_settled_025,
       COUNT(*) FILTER (WHERE sess_after_fire < 20 AND realized_r_trail_025 IS NULL) AS immature_open_025
FROM t GROUP BY 1,2,3 ORDER BY 1,2,3;
\echo == D. ep_low_reclaim first attempts: every fire, newest first
WITH cal AS (SELECT trade_date FROM mi_daily_closes WHERE ticker='SPY' AND trade_date >= DATE '2026-08-20'),
lastd AS (SELECT MAX(trade_date) AS d FROM cal)
SELECT t.id, t.ticker, t.ep_date, t.fire_date, t.fire_minute_et,
       (SELECT COUNT(*) FROM cal c, lastd WHERE c.trade_date > t.fire_date AND c.trade_date <= lastd.d) AS sess_after_fire,
       t.outcome_trail AS inc, t.outcome_trail_025 AS o025, t.outcome_trail_075 AS o075
FROM mi_delayed_entry_trigger t WHERE t.rung='ep_low_reclaim' AND t.reentry_shape='first' AND t.fire_date >= DATE '2026-09-02'
ORDER BY t.fire_date DESC, t.id;
\echo == E. all-rung first-attempt fires per fire week (accrual rate)
SELECT date_trunc('week', fire_date)::date AS wk, rung, COUNT(*) AS first_fires
FROM mi_delayed_entry_trigger WHERE reentry_shape='first' AND fire_date >= DATE '2026-09-02' GROUP BY 1,2 ORDER BY 1,2;
\echo == F. ep_low_reclaim first-attempt fires BEFORE 09-02 left in the live table (not prospective; excluded)
SELECT COUNT(*) AS n_before_0902, MIN(fire_date), MAX(fire_date) FROM mi_delayed_entry_trigger WHERE rung='ep_low_reclaim' AND reentry_shape='first' AND fire_date < DATE '2026-09-02';
\echo == G. are first attempts distinct campaigns? (ticker, ep_date) duplicates among ep_low_reclaim first attempts since 09-02
SELECT COUNT(*) AS rows, COUNT(DISTINCT (ticker, ep_date)) AS campaigns, COUNT(DISTINCT ticker) AS tickers FROM mi_delayed_entry_trigger WHERE rung='ep_low_reclaim' AND reentry_shape='first' AND fire_date >= DATE '2026-09-02';
