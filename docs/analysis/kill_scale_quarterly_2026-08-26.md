# Kill/scale band quarterly review — 2026-08-26 (operator sign-off condition #1)

**MEASUREMENT ONLY. Nothing was changed. Kill/scale bands, sizing and every safeguard are the
operator's sole authority (THE LINE). No threshold, band, toggle, trade state, `PLAN.md` line or
`data_gated_reviews.yaml` entry was touched. Every fork below is his, not a recommendation.**

## The answer in one line

**HOLD.** The automatic size cut (REDUCE) arrives after **12 straight full stop-outs** — 15 if
they land at this book's average loss, and then via the losing-streak arm instead. But what
actually trips it is **PLTR's +3.4R aging out of the last-20 window at exactly trade 12**, not the
losses: one more real winner pushes the trip further out, and twelve losses in a row is not the
modal path for a book that has converted 3 of 23.

## The question

`data_gated_reviews.yaml::kill_scale_bands_quarterly_review` has been filed as ready since
2026-08-14 (bar: 20 closed live trades); the count is **23 today**. Are the SIGNED bands (`docs/setups/safeguards.md`
§ "Kill / scale criteria", #268b, operator-signed 2026-06-12) still correctly calibrated, and what
does the live cohort read against them today?

## Data — one read-only prod capture, $0

- `scripts/probes/_killscale_q3_2026-08-26.py` → `_killscale_q3_2026-08-26_out.txt` (part 1),
  `_killscale_q3b_2026-08-26.py` → `_killscale_q3b_2026-08-26_out.txt` (part 2, open book + stop
  geometry). Piped into `docker exec -i apollo-market python -`; nothing written to prod disk,
  SELECTs only. Captured once, read many.
- The verdict below is the **shipped evaluator's own output** — `assemble_band_inputs("live")` +
  `evaluate_kill_scale_bands` + `get_active_override` + `format_band_line`, called directly in
  the prod container. Not a re-implementation.
- `agents/market_intelligence/kill_scale_bands.py` in the container is **byte-identical** to
  local `main` (`md5 7d33b24efffa09e78e29fc177ce4a08e`), and the six signed thresholds print
  unchanged (`-1.05 / -30.0 / -0.70 / 16 / 0.50 / 20`). Prod is 5 commits behind `origin/main`
  and **none of the five touch this module** — so the local simulations further down are the same
  code prod runs.
- The recomputed per-row R list was asserted **element-wise identical** to the evaluator's
  `realized_rs` before any local arithmetic was done on it.

## Result 1 — the band verdict, from the evaluator

```
⚪ Kill/scale band: HOLD — No change
  n=23 · t20=-0.44R · t40=n/a · streak=1 · cum=-11.9R
  within bands
  📖 open book (NOT in the verdict above): 2 position(s) — AMLX 8d, MRNA 7d
```

| | value | trigger |
|---|---|---|
| trailing-20 expectancy | **−0.4442R** | REDUCE at ≤ −0.70R · KILL at ≤ −1.05R |
| trailing-40 expectancy | **n/a** (needs 40 trades) | SCALE at ≥ +0.50R |
| cumulative live R | **−11.93R** | KILL at ≤ −30R |
| current losing streak | **1** | REDUCE at ≥ 16 |
| n (closed live, band cohort) | **23** | sample floor 20 — **cleared** |
| drawdown breaker tier | OK | KILL on BLOCK (−12% equity) |
| operator override | none active | — |

**This is the first review in which the strategy-health arms can actually evaluate.** The 08-06
run reported "n=14 < 20 floor, cannot evaluate"; the floor is now cleared and the bands are doing
their real job.

**Why it improved since the 08-23 measurement (−14.61R → −11.93R):** ABCL closed 2026-08-24 at
**+2.684R** (+$127.77). That single close is the entire delta; nothing else changed. Band history
confirms only ONE transition has ever been persisted — `live ∅ → HOLD`, 2026-06-19 — and there
are zero `kill_scale_band_eval_error` rows, so the band has never silently frozen.

## Result 2 — distance to each trigger, and the thing that actually moves it

Computed by feeding the captured R series plus synthetic future trades **through the real
evaluator** (never appended to prod), k = 1, 2, 3 … until the band flips:

| Future trades appended | First band change |
|---|---|
| 12 full **−1.00R** stop-outs | **REDUCE** — trailing-20 −0.7101R |
| 15 losses at this book's **average loss (−0.928R)** | REDUCE — via the **streak** arm (16 in a row) |
| 14 losses at MRVL's **−0.953R** | REDUCE — trailing-20 −0.7091R |
| 19 full stop-outs | **KILL** — cumulative −30.93R |

Raw headroom: **0.26R** on trailing-20, **18.1R** on cumulative, **15 consecutive losses** on the
streak arm.

⚠ **The headroom number is misleading on its own, and this is the finding of Result 2.**
Trailing-20 is a ROLLING window — at n=23 the three oldest trades are already outside it, and
each new trade rolls one more off. Because the roll-offs are mostly ≈ −1R losers, **t20 barely
moves for the first eleven losses** (−0.4442 → −0.4890 across k=1…11). What flips it is a
**winner leaving the window**:

- **k=12: PLTR (+3.423R) rolls out** → t20 jumps −0.489 → **−0.7101** → REDUCE.
- k=16: ABCL (+2.684R) rolls out → −0.741 → −0.925.
- k=19: ETON (+0.519R) rolls out → −0.998; cumulative crosses −30R the same trade → KILL.

Plainly: **three winners are holding the band up. The size cut arrives when the first of them
ages out of the last-20 window — not because of the losses themselves.** Conversely, one more
real winner pushes the trip further out. The band is stable in the short run and brittle at the
moment PLTR expires.

**On the SCALE side:** structurally unevaluable today — it needs ≥ 40 closed trades, so
`trailing_40` is `None` and no amount of good performance can scale size until 17 more trades
close. For reference, 17 more trades at this book's own average WIN (+2.209R) would return SCALE;
17 more at +1.00R each would still read HOLD.

## Result 3 — the pop-check warning is clean; no other strategy is in the cohort

The review board flags `mi_live_trades.signal_type not filtered (magna53=23)`. Queried directly
against prod:

- Band cohort by `signal_type`: **magna53 = 23. Nothing else.**
- Every `9m_day2` row in the table is `account_mode='paper'` (8 closed, 8 cancelled, 54 skipped)
  and is excluded by the `account_mode='live'` filter, not by luck.

**No contamination. The read stands as measured.** The warning is the generic
population-mismatch check noting an unfiltered column, not evidence of a mixed cohort.

## Result 4 — zero rows dropped, and the guard has never had anything it *could* drop

**The finding: 0 of 23 rows were dropped, and the drop cannot currently happen in the direction
the question worries about.** `risk_dollars_actual` is NULL on all 23 closed rows, so every row
takes the FALLBACK expression `entry_shares × (entry_price − hard_stop)` — which is positive on
all 23. The `actual` branch of `risk_placed`, and its actual-vs-derived disagreement warning, are
**dead code on live data today**. The first row ever written with `risk_dollars_actual` populated
(#571 writes it at entry, so it will be a post-08-23 entry) is the first row that could ever
produce a mismatch, a zero, or a silent exclusion. That is the row to look at, not this cohort.

The counting evidence behind that: `assemble_band_inputs` drops rows in Python when
`risk_placed()` returns None or ≤ 0 and returns no count — and `len(realized_rs)` is exactly what
`_SAMPLE_FLOOR` checks. Three different filters are in play; all three were counted:

| Definition | Count |
|---|---|
| YAML predicate (`closed` + `live` + `total_pnl IS NOT NULL`) — the "ready" count | 23 |
| All closed live rows | 23 |
| `assemble_band_inputs` SELECT (`closed` + `live` + `pnl_attribution IS NULL`) | 23 |
| **Kept after the Python degenerate guard = `len(realized_rs)`** | **23** |

- **0 rows dropped.** Every row produced a positive denominator, all via the fallback branch.
- 0 closed live rows carry a non-NULL `pnl_attribution` (would be in the YAML count but out of the
  bands).
- 0 closed live rows have `total_pnl` NULL. Worth stating because such a row would raise a
  `TypeError` inside `assemble_band_inputs`, get swallowed into a `kill_scale_band_eval_error`
  row, and **freeze the band silently**. It has not happened; there are no error rows.
- The task's premise **still holds** — confirmed row by row: `risk_dollars_actual` is NULL on all
  23 closed rows and on both open ones.

The cohort is not silently shrinking, and the sample floor is being checked against the number it
should be.

## Result 5 — era split: 22 of 23 closed trades are on a stop rule we no longer trade

The 2R stop went live 2026-08-16. Splitting by **entry (fill) date** — stop geometry is fixed at
entry — and confirming each row's geometry against its own ORB (`hard_stop` vs `2 × ORB_low −
ORB_high`):

| | pre-2R (ORB-low stop) | 2R era |
|---|---|---|
| entries | 22 (WULF 07-06 → ETON 08-14) | 3 (AMLX 08-18, MRVL 08-19, MRNA 08-19) |
| **closed** | **22** | **1 (MRVL, −0.953R)** |
| cumulative R | −10.98R | −0.95R |
| expectancy | −0.499R | n=1 — no distribution |
| winners | 3 of 22 (PLTR, ABCL, ETON) | 0 of 1 closed |
| still open | 0 | 2 (AMLX, MRNA — both partialled, both breakeven-armed) |

**What transfers:** essentially nothing about the 2R era. One closed trade is an arithmetic
check, not a measurement. The current trailing-20 window (TSEM → MRVL) contains **19 pre-2R
trades and 1 post-2R** — the band that decides live sizing is today reading a stop rule we
retired ten days ago.

**What does not transfer, stated as a measurement fact and not a proposal:** pre-2R and post-2R R
are **different units of the same name**. The 2R stop is roughly twice as far from entry, so at
the same dollar budget one R is about twice the dollars (#571 measured the median move: $23 →
$45), a full stop-out is a rarer event, and every profit target is worth half the R it used to be.
The trailing-20 is therefore currently a blend of two definitions of R, and it will stay a blend
for about twenty more closes.

**The same seam runs through the benchmark.** The #268b calibration that set every threshold
(`scripts/selection_replay_268.py`, `--stop-model` default `orb_low`) was simulated on the
**ORB-low** geometry. So the healthy-year fingerprint the bands sit outside of — +0.95R
expectancy, 30% win rate, worst streak 15, −24.1R maxDD, trailing-20 p5 −0.63R — describes the
retired rule too. **Both sides of the comparison are pre-2R today.** That is internally
consistent right now and becomes inconsistent as the live book fills with 2R trades.

⚖ **The operator's fork (not pre-decided here):** as 2R trades accumulate, either (a) let the
bands keep reading a mixed-unit trailing-20 and accept the blur, or (b) re-derive the calibration
envelope on the 2R geometry so the benchmark matches the rule being traded. Both are legitimate;
neither is urgent this week (1 closed 2R trade). No change proposed, none made.

## Result 6 — live distribution vs the calibration envelope

| | calibration (#268b, n=399) | live (n=23) |
|---|---|---|
| expectancy | +0.95R | **−0.52R** |
| win rate | 30% | **13%** (3 of 23) |
| average winner | — | +2.21R |
| average loser | — | −0.93R |
| worst losing streak | 15 | **14** |
| max R drawdown | −24.1R | **−13.1R** |
| trailing-20 | p5 −0.63R, min −1.03R | **−0.44R** now |

- The path statistics (streak 14 vs 15, drawdown −13.1R vs −24.1R) are **inside** the healthy
  year. The strategy has not yet done anything a profitable year does not do.
- Expectancy and win rate are **well outside** it — but at n=23 against n=399 that is exactly the
  comparison `replay_regression.py` was deliberately built NOT to auto-verdict on.
- ⚠ **Do not read the weekly replay-regression series as a trend across 08-23.** Those snapshots
  reuse `assemble_band_inputs`, so every one written before the #586 deploy divides by the OLD
  pre-cap `risk_dollars`: 07-26 −0.83R (n=9), 08-09 −0.73R (n=17), 08-16 −0.69R (n=20), 08-23
  −0.512R (n=22) — that last figure is exactly the pre-fix number safeguards.md records, whose
  corrected twin was −0.664R. Today's **−0.519R (n=23)** is on the CORRECTED denominator. The two
  happen to look adjacent, which is the trap: reading "flat week over week" compares two different
  definitions of R. The fix (commit `40521378`, 2026-08-23) is in the running prod image now, so
  **the Sunday 08-30 snapshot is the first comparable one** and the series restarts there.
- Criterion (c) of the review — repeated overrides in one direction meaning the bands are
  mis-set — **does not apply: there are zero override rows, ever.** Nothing in this data argues
  a threshold is wrong.

## Result 7 — two measurement defects found, neither touched

1. **The SCALE arm's equity condition is structurally always TRUE.** `equity_above_start`
   compares the earliest live equity snapshot to the latest. The earliest row is
   **2026-06-22 = $0** (a bootstrap row written the day before funding); latest is
   $5,001.47. So the guard reads `5001.47 > 0` — it can essentially never be False, and the real
   starting equity ($5,000 from 06-23) is not what it compares against. **Blast radius: it cannot
   currently produce a wrong verdict.** SCALE also requires n ≥ 40 AND trailing-40 ≥ +0.50R; a book
   that clears +0.50R over forty trades has equity above $5,000 anyway, so the guard would read
   True *correctly* on the only path that reaches it. It is a defect that is inert rather than a
   hole that is armed — but it is a live-money safeguard input that does not do what its name says.
   **Not fixed: a safeguard input is THE LINE.**
2. **The YAML predicate and the evaluator use different filters** (`total_pnl IS NOT NULL` vs
   `pnl_attribution IS NULL`). They agree at 23/23 today by coincidence of a clean book, not by
   construction — the review could fire on a count the bands never evaluate. Reported, not
   changed.

## ⚠ What this review does NOT answer

- **Whether the bands are correctly calibrated.** n=23 against a calibration of n=399 is the
  headline caveat. This run measures where the live cohort SITS against pre-committed thresholds;
  it cannot re-derive them. Per-trade expectancy at n=23 is noise; the path statistics (maxDD,
  worst streak) structurally cannot reach the full-year envelope for months.
- **Anything about the 2R stop era.** 3 entries, 1 closed. Needs ~15-20 closes before the era
  split in Result 5 is a distribution.
- **Whether the strategy is profitable.** The bands read CLOSED trades only, and the methodology
  cuts losers fast while letting winners run — so the two open runners (AMLX up from $30.21 to a
  $41.14 high, MRNA from $120.75 to a $176.66 high, both partialled, both breakeven-armed) are
  invisible to every number above. That is a deliberate, operator-instructed design choice
  (safeguards.md 2026-08-09), and it means today's HOLD is a **visibly partial picture** that
  skews pessimistic.
- **Regime.** All 23 trades were taken in Choppy / Correcting / Crisis / early-Bull tape. The
  companion `exit_tune_bull_regime_read` carries that axis; this review fires on trade count only.
- **The demote-side watch-metric** (review input (d) — judge-demoted cohort forward R). Not
  measured here; it is a separate cohort with its own data path and no live evidence has accrued
  against it since the Phase B read.
- **Whether the day-0 stop-out problem is fixed.** The 08-06 run's real finding was that 13 of 14
  closes were same-day. Today: **20 of 23 closed rows carry `hold_days = 0`** (as recorded — MANE's 0 in fact spans an
  overnight, filled 07-15 and closed 07-16 09:30, so the column is not clean), and only three ran
  longer — PLTR 14d and ABCL 11d (the book's two big winners, +3.42R and +2.68R) and SMCI 2d (a
  loser). The third winner, ETON +0.52R, was same-day. The shape has not changed; it is an
  entry/stop-geometry question, and re-tuning bands would paper over it.

## What this means

1. **HOLD, and the floor is cleared** — this is the first evaluation where the bands can actually
   bind, and they read within range on every arm.
2. **We are 12 full stop-outs from an automatic halving of risk per trade** (15 at the book's
   average loss, via the streak arm), 19 from a kill to paper. At this book's actual fill rate
   (25 fills over 33 trading days, ~0.75/day) that is roughly **three trading weeks** of
   uninterrupted losses — and a single winner in that stretch resets the arithmetic.
3. **The trip is being driven by winners aging out of the window, not by losses.** PLTR's +3.42R
   is what stands between HOLD and REDUCE; one more real winner moves the trip further out.
4. **The bands, the benchmark, and 22 of 23 trades are all on a stop rule we stopped trading on
   08-16.** Internally consistent today, increasingly not so with every 2R close.
5. **Nothing here argues a threshold is mis-set.** Zero overrides, one band transition ever, path
   statistics inside the healthy envelope.

## Steps this review is NOT permitted to take (operator / next session)

The review's own `action_when_ready` requires two follow-ups that are out of scope for a
measurement task and were deliberately **not done**:

- **Re-bump `earliest_review_date` +1 quarter** in `data_gated_reviews.yaml` (recurring, not
  one-shot) and record this run in that entry. Untouched.
- **Log the outcome as a `docs/setups/safeguards.md` change-log entry** — "bands are never
  silently re-tuned" cuts both ways; a HOLD verdict is still an outcome that belongs in the log.
  Untouched.
- `PLAN.md` untouched. No deploy, no commit, no override written.
