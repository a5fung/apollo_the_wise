SET default_transaction_read_only = on;
-- WOULD-FAIL-IF arm 2: a 'pending' row whose ticker HAS a score row on the prior complete date
SELECT s.scan_date, s.ticker, max(sc.score_date) AS last_score_date_before, bool_or(sc.adv_20 IS NOT NULL) AS had_adv20
FROM (SELECT DISTINCT scan_date, ticker FROM mi_ep_shortlist_shadow WHERE board_n > 20 AND scan_date >= DATE '2026-10-12' AND adv_source = 'pending') s
LEFT JOIN mi_stock_scores sc ON sc.ticker = s.ticker AND sc.score_date < s.scan_date AND sc.score_date >= s.scan_date - 7
GROUP BY 1,2 ORDER BY 1,2;
SELECT scan_date, max(score_date) FROM (SELECT DISTINCT scan_date FROM mi_ep_shortlist_shadow WHERE board_n > 20 AND scan_date >= DATE '2026-10-12') d
JOIN LATERAL (SELECT score_date FROM mi_stock_scores WHERE score_date < d.scan_date GROUP BY score_date HAVING count(*) > 1000 ORDER BY score_date DESC LIMIT 1) x ON true GROUP BY 1;
