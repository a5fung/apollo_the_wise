SELECT ticker, score_date, rs_rank, rs_1m, rs_composite, close, adv_20
FROM mi_stock_scores
WHERE (ticker='GH' AND score_date BETWEEN '2026-06-08' AND '2026-07-02')
   OR (ticker='HNGE' AND score_date BETWEEN '2026-06-08' AND '2026-07-10')
   OR (ticker='HNGE' AND score_date BETWEEN '2026-08-10' AND '2026-08-26')
   OR (ticker='HPE' AND score_date BETWEEN '2026-05-26' AND '2026-06-12')
   OR (ticker='CDNA' AND score_date BETWEEN '2026-08-03' AND '2026-08-26')
   OR (ticker='MRNA' AND score_date BETWEEN '2026-08-17' AND '2026-09-25')
ORDER BY ticker, score_date;
