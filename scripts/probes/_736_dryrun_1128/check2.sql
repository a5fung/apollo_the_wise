SET default_transaction_read_only = on;
SELECT trade_date,count(*) FROM mi_daily_closes WHERE trade_date>='2026-11-24' GROUP BY 1 ORDER BY 1;
SELECT s.security_type, count(*) FROM mi_security_types s WHERE ticker IN ('AACP','ACAA','ACGC','AEAQ','AESP','AKA','ALF','ALOV','ALUB','ANGH','APAC','APMC','APUR','ARCL','BCCQ','BEBE','BHAV','BPAC','BREZ','BRRK','BSAA','CAII','CAPN','CAQ','CATL','CCII','CEPS','CHAR','CHEC','CHPG','COPL','CRAN','CTAA','DAAQ','DGAC','DRDB','DSAC','DTSQ','DYOR','EGHA') GROUP BY 1;
