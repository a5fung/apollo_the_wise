# PROPOSAL — one parameterised ORB order builder, then 9M Day 2 deletes cleanly (#515)

**Status: DRAFT. Operator approved the SHAPE 2026-08-02 (*"yes, let's move"*); nothing built.**

---

## Why this and not "delete 9M Day 2"

Scoping (`515_9m_day2_removal_scope_2026-08-02.md`) found the removal blocked by a coupling: the
**5-min ORB shadow lane** — which is not 9M and carries the open **#482** bracket-geometry evidence —
imports and runs `prepare_9m_day2_orb_order`.

**The coupling is not an accident to work around. It is the diagnosis.** ORB order preparation is
shared infrastructure that got NAMED after its first caller, so the only place the shadow lane could
find those mechanics was inside a strategy that is now dead.

Re-homing or copying the builder leaves the identical trap for the next strategy that needs ORB
mechanics. Consolidating removes the *reason* the coupling exists.

It also follows the pattern this codebase already states for the layer above:
`entry_pipeline.submit_trade_entry` is documented as *the single funnel for both MAGNA53 EP and 9M
Day 2 entries (strategy differences inject via `spec_builder`)*. **The funnel was unified; the
builders never were.**

## What actually differs — one thing, per the code's own docstring

| | `prepare_orb_order` | `prepare_9m_day2_orb_order` |
|---|---|---|
| entry | ORB high | ORB high |
| **stop** | **today's ORB low** | **prior day's low** (the 9M breakout-day low) |
| sizing | regime-keyed resolver | regime-keyed resolver |
| `today` pinning | caller-passed, single clock | caller-passed, single clock |

`prepare_9m_day2_orb_order`'s docstring states it directly: *"Key difference from
prepare_orb_order(): stop = prior day's low… not today's ORB low."*

⚠ **Step 1 is to PROVE that is the only difference, not to assume it.** A line-by-line diff of the
two bodies, with every divergence enumerated, before any merge. If a second difference exists the
proposal changes shape.

## The change

**One `prepare_orb_order(..., stop_source=...)`** — MAGNA53 passes ORB-low, the 9M/shadow path passes
prior-day-low. Same idiom as `check_fade_guard(ratio=…)` and the `rt_gap_floor_pct` parameter added
on 8/01: **the strategy names its own policy; the shared code holds no strategy's constant.**

Then the 9M Day 2 deletion is genuinely clean — job, entry fn, facade entry, strategy row — with
nothing else pointing at it, and the shadow lane keeps running on the shared builder.

## ⚠ The evidence standard is EQUIVALENCE, not a backtest

**This is not a criteria change.** Same entry, same stop, same sizing, same clock. So CHANGE_PROCESS
r1's *"N≥10 historical samples"* does **not** apply — that governs threshold changes, and no
threshold moves.

The correct gate is **behaviour-preserving proof**:
1. Line-by-line diff, every divergence enumerated (step 1 above).
2. A test that runs BOTH old builders and the new one over the same inputs and asserts
   **identical spec output** — entry, stop, shares, risk — for the MAGNA53 case and the 9M case.
3. Mutation check: break the `stop_source` wiring and confirm the equivalence test fails. A green
   equivalence test that cannot fail is worth nothing.

*(This classification matters — on 8/01 I applied r1's N≥10 to what was actually a bug fix and stalled
real work on the wrong standard. Ask what KIND of change it is first.)*

## Sequence

1. **Prove the diff.** Enumerate every divergence. ← blocking
2. Merge into `prepare_orb_order(stop_source=…)`; equivalence test green; old 9M builder becomes a
   thin alias so nothing breaks mid-change.
3. Point the shadow lane at the shared builder. **#482 evidence must keep accruing — verify the lane
   still writes `mi_orb_shadow_trades`.**
4. Delete 9M Day 2: job, `submit_9m_day2_trade`, facade entries, strategy row, the Day-2 writer and
   watchlist render inside `ninem_detector.py`. Drop the alias.
5. **Verify-live, the anti-over-deletion guard**: 9M CHARACTER detection still writing
   `mi_9m_ep_alerts`, and the shadow lane still writing.
6. Two-step deploy (market-agent → execution). `broker/` routes correctly since the 8/02 scope fix.

## What this does NOT do

No strategy changes behaviour. No threshold moves. MAGNA53 entries are byte-identical or the
equivalence test failed. This removes a dead strategy and the mis-naming that let it own shared
infrastructure.
