-- #594 sample #7 (2026-11-07 page): sample 6's query, every ruled (ticker, date) through 11-04 excluded: sample 5's query (same window, every ruled (ticker, date) excluded); 12 drawn AT RANDOM across both arms (seed 1104) — not by outcome cell — (2026-11-02): sample 4's selection query, window widened to 2026-08-01, every (ticker, date) already ruled excluded.
SET default_transaction_read_only = on;
\echo == ARM_C (HIGH alerts; the winners are wanted this time)
WITH src AS (SELECT a.ticker, a.alert_date AS d, MAX(a.gap_pct) AS gap_pct, MAX(a.ep_score) AS ep_score,
                  NULL::numeric AS ep_bar, MAX(COALESCE(a.catalyst_quality,'?')) AS cat
             FROM mi_ep_alerts a
            WHERE a.alert_date >= DATE '2026-08-01' AND (a.ticker, a.alert_date) NOT IN (('ABCL', DATE '2026-08-10'),('ABVX', DATE '2026-06-03'),('ADVB', DATE '2026-07-24'),('AEHR', DATE '2026-08-14'),('AESI', DATE '2026-09-25'),('AEVA', DATE '2026-08-06'),('AKAM', DATE '2026-09-25'),('ARQQ', DATE '2026-06-15'),('ASPN', DATE '2026-08-06'),('AVAH', DATE '2026-06-02'),('AVAH', DATE '2026-08-13'),('AVGU', DATE '2026-06-02'),('BLMN', DATE '2026-08-05'),('BLZE', DATE '2026-08-04'),('BW', DATE '2026-08-11'),('CAR', DATE '2026-04-01'),('CAR', DATE '2026-04-21'),('CAR', DATE '2026-04-22'),('CCL', DATE '2026-09-29'),('CDNA', DATE '2026-07-16'),('CDRE', DATE '2026-08-06'),('CGEM', DATE '2026-06-08'),('CRWG', DATE '2026-06-01'),('DCTH', DATE '2026-08-06'),('DFTX', DATE '2026-09-14'),('DORM', DATE '2026-08-04'),('EIKN', DATE '2026-08-19'),('FRMI', DATE '2026-08-11'),('GDC', DATE '2026-05-06'),('GNRC', DATE '2026-09-17'),('HAE', DATE '2026-08-18'),('HLIT', DATE '2026-08-13'),('HPE', DATE '2026-06-02'),('HURN', DATE '2026-07-29'),('IBTA', DATE '2026-08-04'),('IOT', DATE '2026-09-04'),('IPCX', DATE '2026-07-29'),('JLHL', DATE '2026-06-08'),('KMT', DATE '2026-08-05'),('KOD', DATE '2026-09-28'),('KRO', DATE '2026-08-06'),('LIFE', DATE '2026-08-04'),('LPTH', DATE '2026-08-14'),('MAN', DATE '2026-07-16'),('MRAM', DATE '2026-05-13'),('MRLN', DATE '2026-06-05'),('MRVI', DATE '2026-08-19'),('MXL', DATE '2026-04-21'),('NESR', DATE '2026-08-10'),('NIQ', DATE '2026-08-11'),('NTRA', DATE '2026-08-07'),('NUAI', DATE '2026-09-21'),('NVTS', DATE '2026-06-03'),('NVTX', DATE '2026-06-03'),('ODD', DATE '2026-09-09'),('OMER', DATE '2026-07-27'),('ONON', DATE '2026-09-22'),('PAGS', DATE '2026-10-05'),('PHVS', DATE '2026-09-08'),('QH', DATE '2026-06-18'),('QTTB', DATE '2026-07-13'),('RARE', DATE '2026-08-20'),('RNG', DATE '2026-07-24'),('ROIV', DATE '2026-09-08'),('RSKD', DATE '2026-08-12'),('RUM', DATE '2026-06-04'),('RXT', DATE '2026-06-16'),('SIG', DATE '2026-09-09'),('TBBB', DATE '2026-08-13'),('VEEE', DATE '2026-07-08'),('WGS', DATE '2026-08-04'),('WYFI', DATE '2026-08-12'),('YOU', DATE '2026-08-05')) AND a.alert_date <= CURRENT_DATE - 30
              AND a.score_tier = 'HIGH'
            GROUP BY a.ticker, a.alert_date),
