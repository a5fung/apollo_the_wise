# EP backtest run 1 — today's admission stack, replayed from raw bars, $0 path

**Date:** 2026-08-29 (PT) · **Task:** #482 successor (spec: `docs/design/ep_backtest_spec_2026-08-29.md`)
· **Status:** read-only evidence. Nothing changed, nothing deployed, nothing proposed.
· **Standard:** `docs/methodology/analysis_standard.md` — §1 questions answered in §0; Gate 6 sections present.

---

## §0 · The decision this serves

Operator (2026-08-29): *"stop using old data when our system has evolved significantly week to
week… just use raw data to run our analysis given we have minute bars stored."* And on the
measure: *"it's not just ratio of winners to losers... more important is the expected return,
how much we lose with the loser and how much we win with winners and is that outcome positive."*

1. **Decision:** does TODAY's EP system (2026-08-29 rules) have positive per-signal expectancy,
   and which admission stage does the work.
2. **What would change it:** the sign of expectancy (mean AND median, in R) on the cohort
   today's rules would have admitted 2026-04-13 → 08-28.
3. **Population:** re-derived from raw daily/minute data, NOT from any alert/trade table (§1).
4. **What would make it wrong:** §5, written against the retracted geometry doc's failure mode —
   and one instance of exactly that failure was caught inside this run (§5, defect A).

**HEADLINE, stated honestly:** the $0 bracket is **sign-indeterminate**.
Run L (catalyst-blind) = **−0.16R mean / +0.33R median, n=17 (insufficient n)**;
Run U (catalyst-generous) = **+0.14R mean / +0.33R median, n=194** — and U's positive mean
rests entirely on its two biggest winners (ex-top-2 mean **−0.01R**, n=192). The robust
statistic is the **median +0.33R** (both runs): the modal filled trade takes the +2R partial on
1/3 and the runner gives the rest back to breakeven. Whether the mean is positive depends on
(a) the catalyst grades this run could not reconstruct for $0 and (b) 2-3 right-tail runners
held under a no-trail exit model. Collapsing (a) is the ~$40 Stage 1b of the spec; it was not
spent, per the brief.

---

## Method / population (§1)

- **Population:** 4,453 ticker-days (1,898 tickers, 97 sessions, 2026-04-13 → 08-28) from
  `_bt_population_capture.psv` — every ticker-day with `max(gap_at_open, scanlog_max_gap) ≥ 9%`
  and prev_close ≥ $5, derived from `mi_daily_closes` (facts) unioned with scan-log ticks,
  deliberately NOT from `mi_ep_alerts`/`mi_live_trades` (rule-era outputs).
