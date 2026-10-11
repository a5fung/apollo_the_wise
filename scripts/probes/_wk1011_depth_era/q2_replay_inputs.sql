-- READ-ONLY (SELECT only). #687/#482 flip-day duty, 2026-10-11: EVERY input the #482 recorder
-- reads for its 15 live MAGNA53 fills, captured once so the before/after replay (origin/main's
-- walker vs this branch's, same inputs) runs offline — plus the 144 stored rows as the "before".
\echo === TRADES
SELECT t.id, t.ticker, t.alert_date::text, t.account_mode, t.signal_type, t.entry_attempt,
       t.status, t.entry_price::text, t.entry_shares::text, t.orb_high::text, t.orb_low::text, t.hard_stop::text,
       t.regime, t.exits::text, t.partial_taken, t.total_pnl::text, t.pnl_attribution,
       t.filled_at::text, t.closed_at::text, t.exit_rule
  FROM mi_live_trades t
 WHERE t.signal_type = 'magna53' AND t.filled_at IS NOT NULL
   AND (t.filled_at AT TIME ZONE 'America/New_York')::date >= DATE '2026-08-16'
 ORDER BY t.filled_at, t.id;
\echo === MINUTES
SELECT b.ticker, b.bar_time::text, b.open::text, b.high::text, b.low::text, b.close::text
  FROM mi_intraday_bars b
  JOIN (SELECT DISTINCT ticker, (filled_at AT TIME ZONE 'America/New_York')::date AS d
          FROM mi_live_trades
         WHERE signal_type = 'magna53' AND filled_at IS NOT NULL
           AND (filled_at AT TIME ZONE 'America/New_York')::date >= DATE '2026-08-16') f
    ON f.ticker = b.ticker
   AND b.bar_time >= (f.d::timestamp + time '09:30') AT TIME ZONE 'America/New_York'
   AND b.bar_time <= (f.d::timestamp + time '16:00') AT TIME ZONE 'America/New_York'
 ORDER BY b.ticker, b.bar_time;
\echo === DAILY
SELECT d.ticker, d.trade_date::text, d.open_price::text, d.high_price::text, d.low_price::text, d.close::text, d.volume::text
  FROM mi_daily_closes d
  JOIN (SELECT DISTINCT ticker, alert_date FROM mi_live_trades
         WHERE signal_type = 'magna53' AND filled_at IS NOT NULL
           AND (filled_at AT TIME ZONE 'America/New_York')::date >= DATE '2026-08-16') f
    ON f.ticker = d.ticker
   AND d.trade_date >= f.alert_date - 400
   AND d.trade_date <= DATE '2026-10-09'
 ORDER BY d.ticker, d.trade_date;
\echo === STAMPS
SELECT a.ticker, a.alert_date::text, a.rubric_version, a.score_tier, a.ep_score::text, a.judge_grade, a.judge_tier,
       a.grade_engine_authority, a.setup_class, a.baseline_floor_tier, a.alert_source
  FROM mi_ep_alerts a
  JOIN (SELECT DISTINCT ticker, alert_date FROM mi_live_trades
         WHERE signal_type = 'magna53' AND filled_at IS NOT NULL
           AND (filled_at AT TIME ZONE 'America/New_York')::date >= DATE '2026-08-16') f
    ON f.ticker = a.ticker AND f.alert_date = a.alert_date
 ORDER BY a.ticker, a.alert_date, a.id;
\echo === OVERRIDES
SELECT signal_type, profit_trigger_r::text, breakeven_arm_r::text FROM mi_strategies
 WHERE profit_trigger_r IS NOT NULL OR breakeven_arm_r IS NOT NULL;
\echo === CF_ROWS
SELECT trade_id, arm, target_r::text, breakeven_arm_r::text, outcome, final_reason, realized_r::text, mark_r::text,
       exit_session, sessions_walked, partial_fired, gap_through, stop_price::text, exit_era, exit_rules::text,
       settle_version, settled_session::text, exits::text
  FROM mi_live_fill_counterfactuals ORDER BY trade_id, arm;
