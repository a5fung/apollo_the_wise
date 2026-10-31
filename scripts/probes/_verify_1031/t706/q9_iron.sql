SET default_transaction_read_only = on;
SELECT id, ticker, status, account_mode, entry_price, entry_shares, remaining_shares, stop_price, hard_stop, orb_low, exits::text, highest_price_seen, lowest_price_seen FROM mi_live_trades WHERE ticker='IRON' ORDER BY id DESC LIMIT 2;
SELECT trade_date, close FROM mi_daily_closes WHERE ticker='IRON' ORDER BY trade_date DESC LIMIT 4;
SELECT snapshot_date, account_mode, equity, created_at AT TIME ZONE 'America/New_York' AS created_et FROM mi_account_equity_snapshots WHERE account_mode='live' ORDER BY snapshot_date DESC, created_at DESC LIMIT 6;
SELECT id, ticker, status, entry_price, entry_shares, total_pnl, round((total_pnl/(entry_price*entry_shares)*100)::numeric,2) AS ret_pct_pnl_frame, exits::text FROM mi_live_trades WHERE ticker IN ('CLS','SMCI','KOD') AND status='closed' AND account_mode='live' ORDER BY id DESC LIMIT 4;
SELECT count(*) FILTER (WHERE status='filled' AND remaining_shares>0 AND account_mode='live') AS open_live, count(*) FILTER (WHERE status='closed' AND account_mode='live') AS closed_live FROM mi_live_trades;