- **Bars:** `mi_intraday_bars` post-backfill; 09:30 ORB coverage re-derived from the DB this
  run (the capture file's coverage flags were stale, as the brief warned). Daily OHLC from
  `mi_daily_closes` through 2026-08-28.
- **Rules manifest — every constant read from code TODAY (2026-08-29), none from docs:**
  universe floors `MIN_PREV_CLOSE=5 / MIN_PREV_DAY_VOLUME=50k / MAX_TICKER_LEN=5 /
  SKIP_TICKERS` + security-type gate (only CS/ADRC pass; unclassified skipped, the live
  fail-safe) · shortlist prescore (liq 15×3 / gap 10×1 / theme 10×1, ADV$-then-ticker
  tie-break) cap `SHORTLIST_SIZE=20` · `EP_COOLDOWN_DAYS=60`, self-consistent against the
  RE-DERIVED alert history · `MAX_EXTENSION_PCT=50.0` (**the 08-29 revert, `ep_detector.py:213`
  — the stale doc still says 75**) vs MIN(close) of [D−10, D) · quality filters: median 30d
  close×volume ≥ $1M (no-data → skip, per code), Wilder ATR14 ≤ 15% (<10 rows → pass),
  mcap ≥ $500M (missing → pass) · score: flat gap 10 (≥8%), ADV$ tiers 500/250/100/50M →
  15/12/10/7, catalyst 25/15/0, theme +10, conviction floor branch 4 only (gap ≥10 +
  game_changer → 60), ×1.2 Bull regime, presented = ×1.25+15, HIGH bar 65 · post-grade M&A
  skip · ORB window: alert evidence must exist by 09:44 ET; fills 09:31–09:59 else cancelled.
- **As-of discipline (no accessor reads "latest"):** regime = last row < D; themes = last
  snapshot per name in [D−7, D−1], Retired dropped; stored ADV = `mi_stock_scores` at last
  score_date < D (130 retained dates — the actual live input); filter-ADV/ATR/extension windows
  all end at D−1. Knowingly-current inputs, named: market cap (spec D5) and today's
  `mi_security_types` table.
- **The catalyst bracket (spec D2):** Run **L** = catalyst 0 for all, no floor. Run **U** =
  strong (15) for all, game_changer (25 + floor) where a stored v3-era grade (≥ 2026-06-12)
  says so, stored `mna` (any era) → post-grade kill. Judge **OFF** both runs (it overwrites
  ~29% of tiers live — an admitted infidelity, not simulated).
- **Replay:** `scripts/probes/_bt_replay.py::replay_trade` unchanged (self-tests + both
  mutation tests green this run). Caller adds only the 09:59 fill-window guard using the
  harness's own `_fill_entry` on the 09:31–09:59 prefix. Outcomes in R = entry − hard_stop
  (the 08-16 bracket), 40-session horizon, stop-first tie-break, `coverage_ok=False` on any
  gap vs the global session calendar (downgrades to `no_bars`, never fabricates a close).
- **Not modeled, direction stated:** sustain rule + pm/session RVOL + pm-shares floor
  (premarket bars not stored → **over-admits**); earnings cooldown-bypass (U: 51 cooldown
  kills had gap ≥15 — the bypass ceiling; L: 5); float + vol_conviction points (0 → up to
  −10 raw = **under-admits**); per-tick shortlist churn (one tick/day → cap binds **tighter**
  than live); breakers/max-5/loss-limit (per spec D6 — per-signal expectancy only);
  `validate_orb_entry`'s ORB-range > 1.5×ATR14 reject — measured post-hoc: it would remove 3
  of U's 194 scored rows (their mean +0.12R ≈ cohort mean; U mean unchanged at +0.14R).
- Pipeline: `scripts/probes/_bt_run1_admission.py` + `_bt_run1_replay.py`; captures under
  `/Users/alvinfung/.claude/jobs/6b173ac9/tmp/bt_*` (4 read-only pulls, captured once).

## §2 · The funnel — where the 4,453 go

| stage (code order) | Run L kills | Run U kills | surviving (L / U) |
|---|---|---|---|
| population (n=4,453) | — | — | 4,453 / 4,453 |
| universe floors (price/vol/len/SKIP) | 0 | 0 | 4,453 / 4,453 |
| **security type (not CS/ADRC 1,610 + unclassified 10)** | 1,620 | 1,620 | 2,833 / 2,833 |
| **shortlist cap (top-20/day by prescore)** | 1,104 | 1,104 | 1,729 / 1,729 |
| cooldown 60d (self-consistent, no bypass) | 29 | 184 | 1,700 / 1,545 |
| extension ≥50% over 5d min close | 167 | 157 | 1,533 / 1,388 |
| ADV$ filter (no-data 51 · <$1M 229) | 280 | 280 | 1,253 / 1,108 |
| ATR14 > 15% | 140 | 125 | 1,113 / 983 |
| mcap < $500M (current-mcap read) | 38 | 38 | 1,075 / 945 |
| score bar (presented ≥ 65) | 1,051 | 591 | 24 / 354 |
| post-grade M&A | 0 | 5 | 24 / 349 |
| **ADMITTED (HIGH)** | — | — | **24 / 349** |
| ORB window (evidence ≥ 09:45 only) | 4 | 54 | 20 / 295 replayable |

- **Two stages do most of the work and neither is the score:** the security-type gate removes
  36% of the population (n=1,620 — the handed population's ETF screen was far weaker than the
  live gate), and the 20/day shortlist cap removes 39% of what remains (n=1,104). The cap is
  the single biggest *discretionary* stage — and this run models it tighter than live (one
  tick/day vs per-tick unions).
- The bracket construction leaks slightly: 6 L-admitted ticker-days are not in U (U's earlier
  alerts put tickers on cooldown that L's sparser history did not). Counted, not hidden.

## §3 · Expectancy — the numbers

**Scored = filled trades only** (never_triggered and no_bars carry no R by construction).

| run | replayed | never_triggered | no_bars | scored n | **mean R** | **median R** | total R | win% | ex-best+worst mean |
|---|---|---|---|---|---|---|---|---|---|
| **L** (catalyst-blind) | 20 | 2 | 1 | **17** | **−0.16** | **+0.33** | −2.8 | 53% | −0.29 (n=15) |
| **U** (catalyst-generous) | 295 | 85 | 16 | **194** | **+0.14** | **+0.33** | +27.5 | 55% | +0.06 (n=192) |

**Exit reasons (the split the operator asked for):**

| reason | L (n=20) | U (n=295) | meaning |
|---|---|---|---|
| stopped | 8 | 85 | full −1.0R each |
| target (+2R partial fired) | 9 | 106 | U: 82 ended exactly +0.33R (runner back to breakeven), 24 runners > +0.33R (median +1.98R) |
| held_to_close | 0 | 3 | +0.10 / −0.10 / −0.77R |
| never_triggered | 2 | 85 | ORB high never hit by 09:59 — no trade, no R |
| no_bars | 1 | 16 | coverage gaps, counted not fabricated |

**Single-big-mover check (standard §5) — this is the crux:** U's +0.14R mean is carried by
AOSL 04-14 (+16.1R) and BABA 07-08 (+12.9R). Ex-top-1 **+0.06R** (n=193), ex-top-2
**−0.01R** (n=192), ex-top-3 **−0.05R** (n=191). Both tails come from the 2/3 runner held up
to 40 sessions behind a breakeven stop — the harness deliberately does not model the live
SMA10/20 trail (its own docstring flags this), which cuts both ways: a trail would exit
runners earlier (smaller right tail) but also lock gains the breakeven stop gives back (82 of
106 targets round-tripped to exactly +0.33R). The tail shape is a model property, not an
observation.

**Splits (Run U, scored rows only; sub-10 cells state it):**

| month | n | mean R | median R | | gap band | n | mean R | median R |
|---|---|---|---|---|---|---|---|---|
| 2026-04 | 48 | +0.66 | +0.33 | | 9–10% | 26 | +0.80 | +0.33 |
| 2026-05 | 65 | −0.34 | −1.00 | | 10–15% | 84 | +0.07 | +0.33 |
| 2026-06 | 14 | −0.43 | −1.00 | | 15–20% | 49 | 0.00 | +0.33 |
| 2026-07 | 25 | +0.51 | −1.00 | | 20+% | 35 | +0.01 | −0.10 |
| 2026-08 | 42 | +0.27 | +0.33 | | (Run L cells all n<10 except 10–15% n=9 — too few to judge) | | | |

Run L's cohort (n=24 admitted) is worth naming: it is the deterministic-max slice — mega-liquid
(ADV$ ≥ $500M), in-theme, Bull-regime names (ARM, INTC, AMD, MU, MRVL, GEV, BABA-class). L is
NOT "the strict version of the system"; it is what clears a 65 bar with zero catalyst. Its n=17
scored is under the spec's ~30-fill line: **no verdict is drawn from L alone.**

## §4 · Mechanism check (spec §6 acceptance, adapted to the $0 scope)

- Harness self-tests + both mutation tests: green this run (bracket math pinned; the stop-math
  cent-level pin vs AMLX/MRNA/MRVL was verified in the SSoT change log on 08-18/19).
- **Current-era reproduction, Run U vs actual live alerts:** 08-27 modeled
  {CHRN, CRM, CRWD, OKTA, VEEV} vs actual {CHRN, CRWD, DG, OKTA, VEEV} — 4/5 overlap
  (n=5 modeled). 08-28 modeled 5 vs actual 1 (SOLS — caught). The over-admission is exactly
  U's construction (strong-catalyst-for-all); the misses (DG) and extras (CRM, AFRM, ESTC,
  GAP, UMC) are catalyst/judge/RVOL differences — the three inputs this run does not have.
  n=2 days: a mechanism check, not a statistic.
- Bracket sanity: L ⊆ U holds except the 6 cooldown-shadow rows (§2, counted).

## §5 · Adversarial — what would make this wrong the way the retracted one was

- **Defect A — caught inside this run (the retraction class, live demonstration):** the first
  pass trusted the handed population's "ETF screen" and did not re-apply the live
  security-type gate. Two leveraged ETPs (BMNG +90.5R, BMNU +39.7R, both 04-22) sailed
  through and alone put Run U's mean at +0.70R — **five times** the corrected +0.14R.
  `mi_security_types` says ETF for both; live skips them. The number you are reading survived
  that check; the first number did not. Residual: today's security-type table is not
  April's — names classified since then pass here but were skipped live then (over-admit),
  and vice versa for delisted names (10 unclassified kills, counted).
- **Is the surviving cohort an artifact of unreconstructible inputs? Partly, yes — quantified:**
  the L/U spread (−0.16 vs +0.14) IS the catalyst reconstruction gap, and the sign lives
  inside it. U's 08-28 check (5 modeled vs 1 actual) shows U over-admits materially. Anything
  downstream of the score bar inherits this. The honest conclusion is the band, not a point.
- **Lookahead audit:** every accessor reads strictly before D (§1). Three named exceptions:
  current mcap (38 kills ride on it), current security-types, and `scanlog_max_gap` includes
  ticks to 09:59 (can exceed the by-09:44 gap by a hair — affects only the ≥10/≥15 gap
  branches, not the ≥9 floor). The ORB-window gate uses first-qualifying-tick times where
  logged; 422 scanlog pairs lack tick times → assumed in-window (over-admit, counted).
- **Do the uncovered ticker-days correlate with anything? Plausibly yes:** 16 of 295 U-replayable
  (5.4%) had no usable bars — above the spec's ~5% line, so the flag is raised: bar absence
  correlates with delisting/thinness, i.e. with BAD outcomes, so the scored mean is likely
  flattered by their absence. One-sided, stated.
- **Simulator artifact in the tails (T6):** the 40-session no-trail runner produced both +16.1R
  and 82 exact-breakeven round-trips. Neither is what the live exit engine (SMA trail,
  Day3-5 partial, giveback floor) would have done. The median is robust to this; the mean is not.

## What this does not answer (§6)

- **The sign of today's EP expectancy.** That is the point: L and U disagree (−0.16R vs
  +0.14R), so the $0 path's honest output is the band plus the direction of each missing
  piece. Collapsing it = Stage 1b, ~$40 (ceiling $60), operator sign-off required — not spent.
- Anything the judge decides (29% of live tier verdicts), the sustain/RVOL/pm-shares gates,
  the earnings cooldown-bypass, portfolio-level truth (breakers, max-5, loss limits), or
  execution reality (slippage, partial fills — entries fill at exactly ORB high here).
- Whether a DIFFERENT rule set would be better — this measures today's manifest, descriptively.
- What the live trail exit would have earned on the 24 runners — needs the `exit_logic.py`
  integration the spec's full build (D7) calls for; this harness models hard-stop/+2R/breakeven
  only, flagged.
- Run L's slice as evidence of anything (n=17 scored — under the line, stated).

## §7 · ⚖ THE LINE

Evidence only. Nothing here changes or proposes changing any strategy, entry/exit discipline,
sizing, target, or safeguard. Any action on these numbers — including spending the ~$40 to
collapse the band — is the operator's decision alone.
