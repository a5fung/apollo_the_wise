SET default_transaction_read_only = on;
-- #720 §1.1: the legacy paper table — a COUNT only (expected 0), never read.
\copy (SELECT COUNT(*) AS legacy_paper_closed_in_window FROM mi_paper_trades WHERE status = 'closed' AND closed_at IS NOT NULL AND (closed_at AT TIME ZONE 'America/New_York')::date >= DATE '2026-08-16') TO STDOUT WITH CSV HEADER
