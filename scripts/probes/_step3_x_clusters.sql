\pset format unaligned
\pset fieldsep '\t'
\pset footer off
-- Step 3 (TIMELINESS / RUNWAY): every stored correlation cluster row. Stored history is
-- UNCOVERED clusters only (_dedup_against_themes drops clusters >=50% covered by an active
-- theme before the write) — the conversion rate this feeds is a floor, not a rate.
SELECT cluster_date, cluster_hash, ticker, member_count, mean_corr, avg_rs FROM mi_correlation_clusters ORDER BY cluster_date, cluster_hash, ticker;
