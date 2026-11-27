SET default_transaction_read_only = on;
SELECT id, market, detail FROM mi_cot_alerts WHERE alert_date = '2026-11-25' AND kind = 'news' ORDER BY id;
