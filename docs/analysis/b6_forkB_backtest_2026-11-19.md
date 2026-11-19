# B6 fork B backtest — the gate stays at 22: the 27 trades fork B would have added lose 5R; the frozen rule reads CLOSE, by a one-trade margin (2026-11-19 PT)

Pre-registration (rule frozen before the data, deviations dated): `docs/analysis/b6_forkB_backtest_prereg_2026-11-19.md`.
Driver, captures, full output: `scripts/probes/_b6_backtest_1119/` (`run_backtest.py`, `results.txt`,
`campaigns.tsv`). $0, read-only, nothing live changed. Owner SSoT: `docs/setups/catalyst_rubric.md`.

## Branch fired

Sample sizes: added arm n = 27 entries (of 62 added HIGH alerts, 176 downgraded names); comparator n = 15 entries.

**CLOSE under the frozen rule — but by one trade. Either reading keeps the gate at 22; no reading brings fork B.**

- The frozen close test: readable, the added trades total zero or below, and their big-winner share is
  no better than the comparator's. Added: 27 entered, −5.2R, 3 of 27 at +3R (11.1%). Comparator (every
  real post-rescale HIGH alert): 15 entered, +5.2R, 2 of 15 at +3R (13.3%).
- ⚠ **CLOSE does not survive a like-for-like comparator.** The added arm is pre-judge; the comparator
  above is post-judge. Against every real alert whose floor tier was HIGH (judge demotions kept in):
  19 entered, +3.2R, 2 of 19 at +3R (10.5%) — the added arm's share is then slightly HIGHER and the
  same frozen tests read IN BETWEEN (keep 22, one re-read at 30 added entries). This is a sensitivity
  added after the run, not the pre-registered comparator.
- **Three thin margins:** the comparator has exactly the 15 entries the rule requires; check 4 passed
  at 54 of 56 (96% against 95%) after fixes aimed at its own misses on those same rows — an in-sample
  fit; and the big-winner share is decided by one trade either way.
- **What is solid:** the added trades total below zero under every variant run (−5.0R to −5.7R; −7.4R
  under mechanism B2), and all three of their big winners sit in one earnings week (−13.3R without it).
  "Bring" needs a positive total that survives removing the best week. It is not close.
- **The call that remains (not THE LINE — nothing live either way):** treat fork B as closed for good
  (the frozen reading), or keep it open for the one re-read at 30 added entries (the like-for-like
  reading). Rec: the re-read — "closed for good" should not rest on one trade.
- **The upper bound points the other way in sign, shown as the rule requires:** all 176 downgraded
  names entered at 09:31 with no score bar and no submission gates total +27.1R over 107 entries. Two
  thirds of that sits in names fork B would NOT add (table below).
- First run the same day read NOT READABLE (check 4 at 85%); see "Run history".

## Population (post-rescale, alert date 2026-08-22 to 2026-11-18)

| | Names | Of which alerted for real |
|---|---|---|
| Downgraded by the composite | 176 (173 from strong, 3 from game-changer) | 4 |
| PASS (scored, never downgraded) | 72 | 26 |
| Pre-rescale downgraded / PASS (separate, never pooled) | 150 / 57 | 15 / 51 |

26 post-rescale downgrade events carry a non-composite reason (missing or weak revenue number, sparse
news); none of those names has a scored row, so none is in either arm.

## Fidelity checks (second run)

| # | Check | Result | |
|---|---|---|---|
| 1 | Re-scorer reproduces the stored score from the stored parts | 3,268 of 3,268 scored ticks | PASS |
| 2 | "First tick over the bar" rebuilds the PASS arm's real alerts | 26 of 26, none predicted that did not exist | PASS |
| 3 | Harness validation against real fills (`ep_replay.py validate`) | entry 100%, exit class 97%, R within 0.25 83% | PASS |
| 4 | Replay entered / not entered vs real trade rows, 56 real post-rescale HIGH alerts, era-correct gates | 54 of 56 (96%; bar 95%) | PASS |
| 5 | Population printed before any return; abstain rate per arm | 0% (added arm), 2% (comparator); ceiling 30% | PASS |

Check 4 by cause:

| Cause | Names | Fixable from stored data? |
|---|---|---|
| Really entered; replay refuses because the 09:31 bar's open reads the gap under 9% — the live read a few seconds earlier or later passed | AEHR 11-03 | No — minute bars cannot place a price inside the minute |
| Really filled 09:35:53 at 72.21; replay's price at 09:35 puts the limit over the 1.5× chase cap | PENG 10-07 | No — same reason |
| Excluded as not replayable (no opening bar at the broker; position too small to size) | 3 names | n/a |

