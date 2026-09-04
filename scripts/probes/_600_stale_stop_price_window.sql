-- #600 probe (READ-ONLY): is the stale-low stop_price window populated right now,
-- how often have the withholding branches fired, and — post-deploy — has the new
-- re-protect floor actually raised a placement?
-- Run: ssh apollo@87.99.134.162 "docker exec -i apollo-postgres psql -U apollo -d apollo -A -F '|'" < scripts/probes/_600_stale_stop_price_window.sql > scripts/probes/_600_stale_stop_price_window_out.psv
--
-- Background: mi_live_trades.stop_price is deliberately allowed to UNDERSTATE
-- the broker (execute_partial_exit keeps the breakeven successor's pointer while
-- withholding the price on an unconfirmed replace; the market-mode fold-in never
-- writes it). Every re-protect used to place at that column. #600 floors it to
-- the stop pointer's broker price (audit event `stop_reprotect_floor_applied`).

-- Part A: open positions whose DB stop_price may understate the broker.
-- A partial was taken, yet stop_price still sits at/below the original hard_stop
-- → breakeven was never written to the row. These are the trades a re-protect
-- would have re-armed ~1R low before #600. Compare stop_price with the pointer's
-- order on Alpaca (dashboard / get_order) to confirm each one.
SELECT id, ticker, account_mode, alert_date, remaining_shares,
       entry_price, hard_stop, stop_price, stop_order_id, partial_taken
FROM mi_live_trades
WHERE status = 'filled' AND remaining_shares > 0
  AND COALESCE(partial_taken, FALSE)
  AND stop_price IS NOT NULL AND hard_stop IS NOT NULL
  AND stop_price <= hard_stop + 0.005
ORDER BY alert_date DESC;

-- Part B: how often the withholding branches fired (last 30 days).
--   partial_exit_breakeven_unverified   → source (3): accepted, successor unconfirmed (pointer = successor, price withheld)
--   partial_exit_breakeven_unverifiable → source (2): replace raised, reduced stop unreadable (pointer kept at old id)
--   partial_exit_breakeven_deferred     → NOT a source (replace rejected, stop live at original) — cross-reference only
--   partial_exit_breakeven_armed with mechanism ABSENT → market-mode fold-in, source (4) (never writes stop_price)
SELECT created_at AT TIME ZONE 'America/New_York' AS et, event_type, summary
FROM mi_audit_log
WHERE event_type IN ('partial_exit_breakeven_unverified',
                     'partial_exit_breakeven_unverifiable',
                     'partial_exit_breakeven_deferred',
                     'partial_exit_breakeven_armed')
  AND created_at > NOW() - INTERVAL '30 days'
ORDER BY created_at DESC;

-- Part C (post-deploy verify-live): every time the floor raised a placement.
-- Empty = the window has not been hit since deploy (not proof the fix is dark —
-- the retry/sync only PLACE when a stop is actually gone). Any row = the fix
-- acted on live state: db_price → placed_price, at which site.
SELECT created_at AT TIME ZONE 'America/New_York' AS et, summary, detail
FROM mi_audit_log
WHERE event_type = 'stop_reprotect_floor_applied'
ORDER BY created_at DESC
LIMIT 20;
