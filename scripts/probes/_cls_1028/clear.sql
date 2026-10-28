BEGIN;
UPDATE mi_live_trades SET depth_sell_pending_on = NULL
 WHERE id = 429 AND ticker = 'CLS' AND account_mode = 'live' AND depth_sell_pending_on = DATE '2026-10-28'
RETURNING id, ticker, depth_sell_pending_on, stop_price, remaining_shares;
COMMIT;
SELECT id, ticker, depth_sell_pending_on, stop_price, status FROM mi_live_trades WHERE depth_sell_pending_on IS NOT NULL AND status = 'filled';
