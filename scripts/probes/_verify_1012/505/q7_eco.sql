SELECT count(*) total FROM mi_theme_ecosystems;
SELECT ecosystem_code, count(*) FROM mi_theme_ecosystems GROUP BY 1 ORDER BY 2 DESC LIMIT 25;
