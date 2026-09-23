# Stop-too-wide outcome cohort — does MAGNA53's ATR gate shed winners? (2026-08-17)

**Verdict in one line: too small a sample to tell, in either direction. Once the cohort is
scoped to the correct setup (a labeling bug had mixed in a different setup's filter), the two
names that likely never filled are set aside, and what's left is normalized by each stock's own
daily range and run through today's actual exit mechanics (including a price-triggered partial
this analysis initially missed), the 5 properly-settled rejected names land within noise of what
the system already trades — not clearly better, not clearly worse. Of the two seed cases: STRL
remains a genuine winner; AIP, once actually run through the bracket, is a real loser — the
second flag does not hold up.**

> **THE LINE — this document is EVIDENCE, not a change.** Nothing here authorizes touching the
> `setup:stop_too_wide` threshold, the stop anchor, sizing, or any other entry/exit discipline.
> Any change requires the operator's sign-off, `docs/setups/CHANGE_PROCESS.md`, and a backtest —
> and per the finding below, the properly-scoped sample here (N=9, 5 settled and fill-plausible)
> is well short of that N≥10 bar. No live behavior was read, touched, or modified in producing
> it (read-only DB reads + a local, no-import re-implementation of the production exit ladder).

Review: `data_gated_reviews.yaml` → `stop_too_wide_outcome_cohort` (went READY 2026-08-08,
7 days overdue at time of run). Origin: STRL 2026-05-05 (+17.0% close / +22.2% max over 5 days)
and AIP 2026-05-13 (rejected at 1.05x, score 115.2 HIGH, AI-semis catalyst) — N=2 raised the
worry the ATR-based `setup:stop_too_wide` filter sheds winners. Probe:
`scripts/probes/stop_too_wide_cohort.py` (reads cached prod pulls under the session scratchpad;
re-pull queries are in the script's SQL comments / header).

Two modeling corrections are documented in place below (§1's profit-trigger paragraph, §1's
day-0 note) rather than silently folded in, since they materially changed the conclusion.

---

## 0. The gate's N=13 conflated two different setups — read this first

The review's `predicate_sql` counts every `mi_live_trades` row with
`skip_reason LIKE 'setup:stop_too_wide%'`. Two *different* code paths write that prefix:

| Setup | Function | Anchor | Threshold | Example message |
|---|---|---|---|---|
| MAGNA53 (this review's subject) | `order_manager.prepare_orb_order` | ORB range vs ATR_14 | range > 1.5×ATR | `"ORB range $3.18 (9.8%) > 1.5x ATR $3.02"` |
| 9M Day 2 (a different setup) | `order_manager.prepare_prior_day_low_orb_order` | stop distance as % of entry price, anchored to the **prior day's low** | distance > 15% of price | `"stop distance 26.5% > 15%"` |

Of the 17 `setup:stop_too_wide%` rows since 2026-05-05, **9 are MAGNA53 and 8 are 9M Day 2** — a
completely different setup with a different stop anchor. Of the 17, 13 are past the review's
25-day settle lag — that's exactly the "N=13" that made the gate fire. **Scoped correctly to
MAGNA53 (what STRL/AIP/the review's question are actually about), the true cohort is N=9, and
only 5 of those are past the 25-day settle lag.** This review proceeds on the correctly-scoped
N=9 cohort since that's what the question is about, but the gate's own N≥10-settled bar is not
actually met once scoped correctly — flagged for whoever revisits `predicate_sql` (not fixed
here; out of this review's scope and not a live-trading change).

---

## 1. Cohorts and method

**Rejected cohort (N=9):** every MAGNA53 HIGH alert rejected by the ATR gate since 2026-05-05 —
STRL, EVER (both 5/05), AIP (5/13), GO (5/14), PONY (5/26), CORT (7/30), AEVA (8/06), ATRO
(8/12), HTFL (8/14). `orb_high`/`orb_low`/`atr_14` are **not persisted** on a row the gate
rejects (the columns are only written on a successful `prepare_orb_order` call), so ORB
geometry was reconstructed algebraically from the skip_reason's own printed numbers (the code's
own arithmetic: `orb_range = orb_high - orb_low`, `orb_pct = orb_range/orb_low*100`, printed
`atr15 = 1.5 * atr_14`, inverted back to `orb_low`/`orb_high`). Checked against each ticker's
actual daily bar for that date via the physical constraint `day_low ≤ orb_low ≤ orb_high ≤
day_high` (the ORB window is a 5-minute subset of the day): 6 of 9 rows satisfy both bounds
cleanly; 3 miss by a small margin explained by the skip_reason's own printed precision (percent
to 1 decimal, dollars to 2) — sub-1% price-level uncertainty, doesn't change cohort membership.
Two of those three misses (GO, PONY) turned out to matter for a different reason — see below.

**Fill plausibility — GO and PONY probably never actually filled.** `orb_high` is by
definition the max of the first 5 minutes, so a stock's day-high must sit at or above it. GO's
reconstructed `orb_high` ($9.475) is *above* its actual day high ($9.44); PONY's ($10.477) is
above its actual day high ($10.40) — both by a small margin, meaning the ORB high effectively
*was* the session high for these two. A stop-limit buy queued at that level, live only from
9:31-9:44 ET, requires price to trade back UP to it after the opening 5 minutes; if the day's
high never got there again, the order almost certainly never filled — a real
`"cancelled: ORB window unfilled"` in production, $0 P&L, not a trade. Every other rejected row
has real headroom (day-high sits 1.5%-25% above the reconstructed ORB high). **GO and PONY are
therefore reported separately and excluded from the primary read** — this isn't a data artifact,
it's the same "did this alert ever actually trade" question the baseline cohort already has to
answer with real status data (below), just without ground truth for these two specific rows,
since the system rejected them before ever trying to place an order.

**This heuristic is validated, not assumed.** The 77 baseline rows have real `orb_high` AND real
fill status, so the same headroom measure can be checked against ground truth: of the 20
baseline rows with headroom ≤0.1% (near-zero or negative, GO/PONY's bucket), only **1 actually
filled (5%)** — versus 59-88% filled in every higher-headroom bucket. Near-zero headroom is a
strong, confirmed predictor of "never filled," not a guess.

**Baseline (N=77 "passed the gate," N=40 "passed AND actually filled"):** every HIGH-tier
MAGNA53 alert in the same window whose `orb_high`/`orb_low`/`atr_14` are on the row (meaning
`prepare_orb_order` ran and the ATR check passed) — this is literally "alerts that passed the
`stop_too_wide` filter," the comparison the task asked for. **37 of 77 never actually filled**
(status `cancelled: ORB window unfilled`, the same mechanism GO/PONY are suspected of above —
except here it's known, not inferred, straight from `mi_live_trades.status`). Those 37 are
excluded from the primary comparison; "baseline" below means the 40 that actually filled unless
labeled "all gate-passers."

**Bracket, applied uniformly to both cohorts:** entry = ORB high (stop-limit buy). Stop = the
**current, 2026-08-16 operator-signed rule** — `stop = entry − 2R` where `R = orb_high − orb_low`,
i.e. `stop = 2·orb_low − orb_high`. This is deliberately the bracket as it exists **today**, not
whatever rule was live on the historical alert date, so both cohorts are judged by the same
yardstick (the ATR gate itself did not move in that change — this is purely a downstream stop
question).

**Two independent exit mechanisms are modeled, not one — missing the second was the analysis's
real bug.** The daily ladder
(`agents/market_intelligence/broker/exit_logic.py::apply_daily_exit_step`: hard stop on
close-below-low, `max(SMA10,SMA20)` trail seeded with the ticker's own pre-alert closes, Day 3-5
hold-based partial, breakeven-floor after a partial) is one. **Separately, and live since
2026-08-01, `order_manager.scan_profit_triggers` (`constants.PROFIT_TRIGGER_R = 2.0`) takes 1/3
off the moment price first trades at `entry + 2·(entry − orb_low)`** — the OLD, orb-defined R,
deliberately held fixed by the 2026-08-16 design so the target doesn't drift when the stop
widens. This is a **separate, earlier-firing, intraday mechanism active from the moment of
fill (day 0 included)** — the first draft of this analysis modeled only the daily ladder and
missed it entirely. That target works out to exactly `entry + risk_per_share` under the current
2R stop (the algebra: `2·(entry−orb_low) = entry − stop_current`) — i.e. it sits at exactly +1R
in this document's own R-unit, symmetric with the −1R stop. **Missing it was not a rounding
error: on the 40-trade filled baseline it moved the median realized R from −1.00 to −0.33 (20
of 40 trades actually cross the target) — the −1.00 draft number was silently reproducing the
OLD, pre-2026-08-16 stop rule's documented behavior instead of testing the current one.** Both
mechanisms are now modeled, sharing the same `partial_taken` flag production itself uses so
they're mutually exclusive per trade, exactly as in the live code.

One thing intentionally NOT added: a same-day hard-stop check. Production's own daily ladder
skips day 0 entirely (a real intraday stop is a live broker order, invisible to a daily-bar
probe); a first attempt at approximating it here using the whole session's low was tested and
rejected — it can trip on a pre-fill dip that happened *before* the ORB-high buy would even have
triggered, and it's what drove the original −1.00R baseline artifact above. The profit-trigger
check, by contrast, is legitimately live from fill onward in production, which is why it — but
not a same-day stop check — is modeled starting day 0.

**Normalization — required, not optional here.** Raw percent return is rigged toward the
rejected cohort by construction: this filter selects on volatility, so wide-range names will
show bigger raw moves whether or not they're better trades. Two separate normalizations are used:
- **ADR20** (house formula, `sell_discipline.py`: mean `(high-low)/close×100` over the 30
  calendar days — ~20 sessions — before the alert) turns any raw $/％ number into "how many of
  this stock's own average days" it moved. Used for the ORB range itself, the stop distance, and
  raw MFE (max high touched, the best price seen — NOT what the bracket kept).
- **R-multiples are NOT comparable between these two cohorts** and are reported for
  completeness only — the rejected cohort's stop, in ADR terms, runs ~2.4-2.5x wider than
  baseline's, so a "less negative R" for rejected partly reflects an inflated R-unit, not a
  better trade. The apples-to-apples figure is **realized return normalized directly by ADR20**
  (`realized_adr_norm` — dollar P&L as % of entry, divided by ADR20%; exactly
  `sell_discipline.py`'s `realized_adr` field, R-unit-independent by construction). This is the
  number to read for "did the trade actually make more."

---

## 2. Results

### 2a. Stop geometry — is the rejected cohort actually unusual, even for itself?

| | N | ORB range, in ADR20s (median) | Current-rule stop distance, in ADR20s (median) |
|---|---|---|---|
| Rejected (all 9) | 9 | **1.56** | **2.91** |
| Rejected (excl. GO/PONY) | 7 | 1.55 | 2.75 |
| Baseline (filled) | 40 | 0.61 | 1.16 |

Yes — even normalized by the stock's *own* volatility, the rejected cohort's opening range runs
**~2.5x wider** than what typically passes. This is not just "the filter flags generically
volatile stocks" — these opening ranges are unusual even for names that are themselves already
volatile enough to be MAGNA53 HIGH candidates. That part of the finding is unaffected by
either correction above and is the most robust single fact in this document.

### 2b. Raw excursion (MFE, best price touched — NOT what the bracket kept)

| | N | 5d MFE, raw % (median) | 5d MFE, in ADR20s (median) |
|---|---|---|---|
| Rejected (all 9) | 9 | +9.0% | 1.98 |
| Baseline (filled) | 40 | +6.3% | 1.08 |

Raw-percent, the rejected cohort looks like it has *more* early upside — this is the number
that would mislead you if you stopped here, exactly the effect the review was warned about.
Normalized it survives at 5 days (1.98 vs 1.08 ADR) but is not, on its own, what a real position
— with a real stop that can get hit first — would have kept. Section 2c is that.

### 2c. Realized return under today's actual bracket (the number that matters)

| Cohort | N | Realized R (median / mean) | **Realized return, ADR-normalized (median / mean / P90)** | Share reaching ≥ +2 ADR |
|---|---|---|---|---|
| Baseline, filled | 40 | −0.33 / −0.26 | −0.35 / −0.30 / +1.27 | 5% |
| Rejected, all 9 | 9 | +0.02 / +0.05 | +0.07 / −0.01 / +1.48 | 0% |
| Rejected, excl. GO/PONY (N=7) | 7 | +0.31 / +0.20 | +0.64 / +0.41 / +1.59 | 0% |
| **Rejected, excl. GO/PONY + 5d-settled (N=5)** | **5** | **−0.11 / +0.04** | **−0.31 / −0.08 / +1.04** | **0%** |

The bottom row is the fairest cut available: the two names that probably never filled are set
aside, and only names with enough forward days to trust are kept (STRL, EVER, AIP, CORT, AEVA —
the two most recent, ATRO/HTFL, are excluded here for being too fresh to settle). **Read against
the baseline row directly above it, the two are within noise of each other** — rejected's
median (−0.31 ADR) and baseline's (−0.35 ADR) are essentially the same; rejected's mean is
somewhat better (−0.08 vs −0.30) but off five trades that's not a distinguishing signal. Neither
cut of the rejected cohort reaches the +2-ADR tier baseline reaches 5% of the time, but at N=5
that's not surprising even under random draws from baseline's own distribution.

**Reconciling against the documented backtest.** `order_manager.py`'s 2026-08-16 change note
cites 43 reconstructed HIGH trades, April-May only, median +0.33R under the 2R stop (explicitly
flagged there as "one regime... no out-of-sample until the shadow accrues"). This probe's
baseline (40 filled trades, 2026-05-05 through today, so mostly *later* than and only partially
overlapping their window) comes out at median −0.33R — the opposite sign, on a later and larger
sample. That's a real, useful data point (partial out-of-sample evidence the April-May median
doesn't fully hold up into June-August), but it's a finding about the 2R-stop rule's general
performance, not about the `stop_too_wide` filter this review is scoped to — noted here only so
the two documents aren't read as silently agreeing when they don't, and flagged as a candidate
follow-up, not resolved in this document.

### 2d. STRL and AIP, specifically — representative, or the false alarm?

| Ticker | Score | ORB range (ADR20s) | 5d raw MFE | Realized R | **Realized, ADR-normalized** | Profit-trigger fired? | Read |
|---|---|---|---|---|---|---|---|
| STRL | 96 | 1.02 | +20.9% | +0.67 | **+1.31 ADR** | Yes | Genuine winner. Confirms the original flag. |
| AIP | 115.2 | 1.71 | +8.0% | −0.37 | **−1.14 ADR** | No | A real loss once actually run through the bracket. Does NOT confirm the flag — the exciting score/catalyst never turned into a good trade. |

Both numbers are essentially unchanged by the profit-trigger correction for AIP (its move never
reached the target, so it was never affected) and only moderately changed for STRL (it did
cross the target — realized R moved from +0.86 in the first draft, which force-fed the whole
position through the slower Day3-5/trail path, to +0.67 once the earlier, real partial is
modeled — still a clear winner, just banked a little earlier and for less on the trailing
two-thirds). STRL's +1.31 ADR sits right around baseline's own top decile (P90 +1.27) — a real,
solid trade, comparable to but not obviously better than the best of what the system already
catches, not evidence of a systematic miss.

### 2e. All 9, for the record

| Ticker | Date | Score | ORB range (ADR) | Fill headroom | 5d MFE | Realized R | Realized (ADR) | Close reason | Settled |
|---|---|---|---|---|---|---|---|---|---|
| STRL | 5/05 | 96 | 1.02 | +9.8% | +20.9% | +0.67 | +1.31 | trail exit | 20d |
| EVER | 5/05 | 100 | 1.07 | +25.0% | +25.0% | +0.31 | +0.64 | trail exit | 20d |
| AIP | 5/13 | 115.2 | 1.71 | +1.5% | +8.0% | −0.37 | −1.14 | trail exit | 20d |
| GO | 5/14 | 84 | 1.65 | **−0.4%** | −0.4% | −1.00 (n/a — likely unfilled) | −3.06 (n/a) | day+1 stop | 20d |
| PONY | 5/26 | 64.8 | 1.58 | **−0.7%** | +7.7% | +0.02 (n/a — likely unfilled) | +0.07 (n/a) | trail exit | 20d |
| CORT | 7/30 | 96 | 1.55 | +8.8% | +8.8% | −0.10 | −0.31 | trail exit | 5d only |
| AEVA | 8/06 | 96 | 1.56 | +9.0% | +9.0% | −0.33 | −0.90 | trail exit | 5d only |
| ATRO | 8/12 | 72 | 1.59 | +8.1% | +10.3% | +0.65 | +1.91 | still open | not yet |
| HTFL | 8/14 | 96 | 1.26 | +10.3% | +11.0% | +0.58 | +1.37 | still open | not yet |

Of the 5 excl.-GO/PONY, 5d-settled names: **1 clear winner (STRL), 1 modest winner (EVER), 3
modest-to-real losers (AIP, CORT, AEVA)**. GO and PONY are set aside as likely non-fills, not
counted either way (their "realized" figures above are what the simulation computes assuming a
fill that probably never happened — kept in the table for transparency, not used in §2c/§3).
ATRO and HTFL are currently positive but have far too little forward data (1-3 trading days) to
call either way.

### 2f. A mechanical property of the current bracket: the profit target scales with the ORB

The profit-trigger target (§1) is fixed at `entry + 2×orb_range` in dollar terms — but a wide
opening range makes that a much **bigger ask in the stock's own ADR units**:

| Cohort | N | Target distance needed, in ADR20s (median) |
|---|---|---|
| Rejected | 9 | **2.91** |
| Baseline (filled) | 40 | **1.16** |

The rejected cohort needs **2.5x more of the stock's own average daily range** just to reach the
first partial than baseline does — mechanically, since the target distance IS `2×orb_range` and
orb_range is what the filter measures. That means the two rejected names with the smallest
opening ranges are arithmetically the two with the smallest bar to clear — and indeed, **the
only two rejected names whose target fired are STRL (1.95 ADR needed) and EVER (2.03 ADR
needed), the two tightest opening ranges in the cohort.** Every other rejected name needed
2.35-3.11 ADR and came up short (AIP needed 3.11 ADR, reached 1.64; GO needed 3.06, reached
0.69; CORT needed 2.91, reached 1.98; AEVA needed 2.75, reached 1.05; ATRO/HTFL needed 2.96/2.35,
reached 2.28/1.99 and are still open). Baseline's target fires roughly half the time (20 of 40).

**This is a real, mechanical cost of the current bracket for wide-ORB names specifically, not
sample noise** — a wide opening range is penalized twice: a bigger stop-side R unit (§2a) AND a
profit target pushed proportionally further away, because the target frame was deliberately
fixed to the OLD orb-defined R when the stop widened on 2026-08-16 (§1) and does not re-scale
with how wide the ORB itself was. It bears directly on the fork the operator would need to
resolve, without deciding it here: **(a) widening the ATR multiple lets through MORE names that
structurally can't reach their own profit target** (a cost the "just admit more" framing
doesn't show); **(b) changing the stop anchor cannot be judged in isolation from this** — a
wider/different anchor without also revisiting the target's R-frame would make the partial even
harder to reach, not easier. That's a second, related fork this document surfaces but does not
resolve.

---

## 3. Which of (a)/(b)/(c) the evidence points to

**Lean: none, at this N — the honest read is "no basis for a change," not "the filter is
correctly tuned."** The properly-scoped, fill-plausible, settled cohort (N=5) cannot be
statistically separated from baseline:
- The rejected cohort's opening range IS genuinely unusual even for its own volatility (2.5x
  baseline's normalized width, robust to every correction above) — the filter is measuring
  something real, not just flagging "any volatile stock." That part is solid.
- But its properly-settled realized outcome, ADR-normalized, is statistically indistinguishable
  from what the system already trades (median −0.31 vs baseline −0.35; mean actually somewhat
  better for rejected). At N=5 this is not evidence the filter is well-tuned — it's evidence the
  sample can't resolve the question either way.
- **The current bracket's profit target mechanically needs ~2.5x more of the stock's own ADR to
  reach for a wide-ORB name than a typical one (§2f)** — the two rejected names that DID convert
  (STRL, EVER) are exactly the two with the smallest target distance in the cohort. This is a
  real, arithmetic property of the current bracket, and it bears on (a)/(b) directly even though
  it doesn't itself explain why the settled cohort came out statistically even with baseline
  above — it's a headwind specific to wide-ORB names under THIS bracket, separate from whether
  the underlying stock was a good one to buy.
- 2 of the 9 rejected names (GO, PONY) most likely never would have filled at all — a real,
  if unmeasurable-from-here, tempering factor on any "cost" estimate for the filter (validated:
  near-zero headroom predicts non-fill 95% of the time in the baseline ground-truth data, §1).
- Of the two seed cases, only 1 of 2 (STRL) holds up; AIP is a false alarm once actually
  simulated with the real bracket mechanics.

**This does NOT support (a) widening the multiple** on its own — it would admit more names that
are structurally further from their own profit target (§2f), a cost the "just let more through"
framing doesn't show, with no measured upside at this N. **It does not support (b) changing the
anchor in isolation either** — the target's R-frame would need to be reconsidered together with
any anchor change, or the partial gets harder to reach, not easier; that's a second, related
fork for the operator, not something this document decides. It also **does not affirmatively
support (c) as "correctly tuned"** — it only shows the filter hasn't been caught shedding real
value at this sample size, and shows a real, separate reason (§2f) why a wide-ORB name would
underperform even if genuinely a good stock. **Default to no change** (nothing here clears the
N≥10 CHANGE_PROCESS bar, and even the properly-scoped N=9 doesn't), and revisit once more
MAGNA53-specific rejections have settled — not on the review's original 25-day-lag predicate_sql
(which double-counts the unrelated 9M filter, see §0), but tracking the true MAGNA53-only count.

---

## 4. What this does NOT support

- **Not a backtest-grade N≥10 read.** 5 settled, fill-plausible MAGNA53-only rejections; the
  review's own gate over-counted by conflating a different setup's filter (§0).
- **Rejected-cohort ORB geometry is reconstructed, not measured** — sub-1% price-level
  uncertainty from the skip_reason's own rounding (§1). Baseline cohort has no such uncertainty
  (real `orb_high`/`orb_low` from the row).
- **GO and PONY's outcomes are not real evidence either way** — both most likely never filled;
  their simulated P&L (a stop-out and a wash, respectively) assumes a fill that probably never
  happened. Kept in §2e for transparency, excluded from every conclusion in §3. The headroom
  heuristic behind this call is validated against 77 real fill outcomes (§1: near-zero headroom
  → filled only 5% of the time) but is still inferred, not measured from GO/PONY's own real
  order state (the system rejected them before ever attempting to place an order, so there is no
  ground truth for these two specific rows, only the base rate from similar-headroom peers).
  The converse is NOT validated: real headroom does not guarantee a fill (baseline's own
  0.1-2% and >5% headroom buckets are only 67% and 59% filled respectively, §1) — so the
  retained 7 (and especially the 5 settled ones: STRL, EVER, AIP, CORT, AEVA) may themselves
  include names that never actually filled, in either direction, which is exactly why §3 reads
  this as "can't resolve at N=5" rather than "resolved and comparable."
- **Not evidence about the 9M Day 2 "stop distance > 15%" filter.** That's a different setup,
  different anchor (prior day low, not ATR), different threshold — untouched by this review.
- **Not a verdict on the 2026-08-16 2R-stop change generally.** §2c's baseline reconciliation
  (median −0.33R here vs the documented +0.33R on an April-May-only sample) is a real,
  interesting divergence but is about that separate change, not this review's filter — flagged,
  not resolved, here.
- **Not a recommendation.** Per THE LINE, this is evidence for the operator to weigh against
  (a)/(b)/(c) — nothing here is authorization to touch the filter, the stop, sizing, or the
  profit-trigger mechanism.

---

## Appendix — reproduction

- Probe: `scripts/probes/stop_too_wide_cohort.py` (pure Python, no imports from
  `agents/market_intelligence/` — a documented, line-checked re-implementation of two
  independent production mechanisms: `exit_logic.py::apply_daily_exit_step` and
  `order_manager.py::scan_profit_triggers`, avoiding the live asyncpg/Alpaca/minute-bar
  dependency graph).
- Raw pulls (session scratchpad, not checked in): `baseline_passed.psv` (78 rows, HIGH MAGNA53
  alerts with `orb_high` populated, `mi_ep_alerts` ⋈ `mi_live_trades`),
  `daily_bars.psv` (7,837 rows, `mi_daily_closes` for the 83 tickers involved, 2026-04-01
  onward), full per-row results in `stop_too_wide_results.json`.
- Re-pull SQL is in the script's module docstring / inline SQL strings (see `load_baseline`,
  `REJECTED_RAW`, and the header comment for the exact `psql` calls used against
  `apollo@87.99.134.162` / `apollo-postgres`).
- $0 — no LLM or paid API calls; DB reads (`mi_ep_alerts`, `mi_live_trades`, `mi_daily_closes`)
  and local computation only.