px AS (
    SELECT c.ticker, c.trade_date, c.open_price, c.close, c.volume,
           LAG(c.close) OVER w AS prev_close,
           AVG(c.volume) OVER (PARTITION BY c.ticker ORDER BY c.trade_date
                               ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING) AS avg_vol20,
           ROW_NUMBER() OVER w AS rn
      FROM mi_daily_closes c
     WHERE c.ticker IN (SELECT ticker FROM src)
    WINDOW w AS (PARTITION BY c.ticker ORDER BY c.trade_date)
),
base AS (
    SELECT s.ticker, s.d AS the_date, s.ep_score, s.cat, p.open_price AS day_open, p.rn,
           (p.open_price / p.prev_close - 1) * 100 AS open_gap, p.volume / NULLIF(p.avg_vol20, 0) AS vol_x
      FROM src s
      JOIN px p ON p.ticker = s.ticker AND p.trade_date = s.d
     WHERE p.open_price > 0 AND p.prev_close > 0
       AND (p.open_price / p.prev_close - 1) * 100 >= 9.0
       AND p.volume >= 3.0 * p.avg_vol20
)
SELECT b.ticker, b.the_date, ROUND(b.open_gap::numeric,1) AS gap, ROUND(b.vol_x::numeric,1) AS vol_x,
       ROUND(b.ep_score::numeric,1) AS score, b.cat,
       ROUND(((MAX(f.close) FILTER (WHERE f.rn = b.rn + 20) / b.day_open) - 1) * 100) AS pct_20d
  FROM base b
  JOIN px f ON f.ticker = b.ticker AND f.rn BETWEEN b.rn + 1 AND b.rn + 20
 GROUP BY b.ticker, b.the_date, b.open_gap, b.vol_x, b.ep_score, b.cat, b.day_open, b.rn
HAVING COUNT(*) = 20 ORDER BY pct_20d ASC;
\echo == ARM_D (scored below the bar; the losers are wanted this time)
WITH src AS (SELECT l.ticker, l.scan_date AS d, MAX(l.gap_pct) AS gap_pct,
                  MAX(l.ep_score) AS ep_score, NULL::numeric AS ep_bar,
                  MAX(COALESCE(l.catalyst_quality,'?')) AS cat
             FROM mi_ep_scan_log l
            WHERE l.scan_date >= DATE '2026-08-01' AND (l.ticker, l.scan_date) NOT IN (('ABCL', DATE '2026-08-10'),('ABVX', DATE '2026-06-03'),('ADVB', DATE '2026-07-24'),('AEHR', DATE '2026-08-14'),('AESI', DATE '2026-09-25'),('AEVA', DATE '2026-08-06'),('AKAM', DATE '2026-09-25'),('ARQQ', DATE '2026-06-15'),('ASPN', DATE '2026-08-06'),('AVAH', DATE '2026-06-02'),('AVAH', DATE '2026-08-13'),('AVGU', DATE '2026-06-02'),('BLMN', DATE '2026-08-05'),('BLZE', DATE '2026-08-04'),('BW', DATE '2026-08-11'),('CAR', DATE '2026-04-01'),('CAR', DATE '2026-04-21'),('CAR', DATE '2026-04-22'),('CCL', DATE '2026-09-29'),('CDNA', DATE '2026-07-16'),('CDRE', DATE '2026-08-06'),('CGEM', DATE '2026-06-08'),('CRWG', DATE '2026-06-01'),('DCTH', DATE '2026-08-06'),('DFTX', DATE '2026-09-14'),('DORM', DATE '2026-08-04'),('EIKN', DATE '2026-08-19'),('FRMI', DATE '2026-08-11'),('GDC', DATE '2026-05-06'),('GNRC', DATE '2026-09-17'),('HAE', DATE '2026-08-18'),('HLIT', DATE '2026-08-13'),('HPE', DATE '2026-06-02'),('HURN', DATE '2026-07-29'),('IBTA', DATE '2026-08-04'),('IOT', DATE '2026-09-04'),('IPCX', DATE '2026-07-29'),('JLHL', DATE '2026-06-08'),('KMT', DATE '2026-08-05'),('KOD', DATE '2026-09-28'),('KRO', DATE '2026-08-06'),('LIFE', DATE '2026-08-04'),('LPTH', DATE '2026-08-14'),('MAN', DATE '2026-07-16'),('MRAM', DATE '2026-05-13'),('MRLN', DATE '2026-06-05'),('MRVI', DATE '2026-08-19'),('MXL', DATE '2026-04-21'),('NESR', DATE '2026-08-10'),('NIQ', DATE '2026-08-11'),('NTRA', DATE '2026-08-07'),('NUAI', DATE '2026-09-21'),('NVTS', DATE '2026-06-03'),('NVTX', DATE '2026-06-03'),('ODD', DATE '2026-09-09'),('OMER', DATE '2026-07-27'),('ONON', DATE '2026-09-22'),('PAGS', DATE '2026-10-05'),('PHVS', DATE '2026-09-08'),('QH', DATE '2026-06-18'),('QTTB', DATE '2026-07-13'),('RARE', DATE '2026-08-20'),('RNG', DATE '2026-07-24'),('ROIV', DATE '2026-09-08'),('RSKD', DATE '2026-08-12'),('RUM', DATE '2026-06-04'),('RXT', DATE '2026-06-16'),('SIG', DATE '2026-09-09'),('TBBB', DATE '2026-08-13'),('VEEE', DATE '2026-07-08'),('WGS', DATE '2026-08-04'),('WYFI', DATE '2026-08-12'),('YOU', DATE '2026-08-05')) AND l.scan_date <= CURRENT_DATE - 30
              AND l.ep_score IS NOT NULL AND l.gap_pct >= 9
              -- ⚠ NEVER SHOW HIM A NAME WE ACTUALLY TOOK. Excluding alerts is not tidiness:
              -- the first run of this probe put MRNA 2026-08-19 in arm B as "we scored it below
              -- the bar and it ran +36%". We ALERTED it at 115.2 and BOUGHT it (trade 374). It
              -- had 37 ticks that day scoring 21.6 to 115.2, and `ORDER BY scan_time_et DESC`
              -- took the LAST one. [[check-what-the-system-already-did]]
              AND NOT EXISTS (SELECT 1 FROM mi_ep_alerts a
                               WHERE a.ticker = l.ticker AND a.alert_date = l.scan_date)
            GROUP BY l.ticker, l.scan_date
              -- The BEST score of the whole day, not a single tick. "We scored it below the bar"
              -- has to mean we never got it above — a name that peaked at 96 and drifted to 21
              -- was not rejected, it was taken.
            HAVING MAX(l.ep_score) < 50),
