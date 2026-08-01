# Exit discipline (#508 / #503) — state of the work, 2026-08-01

> ✅ **APPROVED AS THE SSoT FOR APOLLO EXIT DISCIPLINE (external review, 2026-08-01).** Ruling:
> file it, let `exit_tune_cohort_review` sleep until T1 (20 closed live trades), and take the
> exit debate out of active working memory. **Do not re-open any part of §3 before its trigger
> in §5 fires.** The next live question is §3.5 — why live trades die in 1.5 days — which is an
> ENTRY/REGIME investigation, not an exit one.

**Purpose of this document:** a single self-contained statement of where the exit-discipline work
stands, so nothing has to be re-asked. Goals, what is settled, what is not, what is built, what
unlocks the next decision, and who does what.

**Status: NO RULE SHIPPED. Nothing touches the live exit path.**
**THE LINE:** exit discipline is strategy. Every change below needs operator sign-off +
CHANGE_PROCESS + backtest. This document produces evidence and options; it does not decide.

---

## 1. The goal

Make the existing EP strategy profitable before adding any new setup (operator, 2026-07-29). The
specific failure being attacked: **trades reach a meaningful profit and give all of it back.**

The operator's proposed shape, 2026-07-30:

> *"in general +3R is a good spot to take partial profit, something like 1/3rd at 3R then move stop
> to breakeven — however, this requires R to be set correct, too tight or too loose will mess it up."*

Refined 2026-08-01: **the trigger should be profit-based, not time-based**, and the right level may
**depend on regime** — take profit more aggressively in weak tape, let winners run in bull markets.

**Desired outcome:** a profit-taking rule (level, size, and regime-conditioning) chosen on evidence,
that measurably reduces give-back without capping the rare large winner.

---

## 2. What is SETTLED (verified; safe to rely on)

Every figure below was independently recomputed twice, the second time by a reviewer who
reimplemented the simulation from prose and matched every digit.

**2.1 The deployed rule is effectively inert on live money.**
**What the deployed rule actually is** (stated because parking a rule you have not described is how
it gets misremembered): it takes 1/3 off at hold-day ≥3, and **unconditionally at day ≥5 even when
underwater** — which arms breakeven and, with breakeven above an underwater close, closes the
remainder in the same step (`exit_logic.py:301-303`, `:337-373`). So it is also a **de-facto day-5
full time-exit**. `hold_days` counts **calendar** days from `alert_date` (`exit_logic.py:217`), so a
Friday entry hits the day-3 gate on its 2nd trading day. It runs in `run_partial_exits` (3:45 PM ET)
and `update_open_positions_live` (4:45 PM ET). Before day 10 nothing else can act: the SMA trail needs
≥10 closes and the giveback hook is default-off with no live caller — **which is the mechanical reason
10 of 12 live losses print exactly −1R.**

It gates profit-taking at hold-day 3. Live trades hold **1.50 days** on average; **1 of 12** has ever
reached day 3; **0 partials have ever fired on live money.** Its measured value on the live cohort is
**+0.09R per trade** — last of all 34 candidates tested.

**2.2 The give-back is real and large.**
MANE reached **+7.92R** and closed **−0.23R**. Across the 12 live closes, 4 trades reached ≥+2R and
all 4 gave everything back.

**2.3 A profit trigger fires far more often than the time gate, and scores better on live data.**

| rule | live fires | live gain/trade | paper fires | paper gain/trade |
|---|---|---|---|---|
| **current (day 3)** | **1** | **+0.09** | 7 | +0.36 |
| 1/3 at +1R → breakeven | 4 | +0.36 | 9 | +0.37 |
| 1/3 at +2R → breakeven | 4 | +0.47 | 8 | +0.27 |
| 1/3 at +3R → breakeven | 3 | +0.41 | 6 | +0.29 |
| 1/2 at +2R → breakeven | 4 | +0.58 | 8 | +0.35 |
| exit ALL at +2R | 4 | +0.91 | 8 | +0.60 |
| exit ALL at +3R | 3 | +0.91 | 6 | +0.68 |

*(gain = mean kept R per trade vs what actually happened)*

**2.4 R is not a consistent unit.** Entry-to-stop distance spans **0.15 to 1.17 of the ticker's own
20-day average daily range — a 7.7× spread.** So one "+2R" trigger fires after 0.31 of a normal day's
move on MANE and after 2.35 days on NVCR. This is arithmetic, not a sample artifact.

