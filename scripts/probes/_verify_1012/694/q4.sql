\echo == Q14 all Monday rs_prev_complete rows: adv equals 10-09 mi_stock_scores adv_20?
SELECT count(*) n, count(*) FILTER (WHERE s.adv = m.adv_20) n_equal, count(*) FILTER (WHERE s.adv IS DISTINCT FROM m.adv_20) n_differ
FROM mi_ep_shortlist_shadow s JOIN mi_stock_scores m ON m.ticker=s.ticker AND m.score_date='2026-10-09'
WHERE s.scan_date='2026-10-12' AND s.adv_source='rs_prev_complete';
