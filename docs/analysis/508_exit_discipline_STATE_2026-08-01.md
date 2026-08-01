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

**2.5 The live cohort's losses are not an exit problem.**
10 of 12 stopped out at a full −1R; **4 never went green at all.** No exit rule can act on a trade
that never shows a profit. Exit rules can only improve the 4 trades that ran.

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
23 paper trades, Correcting is 7 of 7 live, only Choppy has both sides (4 live / 2 paper). Today's
grid cannot separate "bull markets run further" from "paper behaves differently from live."

**3.5 Why live trades die in 1.5 days.** Not explained by stop width (tight-stopped live trades hold
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
| **T2** | **Live trades in a BULL tape** | 1 of 12 so far | Makes the regime grid readable — separates "bull runs further" from "paper ≠ live" |
| **T3** | **Live trades that RAN** (peak ≥ 1.5 daily ranges) | 2 (SMCI 1.68, NVCR 2.35) | Prices what a partial gives up vs a full exit — resolves 3.3 |
| **T4** | **Any live trade holding ≥3 days** | 1 of 12 ever | Would make the *current* rule non-inert and testable as-deployed |

**T1 is automatic** — no one has to remember it. T2/T3/T4 are read and reported at each T1 run.

---

## 6. WHAT WE ARE MISSING — stated plainly

1. **Live winners.** Zero. Everything measured so far is loss-cutting.
2. **Live trades in a bull market.** One. This is the specific gap blocking the regime question — not
   sample size in general.
3. **Live trades that survive.** One has reached day 3, ever.
4. **An explanation for the 1.5-day death.** Not stop width, not regime. Unknown.

Note what is *not* missing: instrumentation. The recorder, the engine, the regime grid and the
recurring trigger are all built and verified. **We are waiting on trades, not on tools.**

---

## 7. NEXT STEPS — who does what

**Operator**
- **Decision pending: none required now.** The rule change is deliberately parked (see 3.1–3.4).
- **One judgement call available if he wants to act early:** ship a profit trigger now on the
  strength of 2.3 (every alternative beats the inert day-3 rule), accepting that the *level* is not
  yet tuned. This is a real option, not a recommendation — it trades an unmeasured level for escaping
  a rule that has fired once in twelve trades.
- The larger question worth his time: **why do live trades die in 1.5 days** (3.5) — entry quality,
  entry mechanics, or regime. This is #503's original question and it is upstream of all exit work.

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