The first run's other misses are resolved: the pull gap (DG, QCOM, QXO, SNDK), the open-below-floor
rule applied before it was live (CLS), the price-aware entry (HOOD, now modelled), and five cancelled
orders my check had counted as entries (AKAM, SNOW, U, VRT, REGN).

## What fork B (mechanism B1) would have added — the funnel

| Step | Names |
|---|---|
| Downgraded by the composite | 176 |
| Restored grade still scores under 65 | 97 (best case median 55; 14 within 5 points of the bar) |
| Killed by a rule that never reads the grade (size, gap fell under 9%, shortlist) | 13 |
| Would have alerted anyway / no scan record / corrector already restored it | 4 |
| **Would newly alert HIGH, before the judge** | **62** |
| … opened below the gap floor after a real-time flip-up | 10 |
| … first HIGH at 09:45 or later (outside the entry window) | 7 |
| … opening range wider than 1.5× ATR | 6 |
| … gap under 9% at submission | 4 |
| … order never triggered by 10:00 | 8 |
| **Entered** | **27** (26 closed, 1 still open; 2 by the price-aware limit entry) |

About 29 added entries a quarter before the judge. The judge kept 61 of 90 real floor-HIGH alerts
(68%), so about 18 after it — which 18 cannot be known at $0.

## Results in R (today's entry, stop and exit ladder on every date; one risk unit per trade)

| Arm | Entered | +3R or better | Best | Full losers (−0.9R or worse) | Losing / winning | Total | Mean |
|---|---|---|---|---|---|---|---|
| **Added by fork B (B1)** | 27 | **3 (11%)** | +4.13R | 15 | 20 / 5 | **−5.2R** | −0.19R |
| Added, gates era-correct instead of today's (sensitivity) | 29 | 3 (10%) | +4.13R | 16 | 21 / 6 | −5.7R | −0.20R |
| Added under B2 (gate off, 5% revenue net) | 18 | 1 (6%) | +3.81R | 11 | 14 / 3 | −7.4R | −0.41R |
| PASS names rebuilt the same way | 4 | 0 | +1.62R | 3 | 3 / 1 | −2.1R | −0.53R |
| PASS names that really alerted HIGH | 4 | 0 | +1.62R | 3 | 3 / 1 | −2.1R | −0.53R |
| **Comparator: every real post-rescale HIGH alert** | 15 | **2 (13%)** | +6.01R | 8 | 9 / 4 | **+5.2R** | +0.34R |
| Upper bound: all 176 admitted at 09:31, gates off | 107 | 14 (13%) | +4.67R | 47 | 59 / 40 | +27.1R | +0.25R |
| Pre-rescale upper bound (separate, never pooled) | 96 | 8 (8%) | +8.38R | 35 | 48 / 32 | +19.1R | +0.20R |

- The PASS arm has 4 entries, under the floor of 15, as expected before the data; the rule's fallback
  comparator was used. So this answers "are the added trades as good as what the system already
  takes", not "as good as the earnings names the gate kept".
- Still open, counted at its mark: APP 11-05 (+0.97R) in the added arm; eleven names in the upper bound.

**Per alert week, added arm:**

| Week | Entered | +3R | Total |
|---|---|---|---|
| Aug 24–28 | 3 | 0 | −1.0R |
| Sep 28–Oct 2 | 1 | 0 | −1.0R |
| Oct 19–23 | 1 | 0 | −1.0R |
| **Oct 26–30** | 8 | **3** | **+8.1R** |
| Nov 2–6 | 11 | 0 | −8.3R |
| Nov 9–13 | 3 | 0 | −2.0R |

- Without Oct 26–30 the added arm is −13.3R; its three big winners (CROX, CVNA, CPRI) came on 10-29 and 10-30.
- The comparator: +5.2R, −0.6R without its best week; its two big winners sit in two different weeks.

**Slot cap and breakers (separate column):** none of the 27 added entries met a full book (at most 4
open positions), an account-level block, or five real alerts ranked ahead of it. Removes nothing.

## Where the upper bound's +27R sits (post downgraded names, gates off, split by why fork B does not add them)

