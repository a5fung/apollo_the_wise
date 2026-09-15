# #96 intraday MA-pullback detector — N≥10 graduation read (2026-09-15)

**Review:** `data_gated_reviews.yaml::intraday_ma_pullback_signal_n10`.
**Verdict the review's OWN gate fires: NOT PROMOTE → bucket 2, "signal weak: revise detector".**
Gate 1 needs N≥10 + median 5d ≥ +2% + ≥40% of names up 5%+. Pooled, verbatim population (n=388): median 5d
**+0.76%** (fails the +2% bar); 5d win rate **30.2%** (fails 40%); 10d win rate 42.3% (would pass, if the gate meant
10d — it says 5d). The gate has no marginal bucket; two of its three conditions fail.

**⚖ THE LINE.** Nothing was flipped. Revising the detector (volume ceiling, MA anchoring, sector filter) is a
criterion change — CHANGE_PROCESS + operator sign-off. EP-first priority stands; no PROMOTE fires, so nothing
collides, and sequencing any revise sits behind #508.

## The decision this serves

Whether the MA-pullback detector (#96, VCP/Minervini pullback to SMA10/20 inside the base on light volume) graduates
to an operator-confirm entry (`/mapullback ENTER`, stop just below the MA). What would change it: median 5d return
≥ +2% with ≥40% of names up 5%+ — and, per the standard, a tail: names reaching +20%/+40%.

## Population

- **Source rows:** `mi_flag_ma_pullbacks`, all 529 rows ever (2026-05-26 → 2026-09-14, 201 tickers), joined to
  `mi_daily_closes` for the fire-day OHLC and the next 5/10/20 trading closes, highs and lows. Dumped once to
  `/tmp/gated3/ma_raw.csv`; computed locally.
- **Gate population (predicate, verbatim):** `pullback_date ≤ today−12d`, `parent_invalidated_eod = FALSE`, 10th
  forward close present → **n=388** rows, 163 tickers. 19 survivors not yet settled (fires 08-31 → 09-04).
- **Entry:** `current_price` — the bounce-detection price at the scan tick, as the review instructs.
- **⚠ ERA — parent universe rebuilt 2026-06-27** (#356 HTF spec replaced the n=1 50/60 flag; actionable parent
  roster ~1,000/month → ~65/month). The detector's own gates (±1% tag, ≤2% undercut, 0.5% bounce and hold, ≤100% ADV
  pace) did not change after 05-26. **Era A = fires ≤ 06-26 (retired parent), n=336 of the 388; Era B = fires ≥
  06-29 (current parent), n=52 from 18 tickers.** Pooled = 87% retired-universe.
- **⚠ Survivor filter is outcome-conditioned.** 122 of 529 rows (23%) had the parent stamped INVALIDATED at the same
  day's 17:25 close (invalidation lag = 0 days on every row). That uses the day-0 CLOSE — information not available
  at the bounce price. The excluded set's own 10d read: median −2.2%, 35% ≤ −10% (n=118 settled). The unconditioned
  population (all settled rows) is reported beside the gate number.
- **Independence:** 314 of 529 rows re-fire within 10 days of a prior fire on the same ticker (a ticker sitting on its
  MA fires day after day; NWL 6×, XMTR/TWLO/VCYT/ZBIO/CDNA/CHYM 4× in Era B). First-fire-per-campaign n = 218
  (152 settled Era A, 17 Era B). The gate's N is written on raw rows; both are shown.
- **Split artifacts excluded from the "clean" cut (detection price and stored closes on different share bases,
  verified against same-day close):** AIXI 05-26 (1:7 reverse split → fake +314%), VCIG 06-12 (fake +820%, in the
  invalidated set), SNEX 05-26/05-27/06-01/06-02 (3:2 split → fake −28%). Verbatim gate numbers keep them (n=388);
  clean n=384. A forward-window scan found no other single-day discontinuity that was not a real move on volume
  (QTTB +91% on 27M shares, BJDX −51% on 2.7M).
- **What the system already did:** 0 fires coincided with an EP alert or a live-trade alert date; 16 coincided with a
  same-day flag break, 19 with a same-day support test.
