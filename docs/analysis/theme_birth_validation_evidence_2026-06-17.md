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

## Root-cause — RESOLVED (deterministic code trace, 2026-06-17)

The **0% at ≤1h** is because **theme BIRTH (discovery) never runs the description-match validator on
the founding members.** `_validate_theme_membership` is called at exactly two sites (grep-confirmed):
- `theme_engine.py:1754` — inside `_rescore_existing_theme` (the **Mon/Wed/Fri** rescore of
  **existing** themes).
- `theme_engine.py:2371` — post-assignment, but only for tickers **assigned to an existing theme**
  (`_assign_uncovered_to_themes`; it iterates `existing_themes` with `newly_added` tickers).

The discovery → persist path (`run_theme_engine` Step 3/4, lines ~3895–4004) is:
`_discover_new_themes` → `_score_new_theme` → name-inheritance → `_strip_commodity_contradictions`
(a narrow deterministic gold-in-uranium strip, NOT the general industry-match) → `_save_themes`.
**No `_validate_theme_membership` anywhere on that path.** So a theme born today with mismatched
members is validated for the FIRST time on the next Mon/Wed/Fri `_rescore_existing_theme` run — the
6.0-day median latency, exactly. (CLAUDE.md's "Post-assignment validation: immediately validates newly
assigned stocks" is true but applies ONLY to assign-to-existing, not to discovery births.)

## The fix (minimal, single-source) — CHANGE_PROCESS + operator sign-off

Run the **same, already-trusted `_validate_theme_membership`** (Sonnet, #213-tuned) on each
newly-discovered theme's members in Step 3, **before `_save_themes`** — i.e. validate at birth
instead of 6 days later. Key properties that make this low-risk:
- **Not a new validator** — it's the identical function the Mon/Wed/Fri pass already runs and the
  operator already trusts; #266 only changes WHEN it runs (at birth), not WHAT it checks. Same
  Sonnet model, same prompt, same protected-set/exclusion shields.
- A birth-validation that strips a new theme below `NEW_THEME_MIN_STOCKS=2` → the theme simply isn't
  born (the desired outcome, not a regression).
- Cost: a few extra Sonnet calls per run (one per discovered theme, bounded by `_VALIDATION_SEMAPHORE`).
- **Identity-change half** (secondary): re-validate at the name-inheritance point (`theme_engine.py`
  ~3946) / description revision. Smaller tail; propose as a follow-on after birth-validation lands.

**Safe-subset option** (if the operator wants evidence before flipping live): a SHADOW pass that logs
`would_strip_at_birth: TICKER from THEME` without removing — gathers the specific names + correctness
for the sign-off decision at zero membership-behavior risk. Recommend going straight to live given the
validator is already trusted, but the shadow is the fail-safe.

## Recommendation

1. Root-cause the post-assignment validation gap (above).
2. Run the SAME description-match the Mon/Wed/Fri pass uses at BIRTH + at identity-change (rename /
   description revision), so the 73%/6-day-median tail collapses toward 0.
3. CHANGE_PROCESS entry + sign-off (membership behavior change). Re-run this probe after to confirm the
   latency distribution shifts left. Add the probe to the monthly backward-check sweep
   (`feedback_methodology_insights_need_periodic_revalidation`).
