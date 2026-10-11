\t
SELECT row_to_json(r)::text FROM (
  SELECT review_date, window_days, regime, created_at, summary, suggestions, metrics
  FROM mi_system_reviews
  WHERE review_date IN ('2026-10-11','2026-10-04','2026-09-27')
  ORDER BY review_date DESC
) r;
