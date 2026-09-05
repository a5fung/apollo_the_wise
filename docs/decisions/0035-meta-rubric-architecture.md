# ADR 0035 — Meta-rubric architecture: what it is, where it sits, and the REAL dependency graph (#504)

**Date:** 2026-09-05 · **Status:** DRAFT — §7's forks are the operator's; §1–§6 are findings and
stand regardless · **Decider:** operator · **Task:** #504 (meta-rubric roadmap)

## 0. Why this exists — his words, and the failure it prevents

> *"the meta-rubric is a critical long-term component of Apollo... I don't want this work to be
> blocked for no reason going forward."* (operator, 2026-07-26)

The failure already happened: #329 (the composition parent) sat `blocked` on #335 (the load-bearing
flip) **for a decision #329's own text had exempted** — *"the ADVISORY/SHADOW composite is UN-GATED
(touches no live grade) → build it NOW"*. The foundation was gated on the roof, and nobody noticed
for weeks. #301 (ensemble-divergence shadow) carried the same `blocked_by:#335` for seven weeks;
#331 carried `blocked:#329/#330` for a month after both had closed. The pattern is one thing:
**zero-authority work chained to a load-bearing decision.** §5 encodes the rule that ends it and
re-checks every line in the cluster against it.

Written after #329's STEP-0 shadow landed (07-26) and after #533 closed (09-05), so it plans from
what exists.

## 1. WHAT the meta-rubric is — in plain words

**One decision from several reads.** A stock gaps on a catalyst and clears the gap floor. Then:

1. **The judge says how real the catalyst is** (ADR 0011, live since 06-10): fresh, primary-sourced,
   material for a company that size. Its verdict is the tier — HIGH / MODERATE / none.
