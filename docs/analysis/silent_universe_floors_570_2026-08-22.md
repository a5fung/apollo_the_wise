# #570 — The silent day-1 universe floors: inventory + what they drop (2026-08-22)

**MEASUREMENT ONLY. No criterion changed, nothing committed to the funnel. Any change to any
floor here is entry discipline = THE LINE: CHANGE_PROCESS + operator sign-off.**

Principles engaged: **P1** (a real EP must never be missed — a false exclusion leaves no trace),
**P3** (tail-first, a median cannot see a 10x), **P5** (both directions — winners admitted AND
losers excluded), **P8** (all reads conditional on the current selector), **P9** (loose admission
must be paid for by downstream selectivity).

## The question

Every gate in `mi_ep_missed_outcomes` leaves a row. The floors below leave **nothing** — a name
they drop has no row, no skip_reason, no scan-log line, and never reaches `_rt_universe`, so even
the #489 real-time miss watchdog cannot see it. The 08-16 missed-winner attribution
(`missed_winners_why_2026-08-16.txt`) found 12 of 63 true detection misses died on two of these
floors, carrying the fattest tails of any miss class (median 21.9×ADR vs 11.3× for all missed).
That probe was conditioned on the winner cohort. **This card reconstructs the whole excluded
population, unconditioned**, from `mi_daily_closes` (3.3M bars, 14,687 tickers, 2025-07-14 →
2026-08-21 — full OHLCV, zero nulls).

---

## STAGE 1 — The inventory

The day-1 universe is built inside `run_ep_scan`'s snapshot loop
(`agents/market_intelligence/ep_detector.py:2550-2597`). Every `continue` before
`candidates.append` is invisible. In loop order:

| # | Floor | Where (constant → applied) | Value | Trace left |
|---|---|---|---|---|
| 1 | Ticker shape (warrants/units/ETF list) | `ep_detector.py:154` (`MAX_TICKER_LEN`), `constants.py:481` (`SKIP_TICKERS`) → `:2553` | len>5, ".", list | **none** — also dropped at ingest (`db.py:8810`), so NOT reconstructible |
| 2 | Non-stock security type | `mi_security_types` NOT IN (CS, ADRC) → `:2555` | — | **none** |
| 3 | Unclassified fail-safe (P2.0b) | `:2564` | not yet in `mi_security_types` | aggregate count in container log only |
| 4 | **Prior-day close floor** | `ep_detector.py:153` (`MIN_PREV_CLOSE`) → `:2569` | **$5.00** | **none** |
| 5 | **Prior-day volume floor** | `ep_detector.py:155` (`MIN_PREV_DAY_VOLUME`) → `:2574` | **50,000 sh** | **none** |
| 6 | No current price in snapshot | `:2587` | — | **none** (data availability, not policy) |
| 7 | Pass-1 gap floor | `:2591` (`_pass1_gap_floor`) | 9.0% (5.0% superset while Pass-2 on) | none below the floor; priced separately in #577's decision table; the ARGX 09:31-recheck arm is #559 |

**Floors 4+5 are the card's subject** — real selection rules, never logged, reading the PRIOR
day while the opportunity is created ON the gap day.

**Universe-level scale (measured, capture `570_dropcounts.psv`):** of ~5,160 CS/ADRC names with a
D-1 bar, **~2,000 per day (39%) are outside the scannable universe before any gap is measured** —
~1,310/day on the $5 close floor, ~1,090/day on the 50k volume floor, ~380/day on both.

### Adjacent floors audited — they do NOT drop names (direction matters)

- **`rs_engine.py:54-60`** — `MIN_PRICE` $5, `MIN_DOLLAR_VOL` $10M (+ common-stock and length
  filters at `rs_engine.py:302-320`) bound what `mi_stock_scores` keeps: **2,444 rows** on
  2026-08-21 (prod-counted), vs ~5,160 CS/ADRC names with bars. Effect on the EP scan is
  **degradation, not exclusion**: a name outside the retention has no `adv_20`, so
  `_snap_candidate` (`ep_detector.py:1795-1800`) falls back to **prevDay volume as its ADV**
  (`adv_source="pending"`) — rel_volume is then measured against a possibly-wrong base. Also the
  documented `rs_rank` denominator effect (2,444, not ~9,700).
