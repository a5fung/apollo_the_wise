-- verify pull (read-only, captured once): bars for every ticker with a TIGHTENING/COILED/TRIGGERED row in the 60-day window,
-- plus every row (any stage) for those tickers, plus WATCH-drop recount excluding the 09-07 partial scan.
SELECT 'bar' q, ticker, trade_date::text, open_price::text, high_price::text, low_price::text, close::text, volume::text, '' x1
FROM mi_daily_closes
WHERE ticker IN ('ABVX','AMLX','APPS','ATAI','BWIN','CDNA','CHPT','CHYM','DFTX','EFOR','ESTC','FBRX','FIVN','GH','GSHD','HELP','HTFL','IOVA','KOD','MBX','NEO','NWL','OMER','PAY','PBF','PLSE','PURR','QMCO','REPL','RUM','TEAM','TJGC','VCYT','WDAY','XHLD','ZBIO')
  AND trade_date BETWEEN '2026-05-01' AND '2026-10-09'
UNION ALL
SELECT 'row', ticker, scan_date::text, stage, COALESCE(held_from_stage,''), pivot_high_date::text, COALESCE(base_age::text,''), COALESCE(base_high::text,''), left(COALESCE(reason,''),70)
FROM mi_flag_candidates
WHERE ticker IN ('ABVX','AMLX','APPS','ATAI','BWIN','CDNA','CHPT','CHYM','DFTX','EFOR','ESTC','FBRX','FIVN','GH','GSHD','HELP','HTFL','IOVA','KOD','MBX','NEO','NWL','OMER','PAY','PBF','PLSE','PURR','QMCO','REPL','RUM','TEAM','TJGC','VCYT','WDAY','XHLD','ZBIO')
  AND scan_date >= '2026-07-01'
UNION ALL
SELECT 'watchdrop', w.ticker, w.scan_date::text, COALESCE(w.nd::text,''), dl.nxt::text, '', '', '', ''
FROM (SELECT ticker, scan_date, stage, LEAD(scan_date) OVER (PARTITION BY ticker ORDER BY scan_date) nd
      FROM mi_flag_candidates WHERE scan_date >= '2026-07-17') w
JOIN (SELECT scan_date, LEAD(scan_date) OVER (ORDER BY scan_date) nxt
      FROM (SELECT DISTINCT scan_date FROM mi_flag_candidates WHERE scan_date >= '2026-07-17') d) dl ON dl.scan_date = w.scan_date
WHERE w.stage='WATCH' AND dl.nxt IS NOT NULL AND (w.nd IS NULL OR w.nd > dl.nxt)
ORDER BY 1,2,3;
