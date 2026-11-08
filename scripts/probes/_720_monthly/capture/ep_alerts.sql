SET default_transaction_read_only = on;
-- #720 §3 selection: every EP alert since 08-01, so a labelled name with no trade row reads "alerted, no trade row" vs "never alerted" (mi_ep_alerts, not mi_live_trades alone).
\copy (SELECT ticker, alert_date, ep_score, score_tier, detected_at FROM mi_ep_alerts WHERE alert_date >= DATE '2026-08-01' ORDER BY alert_date, ticker) TO STDOUT WITH CSV HEADER