- **`db.py:7856` `get_top_dollar_volume_universe` ($5M) + `minute_volume.py:69`
  `UNIVERSE_MIN_DOLLAR_VOLUME` ($5M)** — scope which names get pm_rvol baselines. A name below
  the floor has no baseline and the RVOL@T gate **fails open**
  (`MIN_BASELINE_N_FOR_GATE`, `ep_detector.py:2930`). So this floor silently **disables a
  protective gate** for ~60% of the universe; it excludes nobody.
- **OTC** — `include_otc=false` in both the live snapshot (`collector.py:222`) and grouped daily
  (`collector.py:204`). The whole OTC market is invisible to the scanner AND to this
  reconstruction — consistent on both sides, unmeasurable here.

---

## STAGE 2 — What the floors drop, and what those names did

### Method (capture once: `scratchpad/570_candidates.psv`, 27,904 rows + `570_jumps.psv`)

- Window 2025-08-15 → 2026-08-20, **255 sessions**. Would-be candidate = **open gap ≥ 10%** vs
  D-1 close (the floor for all but the last 2 sessions of the window).
- Classes: **P** (prev close <$5 only) · **V** (prev volume <50k only) · **PV** (both) ·
  **PASS** (cleared both, currently CS/ADRC = the real funnel's entrance) · **U** (not in
  `mi_security_types` today) · **T** (classified non-stock — intentional).
- Guards: Nasdaq test symbols (Z?ZZT) removed; **discontinuity guard** — any row whose forward
  window contains a >4× single-day close jump (unadjusted reverse splits; `mi_splits` only
  explained 6 of the top tail names) is excluded from all tail statistics. Removed 789 P /
  347 V / 238 PV / 148 PASS rows.
- **Proxy validated against the live scanner**: all 12 PASS names on 08-14 appear in the real
  `mi_ep_scan_log` that day (the proxy under-counts — 13 more premarket gappers faded below 10%
  by open); of 254 silent-class rows 08-03→08-14, only **3 (1.2%)** were really scanned (DAAQ,
  ULBI 49,488 sh, VATE 49,317 sh — snapshot prevDay.v vs grouped-daily disagreement at the
  line), so the kill-set reconstruction overcounts by ~1%.
- The 08-16 probe's B1 winners reproduce exactly (NPT 03-03 V; ELPW 04-08 and 04-22 V; BYND
  10-17 P).
- **Every outcome below is an EXCURSION (peak of the next 20 sessions vs D0 open), not a fill.**

### Result 1 — the invisible reject pile is twice the size of the visible funnel entrance

Would-be candidates per day (open gap ≥10%, CS/ADRC): **P 15.6 · V 5.9 · PV 5.0 = 26.5/day
silently dropped**, vs **12.2/day PASS** — the names the funnel actually sees and can log.

### Result 2 — per class, tail AND median (P3, P5)

| class | rows/day | med gap | med D0 $vol | excursion med / P90 | ≥8×ADR density (clean) | settled 20-session close (med) |
|---|---|---|---|---|---|---|
| P (<$5) | 15.6 | 25.5% | $10.5M | +20.6% / +120.7% | **12.2%** (382 rows / 283 names) | **−19.0%** |
| V (<50k sh) | 5.9 | 28.1% | $0.4M | +16.1% / +96.3% | 10.0% (114 / 86) | **−25.8%** |
| PV (both) | 5.0 | 17.8% | $0.06M | +19.2% / +104.4% | **13.0%** (136 / 103) | −14.7% |
| **PASS (baseline)** | 12.2 | 16.2% | $86.9M | +13.0% / +64.6% | **8.2%** (237 / 206) | −11.7% |
| U (unclassified)* | 12.8 | 20.5% | ~$0 | +17.2% / +102.8% | 10.2% | −15.1% |
| T (non-stock) | 57.7 | 16.6% | ~$0 | +18.9% / +100.8% | 10.5% | −14.8% |

\* U uses today's `mi_security_types` state — historical unclassified state is unknowable (the
table keeps no history). Median D0 dollar volume ~$0: mostly delisted/foreign-line junk.

**Both directions, honestly:** the floors are **protective on the median** — the silent classes
settle at −15% to −26% twenty sessions later vs −12% for PASS. And they are **costly in the
tail** — every silent class carries a fatter ≥8×ADR excursion density than the pool we actually
admit (11.9% combined clean vs 8.2% PASS).

