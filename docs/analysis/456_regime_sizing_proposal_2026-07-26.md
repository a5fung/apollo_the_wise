# #456 DoD(a) — Regime-keyed position sizing (replace VIX-scaled) — PROPOSAL, 2026-07-26

**Status: WRITTEN PROPOSAL ONLY.** No code, constant, config, or DB row changed. Position
sizing = real money = operator's sole authority (THE LINE). Ships only after operator
sign-off per `docs/setups/CHANGE_PROCESS.md` (read in full for this card, as was
`docs/setups/safeguards.md`).

**Trigger:** operator ruling 2026-07-26 — "fix it, but vix shouldn't be the thing that
controls sizing, we have a full regime" + "this is critical given that we are in correction
regime right now." Prod confirms the premise: `mi_market_regime` = **Correcting
continuously 2026-07-16 → 2026-07-24** (latest row).

---

## 1. Ground truth — how an ORB entry is sized today (verified against code, 2026-07-26)

Chain for a MAGNA53 ORB entry (9M Day 2 is identical in structure):

1. **Regime fetch** — `broker/live_tracker.py:342-347`: at ~9:31 ET the ORB monitor reads
   `SELECT * FROM mi_market_regime WHERE regime_date <= $today ORDER BY regime_date DESC
   LIMIT 1`. Today's row is written by the **17:00 ET nightly** (`scheduler.py:4916` →
   `_nightly_data_pull` → `run_regime_engine`, `regime.py:473`), so at 9:31 this is
   **yesterday evening's row** — yesterday's VIX close, yesterday's label. No freshness
   check: a week-old row would be used silently if the nightly broke.
2. **Spec build** — `broker/order_manager.py::prepare_orb_order` (VIX logic at lines
   150-161; 9M twin at 3656-3661):
   - equity fetched live from Alpaca (per account_mode);
   - `risk_pct = vix_scaled_risk_pct(regime_record["vix"], base_pct=RISK_PCT=1%)`
     (`constants.py:10-39`): multiplier = `clamp(max(0.25, 1 − (VIX−15)/20), ≤1.0)`;
   - **then a second, separate halve**: `if regime_record["qqq_ema_bullish"] is False:
     risk_pct *= 0.5` (order_manager.py:160-161 / 3660-3661) — QQQ 10-EMA < 20-EMA;
   - `shares = floor(equity × risk_pct / (orb_high − orb_low))`, then the **20%-notional
     cap** (`shares × orb_high ≤ 0.20 × equity`).
3. **Composite multiplier** — `broker/entry_pipeline.py:440-484` (step 5b):
   `final_shares = floor(spec.shares × strategy.position_size_multiplier ×
   drawdown_tier_multiplier)`, clamped at the builder baseline. Unchanged by this proposal.
4. Third consumer of the same formula: `flag_detector.py:145-148`
   (`prepare_htf_breakout_order`, HTF **shadow** — never submitted). Sweep for consistency.

**Corrections to the task framing** (code contradicts / refines it):

- **Line drift:** the VIX logic is at order_manager.py **150-161** and **3656-3661** (not
  108-112 / 3530-3533). The fail-open code is `constants.py:35-36`; the comment that
  mislabels it "conservative fallback" is `constants.py:20-22`.
- **The regime LABEL already exists in the sizing path but is telemetry-only** — it is
  stored per trade (`mi_live_trades.regime`, from order_manager.py:205) and gates *alert
  admission* via `ep_threshold` (Bull 65 / Choppy 70 / Correcting 75 / Crisis 80,
  `regime.py:184-199`), but **never touches share count**.
- **"Sizing doesn't know we're correcting" is only half-true.** The `qqq_ema_bullish`
  halve has been active on every regime row a live entry has read since 2026-07-10
  (`qqq_ema_bullish=f`; the lone `t` row, 7/10, was read by no trade) — the recent live
  entries were sized at an effective **0.41-0.48×** base (verified per-trade: CRCL/WDFC
  0.48, TSEM 0.45, HUT/THC/WKC 0.41). The system IS sized down in this
  correction — via an EMA cross that appears nowhere in any SSoT, not via the regime. The
  fix's real content is legibility + the regime key + fail-safety, not a first-ever
  size-down.
