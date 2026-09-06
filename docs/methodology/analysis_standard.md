# How we run an analysis

**Written 2026-08-29** at the operator's direction, after a single session in which I produced a
geometry analysis, corrected it three times as he found successive defects, and finally retracted
it. His words:

> *"you run a lot of analysis, i can't keep pointing out your errors, you need to do these
> reviews and analysis with structure, with known caveats, with understanding of the goals, what
> we're trying to find, what we're missing etc."*

and, on the third correction:

> *"either don't do it or do it right, stop half assing here."*

This is the standard. `scripts/check_analysis_doc.py` enforces the parts of it that are
mechanically decidable; the rest is judgement, and the failure catalogue at the bottom is there
because judgement drifts and a named list of past mistakes drifts less.

---

## 🎯 THE STATISTIC: MEASURE THE TAIL. The median is an execution problem, not a selection one.

**Operator, 2026-09-05 — HARD, and it governs every EP analysis:**

> *"big tail is the key ingredient, median can be somewhat managed with entry and exit."*

**Why this is first, not a footnote:** on 2026-09-05 I ranked cohorts by median return and
"percent still up" and reached THREE conclusions in one evening — that the catalyst rubric was
inverted, that its axes were humped, that 10-15% revenue growth was a sweet spot — and **all three
dissolved the moment the same data was cut on big winners.** Every band that looked different on
the median was identical at p90. His question, *"where does our real EP fall"*, exposed it in one
line: the labelled real EPs sat in the bands the median called worst.

**The rule:**

- **Report the TAIL first** — count of ≥20% / ≥40% moves, hit rate, p90 — and only then the median.
- **A median difference with no tail difference is NOT a selection finding.** Say so explicitly.
- **Never rank bands, cohorts or rules by median or by "percent still up" alone.** For a book whose
  return comes from a handful of large winners, central tendency is close to irrelevant.
- **High variance is not a defect — it is where the tail lives.** The band with the WORST median can
  be the most attractive one (2026-09-05: 10%+ revenue beats had the worst median at −4.5% and the
  best tail at 11% big winners / p90 20.4 — and HTFL, an operator-labelled real EP, sits in it).
- **Then check ground truth**: where do the operator-labelled EPs fall?
  `docs/methodology/operator_labelled_eps.md`. If a conclusion puts them in a losing bucket, the
  ⚠ **This check is DECISIVE only while the list is small (n≤10): with six names you can read
  every one. Above ~10 it becomes its own study and inherits every trap above it — including
  the median trap. Do not let "where do the labelled EPs fall" quietly become a cohort
  average.**
  conclusion is wrong, not the EPs.

