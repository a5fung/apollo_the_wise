SET default_transaction_read_only = on;
SELECT market, jsonb_path_query_first(detail, '$.news[0].release'), jsonb_path_query_first(detail, '$.news[0].series[0]') FROM mi_cot_alerts WHERE alert_date = '2026-11-25' AND kind = 'news' AND market IN ('silver','new_zealand_dollar');
