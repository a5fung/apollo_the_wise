# What the EP judge actually decides — and the wrong claim we carried for months

**Date:** 2026-08-27 (PT) · **Trigger:** operator, on the OKTA alert — *"how is it possible that
the judge thinks it's not game changer yet it keeps high"* · **Status:** corrections shipped;
one prompt fix filed for operator sign-off.

---

## The one-line answer

**The judge has the final say on the alert tier, and it weighs the catalyst to get there. The
only thing it never does is relabel the stored catalyst grade.**

Everything else in this document is evidence for that sentence, or an account of the wrong
sentences we were carrying instead.

---

## What we were saying that was wrong

Five surfaces claimed, in different words, that the judge's view of the catalyst was advisory —
that it "drives nothing", is "advisory by construction", or that the judge "sets the tier, not
the catalyst grade".

| Where | The wrong claim |
|---|---|
| `ep_grade_judge.py` module docstring | "writes only the advisory `judge_tier`/direction/rationale columns and **drives nothing**" |
| `briefing.py` alert renderer | printed the judge's catalyst read under **"Recorded, did NOT act"**, labelled *"advisory only"* |
| `briefing.format_grade_provenance` | "← sets the tier, not the catalyst grade" |
| `docs/decisions/0011-...md` | "so it is advisory by construction" |
| `docs/setups/magna53_ep.md` | "the judge writes only advisory columns" |

**The reasoning error, in all five:** they inferred *does not act* from *is not recorded*.
`update_ep_alert_judge_result` did not write the judge's `grade`, so we concluded its view of
the catalyst had no effect. But the judge's view of the catalyst is the primary input to the
tier it sets — and the tier is load-bearing. Not being written to a column is not the same as
not mattering.

A sixth claim was an invented explanation rather than a stale one: `format_tier_transition`'s
docstring asserted that when the judge reports `promote`/`demote` while holding the tier, that
report "is a read on the CATALYST GRADE". The prompt does not say that (see the fork below).
That was the display layer reverse-engineering the model's intent.

---

## What the judge does — measured, 60 days to 2026-08-27

Read-only against prod (`mi_ep_alerts`, `alert_date >= CURRENT_DATE - 60`).

**It is load-bearing on essentially every alert.**

| `grade_engine_authority` | alerts |
|---|---|
| `judge` | 145 |
| `fallback` (judge returned nothing → our score kept) | 2 |

**It changed the tier on 43 of 147** — i.e. it is not reproducing our arithmetic.

| our score said | judge set | alerts | effect |
|---|---|---|---|
| MODERATE | HIGH | 24 | promoted into the ORB entry path |
| HIGH | MODERATE | 12 | dropped out of entry |
| MODERATE | none | 5 | alert suppressed |
| HIGH | none | 2 | alert suppressed |
| (agreed) | | 104 | no change |

**Three cases that show it is judgment, not accounting:**

- **SCSC 2026-08-20** — our score: **96**, HIGH. The judge read the 8-K, found it was a single
  director's retirement at a $1.0B distributor, and set **none**. Ninety-six points of
  arithmetic overruled by reading the filing.
- **OMER 2026-08-13** — our score: 60, MODERATE, catalyst labelled **`routine`**. The judge read
  launch revenue accelerating 190% quarter-over-quarter and a flip from loss to profit, and set
  **HIGH**. *This is the decisive case: the judge acted on its own view of the catalyst while
  the stored label stayed `routine`.*
- **CRWV 2026-08-12** — same shape: 51.6, `routine` label, judge set HIGH on +112% Y/Y revenue.

**What our score cannot do that the judge did on these names:** open a filing and check the
event is real and dated today; tell a revenue beat from an EPS beat; credit a narrative the
ticker is adjacent to but not a cohort member of; size a catalyst against the company's market
cap.

---

## What the judge does not do

It does not write `catalyst_quality`. That label is set by the Claude grader
(`_classify_catalyst_claude`) and is what the alert prints as the catalyst grade. The judge's
own read was, until today, computed and then dropped — visible only in the `ep_grade_decision`
audit payload.

So the honest split is:

- **Alert tier** — judge decides. Final.
- **Catalyst grade label** — Claude grader owns it. The judge cannot change it.
- **The judge's read of the catalyst** — an input to the tier, therefore acting; now recorded
  as `judge_grade`.

---

## OKTA 2026-08-27, explained

Row: `score_tier=HIGH · baseline_floor_tier=HIGH · judge_tier=HIGH · authority=judge ·
catalyst_quality=game_changer · judge_direction=demote · ep_score=90`.

The judge's own rationale:

> Fresh, primary-sourced catalyst: the 8-K filed 8/26 (Item 2.02) confirms the Q2 FY2027 release
> overnight… revenue beat ($805M vs ~$794M) plus a full-year revenue guidance RAISE… **Demoted
> from game_changer because a ~1–2% revenue beat and modest guide raise on a $23B mega-cap SaaS
> name is material but not transformative — this is a high-quality beat-and-raise, not a
> structural re-rating event.**

So: it read the catalyst as **strong, not game-changing**, weighed that, and still set **HIGH** —
because its own rubric requires a *real, material* catalyst for HIGH, not a transformative one. A
beat-and-raise confirmed by a same-day 8-K clears that; "game changer" is the top of a different
scale.

**Why the alert read as a contradiction.** The stored label still said `game_changer` (the judge
cannot change it), the judge's prose said it had demoted it, and its `direction` field said
`demote` while the tier held at HIGH. Three surfaces, three different-looking answers, none of
them wrong on its own.

---

## Shipped today

1. **`judge_grade` column** on `mi_ep_alerts` — the judge's catalyst read is now persisted, and
   backfilled from the `ep_grade_decision` audit payloads so historical alerts render too.
2. **The alert states all three things the operator asked for**, from recorded values only:
   the judge's catalyst read, the decision it drove, and the reason (its own rationale, printed
   below and attributed). Example: *"The judge read the catalyst as strong, not game changer — it
   weighed that and set alert tier HIGH. The stored grade label is unchanged."*
3. **The judge's catalyst read moved out of the "Recorded, did NOT act" block.** It acts.
4. **All five stale claims corrected** at source, each with a dated note saying what was wrong.
5. **`format_tier_transition`'s invented explanation removed** and replaced with what the prompt
   actually specifies.

---

## Open fork — operator decision, not taken

**The judge's `direction` field is specified one way and used another.** `_RUBRIC`'s closing
line says *"direction_vs_floor compares your tier to the floor tier given"* — tier vs tier. But
rubric **rule 2** teaches PROMOTES / DEMOTES as verbs about the **grade** ("a catalyst that is
immaterial for a large company DEMOTES it"). The model is taught the verb on one axis and then
asked for it on another, so it sometimes answers on the grade axis — which is exactly what OKTA
did (`demote` + tier held at HIGH).

**The fix** is to split the field: ask separately for a grade direction and a tier direction, or
drop `direction` and derive the tier movement (we already derive it for display). Either is a
change to `_RUBRIC`, which bumps `RUBRIC_VERSION` / `RUBRIC_HASH` on a load-bearing judge — so it
needs operator sign-off under CHANGE_PROCESS. **Filed, not taken.**

The prompt also still uses the word "floor" for the tier. Same constraint — it is one character
of `_RUBRIC` away from a hash bump, so it rides the same sign-off rather than being fixed
quietly.

---

## What this does not answer

- Whether the judge's tier calls are **right** — this measures that it decides, not that it
  decides well. The 43 overrides have not been scored against outcomes.
- Whether `catalyst_quality` should stay grader-owned at all, given the judge routinely
  disagrees with it. That is a design question, not a correction.