⚠ **The corollary he stated: a poor median is an ENTRY/EXIT problem (#545), not a reason to reject
a selection rule.** Do not use median underperformance to argue against admitting a cohort.

---

## 0. 🔴 EVERY ANALYSIS CARD GETS `ANALYSIS_CARD_PREAMBLE.md` VERBATIM

`docs/methodology/ANALYSIS_CARD_PREAMBLE.md` carries THE GOAL, the ranking order (recall →
expected return → capture → tail; **never win rate**), the asymmetric failure modes, and the
rules that keep getting re-learned.

**Paste it into the card. Do not summarise it, do not rely on remembering it.** Operator,
2026-08-30: *"can you just internalize the goal and purpose and not needing me to correct you
every time you do an analysis, this is wasting so much time."* A standard re-remembered per card
is a standard that drifts — the same four corrections recurred across three cards in two days.

## 1. Before running anything — answer these four in writing

Not in your head. In the document, before the first query.

1. **What decision does this serve?** If no decision hangs on the answer, do not run it. "Good to
   know" is how a day disappears.
2. **What would change the decision?** Name the number and the direction — *"if the blocked
   cohort's expectancy is positive, the gate is costing us"*. An analysis that cannot fail to
   support its conclusion is not evidence.
3. **What population answers it?** See §2 — this is where most failures live.
4. **What would make this analysis wrong?** Write it down first. It is much harder to see once
   you have a table you like.

## 2. The population is the analysis

**Most of my errors have been population errors, not arithmetic errors.** The arithmetic is
usually right; it is right about the wrong set of rows.

- **Era.** The system changes weekly. In August 2026 alone: the gap floor 10→9, the 2R stop, the
  catalyst lattice, separation scoring, the shortlist, real-time admission, real-time volume and
  gap authority, rubric v4. **A window spanning a rule change measures a system that never
  existed.** Say which era every cut covers, and split when a rule moved inside it.
- **Admission is part of the era.** This is the one I missed and had to retract. It is not enough
  for the *outcomes* to be current — every historical trade was **admitted by whatever filter ran
  that day**. Varying anything downstream across such a set measures your variable *given a mixed
  admission population*, which answers nothing. If the question is about the current system, the
  population must be re-derived under current admission.
- **Prefer a raw-bar replay to stored rows.** `mi_intraday_bars` and `mi_daily_closes` are facts.
  `mi_live_trades` is the *output of the rules that were live that day*. Replay under today's
  rules; use stored rows only to check the replay's calibration.
- **Dead strategies are not evidence.** Check `mi_strategies.enabled/phase` before citing any
  `signal_type`. `9m_day2`, `fishhook_v3` and `flag_continuation` are deprecated.
- **Live and paper never pool.** Different sizing, different safeguards, different psychology of
  the fill. Split them or say which one you used.
- **Is the source table itself sound?** `mi_ep_missed_outcomes` credited pre-market fades as
  missed winners for months — 60% of its ranked "winners" were never setups. A table is not a
  fact just because it is populated.

## 3. The control must be what is actually live

I compared five stop variants against the ORB low and labelled it "live". The live stop had been
`entry − 2R` at half size for two weeks. Every conclusion in that table was against a retired
baseline.

**Read the constant out of the code or the DB, on the day you run it.** Never from memory,
never from an older document, never from a change-log entry that may itself have been superseded.
`scripts/live_rules.py --drift-only` exists for this.

## 3b. 🔴 RUN `scripts/live_rules.py` FIRST, AND HAND IT TO EVERY CARD

Operator, 2026-08-29: *"this is crazy that you don't know what we're trade today, don't know what
EP we rank etc and you go do all these analysis with completely wrong context, wtf is happening."*

He is right, and the tool already existed. `scripts/live_rules.py` prints what is ACTUALLY live —
generated from code and prod state, never from prose. It reads the acting gap floor, the
shortlist ranking and its toggle, the extension cap, the alert bar, every real-time authority
toggle, the exact stop and partial-profit paths, and which of two competing code paths actually
acts. `--drift-only` shows where the docs contradict it.

**What went wrong without it, in one session:** I attributed 22 of 55 missed EPs to a
top-20-by-gap shortlist cap. That ranking was replaced by a three-term pre-score on 2026-08-22
and the toggle is on. The finding described a rule that no longer exists. The same session's
run also found `magna53_ep.md` still quoting a 75% extension cap when the acting value is 50%.

**The rule, therefore:**
1. **Run `scripts/live_rules.py --drift-only` at session open.** It is in the CLAUDE.md OPEN
   ritual for this reason. Offline-safe, read-only, seconds.
2. **Before ANY analysis, capture the full output to a file and HAND THAT PATH TO EVERY CARD.**
   A card cannot know what changed since its training or since the doc was written; a subagent
   reading `docs/` is reading prose that may be stale, and stale prose is what produced both
   failures above.
3. **Any drift it reports is fixed BEFORE the analysis runs**, not after. An analysis built on a
   doc the tool has already flagged is invalid on arrival.

⚠ **This is not the same as §3 (read the constant from the code).** §3 is about not trusting your
memory of one value. This is about not trusting your picture of the whole live system — which
gates act, which toggles are on, which of two code paths is the one that runs.

## 4. Measure the right thing

- **Expectancy, not win rate.** The operator: *"it's not just ratio of winners to losers... more
  important is the expected return, how much we lose with the loser and how much we win with
  winners and is that outcome positive."* A 20% win rate can be excellent.
- **Know what your outcome column IS.** `fwd_5d_pct` and `max_high_5d` are **maximum favourable
  excursion** — positive on nearly every row by construction. A win rate computed on MFE is
  meaningless. `ret_5d` is a 5-day return **with no stop in it**: a −57% row would have been −1R
  in reality, not −57%.
- **R, not percent, whenever a stop exists** — and R must be *each variant's own* R, or the widest
  stop wins by construction.
- **Median beside mean, always.** This data is dominated by a handful of huge movers.
- **Only count what could actually have been traded.** His rule: *"those stocks that we turned
  away has to be theoretically traded before we count them."* Gapped at the open, cleared the
  liquidity floor, entry reachable. On the sustain rule this took 39 "breaches" down to 2.

## 5. Sample size

- **n on every number.** No exceptions.
- **Under ~10: state it and draw no conclusion.** "Too few to judge" is a successful outcome, not
  a failed one.
- **A ratio needs a denominator you can defend.** 2 of 65 is 3%; 2 events is nothing. Say both.
- **Beware the single big mover.** If one name carries the result, name it and show the result
  without it.

## 6. Every output document carries these sections

Enforced by `scripts/check_analysis_doc.py`:

- **the decision it serves** — and the operator's own words where he framed it
- **method** — population, era, and how the population was derived
- **the numbers** — tables, n on every figure
- **what this does not answer** — explicit, and never empty
- **⚖ THE LINE** where the subject is strategy, entry/exit discipline, sizing, targets or
  safeguards: state that the change is his call and that nothing was flipped.

## 7. Reporting

- **Verify before reporting, not after.** Run the adversarial check first; report once.
- **The report is the finding, not the work.** He does not need the mechanism.
- **Corrections are one line.** Not a retrospective.
- **28-word cap on the message** (`scripts/report_format_gate.py`). Tables, code and quotes are
  exempt — put the numbers there.

## 8. When an analysis is wrong

**Retract it; do not patch it a fourth time.** If the defect is in the population, no re-run
fixes it — a fresh table off the same bad set just launders the error. Put a DO-NOT-CITE banner
at the top, keep the document as the record of how it failed, and file what a correct version
would require.

---

## The failure catalogue

Every one of these actually happened. They are listed so the next pass recognises the shape.

| failure | where |
|---|---|
| Population admitted by mixed-era filters | #482 geometry, retracted 2026-08-29 |
| Control was a retired baseline called "live" | #482, same day |
| Era-mixed outcomes averaged into one number | #482, same day |
| Live and paper trades pooled | #482, same day |
| Dead strategy cited as current evidence | 9m_day2, 2026-08-29 |
| Source table itself corrupt | `mi_ep_missed_outcomes`, #595 |
| MFE treated as a return; win rate computed on it | #233 boost read |
| Win rate reported where expectancy was the question | extension band |
| Counted names that were never tradeable | sustain rule, #593 |
| Conclusion drawn from n=2 | extension band, first pass |
| Evidence marshalled for a position not actually held | the delayed-data argument |
| A search truncated with `head` and read as complete | the third Perplexity call site |
| Simulator artifact reported as an observed result | the "+2R winners" |
