SET default_transaction_read_only = on;
\d mi_lowcap_lane_signals
SELECT date_trunc('month', signal_date)::date m, count(*) FROM mi_lowcap_lane_signals GROUP BY 1 ORDER BY 1;
