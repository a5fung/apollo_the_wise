# #211 — Decisive unknown-cohort eyeball (2026-06-08)

**Question (advisor-framed):** before building the #211 Part-2 LLM gap-finder,
look at the historical source-coverage unknowns — graded **strong / game_changer**
with `has_direct_source = False`. Are they genuine sourcing gaps, or would the new
Wave A (Benzinga) / Wave D (8-K EX-99 / 6-K) path now catch them? "That read is 10
minutes and it's dispositive — if 3 of 4 are already-closed-by-the-new-waves, Part 2
is solving a near-solved problem and should wait."

## Method

Provenance is logged as `event_type='ep_catalyst_provenance'` rows in
`mi_audit_log` (detail = the JSON payload, incl. `has_direct_source` + `sources`).
These rows only exist since **Wave B deployed 6/7**, so the measurable window is
post-Wave-B (not the pre-Wave-B 30d). Read-only pull via
`scripts/_unknown_cohort_eyeball.py` (throwaway).

## Result — dispositive

Provenance rows since Wave B: **N=7** (5 routine, 1 strong, 1 game_changer).

Of the two graded-UP alerts, **both had `has_direct_source = True`**, both via the
exact sources the new waves introduced:

| ticker | grade | sources |
|---|---|---|
| CGEM | strong | `{sec_8k:1, benzinga_pr:2, web_perplexity:1}` |
| NRIX | game_changer | `{sec_8k:1, benzinga_pr:1, web_perplexity:1}` |

**Source-coverage unknown cohort (strong/gc, has_direct_source=False) = N=0.**

This is stronger than the advisor's 3-of-4 threshold: 2 of 2 graded-up alerts are
already directly sourced by the new path. The new waves ARE the fix.

## Disposition

- **#211 Part 2 (LLM gap-finder) — DEFER.** It would solve a near-solved problem.
  Re-trigger condition: a non-zero, *persistent* source-coverage unknown cohort
  accrues (graded strong/gc with `has_direct_source=False` recurring across days).
  When that happens, build it as a #212-harness prototype under #235 / #230 — NOT
  a new standalone job in #211.
- **#211 Part 1 (deterministic measurement) — already substantially shipped.** The
  KPI exists: `_ep_scan_watchdog` writes `ep_provenance_daily` at 10:05
  ({date, graded, direct_sourced, unknown_cohort, by_source_class}) and Telegrams
  🔴 only on alerts-but-0-provenance; `/unknownrate` surfaces it on demand. The one
  genuinely-new Part-1 piece — a weekly unknown-rate *trend* digest — is **deferred
  until the KPI accrues enough non-zero history to be worth a trend line.** Surfacing
  a flat-zero series now is the #46 rare-event-zero-heavy noise class.

**Net:** the backbone (Waves A–D) closed the sourcing gap #211 was chartered to
discover. #211 stays open as the measurement KPI (already live); the discovery-loop
half waits on evidence of a real recurring gap.
