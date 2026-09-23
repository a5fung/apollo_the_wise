SELECT run_date, source, name, array_length(tickers,1) AS n,
       array_to_string(tickers,',') AS members
FROM mi_theme_candidates_shadow
WHERE run_date >= CURRENT_DATE - 25
  AND tickers && ARRAY['NRIX','AGIO','ZBIO','ELVN','TGTX','RARE','XENE','ANNX','ACAD','KURA','DNTH','ALMS']
ORDER BY run_date, name;
