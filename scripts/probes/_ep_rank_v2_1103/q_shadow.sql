SET default_transaction_read_only = on;
\copy (SELECT ticker, alert_date, alerted_high, trade_filled, score_tier, tightness_pct_eod, tightness_pct_asof0945, gap_pct_eod, ext_xadr_eod, composite_rank_eod, pool_size_eod, composite_rank_asof0945, pool_size_asof0945, adr20_frac FROM mi_alert_rank_shadow WHERE alert_date >= DATE '2026-03-01' ORDER BY alert_date, ticker) TO STDOUT WITH CSV HEADER
\copy (SELECT alert_date, ticker, score_tier FROM mi_ep_alerts WHERE alert_date >= DATE '2026-03-01' ORDER BY alert_date, ticker) TO STDOUT WITH CSV HEADER
