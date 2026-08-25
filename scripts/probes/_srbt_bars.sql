SELECT ticker, trade_date, open_price, high_price, low_price, close, volume
FROM mi_daily_closes
WHERE ticker IN (SELECT DISTINCT ticker FROM mi_ep_scan_log)
   OR ticker IN ('AEHR','ALGM','AMD','AMKR','APLD','ARM','ASX','BE','FLY','HUT','INTC','IREN','MRNA','MRVL','MU','NBIS','QBTS','QCOM','QURE','SMTC','SNDK','SNOW','STRL','UMC','USAR')
ORDER BY ticker, trade_date;