- **Footnotes:** 27 rows on 05-26 ran the pre-#124 `day_low` version (cumulative-low bug, fixed that evening);
  0 rows on the 08-04 stale-parent day.
- Forward returns are raw closes, no stop, no management. Stop-aware rows use stop = the MA value (the gate's "just
  below MA"); a day-0 hit counts only if the full-day low is below the low recorded at detection AND below the stop.

## The numbers

### The gate, verbatim and clean

| population | n | median 5d | avg 5d | ≥+5% at 5d | avg 10d | median 10d | ≥+5% at 10d |
|---|---|---|---|---|---|---|---|
| gate pop, verbatim | n=388 | +0.76% | +2.10% | 30.2% | +2.82% | +2.73% | 42.3% |
| gate pop, clean (5 split rows out) | n=384 | +0.83% | +1.23% | 30.2% | +2.22% | +2.75% | 42.4% |
| unconditioned (all settled), clean | n=500 | −0.00% | +0.13% | 28.4% | +1.22% | +1.84% | 40.0% |
| **Era B, gate pop** | **n=52** | +0.96% | −0.18% | **19.2%** | **−0.82%** | −0.63% | 28.8% |
| Era B, first-fire only | n=17 | +1.12% | −0.63% | 17.6% | −3.18% | −1.20% | 17.6% |
| Era B, unconditioned | n=64 | +0.53% | −0.71% | 21.9% | −2.37% | −0.88% | 28.1% |

### Tail first (clean gate population)

| window | n | mean | median | p90 | ≥+5% | ≥+20% | ≥+40% | ≤−10% |
|---|---|---|---|---|---|---|---|---|
| 5d | n=384 | +1.2% | +0.8% | +13.4% | 116 (30%) | 17 (4%) | 4 (1%) | 49 (13%) |
| 10d | n=384 | +2.2% | +2.8% | +19.7% | 163 (42%) | 38 (10%) | 5 (1%) | 68 (18%) |
| 20d | n=366 | +2.8% | +3.1% | +26.6% | 172 (47%) | 74 (20%) | 12 (3%) | 97 (27%) |
| MFE 10d (max high — NOT a return) | n=384 | +13.7% | +11.1% | +27.2% | 305 (79%) | 79 (21%) | 12 (3%) | — |
| MFE 20d (max high — NOT a return) | n=366 | +21.4% | +15.3% | +43.8% | 319 (87%) | 147 (40%) | 48 (13%) | — |

Big movers (10d): BLZE 06-22 +100%, QMCO 05-28 +51%, STFS 06-11 +49%, QMCO 05-27 +47%, RXT 06-04 +42%. Without the
top name: mean +2.0%, median +2.8%, 37/383 ≥+20%. **All 38 of the ≥+20% 10d movers and 72 of the 74 20d movers are
Era A.**

| era | n (tickers) | 10d ≥+20% | 10d ≥+40% | 20d ≥+20% | 20d ≥+40% | p90 10d | p90 20d |
|---|---|---|---|---|---|---|---|
| A ≤06-26 (retired parent) | n=332 (146) | 38 (11%) | 5 (2%) | 72/332 (22%) | 12 (4%) | +20.6% | +28.4% |
| A first-fire only | n=150 (141) | 17 (11%) | 3 (2%) | 29/150 (19%) | 5 (3%) | +21.1% | +26.7% |
| **B ≥06-29 (current parent)** | **n=52 (18)** | **0 (0%)** | 0 | 2/34 (6%) | 0 | +8.1% | +15.9% |
| B first-fire only | n=17 (17) | 0 | 0 | 1/12 | 0 | +5.3% | +10.8% |

Era B best 10d: XMTR 07-07 +15%, NEO 07-21 +12%, PBF 08-24 +10%. Worst: SLS 07-15 −26%, VCYT 07-17 −20%.

### Stop-aware — the stop is the binding constraint

| stop rule | population | n | stopped in 10d | mean R 10d | ≥3R 10d | stopped in 20d | mean R 20d | median risk |
|---|---|---|---|---|---|---|---|---|
| MA (literal "just below") | clean gate | n=384 | 90% | +0.02R | 25 (7%) | 94% | −0.04R | 1.3% |
| MA | Era B | n=52 | 94% | −0.80R | 1 (2%) | 100% | −1.00R | 1.3% |
| MA −2% (detector's own undercut tolerance) | verbatim gate | n=388 | 77% | +0.23R | 44 (11%) | 85% | +0.05R | 3.3% |
| MA −2% | Era B | n=52 | 79% | −0.50R | 2 (4%) | 98% | −0.85R | 3.3% |
| base_low (structural) | verbatim gate | n=388 | 35% | +0.20R | 8 (2%) | 49% | +0.19R | 11.3% |
| base_low | Era B | n=52 | 25% | −0.16R | 0 | 57% | −0.48R | 8.0% |

The entry sits 0.5–2% above the MA, so a stop at the MA is hit by daily-bar noise 9 times in 10; widening to 2% still
stops 3 of 4; only the structural stop survives, and at 11% risk the Era A tail is 2–4R at best. In Era B every stop
rule is negative.

### Slices (pooled, clean; Era B too small to slice past n=38)

| slice | n | avg 10d | median 10d | ≥+5% 10d | ≥+20% 10d | ≥+20% 20d |
|---|---|---|---|---|---|---|
| SMA10 | n=279 | +1.7% | +2.4% | 116 (42%) | 23 (8%) | 54/264 (20%) |
| SMA20 | n=105 | +3.5% | +3.6% | 47 (45%) | 15 (14%) | 20/102 (20%) |
| SMA10, Era B | n=38 | −1.7% | −0.9% | 8 (21%) | 0 | 2/23 |
| SMA20, Era B | n=14 | +1.6% | +2.6% | 7 (50%) | 0 | 0/11 |
| TIGHTENING | n=274 | +1.8% | +1.1% | 115 (42%) | 31 (11%) | 49/266 (18%) |
| COILED | n=99 | +3.0% | +3.3% | 41 (41%) | 7 (7%) | 23/93 (25%) |
| TRIGGERED | n=11 | +5.2% | +5.8% | 7 (64%) | 0 | 2/7 |

SMA20 has the better 10d tail pooled (14% vs 8%) but the same 20d tail (20% vs 20%); that is an Era A observation,
not a finding, and it does not survive into Era B (0 of 14 ≥+20%).

## The revise menu, as the gate lists it (each is a criterion change → CHANGE_PROCESS)

- Volume ceiling (≤100% ADV) — untested here; Era B n=52 cannot rank it.
- MA-anchoring strictness (SMA50 variant) — SMA20 vs SMA10 shows no tail difference at 20d.
- Sector filter — not evaluated.
- Not on the menu but visible in the data: the re-fire behaviour (a name on its MA fires on 4–6 consecutive days) and
  the same-day parent invalidation rate (23%) — the detector fires on bounces that do not hold into the close 1 time
  in 4, and the survivor filter hides those from the gate.

## What this does not answer

- **Universe vs regime.** Era A and Era B differ in the parent universe AND the calendar (May–Jun vs Jul–Sep). The
  vanished tail after 06-27 cannot be attributed to the HTF parent from this data alone.
- **Whether the current-era detector has any edge:** n=52 rows but 18 tickers and 17 independent campaigns, all
  negative on every measure — enough to say no tail has appeared in 11 weeks, not enough to size an expectancy.
- **Actual fills and stops.** No minute-bar simulation (the review's own precondition). `current_price` is a
  5-minute snapshot; stop hits are judged on daily lows.
- **Whether the survivor filter should exist.** It conditions on the day-0 close. An operator-confirm entry at the
  bounce would carry the 23% that invalidate by the close (median 10d −2.2%); the unconditioned rows are the honest
  base for any entry design, and they read worse.
- **The Era A tail under today's rules** — those names were admitted by a retired parent detector; not replayed.
- Sector, regime and the Sugar-Baby overlay (n=19 in cohort).

Working files: `/tmp/gated3/` (ma_raw.csv, results_ma.txt, results_ma_clean.txt, results_stop_sensitivity.txt,
jump_scan.txt, compute.py). Prod was read only.
