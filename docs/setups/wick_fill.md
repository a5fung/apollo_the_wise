# Wick-Fill / Negated Shooting Star

**Phase**: Telemetry (Stage 1). Promotion path: `telemetry_review`.
**Origin**: Kristjan Kullamägi / Pradeep Bonde — when a 9M day closes mid-range with a green body and the upper wick traps shorts, the next-day break of `prior_high` becomes the canonical short-cover impulse.
**Code**: `agents/market_intelligence/wick_tracker.py`, EOD sweep called from ninem_detector.

## Definition

A 9M-quality day where the close lands in the middle of the intraday range (cirp 0.50-0.75) with a green body. The upper wick represents trapped shorts who sold the highs; when prior_high breaks the next day, those shorts cover — providing alpha through a different mechanism than the standard 9M continuation.

## Universe / eligibility

- Same gates as Sugar Baby (mirrors `_NINEM_CONTEXT_CTE`):
  - price ≥ $5
  - dollar_vol ≥ $50M
  - volume ≥ 3 × ADV
  - range ≥ 2%
  - extension cap (prev_close ≤ 1.20× MA-10)
  - **net_up ≥ 3%** (categorical breakout, not just close > open)
- Range-position differs: cirp ∈ [0.50, 0.75) (vs sugar baby's ≥ 0.75 close-in-top-quartile)

## Detection criteria (current)

EOD sweep gates (mirrors sugar baby + range-position):
- All Sugar Baby qualifying gates (price/vol/extension/etc.)
- close in [0.50, 0.75) of intraday range (`(close - low) / (high - low)`)

If passes → row written to `mi_wick_candidates`.

### Two-anchor forward returns

- `fwd_{1,3,10}d_from_high_pct` (conditional on fill = price subsequently breaks `prior_high`)
- `fwd_{1,3,10}d_from_close_pct` (unconditional — measures Day 1 close baseline)

The gap between these medians at the 3-day horizon is the strategy's edge in one number.

### Settlement job

`_wick_forward_returns_job` runs 5:35 PM ET cron, walks unsettled rows. Intentionally NOT gated by `should_run('wick_fill')` so in-flight telemetry survives mid-cycle disable.

## Known limitations / open questions

1. **Stop geometry differs from Sugar Baby** (CLAUDE.md TI2 entry): stop = Day 1 close, NOT Day 1 low. Separate order-management path needed when promoted to paper. Filed as productionization concern.

2. **Short-squeeze fake-outs**: common slippage problem on this setup type. Slippage controls TBD before paper.

3. **Promotion eligibility**: `n_candidates ≥ 30 AND fill_rate ≥ 0.50`. Currently insufficient sample.

## Change log (newest first)

### 2026-04-28 — Initial Stage 1 ship

**Trigger**: TI2 in `project_trading_ideas_backlog.md`. First strategy through the Strategy Maturity Framework.

**Evidence**: Verified backfill on POET 2026-04-21 (cirp=0.602, green, net +19.3%, vol_ratio 4.7×, dollar_vol $606M). Day 2 (4/22) high $12.95 broke prior_high $11.09 — wick filled day 1, continued +40% by 4/24.

**Anticipated effect**: candidates accumulate in `mi_wick_candidates`. Forward returns settle T+10. Eligibility flag at n≥30 + fill_rate ≥ 0.50.

**Status**: shipped (CLAUDE.md). Phase=telemetry; no entry pipeline.

---

This setup has had no changes since initial ship. Will backfill any prior history (universe gate edits, etc.) as touched.
