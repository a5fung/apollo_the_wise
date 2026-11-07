SET default_transaction_read_only = on;
SELECT column_name FROM information_schema.columns WHERE table_name='mi_ep_catalyst_metrics' AND column_name ILIKE '%raw%';
SELECT ticker, alert_date, (raw_polygon_news_json::text ILIKE '%Berkshire%') AS polygon_hit,
       (raw_alpaca_news_json::text ILIKE '%Berkshire%') AS alpaca_hit,
       (raw_perplexity_text ILIKE '%Berkshire%') AS pplx_hit
FROM mi_ep_catalyst_metrics WHERE ticker='BSP' AND alert_date='2026-10-14';
SELECT ticker, alert_date, catalyst_quality, left(catalyst_summary,300) AS summary
FROM mi_ep_alerts WHERE ticker='BSP' AND alert_date='2026-10-14';
