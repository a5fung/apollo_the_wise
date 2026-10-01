COPY (SELECT scan_date, ticker, first_seen_et AT TIME ZONE 'America/New_York' AS first_et, last_seen_et AT TIME ZONE 'America/New_York' AS last_et,
 gap_pct_first, minutes_since_open_first, gap_pct_at_open, minutes_since_open_at_open, gap_pct_last, minutes_since_open_last,
 prev_close, prev_day_volume, prev_day_dollar_volume, failed_price_floor, failed_volume_floor,
 today_volume_first, today_price_first, today_dollar_volume_first,
 today_volume_at_open, today_price_at_open, today_dollar_volume_at_open,
 today_volume_last, today_price_last, today_dollar_volume_last
FROM mi_universe_floor_shadow WHERE scan_date <= '2026-09-30' ORDER BY scan_date, ticker) TO STDOUT WITH CSV HEADER;
