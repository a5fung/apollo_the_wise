# ADR 0001 — Dynamic per-strategy parameter tuning from observed R-expectancy

**Status:** Design memo (not yet implemented). Task #67.
**Date:** 2026-05-13
**Context window:** Post-2026-05-23 live-cutover; preconditions on N≥10 paper R-expectancy cohort (#63), drawdown breaker promotion (#40), and dual-account stability (#66 verified).

---

## Problem

Today's per-strategy parameters (`position_size_multiplier`, `max_concurrent_positions`) on `mi_strategies` are operator-set constants. They start at conservative values (e.g. `9m_day2: multiplier=0.5, cap=2`) at live cutover and never change unless the operator manually `UPDATE`s the row.

This is the right shape for cutover Day 1 (we don't trust live-$ performance yet). But it's wrong for steady-state operation: as paper / live R-expectancy data accumulates, the parameters should respond — strategies that demonstrate edge get more capital, strategies that degrade get less. Manually retuning every ~weekly review is operator overhead AND lags the signal.

The proposal is a closed-loop tuning system that consumes observed R-expectancy + drawdown telemetry and adjusts per-strategy params within bounded guardrails.

---

## Non-goals

- **Auto-promoting strategies between phases** (shadow→paper→live). That's a separate decision with higher consequences; promotion model already exists (`promotion_thresholds`) and stays operator-gated.
- **Cross-strategy capital allocation** (Phase 1B allocator, #44). Different problem layer — that picks WHICH candidate to enter when N candidates compete; this picks HOW MUCH each strategy can hold in steady state.
- **Tuning detection criteria** (RVOL gates, ATR thresholds, etc.). Methodology changes go through sample-size discipline + advisor review; this memo is only about position sizing + slot allocation.

---

## Inputs (already computed)

| Signal | Source | Freshness |
|---|---|---|
| Per-strategy R-distribution | `mi_live_trades.total_pnl / risk_dollars` grouped by `signal_type`, last N closed | Continuous |
| Per-strategy win rate | Same grouping, `total_pnl > 0` ratio | Continuous |
| Per-strategy max drawdown (rolling 30d) | `mi_account_equity_snapshots` partitioned by strategy contribution OR per-strategy closed-trade equity curve | Daily 16:12 ET |
| Per-mode account equity | `mi_account_equity_snapshots` | Daily |
| Drawdown breaker state per mode | `mi_safeguard_state` | Daily |

Everything needed already exists. The new code is just a tuning function + a job that runs it.

---

## Proposed mechanism

### Tuning function

```python
def compute_target_params(strategy_id, observations):
    """
    observations = dict with:
      n_closed: int       (rolling window, e.g. last 30 closed)
      median_r: float
      win_rate: float
      max_dd_pct: float   (peak-to-trough on strategy's own closed-trade equity curve)
      n_days_active: int  (how long this strategy has been at current phase)

    Returns: dict with (position_size_multiplier, max_concurrent_positions)
    """
```

**Decision tree** (deliberately conservative; tunable bounds in code, not magic numbers):

| Condition | Action |
|---|---|
| `n_closed < 10` | No change (cold start — under sample-size discipline) |
| `median_r >= 1.0 AND win_rate >= 0.40 AND max_dd_pct >= -0.10` (strong) | +0.1 multiplier, +1 cap (within MAX bounds) |
| `0.5 <= median_r < 1.0 AND win_rate >= 0.35 AND max_dd_pct >= -0.15` (acceptable) | No change — current params are right-sized |
| `0 <= median_r < 0.5 OR win_rate < 0.30` (weak) | -0.1 multiplier (within MIN bounds), cap unchanged |
| `median_r < 0 OR max_dd_pct < -0.20` (degraded) | Multiplier → 0.5, cap → 1, emit `strategy_tuning_degraded` audit event for operator review |

### Bounds

- `position_size_multiplier ∈ [0.25, 2.0]` — never below 25% of risk-per-trade baseline (that's structural noise floor) and never above 2× (compounding bias).
- `max_concurrent_positions ∈ [1, MAX_CONCURRENT_LIVE_POSITIONS]` (global cap is hard ceiling).
- Cooldown between auto-tunes: `≥ 7 days per strategy`. Prevents oscillation around the median.

### Job

`scheduler.py::_strategy_tuning_job` at 16:20 ET (after equity snapshot at 16:12 + post-EOD audit at 16:15):

1. For each strategy with `phase IN ('paper', 'live')`:
   - Query observations (asyncpg, single roll-up over `mi_live_trades` partitioned by `signal_type`).
   - Skip if `n_closed < 10` (sample-size gate).
   - Skip if `now - last_auto_tune_at < 7 days` (cooldown gate).
   - Compute target_params.
   - If different from current → UPDATE mi_strategies + log `strategy_auto_tuned` audit event with from/to.
2. Emit summary to `mi_audit_log`: count tuned, count unchanged, count skipped (cold start / cooldown).

### Surface

- **Weekly digest** appendix: "🎛️ *Strategy tuning (last 7d):*" — one line per strategy showing latest tuning decision + rationale snippet.
- **Telegram** on degradation: when a strategy hits the "degraded" branch, emit immediate Telegram alert (this is the operator-visible safety net).
- **`/strategy <id>`** existing command extended to show `auto_tuning: enabled | disabled` and last tuning event.

### Opt-out

`mi_strategies.auto_tuning_enabled BOOLEAN DEFAULT FALSE`. Default OFF for every strategy until operator explicitly opts in via `/strategy <id> enable-auto-tuning`. Single per-strategy switch; revert at any time.

---

## What this prevents

1. **Compounding losses on a degrading strategy** — drawdown-side branch caps multiplier at 0.5 and slot count at 1 the day after a -20% strategy-attributable drawdown fires. Operator gets a Telegram immediately; doesn't have to be watching to catch the bleed.
2. **Under-sized winners** — strategies that consistently deliver R≥1.0 ramp organically without operator memory burden ("did I bump 9m_day2 last week?").
3. **Operator overhead** — eliminates the "should I retune this week?" loop in every weekly review.

## What it deliberately does NOT do

1. Touch detection criteria, gate thresholds, or risk-per-trade calculation. Those stay operator-controlled methodology decisions.
2. Auto-promote phases. Phase changes ship real-money exposure; that's an operator decision tied to the live-cutover composite gate.
3. Cross-strategy reallocation. If strategy A is winning and strategy B is degrading, this tunes each independently — it doesn't shift slot count from B to A. Cross-strategy allocation is #44 territory.

---

## Implementation order (when this graduates from memo to build)

1. **Schema**: ALTER `mi_strategies` ADD COLUMNS `auto_tuning_enabled BOOL DEFAULT FALSE`, `last_auto_tune_at TIMESTAMPTZ`, `last_auto_tune_reason TEXT`.
2. **Strategy-attributed equity curve query**: helper that returns the per-strategy max drawdown over a rolling window. This is the trickiest part — `mi_account_equity_snapshots` is per-account, not per-strategy. Either (a) compute strategy-attributed equity from closed-trade P&L cumsum (simpler, ignores unrealized — biased toward measuring realized losses), or (b) tag each `mi_live_trades` row's contribution to daily equity at close (more accurate but bigger schema change). Recommend (a) for v1; revisit if false positives accumulate.
3. **`compute_target_params` function** + unit tests (table-driven cases for each branch).
4. **`_strategy_tuning_job` scheduler hook** at 16:20 ET, audit events.
5. **`/strategy` command extension** to surface tuning state.
6. **Weekly digest appendix** in `system_review.py`.
7. **Opt-in for one strategy first** (likely `magna53` since it has the most history) for 30 days; review tuning decisions before opt-in for `9m_day2`.

## When to start

**Pre-conditions** before any code lands on this:
- Live cutover composite gate (#64) GREEN — at least one strategy operating in `phase='live'` with `live_real_enabled=True` for ≥ 14 days.
- ≥ 30 closed live trades total across all strategies — enough that per-strategy buckets have N ≥ 10.
- Drawdown breaker promoted to active phase (#40) — important because the tuning function depends on accurate drawdown signals, and those depend on the breaker's state machine being battle-tested.

Earliest realistic start window: **~2026-06-15** (3-4 weeks post earliest cutover date 2026-05-23, assuming nothing slips).

## Risks

- **Step-function instability**: the "degraded" branch slamming a strategy from multiplier=1.0 → 0.5 in one day could cause its own discontinuity. Mitigation: cap per-tuning delta to ±0.2 multiplier per cycle except for the degraded branch (which is a safety override, not a tuning step).
- **Goodhart's law on R-expectancy**: optimizing for median R can incentivize trades that mechanically reach +1R via early partial exits, sacrificing the right-tail. Mitigation: track both median R and right-tail metric (e.g. P90 R-multiple) in observations; trigger operator review (not auto-tune) if median grows but P90 collapses.
- **Strategy-attributed drawdown miscount**: per-strategy equity curves via closed-trade cumsum (option (a) above) ignore unrealized P&L on open positions. A strategy with chronic open losers but periodic closed winners can look fine to the tuner while bleeding hard. Mitigation: include the strategy's currently-open-position MTM in the rolling drawdown calc (cheap query against Alpaca `get_position(symbol)` per open ticker).

## Open questions for advisor review (when build starts)

1. Should the tuning function be deterministic-table-driven (as drafted here) or learned (regression on observations → params)? Drafted version is auditable; learned version is more adaptive but harder to reason about. Recommend deterministic for v1, revisit if v1 over-tunes or under-tunes systematically.
2. Should `position_size_multiplier` decisions decouple from `max_concurrent_positions` decisions (independent branches) vs joint optimization? Drafted version is joint per-branch.
3. Cooldown of 7 days — is this right? Faster (e.g. 3 days) responds to regime changes; slower (14 days) suppresses noise. Drafted at 7 for balance.

---

## Filed as task #67. Not graduating to build until pre-conditions above are satisfied.
