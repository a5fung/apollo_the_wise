SET default_transaction_read_only = on;
SELECT s.ticker, st.security_type, st.name FROM (SELECT DISTINCT ticker FROM mi_consolidation_entry_shadow WHERE entry_date >= CURRENT_DATE - 60) s LEFT JOIN mi_security_types st USING (ticker) ORDER BY 1;
