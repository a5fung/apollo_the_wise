-- #545 Phase 4 / exit_tune_bull_regime_read — ONE read-only prod capture. Never re-run to re-read.
-- Run: ssh apollo@87.99.134.162 "docker exec -i apollo-postgres psql -U apollo -d apollo -A -F '|'" < scripts/probes/_545p4_bull_capture.sql > scripts/probes/_545p4_bull_capture_out.psv
--
-- WHY THIS EXISTS. The 2026-09-02 run (docs/analysis/exit_tune_bull_regime_read_2026-09-02.md) ran
-- OFFLINE on the 09-01 capture (scripts/ep_replay_data/_pull2_out.txt + _pull4_min.tsv.gz), which has
-- no `regime` stamp, no `highest_price_seen`, no mi_sell_discipline_records rows, and minute bars for
-- the ALERT DAY only. Four things stay open until this file is captured:
--   Q1  confirms the four INFERRED stamps (ABCL/AMLX/SOLS = Bull, CRWD = Choppy) — inferred from the
--       rule "stamp = the regime row of the PRIOR session" (live_tracker.py:522 reads the latest
--       regime_date <= today at 09:31; the nightly writes today's row at 17:00 ET), which reproduced
--       all 22 stamps already on record. A mismatch here changes the Bull cell by one trade.
--   Q2  the recorder's own peaks (peak_r / peak_adr) for the 26 — the offline read reconstructed
--       MFE from bars + daily highs; the recorder's values are the canonical ones.
--   Q3+Q4  the 4-TSV shape `scripts/probes/_508_exit_rule_replay.py` loads (REC_COLS order for
--       records; trades / daily / minute), so the 34-candidate grid runs on the TESTED engine at the
--       next milestone instead of a stand-in. Split this file's sections into the four TSVs with:
--         awk -F'|' '/^===Q3_RECORDS===/{f=1;next} /^===/{f=0} f&&!/^trade_id/{OFS="\t";$1=$1;print}' <out> > _508_records.tsv
--       (same for Q4_TRADES / Q5_DAILY / Q6_MINUTE) and point `replay.HERE` at that directory.
--   Q6  in-hold AND 16-calendar-day FORWARD minute bars for the Bull trades, so
--       `_stop_floor_forward_replay.py` can settle the floored-stop forward walk (the 09-02 read
--       walked forward at DAILY grain — a touch/no-touch read, not a fill-ordered one).
-- $0: read-only SELECTs against tables the system already keeps. THE LINE: evidence only.

\echo ===Q1_STAMPS===
SELECT t.id, t.ticker, t.alert_date, t.regime AS stamp,
       (SELECT r.regime FROM mi_market_regime r
         WHERE r.regime_date = (t.filled_at AT TIME ZONE 'America/New_York')::date) AS join_fill_day,
       (SELECT r.regime FROM mi_market_regime r
         WHERE r.regime_date < (t.filled_at AT TIME ZONE 'America/New_York')::date
         ORDER BY r.regime_date DESC LIMIT 1) AS prior_session_row,
       t.risk_dollars, t.risk_dollars_actual, t.entry_shares, t.orb_high, t.hard_stop,
       t.highest_price_seen, t.lowest_price_seen, t.total_pnl, t.partial_taken, t.breakeven_active,
       to_char(t.filled_at AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI:SS') AS filled_et,
       to_char(t.closed_at AT TIME ZONE 'America/New_York','YYYY-MM-DD HH24:MI:SS') AS closed_et
FROM mi_live_trades t
WHERE t.account_mode = 'live' AND t.status = 'closed' AND t.signal_type = 'magna53'
ORDER BY t.filled_at, t.ticker;

\echo ===Q2_PREDICATE===
SELECT 'bull_stamped' AS k, COUNT(*) FROM mi_live_trades
 WHERE account_mode = 'live' AND status = 'closed' AND regime = 'Bull'
UNION ALL
SELECT 'nonbull_eraC', COUNT(*) FROM mi_live_trades
 WHERE account_mode = 'live' AND status = 'closed' AND COALESCE(regime,'') <> 'Bull'
   AND created_at >= DATE '2026-08-16';

-- Q3: mi_sell_discipline_records in EXACTLY the REC_COLS order _508_exit_rule_replay.py::load() expects.
\echo ===Q3_RECORDS===
SELECT s.trade_id, s.ticker, s.signal_type, s.account_mode, s.alert_date, s.fill_day, s.close_day,
       s.filled_at, s.closed_at, s.entry_price, s.risk_per_share, s.entry_shares, s.realized_pnl,
       s.realized_r, s.peak_price, s.peak_r, s.peak_time, s.peak_day, s.peak_hold_day, s.peak_source,
       s.peak_bars_n, s.peak_close, s.peak_close_r, s.peak_close_day, s.giveback_r, s.capture_pct,
       s.hold_trading_days, s.stop_above_entry_ever, s.partial_taken, s.pnl_attribution,
       t.regime,                      -- ENTRY-STAMPED (the 08-08 rule), never the date join
       s.stop_pct, s.stop_per_adr, s.peak_adr, s.realized_adr
FROM mi_sell_discipline_records s
JOIN mi_live_trades t ON t.id = s.trade_id
WHERE s.signal_type = 'magna53'
ORDER BY s.trade_id;

-- Q4: exit legs + stop fields, the 10-column _508_trades.tsv shape (id, ticker, hard_stop, orb_low,
--     stop_price, hold_days, partial_taken, breakeven_active, remaining_shares, exits).
\echo ===Q4_TRADES===
SELECT t.id, t.ticker, t.hard_stop, t.orb_low, t.stop_price, t.hold_days, t.partial_taken,
       t.breakeven_active, t.remaining_shares, t.exits::text
FROM mi_live_trades t
JOIN mi_sell_discipline_records s ON s.trade_id = t.id
WHERE s.signal_type = 'magna53'
ORDER BY t.id;

-- Q5: daily OHLC over each trade's span (fill_day-1 .. close_day+16d), keyed by trade_id.
\echo ===Q5_DAILY===
SELECT s.trade_id, d.trade_date, d.open_price, d.high_price, d.low_price, d.close
FROM mi_sell_discipline_records s
JOIN mi_daily_closes d ON d.ticker = s.ticker
 AND d.trade_date BETWEEN s.fill_day - 1 AND s.close_day + 16
WHERE s.signal_type = 'magna53'
ORDER BY s.trade_id, d.trade_date;

-- Q6: RTH minute bars, in-hold AND 16 calendar days forward, keyed by trade_id (UTC timestamps,
--     the _508_minute.tsv shape). Live magna53 only — the paper cohort's bars are in the old snapshot.
\echo ===Q6_MINUTE===
SELECT s.trade_id, b.bar_time, b.open, b.high, b.low, b.close
FROM mi_sell_discipline_records s
JOIN mi_intraday_bars b ON b.ticker = s.ticker
 AND (b.bar_time AT TIME ZONE 'America/New_York')::date BETWEEN s.fill_day AND s.close_day + 16
 AND (b.bar_time AT TIME ZONE 'America/New_York')::time >= '09:30'
 AND (b.bar_time AT TIME ZONE 'America/New_York')::time <  '16:00'
WHERE s.signal_type = 'magna53' AND s.account_mode = 'live'
ORDER BY s.trade_id, b.bar_time;
