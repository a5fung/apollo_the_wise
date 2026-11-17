SET default_transaction_read_only = on;
SELECT ticker, security_type FROM mi_security_types WHERE ticker IN ('FNGD','FNGU','SOXL','TQQQ','BULZ');
SELECT security_type, COUNT(*) FROM mi_security_types GROUP BY 1 ORDER BY 2 DESC;
