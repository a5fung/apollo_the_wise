SET default_transaction_read_only = on;
SELECT ticker, score_date, rs_composite FROM mi_stock_scores WHERE ticker IN ('CORZ','CRWV','RIOT','FIGR') AND score_date >= '2026-11-17' ORDER BY ticker, score_date;
