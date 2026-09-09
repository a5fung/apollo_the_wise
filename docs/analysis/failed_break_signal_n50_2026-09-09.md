# A flag break that closes back under its base high ends 7.9 points worse — but only once you measure both cohorts from the same level

**2026-09-09 · read-only · $0 · the `intraday_failed_break_signal_n10` gate (ready 56 days, unreadable until its predicate was fixed today)**

## Method / population — which rows, over what window

- **Rows.** All `mi_flag_breaks` rows with 10 settled sessions after the break: **162** (FAILED 50,
  HELD 112), out of 167 all-time. Joined to `mi_daily_closes` for the break-day close and the
  close 10 sessions later.
- **Cohort definition.** FAILED = the break day CLOSED back below `base_high`. HELD = it did not.
- **⚠ This is the EOD-classified failure, not the real-time one.** The review's stated premise is a
  signal *"captured in real-time the moment the failure occurs, not at 5:25 PM"*. Those columns
  (`failed_at`, `low_after_break`, `bars_until_fail`) do not exist yet — Phase 1 builds them. So
  this measures **whether the phenomenon carries signal at all**, which is the precondition for
  building the real-time surface, not a test of the real-time surface itself.
- **Era.** No entry/exit rule bears on it — nothing here is a trade. `flag_continuation` is
  deprecated as a strategy and its stage board is observational, so no live rule was involved at
  any point in this window.
- **This gate read 0 until today.** Its predicate asked for `parent_invalidated_eod = TRUE`, an
  EOD close-based invalidation that is a different question; 54 settled cases were sitting behind it.

## The trap: measured from the break-day close, the hypothesis looks INVERTED

| cohort | n | fwd-5 avg | fwd-10 avg | fwd-10 median | up at 10 |
|---|---|---|---|---|---|
| FAILED | 50 | **+1.51%** | −3.33% | −5.19% | 38% |
| HELD | 112 | −0.91% | **−5.03%** | −6.75% | 30% |

On this reading a failed break *outperforms* — which would have been a confident, publishable, and
wrong answer. **The two cohorts do not start from the same place:** a FAILED break closes *below*
`base_high` by construction, so it is measured from a lower base and has more room to bounce.

## The control: same reference level for both, and the signal is real

Measured against `base_high` — the one level both cohorts share:

| cohort | n | start vs base_high | at 10 sessions | median at 10 | above base_high at 10 |
|---|---|---|---|---|---|
| FAILED | 50 | −3.85% | **−7.10%** | −8.18% | **34%** (17/50) |
| HELD | 112 | +6.26% | **+0.81%** | −2.52% | **46%** (52/112) |

**A break that closes back under its base high ends 7.9 percentage points worse** relative to the
level both are judged against, and is a third less likely to be trading above that level ten
sessions later. The hypothesis is supported once the starting-point artifact is removed.

⚠ **Both cohorts LOSE ground over the ten sessions** (FAILED −3.85 → −7.10; HELD +6.26 → +0.81).
Clearing `base_high` is not by itself a bullish event in this population. The failed-break signal is
**relative**, not a standalone edge.

## Recommendation

- **The phenomenon carries signal — Phase 1 is justified.** Build `failed_at`, `low_after_break`
  and `bars_until_fail` so the reversal is captured when it happens rather than inferred at the
  close.
- **Ship it as an observational surface only.** `flag_continuation` is a deprecated strategy and
  continuation is a **family**, not a setup — there is no buy point or stop here to attach a signal
  to. This is detector quality, not P&L.
- ⚖ **No live rule, no operator sign-off needed for the shadow columns.** Any promotion to an
  operator-facing alert or an entry/exit input is CHANGE_PROCESS + sign-off.

## What this does not answer

- **It does not test the real-time signal**, which is the thing the review actually wants. An
  intraday reversal below `base_high` that recovers before the close is invisible here and may
  behave differently from one that closes under.
- **It is not a P&L result.** No trade was taken; there is no entry, stop, or slippage in any number
  above. A 7.9-point spread in drift is not 7.9 points of realized return.
- **n=50 failed cases**, and the cohorts are unbalanced 50/112.
- **It does not control for regime, market cap or base age** — a FAILED break may simply be a
  weaker-tape phenomenon, which would make the signal a proxy rather than a cause.
