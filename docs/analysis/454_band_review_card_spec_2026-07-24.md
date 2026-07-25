# CARD SPEC — kill/scale band review, pulled forward (#454 remaining item)

**Assignee: Fable** (complex analysis, per the CLAUDE.md operating model).
**Status: SCOPED, NOT RUN.** Operator to launch.
**Deliverable: a decision-ready keep / retune / park recommendation for operator sign-off — NOT a live
flip.** The bands govern the live-money KILL→paper decision; any change is THE LINE (CHANGE_PROCESS +
sign-off + `safeguards.md` change-log entry).

## Why this is being pulled forward

Approved by the operator 2026-07-19 off the #454 part-2 finding: the `CALIBRATION_ENVELOPE` behind the
signed bands is **Bull-conditional, mechanically** — the "12-month mixed-regime window" was ~94% Bull
by trading days, and its entire non-Bull content is ONE contiguous 3-week episode (the March-2026
crash, ~21 of 399 cohort trades). The bands are **known-mispriced for non-Bull regimes**, so waiting
for the scheduled 8/01 review was judged wrong.
Source: `docs/analysis/454_regime_stratified_envelope_2026-07-17.md`.

## ⚠ The constraint that shapes the whole card — read before scoping any work

**There are 9 closed live trades.** The bands are silent below 20 (~3 months at the live rate).

> **The card must NOT attempt to re-derive or retune the bands from the live cohort.** n=9 against a
> band set calibrated on n=399 would be noise dressed as evidence, and it is exactly the single-case
> overfitting `CHANGE_PROCESS.md` rule 1 (N≥10 minimum) and the parabolic ship→revert→restore scar
> exist to prevent. If the analysis concludes "retune," it must clear that bar on its own stated
> evidence, not on the live cohort's 9 rows.

What this leaves is still substantial: three of the review's four inputs do **not** need n=20.

## Scope — the four review inputs (`data_gated_reviews.yaml::kill_scale_bands_quarterly_review`)

| # | Input | Reachable at n=9? | What the card should produce |
|---|---|---|---|
| (a) | Live closed-trade R-distribution vs the Phase-B envelope | **No — blocked at n=9** | State the block explicitly + the date/trade-count at which it unblocks. Report the 9 rows descriptively (no inference). |
| (b) | P6 replay-regression weekly reports — divergence between the accruing replay and the calibration | Yes | Is the accruing replay drifting from the signed envelope, and in which direction? |
| (c) | Override log — `kill_scale_override` audit rows + `safeguards.md` change-log | Yes | **Repeated overrides in one direction ⇒ the bands are mis-set — recalibrate rather than keep overriding.** Count and direction them. |
| (d) | Demote-side watch-metric — judge-demoted cohort forward R (Phase B showed demotes averaging **+1.01R**, i.e. NOT reliably saves) | Yes | Has the demote-side signal held or inverted since? |

## The real question to rule: the regime-conditionality fork

`454_regime_stratified_envelope_2026-07-17.md` §5 leaves three options. **The card's primary job is to
recommend one, with reasoning — not to pre-decide it.**

- **(a) $0-LLM partial re-cut** — re-run `--scan` + `--simulate` only (both deterministic, no LLM
  spend), stratify the ALL-candidate outcome distribution by regime. Answers "does regime move raw EP
  outcomes?" without grade/judge spend. ⚠ **NOT read-only** — re-inserts `historical_scan` rows and
  loads Polygon. Needs its own go-ahead.
- **(b) Full paid re-run** (~2×1,300 LLM calls) to re-cut the judge-HIGH cohort per regime. Per
  [[rigor-before-paid-eval-spend]]: **only if (a) shows a regime effect worth pricing.** The card
  should not recommend (b) directly.
- **(c) Prospective accrual** — let the live cohort stratify itself; $0, slowest, measures the real
  system.

## Hard constraints

1. **Read-only by default.** Prod access is SELECT-only. Option (a) is write-side — recommend it, do
   not execute it.
2. **No live flip. No threshold change.** Deliverable is a recommendation for sign-off.
3. **CHANGE_PROCESS rule 3** — if a retune is recommended, present the affected decisions for the
   operator's judgment; do not self-classify them as correct.
4. **Single-regime honesty.** Any number derived from the 05→07 window inherits the same
   Bull-conditional caveat this card exists to address. Say so inline rather than in a footnote.
5. **Verify against primary source.** Numbers come from prod SELECTs or the named scripts, not from
   the prose of prior docs — several claims in the register have already gone stale.

## Deliverable

`docs/analysis/454_band_review_<date>.md`:
1. TL;DR — keep / retune / park, one line.
2. The n=9 block stated up front, with its unblock condition.
3. Findings for (b), (c), (d), each with the SQL or script that produced it.
4. Recommendation on the §5 fork, with reasoning.
5. Open forks for the operator, in the "fork + 1-line rec" format.
6. Anything the card could not reach, named — no silent gaps.

## Pointers

- `agents/market_intelligence/kill_scale_bands.py` — `CALIBRATION_ENVELOPE`, band logic
- `docs/setups/safeguards.md` — signed bands + change-log (KILL/SCALE table)
- `docs/analysis/454_regime_stratified_envelope_2026-07-17.md` — the finding + §5 options
- `scripts/_454_regime_stratified_envelope.py` · `scripts/_killscale_bands_268.py`
- `data_gated_reviews.yaml::kill_scale_bands_quarterly_review`
- prod: `mi_live_trades` (9 closed live), `mi_market_regime`, `mi_audit_log` (`kill_scale_override`)