- **The vix=None fail-open is real but LATENT, not a historical loss driver.** All 43
  closed trades to date had a populated VIX (ingest live since ~2026-03). It bites only on
  an ingest regression — and then at full base size, which is why it still must be fixed.

## 2. What the "full regime" model actually offers (measured on prod, read-only)

- **Classifier** (`regime.py::_determine_regime`, 54-217): weighted net score over SPY
  vs 50/200MA, QQQ vs 50MA, VIX bands, T2108 breadth, ±4% ratios (5d/10d), Pradeep
  momentum counts, consecutive-breakdown days, and a whipsaw-divergence nudge. Net ≥4 →
  **Bull**, ≥1 → **Choppy**, ≥−2 → **Correcting**, else **Crisis**. VIX is one input
  (weight up to −3) — the operator's point holds structurally: the label is a superset of
  the VIX signal. (`qqq_ema_bullish` is NOT a classifier input — it's a separate stored
  field used only by the sizing halve.)
- **Cadence:** one row/day, 17:00 ET nightly. Kept forever (`db.py` retention note).
- **Coverage:** 365 rows, 2025-03-03 → 2026-07-24. **BUT** (per
  `docs/analysis/454_regime_stratified_envelope_2026-07-17.md` §3c, re-verified): rows
  before ~2026-03-19 were **backfilled in one batch (all Bull)** — live labeling ≈ **4.3
  months** (2026-03-19+). VIX is NULL on 277/365 rows — all 260 pre-2026-03 rows plus 15 in
  Mar / 1 Apr / 1 May; ~daily since 2026-04, gap-free since June.
- **Live-label window composition** (2026-03-19 → 07-24, 90 weekdays): Bull 53 (59%),
  Choppy 14, Correcting 12, Crisis 11 — a real 41% non-Bull mix, unlike the all-Bull
  backfill stripe.
- **Label stability:** 22 transitions in 92 rows since 3/19 — the label **flaps every
  ~2-4 trading days at the Bull↔Choppy↔Correcting boundaries** in June-July (e.g. 7/08
  Correcting → 7/09 Choppy → 7/13 Correcting → 7/14 Choppy → 7/16 Correcting). A
  regime-keyed multiplier inherits this flap; see §3 design note.
- **Honest thinness finding:** the regime model is real but **young** — 4.3 months of
  trustworthy labels, zero Crisis days with any live/paper trade (the March-2026 crash
  predates the first pipeline trade, 4/17), and the #268b calibration envelope is
  **Bull-conditional** (94% Bull window; per-trade series lost — #454 doc). The operator
  should know the label is richer than VIX but NOT deeply validated as a *sizing* key yet.
- Doc drift flag (cosmetic): `regime.py` module docstring says thresholds 70/80/85/90;
  the code returns 65/70/75/80. Fix the docstring whenever the file is next touched.

## 3. Proposed mapping — regime → risk multiplier

Replace `vix_scaled_risk_pct()` + the `qqq_ema_bullish` halve at all three call sites with
ONE lookup (new `constants.regime_risk_multiplier(regime_label)`):

| Regime | Multiplier | Risk/trade at 1% base (live equity $4,835) | Rationale |
|---|---:|---:|---|
| Bull | 1.00× | ~$48 | Evidenced: the only bucket with real win rate (9/29, −0.35R avg — and the healthy-year +0.95R envelope is a Bull-window artifact, §6e). Low-WR winner-driven methodology needs full participation in its working regime. |
| Choppy | 0.75× | ~$36 | Direction evidenced (1/9 wins, −1.19R; −0.71R excl the SYRE gap-through outlier). Level set mild because Bull↔Choppy is the flappiest boundary (§2) — a 25% step bounds the whipsaw cost of a noisy label day. |
| **Correcting** | **0.50×** | **~$24** | Direction evidenced (0/5 wins, −1.02R; pooled non-Bull 1/14, −1.13R). Level borrows the drawdown-breaker REDUCE grammar (0.5× = "keep fishing, half exposure", safeguards.md 2026-05-18) — n=5 alone is below the N≥10 bar, flagged in §6. |
| Crisis | 0.25× | ~$12 | ZERO trade samples (no pipeline trade has ever met a Crisis label). Pure prior: floor = the old VIX formula's own floor, monotone with severity, matches ep_threshold's "only game-changers" stance. Explicitly NOT evidence-backed. |
| **None / stale / unrecognized** | **0.25×** | ~$12 | Fail-SAFE — see §4. |

- **Today's state:** Correcting → 0.50× (~$24 risk/trade), vs the current formula's
  effective 0.41-0.46×. Slightly LARGER than today's accidental EMA-halved sizing — the
  proposal is not "finally size down in corrections", it is "size down *because the regime
  says so*, legibly, with a fail-safe floor".
- **VIX's role:** influences sizing exactly once, through the classifier (it is a −1/−2/−3
  weight input). No separate VIX override retained — a VIX≥35 tape scores −3 and lands
  Correcting/Crisis on its own.
