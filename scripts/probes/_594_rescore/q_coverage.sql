SELECT 'daily_closes' AS t, MIN(trade_date)::text AS mn, MAX(trade_date)::text AS mx, COUNT(*)::text AS n FROM mi_daily_closes;
SELECT 'intraday_exists', COALESCE(to_regclass('mi_intraday_bars')::text, 'none'), '', '';
