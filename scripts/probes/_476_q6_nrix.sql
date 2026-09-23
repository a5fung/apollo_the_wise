SELECT theme_date, name, stage, array_length(tickers,1) AS n, source
FROM mi_themes
WHERE theme_date >= CURRENT_DATE - 25 AND 'NRIX' = ANY(tickers)
ORDER BY theme_date, name;
