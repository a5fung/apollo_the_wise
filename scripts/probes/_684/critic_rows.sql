-- #684 CRITIC — one row per scored (ticker, scan_date) with an INDEPENDENT server-side outcome and a few
-- features, so the study's numbers can be recomputed without its extract or its Python.  Read-only, $0.
-- Dedupe (independent): alerted = any tick with filter_reason NULL and score_tier set; score = the max
-- ep_score among pass ticks when any, else the max ep_score over all scored ticks.
-- Outcome: run_xadr = (max high over the ticker's next 15 daily rows after scan_date - gap-day close)
--          / (mean((h-l)/c) over the ticker's 20 daily rows before scan_date * gap-day close).
\pset format unaligned
\pset fieldsep '|'
\pset footer off
WITH d AS (
  SELECT trade_date FROM mi_daily_closes WHERE trade_date >= DATE '2026-07-01'
  GROUP BY trade_date HAVING count(*) >= 500
), endd AS (
  SELECT trade_date AS e FROM d ORDER BY trade_date DESC OFFSET 15 LIMIT 1
), t AS (
  SELECT l.ticker, l.scan_date, l.ep_score, l.scan_time_et,
         (l.filter_reason IS NULL AND l.score_tier IS NOT NULL) AS is_pass
  FROM mi_ep_scan_log l, endd
  WHERE l.scan_date >= DATE '2026-05-01' AND l.scan_date <= endd.e AND l.ep_score IS NOT NULL
), pr AS (
  SELECT ticker, scan_date, count(*) n_ticks, bool_or(is_pass) alerted,
         COALESCE(max(ep_score) FILTER (WHERE is_pass), max(ep_score)) AS score,
         to_char(min(scan_time_et) FILTER (WHERE is_pass) AT TIME ZONE 'America/New_York', 'HH24:MI') AS first_pass_hhmm,
         to_char(min(scan_time_et) AT TIME ZONE 'America/New_York', 'HH24:MI') AS first_tick_hhmm
  FROM t GROUP BY 1, 2
), maxtick AS (
  SELECT DISTINCT ON (ticker, scan_date) ticker, scan_date,
         to_char(scan_time_et AT TIME ZONE 'America/New_York', 'HH24:MI') AS chosen_hhmm
  FROM t ORDER BY ticker, scan_date, is_pass DESC, ep_score DESC, scan_time_et DESC
), bars AS (
  SELECT m.ticker, m.trade_date, m.open_price o, m.high_price h, m.low_price l, m.close c, m.volume v,
         row_number() OVER (PARTITION BY m.ticker ORDER BY m.trade_date) rn
  FROM mi_daily_closes m
  WHERE m.ticker IN (SELECT DISTINCT ticker FROM pr) AND m.trade_date >= DATE '2025-12-01'
), g AS (
  SELECT pr.*, b.rn AS rn0, b.o AS o0, b.c AS c0, b.h AS h0, b.l AS l0
  FROM pr LEFT JOIN bars b ON b.ticker = pr.ticker AND b.trade_date = pr.scan_date
)
SELECT g.ticker, g.scan_date, g.n_ticks, g.alerted, g.score, g.first_pass_hhmm, g.first_tick_hhmm, mt.chosen_hhmm,
       (SELECT count(*) FROM mi_ep_alerts a WHERE a.ticker = g.ticker AND a.alert_date = g.scan_date AND COALESCE(a.source, 'live') = 'live') AS live_alert_rows,
       g.o0, g.c0,
       (SELECT avg((b.h - b.l) / b.c) FROM bars b WHERE b.ticker = g.ticker AND b.rn BETWEEN g.rn0 - 20 AND g.rn0 - 1 AND b.c > 0) AS adr20,
       (SELECT count(*) FROM bars b WHERE b.ticker = g.ticker AND b.rn BETWEEN g.rn0 - 20 AND g.rn0 - 1) AS n_pre20,
       (SELECT avg(b.c * b.v) FROM bars b WHERE b.ticker = g.ticker AND b.rn BETWEEN g.rn0 - 20 AND g.rn0 - 1) AS dv20,
       (SELECT b.c FROM bars b WHERE b.ticker = g.ticker AND b.rn = g.rn0 - 1) AS prev_close_adj,
       (SELECT max(b.h) FROM bars b WHERE b.ticker = g.ticker AND b.rn BETWEEN g.rn0 + 1 AND g.rn0 + 15) AS maxh15,
       (SELECT count(*) FROM bars b WHERE b.ticker = g.ticker AND b.rn BETWEEN g.rn0 + 1 AND g.rn0 + 15) AS n_fwd,
       (SELECT (max(b.c) - min(b.c)) FROM bars b WHERE b.ticker = g.ticker AND b.rn BETWEEN g.rn0 - 20 AND g.rn0 - 1) AS range20_abs,
       (SELECT min(b.c) FROM bars b WHERE b.ticker = g.ticker AND b.rn BETWEEN g.rn0 - 5 AND g.rn0 - 1) AS min5_close
FROM g LEFT JOIN maxtick mt USING (ticker, scan_date)
ORDER BY g.scan_date, g.ticker;
