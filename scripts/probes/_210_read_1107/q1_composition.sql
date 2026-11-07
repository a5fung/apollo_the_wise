SET default_transaction_read_only = on;
-- 1. composition: which rows are post-fix (our_captured_at set by the 10-10 card) and readable
SELECT (our_captured_at IS NOT NULL) AS post_fix, tv_status,
       count(*) AS n,
       count(*) FILTER (WHERE tv_items_we_missed IS NOT NULL) AS readable,
       count(*) FILTER (WHERE tv_coverage_reaches_period_start) AS reaches,
       min(alert_date) AS first_day, max(alert_date) AS last_day
FROM mi_tv_news_shadow GROUP BY 1,2 ORDER BY 1,2;
-- 2. false-zero check: [] on a row that does not reach the period start
SELECT count(*) AS false_zero FROM mi_tv_news_shadow
WHERE tv_items_we_missed IS NOT NULL AND jsonb_array_length(tv_items_we_missed)=0
  AND tv_coverage_reaches_period_start IS NOT TRUE;
-- 3. missed items lacking a match or bucket tag
SELECT count(*) AS untagged FROM mi_tv_news_shadow s, jsonb_array_elements(s.tv_items_we_missed) i
WHERE s.tv_items_we_missed IS NOT NULL AND (i->>'match' IS NULL OR i->>'bucket' IS NULL);
-- 4. the card's readout
SELECT our_acting_grade, catalyst_quality AS raw_grade,
  count(*) FILTER (WHERE tv_items_we_missed IS NOT NULL) AS readable,
  count(*) FILTER (WHERE EXISTS (SELECT 1 FROM jsonb_array_elements(tv_items_we_missed) i
                   WHERE i->>'bucket'='before_grade' AND i->>'match'='none')) AS strict_before_grade,
  count(*) FILTER (WHERE EXISTS (SELECT 1 FROM jsonb_array_elements(tv_items_we_missed) i
                   WHERE i->>'bucket'='before_grade')) AS loose_before_grade,
  count(*) FILTER (WHERE EXISTS (SELECT 1 FROM jsonb_array_elements(tv_items_we_missed) i
                   WHERE i->>'bucket'='repoll_window' AND i->>'match'='none')) AS strict_repoll,
  count(*) FILTER (WHERE tv_items_we_missed IS NULL AND tv_items_unmatched_seen IS NOT NULL
                   AND jsonb_array_length(tv_items_unmatched_seen) > 0) AS rolled_with_confirmed_unmatched
FROM mi_tv_news_shadow
WHERE tv_status = 'ok' AND our_captured_at IS NOT NULL
GROUP BY 1, 2 ORDER BY 1, 2;
-- 5. per-row detail of every readable post-fix row
SELECT ticker, alert_date, our_acting_grade, catalyst_quality, our_corpus_source,
       tv_items_before_grade, tv_items_in_repoll_window, tv_items_after_cutoff,
       jsonb_array_length(tv_items_we_missed) AS n_missed,
       (SELECT string_agg(i->>'bucket'||':'||(i->>'match')||':'||left(i->>'title',90), ' || ')
          FROM jsonb_array_elements(tv_items_we_missed) i) AS missed
FROM mi_tv_news_shadow
WHERE our_captured_at IS NOT NULL AND tv_items_we_missed IS NOT NULL
ORDER BY alert_date, ticker;
