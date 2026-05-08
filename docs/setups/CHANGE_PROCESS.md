# Setup Change Process

Required reading before any change to a trading setup. Discipline file — every rule here exists because we previously hurt ourselves by skipping it.

## The rule

**Before changing any setup detection criterion: read the setup's SSoT file (entire file, not just the change log) and confirm the change isn't a reversal of a recent decision.**

If it IS a reversal: read the prior change-log entry to understand WHY the prior decision was made, and document why the prior reasoning is wrong (not just incomplete) before reverting.

## Required change-log fields

Every change-log entry on a setup file must have:

```
### YYYY-MM-DD — Short title

**Trigger**: what made us notice this needed changing? (Specific incident, user observation, backtest finding, advisor flag)

**Evidence**: what data supports the change? Required for any threshold or gate change. Forms:
  - "N case studies: X, Y, Z" (insufficient if N=1 — flag as such)
  - "30d backtest: A of B candidates affected, C correct, D incorrect"
  - "Replay against 60d historical: result"
  - "User judgment after reviewing filter list" (acceptable but document who reviewed what)

**Anticipated effect**: what should change in production behavior? Concrete: "filter rate goes from X% to Y%", "expect M more alerts/day", etc.

**Reversion-flag**:
  - NEW (no prior change to this constant/logic)
  - REFINEMENT of [date] change (tweaking direction)
  - REVERSAL of [date] change (going opposite direction — must explain why prior was wrong)
  - EMERGENCY revert (production breaking)

**Status**:
  - shipped, awaiting field validation
  - shipped + validated against [N] live sessions
  - reverted [date] (then write the next entry as the revert)
```

## Discipline rules

1. **Backtest before deploying any threshold change.** N≥10 historical samples evaluated. If you can't measure the impact, don't ship.

2. **Single-case fixes are flagged.** "Trigger: VECO 5/6 incident, Evidence: 1 case study" is allowed but must be marked "single-case-tune" in the entry. Stay alert for future cases that contradict.

3. **HARD gates require sign-off.** A filter that drops candidates entirely (no fallback) needs a user-reviewed list of what would be filtered before ship. The agent must NOT classify the filter list as "correct" or "false positive" without the user's call (see `parabolic_short.md` 2026-05-08 reversal — agent classified VECO as correctly-filtered without ground truth, then reverted, then restored).

4. **Reversals must explain why prior was wrong.** Not just incomplete, not just "we got new evidence" — articulate what specific reasoning the prior change rested on, and why that reasoning was incorrect. A reversal with weak rationale is a candidate for re-reversal next month.

5. **Field-validate before ship to live.** Shadow phase or paper-only first. Audit-event counts confirm the change behaves as anticipated. Live promotion requires the "shipped + validated against [N] live sessions" status.

6. **Update the SSoT in the same commit as the code change.** Stale SSoT is worse than no SSoT — it'll be cited authoritatively but contradict the code. CI should flag commits that touch detector code without touching the corresponding SSoT file (future).

7. **Open questions go in the file, not in tickets that get lost.** The setup file's "Known limitations / open questions" section is the canonical surface. Tickets/tasks reference back to it.

## When NOT to log

- Pure refactor with no behavior change (rename, extract function, etc.) — log in commit only.
- Adding telemetry / audit events / observability without changing detection logic — log in commit only.
- Comment changes — log in commit only.

## Migration from CLAUDE.md "Recent Changes"

CLAUDE.md historical entries pre-date this SSoT. As each setup file is touched, backfill the relevant prior entries (last ~2 weeks at minimum) into its change log so the file is self-contained. Don't try to backfill everything at once — incremental as each setup gets edited.
