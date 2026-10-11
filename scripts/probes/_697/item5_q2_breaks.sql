-- #697 item 5 (2026-10-11): the intraday break scan reads the latest TIGHTENING/COILED/TRIGGERED rows as its watchlist,
-- so a stage label that changes can add/remove a name from it. Every stored break in the replay window. READ-ONLY.
SELECT ticker, break_date::text, COALESCE(parent_scan_date::text,''), COALESCE(parent_stage,'') FROM mi_flag_breaks
WHERE break_date >= '2026-07-01' ORDER BY break_date, ticker;