### Result 3 — the mechanism is real: D-1-invisible, tier-A on D0 (DoD b)

The floors read D-1; the event that makes a name tradeable happens on D0. Measured:

- **6.1 rows/day** of silent-floor names did ≥ **$50M dollar volume ON the gap day** (1,568
  rows / 787 names / a majority of sessions). Median gap 39%, median D0 $vol $141M.
- That same-day-liquid subset is the **fattest-tailed slice in this entire study**: excursion
  median +32.9%, P90 +175%, **≥8×ADR density 21.6%** (324 clean rows / 258 names) — **2.6× the
  PASS pool's 8.2%**.
- It is also the **worst-crashing** slice: median settled close **−27.9%**. The tail and the
  wreckage live in the same pool — exactly the population only a proven ranker can hold (P9).
- At $10M D0 the admit set is ~10.3/day at 16.5% density; the looser check buys more names at
  lower density, same shape as every other floor priced so far.
- ⚠ Full-day D0 $vol is only known at the close; at 09:31-09:45 the scanner would see a
  projection (the open-intensity machinery already computes one). These numbers are the
  **upper bound** of what a same-day liquidity check could admit, not a deployable rule.

Names the floors killed that became tier-A that day and ran (clean rows, settled close shown):
BNAI 12-29 ($1.20 prev, $377M D0, 233×ADR, settled +2,821%) · SDOT 06-03 (85×, +1,084%) ·
AIIO 05-08 (83×, +201%) · BYND 10-17 (76×, +66%) · AQMS 09-24 (73×, +118%) · SOGP 08-28
(69×, +306%) · ELPW 04-08 (V-class, 3,266 sh D-1 → $67M D0, ran $122→$459). Also WNW 03-16
(83×ADR excursion, settled **−99%**) — the same pool, the other outcome.

### Result 4 — what a change would actually contend with

27% of P-class rows (the $5 floor) are the **same names re-gapping** (1,240 names / 3,974 rows);
serial gappers dominate. The class-V tail above $50M-D0 includes dual-class oddities (KELYB,
LBTYB) and $1,700-print foreign lines (OCG) where the "excursion" is a data artifact the
discontinuity guard cannot fully clean. Median entry price of the P class is sub-$5 **at entry**
too — the live bracket, slippage, and halt behavior on these names are unmodelled. **No
R-per-trade exists in this study; nothing here says "loosen."**

---

## What remains unknowable (stated, per the card's own bar)

1. **Warrants/units/long tickers** — dropped at ingest (`db.py:8810`); not in the store at all.
2. **OTC** — invisible to scanner and store both.
3. **Historical security-type state** — class U is measured against today's table.
4. **Premarket gaps** — the open-gap proxy misses names that gapped ≥10% premarket and faded by
   open (~half the real scan log on the validation day); the silent-floor counts are therefore a
   **floor, not a ceiling**.
5. **True fills** — every number is an excursion. Peak is not a fill (the #556 lesson stands).
6. Rows after 2026-07-23 are right-censored (fwd_n<20 for 482 silent rows); their peaks are
   floors.

## What this means

1. **The invisibility is the defect, and it is cheap to end** — the loop holds prev_close and
   prev_volume in hand at the `continue`; DoD (a) (log a skip_reason, or at minimum a daily
   aggregate row per floor) is a build card, deliberately NOT done under this measurement card.
2. **The floors are doing real protective work on the median** (−19/−26% settled) — P5 cuts both
   ways, and any proposal to remove them outright is contradicted by this study's own data.
3. **The tail cost is real and concentrated**: the D-1-illiquid → D0-tier-A class (~6/day) out-
   densities the admitted pool 2.6× in ≥8×ADR excursions. If the operator ever wants that tail,
   the instrument is a **same-day liquidity re-check** (the ARGX timing shape, #559), not a
   lower D-1 floor — a lower floor admits the $0.06M-D0 sludge too.
4. Folds into **#577** (price every gate) alongside #556 (ADV), #557 (cooldown), the gap-floor
   table, and #359 (mcap). Ordering per P9: none of this moves before the ranker earns it.

Captures: `scratchpad/570_{coverage,dropcounts,candidates,jumps,splits,scanlog_0814,scanlog_2w,daaq,scores_count}.psv`,
queries `570_q1..q4.sql`, analysis `570_analyze2.py`. All prod reads via psql, $0, no writes.
