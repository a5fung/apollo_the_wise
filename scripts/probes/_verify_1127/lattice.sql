SET default_transaction_read_only = on;
SELECT string_agg(column_name, ',' ORDER BY ordinal_position) FROM information_schema.columns WHERE table_name='mi_catalyst_tier_shadow';
\echo == 11-25 scan-log outcome per ticker (latest row) for names that opened 10%+
WITH px AS (SELECT ticker, trade_date, open_price, LAG(close) OVER (PARTITION BY ticker ORDER BY trade_date) pc FROM mi_daily_closes WHERE trade_date >= DATE '2026-11-15'),
g AS (SELECT ticker FROM px WHERE trade_date = DATE '2026-11-25' AND pc >= 5 AND open_price >= 1.10*pc)
SELECT DISTINCT ON (s.ticker) s.ticker, s.filter_reason, s.reject_stage, s.score_tier, s.ep_score, s.catalyst_quality, s.llm_catalyst_quality
  FROM mi_ep_scan_log s JOIN g USING (ticker) WHERE s.scan_date = DATE '2026-11-25' ORDER BY s.ticker, s.created_at DESC;
