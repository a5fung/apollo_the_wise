SET default_transaction_read_only = on;
SELECT ticker, max(ep_score) max_score, string_agg(DISTINCT score_tier,',') tiers, string_agg(DISTINCT catalyst_quality,',') cq, round(max(gap_pct)::numeric,1) gap, string_agg(DISTINCT coalesce(filter_reason,'-'),',') reasons FROM mi_ep_scan_log WHERE scan_date = DATE '2026-11-10' AND ticker IN ('QMCO','HROW','SECZ','EIKN','RLGT','CSQR','VMD','CCAP','PAYS','MCFT','CTY') GROUP BY 1 ORDER BY 2 DESC NULLS LAST;
SELECT ticker, score_tier, ep_score, catalyst_quality, created_at AT TIME ZONE 'America/New_York' et FROM mi_ep_alerts WHERE alert_date = DATE '2026-11-10' ORDER BY id;
SELECT regime FROM mi_market_regime ORDER BY 1 DESC LIMIT 0;
