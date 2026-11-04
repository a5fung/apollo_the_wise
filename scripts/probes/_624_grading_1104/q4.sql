SET default_transaction_read_only = on;
SELECT entry_status, outcome, count(*), round(sum(coalesce(realized_r,0))::numeric,2) AS sum_r, sum((realized_r >= 3)::int) AS r3plus FROM (SELECT DISTINCT ON (signal_id) * FROM mi_lowcap_lane_replays ORDER BY signal_id, settled_session DESC) x GROUP BY 1,2 ORDER BY 1,2;
