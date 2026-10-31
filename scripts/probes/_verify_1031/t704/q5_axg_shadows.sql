SET default_transaction_read_only = on;
\echo == tables with a ticker column whose name marks a shadow / walk that reads split scale
SELECT table_name FROM information_schema.columns WHERE column_name='ticker' AND table_schema='public'
  AND (table_name LIKE '%cb_%' OR table_name LIKE '%parabolic%' OR table_name LIKE '%htf%' OR table_name LIKE '%consolidation%') ORDER BY 1;