px AS (
    SELECT c.ticker, c.trade_date, c.open_price, c.close, c.volume,
           LAG(c.close) OVER w AS prev_close,
           AVG(c.volume) OVER (PARTITION BY c.ticker ORDER BY c.trade_date
                               ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING) AS avg_vol20,
           ROW_NUMBER() OVER w AS rn
      FROM mi_daily_closes c
     WHERE c.ticker IN (SELECT ticker FROM src)
    WINDOW w AS (PARTITION BY c.ticker ORDER BY c.trade_date)
),
base AS (
    SELECT s.ticker, s.d AS the_date, s.ep_score, s.cat, p.open_price AS day_open, p.rn,
           (p.open_price / p.prev_close - 1) * 100 AS open_gap, p.volume / NULLIF(p.avg_vol20, 0) AS vol_x
      FROM src s
      JOIN px p ON p.ticker = s.ticker AND p.trade_date = s.d
     WHERE p.open_price > 0 AND p.prev_close > 0
       AND (p.open_price / p.prev_close - 1) * 100 >= 9.0
       AND p.volume >= 3.0 * p.avg_vol20
)
SELECT b.ticker, b.the_date, ROUND(b.open_gap::numeric,1) AS gap, ROUND(b.vol_x::numeric,1) AS vol_x,
       ROUND(b.ep_score::numeric,1) AS score, b.cat,
       ROUND(((MAX(f.close) FILTER (WHERE f.rn = b.rn + 20) / b.day_open) - 1) * 100) AS pct_20d
  FROM base b
  JOIN px f ON f.ticker = b.ticker AND f.rn BETWEEN b.rn + 1 AND b.rn + 20
 GROUP BY b.ticker, b.the_date, b.open_gap, b.vol_x, b.ep_score, b.cat, b.day_open, b.rn
HAVING COUNT(*) = 20 ORDER BY pct_20d DESC;
