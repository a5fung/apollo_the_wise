# M1 sitting pack — the judge-authority flip (#335), sitting 2026-07-18

*Assembled by Fable 2026-07-11 (Block 3 T5a) so the 7/18 sitting is turnkey. Two inputs land
during the week and slot in below (marked ⬜); everything else is ready now.*

> **⚠️ CORRECTED 2026-07-13 (Opus, verified vs prod+code — see `m1_htf_readiness_2026-07-18.md`
> §Decision 1, F1/F2/F3/F4).** The "The decision" section below as originally drafted is FALSE on
> prod: the holistic judge has been **LOAD-BEARING since 2026-06-10** (`holistic_judge_enabled`
> toggle `on`; 41/42 alerts since 6/10 carry `grade_engine_authority='judge'`). The real M1 flip
> is **`composite_authority`** (the theme-axis composition ON TOP of the judge's verdict), NOT
> `get_holistic_judge_enabled` (already flipped). The decision paragraph + verify-live step are
> corrected in place below; the readiness doc is authoritative on any conflict. **7/18 is
> GO-CONDITIONAL**: signable only if the composite wire-in is deployed dark (built this week,
> M1-d) + M1-b's regrade delta table is at the sitting; else sign the package and defer only the
> flip.

## The decision (CORRECTED)

Flip **`composite_authority`** (a new DB-backed `mi_safeguard_state` toggle, default OFF/dark) →
the operator-signed theme-axis credit table (`theme_axis_credit`) becomes LOAD-BEARING: the
grade path composes the credit onto the authoritative tier via `compose_final_tier`
(±1 net cap), and the COMPOSED tier drives the paper grade. Today that composition is computed
only in SHADOW (`theme_axis_shadow_adjusted` audit rows) — nothing consumes it live. **NOTE: the
holistic judge itself is ALREADY authoritative (since 6/10) — this flip is one layer up: theme
context composing onto the judge's verdict, not the judge flip.** **Money exposure: governs the
PAPER path decision quality; MAGNA53 live entries remain floor+filters as wired — an authority
change on the grade, not a new order path.** Rollback = the `composite_authority` DB toggle OFF
(instant, no deploy — mirrors `holistic_judge_enabled`; the env-var read in `meta_rubric_compose.py`
is superseded by the DB toggle at M1-d so revert is genuinely deploy-free).

## Preconditions checklist (rule each ✔/✖ at the sitting)

1. ⬜ **The robustness map** (ADR 0030 C3, runs this week): per-class failure rates over the
   36-case corpus + mined half. **Interpretation contract (pre-agreed):** failures found ≠ block
   the flip; hard-class failures (zero-tolerance classes) become rubric amendments BEFORE
   authority; soft-class failures become monitored-with-band. What blocks the flip is only: a
   positive-control failure rate >20% (the judge kills real winners) or an unfixable hard-class
   cluster.
2. ⬜ **Theme-axis gating review** (`theme_axis_gating_logic`, deferred to 7/18): rules whether
   the theme axis stays a judge INPUT only or gains gate authority. Rec: input-only at M1
   (axis authority is a separate, later fork — don't couple it to the M1 flip).
3. ✅ **R5 preconditions (premortem)**: the runtime drift band is SPECCED (T2c —
   `judge_high_rate_daily` + `judge_demote_share_daily`, L2-banded). **Build T2c-C1 before 7/18**
   (~40 lines + 2 tests) so the tripwire is live the day authority flips. #301's golden cases:
   seeded by the 0030 corpus (recorded; build not a flip-blocker).
4. ✅ **The regression gate** (ADR 0030 [5m/7]): pass-record mechanism designed; C2 lands after
   C3's first run. From then on, no rubric/prompt/model change ships ungraded — the standing
   answer to "what if the judge silently degrades after we hand it authority."
5. ✅ **Grade-era versioning**: RUBRIC_VERSION v3 + RUBRIC_HASH + prompt version stamped on every
   decision — post-flip decisions are segmentable from pre-flip forever (already live).
6. ✅ **Fail-open preserved**: `grade_holistic` returns None on any error → the floor decides.
   The flip does NOT change the failure mode; a judge outage degrades to today's behavior.

## What ships WITH the flip (same sitting, pre-argued)

- **The m1_rubric_amendment_draft (7/8)** — rule it as part of the flip package: if signed, it
  bumps RUBRIC_VERSION → the 0030 eval re-runs against the SAME corpus before deploy (the gate's
  first real exercise, by design).
- **Axis wire-ins gated on #335** (theme heat stage/score into the prompt; `axis_reads` live):
  rec = flip them WITH authority (they were built for this gate; the eval arm already exercises
  axis_reads).
- **Pre-declared baseline shifts (register R7 idiom):** the T2c metrics will level-shift at the
  flip — pre-declare in the flip's audit note so the first L2 read isn't a false alarm.

## The flip mechanics (CORRECTED — so the sitting ends in an action, not a plan)

*Pre-7/18 (this week, DARK): the `composite_authority` wire-in + DB toggle are built
default-OFF (M1-d, byte-identical until flipped — code-only, no `_RUBRIC` change so [5m/7]
passes and it deploys without a $5 eval re-run); M1-b's ONE paid regrade is run → the
verdict-delta table lands on this table for the sitting.*

1. Sign the package (composite table §3 credit values + ±1 cap + the rubric amendment wording
   + Mainstream open question). Walk the M1-b deltas + operator labels first.
2. **If the amendment is signed:** it edits `_RUBRIC` → bump RUBRIC_VERSION → run the 0030 eval
   on the amended rubric on prod → green → regenerate `judge_eval_pass_record.json` → `deploy.sh
   market-agent` ([5m/7] passes on the new record; the composite toggle still OFF ⇒ byte-identical).
3. Operator flips the **`composite_authority`** DB toggle on
   (`set_composite_authority.py on`; runtime, no deploy) during off-hours.
4. **Verify-live (composition evidence, NOT `authority='judge'` — that would pass TODAY with no
   action):** next scan day, a composed tier visibly **≠** the judge tier on an
   Accelerating-theme alert — i.e. a `theme_axis_composed` audit row (`base_tier -> composed`,
   `authority=composite`) + the `/why` render showing the contribution + T2c samples ticking.
5. The drift band + judge-delta digest are the standing watch; **rollback = `composite_authority`
   DB toggle OFF** (instant; composition stops, the judge-authority behavior of the last month
   resumes).

## Open items the sitting does NOT decide (parked deliberately)

- Theme-axis AUTHORITY (input-only at M1; own fork later, with its own evidence).
- 0028 salience profiles (P0 visibility first; its P1 interacts with the judge via the R6
  gate-tuple extension when it comes).
- Chart-vision (#267) and tape-features (#299) wire-ins — each stays behind its own eval arm.
