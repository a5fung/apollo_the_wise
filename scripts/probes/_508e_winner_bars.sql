-- first_live_winner — MINUTE BAR capture, read-only, 2026-08-24. Capture once, read many.
\echo ===B1_MINUTE_BARS===
COPY (
  SELECT ticker,
         to_char(bar_time AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI') AS et,
         open, high, low, close, volume
  FROM mi_intraday_bars
  WHERE (ticker='PLTR' AND bar_time >= '2026-08-04' AND bar_time < '2026-08-21')
     OR (ticker='ETON' AND bar_time >= '2026-08-14' AND bar_time < '2026-08-18')
  ORDER BY ticker, bar_time
) TO STDOUT WITH (FORMAT csv, HEADER);
