-- #286 RS liquidity-floor blast-radius (READ-ONLY). Replicates the deployed filter
-- (current_close * median_20d_volume < $10M, among names that would otherwise score, i.e.
-- close >= $5) and intersects the EXCLUDED set with the downstream consumers that read
-- mi_stock_scores: active tracked stocks, current theme members, open held positions.
-- If excluded ∩ {tracked,theme,held} is ~0 we drop illiquid nobodies (safe); if it hits
-- legit names they lose their score row -> null downstream joins (fix before the 5 PM RS run).

\echo '== headline counts =='
WITH ref AS (SELECT MAX(trade_date) AS d FROM mi_daily_closes),
adv AS (
  SELECT ticker, PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY volume) AS adv
  FROM mi_daily_closes, ref
  WHERE trade_date <= ref.d AND trade_date >= ref.d - INTERVAL '30 days' AND volume > 0
  GROUP BY ticker HAVING COUNT(*) >= 10
),
latest AS (
  SELECT DISTINCT ON (ticker) ticker, close
  FROM mi_daily_closes ORDER BY ticker, trade_date DESC
),
excluded AS (
  SELECT a.ticker, l.close, a.adv, l.close*a.adv AS dv
  FROM adv a JOIN latest l USING (ticker)
  WHERE l.close >= 5.0 AND l.close*a.adv < 10000000
),
tm AS (
  SELECT DISTINCT unnest(tickers) AS ticker FROM mi_themes
  WHERE stage <> 'Retired' AND theme_date >= CURRENT_DATE - INTERVAL '7 days'
)
SELECT
 (SELECT d FROM ref) AS ref_date,
 (SELECT COUNT(*) FROM latest WHERE close >= 5.0) AS scored_ge5,
 (SELECT COUNT(*) FROM excluded) AS excl_total,
 (SELECT COUNT(*) FROM excluded e JOIN mi_tracked_stocks t ON t.ticker=e.ticker AND t.active) AS excl_tracked,
 (SELECT COUNT(*) FROM excluded e JOIN tm ON tm.ticker=e.ticker) AS excl_theme,
 (SELECT COUNT(*) FROM excluded e JOIN mi_live_trades lt ON lt.ticker=e.ticker AND lt.status='filled' AND lt.remaining_shares>0) AS excl_held;

\echo '== detail: tracked / theme / held names that get EXCLUDED =='
WITH ref AS (SELECT MAX(trade_date) AS d FROM mi_daily_closes),
adv AS (
  SELECT ticker, PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY volume) AS adv
  FROM mi_daily_closes, ref
  WHERE trade_date <= ref.d AND trade_date >= ref.d - INTERVAL '30 days' AND volume > 0
  GROUP BY ticker HAVING COUNT(*) >= 10
),
latest AS (
  SELECT DISTINCT ON (ticker) ticker, close
  FROM mi_daily_closes ORDER BY ticker, trade_date DESC
),
excluded AS (
  SELECT a.ticker, l.close, a.adv, l.close*a.adv AS dv
  FROM adv a JOIN latest l USING (ticker)
  WHERE l.close >= 5.0 AND l.close*a.adv < 10000000
),
tm AS (
  SELECT DISTINCT unnest(tickers) AS ticker FROM mi_themes
  WHERE stage <> 'Retired' AND theme_date >= CURRENT_DATE - INTERVAL '7 days'
)
SELECT e.ticker,
  round(e.close::numeric,2) AS close,
  e.adv::bigint AS adv_20,
  round((e.dv/1e6)::numeric,2) AS dollar_vol_m,
  EXISTS(SELECT 1 FROM mi_tracked_stocks t WHERE t.ticker=e.ticker AND t.active) AS tracked,
  EXISTS(SELECT 1 FROM tm WHERE tm.ticker=e.ticker) AS theme,
  EXISTS(SELECT 1 FROM mi_live_trades lt WHERE lt.ticker=e.ticker AND lt.status='filled' AND lt.remaining_shares>0) AS held
FROM excluded e
WHERE EXISTS(SELECT 1 FROM mi_tracked_stocks t WHERE t.ticker=e.ticker AND t.active)
   OR EXISTS(SELECT 1 FROM tm WHERE tm.ticker=e.ticker)
   OR EXISTS(SELECT 1 FROM mi_live_trades lt WHERE lt.ticker=e.ticker AND lt.status='filled' AND lt.remaining_shares>0)
ORDER BY dollar_vol_m;
