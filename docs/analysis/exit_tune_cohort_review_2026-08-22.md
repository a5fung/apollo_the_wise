# exit_tune_cohort_review — run 1 at n=22 closed live trades (2026-08-22)

**MEASUREMENT ONLY. No exit rule, stop width, profit-take level or sizing changed. Any change is
CHANGE_PROCESS + operator sign-off + backtest (THE LINE).**

## The ask

The recurring review (`data_gated_reviews.yaml :: exit_tune_cohort_review`, threshold 20) fired:
22 closed live trades against the 20 bar, 3 runner-gate trades (peak ≥ 1.5 ADR: PLTR 4.56,
NVCR 2.35, SMCI 1.68 → term 30; LEAST(22,30)=22). Methods (a)–(e) re-run on the full cohort.
The operator's underlying question: **is our stop too tight relative to how much these stocks
normally move, and what does the closed-trade record say about it?**

## Data + provenance

- Fresh prod snapshot pulled 2026-08-22 (read-only `COPY TO STDOUT` over ssh, $0):
  `mi_sell_discipline_records` (53 rows; live/magna53 22, paper/magna53 24, other 7) + exit legs
  and stop fields from `mi_live_trades` + in-hold RTH `mi_intraday_bars` (23,012 bars) +
  `mi_daily_closes` spans. Capture: scratchpad `6b173ac9…/scratchpad/_508_{records,trades,daily,minute}.tsv`,
  pulled once, read many.
- **Regime is ENTRY-STAMPED** (`mi_live_trades.regime` joined on trade_id) per the #508
  2026-08-08 rule — not the date-join the YAML predicate uses.
- Engine: `scripts/probes/_508_exit_rule_replay.py` **unchanged** (same fill contract, verified
  twice); runner: `scripts/probes/_508d_exit_tune_cohort_n22_2026-08-22.py` (untracked); full
  output: scratchpad `508d_output.txt`.
- Recorder coverage verified: all 22 closed live trades have records; 1 skip (CRMD, paper-era
  degenerate R frame). Cohort cash total: **−$321.54 across the 22** (−14.61R, deployed-risk basis).
- Peak caveat carried from #503/#306: pre-08-14 same-day round trips have FLOOR peaks (the
  recorder was blind under ~10 min until #306's instrumentation close on 08-19 — CRCL's true peak
  was +1.62R vs the recorded 0.00). Direction: every era-A candidate edge is understated, not
  overstated.

## Era segmentation — the exit stack changed underneath this cohort. Never average across.

| era | exit stack | fills | n closed | sum R | wins | day-0 exits |
|---|---|---|---|---|---|---|
| **A** | ORB-low stop, NO executable partial | 07-06 → 08-04 | **15** | −9.73 | 1/15 | 10/15 |
| **B** | ORB-low stop + live +2R partial (1/3 → BE) | 08-05 → 08-14 | **6** | −3.93 | 1/6 | 6/6 |
| **C** | entry−2R stop, half size, target pinned (signed 08-16) | 08-17 → | **1** | −0.95 | 0/1 | 1/1 |

- The +2R partial was *deployed* 08-01 but structurally could not execute on MAGNA53 OTO brackets
  until the leg-safe path (commit `18ce574f`, live 08-05). Era A's one win is **PLTR: filled
  08-04 (era A) but MANAGED under era B** — its partial fired 08-05, its stop trailed, it closed
  08-19 at +3.42R. Era A excluding PLTR = the old baseline exactly: **−13.15R, 0-for-14.**
- **Era C has one closed trade (n=1) and decides nothing.** Said, not smoothed.

## Result 1 — the answer to the stop question: yes, the old stop sat inside one day's noise

- Across the 21 ORB-low-stop trades (eras A+B), stop width vs the stock's own 20-day average
  daily range: **min 0.15 · median 0.42 · max 1.17; 18 of 21 under 1.0.** The median stop was
  less than HALF of one normal day's movement — and the width is uncorrelated with the stock's
  character (same 0.15–1.17 spread measured on 07-25, 08-06, and now).
- Meanwhile every trade that ever went anywhere ran ≥ 1.0 daily ranges: 9 of 22 peaked at
  1.0–4.6 ADR. The stop is priced in a different unit than the winners move in.
- **17 of 22 closed live trades exited on the entry day.** Three died in under one minute
  (HUT 51s, FRMI 35s, BW 7s) — that is the 9:31 whipsaw, an entry-mechanics exposure the stop
  width only modulates. Holds: 17×1d, 3×2d, 1×4d, 1×12d. Nothing has reached 20 sessions.
