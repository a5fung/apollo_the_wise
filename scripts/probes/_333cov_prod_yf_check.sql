SELECT ticker, period_end_date, revenue_avg, revenue_low, revenue_high, num_analysts_revenue
FROM mi_analyst_estimates
WHERE source = 'yfinance' AND period_type = 'quarter'
  AND ticker IN ('NRIX','ARWR','HTFL','VERA','KYMR','SHAZ')
ORDER BY ticker, period_end_date;
