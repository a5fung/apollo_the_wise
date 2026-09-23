WITH base AS (
  SELECT s.ticker, s.alert_date, s.adr20_frac, s.alerted_high, s.trade_filled, s.score_tier,
         s.composite_rank_eod, s.pool_size_eod, s.composite_rank_asof0945, s.pool_size_asof0945
  FROM mi_alert_rank_shadow s WHERE s.alert_date > DATE '2026-08-16'
), enr AS (
  SELECT b.*, d0.open_price AS open_d0, d0.close AS close_d0, d0.low_price AS low_d0,
         d5.close AS close_d5, d20.close AS close_d20, h5.h AS h5, h20.h AS h20,
         ns.n AS sessions_avail, l5.l AS minlow_d1_d5
  FROM base b
  LEFT JOIN LATERAL (SELECT open_price, close, low_price FROM mi_daily_closes WHERE ticker=b.ticker AND trade_date=b.alert_date) d0 ON TRUE
  LEFT JOIN LATERAL (SELECT close FROM mi_daily_closes WHERE ticker=b.ticker AND trade_date>b.alert_date ORDER BY trade_date ASC OFFSET 4 LIMIT 1) d5 ON TRUE
  LEFT JOIN LATERAL (SELECT close FROM mi_daily_closes WHERE ticker=b.ticker AND trade_date>b.alert_date ORDER BY trade_date ASC OFFSET 19 LIMIT 1) d20 ON TRUE
  LEFT JOIN LATERAL (SELECT MAX(high_price) h FROM (SELECT high_price FROM mi_daily_closes WHERE ticker=b.ticker AND trade_date>=b.alert_date ORDER BY trade_date ASC LIMIT 6) x) h5 ON TRUE
  LEFT JOIN LATERAL (SELECT MAX(high_price) h FROM (SELECT high_price FROM mi_daily_closes WHERE ticker=b.ticker AND trade_date>=b.alert_date ORDER BY trade_date ASC LIMIT 21) x) h20 ON TRUE
  LEFT JOIN LATERAL (SELECT count(*) n FROM mi_daily_closes WHERE ticker=b.ticker AND trade_date>=b.alert_date) ns ON TRUE
  LEFT JOIN LATERAL (SELECT MIN(low_price) l FROM (SELECT low_price FROM mi_daily_closes WHERE ticker=b.ticker AND trade_date>b.alert_date ORDER BY trade_date ASC LIMIT 5) x) l5 ON TRUE
)
SELECT ticker, alert_date, adr20_frac, alerted_high, trade_filled, score_tier,
       composite_rank_eod, pool_size_eod, composite_rank_asof0945, pool_size_asof0945,
       open_d0, low_d0, sessions_avail,
       (h5-open_d0)/open_d0 AS mh5, (h20-open_d0)/open_d0 AS mh20,
       (close_d5-open_d0)/open_d0 AS r5, (close_d20-open_d0)/open_d0 AS r20,
       minlow_d1_d5
FROM enr ORDER BY alert_date, ticker
