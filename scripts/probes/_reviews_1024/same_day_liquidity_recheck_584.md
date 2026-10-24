# Review: same_day_liquidity_recheck_584 -- run 2026-10-24 (Sat, PT), read-only, $0

## VERDICT
- Predicate now reads **21 vs threshold 15 -> FIRES** ($100M level; same text reads 46 at $50M, 73 at $25M).
- Action's own result: **pre-registered bar NOT met at any of the four levels** ($10M/$25M/$50M/$100M). Governing one-sided Fisher p (reach to 8xADR over D1..D20 vs gap-matched admitted 9/94 = 9.6%): **0.362 / 0.724 / 0.575 / 0.190**, all >= 0.05 (4 levels tested, nominal p). Leave-one-D0-date-out never crosses 0.05 (lowest 0.090, at $100M).
- Crash cost (settle <= -20% vs D0 open): $50M 41/50 = 82% vs 41/94 = 43.6% gap-matched admitted; median settled -54.4% vs -16.8%. $100M 17/21 = 81%; only 1/21 settles >= +20%.
- Fork for the operator: **none**. The D-1 floors stand as is; admission is his (THE LINE) and nothing is proposed. Optional for the main loop: close the review (answered) or extend at $100M only (4/21 = 19.0% vs 9.6%, p = 0.19, directional and underpowered).

## Predicate reading (the YAML's predicate_sql run verbatim, read-only, at its own $100M level, then the same text at $50M and $25M)
```
BEGIN
=== PRED verbatim (100M, threshold 15)
 count 
-------
    21
(1 row)

=== PRED same text at 50M
 count 
-------
    46
(1 row)

=== PRED same text at 25M
 count 
-------
    73
(1 row)

ROLLBACK
```

## Population (stated before any outcome)
- mi_universe_floor_shadow: 9,767 rows / 2,722 names / 37 scan dates 2026-09-02..2026-10-23; acting floors $5 / 50k on EVERY row; 0 null side flags; 0 backfill rows (created_at ET date == scan_date on all); 0 rejected rows that lacked an at_open read but were `_last`-fallback-eligible (fallback NOT used).
- Rejected 7,432 rows / 1,660 names; admitted 2,335 rows / 1,217 names. In-window (at_open read <= 15 min): rejected 3,354 rows / 1,327 names, admitted 1,081 rows / 734 names (193 rows with gap_at_open >= 10). About 78% of in-window reads are the 09:31 read (minute 1).
- mi_daily_closes through 2026-10-23 (no thin dates since 07-01, 0 duplicate bars). Last D0 with a 20th close = 2026-09-25 (16 D0 dates at $50M).
- Recorder healthy through 10-23: 64-153 in-window rejected rows a day for every scan date 10-05..10-23 (no flatline).
- Cutoff: the 10-15 NEXT said "cutoffs to 10-21"; the run slipped to Sat 10-24 so closes through 10-23 are used. Same verdict at the registered 10-21 cutoff (D0 <= 09-23): $100M 17 names p=0.162; $50M 41 names p=0.591; $25M 65 names p=0.886; $10M 96 names p=0.546.

