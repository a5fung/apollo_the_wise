# M1 sitting pack — the judge-authority flip (#335), sitting 2026-07-18

*Assembled by Fable 2026-07-11 (Block 3 T5a) so the 7/18 sitting is turnkey. Two inputs land
during the week and slot in below (marked ⬜); everything else is ready now.*

## The decision

Flip `get_holistic_judge_enabled()` → the judge's verdict becomes LOAD-BEARING on the paper
grade path (`_resolve_grade_authority` stops treating it as advisory). Today the judge writes
advisory columns only; the conviction floor decides. **Money exposure: the flip governs the
PAPER path decision quality; MAGNA53 live entries remain floor+filters as wired — this is an
authority change on the grade, not a new order path.** Rollback = the same runtime toggle, off
(no deploy).

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

## The flip mechanics (so the sitting ends in an action, not a plan)

1. Sign the package (flip + amendment draft ruling + wire-ins).
2. If the amendment is signed: bump RUBRIC_VERSION → run the 0030 eval → green pass-record.
3. Toggle `get_holistic_judge_enabled` on (runtime; no deploy) during off-hours.
4. Verify-live: next scan day, `ep_grade_decision` rows show `authority='judge'` with
   `judge_outcome='verdict'` driving the tier + the T2c metrics ticking.
5. The drift band + judge-delta digest are the standing watch; rollback = toggle off.

## Open items the sitting does NOT decide (parked deliberately)

- Theme-axis AUTHORITY (input-only at M1; own fork later, with its own evidence).
- 0028 salience profiles (P0 visibility first; its P1 interacts with the judge via the R6
  gate-tuple extension when it comes).
- Chart-vision (#267) and tape-features (#299) wire-ins — each stays behind its own eval arm.
