# #271 — CLASS B breadth (Pradeep 20%-in-5d thrust): metric computed + calibrated (gate-free)

**Status: ANALYSIS DONE 2026-06-14 (gate-free). The missing CLASS B metric feed is computed,
calibrated, and validated against Pradeep's 5/24 anchor. The deployable wiring (feed in
`regime.py::calculate_breadth_full` + `class_b_color()` in `breadth_color_rules.py` + the
`/breadth`/briefing cell) touches `combined`-deployed code → GATED post-#277, same discipline as
#270 step 3 / #258 step 2.** Read-only analysis: `scripts/_271_breadth_classb.sql` + `_271_analyze.py`.

## The gap

`breadth_color_rules.py` *describes* CLASS B — "unpaired thrust (up 20%+/5d alone) = amber
exhaustion (Pradeep 2026-05-24 SPY annotation)" — but, unlike CLASS A/C/D, ships **no
`class_b_color()` function and no metric feed**. `regime.py::calculate_breadth_full` computes the
A/C/D feeds but never the 5-day ±20% thrust count. #271 = compute the feed + add the color rule.

## Altitude (advisor 6/14): CLASS B is a DISPLAY ANNOTATION, not a trade gate

A/C/D are colored breadth cells with **convention** thresholds (T2108's 20/85 are Stockbee
convention, never backtested in this repo). CLASS B is a sibling annotation. So the bar is:
compute the metric, show the distribution, set a sensible extreme threshold, confirm it lights on
Pradeep's anchor — **NOT a forward-return P&L backtest** (extremes are rare → N tiny; the
sample-size discipline governs *trade-gating* criteria, not a breadth cell). Building CLASS B to a
standard its three shipped siblings never met would be the wrong altitude.

## Metric

Per trading day, count common stocks (CS/ADRC or unknown, the `COMMON_STOCK_TYPES` filter
regime.py already uses) whose **5-trading-day return ≥ +20%** (up-thrust / exhaustion side) and
**≤ −20%** (down-thrust / washout side). Corporate-action guard: drop |5d| > 200% / < −90%
(splits). **$5 price floor** (Pradeep's thrust = real names, not a $1→$1.20 penny pop — advisor).

## Calibration (269 trading days, 2025-05-19 .. 2026-06-12)

**Count vs %: normalize to % of universe.** Universe drifts min 5078 / median 5493 / max 5627 =
**10% spread** — enough that a raw count would mean different things at the ends of the window. So
the metric is **% of universe** (Pradeep's raw count is shown alongside for familiarity).

**Distribution ($5-floor, % of universe):**

| side | p50 | p90 | p95 | p99 | max |
|---|---|---|---|---|---|
| UP20 (exhaustion) | 1.6% | **2.7%** | 3.0% | 4.3% | 4.5% |
| DOWN20 (washout) | 0.9% | **1.8%** | 2.4% | 3.3% | 4.7% |

**Proposed CONVENTION thresholds (p90, tunable like T2108's 20/85):**
`AMBER (exhaustion) up20_$5 ≥ 2.7% of universe` · `GREEN (washout) down20_$5 ≥ 1.8%`. p90 lights
~10% of days — the right cadence for an "extreme" cell.

## Two-directional BY CONSTRUCTION (no transition-state detector — advisor)

"Post-washout rally-watch" **is the down-thrust-high reading itself** — washout present = oversold
setup = green, exactly as T2108-low = green. No stateful "washout-then-clearing" rule (that would
overfit the handful of washout episodes 13 months supplies). Two fields, two thresholds, two
colors, zero state — `class_b_color` is a clone of `t2108_color`.

## Validation — Pradeep's 5/24 anchor (the only validation an annotation needs)

The up-thrust ramped into late May 2026 and **lights AMBER 5/26–5/29**, peaking 5/27:

```
2026-05-21  up20_$5  1.0%      2026-05-27  up20_$5  4.3%  <- AMBER (p99, #3 day in 13mo)
2026-05-22  up20_$5  1.9%      2026-05-28  up20_$5  3.8%  <- AMBER
2026-05-26  up20_$5  2.9% <-A  2026-05-29  up20_$5  2.8%  <- AMBER
```

Pradeep annotated the building exhaustion on 5/24; the metric peaks at an extreme right after =
the cell captures exactly what he flagged. Face-validity on the extremes: up-thrust peaks =
post-pullback rips (2025-11-28, 2026-04-17, 2026-05-27); washout peaks = selloffs (2026-02-05 at
4.7% = the biggest washout in the series; the Nov-2025 correction cluster).

## Turnkey wiring spec (GATED post-#277 — touches `combined`)

**1. The color rule** — add to `breadth_color_rules.py` (mirrors `t2108_color`, pure/stateless):

```python
# CLASS B thresholds (SSoT) — $5-floor count as % of universe, p90 convention (tunable)
CLASS_B_UP_EXHAUSTION = 2.7    # up>=20%/5d ($5) % of universe: >= -> amber (exhaustion)
CLASS_B_DOWN_WASHOUT  = 1.8    # down>=20%/5d ($5) % of universe: >= -> green (washout setup)

def class_b_color(up_20_5d_pct: Optional[float], down_20_5d_pct: Optional[float]) -> str:
    """CLASS B unpaired-thrust color (clone of t2108_color — pure, stateless, convention
    thresholds). Up-thrust extreme -> amber (Pradeep exhaustion); down-thrust extreme (washout)
    -> green (oversold setup = the 'post-washout rally-watch', the reading itself, no transition
    state). Two-directional by construction; up side wins if both somehow extreme."""
    if up_20_5d_pct is not None and up_20_5d_pct >= CLASS_B_UP_EXHAUSTION:
        return CAUTION
    if down_20_5d_pct is not None and down_20_5d_pct >= CLASS_B_DOWN_WASHOUT:
        return BULL
    return NEUTRAL
```

**2. The feed** — in `regime.py::calculate_breadth_full`, piggyback on the closes already pulled
for the 4% ratios (it fetches the last 11 trade_dates into `closes_by_ticker`; the 5-day window is
a subset — NO second query). Compute per common stock with `close >= 5`: `r5 = close[trade_dates[-1]]
/ close[trade_dates[-6]] - 1`, drop `r5 > 2.0 or r5 < -0.9` (splits); count `r5 >= 0.20` (up) and
`r5 <= -0.20` (down); store `up_20_5d`, `down_20_5d`, and the `_pct` (÷ universe ×100) in the
`breadth_monitor` dict.

**3. The cell** — render the CLASS B cell (amber/green/neutral via `class_b_color(up_pct, down_pct)`)
in the evening briefing breadth block + the `/breadth` command, alongside A/C/D.

**Acceptance:** the nightly regime job writes `up_20_5d`/`down_20_5d` to `breadth_monitor`;
`/breadth` shows the CLASS B cell; a backfill spot-check reproduces AMBER on 2026-05-27.

## Gate

The SQL + analyze script + this doc are read-only = gate-free. The wiring (feed + color rule +
cell) runs in `combined` (nightly regime job + a briefing/Telegram surface) = GATED post-#277.
Branch + verify, merge post-gate. It is a **display annotation**, so it ships independent of any
trade-gating evidence (#271 is in the 6/22 launch DoD's "detector cluster in shadow", but CLASS B
is observational from day one — no sizing/live decision rides it).
