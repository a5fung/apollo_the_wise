# ADR 0002 — TI5 v1: Mid-Range Continuation detector (shadow ship)

**Status:** Design memo (not yet built). Task #55.
**Date:** 2026-05-13
**Source:** TI5 v0 explorer findings (180d, 302 settled HIGH/MODERATE EP alerts).

---

## v0 findings (the headline)

180-day cohort, 302 alerts, T+10 horizon, R = (price − anchor_close) / (anchor_close − anchor_low):

| Bucket | n | stop% | medMaxR | exp_3R | PF | WR3R |
|---|---|---|---|---|---|---|
| `strong_close_continuation` (9M Day 2 sugar baby cohort) | 31 | 45.2% | +0.93R | +0.06R | 1.11 | 35.5% |
| `strong_close_fade` | 36 | 77.8% | +0.21R | -0.79R | 0.05 | 11.1% |
| **`mid_range_continuation` ★** | **46** | **28.3%** | **+3.14R** | **+1.60R** | **7.98** | **73.9%** |
| `mid_range_fade` | 46 | 91.3% | +0.00R | -0.87R | 0.05 | 6.5% |
| `weak_close_continuation` | 48 | 77.1% | +0.00R | +0.04R | 1.06 | 29.2% |
| `weak_close_fade` | 63 | 100.0% | +0.00R | -0.87R | 0.10 | 3.2% |

Baseline (all 301 settled at T+5): -0.15R exp_3R, PF 0.78.

**Sanity gate** (per TI5 memo): ≥30 anchors per bucket, ≥200 total. Both cleared.
**Decision rule** (per TI5 memo): medMaxR ≥ 3R AND exp_3R ≥ +0.5R AND n ≥ 30. Mid-range-continuation passes cleanly at T+10 (+3.14R / +1.60R / n=46).

