# Breakout v1 — three shape gates from his MTW read (DEFINITIONS, fixed before any outcome)

Written 2026-11-02 BEFORE any outcome was computed. Paper rules are his call: this DEFINES and TESTS, ships nothing.

His words (operator_shared_notes 2026-11-02, on MTW, v1's first paper buy):
"It's choppy around the 10/20ma and not really making higher lows, if anything the breakout attempt is 10/28-29.
I don't see any breakout pattern at all."
His standard (2026-10-29): "a strong up move, a pullback to around the averages, higher lows, tightening, then the breakout."

All three gates are read at the watch night D on bars up to D only (no look-ahead). ADR20(s) = the mean of
(high - low) / close over the 20 sessions ending s, as in v1. P = v1's pole top (unchanged).

## G1 — RIDING THE AVERAGE (`riding`)

- For the 10-day and for the 20-day separately: over the last **10 sessions** (D-9 .. D), EVERY close is at or above
  that day's average, AND every low is no more than **0.5 x ADR20(s) x close(s)** below that day's average
  (each session's own average, ADR20 and close, as v1's surf already does).
- Passes if it holds for the 10-day OR the 20-day (one average ridden the whole window; no switching mid-window).
- The one new constant: **0.5 ADR** below the line for a low. Why: "a small tolerance" — an intraday dip under the
  line that is bought back by the close. 0.5 is the tighter of the bands v1's own calibration already measured
  (k = 0.5 / 1.0 / 1.5 in `_qm_0810_review/dated_setups_2020-08-10.tsv`); v1's 1.0 "either side" is the loose band
  that let MTW through.
- The window (10 sessions) is not new: it is the span v1's tightening rule already reads (D-9..D-5 vs D-4..D).
  Why not 5: MTW's last 5 sessions (10-26 .. 10-30) DO ride the 10-day (every close above, lows within 0.3 ADR); his
  "choppy around the 10/20ma" is 10-16 .. 10-23 (closes under both averages on 10-16, 10-19, 10-22, 10-23; lows 0.9 -
  1.2 ADR under). A 5-session window would not read his reason at all.
- MTW 10-30 (window 10-19 .. 10-30): FAILS (10-day: close under it on 10-19, lows 0.5-1.0 ADR under it on 10-19, 10-20,
  10-22, 10-23 (10-19 added after the code's reading — a hand-read slip, no constant changed); 20-day: close under it on 10-19, 10-22, 10-23). Hand-read from the bars; the code's reading is in RESULTS.md.

## G2 — A RISING SERIES OF LOWS (`rising_lows`)

- Split the last 15 sessions into **3 blocks of 5**: D-14..D-10, D-9..D-5, D-4..D. Each block's lowest low must be
  strictly above the block before's. Two rises in a row = a series, not one compare.
- The one constant: **3 blocks** (of v1's existing 5-session unit). Why: "higher lows", plural — one compare (v1 today:
  last-5 low vs base low) is a single higher low; three blocks is the fewest that makes two in a row.
- Known property: for a base of 10-14 sessions the first block reaches back into the run-up, whose lows are usually
  lower — that block then passes easily. Stated now, not a surprise later.
- MTW 10-30: FAILS (block lows 21.28 (10-12..10-16) > 21.05 (10-19..10-23) — the middle block made a LOWER low).

## G3 — NO RETEST OF A FAILED ATTEMPT (`no_failed_attempt`)

- The base's ceiling BEFORE the last 5 sessions: CEIL = the highest high of P+1 .. D-5 (after the pole top, before
  the window that sets tomorrow's buy level).
- A failed attempt = the last 5 sessions traded ABOVE CEIL (the highest high of D-4..D > CEIL) AND close(D) is back
  BELOW CEIL. Such a name is not a first breakout — skip it.
- The one constant: **5 sessions** (the window v1 already uses to set the buy level, so "the attempt" = whatever set
  the level). The pole top is NOT the ceiling: MTW's pole high is $24.00 and the 10-28/29 attempt topped at $23.875 —
  his "breakout attempt" is out of the 10-07 .. 10-23 range (ceiling $23.114), not a new high.
- Why the reference is not v1's level itself: the level is the highest high of D-4..D, so close(D) is always under it —
  "traded through the level and closed back below" would fail every list row.
- MTW 10-30: FAILS, but on a THIN margin — 10-29's high $23.875 > ceiling $23.114, and 10-30 closed $23.03, 8 cents under
  the ceiling. Two cents of the other way and G3 alone would pass MTW.

## Data and the one declared exception to the seal

- The 2017-24 replay reads only the sealed stores (`cb702_pre_v2`, and the cb702 copy filtered to < 2025-01-01).
- MTW (check a) needs its 2026 bars. ONLY `scripts/probes/_mtw_1102/mtw_bars.csv` is read (the task's named input,
  already pulled by the main loop); its last row is 10-30 — there is no bar after the watch night, so no outcome is
  seen. Nothing else dated 2025 or later is read.
- ZCSH: NOT in either store (0 rows in cb702_pre_v2 and in the sealed cb702 copy — a 2026 fund). Check (b) rests on the
  12 of his 24 alone.
- Tested as ADDITIONS to v1's gates, not replacements: the frozen list only holds names that passed today's surf and
  higher-lows, so the replay can only REMOVE names (adr_floor_effect's pattern). Replacing surf / higher_lows outright
  could ADMIT names the walk never priced — untested, and not claimed.

## The pass bar for shipping (numbers to beat, fixed now)

Candidates judged: G1 alone, G2 alone, G3 alone, and all three together. Each is applied ON TOP of the 4.26% daily-range
floor (live since 11-02), so the baseline is the floor-only book (`adr_floor_1102/adr_floor_effect.txt`).

- (a) MTW 10-30 fails at least one new gate (for a single gate: fails THAT gate).
- (b) At least **10 of the 12** of his 24 good setups v1 already catches still pass (each at its own catching watch
  night; the 12 = the HIT + LATE rows of `v1_check_variant_rs.txt`, V3 + best-of-three RS). ZCSH: not in the stores.
- (c1) 5-slot paper book at 2 cents, mean R per trade: **>= -0.139R in 2017-21** (baseline n 983) AND
  **>= -0.340R in 2022-24** (baseline n 556).
- (c2) The trades the gate removes (filled, decisive, 2c, no slot limit, from the floor-kept set, both eras pooled)
  average BELOW the ones it keeps (floor-only baseline: all 4,029 trades average -0.092R).
- (c3) Readable: the kept 5-slot book has at least 100 trades per era (the registration's n floor).

Verdict rule, fixed now: the combined set ships if it passes (a), (b), (c1), (c2), (c3). If it fails, any single gate that
passes all five is the alternative. No pairs, no constant changed after seeing an outcome; a variant shown after the fact
is labelled as such and cannot carry a PASS.
