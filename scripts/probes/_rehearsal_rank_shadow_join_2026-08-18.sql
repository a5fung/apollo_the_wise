-- Rehearsal join for alert_rank_shadow_out_of_sample (2026-08-18).
-- Proves the composite-rank -> forward-outcome join can actually be executed against
-- mi_alert_rank_shadow (which stores NO forward-outcome column itself).
-- Forward outcome = R1 geometry (matches scripts/probes/_expectedness_and_ranking.py
-- cohort_features's "R geometry 1"): entry = EP-day high, stop = EP-day low,
-- R = (max close-adjacent HIGH over the next up-to-60 trading days - entry) / (entry-stop).
-- Read-only. No writes. THE LINE: nothing here feeds any grading/entry/sizing path.
SELECT
  s.alert_id, s.ticker, s.alert_date,
  s.day_high, s.day_low,
  s.qualifies_for_rank_eod, s.composite_rank_eod, s.pool_size_eod,
  s.qualifies_for_rank_asof0945, s.composite_rank_asof0945, s.pool_size_asof0945,
  s.trade_exists, s.trade_filled,
  f.fwd_high, f.fwd_low, f.fwd_n
FROM mi_alert_rank_shadow s
LEFT JOIN LATERAL (
  SELECT MAX(x.high_price) AS fwd_high, MIN(x.low_price) AS fwd_low, COUNT(*) AS fwd_n
  FROM (
    SELECT high_price, low_price
    FROM mi_daily_closes d
    WHERE d.ticker = s.ticker AND d.trade_date > s.alert_date
      AND d.high_price IS NOT NULL AND d.low_price IS NOT NULL
    ORDER BY d.trade_date ASC
    LIMIT 60
  ) x
) f ON TRUE
WHERE s.day_high IS NOT NULL AND s.day_low IS NOT NULL AND s.day_high > s.day_low
ORDER BY s.alert_date, s.ticker;
