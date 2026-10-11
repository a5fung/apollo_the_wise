-- #697 item 5 review fix (2026-10-11): the five intraday scans (break, support test, undercut & rally, MA pullback, low-vol rest)
-- all take their watchlist from the latest stored TIGHTENING/COILED/TRIGGERED rows (flag_detector.py ~2462/2821/3077/3306/3673),
-- so a stage label that changes can add/remove a name from any of them. Every stored shadow row since 2026-07-01, with the parent
-- row it was scanned from. One read-only pull; the replay (item5_replay_hold.py) joins it to the re-threaded chain. READ-ONLY.
SET statement_timeout = '30s';
SELECT 'break' AS tbl, ticker, break_date::text AS d, parent_scan_date::text AS parent_date, parent_stage FROM mi_flag_breaks WHERE break_date >= '2026-07-01'
UNION ALL SELECT 'support_test',   ticker, test_date::text,     parent_scan_date::text, parent_stage FROM mi_flag_support_tests  WHERE test_date     >= '2026-07-01'
UNION ALL SELECT 'undercut_rally', ticker, ur_date::text,       parent_scan_date::text, parent_stage FROM mi_flag_undercut_rally WHERE ur_date       >= '2026-07-01'
UNION ALL SELECT 'ma_pullback',    ticker, pullback_date::text, parent_scan_date::text, parent_stage FROM mi_flag_ma_pullbacks   WHERE pullback_date >= '2026-07-01'
UNION ALL SELECT 'low_vol_rest',   ticker, rest_date::text,     parent_scan_date::text, parent_stage FROM mi_flag_low_vol_rests  WHERE rest_date     >= '2026-07-01'
ORDER BY 1, 3, 2;
