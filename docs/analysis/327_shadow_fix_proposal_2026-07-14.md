# #327 anticipate-entry — shadow-fix proposal (2026-07-14, for operator sign-off)

**Diagnostic:** `docs/analysis/327_anticipate_diagnostic_2026-07-14.md` (Fable-run, Opus-verified).
**Headline:** the coil-breakout setup is NOT dead — the −1.04R (blend) is anticipate **−1.23R (N=34)** +
Confirm ~breakeven; the shadow *replicated* the offline validation (41% capture vs 44%). We mechanized
the coil's **timing** but not the trader's **selection stack + risk geometry + the anticipate-vs-confirm
choice.** That's the gap — not an absent edge.

## ⚠ Two honesty caveats (do not overweight the diagnostic)
- The **+0.41R counterfactual** (quality-gate + stop-fix flips it positive) is **IN-SAMPLE / post-hoc**
  (N=14, one June fortnight, PRIM = ⅓ of the loss). *Suggestive* the setup isn't dead — NOT proof.
  Validate **FORWARD through a trending leg**, never act on the in-sample flip.
- Fable's flagship "SQQQ inverse fund at −1.95R" was **factually wrong** (verified: SQQQ is 1 row at
  **+2.00R**, a winner). So the "21% ETFs" magnitude is **unverified** — the RS/trend-location lever is
  *directionally* plausible but its size must be re-derived on clean data before trusting it.

## Proposed shadow changes (ALL shadow — no live money; a live flip is separately operator-signed)
1. **Quality gate** — via a `would_pass_quality` flag (BOTH cohorts keep accruing so we A/B it): stocks-only
   (no ETFs/ETPs), above the 50-SMA, RS floor ~60–70, ADV ≥ $5M. Rationale: winners' median RS 72 vs
   losers' 53; sub-50SMA "coils" are bear-bounces. *(Re-verify the magnitude — the ETF claim was wrong.)*
2. **Risk geometry** — make `structural_low` the headline stop **with a floor** (reject sub-1% `coiled_low`
   fires; min observed was 0.06%). Rationale: 64% of the loss was gap-through-stop slippage beyond −1R.
3. **Anticipate → Confirm** — wire the **Confirm arm** (enter ON the confirmed `base_high` breakout +
   volume, stop = base_low) as a **tagged control arm**, measured forward. Rationale: ~85% of anticipated
   coils never broke out; anticipating pays for false coils. This is the operator's "entering too early" gap.
4. **Record regime-at-entry** on every row (the regime-gate question is unanswerable until we accrue a
   trending leg — all 34 entries were the June roll-over).
5. **Fix the measurement bounds** — the capture (target-first) vs realized (stop-first) metrics measure
   opposite bounds; align the horizon so a "capture" isn't reported alongside a negative realize.

## Blocker (fix FIRST — nothing on #327 progresses until this clears)
The `consolidation_readiness` settlement job **HUNG >2h and aborted 7/13** (last insert 7/10; **170 rows
stuck past-ripe**, incl. the Confirm-arm rows the diagnostic needs). Suspect: an unbounded Polygon call in
the readiness scan's #387 M&A guard (`get_polygon_news`/`get_ticker_details`). Fix direction: firm
per-call timeouts + a per-run time budget so one hung fetch fails-open instead of blocking the whole job.
Watch tonight's 21:35 UTC run to confirm persistent-vs-transient; the 170-row backlog must settle.

## Sign-off asks
- [ ] Approve the 5 shadow changes (build as shadow, A/B via the flag, validate forward)
- [ ] Approve fixing the hung settlement job (defensive timeouts/budget) as the first step
- [ ] Acknowledge: the +0.41R is in-sample; the live flip waits on FORWARD data through a trending leg
