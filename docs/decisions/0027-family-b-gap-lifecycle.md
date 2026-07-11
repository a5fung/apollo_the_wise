# ADR 0027 — Family-B gap-anchored lifecycle (#297): EP/9M inherits the anticipation machinery

**Date**: 2026-07-11
**Status**: **DESIGN — awaiting operator sign-off** (Fable weekend block 1). All-shadow (no money
path); ships full once signed per the no-conservatism rule. This is the **receiving structure**
for #326 (the dated 9/15 Day-2-ORB retirement decision) — it must be accruing forward shadow by
mid-August so #326 decides on evidence.
**Authors**: Fable (operator-triggered weekend block, 2026-07-11)
**Relates**: #326 (Day-2 ORB retirement: filled median **−0.24R**, no robust edge —
`ninem_consolidation_vs_day2_replay_327_2026-06-18.md`), #327 (consolidation entry shadow — the
sibling forward-shadow), #446 (cancelled-unfilled EP HIGHs = 36.7% winners — the same
"gap fired, entry missed, no second look" hole), `docs/roadmap/family_a_setups_split_2026-06-22.md`.

## 1. Context — Family B has detection but no lifecycle

Family A (consolidation) got the full lifecycle treatment: `anticipation.replay()` /
`evaluate_candidate()` (`anticipation.py:82-593`) track WATCHED→ARMED→(COILED/READY)→TRIGGERED→
EXPIRED per gap event, anchored to absolute dates (the ANCHOR-STABILITY invariant,
`:606-611`), persisted in `mi_anticipation_lifecycle` (`db.py:1606-1661`), settled to shadow
entries. Family B (EP/9M gap-ups) has **detection only**: a gap event either enters same-day or
falls on the floor — the sole second-chance mechanic is the 9M **Day-2 ORB**, which #326's replay
showed earns nothing (−0.24R filled median) and is queued for retirement. Meanwhile the machinery
Family B needs *already exists and is already gap-anchored* — `replay()`'s states literally key on
`gap_day_low` undercut/reclaim. The rework is inheritance, not invention.

Also in scope: `mi_anticipation_lifecycle` carries **phantom rows** — silent pace-projected
anticipation rows that settle `realized_r` but carry no realized edge (advisor 6/14); the #327
predicate already dodges them via `entry_tactic IN ('first5_break','gdl_reclaim')`. They need a
structural fix, not per-consumer filters.

## 2. Decision

### D1 — provenance column + phantom archive (the cleanup, first)

`mi_anticipation_lifecycle` gains `origin TEXT NOT NULL DEFAULT 'family_a'`
(`'family_a' | 'family_b_9m' | 'family_b_ep' | 'pace_phantom'`). One-time backfill classifies
existing rows (the silent pace-projected set → `'pace_phantom'`). EVERY consumer (settlement job,
digests, the #327 predicate, future reviews) filters on `origin` — the per-consumer
`entry_tactic` dodge retires. Phantoms stay queryable (audit trail) but are structurally out of
every stat. No deletes (trade-adjacent hygiene: archive-by-tag, never destroy).

### D2 — Family-B seeding (what creates a lifecycle row)

Two seed classes, both post-detection (no new detection criteria — this consumes existing
signals):
- **9M EOD confirm** (`mi_9m_day2_candidates` insert): seed `origin='family_b_9m'`, gap_day =
  the 9M day, `gap_day_low` = that day's low. This is the direct Day-2-ORB replacement surface.
- **Un-entered EP HIGH** (window-out `WINDOW_OUT_OF_ORB`, `cancelled_unfilled`, or
  judge-HIGH-not-filled): seed `origin='family_b_ep'` — the #446 finding (36.7% winners among
  cancelled HIGHs) says this cohort is worth a tracked second look.
Seeding is idempotent on (ticker, gap_day, origin) via the existing anchor invariant. Cap: skip
seeding when the ticker already has an open Family-B row (one live lifecycle per name per origin).

### D3 — lifecycle + the shadow entry (pure inheritance)

Run the EXISTING `evaluate_candidate()` semantics over Family-B rows in the nightly Family-A job
(same code path, origin-parameterized): WATCHED → ARMED (undercut `gap_day_low` on contraction) →
TRIGGERED (reclaim above `gap_day_low` + volume expansion ≥1.5× pullback avg) → EXPIRED (no
undercut in the arm window). A TRIGGERED Family-B row writes a **shadow entry**
(`entry_tactic='gdl_reclaim'`, entry = reclaim close, stop = undercut low) into the same
settlement machinery as #327 — realized-R accrues per-origin, **never blended** with Family-A or
with each other. NO live/paper path — shadow only; any promotion is a separate future money gate.

Parameter honesty: the WATCHED seed quality gates (≥40%-of-range close on ≥3× ADV20) were tuned
for Family-A anticipation seeds. Family-B seeds arrive pre-qualified (a 9M print / an EP HIGH IS
the qualification) → the seed gate is **bypassed for Family-B** (they enter WATCHED
unconditionally), **except a hard liquidity floor stays**: dollar-volume ≥ $20M on the gap day
(the family universe floor) — an EP HIGH can be cancelled *because* it was thin, and a thin
name's undercut/reclaim prints are exactly where the l=c-class replay math misreads. The
undercut/reclaim mechanics apply unchanged. This is the one deliberate divergence, recorded here
so the shadow readout can falsify it (if Family-B triggered-rows underperform, the first suspect
is seed quality).

## 3. Rollout + built-in triggers

1. C1 (origin+archive) → C2 (seeding) → C3 (lifecycle run + shadow settlement) — one deploy,
   all dark-equivalent (shadow tables only).
2. **Gated review `family_b_lifecycle_first_read`**: predicate ≥15 settled Family-B shadow rows
   (both origins pooled for the *readiness* count, split in the readout); earliest 8/25 — timed
   so its output lands BEFORE the #326 sitting (9/15): the Day-2-ORB retirement decides against
   the GDL-reclaim shadow evidence, not a vacuum. On ready → per-origin R table → feeds #326.
3. SSoT: `docs/setups/ninem.md` gains the lifecycle section (same commit as C2/C3);
   `family_a_setups_split` roadmap updated (Family B = detection + lifecycle).

## 4. Cards

- **C1 — origin column + phantom backfill** (migration + backfill script dry-run-first + every
  consumer read-path filtered; 5 tests incl. #327-predicate-equivalence pre/post).
- **C2 — Family-B seeders** (9M-EOD hook + un-entered-EP-HIGH hook; idempotent, capped; 6 tests).
- **C3 — origin-parameterized lifecycle run + gdl_reclaim shadow settlement** (reuse
  evaluate_candidate; per-origin settlement lanes; 7 tests incl. seed-gate-bypass-for-B +
  never-blend).
- **C4 — the gated review + ninem.md SSoT section.**

## 5. Operator forks

- **F1 — EP-seed scope:** rec = window-out + cancelled-unfilled + judge-HIGH-unfilled (the
  full un-entered set; it's shadow — breadth is cheap and #446 says the cohort is hot).
  Alternative: 9M-only first — loses the EP arm of the evidence for no risk saved.
- **F2 — seed-gate bypass (D3):** rec = bypass for Family-B (pre-qualified seeds). Alternative:
  apply Family-A seed gates — cleaner symmetry, but filters the already-thin cohort and delays
  the #326 evidence.