2. **The context axes say whether the context makes it a better bet**, each a small signed table
   that returns **+1 step or 0, never negative**:
   - **Theme** (ADR 0015, #328) — in an Accelerating theme, +1; Mainstream, tie-break; Fading or no
     theme, 0. *Never* penalise a name for having no theme (the 06-05 backtest: themeless names were
     88% of HIGHs and held the +137% winner).
   - **Structure** (ADR 0016, #330) — Stage-2 trend *and* a tight base coming in, +1; else 0.
   - **Gap-vs-structure alignment** (ADR 0033, #331) — gap cleared the whole overhead supply, +1;
     landed back in its own congestion, 0. Not yet validated (§5).
   - **Setup-class** (ADR 0028, #332) — a TAG (Pradeep-explosive / mature-leader / episodic-neglect),
     not a credit; it may later change which axes carry weight for that class.
3. **The composition adds the credits to the judge's verdict, capped at one tier-step net**
   (ADR 0024 F1/F2, operator-signed 07-07), and names every contribution in `/why`:
   *"judge strong (catalyst) + theme Accelerating (+1) → HIGH"*. No invisible maths.

**The trader's sentence:** *the judge grades the reason; the axes grade the company it happened to;
the tier is the judge's grade moved at most one step by the context, and the trace shows which
read moved it.*

What it is NOT: not a gate (it only adds); not a second grading authority (Path A, 06-18: enrich
the ONE judge); not detection (it runs **after** the gap floor at `ep_detector.py:3189`, so the
2026-09-05 ruling *"if there's just vol, but no gap that is no EP"* holds by construction — nothing
here can admit a name that did not gap); not a setup (P11 — it has no buy point or stop; it ranks
and grades names for a setup that does, MAGNA53).

⚠ **9M, stated so it is not re-litigated:** the setup-class table uses `is_9m_same_day` as one
predicate of `pradeep_explosive`. That is the **9M volume CONDITION**, which the operator ruled on
2026-09-05 *"is still potential as a stock condition"* — a legitimate rubric input. The **9M Day-2
trading SETUP is retired** (code deleted 08-02, #515) and nothing in this ADR proposes or seeds
from it.

## 2. WHERE it sits, and what consumes it

```
universe (~9,700)
  → gap floor 9% + filters            (detection — NOT the rubric's domain)
  → ep_score / conviction floor        (the number he reads on his phone)
  → JUDGE verdict → tier               (live, load-bearing, L3)
  → [COMPOSITION: axes' credits → final tier]   ← the meta-rubric. DARK.
  → alert (HIGH = ORB-eligible)
  → entry path: 5 slots, ordered by RS rank since 09-03 (#533)   ← the rubric's 2nd consumer
  → bracket → exit stack               (where the R is currently lost — §6)
```

Three consumers, in the order they can pay:

| consumer | what the rubric would change | authority class |
|---|---|---|
| **Slot ORDER** on a multi-alert morning | which of N alerts get the 5 slots | entry-path selection — CHANGE_PROCESS (S-1 territory) |
| **Alert TIER** (the grade boost) | a themed MODERATE becomes HIGH | detection criterion — CHANGE_PROCESS + the 0024 rubric amendment |
| **Sizing / slot count** by theme heat | more capital or more slots to a hot area | sizing + safeguard — THE LINE, backtest, sign-off |

### As built at HEAD (2026-09-05)

| component | file / table | state | authority |
|---|---|---|---|
| Holistic judge | `ep_grade_judge.py` | live; `has_direct_source` + `revenue_stage` finally wired 09-01 (bug fix, effect review at 40 grades ≈ 10-15) | L3 live |
| Composition | `meta_rubric_compose.py::compose_final_tier`, net cap ±1 | built 07-08; wired into `_judge_shadow` behind the `composite_authority_enabled` DB toggle (theme credit only) | **dark — OFF, last recorded 08-09** |
| Theme axis | `theme_axis_shadow.py` → `mi_theme_axis_shadow` | writing since 03-24 (backfilled); 588 rows at 08-30, +3.7/day; co-movement + 7d-bounded read added 08-29 | L0 shadow |
| Structure axis | `structure_axis_shadow.py` → `mi_structure_axis_shadow` | writing; 122 rows at 08-28 | L0 shadow |
| Gap-alignment | none — STEP-0 probe only (`_331_gap_alignment_step0.py`, 07-21) | table not validated; no shadow by ADR 0033's own order | not built |
| Setup-class tag | `setup_class_classifier.py` → `mi_ep_alerts.setup_class` | P0 visibility since 07-18; never rendered to the judge | L0 tag |
| Chart-vision axis | `chart_axis.py` | paused 08-02 (#519): ~85% of judge spend, zero trade influence | offline eval |
| Tape axis | `scripts/eval_tape_judge.py` rig | built 06-17; full run needs $50–170 | funding |
| Ensemble divergence | `mi_judge_divergence` (#301) | live telemetry since 08-08 | L0 |
| Label cohort | `mi_theme_relevance_cohort` (190 rows) | 90 labelled 08-04: all 59 themed rows done, 31 of 131 themeless-winner | operator input |
| Entry ranking | `live_tracker.py` RS order; `mi_ep_slot_rank_shadow` records 6 candidate orders (rs / ep_score / briefing composite / ADV$ / alphabetical control / vol-pct) | acting since 09-03 | live (order only) |

The **briefing composite** (`briefing._ep_composite_key` = ep_score + theme bonus 15/10/5 + RS
bonus) is the only theme-aware ranking that exists, and it sorts the briefing for reading. The
calibrated axes' credits are **not** among the six candidate orders the slot-rank shadow records.

## 3. THE PATH, stage by stage — what each stage is, and what it unlocks

| stage | what | owner | state (09-05) |
|---|---|---|---|
| **0. Shadow attribution** — every HIGH/MODERATE alert gets its theme/structure reads recorded beside the live grade | #329 / #330 | ME | ✅ live, accruing (588 / 122 rows) |
| **1. The labelled cohort** — themed rows + themeless WINNERS, so the theme read can be checked both ways | #367 → #368 | HIM (labels) | 90 of 190; themed side complete: **theme credit right 84.5%** (49/58 decidable); 5 of the 9 errors are ONE misclassification (crypto miners → AI-infra, #529) |
| **2. The weighting decision** — magnitude and stage→credit (D2/D3): v1 table is SIGNED (0015, 07-04); two questions open (§7 F-C). ⚠ The #504 PLAN line put Path B's weight FIT (`phase5_meta_rubric_calibration`, a logistic regression) here; ADR 0024 superseded Path B on 07-07 and its events have no writer (§5) — the stage is his decision on a signed table, not a fit | #368 | HIM | open |
| **3. Evidence for the flip** — do would-be MODERATE→HIGH upgrades beat their MODERATE grade? | `theme_axis_boost_reeval` | CALENDAR | 0 of 10 themed-MODERATE settled (07-25); **slow, not frozen** — see §5 #335 |
| **4. The flip** — `composite_authority` ON + the 0024 clause-4 rubric amendment, atomically | #335 | HIM (CHANGE_PROCESS + sign-off) | pending; sequenced behind #545 (§6) |
| **5. Later axes** — structure (M2), gap #331, setup-class P1–P3, chart #519, tape #299 | each its own ADR | mixed | each at its own evidence gate |
| **6. Portfolio uses** — order, allocation, slots (§4) | — | HIM | order is measurable now; the other two need Stage 2 + a signed money rule |

Stage 0 needed nothing but a build. Stage 1 needs only him. Stage 2 needs Stage 1's themed side
(done). Stage 3 needs data. Stage 4 needs 2 + 3 + a sitting. **Nothing in Stages 0–3 needs Stage 4.**

## 4. THE PORTFOLIO USES — first-class goals, and what each actually needs

These are the reason to get the rubric right *independent of* whether today's marginal
MODERATE→HIGH boost clears any bar (operator, 2026-07-26).

| use | needs | does NOT need | measurable | pays with a leaky exit? |
|---|---|---|---|---|
| **Arbitrate competing EPs for limited slots** | a within-day order that beats RS order on multi-alert mornings; the slot-rank shadow already records six candidates at $0 | the tier flip (#335) — an ORDER is not a TIER; the phase-5 weight fit | **now** — add the composed credits as a seventh candidate order (§7 F-E) | **yes** — P4: MRNA vs MRVL, both HIGH, book at 5/5, only the order separated a winner from a loser. The tail name must win a slot before any exit can convert it |
| **Boost capital allocation toward hot areas** | a theme-strength read he trusts (Stage 1–2; #486 cross-val; coverage 319 of ~9,700 tickers, 70% of HIGH alerts outside any theme) + a signed sizing rule | the tier flip | after Stage 2 | no — sizing multiplies whatever the exit keeps |
| **Expand slots for a strong theme** | the same read + a safeguard change (`MAX_CONCURRENT_LIVE_POSITIONS` 5) — precedent for own-slot mechanics is the low-cap lane (#624) | the tier flip | last | no |

**Note on the theme read itself (Stage 1–2 evidence, both directions):** our engine is 3× more
restrictive than the judge (flags a theme on 7.0% of alerts vs 20.2%; agreement 82%), and by
forward excursion the judge's read is the better one (judge-only 12.2% vs engine-only 7.6%, n=8);
19 of 59 misses were themes we KNEW and excluded by stage (Fading/Nascent), and both ran above
average (#486, 08-29). The 84.5% label accuracy is on the rows the engine DID flag. Allocation on
the engine's read alone would allocate on the thinner of the two instruments — a Stage-2 input,
not a reason to stop.

## 5. THE ANTI-BLOCK TABLE — the operative deliverable

**Ground rule, encoded:** anything **zero-authority** — a shadow, an advisory column, telemetry, a
label sheet, a read-only analysis; i.e. it cannot change a grade, alert, entry, exit or size — **is
NOT gated by a load-bearing flip decision.** A stated block must name a **concrete, checkable
unblock condition**: a row count with its accrual rate, a named ruling, a named file. A phase name
("post-M1", "after the flip") is not a block.

Every task the #504 DoD names, plus the adjacent lines, re-checked against that rule:

| # (plain name) | status today | genuinely needs | does NOT need | verdict |
|---|---|---|---|---|
| #328 (theme axis credit table) | CLOSED 07-18 | — | — | table signed 07-04; shadow live |
| #329 (composition parent, STEP-0 shadow) | CLOSED 08-08 | — | — | its own block on #335 was fiction; closed on the live shadow |
| #330 (structure axis) | CLOSED 07-20 | — | — | shadow live |
| #332 (setup-class tag) | CLOSED 07-20 | — | — | P0 shipped 07-18; P1–P3 are their own gated flips |
| #367 (label-cohort seed + health read) | CLOSED 07-06 | — | — | signal (a) name-attribution dead; cohort seeded |
| #301 (ensemble-divergence shadow) | CLOSED 08-08 | — | — | carried `blocked_by:#335` 7 weeks; built + live |
| **#331 (gap-alignment axis)** | in_progress, 09-29 | DATA: `gap_alignment_331_accrual` = 700 theme-shadow rows (588 at 08-30, +3.7/day → ≈09-29), then the re-run; the operator's 07-21 ruling was *collect more* | #335, #368, #448 | **block is REAL and data-shaped.** Its `blocked:#329/#330` was fiction for a month (unblocked 08-30). Not re-opened here |
| **#335 (the load-bearing flip)** | pending, 09-15 | (a) Stage 2 signed, (b) evidence: ≥10 themed-MODERATE settled, (c) the sitting: CHANGE_PROCESS + amendment + toggle | #331, #448, #486, #299, the phase-5 weight fit | **gated on DATA that accrues SLOWLY — not frozen.** The 08-22 rescale removed the *ep_score* MODERATE cutline, but the shadow gate reads the FINAL post-override tier (`ep_detector.py` ~6142; `theme_axis_shadow.py:331`) and the judge still emits MODERATE (`ep_grade_judge.py:57`; 21 of 101 grades in the 30 days to 09-01). At ~0.7 MODERATE/day × the engine's 7% themed rate ≈ 0.05/day → **~6 months to 10.** The 09-15 review will fire on a count that cannot have reached 10; that is a FORK (§7 F-A), not a park |
| **#368 (labels + the weighting decision)** | in_progress, 09-11 | HIM: ~100 remaining themeless-winner labels (~1h, resumable sheet) + D2/D3 | #335 (dropped 07-26), #367 (closed), #331 | **block is REAL and his.** The date is a check-back, not a delivery |
| **#448 (B6: does the fundamentals rubric's `composite_min=22` downgrade losers more than winners?)** | pending, 09-15 | DATA: `b6_gate_inversion_recheck` (+8 live-PASS post-07-16) | anything in this cluster | **MIS-FILED, not mis-blocked** — this is `catalyst_rubric.md`'s deterministic gate, not the meta-rubric. ⚠ The re-check must split pre/post 09-01: the `has_direct_source`/`revenue_stage` wiring fix moved the graded population |
| **#486 (judge ↔ theme-engine cross-validation)** | in_progress, 09-06 | accrual of `bounded_matches_unbounded=true` rows (forward-only from 08-29) | #335, #368 | **block is REAL** (rows). Expect the ETA to move to a row count, not a date |
| **#299 (tape axis eval — $50–170)** | **blocked**, 09-09, `blocked_by:#335` | the $0 rigor check he named, then the spend he **already authorized** | **#335** | **🔴 BLOCKED FOR NO REASON.** The last OPERATOR word on this line is 2026-08-03: *"UNCHAIN FROM #335 AND RUN IT... Status → the eval run, no longer 'blocked'."* Then an agent revalidation on 08-16 RE-ASSERTED the 07-04 hold (*"batched at the #335 checkpoint... nothing here is agent-unblockable"*) against that ruling, and the parseable `blocked_by:#335` was never stripped. No gate catches it: `stale_blockers` reads only the LAST `[blocked:]` tag and fires only when the blocker has LEFT the board — #335 is still open. **Status should be `in_progress`: run the $0 rigor check he named, then the spend he authorized; strip both tags** |
| #519 (chart-vision, offline) | in_progress | HIM: scorer choice + a cost number | #335 | real, his |
| #529 (crypto↔AI-infra theme merge family) | blocked_by:#471 | #471 (on the board) | — | real; adjacent — it is the fix for 5 of #368's 9 theme errors |
| #533 (within-day ranking) | CLOSED 09-05 | — | — | RS order acted 09-03; the slot-rank shadow is the instrument the ranking use now runs on |
| #623 (vol-percentile as 6th candidate order) | in_progress | the next ORB session's rows | — | real (verify) |
| #545 (entry/exit tactics programme) | pending | — | — | **the rock the grade-affecting stages sequence behind** (§6) |

**Blocked for no reason, today: one line — #299.** The other fictional blocks in this cluster were
already removed before this ADR (#368's #335/#367 blocks 07-26; #329 and #301 closed 08-08; #331
unblocked 08-30) and are recorded above so the DoD's *"re-checked"* is visible, not asserted.

**Gates that can never open (registry hygiene, §7 F-D):** `phase5_meta_rubric_calibration`
(threshold 30, earliest 09-08) counts `catalyst_rubric_scored` ⋈ `theme_context_scored` audit
events, and `phase6_meta_rubric_gating` counts `meta_rubric_score_advisory` — **none of the three
events has a writer anywhere in `agents/` or `scripts/`.** They are Path-B (logistic weight fit)
artefacts from May; ADR 0024's M1/M2 machinery superseded them on 07-07. A review that surfaces
"not ready" forever is the calendar cousin of a fictional block.

**Why the mechanism missed #299, and what would catch the class:** a `blocked_by:#N` whose line
also carries an operator ruling that unchains it is not decidable from text. The process rule is
the fix — *when he unchains a task, the tag comes off in the same commit* — and the CLOSE
reconcile is where it is checked.

## 6. Where this sits against P10 and this week's conversion finding

**P10 does not defer the rubric** — it is work on the existing setup (MAGNA53), not a new one.
What sequences it is the arithmetic:

- **The whole book is breakeven:** 1,577 replayed trades sum **−0.42R** once 13 two-cent-stop
  rows are removed (#621's line, 09-04). The **modal trade is +0.33R** — take the partial, get
  stopped at breakeven — 82 of ~106 partial-takers finish at exactly that number
  (`docs/analysis/runner_rule_sweep_2026-08-29.md`). Live: 26 closed, **−7.8R, zero at ≥4R**
  (`545p2`, 09-02). The tail is already in what we admit (13.8% of HIGHs reach +20% in 20
  sessions); the bracket realises none of it.
- **So the binding constraint is CONVERSION, not selection.** A better selector feeding this exit
  raises the *count of +0.33R scratches*, not R. **A roadmap that improves selection while the
  exit leaks is optimising the wrong end — and this graph shows that for Stages 4–6.** Every
  grade-affecting flip sequences behind #545 (his 09-04 ruling: *the exit change is the next big
  rock*).
- **What is NOT deferred:** Stages 0–3 cost nothing and accrue on their own (shadows, labels,
  cross-validation); and the **slot-ORDER use pays even with a leaky exit** (P4 — the tail name has
  to win a slot before any exit can convert it), and is measurable today on the slot-rank shadow.
- **P9's caveat holds both ways:** downstream selectivity is what unlocks loose upstream admission,
  so this is not a nicety — but it is *measured*, not flipped, until the exit converts. And the
  score it would compose on is measured anti-selective end to end (composite AUC 0.37–0.41 against
  the 26 labelled real EPs; dollar volume, AUC ~0.65, absent from the stack — #533, 08-22). The
  axes add context to a base whose own ordering is under repair; that is a reason to measure the
  composed ORDER against RS now, not a reason to wait.

## 7. Decisions that are HIS — each a fork with its cost (nothing picked)

**F-A — #335's evidence population.** The gate needs 10 themed-MODERATE settled; ≈6 months at
current rates, and the 07-26 rate estimate was itself retracted for a circular themeless check.
(a) *Wait it out* — cost: the flip and both money uses stay behind a clock nothing else on the
board is waiting for. (b) *Re-target the composite's FIRST authority at slot ORDER* — first step is F-E (record the
composed order as a candidate on the slot-rank shadow), measure it against RS order, and only
then CHANGE_PROCESS; cost: the grade-boost use is shelved, not killed; order authority is an
entry-path change, but its population is every multi-alert morning and the instrument exists. (c) *Rule don't flip* —
#335 closes as decided; the theme axis stays telemetry; the portfolio uses route through (b) later.
*Rec: (b), because it is the one branch the conversion finding does not argue against.*

**F-B — #368's remaining ~100 labels.** (a) Finish them (~1h): the false-negative RATE becomes a
number. (b) Rule the themed side (done, 84.5%) sufficient for v1 and keep the themeless side as a
sample: cost — we hold a *list* of missed themes, not a *proportion*, and the 22 named misses all
fall in one ten-day window. *Rec: (b) for v1; (a) before any allocation use.*

**F-C — the two open magnitudes in the signed table (D2/D3, THE LINE).** (i) *Mainstream*: 0015's
STEP-0 read +14.0% / 67% win, more than tie-break credit implies — upgrade to a near-miss band like
Nascent, or hold v1? (ii) *Fading-dip credit* (CRWD 08-27): of 12 Fading-at-alert misses only 3
were back to Accelerating/Mainstream within 5 days — credit a recently-Mainstream Fading theme at
that 1-in-4, or not? Cost of each: a table change is grade-affecting → CHANGE_PROCESS, and lands in
the same amendment as the flip. *Rec: decide at the F-A sitting, not before.*

**F-D — retire the two Path-B registry reviews** (`phase5_meta_rubric_calibration`,
`phase6_meta_rubric_gating`) as superseded by ADR 0024, or keep them dormant. Cost of keeping:
they surface "not ready" on every weekly run for events that are never written. *Rec: retire, one
YAML edit, status `done` with the pointer here.*

**F-E — the seventh candidate order on the slot-rank shadow:** `credits desc, then the acting RS
order` (theme + structure credit_steps from the shadows; gap not yet validated). Zero-authority by
§5's rule — no ruling needed to BUILD it — but a new line needs a burndown offset or his carryover.
Cost: a small Sonnet card; touches `ep_slot_rank_shadow.py` + one column. *Rec: open it; it is the
$0 test of the portfolio use he named first.*

**Not re-opened here:** ADR 0024 F1/F2 (judge owns catalyst, axes own context, net ±1 — signed
07-07); #331's 07-21 ruling (*collect more*); the #299 unchain (08-03).

## 8. What this ADR explicitly does NOT do

No production code. No status applied — §5's verdicts are for the operator/main loop to apply. No
weighting, composition rule or gate moved. No new setup proposed. It does not re-derive the
delta matrix (`meta_rubric_reconciliation_329_2026-06-18.md`) or the D1–D7 tee-up
(`meta_rubric_groundwork_2026-06-24.md`); it sequences them.

## 9. Pointers

- Owner of the meta rubric's criteria + findings: `docs/setups/meta_rubric.md`
- The judge: ADR 0011 · composition + ladder: ADR 0024 · axes: ADR 0015 / 0016 / 0033 / 0028
- Evidence cited: `docs/analysis/368_first_90_labels_read_2026-08-04.md` ·
  `486_judge_vs_theme_engine_2026-08-29.md` · `331_gap_alignment_step0_2026-07-21.md` ·
  `335_theme_boost_keep_rationale_2026-07-19.md` · `m1b_regrade_2026-07-13.md` ·
  `runner_rule_sweep_2026-08-29.md` · `545p2_missed_ep_tail_read_2026-09-02.md`
- The principles this ranks against: `docs/roadmap/ep_profitability_program.md` (P1–P15, §1b)
- Registry: `data_gated_reviews.yaml::theme_axis_boost_reeval` · `gap_alignment_331_accrual` ·
  `b6_gate_inversion_recheck` · `judge_signal_wiring_effect_2026_09_01`