- The operator already signed the fix (2R stop at half size, live 08-16). Its first closed trade
  (MRVL) had width 0.72 ADR — roughly double what the ORB-low would have been (~0.36) — and
  still stopped day 0 on a real 4.5% collapse (peak +0.35R). n=1. The record cannot grade the
  new stop yet.

## Result 2 — what reaching +2R was worth under each stack (the give-back, priced)

7 of 22 trades reached ≥ +2R:

| tkr | era | peak R | kept R | capture |
|---|---|---|---|---|
| MANE | A | +7.92 | −0.23 | −3% |
| PLTR | A→B | +5.39 | **+3.42** | **+64%** |
| QBTS | A | +3.74 | −1.00 | −27% |
| SMCI | A | +3.21 | −0.70 | −22% |
| FIGS | B | +2.90 | −0.37 | −13% |
| ETON | B | +2.09 | +0.52 | +25% |
| NVCR | A | +2.00 | −1.00 | −50% |

- **Under the no-partial stack (era A), four runners reached a combined +16.9R of peaks and
  banked −2.93R.** Under the partial stack, PLTR kept 64% of a 5.4R run. That is the whole
  live-money case for profit-protection, in one column.
- Honesty on era B's two: **ETON's +0.52R came through a DEFECT**, not the design — its 5-share
  partial limit was left unstopped/untracked after the full stop-out and happened to fill +$21.89
  hours later (the #566 hole, fixed and proven on AMLX 08-18). **FIGS under-delivered on both
  halves**: partial filled +1.13R against a +2R target, BE stop filled −1.10R against 0 — live
  fills slip on fast collapses, so every sim row below (limit-at-level contract) is optimistic
  against era-B reality.

## Result 3 — the 34-candidate grid, era A only (the clean cells)

Era A is the only era where a candidate cleanly REPLACES the deployed rule (era B/C trades
already ran with a live partial acting on the path). Mean kept R per trade, n=15, top/bottom:

```
ADR1_exit_all        +0.48   <- lead is ONE trade: MANE (+6.56R — full exit at 1 ADR on a
rgm_none/3R/2R_exit  +0.12      0.15-ADR stop). Without MANE it is +0.05. Not evidence.
R3_exit_all          +0.05
R2_part1/3+BE        -0.30   <- the deployed rule's replay: beats actual by +0.35/trade,
...                             spread across 4 trades (MANE/SMCI/NVCR/QBTS +0.67 each),
nothing              -0.63      and it does NOT destroy PLTR (+3.13 vs +3.42 actual).
actual               -0.65
```

- Direction unchanged from the 07-30 and 08-17 runs: **any profit-protection beats the nothing
  that era A actually ran.** Level/basis rankings remain single-trade-driven — do not read them.
- The full-cohort n=22 grid (era-mixed, continuity only) is in the probe output; its 'nothing'
  row inherits ETON's defect leg as a fake +2.00 terminal and is flagged there.

## Result 4 — regime (c0): the cells filled, and the confound MOVED, it did not die

Live-only, entry-stamped, n≥4 floor met in three cells — the paper-vs-live axis is gone:

| regime | n | mean realized R | wins | peak mean / max | eras |
|---|---|---|---|---|---|
| Bull | 7 | −0.70 | 1/7 | +1.16 / +2.90 | B×6, C×1 |
| Choppy | 7 | −0.27 | 1/7 | +2.18 / +7.92 | A×7 |
| Correcting | 7 | −0.97 | 0/7 | +1.50 / +3.74 | A×7 |
| Crisis | 1 | −1.03 | 0/1 | +0.07 | A×1 |

🔴 **SAY THE LIMIT OUT LOUD: regime is now confounded with ERA.** Every live-Bull trade ran
under the post-08-05 stack (partial/2R-stop); every non-Bull trade ran under the bare ORB-low
stop (PLTR the spanner). A per-regime realized-R verdict is a comparison of exit stacks as much
as of tapes, and **this doc publishes none.** The 08-01 confound (paper-vs-live) was broken by
accrual; this one will break the same way — non-Bull trades under the era-C stack.

On the operator's hypothesis ("runners probably happen more often in bull markets"): the only
semi-era-robust column, peak reached, still runs AGAINST it — Bull is the weakest of the three
cells (max +2.90 vs +7.92 Choppy / +3.74 Correcting), same direction as the 08-17
`exit_regime_separability` read. But Bull peaks are truncated by partial/BE-shortened holds, so
even this is not clean. **Not testable to a verdict on this data; what settles it is non-Bull
closes under the era-C stack, which accrue automatically.**

The `rgm_*` (let-runners-go-in-Bull) arms all print Bull=−0.59 — an artifact of the same
confound (the Bull cell contains no untouched runner to let go), not a refutation.

## Result 5 — stop-floor refutation (e): stands, and its lesson is already live

- The 08-06 refutation (floored stops = delayed stops; k floors −5.7R to −14R, zero winners) is
  not re-run here — no new non-bull no-partial trades exist to re-run it on. **It stands as
  measured.**
- Its durable mechanism — *widening the stop widens the R-unit and silently moves the +2R
  target* — is exactly what the operator-signed 08-16 change neutralizes (target PINNED to the
  ORB-based price while the stop widens). The open question the refutation flagged ("a floor
  that fails when nothing trends may behave differently when things run") is now a LIVE
  experiment: era C. n=1 closed. Grade it at the next milestone, not today.

## Result 6 — character (c): still under-populated, one consistent note

ADR20 tiers (slow <3.5% n=2 · mid 3.5–6.5% n=9 · fast >6.5% n=11): the mid tier holds every
winner and 5 of 7 runners; the fast tier is 0-for-11 (−10.37R) with the tightest stops
(median 0.36 ADR). Cells are n≤11 with era mixing — **directional at best, no per-tier level
supported.** (The 07-25 finding repeats: fast names carry the narrowest stops relative to their
own range — backwards from the operator's premise that fast names need the most room to breathe.)

## Banked vs open — kept strictly apart (unrealised marks are NOT results)

- **Banked, the 22 closed: −$321.54.** Everything above is from these.
- **Open, 3 positions (not counted anywhere above):** ABCL (era B, entered 08-10, peak +35%),
  AMLX (era C, 08-18, peak +36%), MRNA (era C, 08-19, peak +46%) — all Bull, all partial-fired
  with banked thirds inside their `total_pnl`, all first-ever live positions to run multi-week.
  If they finish well they land in the era-C column of the NEXT run; today they prove only that
  the new stack lets positions survive long enough to have marks.

## What this does NOT answer

1. **Whether the 2R stop is right** — era C has one closed trade. It answers "was the OLD stop
   too tight" (yes, measured three times), not "is the new one correct."
2. **A per-regime exit rule** — blocked by the era confound above; publishing one would be false
   precision.
3. **Trigger level/basis within the partial family** — rankings ride on 1–4 trades (the ADR1
   full-exit "win" is one trade). n=22 with 7 runners cannot separate levels.
4. **Live fill quality vs the sim contract** — FIGS shows real partials slip on both halves;
   nothing here quantifies that beyond n=1.
5. **#545's grid cells**: #545 (entry/exit tactics program) is still pending design (ETA 08-26),
   so per its own instruction this ran standalone. It covers the exit-side cells only (profit-take
   level × basis × regime × era on the live cohort); entry-timing and re-entry cells untouched.

## Verdict, plain words

**Yes — the stop this record was compiled under was too tight: the median stop was 0.42 of one
normal day's range, 18 of 21 were under one day's range, and 17 of 22 trades died the day they
were opened.** Trades that reached +2R under that stack gave essentially all of it back
(4 runners, +16.9R of peaks, −2.93R banked). The two mechanisms the operator has since signed —
the +2R partial and the 2R-wide stop with the pinned target — are each visible working exactly
once on closed live money (PLTR +3.42R; MRVL's wider stop absorbing nothing it shouldn't), and
three open positions are the first ever to run. **The record supports the direction of both
changes and cannot yet grade either; the next milestone (n=40) with era-C closes is what grades
them. No new rule change is recommended from this data.**

## Follow-ups for the main session (not applied here — no commits from this card)

- `data_gated_reviews.yaml`: re-bump `exit_tune_cohort_review` threshold 20 → 40 (RECURRING
  idiom) + record this run; note the ETON defect caveat beside any future use of its legs.
- `exit_tune_bull_regime_read` sits at **7 of 8** closed live Bull trades — it fires on the next
  Bull close; this doc's Result 4 is most of its prep.
- Feed this doc into #545's inventory (scope item a).
