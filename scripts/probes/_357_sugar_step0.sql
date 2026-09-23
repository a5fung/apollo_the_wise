-- #357 STEP-0 — sugar-baby membership as a forward-return confluence signal (Lane-1 pre-build).
-- Read-only. Membership taken AS-OF the alert date (cohort_date <= alert_date) — no lookahead.
-- Forward = 5d-max-high % from the alert-day close; winner = >= +10%. Table doc:
-- docs/analysis/357_sugar_step0_table_2026-07-11.md
WITH alerts AS (
  SELECT a.ticker, a.alert_date, a.score_tier, dc.close AS entry_close,
         EXISTS (SELECT 1 FROM mi_sugar_babies_cohort s
                 WHERE s.ticker=a.ticker AND s.cohort_date <= a.alert_date) AS is_member
  FROM mi_ep_alerts a
  JOIN mi_daily_closes dc ON dc.ticker=a.ticker AND dc.trade_date=a.alert_date
  WHERE a.alert_date >= '2026-03-16' AND a.score_tier='HIGH'
),
fwd AS (
  SELECT al.*,
         (SELECT max(f.high_price) FROM mi_daily_closes f
          WHERE f.ticker=al.ticker AND f.trade_date BETWEEN al.alert_date+1 AND al.alert_date+8
            AND f.high_price IS NOT NULL) AS fwd_max_high
  FROM alerts al WHERE al.entry_close > 0
)
SELECT CASE WHEN is_member THEN 'sugar-baby member' ELSE 'non-member' END AS cohort,
       count(*) n, count(fwd_max_high) settled,
       round(avg(100.0*(fwd_max_high-entry_close)/entry_close)::numeric,1) mean_fwd_max_pct,
       round((percentile_cont(0.5) WITHIN GROUP (
              ORDER BY 100.0*(fwd_max_high-entry_close)/entry_close))::numeric,1) median_pct,
       round(100.0*count(*) FILTER (WHERE fwd_max_high >= entry_close*1.10)
             /NULLIF(count(fwd_max_high),0),0) win_pct_ge10
FROM fwd GROUP BY is_member ORDER BY is_member DESC;
