# #687 — Does the depth trail beat today's stop? A backfill on a rebuilt EP-like population, 2024-01 → 2026-04 (2026-09-29)

**MEASUREMENT ONLY. $0 — prod read-only (captured once, 06:48–06:53 PT), Polygon minute bars already captured
(no new pulls for this write-up), no LLM calls. Nothing changed, nothing decided. Any change to the live trail or
the runner exit is CHANGE_PROCESS and the operator's call (THE LINE).** Probe: `scripts/probes/_687/backfill.py`
(its docstring is the pre-registration), outputs `backfill_out_final.txt` (the run), `backfill_out_repro.txt`
(the reproduction), `arms_summary.tsv`, `line_tests.tsv`, `arms_per_trade.tsv` and `arms_results.json` (both
git-ignored for size; `backfill.py --final` regenerates them byte-identically from the captures). Every number
carries its n.

**Units.** money-R = profit ÷ the dollars actually at risk on the fill (entry − stop); the stop sits 2 ORB-R under
entry, so 1 money-R = 2 ORB-R on a normal fill. "≥3R / ≥8R kept" counts trades whose WHOLE position made at least
3 / 8 ORB-R. **"Drop-best-2" = the arm's own total minus its own two best trades** (the probe's measure) — NOT the
paired difference minus its two largest contributors; that second cut is mine, post-hoc, and is always labelled
"diff without its top 2". p = week-block sign-flip permutation on the paired difference (blocks = entry week,
5,000 draws, seed 687, two-sided). "Better / worse" = trades where the arm beat / trailed today's stop by > 0.005R.

## ⚠ VERIFIED 2026-09-29 — an independent check reproduced every trade and every entry count with its own code; the conclusions stand; these corrections win over the text below

- **Survives:** the depth rule is +29.46R vs today's stop over 1,505 paired trades (p 0.33), +0.12R without BE and HL,
  −3.60R in 2024, +33.07R held-out (p 0.24); it trails close-only by 17.85R. Close-only is +47.3R (p 0.13): +0.38R in
  2024, +46.94R held-out (p 0.11). Line tests: shallow dips closed back above the line 240 of 286 times, full-day-range
  dips 10 of 82; today's stop sold 215 of the 358 recoveries.
- **Survivorship does not explain the positive level:** 356 gap-days in names that later stopped trading are IN the list
  and lose money (−0.13R a trade vs +0.36R); and because arms are paired on the same trades, survivorship can shift the
  level but not the rule-vs-rule differences.
- **Corrections:** T20_be (hold 20 sessions, stop at entry, after the +8R partial) is **+73.53R, p ≈ 0.066, +44.12R
  without the top two, discovery +28.37R** (not +76.15R / 0.054 / +46.74R / +30.99R — DWAC 2024-03-25 had no bars after
  entry and was valued differently across rules); the +8R partial fires on **234 of 1,533 (15%)**, not 217 (17 fired and
  hit breakeven the same day); **246 tickers** (356 gap-days) stop reporting before the end, not 184; ALPN was stopped
  under today's stop before delisting; T20_hs / S20_hs are understated by 2.79R / 2.08R (the 17 day-0 trades); fill
  labels are 1,389 at the ORB high / 106 open inside the band / 6 pullback (prices and outcomes unchanged); the
  population query applied the floors to split-adjusted values and rounded the volume ratio (the check's rebuild agrees
  on 2,602 of 2,607 gap-days).
- **Caveat that limits the runner result:** this rebuilt list reaches the +8R partial ~15x as often as real EPs have
  (234 of 1,533 vs 1 of 86 live-era trades), so a runner-exit gain here may not transfer to the EPs we actually trade.

## The answer first

- **The depth rule does not beat today's touch stop.** Over 1,505 paired trades it is +29.46R ahead (p 0.33),
  but **+0.12R without two trades** (BE 2025-07 +18.2R, HL 2025-08 +11.1R); it is behind on more trades than
  ahead (144 better / 246 worse).
