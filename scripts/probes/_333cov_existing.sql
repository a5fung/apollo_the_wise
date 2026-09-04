SELECT source, period_type, count(*) AS n, count(DISTINCT ticker) AS n_tickers,
       min(as_of_date) AS min_as_of, max(as_of_date) AS max_as_of
FROM mi_analyst_estimates
GROUP BY source, period_type
ORDER BY source, period_type;
