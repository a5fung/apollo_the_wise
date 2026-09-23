# #170 C1 — EP cooldown re-setup admission backtest (Lane-1 pre-build, 2026-07-11)

**Question:** re-admit EP names currently suppressed by the ~60d cooldown when they re-gap
"freshly enough"? The design's proposed rule = **days_since ≥ 10 AND gap ≥ 15%**
(`docs/analysis/170_cooldown_resetup_design_2026-07-11.md`). Probe: `scripts/probes/_170_resetup_backtest.py`.
Cohort = cooldown-suppressed scan-log ticker-days (deduped, max gap), days_since computed vs the
most-recent prior EP alert, forward = 5d-max-high % from the scan-day close, winner ≥ +10%.
Read-only.

## The table (N=89 cooldown-suppressed ticker-days with a forward path)

**Baseline — all cooldown-suppressed (the do-nothing pool): mean +13.7% · median +7.3% · win 42%.**

Admitted cohort by (days_since ≥ D) × (gap ≥ G):

| | gap ≥12% | gap ≥15% | gap ≥20% |
|---|---|---|---|
| days≥7 | n=37 +8.5% / 41% | n=19 +6.8% / 32% | n=4 +9.3% / 75% |
| days≥10 | n=33 +8.1% / 39% | **n=17 +6.7% / 35%** | n=4 +9.3% / 75% |
| days≥14 | n=29 +8.5% / 41% | n=14 +6.5% / 36% | n=4 +9.3% / 75% |

*(cell = mean fwd-max / win≥10%; bold = the proposed headline rule.)*

## The read → NO-GO (the admitted cohort isn't tradeable)

1. **The admitted cohort is R-negative once settled.** Headline cell (days≥10 & gap≥15) = +5.6%
   median *forward-max* — and forward-max is an upper bound (no stop, perfect exit). Settled
   through a real stop (cf. #290, where a +0.3R forward-max window settled clearly negative), a
   +5.6% median cohort is R-negative. There is no tradeable edge in the cell we'd admit.
2. **It underperforms the live EP book we ALREADY trade.** Same metric, same window: non-member
   EP HIGH alerts (#357 table) = +7.4% median / 40% win; the #170 admitted cohort = +5.6% / 35%.
   Re-admitting these names *dilutes* the EP book rather than adding to it — the strongest single
   argument, because it's a like-for-like comparison against a known baseline.
3. **The gap filter is anti-selective** (why #2 happens): gap≥12 beats gap≥15 across the grid — a
   BIGGER re-gap after a cooldown means MORE exhaustion, less forward juice, the opposite of the
   rule's premise. days_since is flat (7/10/14 all ~+8%): no signal. The gap≥20/75%-win cell is
   N=4 noise.
4. **The 6/01 backward-check does not replicate.** That check reported +17% median vs +8.8%
   (N=22 at gap≥15) using the SAME forward-max metric; the current full-history pull puts the same
   cell at +5.6%. Cohort boundaries differ (its ~22 vs this 17 at the cell — different dedup/date
   window), so this is "the effect doesn't hold under the current cohort," not proof the prior math
   was wrong — but the CHANGE_PROCESS N≥10 gate is exactly why we re-confirm before shipping, and
   it didn't confirm.

*(Footnote — the all-suppressed baseline is +13.7% / 42%, above every admitted cell; but you'd
never re-admit the whole pool, so that comparison only demonstrates the filter's anti-selectivity,
not profitability. Attrition is clean: 104 deduped cooldown ticker-days → 89 usable (86%); zero
lost to missing price data, so no liquidity skew.)*

## Recommendation for the sitting

- **NO-GO on the days≥10 & gap≥15 admission rule** — it selects the exhausted tail, not fresh
  re-setups. Do not weaken the cooldown on this basis.
- **If the operator still wants a re-admission path**, it needs a DIFFERENT discriminator than
  gap-size (the design's "fresh catalyst" arm — a NEW distinct catalyst since the prior alert,
  not merely a re-gap). That's a data-sourcing task (catalyst dedup), not a threshold — file as a
  redesign, don't ship the threshold.
- The cooldown stays as-is (no money-path change). This probe is the evidence to keep it.

*Feeds #170. The 60d cooldown is a suppression heuristic, not a safeguard — but leave it; the
evidence says it's protecting us from the exhausted-re-gap tail.*