**2.5 The live cohort's losses are largely not an exit problem.**
10 of 12 stopped out at a full −1R.

⚠ **Corrected 2026-08-01 — the "4 never went green" figure is NOT verified and one case is known
false.** The peak instrumentation reads `highest_price_seen`, which is blind under ~10 minutes, and
**all four of those trades lived inside that window**: CRCL 9.5 min, WDFC 9.3 min, TSEM 11.7 min,
**HUT 51 seconds**. CRCL's true intraday peak was **+1.62R** against a recorded 0.00. So the correct
statement is: *at least 4 trades that ran, and an unknown number of the 4 short-lived ones, are
addressable by an exit rule.* **Every recorded peak here is a FLOOR**, which biases every candidate's
measured edge DOWN.

⚠ **The triggers inherit this undercount.** T3 and T1's runner term both key on the same recorded
`peak_adr`, so a fast trade that ran and reversed inside 10 minutes does not count toward either.
Fixing the instrumentation (minute-bar peaks for short holds) would raise both counts — that is a
build, not a wait, and it is the one thing on this page that could be accelerated rather than
waited for.

---

## 3. What is NOT settled — and precisely why

**3.1 Which trigger LEVEL is best.** +1R / +2R / +3R are within noise of each other at n=12.

**3.2 Which UNIT (R vs daily range).** Unresolvable with current data, for a concrete reason: on
KURA the stop is 0.166 daily ranges, so its "+3R" **is** 0.50 daily ranges — the two units are the
same print on that trade. The apparent cohort disagreement traces to one or two trades clearing a
trigger by cents.

**3.3 Partial vs full exit.** Full exits score highest on both cohorts — but only because almost
nothing in this data ran. **No live trade has ever run**, so the upside that a partial preserves and
a full exit forgoes has never been observed on real money. The comparison is undecidable until it is.

**3.4 Whether regime should condition the rule.** **Regime is confounded with cohort**: Bull is 22 of
**24** paper magna53 trades, Correcting is 7 of 7 live, only Choppy has both sides (4 live / 2
paper). Today's grid cannot separate "bull markets run further" from "paper behaves differently
from live."

⚠ **A second confound §3.4 originally missed: paper is also OLD ENTRY MECHANICS.** 19 of the 24
paper magna53 entries predate the 2026-06-05 timezone/ORB-window fix (`8de7849`), and the data
shows it — paper fills as late as **11:35 ET** (KURA), 11:31 (TEAM), 10:53 (AMD), all of which
today's system hard-cancels at 10:00. Later fills select for breakouts that already persisted.
So "paper vs live" is *regime* **and** *entry era*, and KURA — one of only two magna53 winners
powering every cost/win figure — is one of the impossible-today fills.

**3.5 Why live trades die in 1.5 days.** ⭐ **A CONTROL ALREADY EXISTS AND NOBODY HAD USED IT.**

`mi_orb_shadow_trades` runs the SAME alert universe through the SAME gates and the SAME exit ladder
with **no broker, no real fills, no real stops**, since 2026-04-29. That makes it the clean test of
"is this live execution, or is it the setup?" — it removes the execution axis entirely.

**Closed shadow trades, by month** (⚠ n=16 of 241 rows — 132 never entered, 48 still open, 45
gate-blocked; the hold figures below are CLOSED rows only, an earlier read of mine that included open
positions was wrong):

| month | regime era | n | mean hold | winners | mean R |
|---|---|---|---|---|---|
| 2026-05 | Bull | 4 | 2.50d | **0** | −0.81 |
| 2026-06 | Bull | 5 | 1.40d | **0** | −0.85 |
| 2026-07 | Choppy/Correcting | 7 | 1.29d | **0** | −0.99 |

**Zero winners in every month, including the two BULL months, with no broker involved.** Holds are
1.3–2.5 days throughout — matching live's 1.50, not paper's 3.17.

