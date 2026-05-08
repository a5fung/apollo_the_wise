# Trading Setup SSoT — Index

**Purpose**: single source of truth for every trading setup Apollo detects. Each setup file is the canonical definition; code is the implementation. When the two diverge, the SSoT documents the intent and the code is fixed to match.

**Why this exists**: Apollo has accumulated dozens of detection-criteria changes across 6+ setups. Without a write-it-down discipline, we accumulated overfitting (single-case threshold tweaks), oscillation (same parameter changed back and forth — see parabolic days_up_streak 2026-05-08), and rediscovery of solved problems. The SSoT prevents this by forcing every change to be logged with rationale + evidence + reversion-flag, then reviewed against the change log before the next change to the same setup.

## Active setups

| File | Setup | Phase | Last changed | Open questions |
|---|---|---|---|---|
| [magna53_ep.md](magna53_ep.md) | MAGNA53 EP (Episodic Pivot, Pradeep Bonde) | Live (paper) | 2026-05-08 | 0 |
| [ninem.md](ninem.md) | 9M EP intraday + Sugar Baby + Day 2 ORB | Live (paper) | 2026-05-08 | 0 |
| [parabolic_short.md](parabolic_short.md) | Parabolic Short (Stamatoudis / Quallamaggie) | Shadow | 2026-05-08 | 1 (pivot stability) |
| [flag_continuation.md](flag_continuation.md) | Continuation Flag (VCP / Qullamaggie tightening) | Shadow | 2026-05-08 | 0 |
| [wick_fill.md](wick_fill.md) | Wick-Fill / Negated Shooting Star (Kristjan/Bonde) | Telemetry | 2026-04-28 | 0 |
| [convergence.md](convergence.md) | Base + Anticipated Catalyst (Wave D #8) | Spike memo only | 2026-05-08 | 7 (in spike memo) |
| [safeguards.md](safeguards.md) | Portfolio safeguards (drawdown breaker #6 in shadow) | Shadow → Active (target ≥14d post-live-cutover) | 2026-05-08 | 3 |

## Discipline

[CHANGE_PROCESS.md](CHANGE_PROCESS.md) — required reading before any setup change. Defines the change-log fields and the review-before-change rule.

## Cross-references

- **Strategy registry**: `agents/market_intelligence/strategies/registry.py` — runtime config (live/shadow/disabled phase per strategy)
- **CLAUDE.md** — historical "Recent Changes" entries that predate this SSoT (will be migrated incrementally as each setup is touched)
- **Spike memos**: `~/.claude/plans/` — detailed design memos for new setups (e.g., `wave-d-convergence-spike.md`, `cross-strategy-ranking-spike.md`)
- **Trading ideas backlog**: `memory/project_trading_ideas_backlog.md` — pre-spike ideas, not yet active setups