- **The `qqq_ema_bullish` halve is REMOVED** (folded into "the regime is the one sizing
  key"). This is a real behavior change in the current tape (see §6d) — operator fork Q2.
- **Composition unchanged:** `final = builder_shares(regime_mult) ×
  strategy_multiplier × drawdown_tier_multiplier`. Worst-case compound (Crisis 0.25 ×
  9M-Day2 0.5 × REDUCE 0.5 = 0.0625×) → sub-1-share → clean `size_too_small` skip —
  identical shape to today's floor math, fail-safe.
- **Flap handling: none in v1 (deliberate).** A sizing multiplier has no whipsaw *cost*
  (unlike an exit/entry flip — nothing churns; consecutive days just size differently),
  the current VIX formula is equally stateless, and hysteresis would add a state machine
  to the money path for an unproven benefit. If flap-driven size dispersion annoys in
  practice, add drawdown-breaker-style hysteresis as a follow-up with its own change log.

## 4. The fail-open fix (the part that must ship in the conservative direction)

**Today** (`constants.py:35-36`): `vix_value is None or <= 0 → return base_pct` — full
1% risk on unknown volatility, mislabeled "conservative" by the comment at lines 20-22.
This ran fail-open in effect for every pre-2026-03 day (277/365 rows VIX-null) and
remains latent behind any future ingest regression. Additionally `regime_record=None`
(empty table / query failure) skips BOTH the VIX scale and the EMA halve today, and a
**stale** row (nightly broke) is consumed with no freshness check at all.

**Proposed behavior** (exact):

1. `regime_risk_multiplier(label)` returns 0.25 for `None` or any unrecognized label
   (future-proof against label renames — unknown vocabulary must not silently full-size).
2. **Staleness gate at the fetch site** (live_tracker.py:342-347 + the 9M/HTF twins): if
   `regime_date < last_trading_day(today)` (trading-calendar-aware — `collector.
   last_trading_day` exists; Monday correctly accepts Friday's row), treat as missing →
   0.25×.
3. Both fallback paths emit a `sizing_regime_fallback` audit row (ticker, regime_date
   seen, multiplier applied). No Telegram — the nightly-failure alert + L1/L2 audit
   already page on the root cause; per-entry pages would duplicate. Surfaces in `/why`.
4. Delete the misleading comment; the docstring states the fail-safe direction.

**Why fail-safe, not fail-closed:** unlike the `/pause` halt-state (unreadable → block,
an operator-intent flag), missing regime data doesn't mean "the operator wants no
trades" — it means "we are blind to environment quality". Sizing at the floor keeps the
methodology operating (the drawdown breaker's own stale-data rationale, safeguards.md)
while capping blind exposure at ¼. Blocking outright would let a broken nightly silently
halt the strategy — a different failure of the same severity we're fixing.

## 5. Staleness at 9:31 — is a fresher read available?

- **Intraday VIX: not cleanly. Documented no.** Polygon Starter excludes Indices (I:VIX
  returns 403 — `collector.py:506-511`); Alpaca serves no indices; yfinance intraday
  quotes are scrape-grade — a fragile new runtime dependency inside the money path.
  Under this proposal the question also changes shape: the sizing key becomes the LABEL,
  whose inputs (MAs, breadth, T2108) are EOD by construction — a 9:31 label recompute is
  not meaningful. The label is inherently one-session-old at the open.
- **Quantified exposure of accepting that** (prod `mi_daily_closes`, SPY, 273 trading
  days 2025-06-24 → 2026-07-24): open gap ≤ −1% on **10** days, ≤ −1.5% on **1** day
  (2026-03-03, −1.65%), ≤ −2% **never**. The crash-morning-spike scenario the staleness
  worry contemplates has occurred ~1×/13mo at the −1.5% threshold. Prior-evening labels
  on those mornings (queried): in the live-label window, 3 of 4 gap-≥1% mornings had a
  non-Bull label going in (4/02 Crisis, 7/17 + 7/23 Correcting) and **one was a miss**
  (6/23, −1.42%, prior label Bull — the classifier flipped to Choppy only that evening).
  The 6 remaining gap days precede live labeling (backfill-Bull rows, unknowable). So the
  label usually — not always — carries deterioration into the next open; the residual
  exposure is ~1 mis-labeled ≥1% gap morning per ~4 months, sized one tier too big.
- **Optional guard, NOT recommended for v1:** a 9:31 SPY-gap check (one Alpaca snapshot,
  data already in-path): open ≤ −1.5% vs prior close → knock the day's multiplier one
  tier down. Clean to build, but it would have fired once in 13 months — shipping it now
  is a single-case-tune (CHANGE_PROCESS rule 2) with no measurable backtest. Listed as
  operator fork Q3.

## 6. Evidence (all read-only prod; scripts inline in this card's session)

**Cohort:** all 43 closed pipeline trades with P&L (`mi_live_trades`, 2026-04-17 →
07-24: 34 paper + 9 live; 29 Bull / 9 Choppy / 5 Correcting / 0 Crisis by the label the
sizing path saw — the stored `regime` column, verified identical to the prior-evening row
in 43/43). R = total_pnl / risk_dollars.

**(a) The regime label separates outcomes; VIX (in its traded range) barely does.**

| Regime at entry | n | wins | avg R |
|---|---:|---:|---:|
| Bull | 29 | 9 (31%) | **−0.35R** |
| Choppy | 9 | 1 (11%) | −1.19R (−0.71R excl SYRE −5.0R gap-through) |
| Correcting | 5 | 0 (0%) | −1.02R |
| non-Bull pooled | 14 | 1 (7%) | **−1.13R** |

| VIX seen at entry | n | wins | avg R |
|---|---:|---:|---:|
| < 16 | 5 | 1 | −0.52R |
| 16-17.5 | 23 | 6 | −0.55R |
| 17.5-19 | 11 | 3 | −0.62R |
| ≥ 19 | 4 | 0 | −0.96R |

Entire traded VIX range: **15.0-22.2** → the formula's multiplier lived in 0.64-0.98,
never using the 0.25-0.5 half of its range. VIX ≥ 25 — where the formula does real work —
has never coincided with a pipeline trade. The regime label spread (31% vs 7% win rate)
is the sharper conditioner on exactly this cohort.

**(b) Counterfactual weighting, R-space** (Σ multiplier×R over the same 43 trades, in
base-risk units; the fair scheme-vs-scheme test — dollar replay is contaminated because
28/43 trades were 20%-notional-capped, where risk_pct changes don't move shares
proportionally, and the 14 pre-2026-05-14 trades predate the VIX wiring entirely):

| Scheme | all 43 | non-Bull 14 (where the change binds) | live 9 |
|---|---:|---:|---:|
| flat 1.0 (no scaling) | −25.9 | −15.8 | −7.5 |
| current (VIX × EMA-halve) | −19.4 | −10.7 | −3.6 |
| **proposed A (1/.75/.5/.25)** | −20.6 | −10.6 | −4.4 |
| variant B (1/.5/.5/.25) | −18.0 | −7.9 | −3.7 |
| A × EMA-halve retained | −18.7 | −8.7 | −2.4 |

Honest reading: on this all-negative cohort ANY down-weighting "wins" vs flat, and
proposed-A is a *wash* vs current in total (−20.6 vs −19.4: it gives back current's
accidental ~0.88× Bull discount — a discount that costs expectancy in a healthy Bull
year). The mapping's case is NOT this table's bottom line; it is (a)'s separation + the
structural fixes (fail-open, dead dynamic range, one legible key). Variant B is better on
this sample but harsher on the flappiest label — fork Q1.

**(c) Large-N corroboration — candidate-pool quality degrades monotonically by regime**
(`mi_ep_missed_outcomes`, n=2,567 with 5d forward returns, 2026-02-11 → 07-24; % with
positive 5d return): Bull 47.1% (n=2,249) → Choppy 35.0% (n=234) → Correcting 27.8%
(n=79) → Crisis 20% (n=5). Caveats: pools all skip categories (incl. junk-filtered); the
HIGH-only slice is Bull-dominated (360 of 366) so it can't be cut by regime; pre-3/19
rows ride backfilled Bull labels. Directional support only — but monotone and large-N.

**(d) The recent live stretch, per-trade** (what actually changes right now): current
effective multipliers 0.94 on 7/06 (EMA still bullish), 0.41-0.48 since; proposed-A gives
0.50 (Correcting) / 0.75 (Choppy). On the 9 live trades (9 losses, −$180 total)
proposed-A would have lost ~$34 more; A-with-EMA-halve-retained ~$58 less (base-risk
units × ~$48 base; the live rows sit just under the notional cap, so this idealization is
near-exact here). In this specific three-week losing tape the accidental EMA halve
out-protected the proposal. Small-N, all-loss stretch — but it is the honest local read,
and it feeds fork Q2.

**(e) What the evidence CANNOT support (stated per CHANGE_PROCESS):** the N≥10 bar is
met for Bull (29), pooled non-Bull (14), and marginally Choppy (9); **Correcting alone
(5) and Crisis (0) fail it.** The 0.50 and 0.25 levels are therefore *structure*
(severity-monotone, borrowing the signed drawdown-tier grammar), not fitted values. The
#268b healthy-year envelope cannot arbitrate — it is Bull-conditional with its per-trade
series lost (#454 doc). If the operator wants Correcting/Crisis levels *evidenced* before
ship, the $0 path is #454 §5(a): re-run scan+simulate (no LLM spend) over the 12-month
window and stratify simulated ORB outcomes by regime — write-side, so it needs its own
go-ahead. Shipping the mapping now and letting the live cohort accrue per-regime
(labels are recorded per trade) is the alternative; both are listed in Q4.

## 7. Draft SSoT change-log entry + reversion (ready for operator signature)

Target: `docs/setups/safeguards.md` (sizing composition already lives there); same commit
updates the composition formula there + `docs/setups/magna53_ep.md` / `ninem.md`
sizing pointers + `constants.py` / `order_manager.py` / `flag_detector.py` /
`live_tracker.py`.

> ### 2026-MM-DD — Regime-keyed risk multiplier replaces VIX-scaled sizing + fail-open→fail-safe (#456 DoD(a))
>
> **Trigger**: operator ruling 2026-07-26 ("vix shouldn't be the thing that controls
> sizing, we have a full regime"), during a live Correcting stretch; #450-premortem
> residuals (VIX staleness + `vix=None` full-base-risk fail-open, `constants.py:35-36`).
>
> **Evidence**: `docs/analysis/456_regime_sizing_proposal_2026-07-26.md` — 43-trade
> closed cohort: Bull −0.35R (9/29 wins) vs non-Bull −1.13R (1/14); traded-range VIX
> bands don't separate (−0.52/−0.55/−0.62/−0.96); candidate-pool 5d-positive rate
> monotone by regime (47/35/28/20%, n=2,567). N≥10 met for Bull + pooled non-Bull;
> **Correcting (n=5) / Crisis (n=0) levels are structural priors, flagged as such.**
>
> **Change**: `risk_pct = RISK_PCT × regime_risk_multiplier(label)` — Bull 1.0 / Choppy
> 0.75 / Correcting 0.5 / Crisis 0.25 / missing-stale-unknown 0.25 (stale = regime_date <
> last completed trading day). Removes `vix_scaled_risk_pct` and the `qqq_ema_bullish`
> ×0.5 halve from all three sizing sites (order_manager ×2, flag_detector HTF shadow).
> VIX now affects sizing only through the regime classifier. Strategy × drawdown
> composition (entry_pipeline 5b) unchanged. New audit event `sizing_regime_fallback`.
>
> **Anticipated effect**: in the current Correcting tape, risk/trade ~0.50× base (~$24
> live) vs current effective 0.41-0.48×; on a Bull day, 1.0× vs current ~0.85-0.95×
> (the VIX formula's permanent haircut disappears); on a missing/stale regime row, 0.25×
> instead of 1.0×. Verify-live: first entry logs `regime=<label>` + multiplier in the
> order-spec log line; `sizing_regime_fallback` count stays 0 in normal operation.
>
> **Reversion-flag**: REVERSAL of P19 (2026-05-14, `cc8f2e9`) VIX-scaled sizing + its
> None-fallback, and of the bearish-EMA halve it preserved. Why the prior was *wrong*,
> not just incomplete: (1) its None-fallback comment claimed "conservative" while
> returning FULL base risk — factually inverted, and it ran that way for every VIX-null
> day; (2) it keyed sizing on one classifier input whose traded dynamic range (15-22)
> left the formula ~flat while the composite label it ignored separated outcomes on the
> same trades; (3) it introduced a second, undocumented sizing axis (the EMA halve) that
> no SSoT records — the de-facto sizing policy was illegible. Rollback = revert commit
> (the three call sites restore `vix_scaled_risk_pct` + halve; constants keeps the old fn
> until the deprecation window closes).
>
> **Status**: DRAFT — awaiting operator sign-off; then shadow-verify (paper sizes with
> new multiplier ≥3 sessions incl. one label transition) before the live deploy.

**Explicit revert triggers** (what would make us undo this): (i) a regime-label outage
class appears (repeated `sizing_regime_fallback` days) that the old VIX path would have
sized normally; (ii) 20+ further live/paper trades show Bull-labeled expectancy at or
below non-Bull (label loses its separation = the key is wrong); (iii) label flap produces
operator-visible sizing incoherence (same setup, adjacent days, >2× size swing) that
hysteresis can't cheaply fix; (iv) any evidence the classifier's label lags a crash
morning WORSE than yesterday's-VIX did (the 2026 gap-day audit in §5 says the opposite
today).

## 8. Open questions for the operator (forks — one-line rec each, none pre-decided)

- **Q1 — Choppy level: 0.75× (map A) or 0.5× (map B)?** B scores better on the 43-trade
  sample (−18.0 vs −20.6) but punishes the flappiest label; A bounds flap cost. **Rec: A
  (0.75×)** — thin N shouldn't buy the harsher step at the noisiest boundary.
- **Q2 — keep the `qqq_ema_bullish` ×0.5 halve as a second axis, or fold it?** Keeping it
  (A×halve) was the best performer on the recent live stretch (−2.4 vs −3.6 current) and
  Correcting+bearish-EMA would sit at 0.25×; but it preserves the two-axis illegibility
  the ruling targets, and the EMA cross is regime-adjacent information the classifier
  could ingest properly later. **Rec: fold it** (one key, one table; revisit as a
  classifier input, not a sizing side-channel).
- **Q3 — ship the 9:31 SPY-gap one-tier-down guard now?** Clean to build; fired ~1×/13mo
  at −1.5%. **Rec: no** — document (done, §5), add only if a real stale-morning incident
  occurs (it would be a single-case-tune today).
- **Q4 — evidence the Correcting/Crisis levels before ship, or accrue live?** Options:
  $0-LLM scan+simulate regime re-cut (#454 §5a — write-side rerun, needs its own
  go-ahead) vs ship-and-accrue (labels recorded per trade; review at the quarterly band
  review alongside `kill_scale_bands_quarterly_review`, first due 2026-08-01). **Rec:
  ship-and-accrue** — the direction is evidenced, the levels are conservative, and the
  quarterly review is already the standing re-derivation surface.
- **Q5 — unknown/stale floor at 0.25× vs 0.5×?** 0.25× is the maximal-caution reading of
  "unknown environment"; 0.5× trades more through a broken nightly. **Rec: 0.25×** — the
  condition is loud (nightly-failure alert + audit) and short-lived; blind exposure
  should sit at the floor.
