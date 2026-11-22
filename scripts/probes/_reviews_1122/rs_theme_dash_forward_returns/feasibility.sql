SET default_transaction_read_only = on;
\echo == Q1 mi_themes history span (R4 needs >=6 months stable naming)
SELECT min(theme_date) first_date, max(theme_date) last_date, count(DISTINCT theme_date) days, count(DISTINCT name) distinct_names, (max(theme_date)-min(theme_date)) span_days FROM mi_themes;
\echo == Q2 monthly: snapshot days, distinct names, rows
SELECT date_trunc('month',theme_date)::date m, count(DISTINCT theme_date) days, count(DISTINCT name) names, count(*) rows, count(*) FILTER (WHERE source='shadow_promoted') promoted_rows FROM mi_themes GROUP BY 1 ORDER BY 1;
\echo == Q3 naming stability: names per ticker-set (same sorted basket, different names over time)
WITH b AS (SELECT theme_date,name,(SELECT string_agg(t,',' ORDER BY t) FROM unnest(tickers) t) bk FROM mi_themes WHERE tickers IS NOT NULL AND array_length(tickers,1)>0)
SELECT count(*) baskets_with_multi_names, coalesce(max(n),0) max_names FROM (SELECT bk,count(DISTINCT name) n FROM b GROUP BY bk HAVING count(DISTINCT name)>1) x;
\echo == Q4 names whose basket changed day-to-day: median Jaccard of consecutive snapshots per name (last 60d)
WITH s AS (SELECT name,theme_date,tickers,lag(tickers) OVER (PARTITION BY name ORDER BY theme_date) pt FROM mi_themes WHERE theme_date>=current_date-60),
j AS (SELECT name,theme_date,
 (SELECT count(*) FROM unnest(tickers) a WHERE a=ANY(pt))::float / NULLIF((SELECT count(DISTINCT x) FROM unnest(tickers||pt) x),0) jac FROM s WHERE pt IS NOT NULL)
SELECT count(*) pairs, percentile_cont(0.5) WITHIN GROUP (ORDER BY jac) med_jaccard, percentile_cont(0.1) WITHIN GROUP (ORDER BY jac) p10_jaccard FROM j;
\echo == Q5 closes coverage for forward 5d/20d: latest close date, SPY rows, tickers in last-30d themes lacking closes
SELECT max(trade_date) last_close, min(trade_date) first_close, count(DISTINCT trade_date) FILTER (WHERE ticker='SPY') spy_days FROM mi_daily_closes;
WITH t AS (SELECT DISTINCT unnest(tickers) tk FROM mi_themes WHERE theme_date>=current_date-30)
SELECT count(*) theme_tickers, count(*) FILTER (WHERE NOT EXISTS (SELECT 1 FROM mi_daily_closes c WHERE c.ticker=t.tk AND c.trade_date>=current_date-30)) without_recent_closes FROM t;
\echo == Q6 era split: days per engine era (#655 rule B 10-05, fold 10-12) for theme-days
SELECT CASE WHEN theme_date<'2026-10-05' THEN 'pre_10-05' WHEN theme_date<'2026-10-12' THEN '10-05_to_10-12' ELSE 'post_10-12' END era, count(DISTINCT theme_date) days, count(DISTINCT name) names FROM mi_themes GROUP BY 1 ORDER BY 1;
\echo == Q7 days a theme has been in existence: median days_active at snapshot, and share of latest-day themes with days_active<30
SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY days_active) med_days_active, count(*) FILTER (WHERE days_active<30) lt30, count(*) n FROM mi_themes WHERE theme_date=(SELECT max(theme_date) FROM mi_themes);
\echo == Q8 resilience recorder weekly rows (shows recorder still running)
SELECT week_start, count(*) rows, count(resilience) scored FROM mi_theme_resilience_weekly GROUP BY 1 ORDER BY 1;
\echo == Q9 R4 flag / dashboard dependency: any forward-return table already present
SELECT table_name FROM information_schema.tables WHERE table_name ILIKE '%forward%' OR table_name ILIKE '%theme%ret%';
