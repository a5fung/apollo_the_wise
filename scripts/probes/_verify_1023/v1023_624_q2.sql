\pset pager off
\echo === Q2-1 shadow lane signals: total, sessions, per-day since 10-12
SELECT count(*) total, count(DISTINCT scan_date) sessions, count(DISTINCT ticker) tickers, min(scan_date) first_d, max(scan_date) last_d FROM mi_lowcap_lane_signals;
SELECT scan_date, count(*) n, string_agg(ticker, ',' ORDER BY id) tickers FROM mi_lowcap_lane_signals WHERE scan_date >= '2026-10-12' GROUP BY 1 ORDER BY 1;
\echo === Q2-2 shadow lane replays: outcome counts, settled, tickers, tail events, eras
SELECT outcome, count(*) n, count(DISTINCT ticker) tickers, count(*) FILTER (WHERE meets_3r) meets_3r, count(*) FILTER (WHERE meets_4r) meets_4r FROM mi_lowcap_lane_replays GROUP BY 1 ORDER BY 1;
SELECT count(*) total, count(*) FILTER (WHERE outcome='settled') settled, count(DISTINCT ticker) FILTER (WHERE outcome='settled') settled_tickers, count(*) FILTER (WHERE outcome='settled' AND meets_3r) tail_ge3r, round(avg(realized_r) FILTER (WHERE outcome='settled')::numeric,3) mean_r, replay_exit_era FROM mi_lowcap_lane_replays GROUP BY replay_exit_era ORDER BY replay_exit_era;
SELECT max(session_date) last_session, max(to_char(recorded_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI')) last_recorded FROM mi_lowcap_lane_replays;
\echo === Q2-3 shadow signals vs replays: signals with no replay row (should be only same-day / pending)
SELECT s.scan_date, count(*) FILTER (WHERE r.id IS NULL) no_replay, count(*) n FROM mi_lowcap_lane_signals s LEFT JOIN mi_lowcap_lane_replays r ON r.signal_id = s.id WHERE s.scan_date >= '2026-10-01' GROUP BY 1 ORDER BY 1;
\echo === Q2-4 paper lane replays (all rows, key cols)
SELECT ticker, session_date, signal_id, entry_status, outcome, final_reason, realized_r, replay_exit_era, to_char(recorded_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI') rec_et FROM mi_lowcap_paper_lane_replays ORDER BY signal_id;
\echo === Q2-5 yesterday and today audit rows of replay jobs and heartbeat (full summary)
SELECT id, to_char(created_at AT TIME ZONE 'America/New_York','MM-DD HH24:MI:SS') t_et, event_type, left(summary,260) FROM mi_audit_log WHERE created_at >= '2026-10-19 04:00+00' AND event_type IN ('lowcap_lane_replay_recorded','lowcap_paper_lane_replay_recorded','lowcap_paper_lane_heartbeat') ORDER BY id;
