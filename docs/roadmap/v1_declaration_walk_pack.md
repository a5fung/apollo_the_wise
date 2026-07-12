# v1.0 DECLARATION WALK PACK (#425) — turnkey, pre-argued (Fable, 2026-07-12 eve)

**How to use:** at the walk (target **~7/22–24**), go FL by FL; each row has its measure, its
current state, and WHERE the evidence lives. Rule the two forks first — they set the date.
Companion: `done-done-map-2026-07-12.md` (the definition of done above v1.0).

## The two forks (rule these first)

**F1 — the soak ruling (sets the clock).** FL-1 resets on trade-state touches "outside designed
surfaces." On 7/6–7/7 two COMMITTED, DRY-RUN-REVIEWED scripts touched mi_live_trades (the
phantom reap; the jsonb cleanup). *Strict reading (REC): they were REPAIRS — the system needed
hands — the clock reset 7/7 → clean-streak start 7/8 → 10 trading days completes ≈ Tue 7/22.*
Lenient reading: reviewed scripts ARE designed surfaces → streak from 7/3 → completes sooner
but declares a soak containing manual repairs — hollow. **Rec: strict; declare ≈ 7/22.**

**F2 — pull the ingest promotion (sets FL-4).** The 7/25 review is a BACKSTOP date, not an
earliest. Flip `dry_run` Monday 7/13 (1-minute toggle; propose-only, zero risk) → ≥3 clean R1
proposals → sign `live_r1` (~7/17) → 5 quiet days → FL-4 green ≈ 7/24, inside the soak window.
**Rec: flip Monday.**

## The FL walk

| FL | Measure | State 7/12 | Evidence / what remains |
|---|---|---|---|
| **FL-1** soak | 10 consecutive clean trading days | **3/10** under the strict ruling (7/8, 7/9, 7/10) | mi_audit_log: zero repair-class events since 7/7; the 7/12 hardening deploys (locks, /pause hole, watchdogs) exist to keep it clean. Completes ≈ **7/22** |
| **FL-2** fences exercised | every safeguard live-exercised | ~85% | ✅ max-positions block (LIVE, 7/6 — the phantoms capped the book) · ✅ /pause path (verified in code + the R2 gates now cover re-entry) · ✅ [5l/7] fence + boot preflight (run every deploy, 5× on 7/12 alone) · ✅ never-naked remediation (`_ensure_stop_coverage` exercised; see reconcile history) · ⬜ **daily-loss halt synthetic drill** · ⬜ drawdown-breaker per-mode transition evidence (16:12 job emits — pull the audit rows). Two items; drill-able this week |
| **FL-3** ops autonomy | 7 green nights | ✅ **DONE** (7/5→7/12: zero backup/restore/watchdog alerts — verified 7/12) | keep green through the walk |
| **FL-4** mirror completeness | ingest closed + 5 quiet days | built + paper-proven + DARK | F2 pulls it green ≈ 7/24. Coverage-drift quiet-days already accruing (D3 noise fixed by fork B 7/11) |
| **FL-5** docs-only recovery | DR current + #417 parity + setup docs reconciled at close | partial | #417 pass-1 done (7/5); DR roles fix done (7/5 — restore-check run-1 caught it, the system working); ⬜ the setup-doc reconcile sweep = a walk-day item (half-day, mechanical) |
| **FL-6** cost envelope | one spend surface + ceiling alert | ⬜ the last BUILD item | the data already exists (#377 meter logs every LLM call); the card = surface + threshold alert (Sonnet, ~half-day this week) |
| **FL-7** board zero (v1.0 scope) | blocking set closed; Phase-2 re-homed; zero overdue | ~done | remaining = market-gated verify-lives (#183 first fill · #287 next exit · #443 next HIGH · #463 Monday watchdogs · #445/T5/#452 job debuts) — they close DURING the soak by themselves. check_plan green daily |
| **FL-8** learning loop 4-Sunday streak | 4 consecutive clean Sundays | ✅ **DONE 7/12** (6/21 · 6/28 · 7/5 · 7/12 — the 4th verified this morning incl. the #412 encode fix) | — |

## The declaration checklist (walk day)

1. Rule F1 + F2 (above) — if already ruled, confirm the dates held.
2. FL-2: run the daily-loss synthetic drill + pull the drawdown transition rows (both ≤1h).
3. FL-5: the setup-doc reconcile sweep (docs/setups/* vs code, half-day, mechanical).
4. Walk FL-1..FL-8 against this table's evidence pointers; check each measure.
5. **Sign §8 of `v1-closeout-productization.md`. That signature IS v1.0 shipped.**
6. Same sitting, 10 minutes: bless the D-ladder in `done-done-map-2026-07-12.md` (D2–D5) so
   the next "are we done?" has a standing, metered answer.

## What declaration changes (so it's not just a ribbon)

- The BLOCKING lens retires; the board becomes the #419 Phase-2 program only.
- The operating cadence becomes the product: scans → judge (authority per M1) → entries →
  management → EOD audits → weekly review → data-gated sittings. The operator's job narrows
  to sign-offs and sittings — the D5 posture starts here.
- D2 (the bands verdict at N≥20) becomes the single most important number Apollo is
  accumulating. Everything else is in service of reaching it with the system intact.
