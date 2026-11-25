-- READ-ONLY. Not run (the session's prod read was refused 2026-11-25). Answers: is the 11-22 news-source build live
-- (OPEC / USDA_EXPORTS / AU_CPI / PCE rows), what the calendar holds for the next two weeks, what alerts store.
SET default_transaction_read_only = on;
\d mi_cot_calendar
\d mi_cot_alerts
SELECT event_date, event_type, release_et AT TIME ZONE 'America/New_York' AS rel_et, source, refreshed_at
  FROM mi_cot_calendar WHERE event_date >= DATE '2026-11-16' ORDER BY 1, 2;
SELECT count(*), min(event_date), max(event_date) FROM mi_cot_calendar;
SELECT id, alert_date, market, direction, kind, level, events, z, peer_z, first_minute, first_minute_big, news_class, detail
  FROM mi_cot_alerts ORDER BY alert_date DESC, id DESC LIMIT 12;
SELECT report_date, market, comm, lspec, sspec, setup, close_setup FROM mi_cot_index_weekly
 WHERE report_date = (SELECT max(report_date) FROM mi_cot_index_weekly) AND (setup IS NOT NULL OR close_setup IS NOT NULL) ORDER BY 2;
SELECT report_date, known_from, message_sent_at FROM mi_cot_weeks ORDER BY 1 DESC LIMIT 4;
