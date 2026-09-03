-- #617 STEP 1 — the universe-admission recall read, capture 1 of 3 (READ-ONLY, $0).
-- Run ONCE on prod and read the saved file many times (CLAUDE.md "capture once, read many"):
--   ssh apollo@87.99.134.162 'docker exec -i apollo-postgres psql -U apollo -d apollo -A -F "|"' \
--       < scripts/probes/_617_population.sql > scripts/probes/_617_population_out.txt
-- Sections (psql -A format: header row, | delimiter, "(N rows)" trailer, "=== NAME ===" banners):
--   POP      every (ticker, session) Jun 1 - Aug 31 2026 in mi_daily_closes whose OPEN gapped >= 5%
--            over the strictly-prior session close OR whose HIGH cleared +9% — the widest set any
--            admission-floor change could plausibly admit — with every D-1 input the live universe
--            floors read (prev close, prev volume), the extension input (min close of the prior 5
--            sessions) and a 20-session $ADV proxy. Gaps are on the SESSION-OPEN basis; the live
--            scan decides on a 09:30-09:45 delayed/real-time price, so the SCAN section carries the
--            live-decided gap where a row exists.
--   SCAN     every mi_ep_scan_log row Jun 1 - Aug 31 (which names ENTERED the funnel, and why they
--            left it) — the #605 reject_stage column is NULL before 2026-08-29; filter_reason is
--            the pre-#605 stage carrier.
--   ALERTS   live-source mi_ep_alerts Jun 1 - Aug 31.
--   TRADES   magna53 mi_live_trades Jun 1 - Aug 31 (any status) — names that became trades.
--   SECTYPES mi_security_types (the P2.0b stock/non-stock classifier the universe loop reads).
--   SCANDAYS one row per scan_date with the first/last scan_time and row count — detects sessions
--            the scanner never ran (a hole is a coverage fact, not a filter).
--   BARSCOV  for every POP pair, the count of stored RTH minute bars that session (what can be
--            replayed from mi_intraday_bars without a fetch).

\echo === POP ===
WITH d AS (
  SELECT ticker, trade_date, open_price, high_price, low_price, close, volume,
         LAG(close)  OVER w AS prev_close,
         LAG(volume) OVER w AS prev_volume,
         LAG(trade_date) OVER w AS prev_date,
         MIN(close) OVER (PARTITION BY ticker ORDER BY trade_date
                          ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING) AS low5_close,
         AVG(close * volume) OVER (PARTITION BY ticker ORDER BY trade_date
                          ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING) AS adv20_dollar,
         COUNT(close) OVER (PARTITION BY ticker ORDER BY trade_date
                          ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING) AS adv20_n
  FROM mi_daily_closes
  WHERE trade_date BETWEEN '2026-04-20' AND '2026-08-31'
  WINDOW w AS (PARTITION BY ticker ORDER BY trade_date)
)
SELECT ticker, trade_date, prev_date, prev_close, prev_volume,
       open_price, high_price, low_price, close, volume,
       ROUND(((open_price - prev_close) / prev_close * 100)::numeric, 2) AS open_gap_pct,
       ROUND(((high_price - prev_close) / prev_close * 100)::numeric, 2) AS high_gap_pct,
       low5_close,
       CASE WHEN low5_close > 0 THEN ROUND(((prev_close - low5_close) / low5_close * 100)::numeric, 1) END AS ext5_pct,
       ROUND(adv20_dollar::numeric, 0) AS adv20_dollar, adv20_n,
       length(ticker) AS tlen
FROM d
WHERE trade_date BETWEEN '2026-06-01' AND '2026-08-31'
  AND prev_close IS NOT NULL AND prev_close > 0
  AND open_price IS NOT NULL AND high_price IS NOT NULL
  AND ( (open_price - prev_close) / prev_close * 100 >= 5.0
        OR (high_price - prev_close) / prev_close * 100 >= 9.0 )
ORDER BY trade_date, ticker;

\echo === SCAN ===
SELECT id, scan_date, ticker, gap_pct, gap_pct_rt, gap_pct_delayed, prev_close, rel_volume,
       filter_reason, ep_score, score_tier, catalyst_quality, reject_stage,
       to_char(scan_time_et AT TIME ZONE 'America/New_York', 'HH24:MI') AS scan_et,
       minutes_since_open, adv, current_price, prev_day_volume, today_volume,
       extension_pct, quality_adv_dollar, atr_pct, market_cap
FROM mi_ep_scan_log
WHERE scan_date BETWEEN '2026-06-01' AND '2026-08-31'
ORDER BY scan_date, ticker, id;

\echo === ALERTS ===
SELECT id, ticker, alert_date, gap_pct, ep_score, score_tier, catalyst_quality, judge_tier,
       to_char(detected_at AT TIME ZONE 'America/New_York', 'HH24:MI') AS detected_et
FROM mi_ep_alerts
WHERE alert_date BETWEEN '2026-06-01' AND '2026-08-31' AND COALESCE(source, 'live') = 'live'
ORDER BY alert_date, ticker;

\echo === TRADES ===
SELECT id, ticker, alert_date, account_mode, status, entry_attempt, orb_high, orb_low,
       entry_price, stop_price, total_pnl
FROM mi_live_trades
WHERE signal_type = 'magna53' AND alert_date BETWEEN '2026-06-01' AND '2026-08-31'
ORDER BY alert_date, ticker, id;

\echo === SECTYPES ===
SELECT ticker, security_type, exchange FROM mi_security_types ORDER BY ticker;

\echo === SCANDAYS ===
SELECT scan_date, count(*) AS rows_n,
       to_char(min(scan_time_et) AT TIME ZONE 'America/New_York', 'HH24:MI') AS first_et,
       to_char(max(scan_time_et) AT TIME ZONE 'America/New_York', 'HH24:MI') AS last_et,
       count(*) FILTER (WHERE filter_reason IS NULL) AS scored_n
FROM mi_ep_scan_log
WHERE scan_date BETWEEN '2026-06-01' AND '2026-08-31'
GROUP BY scan_date ORDER BY scan_date;

\echo === BARSCOV ===
WITH d AS (
  SELECT ticker, trade_date, open_price, high_price,
         LAG(close) OVER (PARTITION BY ticker ORDER BY trade_date) AS prev_close
  FROM mi_daily_closes
  WHERE trade_date BETWEEN '2026-05-20' AND '2026-08-31'
), pop AS (
  SELECT ticker, trade_date FROM d
  WHERE trade_date BETWEEN '2026-06-01' AND '2026-08-31'
    AND prev_close > 0 AND open_price IS NOT NULL AND high_price IS NOT NULL
    AND ( (open_price - prev_close) / prev_close * 100 >= 5.0
          OR (high_price - prev_close) / prev_close * 100 >= 9.0 )
)
SELECT p.ticker, p.trade_date, count(b.bar_time) AS rth_bars,
       bool_or((b.bar_time AT TIME ZONE 'America/New_York')::time = '09:30') AS has_930
FROM pop p
LEFT JOIN mi_intraday_bars b
  ON b.ticker = p.ticker
 AND b.bar_time >= (p.trade_date::timestamp + interval '9 hours 30 minutes') AT TIME ZONE 'America/New_York'
 AND b.bar_time <  (p.trade_date::timestamp + interval '16 hours') AT TIME ZONE 'America/New_York'
GROUP BY p.ticker, p.trade_date
HAVING count(b.bar_time) > 0
ORDER BY p.trade_date, p.ticker;
