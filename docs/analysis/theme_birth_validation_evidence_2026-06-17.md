# #266 — Theme membership validation AT BIRTH: evidence run (2026-06-17)

**Question:** given post-assignment validation + the 6 AM round-trip validator + the Mon/Wed/Fri
`_validate_theme_membership` already exist, does validating membership AT BIRTH (and at
identity-change) add measurable value, or is it redundant?

**Verdict: evidence-SUPPORTED.** Birth/identity-change validation would catch a large class of
mismatched members ~6 days earlier than today. CHANGE_PROCESS + sign-off still required (it changes
theme membership behavior); one root-cause must be resolved first (below).

## The data (read-only, `scripts/_theme_birth_validation_evidence.py`, 60-day window)

- **1,338** themes born with ≥2 members; **608** member-strips within 14d of birth.
- **Strip latency from birth — the decisive metric:**
  | bucket | share | meaning |
  |---|---|---|
  | ≤ 1h (at-birth) | **0%** | post-assignment validation is NOT catching these at birth |
  | ≤ 24h | 10% | |
  | ≤ 72h (round-trip window) | 27% | |
  | **> 72h (the gap)** | **73%** | caught only on the next Mon/Wed/Fri cycle |
  | **median latency** | **144h (6.0 days)** | a mismatched member sits in the theme ~6 days |
- **247** themes had ≥1 post-birth strip; the round-trip alarm (≥50% & ≥2 in 3d) fires on only
  **13** → a **residual of 234** themes carrying bad-birth members below the alarm bar.

## Why the confound resolves in #266's favor

Strip-latency alone conflates "bad at birth" with "legitimately churned out later." But the
`removal_reason` breakdown is unambiguous: **every reason is `Description '<company>' does not match
theme`** — a mismatch between the company's (static) description and the theme description. Both are
known **at birth**, so this class is fully birth-detectable. A member stripped for description-mismatch
6 days after birth *could have been caught at creation*. (Where the theme's own description was later
revised, that's the "+ identity-change" half of #266 — same validation, applied at the rename.)

## The one root-cause to resolve before building (fix-design, not evidence)

The **0% at ≤1h** is the key anomaly: CLAUDE.md states "Post-assignment validation: immediately
validates newly assigned stocks." If it ran a description-match at birth it would catch these. So
either post-assignment validation (a) isn't running, (b) doesn't do the description-match the periodic
pass does, or (c) is materially more lenient. **#266 is therefore "find out why post-assignment
validation misses birth description-mismatches, then strengthen it,"** NOT necessarily a brand-new
pass. Root-cause that before the CHANGE_PROCESS change.

## Recommendation

1. Root-cause the post-assignment validation gap (above).
2. Run the SAME description-match the Mon/Wed/Fri pass uses at BIRTH + at identity-change (rename /
   description revision), so the 73%/6-day-median tail collapses toward 0.
3. CHANGE_PROCESS entry + sign-off (membership behavior change). Re-run this probe after to confirm the
   latency distribution shifts left. Add the probe to the monthly backward-check sweep
   (`feedback_methodology_insights_need_periodic_revalidation`).
