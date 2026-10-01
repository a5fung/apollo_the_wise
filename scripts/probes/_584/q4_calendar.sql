\copy (SELECT trade_date, count(*) n FROM mi_daily_closes WHERE trade_date >= DATE '2026-07-20' GROUP BY 1 ORDER BY 1) TO STDOUT WITH CSV HEADER
