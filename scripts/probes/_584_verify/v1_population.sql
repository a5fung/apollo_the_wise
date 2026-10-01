SELECT 'dates', MIN(scan_date)::text, MAX(scan_date)::text, COUNT(DISTINCT scan_date)::text, COUNT(*)::text FROM mi_universe_floor_shadow;
SELECT 'per_date', scan_date::text, COUNT(*)::text, SUM(CASE WHEN failed_price_floor OR failed_volume_floor THEN 1 ELSE 0 END)::text, MAX(last_seen_et)::text FROM mi_universe_floor_shadow GROUP BY scan_date ORDER BY scan_date;
SELECT 'floors', acting_price_floor::text, acting_volume_floor::text, COUNT(*)::text FROM mi_universe_floor_shadow GROUP BY 2,3;
SELECT 'maxclose', MAX(trade_date)::text, COUNT(*)::text FROM mi_daily_closes WHERE trade_date >= '2026-09-25';
SELECT 'closes_per_date', trade_date::text, COUNT(*)::text FROM mi_daily_closes WHERE trade_date >= '2026-09-20' GROUP BY trade_date ORDER BY trade_date;
