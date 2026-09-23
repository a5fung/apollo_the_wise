# Base + Anticipated Catalyst Convergence

**Phase**: Spike memo only. Not yet implemented.
**Origin**: Wave D #8 from 5/06 paper-session triage. Generalized 5/07 from "flag base + earnings" to "base + anticipated catalyst (any source)" per user reframing.
**Spike memo**: `~/.claude/plans/wave-d-convergence-spike.md`
**Backlog entry**: `memory/project_trading_ideas_backlog.md` TI4

## Definition

A stock forming a tight base (TIGHTENING / COILED in `mi_flag_candidates`) AND with a known scheduled catalyst inside the next N trading sessions = anticipatory "position-build window" signal.

Different time horizon from EP / 9M (which fire reactively after the gap):

| Surface | Fires | Decision |
|---|---|---|
| Flag scanner (existing V0) | Base is tight | "Watch for breakout" |
| EP / 9M (existing) | After gap | "Day 2 ORB entry?" |
| **Convergence (this)** | Pre-catalyst, while basing | "Position-build window?" |

The convergence detector adds the catalyst dimension to existing base detection — earnings is V1, FDA / lock-up / index reconstitution / investor days are V2+.

## Universe / eligibility

- Stages: TIGHTENING + COILED (drop WATCH = too noisy ~50/day; drop TRIGGERED = catalyst is old news once price has moved)
- N-session window: 7 trading days (configurable)
- M&A pre-filter via existing `is_likely_ma()` SSoT (CLAUDE.md 2026-05-04)

## Detection criteria (V1 spec)

NOT IMPLEMENTED YET. Spec locked 2026-05-08 per user rulings — see spike memo for detailed scope, plugin architecture, and 9-step code work order.

V1 catalyst source: earnings via existing `is_earnings_day` (yfinance backstop).

V2+ catalyst sources (gated on V1 outcome data):
- FDA / PDUFA dates (biotech-specific, biggest single-event reactions)
- Lock-up expiry (post-IPO, SEC filings)
- Index reconstitution (S&P / Russell schedules)
- Investor days / conferences (manual / IR pages)

Out of scope: macro events (CPI, FOMC, jobs reports — not ticker-specific), open-ended rumors, sympathy plays.

## Stage transitions

NOT IMPLEMENTED YET. V1 will write rows to `mi_convergence_candidates` (proposed schema in spike memo) with `(ticker, scan_date, base_stage, catalyst_type, catalyst_date, sessions_to_catalyst, confidence, source_name)`.

## Known limitations / open questions

7 open questions from spike memo (Q1-Q5 ruled by user 2026-05-08; Q6-Q7 added by advisor; all 7 resolved):
- Q1 reservation accounting: NO re-allocation within morning wave
- Q2 tie-breaking: pm_rvol → gap → strategy priority (MAGNA53 > 9M > Flag)
- Q3 manual override: TV webhooks bypass
- Q4 allocator failure: FCFS fallback + Telegram warning
- Q5 cron architecture: shared queue (mi_pending_allocations) with strategies still emitting
- Q6 price freshness: HARD gate at >1.5% past trigger
- Q7 intraday slot re-allocation: re-runnable on stop-out / full-exit events

Spike-before-code item: simulate against 5/07 paper data — would the allocator have picked FTNT, AAON, HIMX over the 9M Day 2 sugar babies? Run before writing the allocator code.

## Change log (newest first)

### 2026-05-08 — Cross-strategy ranking spec locked (related but separate concern)

This is recorded here because the convergence detector's V2+ planning intersects with the cross-strategy ranking question. See `~/.claude/plans/cross-strategy-ranking-spike.md` for the locked spec. Not a change to the convergence setup itself; tracking for cross-reference.

### 2026-05-08 — Generalized scope from earnings-only to multi-catalyst

**Trigger**: User feedback during memo review — "this is a specific instance of a bigger pattern; these are basically a basing pattern and this instance is convergence with earnings expectation, but other instances the catalyst may be something else and not earnings."

**Evidence**: User framing.

**Anticipated effect**: V1 ships earnings as the first catalyst source. Architecture supports plugin-shaped expansion (V2+ = FDA, lock-up, etc.) without engine rewrite.

**Reversion-flag**: REFINEMENT of original 5/07 spike scope.

**Status**: spike memo updated. Code not started.

### 2026-05-07 — Initial spike memo

**Trigger**: Wave D #8 from 5/06 paper-session triage.

**Evidence**: Conceptual + cross-references to flag scanner (V0), is_earnings_day, ma_filter SSoT, Friday Watchlist two-depth pattern as architectural precedent.

**Status**: spike memo written. Implementation pending user sign-off on 5 open questions and the spike-before-code simulation.

---

V1 implementation effort: 8-10 hr (per locked spec). Phase=shadow on first ship. Promotion criteria per-catalyst-type defined in spike memo.
