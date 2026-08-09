# Kill/scale band samples closed trades only — and winners take 24x longer to close

**Operator, 2026-08-09:** *"but winning trades takes longer, e.g. I'd expect us to hold pltr for
weeks if it really works out"*

## The measurement (all closed trades to date)

| account | side   |  n | avg hold days | max |
|---------|--------|---:|--------------:|----:|
| live    | loser  | 17 |           0.1 | 2.0 |
| paper   | loser  | 24 |           0.5 | 5.0 |
| paper   | winner | 10 |          11.9 |23.0 |

**Winners hold ~24x longer than losers (11.9d vs 0.5d paper; live losers 0.1d).** Live has no
winners yet, so the live row cannot show the other side.

## Why that breaks the band

`kill_scale_bands.py` computes every strategy-health trigger from the CLOSED realized-R cohort:
`_SAMPLE_FLOOR = 20` closed trades, then trailing-20 expectancy, current losing streak, and
cumulative R. `current_losing_streak(rs)` reads trade-level realized R, so a trade that banks a
+2R partial and still closes net red counts as a LOSS (FIGS, 2026-08-07: +$6.90 partial, -$7 net).

If losers exit in hours and winners run for weeks, then at any given moment the closed pool is
structurally loser-heavy — the winners are still OPEN and uncounted. The band therefore reads a
biased sample **by construction**, not by bad luck, and the bias is worst exactly when a runner is
developing.

## Current state (informational — the band is HOLD, below its floor)

- n=17 closed live, streak 17, cumulative -12.4R, trailing expectancy -0.73R.
- At n=20 the band would read **REDUCE** (halve risk) on two counts at once: streak 17 >= 16, and
  -0.73R <= the -0.70R REDUCE line.
- KILL is NOT close: it needs cumulative <= -30R or trailing-20 <= -1.05R.
- The book is FLAT today, so no open winner is being missed right now.

**Correction (same day):** PLTR (entered 2026-08-04) is open, hold_days=3 — the book is not
flat; the open-book line renders it (`PLTR 3d`).

## The fork for the operator

Whether the band should count open positions at mark, wait for closes, or something else, is a
SAFEGUARD change and therefore his sole call (THE LINE). Nothing changed here.

---

## PROPOSAL (2026-08-09) — smaller than it first looked, because the band only TELLS you

### It is ADVISORY, not enforcing — verified, not assumed
- `scheduler.py:1590` calls `run_band_evaluation("live", send=True)`; the verdict goes to a
  Telegram on a band TRANSITION and an audit row. Nothing else consumes it.
- Nothing in `broker/` reads `BandVerdict`, `band.action`, or `run_band_evaluation` — grep is empty.
- The `_ACTION` strings are instructions to a human: *"Halve risk/trade until trailing-20
  expectancy >= 0"*, *"Stop live entries; revert to paper; postmortem + operator re-arm"*.
- **So REDUCE at n=20 will not halve anything. It will send a message asking YOU to.** The
  question is therefore what the nightly message should say — not what the safeguard should do.
  That keeps this off THE LINE, so long as no one wires it to sizing.

### ⛔ Option ruled OUT, on this system's own evidence: mark open positions to market
- The exit review found 4 of 6 live Bull trades touched >=+1R and every one closed red; FIGS
  peaked past +2R and closed -$7.
- Marking open positions at their high-water mark would have shown a healthy book on exactly
  those days. **A band that reads unrealized gains relaxes precisely when the give-back problem
  is worst.** Do not offer this as a co-equal option.

### The real defect, stated precisely
The bias is PROSPECTIVE, not current. The book is flat and all 17 closed trades are genuine
losses, so nothing is hidden today. It bites the first time a runner is held for weeks: closed
trades will then be loser-heavy by construction while the winner is still open and uncounted.

### Recommendation — two changes, both to what it SAYS
1. **Require N distinct ENTRY DAYS, not N trades, before the band speaks.** This is the same
   independence problem that just failed #354's graduation (107 rows, 9 days, 73 on one morning).
   17 closed live trades span far fewer independent tapes than 17 implies.
2. **Make the message carry the open book.** When the band fires, state open-position count and
   days held alongside the closed stats — so a REDUCE arriving while a three-week runner is open
   is visibly a partial picture, and the operator can weigh it. Reporting the open book is safe;
   scoring on it is not (see ruled-out above).

### Explicitly NOT proposed
- No threshold change (`_REDUCE_STREAK` 16, `_REDUCE_T20` -0.70, `_KILL_*`) — those are calibrated
  and are his to move.
- No wiring of the verdict to sizing.

---

## SHIPPED (2026-08-09) — recommendation 2 only; recommendation 1 REMOVED

Recommendation 2 implemented in `agents/market_intelligence/kill_scale_bands.py`:

- **Open-book reporting**: `format_band_line` now takes `open_positions` (ticker + hold
  days) and appends it as a trailing, clearly-labeled line — plumbed through
  `assemble_band_inputs` → `assess_bands` → `run_band_evaluation` / `band_digest_section`.
  `evaluate_kill_scale_bands` itself never receives open-position data (structural
  guarantee, not just convention), so it cannot enter the score/trigger/threshold.

Recommendation 1 (`_DAY_FLOOR = 12` distinct entry days) was initially implemented alongside
it, then REMOVED before this doc closed out — the operator called it arbitrary, and
re-measuring the premise it rested on confirmed he was right:

- **Not calibrated.** 12 was set equal to the LIVE cohort's own distinct-entry-day count on
  the day it was written (17 trades / 12 days) — a floor pinned to today's number can never
  bind against today's cohort.
- **The correlation problem doesn't reproduce.** Across the fuller paper closed-trade history
  (33 trades), only 7 distinct entry days have more than one trade, and 4 of those 7 mix a
  winner and a loser same day — no consistent within-day correlation to correct for. Live
  cannot test this at all: it has zero closed winners in its entire 17-trade cohort, so no
  live day can be mixed by construction — not evidence either way, just an untestable cohort.
- **The arithmetic alone makes any such floor moot.** This system runs ~1.3–1.4 trades per
  entry day (live 17/12 = 1.42/day, paper 33/25 = 1.32/day). A 20-trade cohort therefore
  already spans ~14 days by the time `_SAMPLE_FLOOR` clears — any day floor under ~14 is inert
  by construction, and 12 sits below that line.

So the honest outcome was removal, not a re-calibrated second number. `_DAY_FLOOR`, the
`entry_dates`/`distinct_entry_days` plumbing, and the "not independent enough to band" branch
are gone; the open-book reporting is unaffected and stays.

Verified against prod (read-only, 2026-08-09): today's verdict is HOLD before and after
(n=17 closed live trades < 20 sample floor either way — the sample floor alone accounts for
it, independent of whether a day floor exists). 20 tests in `tests/test_kill_scale_bands.py`,
full suite green (4880 passed, 7 skipped). SSoT updated: `docs/setups/safeguards.md`
"Kill / scale criteria" section + change-log entry.
