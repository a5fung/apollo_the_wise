SET default_transaction_read_only = on;
-- #679-adjacent fix, 2026-09-21: this counted EVERY name rejected as "(extended)", not the
-- 50-75% band the review is about, so it went ripe on a population the question never named.
-- The percentage is embedded in filter_reason ("already up 128% in prior 5 days (extended)").
SELECT COUNT(DISTINCT ticker) FROM (
  SELECT ticker,
         NULLIF(regexp_replace(filter_reason, '^already up ([0-9.]+)%.*$', '\1'),
                filter_reason)::numeric AS pct
    FROM mi_ep_scan_log
   WHERE filter_reason ILIKE '%(extended)%'
     AND scan_date >= DATE '2026-08-23'
     AND scan_date < CURRENT_DATE - 5
) x WHERE pct >= 50 AND pct < 75;
