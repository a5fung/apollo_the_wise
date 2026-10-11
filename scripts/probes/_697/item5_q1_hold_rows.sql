-- #697 item 5 (2026-10-11): the stored stage chain behind the hysteresis hold. READ-ONLY.
-- Every stored row of every ticker that ever read WATCH/TIGHTENING/COILED/TRIGGERED in the last 70 scan dates
-- (60 reported + 10 warm-up so a chain already running at the window edge is seen). `held_from_stage` NOT NULL = a hold.
WITH days AS (SELECT DISTINCT scan_date FROM mi_flag_candidates ORDER BY scan_date DESC LIMIT 70),
     names AS (SELECT DISTINCT ticker FROM mi_flag_candidates
               WHERE scan_date IN (SELECT scan_date FROM days) AND stage IN ('WATCH','TIGHTENING','COILED','TRIGGERED'))
SELECT ticker, scan_date::text, stage, COALESCE(held_from_stage,''), COALESCE(left(reason,90),''),
       (SELECT count(*) FROM days) ndays
FROM mi_flag_candidates
WHERE scan_date IN (SELECT scan_date FROM days) AND ticker IN (SELECT ticker FROM names)
ORDER BY ticker, scan_date;
