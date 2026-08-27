-- SHORTLIST PRE-SCORE replay — ONE capture (read-only), 2026-08-22.
-- Consumed by scripts/ep_rubric_replay.py -> docs/analysis/shortlist_prescore_replay_2026-08-22.md.
-- CAPTURE ONCE, READ MANY (CLAUDE.md cost rule): outputs saved as
-- scripts/probes/_prescore_replay_{boards,themes,outcomes,board0408,outcomes0408}.psv.
-- Never re-run to re-read. Run shape:
--   ssh apollo@87.99.134.162 "docker exec apollo-postgres psql -U apollo -d apollo -A -F'|' -t -c \"<q>\"" > <file>

-- q1 -> _prescore_replay_boards.psv
-- Last-seen state per (scan_date, ticker) — the house day-level read
-- (db.get_ep_scan_log's DISTINCT ON idiom). Caveat stated in the doc: the live
-- shortlist decision is per-tick; last-seen is the settled day picture and has
-- the best ADV coverage (top-50-by-gap got backfilled historically).
SELECT DISTINCT ON (scan_date, ticker)
    scan_date, ticker, gap_pct, prev_close, adv, adv_source, rank_by_gap,
    minutes_since_open, filter_reason, ep_score, score_tier
FROM mi_ep_scan_log
ORDER BY scan_date, ticker, scan_time_et DESC NULLS LAST, id DESC;

-- q2 -> _prescore_replay_themes.psv
-- Historical theme membership IS reconstructible (plan Stage 3): join on
-- theme_date for the same predicate the live R4 set uses.
SELECT theme_date, stage, name, array_to_string(tickers, ' ')
FROM mi_themes
WHERE stage IN ('Accelerating','Mainstream')
ORDER BY theme_date, name;

-- q3 -> _prescore_replay_outcomes.psv
-- $0 uniform outcomes from daily bars (mi_ep_missed_outcomes is a 30d rolling
-- window and its stale-row class corrupted a prior ranking table — computing
-- from bars avoids both).
WITH b AS (SELECT DISTINCT scan_date, ticker FROM mi_ep_scan_log)
SELECT b.scan_date, b.ticker, d0.open_price AS open_d0, d0.close AS close_d0,
       f.max_high_5d, f.close_5d
FROM b
LEFT JOIN mi_daily_closes d0 ON d0.ticker = b.ticker AND d0.trade_date = b.scan_date
LEFT JOIN LATERAL (
  SELECT max(x.high_price) AS max_high_5d,
         (ARRAY(SELECT c2.close FROM mi_daily_closes c2
                WHERE c2.ticker = b.ticker AND c2.trade_date > b.scan_date
                ORDER BY c2.trade_date LIMIT 5))[5] AS close_5d
  FROM (SELECT c.high_price FROM mi_daily_closes c
        WHERE c.ticker = b.ticker AND c.trade_date > b.scan_date
        ORDER BY c.trade_date LIMIT 5) x
) f ON true
ORDER BY b.scan_date, b.ticker;

-- q4 -> _prescore_replay_board0408.psv
-- 2026-04-08 open-tick board reconstruction (the scan log starts 04-13; 13 of
-- the 26 labelled real EPs died 04-08). Official daily prints, same recipe as
-- Stage 0: open gap >= 9%, prev close >= $5, common stock, ticker <= 5 chars.
-- Caveats stated in the doc: mi_security_types membership is TODAY's; ADV20 is
-- mean volume over the prior <=20 bars.
WITH pc AS (SELECT ticker, close AS prev_close FROM mi_daily_closes
            WHERE trade_date = '2026-04-07' AND close >= 5),
     op AS (SELECT ticker, open_price FROM mi_daily_closes
            WHERE trade_date = '2026-04-08' AND open_price > 0),
     board AS (
       SELECT op.ticker, pc.prev_close, op.open_price,
              (op.open_price - pc.prev_close) / pc.prev_close * 100 AS open_gap_pct
       FROM op JOIN pc USING (ticker)
       JOIN mi_security_types st ON st.ticker = op.ticker
            AND st.security_type IN ('CS','ADRC')
       WHERE length(op.ticker) <= 5
         AND (op.open_price - pc.prev_close) / pc.prev_close * 100 >= 9.0),
     adv AS (
       SELECT z.ticker, avg(z.volume) AS adv20 FROM (
         SELECT c.ticker, c.volume,
                row_number() OVER (PARTITION BY c.ticker ORDER BY c.trade_date DESC) rn
         FROM mi_daily_closes c JOIN board b ON b.ticker = c.ticker
         WHERE c.trade_date < '2026-04-08' AND c.trade_date >= '2026-02-01') z
       WHERE z.rn <= 20 GROUP BY z.ticker)
SELECT b.ticker, b.prev_close, b.open_price, b.open_gap_pct, adv.adv20
FROM board b LEFT JOIN adv ON adv.ticker = b.ticker
ORDER BY b.open_gap_pct DESC;

-- q5 -> _prescore_replay_outcomes0408.psv
-- Forward outcomes for the reconstructed 04-08 board (same board CTE).
WITH pc AS (SELECT ticker, close AS prev_close FROM mi_daily_closes
            WHERE trade_date = '2026-04-07' AND close >= 5),
     op AS (SELECT ticker, open_price FROM mi_daily_closes
            WHERE trade_date = '2026-04-08' AND open_price > 0),
     board AS (
       SELECT op.ticker FROM op JOIN pc USING (ticker)
       JOIN mi_security_types st ON st.ticker = op.ticker
            AND st.security_type IN ('CS','ADRC')
       WHERE length(op.ticker) <= 5
         AND (op.open_price - pc.prev_close) / pc.prev_close * 100 >= 9.0)
SELECT b.ticker, d0.open_price AS open_d0, d0.close AS close_d0,
       f.max_high_5d, f.close_5d
FROM board b
LEFT JOIN mi_daily_closes d0 ON d0.ticker = b.ticker AND d0.trade_date = '2026-04-08'
LEFT JOIN LATERAL (
  SELECT max(x.high_price) AS max_high_5d,
         (ARRAY(SELECT c2.close FROM mi_daily_closes c2
                WHERE c2.ticker = b.ticker AND c2.trade_date > DATE '2026-04-08'
                ORDER BY c2.trade_date LIMIT 5))[5] AS close_5d
  FROM (SELECT c.high_price FROM mi_daily_closes c
        WHERE c.ticker = b.ticker AND c.trade_date > DATE '2026-04-08'
        ORDER BY c.trade_date LIMIT 5) x
) f ON true
ORDER BY b.ticker;

-- q6 -> _prescore_replay_advfill.psv  (supplemental, same capture session)
-- The 13 scan-log days 2026-04-13..2026-04-30 predate the adv column being
-- populated (0% coverage; from 2026-05-01 coverage is 100%). Without ADV the
-- pre-score degenerates to a flat-composite ticker-order lottery on exactly
-- those days, so they are backfilled from daily bars (mean volume over the
-- prior <=20 bars — the 04-08 reconstruction's recipe, flagged 'bars_20d' in
-- the replay).
WITH b AS (SELECT DISTINCT scan_date, ticker FROM mi_ep_scan_log
           WHERE scan_date BETWEEN '2026-04-13' AND '2026-04-30')
SELECT b.scan_date, b.ticker,
       (SELECT avg(v.volume) FROM (
            SELECT c.volume FROM mi_daily_closes c
            WHERE c.ticker = b.ticker AND c.trade_date < b.scan_date
            ORDER BY c.trade_date DESC LIMIT 20) v) AS adv20
FROM b ORDER BY b.scan_date, b.ticker;