- **By block:** discovery (2024, n 614) the depth rule is −3.60R vs today (p 0.75), close-only +0.38R (p 0.97) —
  flat. Held-out (2025-01 → 2026-04, n 891) the depth rule is +33.07R (p 0.24), close-only +46.94R (p 0.11) —
  positive only through BE, HL and FCEL (the depth rule is −5.30R without those three).
- **The depth rule also trails plain close-only** by 17.85R: it differs from close-only on 69 of 1,505 trades
  (31 better / 38 worse), and EPSM (−10.79R) and SEZL (−5.60R) — two stocks that fell a full day's range under
  the line and then recovered — carry 16.4R of it. In #685 it beat close-only on the only two trades it touched.
  (Post-hoc comparison; no p.)
- **His observation holds at scale:** 358 of 656 line-test days (55%) closed back above the line, and today's stop
  sold 215 of those 358 (60%). The deeper the dip, the less often it recovers: 240 of 286 shallow dips (under
  ¼ day's range) recovered vs 10 of 82 dips of a full day's range or more. Acting on it still does not clearly pay.
- **Runner exit (after the +8 ORB-R partial, 217 trades):** "hold 20 sessions with the stop at entry" (T20_be, the
  only form orderable live) is +76.15R vs today (p 0.054), ahead in both blocks, still +46.74R without its top 2
  trades — but it is the best of four rules tried, it keeps fewer ≥3R winners (142 vs 174 of 217), and this rebuilt
  list reaches the +8 ORB-R partial 14× as often as real EPs do (217 of 1,533 vs 1 of 86 in #685).
- **Caveat that rides on everything:** this is a REBUILT list, not our alerts — it is far more explosive than what the
  live system trades (see "What this does not answer"). The pre-registration expected "a few dozen at most" runner
  engagements; 217 came in.

## Method and population

- **Reproduction (2026-09-29 10:31 ET):** `python3 scripts/probes/_687/backfill.py --final` re-run from the captures
  into `backfill_out_repro.txt`; every line after the timestamp is identical to `backfill_out_final.txt` (the 10:27
  ET run), and `arms_per_trade.tsv`, `arms_summary.tsv`, `line_tests.tsv`, `arms_results.json` are byte-identical.
- **Population — a REBUILT EP-like list, NOT our live alerts** (`population.py`, rules fixed before any outcome):
  gap ≥ 9% at the open; raw prior close ≥ $5 and raw prior-day volume ≥ 50k (split un-adjusted); 30-day median
  dollar volume ≥ $1M; ATR14 ≤ 15% of price; extension < 50%; common stock / ADR only, delisted names kept;
  one entry per ticker per 60 days; full-day volume ≥ 3× the prior 20-session mean.
- **How it differs from real alerts:** no catalyst, no EP score, no regime threshold, no market-cap floor, no
  pre-market share floor, no theme, no operator judgement — none exists for this history. The volume rule is a
  **look-ahead proxy** (full-day volume is known only at the close; live gates on early RVOL), so it favours days
  that kept trading. Measured difference (its cause is not isolated): the +8 ORB-R partial fires on 217 of 1,533 campaigns (14%) here vs 1 of 86 on
  real EPs (#685); today's stop averages +0.29 money-R a trade here (n 1,505) vs −0.07 on #685's 79 real EPs.
- **Composition:** 2,607 gap-days on 1,571 tickers (184 since delisted); by entry year 2024 1,090 / 2025 1,157 /
  2026 360; prior close under $10 561, $10–20 667, $20–50 695, $50–100 340, $100+ 344; gap 9–12% 812, 12–15% 517,
  15–20% 564, 20–30% 451, 30–50% 180, 50%+ 83; medians gap 14.8%, prior close $21.74, volume 5.0× normal, dollar
  volume $18.9M/day. No ticker over 2% of rows, no month over 15%.
- **Split, fixed in advance:** DISCOVERY = entries in 2024 (1,090 gap-days → 614 paired trades); HELD-OUT = entries
  2025-01-02 → 2026-04-30 (1,517 → 891). Horizon 2026-08-31; 0 trades open at the horizon in any arm; 5 paired
  trades whose stock stopped trading are closed at their last close in every arm.
- **Entry, as the live MAGNA53 order does it:** ORB = the 09:30 one-minute bar; no trade if its range is zero or wider
  than 1.5 × ATR14; stop = entry − 2 ORB-R; submit 09:31 — stop-limit at the ORB high, or a marketable limit if price
  is already above it (skip if that inflates risk past 1.5×); unfilled orders cancel at 10:00.

| entry funnel | count |
|---|---|
| gap-days in the list | 2,607 |
| no readable open (96 no 09:30 bar, 68 minute gaps in the entry window, 1 minute bars disagree with the daily bar — PSTV 2025-09-25) | 165 |
| no trade: opening range wider than 1.5 × ATR (349) or zero (59) | 408 |
| skipped: already too far above the ORB high to chase | 27 |
| never crossed the ORB high by 10:00 | 390 |
| **filled** (1,470 at the ORB high, 116 chased at 09:31, 22 at an open inside the band, 9 on a pullback to the limit) | **1,617** |
| entry-day order of events unknowable from the minute bar (stop and fill/target/breakeven in one bar) | 84 |
| **campaigns** (651 settled on the entry day — identical in every arm; 882 reached day 1) | **1,533** |
| unreadable later on (identical in every arm) | 28 |
| **paired trades** (every arm settled) — 614 discovery / 891 held-out | **1,505** |

- **Effective sample:** 651 of the 1,505 end on the entry day before any trail exists; 402 trades ever tested the
  line; **390 end differently in close-only or the depth rule vs today** — every difference below lives there.
- **Forward walk:** `scripts/probes/_685/study.py` imported unchanged (the #685 instrument): the 16:45 trail at
  max(SMA10, SMA20), breakeven at +3 ORB-R, the 1/3 partial at +8 ORB-R, minute bars on every line-test day (656 of
  656 fetched), daily bars otherwise, gaps through a stop charged at the open. ADR = the 20 sessions before entry.
- **Anchors (all passed before any population number was read):** (a) #685's 79 real trades reproduced — today −5.77R,
  close-only −9.85R, 0 per-trade mismatches; (b) the entry-day builder matches #685's entry-day state on 86 of 86
  campaigns; (c) on #685's 149 ordered alerts the live order path gives the same fill as #685's entry walk on 85 of
  the 89 either filled (4 differ: 3 chase skips, 1 chase fill — the chase logic #685 did not model); Polygon's
  opening bar differs from the stored bar on 7 of 149 days, one fill price flips (TSEM 2026-07-14, $273.25 vs
  $271.50). Polygon's open matches the daily open within 0.5% on 2,510 of 2,511 entry days (44 of 44 split days).
- **Pre-registration check** (the docstring vs the output):
  - Arms (today / close-only / depth at 1.0 × ADR; the four runner arms), the split, and the measures (total, mean,
    drop-best-2, paired difference, p, better/worse, ≥3R/≥8R kept, worst trade, losses beyond −1.5R, held-longer,
    open at horizon, force-closes, R vs planned risk, the line-test table) are all named in advance.
  - The 1-ADR distance is fixed in code (`ST.ADR_MULT = 1.0`) and is the only multiple run — **no re-tuning**.
  - **NOT pre-registered (post-hoc or descriptive):** the median column; the runner table cut to the 217 engaged
    trades (the paired differences are identical to the all-trades table by construction); the top-40 per-trade
    list; the line-test summary counts (≥1-ADR days, reclaim days sold, median depths); the 4th entry-day abstain
    class (6 trades, same kind as the three named); and, mine, every "diff without its top 2" figure, the depth-vs-
    close-only comparison and the depth buckets.
  - **Added after the docstring:** the PSTV 2025-09-25 minute-vs-daily exclusion appeared between the daily-only pass
    (10:22 ET, "never crossed 391") and the final run (10:27 ET, "never crossed 390, join mismatch 1"). It was a
    no-entry in the earlier pass, so no trade outcome moved.
  - **Failed expectation:** the docstring predicted "a few dozen at most" trades reaching the +8 ORB-R partial; 217 did.
  - The pull estimate held: 2,799 entry-day + 656 line-test-day pulls = 3,455 (estimate 3,300–3,800), 0 errors.
  - `backfill.py` is untracked, so the docstring's "written before any outcome" cannot be checked from git; its last
    edit (10:26 ET) came after two runs that print no totals (the daily-only pass and the anchor) and before the
    only final run.

## Exit rules — today vs close-only vs depth

Today = the trail line rests at the broker (touch sells). Close-only = sell at the close below the line; only the
hard stop / breakeven rests. Depth = close-only, plus a resting stop 1 × ADR under the line.

**All (paired n 1,505)**

| rule | n | total R | mean | median | drop-best-2 | vs today | p | better / worse | diff without its top 2 | ≥3R kept | ≥8R kept | worst loss | losses beyond −1.5R |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| today | 1,505 | +437.63 | +0.291 | −0.06 | +393.23 | — | — | — | — | 241 | 88 | −3.62 (ALEX 2025-12-09) | 9 |
| close-only | 1,505 | +484.95 | +0.322 | −0.06 | +437.60 | +47.31 | 0.131 | 154 / 235 | +18.02 | 232 | 93 | −3.62 | 9 |
| depth | 1,505 | +467.10 | +0.310 | −0.04 | +419.88 | +29.46 | 0.332 | 144 / 246 | +0.12 | 231 | 92 | −3.62 | 9 |

**Discovery — entries in 2024 (paired n 614)**

| rule | n | total R | mean | median | drop-best-2 | vs today | p | better / worse | diff without its top 2 | ≥3R kept | ≥8R kept | worst loss | losses beyond −1.5R |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| today | 614 | +231.90 | +0.378 | +0.00 | +187.50 | — | — | — | — | 104 | 36 | −2.00 (HA 2024-08-20) | 3 |
| close-only | 614 | +232.27 | +0.378 | −0.00 | +188.34 | +0.38 | 0.974 | 63 / 92 | −9.59 | 97 | 38 | −2.00 | 3 |
| depth | 614 | +228.29 | +0.372 | −0.00 | +184.55 | −3.60 | 0.746 | 59 / 96 | −13.31 | 96 | 38 | −2.00 | 3 |

**Held-out — entries 2025-01-02 → 2026-04-30 (paired n 891)**

| rule | n | total R | mean | median | drop-best-2 | vs today | p | better / worse | diff without its top 2 | ≥3R kept | ≥8R kept | worst loss | losses beyond −1.5R |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| today | 891 | +205.74 | +0.231 | −0.11 | +182.83 | — | — | — | — | 137 | 52 | −3.62 (ALEX 2025-12-09) | 6 |
| close-only | 891 | +252.67 | +0.284 | −0.09 | +212.12 | +46.94 | 0.106 | 91 / 143 | +17.65 | 135 | 55 | −3.62 | 6 |
| depth | 891 | +238.81 | +0.268 | −0.09 | +201.63 | +33.07 | 0.237 | 85 / 150 | +3.72 | 135 | 54 | −3.62 | 6 |

- **Where it moves (paired, all):** the biggest gains for holding are BE 2025-07-24 (today +4.67 → depth +22.88),
  HL 2025-08-07 (+3.17 → +14.30), FCEL 2026-04-29 (+0.70 → +9.72), AXGN 2024-01-05 (+13.86 → +19.40); the biggest
  cost is EPSM 2025-04-24 (today +10.06, close-only +17.73, depth +6.94 — the depth stop sold a day that recovered).
- **Depth vs close-only (post-hoc, no p):** −17.85R all (31 better / 38 worse of 69 that differ), −3.98R discovery
  (13 / 17), −13.87R held-out (18 / 21).
- Worst loss and the losses beyond −1.5R are the same 9 trades in every arm (8 overnight gaps through the stop, 1 entry-day loss).

## Runner exits after the +8R partial

Pre-partial every runner rule IS today's stop. After the 1/3 partial fires: **T20** holds 20 sessions and sells at
the 20th close; **S20** sells at the first close below the 20-day average. Floor: **_be** = stop at entry (orderable
live), **_hs** = the hard stop stays (the 08-29 sweep's literal; NOT orderable live — the stop only rises). Why ≥8R
kept is 88 of 217 when all 217 fired the +8R partial: the partial is 1/3 of the position, so the whole trade reaches
8 ORB-R only if the runner also ran.

**Engaged trades only — the partial fired (n 217: 89 discovery / 128 held-out; 79 of the 217 fired on the entry day)**

| block | rule | n | total R | mean | median | drop-best-2 | vs today | p | better / worse | diff without its top 2 | ≥3R kept | ≥8R kept | worst loss | losses beyond −1.5R |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| all | today | 217 | +870.00 | +4.009 | +3.53 | +825.60 | — | — | — | — | 174 | 88 | −0.58 (ABAT 2025-10-13) | 0 |
| all | T20_hs | 217 | +956.84 | +4.409 | +3.74 | +907.44 | +86.84 | 0.044 | 102 / 110 | +57.43 | 157 | 96 | −0.83 (MHK 2024-07-26) | 0 |
| all | S20_hs | 217 | +959.83 | +4.423 | +3.38 | +870.46 | +89.83 | 0.221 | 73 / 139 | +6.46 | 168 | 84 | −0.83 | 0 |
| all | **T20_be** | 217 | +946.15 | +4.360 | +3.65 | +896.75 | **+76.15** | **0.054** | 91 / 87 | **+46.74** | 142 | 90 | −0.58 | 0 |
| all | S20_be | 217 | +916.35 | +4.223 | +3.23 | +849.15 | +46.35 | 0.423 | 65 / 113 | −10.67 | 160 | 80 | −0.58 | 0 |
| disc | today | 89 | +384.27 | +4.318 | +3.63 | +339.87 | — | — | — | — | 69 | 36 | −0.40 (RLAY 2024-09-09) | 0 |
| disc | T20_hs | 89 | +406.52 | +4.568 | +3.77 | +357.12 | +22.25 | 0.372 | 40 / 46 | −0.51 | 60 | 40 | −0.83 | 0 |
| disc | S20_hs | 89 | +385.75 | +4.334 | +3.38 | +338.16 | +1.48 | 0.967 | 32 / 54 | −32.73 | 68 | 34 | −0.83 | 0 |
| disc | **T20_be** | 89 | +415.26 | +4.666 | +3.68 | +365.86 | **+30.99** | 0.171 | 37 / 34 | **+8.23** | 56 | 39 | −0.40 | 0 |
| disc | S20_be | 89 | +393.67 | +4.423 | +3.23 | +346.08 | +9.40 | 0.798 | 29 / 42 | −24.81 | 65 | 33 | −0.40 | 0 |
| held | today | 128 | +485.73 | +3.795 | +3.35 | +462.83 | — | — | — | — | 105 | 52 | −0.58 | 0 |
| held | T20_hs | 128 | +550.32 | +4.299 | +3.73 | +518.56 | +64.59 | 0.087 | 62 / 64 | +42.75 | 97 | 56 | −0.58 | 0 |
| held | S20_hs | 128 | +574.08 | +4.485 | +3.38 | +484.71 | +88.35 | 0.193 | 41 / 85 | +4.98 | 100 | 50 | −0.58 | 0 |
| held | **T20_be** | 128 | +530.89 | +4.148 | +3.65 | +499.13 | **+45.16** | 0.180 | 54 / 53 | **+23.32** | 86 | 51 | −0.58 | 0 |
| held | S20_be | 128 | +522.69 | +4.083 | +3.22 | +459.80 | +36.96 | 0.514 | 36 / 71 | −18.09 | 95 | 47 | −0.58 | 0 |

**All trades (paired n 1,505: 614 / 891; the 1,288 not engaged are identical to today in every runner arm)**

| block | rule | n | total R | mean | median | drop-best-2 | vs today | p | better / worse | ≥3R kept | ≥8R kept | worst loss | losses beyond −1.5R |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| all | today | 1,505 | +437.63 | +0.291 | −0.06 | +393.23 | — | — | — | 241 | 88 | −3.62 | 9 |
| all | T20_hs | 1,505 | +524.48 | +0.348 | −0.06 | +475.08 | +86.84 | 0.041 | 102 / 110 | 224 | 96 | −3.62 | 9 |
| all | S20_hs | 1,505 | +527.47 | +0.350 | −0.06 | +438.10 | +89.83 | 0.222 | 73 / 139 | 235 | 84 | −3.62 | 9 |
| all | T20_be | 1,505 | +513.79 | +0.341 | −0.06 | +464.39 | +76.15 | 0.052 | 91 / 87 | 209 | 90 | −3.62 | 9 |
| all | S20_be | 1,505 | +483.99 | +0.322 | −0.06 | +416.79 | +46.35 | 0.440 | 65 / 113 | 227 | 80 | −3.62 | 9 |
| disc | today | 614 | +231.90 | +0.378 | +0.00 | +187.50 | — | — | — | 104 | 36 | −2.00 | 3 |
| disc | T20_hs | 614 | +254.15 | +0.414 | −0.00 | +204.75 | +22.25 | 0.364 | 40 / 46 | 95 | 40 | −2.00 | 3 |
| disc | S20_hs | 614 | +233.38 | +0.380 | −0.00 | +185.79 | +1.48 | 0.969 | 32 / 54 | 103 | 34 | −2.00 | 3 |
| disc | T20_be | 614 | +262.89 | +0.428 | +0.00 | +213.49 | +30.99 | 0.184 | 37 / 34 | 91 | 39 | −2.00 | 3 |
| disc | S20_be | 614 | +241.29 | +0.393 | +0.00 | +193.71 | +9.40 | 0.795 | 29 / 42 | 100 | 33 | −2.00 | 3 |
| held | today | 891 | +205.74 | +0.231 | −0.11 | +182.83 | — | — | — | 137 | 52 | −3.62 | 6 |
| held | T20_hs | 891 | +270.33 | +0.303 | −0.11 | +238.57 | +64.59 | 0.083 | 62 / 64 | 129 | 56 | −3.62 | 6 |
| held | S20_hs | 891 | +294.09 | +0.330 | −0.11 | +204.72 | +88.35 | 0.188 | 41 / 85 | 132 | 50 | −3.62 | 6 |
| held | T20_be | 891 | +250.90 | +0.282 | −0.11 | +219.14 | +45.16 | 0.182 | 54 / 53 | 118 | 51 | −3.62 | 6 |
| held | S20_be | 891 | +242.69 | +0.272 | −0.11 | +179.81 | +36.96 | 0.504 | 36 / 71 | 127 | 47 | −3.62 | 6 |

- The p values differ by up to 0.017 between the two tables only through permutation noise (same differences, more
  zero-difference weeks).
- **T20_be is the only rule ahead in both blocks that stays ahead without its top 2 or top 3 trades** (+36.90R all,
  +3.68R discovery, +15.85R held-out without the top 3); its median trade is unchanged (median difference 0.00).
  The 20-day-average rules (S20) collapse without their top 2 (DELL +46.1R, BE +37.3R carry S20_hs).
- **Four runner rules were tried; the best p is 0.044–0.054** — that is not a separation once four are tested.
- **Against the 08-29 sweep** (n 194, the retired +2R partial): the same direction — hold-20 led there too (+0.36R vs
  +0.14R a trade, i.e. +0.22R ahead, not significant). Here, under today's +8 ORB-R partial, T20_be is +0.35R a
  trade ahead on the 217 engaged.

## Line tests

A line-test day = a held day (on the close-only path) whose low reached the trail line. RECLAIM = closed at/above
the line; SLICE = closed below. Depth = how far the low went under the line, in multiples of the stock's normal
daily range (ADR). Minute bars on 656 of 656 days.

| block | days | trades | reclaim | slice | days ≥ 1 ADR under | of those, reclaimed | today's stop sold a reclaim day | depth rule sold a reclaim day | median depth, reclaim | median depth, slice |
|---|---|---|---|---|---|---|---|---|---|---|
| all | 656 | 402 | 358 (55%) | 298 | 82 | 10 | 215 of 358 (60%) | 22 of 358 (6%) | 0.15 ADR (0.74% of price) | 0.60 ADR (2.88%) |
| disc | 249 | 160 | 136 (55%) | 113 | 35 | 5 | 80 of 136 (59%) | 9 of 136 | 0.15 | 0.62 |
| held | 407 | 242 | 222 (55%) | 185 | 47 | 5 | 135 of 222 (61%) | 13 of 222 | 0.15 | 0.59 |

| depth under the line (all) | days | reclaimed | rate |
|---|---|---|---|
| under ¼ ADR | 286 | 240 | 84% |
| ¼ – ½ ADR | 150 | 70 | 47% |
| ½ – 1 ADR | 138 | 38 | 28% |
| 1 ADR or more | 82 | 10 | 12% |

- Of the depth rule's 22 reclaim-day sales, 9 fell on days at least 1 ADR deep (9 of the 10 such days that recovered;
  close-only held through 6 of them — SMCI, APPF, ARIS, EPSM, SEZL, ATEC — and EPSM and SEZL are the costly ones);
  the other 13 are the breakeven / hard stop that close-only hits too.
- Descriptive, and it supports the rule's premise: a dip of a full day's range recovers 1 time in 8 (10 of 82),
  a shallow one 5 times in 6 (240 of 286). The totals above say the premise alone does not turn into money.

## How this compares with #685 and the 09-06 ruling

| read | population | n | close-only vs today | depth vs today | depth vs close-only |
|---|---|---|---|---|---|
| 09-06 ruling (`magna53_ep.md`) | admitted MAGNA53, era C, to 08-31 | 62 | −5.30R | not run | — |
| #685 (verified) | real EPs, 2026-05-11 → 09-25 | 79 | −4.08R (p 0.061; 8 / 12) | −1.82R (p 0.19); ~−0.6R at FTK's realistic fill | +2.26R, all on FTK and INFQ |
| #685 without FTK, INFQ | | 77 | +0.70R | +0.70R | 0 |
| **#687 all** | rebuilt, 2024-01 → 2026-04 | 1,505 | +47.31R (p 0.131; 154 / 235) | +29.46R (p 0.332; 144 / 246) | −17.85R (31 / 38) |
| #687 without BE, HL | | 1,503 | +18.02R | +0.12R | — |
| #687 discovery | 2024 | 614 | +0.38R (p 0.974) | −3.60R (p 0.746) | −3.98R |
| #687 held-out | 2025-01 → 2026-04 | 891 | +46.94R (p 0.106) | +33.07R (p 0.237) | −13.87R |

- **Same shape, opposite sign, never significant:** on real EPs two slice days (FTK, INFQ) made holding cost ~4R; on
  the rebuilt list two runners (BE, HL) make holding pay ~29R. Take the two out of either read and every rule is
  within noise of today's stop.
- **Per trade, holding loses more often than it wins in every read** (#685 close-only 8 better / 12 worse; here
  154 / 235), and wins bigger when it wins.
- **The depth rule's one clean property in #685 — it never sold a day that recovered (0 of 19) — does not hold
  at scale:** it sold on 9 of 358 recovering days here (close-only held through 6 of them), and two of those (EPSM,
  SEZL) cost 16.4R vs close-only.
- **The 09-06 ruling** kept the trail line and its intraday timing because close-only lost (−5.3R on 62). Nothing here
  overturns it: discovery is flat and the held-out gain rests on two trades.
- **Runner:** `runner_rule_sweep_recut` stays armed and is NOT closed by this — it counts 40 era-D live closes
  (reads 3). This is the era-D re-cut evidence its action asks for, on a population that reaches the partial 14×
  as often as real EPs.

## What this does not answer

- **Whether these rules behave the same on OUR EPs.** The rebuilt list is a different animal: no catalyst, score,
  regime, market-cap or pre-market gate; a look-ahead volume rule; the +8 ORB-R partial fires on 217 of 1,533 (14%)
  vs 1 of 86 real EPs; today's stop averages +0.29R a trade here vs −0.07R on real EPs. The pre-registered
  expectation of "a few dozen at most" partials failed. Every conclusion, the runner one most, rides on this.
- **EP profitability.** The absolute totals (+437.63R for today's stop) measure the rebuilt list, not the strategy.
- **Execution the replay does not model:** safeguards (max positions, breakers, daily loss), sizing, the fade guard,
  slippage, broker rejects. Close sales book at the 16:00 close; live sells at 16:45 after hours (09-11 OKTA was
  rejected on that path). The partial and breakeven fill on the minute bar; live polls every 5 minutes — with 217
  partials that matters more here than in #685.
- **The entry-price proxy:** "latest trade at 09:31" = the 09:31 bar's open; under the 09:30 close instead, 55 entry
  verdicts flip (25 chase skips become fills, 5 fills become no-entry, 23 fill lower, 2 skips become no-entry). Not
  re-run through the arms.
- **Abstains** (identical in every arm, so the pairing is unmoved): 165 unreadable entries, 84 unorderable entry
  days, 28 unreadable later days; 5 force-closed delistings.
- **A p value for depth vs close-only** (not pre-registered), and any depth other than 1.0 × ADR (deliberately not run).
- **Out-of-sample for the runner rule:** four rules on one population; the 08-29 sweep is a different population
  under a retired partial, not a replication.

## Proposal for his ruling

The depth rule does not earn a change: it is flat in 2024 (−3.60R, p 0.75), its 2025–26 gain is two trades (BE,
HL), it is behind today's stop on more trades than it is ahead (144 / 246), and it trails plain close-only by 17.85R;
#685 on real EPs pointed the other way on two trades of its own. PLAN gates the forward tracker (Part 2) on Part 1
supporting the depth rule, and it does not — so the fork is his: **(a)** keep today's touch stop, close the #687
depth-trail question, and do not build the tracker; or **(b)** keep today's stop live and build the shadow tracker
anyway (no money, no order change) as the only out-of-sample path — knowing the answer is decided by rare runners
(two in 1,505 here) and the live rate is ~9 line tests a month, so it would take years to settle. Separately, for the
runner after the +8 ORB-R partial: T20_be (hold 20 sessions, stop at entry) is the only candidate that holds across
both blocks and without its top trades (+76.15R on 217, p 0.054), but it is the best of four on a list that reaches
the partial 14× as often as real EPs; the fork is **(i)** name it as the candidate `runner_rule_sweep_recut` tests
when it fires, no change now, or **(ii)** also shadow it beside live positions (1 of 86 real EPs reached the partial in May–Sep, so ~1 read every 4–5 months).
**Rec: (a) and (i).** Any change to the live trail or the runner exit is CHANGE_PROCESS and his call.

## THE LINE

- Nothing here is a change. No live code, PLAN.md or prod state was touched; the prod reads were SELECTs captured once.
- Any change to the live trail (close-only, depth, or anything else) or to the runner exit is CHANGE_PROCESS, needs his
  sign-off, and would be backed by a rebuilt-population replay — not by his own EPs.
- **A catastrophic stop must always rest at the broker.** Close-only keeps only the hard stop / breakeven resting; the
  depth rule keeps line − 1 ADR. Losses beyond −1.5R are the same 9 of 1,505 in every arm here — "no extra blow-up on
  1,505 trades" is not "cannot blow up".
- T20_hs / S20_hs step the stop DOWN from entry after the partial; live's raise-only stop cannot do that, so only the
  _be forms are candidates.
