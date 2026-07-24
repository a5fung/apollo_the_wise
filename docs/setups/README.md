# Trading Setup SSoT — Index

**Purpose**: single source of truth for every trading setup Apollo detects. Each setup file is the canonical definition; code is the implementation. When the two diverge, the SSoT documents the intent and the code is fixed to match.

**Why this exists**: Apollo has accumulated dozens of detection-criteria changes across 6+ setups. Without a write-it-down discipline, we accumulated overfitting (single-case threshold tweaks), oscillation (same parameter changed back and forth — see parabolic days_up_streak 2026-05-08), and rediscovery of solved problems. The SSoT prevents this by forcing every change to be logged with rationale + evidence + reversion-flag, then reviewed against the change log before the next change to the same setup.

## Active setups

| File | Setup | Phase | Last changed | Open questions |
|---|---|---|---|---|
| [magna53_ep.md](magna53_ep.md) | MAGNA53 EP (Episodic Pivot, Pradeep Bonde) | Live (paper) | 2026-07-23 | 0 |
| [ninem.md](ninem.md) | 9M EP intraday + Sugar Baby (Stage 3 Day-2 ORB DEPRECATED #424, 7/5) | Live (paper), Stage 3 deprecated | 2026-07-05 | 0 |
| [htf.md](htf.md) | HTF — High Tight Flag (O'Neil/Minervini/Qullamaggie, sourced) — supersedes `flag_continuation.md`'s detection criteria | Shadow (telemetry-only; breakout-entry shadow→paper→live is the promotion path) | 2026-07-19 | see file (liquidity floor tune, ADR-0026 Confirm(b) reconciliation) |
| [parabolic_short.md](parabolic_short.md) | Parabolic Short (Stamatoudis / Quallamaggie) | Shadow | 2026-05-08 | 1 (pivot stability) |
| [flag_continuation.md](flag_continuation.md) | Continuation Flag (VCP / Qullamaggie tightening) — **RETIRED as a standalone strategy 2026-07-19** (ADR 0026 D1/C4); code lives on as `htf.md`'s engine + the Confirm(b) entry mode | Deprecated (registry `phase='deprecated'`, #424 2026-07-05, confirmed by ADR 0026 2026-07-19) | 2026-07-19 | 0 |
| [wick_fill.md](wick_fill.md) | Wick-Fill / Negated Shooting Star (Kristjan/Bonde) | Telemetry | 2026-04-29 | 0 |
| [delayed_ep_reentry.md](delayed_ep_reentry.md) | Delayed-EP Re-entry / tiny-cap fast-runner (#270) | Pre-deploy spec (paused — analysis+tuning complete 2026-06-14; deployable wiring blocked on #277 op-split residuals) | 2026-06-14 | wiring sequencing, post-#277 |
| [undercut_rally.md](undercut_rally.md) | Undercut & Rally (Morales/OWL, entry-technique #5) | Shadow (telemetry-only; promotion gated on `undercut_rally_signal_n10` N≥10) | 2026-05-31 | 6 (V2 deferrals) |
| [convergence.md](convergence.md) | Base + Anticipated Catalyst (Wave D #8) | Spike memo only | 2026-05-08 | 7 (in spike memo) |
| [safeguards.md](safeguards.md) | Portfolio safeguards (drawdown breaker #6 in shadow) | Shadow → Active (target ≥14d post-live-cutover) | 2026-05-08 | 3 |

Not yet tabled above (exist as SSoT files, not part of the original active-setups list):
[catalyst_rubric.md](catalyst_rubric.md) (LIVE gate, see file), [meta_rubric.md](meta_rubric.md),
[PORTFOLIO.md](PORTFOLIO.md).

## Discipline

[CHANGE_PROCESS.md](CHANGE_PROCESS.md) — required reading before any setup change. Defines the change-log fields and the review-before-change rule.

## Cross-references

- **Strategy registry**: `agents/market_intelligence/strategies/registry.py` — runtime config (live/shadow/disabled phase per strategy)
- **CLAUDE.md** — historical "Recent Changes" entries that predate this SSoT (will be migrated incrementally as each setup is touched)
- **Spike memos**: `~/.claude/plans/` — detailed design memos for new setups (e.g., `wave-d-convergence-spike.md`, `cross-strategy-ranking-spike.md`)
- **Trading ideas backlog**: `memory/project_trading_ideas_backlog.md` — pre-spike ideas, not yet active setups

## Change log

- **2026-07-24 — FL-5 reconcile: doc synced to code.** The Active-setups table was ~2.5 months
  stale: added the `htf.md` row (missing entirely since its 2026-06-27 ship), marked
  `flag_continuation.md` retired-as-standalone (2026-07-19, ADR 0026 D1/C4) with a phase of
  `Deprecated` rather than `Shadow`, added `delayed_ep_reentry.md` (paused, blocked on #277) and
  `undercut_rally.md` (shadow) rows, refreshed "Last changed" dates for the rows touched in this
  reconcile, and noted the 3 SSoT files that existed but were never tabled
  (`catalyst_rubric.md`, `meta_rubric.md`, `PORTFOLIO.md`). No code change.