| Group | Entered | +3R or better | Total | Mean |
|---|---|---|---|---|
| Restored grade still under the score bar | 55 | 8 | +17.9R | +0.33R |
| **Added by fork B and entered** | 27 | 3 | −5.0R | −0.18R |
| Would alert, opened below the gap floor | 8 | 0 | +1.2R | +0.15R |
| Killed by a rule that never reads the grade | 7 | 2 | +7.8R | +1.12R |
| Would alert, first HIGH after 09:45 | 5 | 1 | +8.1R | +1.62R |
| Other (alerted anyway, gap under 9% at submit, never triggered) | 5 | 0 | −2.9R | |

(The added row reads −5.0R here and −5.2R above: here every name is entered at 09:31, above at its own submit time.)

## Sensitivity: the pre-judge comparator

| Comparator | Entered | +3R or better | Total | Mean | Frozen tests read |
|---|---|---|---|---|---|
| Real final HIGH alerts (pre-registered) | 15 | 2 (13.3%) | +5.2R | +0.34R | CLOSE |
| Real floor-HIGH alerts, judge demotions kept in (added after the run) | 19 | 2 (10.5%) | +3.2R | +0.17R | IN BETWEEN |

## Meaning

- Restoring the grade mostly changes nothing: 97 of 176 still score under the bar, and of the 62 that
  would alert, 27 become trades.
- Those 27 carry about the same big-winner rate as the trades already taken, more full losers, and a
  negative total against a positive one. All of their upside is one earnings week.
- B2 is worse than B1 on every line: two of the three big winners (CROX, CPRI) had revenue growth under
  5%, so the safety net would have cut them anyway. The B1-vs-B2 ruling is moot on this result.
- The earlier price read (downgraded names ran more often) is real and shows up in the upper bound —
  but 8 of its 14 big winners and +17.9R of its +27.1R sit in names that stay under the score bar even
  with the grade restored. Fork B does not reach them. That is an observation about the score on one
  season of 55 trades, not a finding.

## What this does not answer

- **Inside-the-minute timing.** The submission price is the minute bar's open; two real entries were
  misread for that reason. Check 4's margin is one name.
- **The judge.** It removes about a third of floor-HIGH alerts; which third of the 27 is unknown.
- **More than one earnings season.** 22 of the 27 entries fall in three weeks; the comparator is 15 trades.
- **Names the grade corrector or an intraday re-grade would have changed** after the downgrade tick.
- **The ask-aware entry trigger** (no stored quotes).
- **Live sizing on a price-aware fill.** Live sizes on planned risk; the replay scores R on the actual
  entry-to-stop distance. Two added entries and one comparator entry are affected.
- **Whether the composite measures the right thing** (operator ruling 2026-09-05). This measures only
  what its downgrade costs or saves as trades.

## Action

- Operator: none required for the gate — keeping 22 is the status quo under every reading.
- One small call: closed for good, or one re-read at 30 added entries (see "Branch fired"; rec: re-read).
- Open observation, not filed as work here: downgraded names that stay under the score bar were
  +17.9R on 55 entries with the gates off. If he wants it looked at, it is a score question.

## Run history (2026-11-19 PT)

1. **First run — NOT READABLE.** Check 4 read 42 of 55, corrected to 45 of 53 (85%). Causes: scan ticks
   and flip events had been pulled for the earnings population only, so 35 comparator names ran with
   two gates off; the "still on the board" rule was an approximation; the price-aware entry was not
   modelled; my check counted cancelled orders as entries.
2. **Second run — CLOSE.** `pull_6` wired in; the live submission order modelled from
   `entry_pipeline.submit_trade_entry` and `order_manager._pick_entry`; check 4 scored with era-correct
   gates. No bar or decision threshold moved. Added arm: 27 entered and −5.0R in the first run, 27 and
   −5.2R in the second; the comparator moved from 21 entered (−0.5R, inflated) to 15 (+5.2R).

## The names

All 62 that would newly alert, one line each with composite, first HIGH tick, outcome and the B2 flag:
`scripts/probes/_b6_backtest_1119/results.txt` §"the ADDED names". The 27 that enter: ANF, ESTC, GAP,
ACN, RNG, CROX, CVNA, HII, MAX, NCLH, AN, CDNA, CPRI, BRKR, DUOL, RIOT, W, XYZ, APP, EPAM, GCT, TPR,
IREN, SNDK, LITE, CBRS, LFTO. Not classified here as good or bad cuts.
