SET default_transaction_read_only = on;
SET statement_timeout = '60s';
\echo '== A. audit columns'
SELECT column_name FROM information_schema.columns WHERE table_name='mi_audit_log' ORDER BY ordinal_position;
