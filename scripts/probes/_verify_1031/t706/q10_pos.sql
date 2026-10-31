SET default_transaction_read_only = on;
SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND (table_name ILIKE '%position%' OR table_name ILIKE '%broker%' OR table_name ILIKE '%equity%' OR table_name ILIKE '%recon%' OR table_name ILIKE '%account%') ORDER BY 1;