**Secondary observation worth noting:** weak_close_fade is the inverse signal — 100% stop rate, -0.87R exp_3R, n=63. That's a clean short-side cohort but Apollo doesn't currently trade short (TI1 parabolic-short is the only short framework and it's still in shadow). Defer.

---

## Problem this solves

The user's original FTNT case study (5/7 HIGH EP score 96, +6% follow-through 5/8 with mid-range close) wasn't captured by any existing detector:
- Not strong-close → 9M Day 2 sugar baby missed it (cir<0.75 floor).
- No undercut → Fishhook v3 missed it.
- No base → Continuation Flag missed it.

The v0 data confirms FTNT wasn't a one-off — there's a *systematic* bucket of 46 alerts in 180d where mid-range close on an EP day continues with positive R-expectancy. The current detector stack has a gap where this entire bucket lives.

---

## Proposed detector

### Trigger criteria (deterministic, Day-2 anchored)

Day 1 = EP alert day. Detector fires Day 2.

| Gate | Threshold | Source |
|---|---|---|
| Day-1 was HIGH or MODERATE EP alert | `mi_ep_alerts.score_tier IN ('HIGH', 'MODERATE')` | Existing |
| Day-1 close-in-range | `0.4 ≤ cir < 0.75` | Same helper as 9M sugar baby `_close_in_range_pct` |
| Day-1 green | `close > open` AND `close ≥ prev_close × 1.03` | Matches 9M sugar baby net-up floor |
| Day-1 not stop-tagged | `low ≥ anchor_low candidate` (no anchor breach) | mi_daily_closes |
| Day-1 not extended | `prev_close ≤ 1.20 × SMA-10` | Same extension gate as 9M sugar baby |
| Day-1 not M&A | `NOT is_likely_ma(ticker)` | Existing ma_filter |
| Day-1 not climax | `parabolic_short.is_climax == False` if scanned | Existing parabolic detector |

### Entry on Day 2

Standard ORB entry mechanics (same plumbing as 9M Day 2 + MAGNA53):
- Stop-buy at `anchor_high` (Day-1 high)
- Stop-loss at `anchor_low` (Day-1 low) — matches v0 explorer's R basis
- 9:31 ET entry submission window
- 10:00 ET cleanup cancels unfilled

### Exit policy

Per Qullamaggie methodology + v0 findings (medMaxR=+3.14R at T+10 ≫ exp_3R=+1.60R):

- **Partial at +3R** (50% off): captures the bulk of the expectancy.
- **Trail remainder behind SMA-10** on close basis: lets the right-tail run. v0 max-favorable distribution suggests winners reach +5R / +10R territory; SMA-10 trail catches those without giving back the +3R already booked.
- **Time-stop at T+15** if not stopped or trailed by then: prevents indefinite holds.

### Schema

Reuse `mi_paper_trades` / `mi_live_trades` with `signal_type='mid_range_cont'`. New strategy row:
```sql
INSERT INTO mi_strategies (strategy_id, name, family, phase, signal_type,
    outcomes_table, promotion_model, promotion_thresholds, position_size_multiplier,
    max_concurrent_positions)
VALUES ('mid_range_cont', 'Mid-Range Continuation', 'orb_long', 'shadow',
    'mid_range_cont', 'mi_live_trades', 'unpaired_r', '{
      "shadow_to_paper": {"min_closed": 30, "min_median_r": 0.5, "max_drawdown_pct": 0.30},
      "paper_to_live":   {"min_closed": 30, "min_median_r": 0.5, "min_win_rate": 0.40,
                          "max_drawdown_dollars": 5000}
    }', 0.5, 2);
```

Multiplier 0.5 + cap 2 = same conservative bias 9M Day 2 ships with. Promote on demonstrated edge.

### Telegram + audit surfaces

- New `_handle_mid_range_query` in agent.py for `/midrange` slash. Mirrors `/9m` shape (today's candidates + recent outcomes).
- Evening briefing line: "🎯 Mid-Range Continuation: N candidates for tomorrow's Day 2 ORB."
- Weekly digest: per-strategy R-expectancy table includes new row once n_closed ≥ 5.

---

## What this is NOT

- **Not a methodology change to existing detectors.** 9M Day 2 sugar baby keeps its 0.75 close-in-range floor (that's its bucket). Fishhook keeps its undercut requirement. Flag keeps its base requirement. This adds a NEW signal type to the orb_long family; existing detectors are untouched.
- **Not real-money on Day 1.** Phase = shadow. Telegram surfaces candidates; no Alpaca orders submitted. Promotion to paper requires the documented `promotion_thresholds`.
- **Not a refactor of the EP cohort.** Reuses `mi_ep_alerts` rows directly. No new daily scan tier.
- **Not coupled to the v0 explorer script.** Explorer was a one-shot exploration; v1 detector reads live EP alerts and computes its gates per-bar.

---

## Risk: small-sample bucket size

n=46 at T+10 is above the documented sanity floor (30) but it's still a modest sample. The +3.14R medMax / +1.60R exp_3R is striking enough that I trust the directional signal, but the *magnitude* may regress in live.

Mitigation: ship as shadow with full telemetry; the strategy registry's promotion model gates paper→live on 30 *fresh* closed shadow trades. If the magnitude regresses we'll see it in the shadow cohort before any capital is at risk.

## Risk: the FTNT-class names overlap with existing MAGNA53 / 9M Day 2 entries

The v0 explorer treated every HIGH/MODERATE EP as an anchor regardless of whether it became a trade. Some of the 46 mid-range-continuation rows were probably already entered via MAGNA53 (Day-1 ORB) — different entry timing, different stop. v1 detector fires Day 2 like 9M Day 2 does; the question is whether mid-range-continuation Day-2 entries CONFLICT with MAGNA53 Day-1 entries that are already in the position.

Mitigation: existing `BLOCK_TICKER_OPEN_POSITION` safeguard prevents same-ticker duplicates within the same account_mode. So if MAGNA53 took the trade Day 1, mid-range-continuation will be blocked Day 2 — natural deduplication, no new gate needed.

## Risk: Day-2 entry on a Day-1 gap-down to close-in-range

The v0 bucket `mid_range_continuation` selected on Day-1 cir ∈ [0.4, 0.75) AND green close. A green close on a gap-down day is rare but possible (gap −5%, intraday recovery to close at -1%, cir 0.55). That's structurally different from a gap-up that closes mid-range — same cir but very different setup.

Mitigation: add explicit gate `gap_pct ≥ 0` (no Day-1 gap-downs admitted). Doesn't lose data — v0 baseline included gap-downs but the 9M sugar baby methodology only admits gap-ups anyway, so the v1 detector mirrors that.

---

## Implementation order (when this graduates from memo to build)

1. **Strategy registry seed** for `mid_range_cont`, phase=shadow.
2. **Detector** `agents/market_intelligence/mid_range_continuation_detector.py`. Mirrors `ninem_detector.py` Day 2 pattern. Functions: `compute_day1_shape_primitives(ticker, date)`, `get_eod_mid_range_candidates(date)`, `run_mid_range_sweep()`.
3. **Day-2 ORB plumbing**: reuse `prepare_orb_order` / `submit_trade_entry` from `entry_pipeline.py` with `signal_type='mid_range_cont'`. Spec builder identical to 9M Day 2 (anchor_high entry, anchor_low stop, ORB-time submission window).
4. **Scheduler**: EOD sweep slot in nightly_data_pull (alongside 9M sugar baby write). Day-2 entry happens via the existing 9:31 ET ORB monitor — no new entry-side cron.
5. **Audit + Telegram surfaces**: `/midrange` command, evening briefing line, weekly review R-row.
6. **Setups SSoT**: `docs/setups/mid_range_continuation.md` with the criteria + v0 evidence + change-log header (per CHANGE_PROCESS.md).
7. **Preflight smoke**: add to scripts/preflight_check.py — once strategy is enabled in shadow phase, preflight should NOT exercise it (shadow phase is skipped anyway).
8. **Backtest sanity**: run scripts/orb_sim_filtered_candidates.py or similar against the 46 v0 hits to confirm the Day-2 ORB mechanics would have captured the +1.60R expectancy. Failure here = the v0 R math is theoretical, ORB mechanics in practice eat the edge. Decision blocker before shadow ship.

### Estimated effort: ~5-7 hr.

---

## When to start

**Pre-conditions** (relatively light — this is shadow ship):
- Live cutover decision (#64) does NOT block this. Shadow ships alongside live-cutover work; they're independent.
- TI5 v0 explorer findings reviewed (done — this memo IS the review).
- Step 8 (Day-2 ORB backtest against v0 hits) passes — i.e., the +1.60R expectancy actually survives ORB-mechanics friction.

**Recommended start**: post live-cutover (after 5/23) to reduce concurrent change surface during the cutover window. Cutover risk is high; adding a new detector mid-cutover muddies attribution of any surprise behavior.

**Realistic ship date**: late May / early June 2026.

---

## Filed as task #55. Promotes from memo to build when (a) live cutover is resolved AND (b) Day-2 ORB backtest confirms the v0 expectancy survives execution mechanics.
