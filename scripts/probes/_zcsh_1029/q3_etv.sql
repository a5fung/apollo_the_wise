SET default_transaction_read_only = on;
SELECT string_agg(ticker, ' ' ORDER BY ticker) FROM mi_security_types WHERE security_type='ETV';
