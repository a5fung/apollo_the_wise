SET default_transaction_read_only = on;
SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND (table_name ILIKE '%log%' OR table_name ILIKE '%alert%' OR table_name ILIKE '%digest%' OR table_name ILIKE '%send%' OR table_name ILIKE '%chat%') ORDER BY 1;
