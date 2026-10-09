-- verify #694 (d): the counted-out real EPs. Read-only.
\echo '### V4a TDIC any scan-log row 2026-05-01..2026-05-20, and any EP alert row'
SELECT scan_date, count(*) n, min(to_char(scan_time_et AT TIME ZONE 'America/New_York','HH24:MI')) first_t, max(gap_pct) max_gap
  FROM mi_ep_scan_log WHERE ticker='TDIC' AND scan_date BETWEEN '2026-05-01' AND '2026-05-20' GROUP BY 1 ORDER BY 1;
SELECT count(*) n_scanlog_all_time_tdic FROM mi_ep_scan_log WHERE ticker='TDIC';
\echo '### V4b ABNB 2026-08-07 rows by tick'
SELECT to_char(scan_time_et AT TIME ZONE 'America/New_York','HH24:MI:SS') t, rank_by_gap, gap_pct, reject_stage, left(filter_reason,70) fr
  FROM mi_ep_scan_log WHERE ticker='ABNB' AND scan_date='2026-08-07' ORDER BY scan_time_et LIMIT 12;
\echo '### V4c PENG 2026-10-07 pre-open rows: gap, stage, reason (first 6 and last 6 pre-open)'
(SELECT to_char(scan_time_et AT TIME ZONE 'America/New_York','HH24:MI:SS') t, rank_by_gap, gap_pct, gap_pct_rt, gap_pct_delayed, reject_stage, left(filter_reason,90) fr
  FROM mi_ep_scan_log WHERE ticker='PENG' AND scan_date='2026-10-07' AND (scan_time_et AT TIME ZONE 'America/New_York')::time < '09:30' ORDER BY scan_time_et DESC LIMIT 6)
UNION ALL
(SELECT to_char(scan_time_et AT TIME ZONE 'America/New_York','HH24:MI:SS') t, rank_by_gap, gap_pct, gap_pct_rt, gap_pct_delayed, reject_stage, left(filter_reason,90) fr
  FROM mi_ep_scan_log WHERE ticker='PENG' AND scan_date='2026-10-07' AND (scan_time_et AT TIME ZONE 'America/New_York')::time < '09:30' ORDER BY scan_time_et LIMIT 4);
SELECT count(*) n_preopen, count(rank_by_gap) n_ranked, max(gap_pct) max_gap
  FROM mi_ep_scan_log WHERE ticker='PENG' AND scan_date='2026-10-07' AND (scan_time_et AT TIME ZONE 'America/New_York')::time < '09:30';
\echo '### V4d April positives: rows, scan_time_et null?, rank_by_gap'
SELECT ticker, scan_date, count(*) n, count(scan_time_et) n_with_time, count(rank_by_gap) n_ranked, max(gap_pct) gap, max(left(filter_reason,60)) fr
  FROM mi_ep_scan_log WHERE (ticker,scan_date) IN (('UMC','2026-04-17'),('AMD','2026-04-24'),('INTC','2026-04-24'),('QCOM','2026-04-24'))
 GROUP BY 1,2;
SELECT count(*) n_april_rows, count(scan_time_et) with_time, count(rank_by_gap) ranked FROM mi_ep_scan_log WHERE scan_date BETWEEN '2026-04-13' AND '2026-04-30';