**What that implies, stated at the strength n=16 supports:** the short hold and the round-trip to −1R
are properties of **the setup as currently specified — ORB entry with an ORB-low stop — not of live
execution, and not solely of the July tape.** It also means the PAPER cohort's 3.17-day hold is the
outlier that needs explaining (see §3.4's entry-era confound: 19 of 24 paper trades predate the
2026-06-05 ORB-window fix, with fills as late as 11:35 ET that today's system cancels at 10:00).

⚠ Not conclusive: 16 closed trades, and 48 shadow positions are still open. But this is evidence that
**already exists** — no waiting required — and it points away from exits and away from execution. Not explained by stop width (tight-stopped live trades hold
1.33 days, wide-stopped 1.67) nor by regime (live holds are 1.0–1.7 days in *every* regime, while
paper holds 2.9–6.0 in every regime). **This is upstream of exits and is the larger open question.**

---

## 4. What is BUILT and working

- **Recorder** (`sell_discipline.py`) — 43 closed trades with peak, give-back, capture, hold days,
  regime, and daily-range-normalised fields. ⚠ It had a defect until 2026-08-01: it measured stop
  width from the *trailed* stop, so every trade that ran recorded garbage. **Fixed at the root and
  all 43 rows backfilled** (43/43 internally consistent; the 12 live rows verified byte-for-byte
  unchanged). Data accruing from here is sound.
- **Replay engine** (`scripts/probes/_508_exit_rule_replay.py`) — **34 candidate rules** scored under
  a conservative fill contract (limit-at-level fills, breakeven stops that gap through, bar-by-bar
  replay where minute data covers the day, pessimistic tie-breaks). Verified twice.
- **Regime-conditional family** — `rgm_<bull>/<chop>/<corr>`, where an arm set to *none* means hold
  with no profit-take in that regime. Six partial variants and two full-exit variants, i.e. the
  operator's "aggressive in bear, let it run in bull" hypothesis is already encoded and scored.
- **Per-regime breakdown** of every rule, each cell printing its own n.
- **Recurring review** (`exit_tune_cohort_review` in `data_gated_reviews.yaml`) — re-runs the whole
  comparison automatically at 20 / 40 / 60 / 80 / 100 closed live trades.

---

## 5. TRIGGERS — what fires the next decision, and when

| # | Trigger | Status today | What it unlocks |
|---|---|---|---|
| **T1** | **20 closed live trades** | **12 of 20** — 8 more needed | The recurring review fires automatically; the full 34-rule comparison re-runs |
| **T2** | **Live trades in a BULL tape reach 4** | **1 of 4** | Makes the regime grid readable — separates "bull runs further" from "paper ≠ live". **AUTOMATIC** since 2026-08-01: `exit_regime_separability` in `data_gated_reviews.yaml`, evaluated nightly, fires independently of T1 |
| **T3** | **Live trades that RAN** (peak ≥ 1.5 daily ranges) | 2 (SMCI 1.68, NVCR 2.35) | Prices what a partial gives up vs a full exit — resolves 3.3 |
| **T4** | **Any live trade holding ≥3 days** | 1 of 12 ever | Would make the *current* rule non-inert and testable as-deployed |

### ⚠ WHAT STOPS THE CLOCK — read this before trusting the triggers

**The single most likely way this work dies is not being wrong; it is going silent.**

1. **The kill/scale bands activate at the SAME n=20** (PLAN #503; projected ~2026-08-20), and on a
   0-for-12 start **REDUCE is the modal outcome and KILL is live.** If the band reduces or halts live
   trading, **live accrual stops and every trigger on this page goes quiet forever** — the escalation
   job only surfaces reviews that are READY or ERRORING, so a healthily-pending predicate frozen at
   12/20 is never mentioned again. This is scheduled, not hypothetical.
2. **STALL CLAUSE (added 2026-08-01, mirroring `cooldown_admission_unassumed`):** if live accrual halts
   — band action, `/pause`, demotion — or if n < 20 by **2026-10-01**, **run the review at whatever n
   exists** rather than continuing to sleep. A smaller honest read beats an indefinite wait.
3. **ABANDONMENT / RE-BASELINE:** if #503 concludes the entries themselves are the problem and they
   are changed, the pre-change cohort is **re-baselined, not blended** — trades taken under different
   entry mechanics are a different population (see §3.4's entry-era confound).

**T1 and T2 are AUTOMATIC and independent of each other** — both are `data_gated_reviews.yaml`
predicates, evaluated every weeknight at 17:30 ET by `escalate_overdue_reviews()` inside
`_post_nightly_audit_job`, which Telegrams when a review becomes ready and escalates again if a
ready review is left sitting. Verified 2026-08-01 against prod: T1 returns 12/20, T2 returns 1/4.
**T3 and T4 are NOT independently automatic** — they are read and reported whenever T1 or T2
fires. That is deliberate: neither unlocks a decision on its own, they qualify one.

⚠ **Two honest caveats on T1's mechanics**: (a) its first term counts **all** live closes with no
`signal_type` filter, so another strategy graduating to live would advance it with out-of-cohort
trades — the comparison cohort and T2 are magna53-only; (b) "re-runs at 20/40/60/80/100" overstates
it — only the **notification** is automatic; each later milestone is a manual threshold re-bump, and
the runner conjunct scales with it (at 40 it silently requires 4 runners, at 100 it requires 10).

Why T2 exists separately: a bull tape could arrive long before 20 closed trades, and it is the
ONLY thing that breaks the regime/cohort confound. Without it the regime question would have
waited on an unrelated counter.

---

## 6. WHAT WE ARE MISSING — stated plainly

1. **Live winners.** Zero. Everything measured so far is loss-cutting.
2. **Live trades in a bull market.** One. This is the specific gap blocking the regime question — not
   sample size in general.
3. **Live trades that survive.** One has reached day 3, ever.
4. **An explanation for the 1.5-day death.** Not stop width, not regime, and — per the shadow control
   — **not live execution either.** The remaining candidate is the setup specification itself: an ORB
   entry filled in the first 2-3 minutes with a stop at the ORB low is maximally exposed to
   opening-auction whipsaw. Unproven, but it is now the leading hypothesis rather than one of four.

Note what is *not* missing: instrumentation. The recorder, the engine, the regime grid and the
recurring trigger are all built and verified. **We are waiting on trades, not on tools.**

---

## 7. NEXT STEPS — who does what

**Operator**
- **Decision pending: none required now.** The rule change is deliberately parked (see 3.1–3.4).
- **One judgement call available if he wants to act early:** ship a profit trigger now, accepting
  that the *level* is not yet tuned. ⚠ **Corrected 2026-08-01:** an earlier draft justified this with
  "every alternative beats the inert day-3 rule". **That is true on LIVE only.** On paper the current
  rule scores +0.36 against +0.27 (1/3@2R), +0.29 (1/3@3R) and +0.35 (1/2@2R) — it BEATS them — and
  paper is the only cohort containing winners. So the honest case is narrower: the current rule is
  worth +0.09/trade where the money actually is, and any profit trigger is worth +0.36 to +0.47 there.
  It is a real option, not a recommendation.
- **Dollar frame, which is the strongest argument for waiting and was missing:** live 1R ≈ $18.5; the
  whole 12-trade cohort lost ≈$224; the best candidate's edge is ≈$17/trade. **Waiting 8 more trades
  forgoes roughly $50–150.** That is what "waiting is cheap" means numerically.
- The larger question worth his time: **why do live trades die in 1.5 days** (3.5) — entry quality,
  entry mechanics, or regime. This is #503's original question and it is upstream of all exit work.
  **START WITH THE SHADOW CONTROL (§3.5)** — it already shows 0 winners across bull AND correcting
  months with no broker involved, which points at the setup specification rather than at execution or
  tape. Working that data costs nothing and it reframes the session before any of the confounded
  paper comparison is touched.

**System (automatic, no one needs to remember)**
- Recorder captures every closed live trade with correct normalised fields.
- `exit_tune_cohort_review` fires at 20 closed live trades and re-runs all 34 candidates.
- Each run re-reads T2/T3/T4 and reports which have become readable.

**Me, at the next trigger**
- Re-run the comparison, report the ranking with per-regime cells and their sample sizes.
- State explicitly which of 3.1–3.5 have become answerable and which have not.
- Do **not** re-open the unit question (3.2) before T3 provides runner evidence.

---

## 8. Process note — why this took as long as it did

The operator's ask was simple: test several profit-taking options, keep testing as samples grow. Two
mistakes stretched it. First, I substituted a narrower question — *which unit should the trigger use*
— and then reported that my question was unanswerable, which read as "do nothing" against an ask that
was never about units. Second, I presented several conclusions before they were verified, and three
were later retracted (a backwards data exhibit, a false claim that no paper trade ran far, and an
over-read cohort comparison). All three traced to one real bug in the recorder, now fixed.

What the adversarial reviews were worth: they confirmed the arithmetic twice, found the recorder
defect that had corrupted every winner in the dataset, and caught three over-readings before any of
them reached a trading rule. Nothing incorrect reached the exit path.