## What a BROKEN pipeline would show -> checks run
- Clean-name count == the YAML predicate, exact: $100M 21=21, $50M 46=46, $25M 73=73 (rows 21/50/86; $10M 109 names / 142 rows). A bad join or guard breaks the equality.
- Regression to the 10-15 run (filter D0 <= 09-16): $50M 19 names, reach_in 6, reach_ex 3, crash 13; $100M 5 names; admitted gap>=10 4/44 -- ALL reproduce 10-15 exactly, so back-adjusted bars have not drifted (every split on a clean ticker has adjustment_applied = t; GCTK and LHSW splits execute 10-26, after the last bar).
- Outputs not degenerate: reach 8-19% (not 0/100%), crash 74-82% (same direction as 10-13/10-15), reach hits are named real runners (PDSB +114%, NCPL +216% at $10M, VEEA, GRML, GLND, TNON).
- Guard = drop rows with a >4x single-day close jump up inside D0..D20 (dropped: BENF 09-16 and 09-18; BENF's +439% day on 09-23 had no split). Without the guard: $50M 6/51 p=0.440; $100M unchanged (4/21 p=0.190). Verdict unchanged.
- Rows vs names: 4 tickers repeat at $50M (rows 50, names 46). By-name (first row per ticker, admitted likewise) sensitivity: $10M p=0.310, $25M p=0.570, $50M p=0.384 (5/46 vs 6/78), $100M p=0.132 (4/21 vs 6/78). Verdict unchanged.

## Results, H = 20 sessions
Clean = D0 bar, D0 open > 0, all 20 forward bars, 20 prior bars for ADR, no >4x jump up. Admitted gap-matched control (admitted side, in-window, gap_at_open >= 10, same clean rules): 94 rows / 78 names / 17 D0 dates; reach_ex 9 (9.6%), crash 41 (43.6%), median settled -16.8%.
```
level   clean names/rows  reach_ex k/n (Wilson)      GOV p (vs 9/94)  LOO p min-max     reach_in k/n   p(in vs gm)  crash<=-20%      median settled  settle>=+20%
>=$10M  109 / 142         17/142 = 12.0%  (7.6-18.3)   0.362            0.178 - 0.616     24/142 = 16.9% 0.124        105/142 = 73.9%  -42.5%          10
>=$25M   73 /  86          7/86  =  8.1%  (4.0-15.9)   0.724            0.526 - 0.877     12/86  = 14.0% 0.326         68/86  = 79.1%  -46.9%           5
>=$50M   46 /  50          5/50  = 10.0%  (4.3-21.4)   0.575            0.365 - 0.834      9/50  = 18.0% 0.162         41/50  = 82.0%  -54.4%           3
>=$100M  21 /  21          4/21  = 19.0%  (7.7-40.0)   0.190            0.090 - 0.605      5/21  = 23.8% 0.107         17/21  = 81.0%  -54.8%           1
```
- Shown, NOT governing: p vs #570's 8.2% (cross-era, base = D0 close) for reach_ex: $10M 0.074, $25M 0.565, $50M 0.391, $100M 0.088; for reach_in (gap day's own high included): $10M 0.0006, $25M 0.048, $50M 0.019, $100M 0.025. The incl-column hits are largely the gap day's own high (DLXY, MEDS, RETO on 09-16 reach 8xADR only inside D0, then settle -59% / -29% / -99%). 4 levels tested; no multiple-test correction was pre-registered (stated, not applied).
- Crash vs gap-matched admitted, one-sided Fisher: p < 0.0001 at $10M/$25M/$50M, 0.0018 at $100M.
- 5-session horizon (shown only; D0 <= 10-16; admitted gm 11/170 = 6.5%): governing p $10M 0.403, $25M 0.779, $50M 0.567, $100M 0.117; crash 59-70%.
- Names/day the bar would admit (rejected in-window rows clearing it, all 37 scan dates, settled or not): $10M 336 rows = 9.1/day, $25M 201 = 5.4/day, $50M 115 = 3.1/day, $100M 45 = 1.2/day.
- Bar condition (a) "identifiable from the at_open read inside 09:31-09:45" holds by construction (in-window = at_open read <= 15 min); condition (b) "tail density materially above the admitted pool on >= 15 settled names" is what fails.

## Per-row listing, H=20 clean, rejected, in-window

### REJ >= $100M (clean rows)
```
per-row (clean, H=20):
    2026-09-08 BNC    ao $  183.6M m=1 gap   62.8% 8xADR 0.60 | exc_ex +0.29 exc_in +0.29 | reach_ex 0 | settled +9%
    2026-09-10 TNON   ao $  109.2M m=1 gap   77.0% 8xADR 1.42 | exc_ex +1.58 exc_in +1.58 | reach_ex 1 | settled -18%
    2026-09-15 VEEA   ao $  175.2M m=1 gap   88.6% 8xADR 0.99 | exc_ex +1.05 exc_in +1.05 | reach_ex 1 | settled +20%
    2026-09-16 MEDS   ao $  239.6M m=1 gap  164.2% 8xADR 1.54 | exc_ex +0.67 exc_in +2.05 | reach_ex 0 | settled -29%
    2026-09-16 ZTG    ao $  135.8M m=1 gap  247.7% 8xADR 2.20 | exc_ex +0.04 exc_in +0.04 | reach_ex 0 | settled -73%
    2026-09-17 AEMD   ao $  364.0M m=1 gap  490.2% 8xADR 0.85 | exc_ex -0.15 exc_in +0.12 | reach_ex 0 | settled -38%
    2026-09-17 DAIC   ao $  103.8M m=1 gap  102.7% 8xADR 2.24 | exc_ex +0.10 exc_in +0.74 | reach_ex 0 | settled -68%
    2026-09-18 GIPR   ao $  162.7M m=1 gap  173.0% 8xADR 1.65 | exc_ex -0.48 exc_in +0.16 | reach_ex 0 | settled -74%
    2026-09-18 TNMG   ao $  105.2M m=1 gap   74.7% 8xADR 1.12 | exc_ex +0.64 exc_in +0.64 | reach_ex 0 | settled -27%
    2026-09-21 GLND   ao $  164.0M m=1 gap  148.3% 8xADR 0.53 | exc_ex +1.22 exc_in +1.22 | reach_ex 1 | settled +0%
    2026-09-21 GRML   ao $  376.5M m=1 gap  153.6% 8xADR 1.12 | exc_ex +1.48 exc_in +1.48 | reach_ex 1 | settled -23%
    2026-09-22 DCOY   ao $  178.3M m=1 gap   95.0% 8xADR 0.61 | exc_ex -0.09 exc_in +0.48 | reach_ex 0 | settled -78%
    2026-09-22 LHSW   ao $  130.1M m=1 gap  181.8% 8xADR 3.21 | exc_ex -0.34 exc_in +0.06 | reach_ex 0 | settled -43%
    2026-09-22 QNME   ao $  103.8M m=1 gap  115.5% 8xADR 1.59 | exc_ex -0.29 exc_in +0.06 | reach_ex 0 | settled -64%
    2026-09-23 BENF   ao $  296.3M m=1 gap  290.1% 8xADR 2.27 | exc_ex -0.25 exc_in +0.08 | reach_ex 0 | settled -70%
    2026-09-23 IPDN   ao $  116.6M m=1 gap   71.5% 8xADR 1.48 | exc_ex -0.02 exc_in +0.11 | reach_ex 0 | settled -62%
    2026-09-23 WHLR   ao $  132.4M m=1 gap  157.2% 8xADR 1.78 | exc_ex +0.05 exc_in +0.67 | reach_ex 0 | settled -90%
    2026-09-24 APUS   ao $  163.9M m=1 gap  170.1% 8xADR 1.30 | exc_ex +0.41 exc_in +0.41 | reach_ex 0 | settled -55%
    2026-09-24 PFSA   ao $  146.0M m=1 gap   76.6% 8xADR 1.37 | exc_ex -0.22 exc_in +0.19 | reach_ex 0 | settled -71%
    2026-09-25 AIFF   ao $  101.5M m=1 gap   40.3% 8xADR 0.64 | exc_ex +0.05 exc_in +0.25 | reach_ex 0 | settled -46%
    2026-09-25 INLF   ao $  185.0M m=1 gap  118.0% 8xADR 0.61 | exc_ex -0.14 exc_in +0.10 | reach_ex 0 | settled -97%
```

### REJ >= $50M (clean rows)
```
per-row (clean, H=20):
    2026-09-02 LHAI   ao $   63.6M m=1 gap   57.1% 8xADR 0.59 | exc_ex +0.18 exc_in +0.18 | reach_ex 0 | settled -18%
    2026-09-02 PPBT   ao $   84.2M m=1 gap   45.3% 8xADR 0.78 | exc_ex -0.12 exc_in +0.08 | reach_ex 0 | settled -36%
    2026-09-03 MIMI   ao $   57.8M m=1 gap   56.0% 8xADR 1.71 | exc_ex -0.07 exc_in +0.03 | reach_ex 0 | settled -23%
    2026-09-04 AKAN   ao $   67.2M m=1 gap   19.9% 8xADR 0.90 | exc_ex -0.18 exc_in +0.02 | reach_ex 0 | settled -56%
    2026-09-04 IMRN   ao $   91.5M m=1 gap   60.4% 8xADR 0.42 | exc_ex +0.06 exc_in +0.10 | reach_ex 0 | settled -41%
    2026-09-08 ARBE   ao $   56.2M m=1 gap   33.4% 8xADR 0.45 | exc_ex +0.10 exc_in +0.10 | reach_ex 0 | settled -28%
    2026-09-08 BNC    ao $  183.6M m=1 gap   62.8% 8xADR 0.60 | exc_ex +0.29 exc_in +0.29 | reach_ex 0 | settled +9%
    2026-09-08 PDSB   ao $   56.9M m=1 gap  138.2% 8xADR 1.47 | exc_ex +1.77 exc_in +1.77 | reach_ex 1 | settled +114%
    2026-09-08 WYHG   ao $   59.3M m=1 gap   30.5% 8xADR 1.53 | exc_ex -0.05 exc_in +0.12 | reach_ex 0 | settled -31%
    2026-09-09 OLB    ao $   71.5M m=1 gap   35.9% 8xADR 0.96 | exc_ex +0.24 exc_in +0.24 | reach_ex 0 | settled -2%
    2026-09-10 TNON   ao $  109.2M m=1 gap   77.0% 8xADR 1.42 | exc_ex +1.58 exc_in +1.58 | reach_ex 1 | settled -18%
    2026-09-14 BMGL   ao $   85.6M m=1 gap   68.8% 8xADR 0.84 | exc_ex -0.18 exc_in +0.14 | reach_ex 0 | settled -54%
    2026-09-14 NCT    ao $   59.1M m=1 gap   76.9% 8xADR 4.45 | exc_ex +0.14 exc_in +0.14 | reach_ex 0 | settled -89%
    2026-09-15 SUGP   ao $   68.9M m=1 gap   49.0% 8xADR 1.68 | exc_ex -0.37 exc_in +0.16 | reach_ex 0 | settled -65%
    2026-09-15 VEEA   ao $  175.2M m=1 gap   88.6% 8xADR 0.99 | exc_ex +1.05 exc_in +1.05 | reach_ex 1 | settled +20%
    2026-09-16 DLXY   ao $   95.0M m=1 gap  134.2% 8xADR 0.70 | exc_ex +0.24 exc_in +3.36 | reach_ex 0 | settled -59%
    2026-09-16 MEDS   ao $  239.6M m=1 gap  164.2% 8xADR 1.54 | exc_ex +0.67 exc_in +2.05 | reach_ex 0 | settled -29%
    2026-09-16 RETO   ao $   81.8M m=1 gap   36.4% 8xADR 2.43 | exc_ex -0.86 exc_in +3.61 | reach_ex 0 | settled -99%
    2026-09-16 ZTG    ao $  135.8M m=1 gap  247.7% 8xADR 2.20 | exc_ex +0.04 exc_in +0.04 | reach_ex 0 | settled -73%
    2026-09-17 AEMD   ao $  364.0M m=1 gap  490.2% 8xADR 0.85 | exc_ex -0.15 exc_in +0.12 | reach_ex 0 | settled -38%
    2026-09-17 CTNT   ao $   66.4M m=1 gap   94.7% 8xADR 3.29 | exc_ex -0.24 exc_in +0.05 | reach_ex 0 | settled -74%
    2026-09-17 DAIC   ao $  103.8M m=1 gap  102.7% 8xADR 2.24 | exc_ex +0.10 exc_in +0.74 | reach_ex 0 | settled -68%
    2026-09-17 SDST   ao $   79.3M m=1 gap   62.7% 8xADR 1.31 | exc_ex -0.35 exc_in +0.37 | reach_ex 0 | settled -84%
    2026-09-17 TURB   ao $   56.4M m=1 gap   65.6% 8xADR 0.67 | exc_ex -0.13 exc_in +0.33 | reach_ex 0 | settled -43%
    2026-09-18 GIPR   ao $  162.7M m=1 gap  173.0% 8xADR 1.65 | exc_ex -0.48 exc_in +0.16 | reach_ex 0 | settled -74%
    2026-09-18 IMCC   ao $   67.8M m=1 gap   74.7% 8xADR 1.03 | exc_ex +0.76 exc_in +1.67 | reach_ex 0 | settled -57%
    2026-09-18 MEDS   ao $   53.3M m=1 gap   29.7% 8xADR 2.23 | exc_ex -0.10 exc_in +0.05 | reach_ex 0 | settled -56%
    2026-09-18 TNMG   ao $  105.2M m=1 gap   74.7% 8xADR 1.12 | exc_ex +0.64 exc_in +0.64 | reach_ex 0 | settled -27%
    2026-09-21 BTTC   ao $   88.8M m=1 gap   76.5% 8xADR 0.64 | exc_ex +0.39 exc_in +0.52 | reach_ex 0 | settled -46%
    2026-09-21 GLND   ao $  164.0M m=1 gap  148.3% 8xADR 0.53 | exc_ex +1.22 exc_in +1.22 | reach_ex 1 | settled +0%
    2026-09-21 GRML   ao $  376.5M m=1 gap  153.6% 8xADR 1.12 | exc_ex +1.48 exc_in +1.48 | reach_ex 1 | settled -23%
    2026-09-21 NCPL   ao $   55.3M m=1 gap   59.2% 8xADR 2.51 | exc_ex +1.27 exc_in +1.27 | reach_ex 0 | settled +39%
    2026-09-22 DCOY   ao $  178.3M m=1 gap   95.0% 8xADR 0.61 | exc_ex -0.09 exc_in +0.48 | reach_ex 0 | settled -78%
    2026-09-22 GRAB   ao $   54.0M m=10 gap    5.5% 8xADR 0.30 | exc_ex +0.07 exc_in +0.07 | reach_ex 0 | settled -5%
    2026-09-22 IMCC   ao $   54.0M m=1 gap   44.8% 8xADR 1.56 | exc_ex -0.24 exc_in +0.27 | reach_ex 0 | settled -69%
    2026-09-22 LHSW   ao $  130.1M m=1 gap  181.8% 8xADR 3.21 | exc_ex -0.34 exc_in +0.06 | reach_ex 0 | settled -43%
    2026-09-22 QNME   ao $  103.8M m=1 gap  115.5% 8xADR 1.59 | exc_ex -0.29 exc_in +0.06 | reach_ex 0 | settled -64%
    2026-09-22 TOPS   ao $   64.9M m=1 gap   86.8% 8xADR 0.46 | exc_ex -0.42 exc_in +0.00 | reach_ex 0 | settled -67%
    2026-09-23 BENF   ao $  296.3M m=1 gap  290.1% 8xADR 2.27 | exc_ex -0.25 exc_in +0.08 | reach_ex 0 | settled -70%
    2026-09-23 DCOY   ao $   72.5M m=1 gap   50.0% 8xADR 1.19 | exc_ex -0.16 exc_in +0.07 | reach_ex 0 | settled -76%
    2026-09-23 IPDN   ao $  116.6M m=1 gap   71.5% 8xADR 1.48 | exc_ex -0.02 exc_in +0.11 | reach_ex 0 | settled -62%
    2026-09-23 MSS    ao $   55.7M m=1 gap   50.6% 8xADR 0.85 | exc_ex -0.08 exc_in +0.43 | reach_ex 0 | settled -39%
    2026-09-23 VTGN   ao $   89.6M m=1 gap   57.1% 8xADR 0.47 | exc_ex -0.07 exc_in +0.42 | reach_ex 0 | settled -50%
    2026-09-23 WHLR   ao $  132.4M m=1 gap  157.2% 8xADR 1.78 | exc_ex +0.05 exc_in +0.67 | reach_ex 0 | settled -90%
    2026-09-24 APUS   ao $  163.9M m=1 gap  170.1% 8xADR 1.30 | exc_ex +0.41 exc_in +0.41 | reach_ex 0 | settled -55%
    2026-09-24 GCTK   ao $   68.0M m=1 gap   11.8% 8xADR 0.90 | exc_ex -0.03 exc_in +0.34 | reach_ex 0 | settled -75%
    2026-09-24 PFSA   ao $  146.0M m=1 gap   76.6% 8xADR 1.37 | exc_ex -0.22 exc_in +0.19 | reach_ex 0 | settled -71%
    2026-09-25 AIFF   ao $  101.5M m=1 gap   40.3% 8xADR 0.64 | exc_ex +0.05 exc_in +0.25 | reach_ex 0 | settled -46%
    2026-09-25 APUS   ao $   73.7M m=1 gap   41.9% 8xADR 1.58 | exc_ex +0.18 exc_in +0.18 | reach_ex 0 | settled -65%
    2026-09-25 INLF   ao $  185.0M m=1 gap  118.0% 8xADR 0.61 | exc_ex -0.14 exc_in +0.10 | reach_ex 0 | settled -97%
```

## SQL / code that ran
Captured once to the scratchpad (remote temp files /tmp/rv1024_same_day_liquidity_recheck_584_{1..4}.sql, removed after use; BEGIN READ ONLY ... ROLLBACK), analysed locally. The 529-row capture = rejected in-window at_open >= $10M plus admitted in-window gap_at_open >= 10 (cutoffs moved to 2026-10-23 from `scripts/probes/_584_rerun_1015/verify/z2_rows.sql`):
```sql
-- #584 10-15 VERIFIER: per-row outcomes computed ENTIRELY in SQL (no pandas, no reader code).
-- Rows: rejected-side in-window (at_open read <= 15 min) with at_open $vol >= $10M, plus admitted-side in-window with gap_at_open >= 10.
-- Per row, for H in (5, 20): D0 open/close, ADR = mean (H-L)/C over the ticker's 20 most recent bars before D0 (and how many exist),
-- n forward bars D1..DH, close at DH, peak high D0..DH (incl gap day) and D1..DH (ex gap day), max close-to-close ratio D0..DH (the >4x guard).
BEGIN READ ONLY;
COPY (
WITH cal AS (
  SELECT trade_date, (row_number() OVER (ORDER BY trade_date))::int rn
  FROM (SELECT DISTINCT trade_date FROM mi_daily_closes WHERE trade_date BETWEEN DATE '2026-07-01' AND DATE '2026-10-23') x),
s AS (
  SELECT scan_date, ticker, (failed_price_floor OR failed_volume_floor) AS rej,
         failed_price_floor fp, failed_volume_floor fv, gap_pct_at_open g, today_dollar_volume_at_open ao,
         minutes_since_open_at_open m, today_price_at_open p_ao, prev_close
  FROM mi_universe_floor_shadow
  WHERE scan_date <= DATE '2026-10-23' AND today_dollar_volume_at_open IS NOT NULL AND minutes_since_open_at_open <= 15
    AND ( ((failed_price_floor OR failed_volume_floor) AND today_dollar_volume_at_open >= 10000000)
       OR (NOT (failed_price_floor OR failed_volume_floor) AND gap_pct_at_open >= 10) ))
SELECT s.scan_date, s.ticker, s.rej, s.fp, s.fv, s.g, s.ao, s.m, s.p_ao, s.prev_close,
       d0.open_price o0, d0.high_price h0, d0.close c0,
       pre.adr, pre.npre,
       c5.trade_date d5, f5.nfwd nfwd5, f5.cH c5, f5.pk_in pk5_in, f5.pk_ex pk5_ex, f5.maxq maxq5,
       c20.trade_date d20, f20.nfwd nfwd20, f20.cH c20, f20.pk_in pk20_in, f20.pk_ex pk20_ex, f20.maxq maxq20
FROM s
JOIN cal c0 ON c0.trade_date = s.scan_date
LEFT JOIN cal c5  ON c5.rn  = c0.rn + 5
LEFT JOIN cal c20 ON c20.rn = c0.rn + 20
LEFT JOIN mi_daily_closes d0 ON d0.ticker = s.ticker AND d0.trade_date = s.scan_date
LEFT JOIN LATERAL (
  SELECT avg((z.high_price - z.low_price) / NULLIF(z.close, 0)) adr, count(*) npre
  FROM (SELECT high_price, low_price, close FROM mi_daily_closes p
        WHERE p.ticker = s.ticker AND p.trade_date < s.scan_date ORDER BY p.trade_date DESC LIMIT 20) z) pre ON true
LEFT JOIN LATERAL (
  SELECT count(*) FILTER (WHERE w.trade_date > s.scan_date) nfwd,
         max(w.close) FILTER (WHERE w.trade_date = c5.trade_date) cH,
         max(w.high_price) pk_in,
         max(w.high_price) FILTER (WHERE w.trade_date > s.scan_date) pk_ex,
         max(w.q) maxq
  FROM (SELECT d.trade_date, d.close, d.high_price, d.close / NULLIF(lag(d.close) OVER (ORDER BY d.trade_date), 0) q
        FROM mi_daily_closes d WHERE d.ticker = s.ticker AND d.trade_date BETWEEN s.scan_date AND c5.trade_date) w) f5 ON c5.trade_date IS NOT NULL
LEFT JOIN LATERAL (
  SELECT count(*) FILTER (WHERE w.trade_date > s.scan_date) nfwd,
         max(w.close) FILTER (WHERE w.trade_date = c20.trade_date) cH,
         max(w.high_price) pk_in,
         max(w.high_price) FILTER (WHERE w.trade_date > s.scan_date) pk_ex,
         max(w.q) maxq
  FROM (SELECT d.trade_date, d.close, d.high_price, d.close / NULLIF(lag(d.close) OVER (ORDER BY d.trade_date), 0) q
        FROM mi_daily_closes d WHERE d.ticker = s.ticker AND d.trade_date BETWEEN s.scan_date AND c20.trade_date) w) f20 ON c20.trade_date IS NOT NULL
ORDER BY s.scan_date, s.ticker
) TO STDOUT WITH CSV HEADER;
\echo === SPLITS touching any of these rows' windows (execution_date since 08-01)
SELECT sp.ticker, sp.execution_date, sp.split_from, sp.split_to, sp.adjustment_applied
FROM mi_splits sp
WHERE sp.execution_date >= DATE '2026-08-01'
  AND sp.ticker IN (SELECT ticker FROM mi_universe_floor_shadow
                    WHERE scan_date <= DATE '2026-10-23' AND today_dollar_volume_at_open IS NOT NULL AND minutes_since_open_at_open <= 15
                      AND ( ((failed_price_floor OR failed_volume_floor) AND today_dollar_volume_at_open >= 10000000)
                         OR (NOT (failed_price_floor OR failed_volume_floor) AND gap_pct_at_open >= 10)))
ORDER BY 2, 1;

COPY (SELECT trade_date, count(*) n FROM mi_daily_closes WHERE trade_date >= DATE '2026-07-01' GROUP BY 1 ORDER BY 1) TO STDOUT WITH CSV HEADER;
ROLLBACK;
```
Stats script (local, csv + math only; clean-name cross-check, regression, Fisher/Wilson, leave-one-D0-date-out):
```python
import csv, io, math, statistics as st, sys
t=open('w2_rows_clean.out').read().split('\n')
s=next(i for i,l in enumerate(t) if l.startswith('scan_date,'))
e=next(i for i,l in enumerate(t) if l.startswith('=== SPLITS'))
rows=list(csv.DictReader(io.StringIO('\n'.join(t[s:e]))))
F=lambda x: float(x) if x not in ('',None) else None
for r in rows:
    for k in ('g','ao','o0','h0','c0','adr','c5','pk5_in','pk5_ex','maxq5','c20','pk20_in','pk20_ex','maxq20','p_ao','prev_close'): r[k]=F(r[k])
    for k in ('npre','nfwd5','nfwd20','m'): r[k]=int(r[k]) if r[k] else None
    r['rej']=r['rej']=='t'
out=[]
def P(*a):
    x=' '.join(str(y) for y in a); print(x); out.append(x)
def clean(r,H,maxd=None):
    if maxd and r['scan_date']>maxd: return False
    return (r['o0'] or 0)>0 and r[f'c{H}'] is not None and r[f'nfwd{H}']==H and r['npre']==20 and r['adr'] is not None and (r[f'maxq{H}'] or 0)<=4
def ev(r,H):
    a=r['adr']; o=r['o0']
    return dict(rin=(r[f'pk{H}_in']/o-1)>=8*a, rex=(r[f'pk{H}_ex']/o-1)>=8*a, s=r[f'c{H}']/o-1, d=r['scan_date'], t=r['ticker'])
def fg(a,n1,c,n2):
    k=a+c; N=n1+n2
    return sum(math.comb(n1,x)*math.comb(n2,k-x)/math.comb(N,k) for x in range(a,min(n1,k)+1))
def bg(k,n,p=.082): return sum(math.comb(n,x)*p**x*(1-p)**(n-x) for x in range(k,n+1))
def wil(k,n,z=1.96):
    p=k/n; d=1+z*z/n; c=p+z*z/(2*n); a=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n)); return (c-a)/d,(c+a)/d
LV=(10e6,25e6,50e6,100e6)
P('rows parsed',len(rows),'rej',sum(r['rej'] for r in rows),'adm g>=10',sum(not r['rej'] for r in rows),'| scan dates',len({r['scan_date'] for r in rows}))
# STEP 1: clean-count cross-check vs predicate (names, H=20)
P('\n=== STEP 1: clean 20-session NAMES per level vs verbatim predicate (10-24 run: 100M=21, 50M=46, 25M=73) ===')
for lv in LV:
    cl=[r for r in rows if r['rej'] and r['ao']>=lv and clean(r,20)]
    P(f'  >=${int(lv/1e6)}M: clean names {len({r["ticker"] for r in cl})} rows {len(cl)}')
# STEP 2: regression to 10-15 (D0<=09-16)
P('\n=== STEP 2: regression, D0 <= 2026-09-16 (10-15 run: $50M 19 names, reach_in 6, reach_ex 3, crash 13; $100M 5 names; adm g10 4/44) ===')
for H,md in ((20,'2026-09-16'),):
    adm=[ev(r,H) for r in rows if not r['rej'] and clean(r,H,md)]
    P(f'  ADM g10 clean rows {len(adm)} reach_in {sum(e["rin"] for e in adm)} reach_ex {sum(e["rex"] for e in adm)} crash {sum(e["s"]<=-.2 for e in adm)}')
    for lv in LV:
        cl=[r for r in rows if r['rej'] and r['ao']>=lv and clean(r,H,md)]; E=[ev(r,H) for r in cl]
        P(f'  REJ>=${int(lv/1e6)}M: names {len({r["ticker"] for r in cl})} rows {len(cl)} reach_in {sum(e["rin"] for e in E)} reach_ex {sum(e["rex"] for e in E)} crash {sum(e["s"]<=-.2 for e in E)}')
# STEP 3/4: main
for H in (20,5):
    P(f'\n=================== H={H} ===================')
    adm=[ev(r,H) for r in rows if not r['rej'] and clean(r,H)]
    ak_in=sum(e['rin'] for e in adm); ak_ex=sum(e['rex'] for e in adm); ac=sum(e['s']<=-.2 for e in adm)
    P(f'ADM (gap-matched g>=10, in-window, clean): rows {len(adm)} names {len({e["t"] for e in adm})} dates {len({e["d"] for e in adm})} | reach_ex {ak_ex} ({ak_ex/len(adm):.1%}) reach_in {ak_in} | crash {ac} ({ac/len(adm):.1%}) | median settled {st.median(e["s"] for e in adm):+.1%}')
    adm_all=[r for r in rows if not r['rej']]
    for lv in LV:
        clr=[r for r in rows if r['rej'] and r['ao']>=lv]
        cl=[r for r in clr if clean(r,H)]
        gd=[(r['ticker'],r['scan_date']) for r in clr if r[f'c{H}'] is not None and r[f'nfwd{H}']==H and (r['maxq%d'%H] or 0)>4]
        E=[ev(r,H) for r in cl]; n=len(E)
        P(f'\nREJ >= ${int(lv/1e6)}M: clearing names {len({r["ticker"] for r in clr})} rows {len(clr)} | clean names {len({e["t"] for e in E})} rows {n} | guard-dropped {gd}')
        if n==0: continue
        kin=sum(e['rin'] for e in E); kex=sum(e['rex'] for e in E); kc=sum(e['s']<=-.2 for e in E); kw=sum(e['s']>=.2 for e in E)
        ss=sorted(e['s'] for e in E)
        lo,hi=wil(kex,n)
        P(f'  reach_ex {kex}/{n} = {kex/n:.1%} [{lo:.1%}-{hi:.1%}] | reach_in {kin}/{n} = {kin/n:.1%} | crash(<=-20%) {kc}/{n} = {kc/n:.1%} | win(>=+20%) {kw} | settled median {st.median(ss):+.1%} mean {st.mean(ss):+.1%}')
        P(f'  GOVERNING p (Fisher 1-sided, reach_ex vs gap-matched {ak_ex}/{len(adm)}) = {fg(kex,n,ak_ex,len(adm)):.4f} | non-governing: reach_in vs gm {fg(kin,n,ak_in,len(adm)):.4f} | reach_ex vs 8.2% {bg(kex,n):.4f} | reach_in vs 8.2% {bg(kin,n):.4f} | crash vs gm {fg(kc,n,ac,len(adm)):.4f}')
        # leave-one-D0-date-out
        ds=sorted({e['d'] for e in E}|{e['d'] for e in adm}); ps=[]
        for d in ds:
            Er=[e for e in E if e['d']!=d]; Ar=[e for e in adm if e['d']!=d]
            if not Er or not Ar: continue
            ps.append((fg(sum(e['rex'] for e in Er),len(Er),sum(e['rex'] for e in Ar),len(Ar)),d,len(Er),sum(e['rex'] for e in Er)))
        if ps:
            lo_p=min(ps); hi_p=max(ps)
            P(f'  leave-one-D0-date-out governing p: min {lo_p[0]:.4f} (drop {lo_p[1]}) max {hi_p[0]:.4f} (drop {hi_p[1]}, test then {hi_p[3]}/{hi_p[2]}) over {len(ps)} drops; # drops with p<0.05: {sum(p[0]<0.05 for p in ps)}')
        hits=[e for e in E if e['rex']]
        P('  reach_ex hits:',[(e['t'],e['d'][5:],f'{e["s"]:+.0%}') for e in hits])
        if H==20 and lv in (50e6,100e6):
            P('  per-row (clean, H=20):')
            for r,e in sorted(zip(cl,E),key=lambda x:(x[0]['scan_date'],x[0]['ticker'])):
                P(f'    {r["scan_date"]} {r["ticker"]:6s} ao ${r["ao"]/1e6:7.1f}M m={r["m"]} gap {r["g"]:6.1f}% 8xADR {8*r["adr"]:.2f} | exc_ex {r["pk20_ex"]/r["o0"]-1:+.2f} exc_in {r["pk20_in"]/r["o0"]-1:+.2f} | reach_ex {int(e["rex"])} | settled {e["s"]:+.0%}')
    P('\n  multiple-level note: 4 levels tested at nominal p (Bonferroni x4 not pre-registered)')
open('an.out','w').write('\n'.join(out)+'\n')
```

## Proposed YAML / PLAN update (main loop)
- PLAN.md: **none** -- there is no #584 line (the recorder task #584 closed 2026-09-02; this review lives only in data_gated_reviews.yaml).
- data_gated_reviews.yaml `same_day_liquidity_recheck_584`: set `status: done` (the file's vocabulary is pending/done/deferred) and add:
  `resolution_2026_10_24: RAN 2026-10-24 ($0, read-only; scripts/probes/_reviews_1024/same_day_liquidity_recheck_584.md). Predicate 21 vs 15. All four levels have >=15 clean settled rejected-side names (109/73/46/21). Pre-registered bar NOT met at any level: governing one-sided Fisher p (reach_ex vs gap-matched admitted 9/94) 0.362/0.724/0.575/0.190 at $10M/$25M/$50M/$100M, 4 levels tested nominal; leave-one-D0-date-out never < 0.05 (lowest 0.090 at $100M). Crash cost at $50M 82% settle <= -20% vs 43.6% gap-matched, median settled -54.4% vs -16.8%. Regression to the 10-15 run reproduces exactly. The D-1 floors stand as is; admission stays his (THE LINE); nothing goes to him. $100M is directionally higher (4/21 = 19.0% vs 9.6%, p 0.19) and underpowered, not a bar-clear.`
  and `can_fire.threshold_vs_observed`: "21 clean settled $100M names on 2026-10-24 vs bar 15 (predicate fires)".
- Alternative the main loop may pick instead of `done`: keep `pending` and set `earliest_review_date` ~2026-11-19 (D0s through ~10-22 settle, roughly doubling the $100M n). The pre-registered rule is already satisfied, so this is optional.
