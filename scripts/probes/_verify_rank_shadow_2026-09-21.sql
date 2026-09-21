WITH b AS (SELECT ticker,alert_date,adr20_frac,trade_filled,score_tier,composite_rank_eod,pool_size_eod,composite_rank_asof0945,pool_size_asof0945 FROM mi_alert_rank_shadow WHERE alert_date > DATE '2026-08-16')
SELECT b.ticker,b.alert_date,b.adr20_frac,b.trade_filled,b.score_tier,
 b.composite_rank_eod,b.pool_size_eod,b.composite_rank_asof0945,b.pool_size_asof0945,
 d0.open_price, d0.low_price,
 (SELECT count(*) FROM mi_daily_closes z WHERE z.ticker=b.ticker AND z.trade_date>=b.alert_date) AS sess,
 h5.h, h20.h, l5.l
FROM b
LEFT JOIN LATERAL (SELECT open_price,low_price FROM mi_daily_closes WHERE ticker=b.ticker AND trade_date=b.alert_date) d0 ON TRUE
LEFT JOIN LATERAL (SELECT MAX(high_price) h FROM (SELECT high_price FROM mi_daily_closes WHERE ticker=b.ticker AND trade_date>=b.alert_date ORDER BY trade_date LIMIT 6) x) h5 ON TRUE
LEFT JOIN LATERAL (SELECT MAX(high_price) h FROM (SELECT high_price FROM mi_daily_closes WHERE ticker=b.ticker AND trade_date>=b.alert_date ORDER BY trade_date LIMIT 21) x) h20 ON TRUE
LEFT JOIN LATERAL (SELECT MIN(low_price) l FROM (SELECT low_price FROM mi_daily_closes WHERE ticker=b.ticker AND trade_date>b.alert_date ORDER BY trade_date LIMIT 5) x) l5 ON TRUE
ORDER BY b.alert_date,b.ticker
