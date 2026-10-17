-- READ-ONLY. #333 Finnhub quarter-label drift: same ticker, Finnhub period_end_dates within 1-20 days of each other = one quarter split into two keys.
WITH f AS (SELECT DISTINCT ticker, period_end_date FROM mi_analyst_estimates WHERE source='finnhub_calendar' AND period_type='quarter')
SELECT a.ticker, a.period_end_date AS d1, b.period_end_date AS d2, (b.period_end_date - a.period_end_date) AS gap_days
FROM f a JOIN f b ON a.ticker=b.ticker AND b.period_end_date > a.period_end_date AND b.period_end_date - a.period_end_date BETWEEN 1 AND 20
ORDER BY gap_days, a.ticker;
SELECT count(DISTINCT ticker) AS finnhub_tickers, count(*) AS rows FROM mi_analyst_estimates WHERE source='finnhub_calendar';
-- same check on yfinance quarter rows (stabilized) for comparison
WITH f AS (SELECT DISTINCT ticker, period_end_date FROM mi_analyst_estimates WHERE source='yfinance' AND period_type='quarter')
SELECT count(*) AS yf_split_pairs FROM f a JOIN f b ON a.ticker=b.ticker AND b.period_end_date > a.period_end_date AND b.period_end_date - a.period_end_date BETWEEN 1 AND 20;
-- AEHR (EDGAR year end wrong): its Finnhub labels
SELECT as_of_date, period_end_date, fiscal_quarter, fiscal_year FROM mi_analyst_estimates WHERE ticker='AEHR' AND source='finnhub_calendar' ORDER BY as_of_date DESC LIMIT 6;
