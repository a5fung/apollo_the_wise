SET default_transaction_read_only = on;
-- live-PASS proxy, POST-RESCALE ONLY: scored row, settled 12d, with NO downgrade event
-- of ANY reason (the 7/16 lesson — matching only rubric_composite_* reasons let safety-net
-- q_rev_yoy_* downgrades count as PASS and inflate the counter).
SELECT COUNT(*) FROM mi_ep_catalyst_metrics m
WHERE m.alert_date >= '2026-08-22'
  AND m.alert_date <= CURRENT_DATE - 12
  AND m.q_revenue_yoy_pct IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM mi_audit_log a
    WHERE a.event_type = 'catalyst_earnings_revenue_weak_downgrade'
      AND a.detail LIKE '%"ticker": "' || m.ticker || '"%'
      AND a.detail LIKE '%"alert_date": "' || m.alert_date || '"%'
  );
