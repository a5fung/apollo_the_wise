SET default_transaction_read_only = on;
SELECT count(*) rows, count(DISTINCT week_start) weeks, min(week_start), max(week_start), count(*) FILTER (WHERE resilience_computable) computable FROM mi_theme_resilience_weekly;
SELECT week_start, count(*) FROM mi_theme_resilience_weekly GROUP BY 1 ORDER BY 1 DESC LIMIT 6;
