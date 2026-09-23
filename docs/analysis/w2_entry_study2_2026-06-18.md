# W2 Entry Study #2 — stop geometry (2026-06-18)

**VERDICT: the live ORB-low stop is the best tested geometry — NO change proposed.**
Widening the day-1 stop (atr-floor / prior-day-low) monotonically degrades both
expectancy and total $ in the *trustworthy* direction; the one marginal arm
(atr-cap, tighter) is noise-level, barely operated (9% coverage), and sits in the
*suspect* (sim-flattered) direction. Confirmatory result: the current rule holds.

## Method

Harness: `selection_replay_268.py --simulate --stop-model M --stop-atr-k K`
(knob added this study). Each arm holds selection / entry / exit-model FIXED and
varies ONLY the **day-1 stop**, which is threaded into **both** the risk-based
position sizing AND the exit — so every arm risks the same $ and R is comparable
(advisor 2026-06-18; `_position_size` is risk-based off `entry − stop`, so an
exit-only change would make R meaningless). `resolve_entry_stop` (filters.py, 9
unit tests):

- **orb_low** — the live MAGNA53 stop (baseline).
- **atr_floor K** — WIDEN too-tight ORBs to ≥ K×ATR below entry (`min`; only widens).
- **atr_cap K** — TIGHTEN wide ORBs to ≤ K×ATR below entry (`max`; only tightens).
- **day_low** — the prior trading day's low (structural, 9M-analog).

Pre-registered discipline (carried from study #1's two artifact catches):
- **Coverage** — % of trades the model actually changed the stop on (a model that
  no-ops on the good segment and acts on the bad one manufactures lift).
- **Outlier decomposition** — drop the top-5 winners; the edge must survive.
- **Fidelity asymmetry** (pre-registered BEFORE reading numbers) — 1-min IEX bars
  under-count intra-bar stop-outs, so the sim **flatters tighter stops**. A
  **wider**-direction result is trustworthy; a **tighter** one is suspect.

## Result — judge-HIGH arm (n=44)

| arm | n | exp | win | sumR | total $ | stopout | coverage | expDrop5 | sumRDrop5 | Δ vs base |
|---|---|---|---|---|---|---|---|---|---|---|
| **baseline (orb_low, live)** | 44 | **+1.40R** | 39% | +61.7 | **+$20,890** | 59% | 0% | −0.03 | −1.3 | — |
| atr_floor 0.5 | 44 | +0.66R | 39% | +29.2 | +$19,255 | 57% | 34% | −0.12 | −4.7 | ΔR −0.74 / Δ$ −1,635 |
| atr_floor 1.0 | 44 | +0.48R | 43% | +21.3 | +$13,810 | 41% | 91% | −0.16 | −6.4 | ΔR −0.92 / Δ$ −7,080 |
| atr_floor 1.5 | 44 | +0.27R | 43% | +12.0 | +$9,729 | 30% | 100% | −0.18 | −7.1 | ΔR −1.13 / Δ$ −11,161 |
| day_low | 44 | +0.14R | 43% | +6.0 | +$4,375 | 7% | 100% | −0.10 | −4.1 | ΔR −1.27 / Δ$ −16,515 |
| atr_cap 1.0 *(suspect dir.)* | 44 | +1.45R | 39% | +63.6 | +$22,692 | 59% | **9%** | +0.01 | +0.6 | ΔR +0.04 / Δ$ +1,802 |

## Reading

1. **Widening the stop is decisively worse, monotonically** (0.5 → 1.0 → 1.5 →
   day_low: +0.66 → +0.48 → +0.27 → +0.14R; total $ +19.3k → +13.8k → +9.7k →
   +4.4k). This is the **trustworthy** direction — the sim does NOT flatter wider
   stops — so it is a credible refutation, not an artifact.
2. **Mechanism (the stopout column).** Wider stops DO cut stop-outs (59% → 7%),
   but the trade is a bad one: the surviving winners pay smaller R-multiples (the
   risk denominator grew) AND fewer total dollars, because the Day-2 SMA-trail /
   EOD exit doesn't run far enough to earn back the wider risk. The tight ORB-low
   stop is integral to the momentum profile — cut at −1R, let the *tail* pay.
3. **atr_cap (tighter) is NOT shippable** despite the +0.04R / +$1,802 headline:
   it is noise-level, **operated on only 9%** of trades (the few with an ORB wider
   than 1×ATR), sits in the **suspect** direction (intra-bar stop-outs the 1-min
   sim can't see — the LYG one-cent-ORB class), and its edge is entirely top-5
   carried (expDrop5 +0.01 ≈ 0). It selects the same tail-concentrated, sim-
   flattered class study #1's skip-wide-open did.
4. **Every arm is tail-carried** (baseline expDrop5 = −0.03): drop the top-5
   winners and even the live stop is ~break-even. This is the correct
   Qullamaggie/momentum shape (confirmed at the cohort level in Phase B,
   +0.95R judge-HIGH), NOT a stop-geometry artifact — it just means no stop model
   can be judged on the body; the tail decides, and widening shrinks the tail's R.

## Caveats (do NOT overclaim)

- **Cohort = the RETAINED judge-HIGH window, n=44, NOT the full Phase-B year.**
  `mi_ep_alerts` is pruned to 2026-03-16+ (#341 retention class), so the stored
  judge verdicts for 2025-06…2026-03 are gone; the judge-JOIN can only see ~7
  weeks (2026-03-16…05-04). The 1-month smoke (n=30) and this run (n=44) overlap
  heavily and agree on the monotonic degradation, so the **direction is robust**,
  but the absolute n is modest.
- **VALIDITY ANCHOR — the within-study comparison is EXACT regardless of n.** The
  stop model is applied at the entry (engine line 118) *after* the breakout / skip
  gates, so it **never changes which trades enter** — all six arms run the
  identical 44 trades on the identical price paths; only the stop (and its risk-
  based share count) differs. So the small/pruned cohort weakens *generalization*,
  not the *relative* ranking of the arms.
- **Why no-change survives the small-n (structural, not a data assertion):**
  (a) the winner-R compression is near-mechanical — risk-based sizing means a wider
  stop = fewer shares = smaller R *and* fewer dollars on the tail winners that
  carry the strategy, for the same path; so widening's only possible rescue is a
  bounded reduction in −1R stop-outs. (b) The 4-level **monotonic ladder**
  (+0.66 → +0.48 → +0.27 → +0.14R) is not what n=44 sampling noise produces —
  noise doesn't ladder. (c) A second-order mechanic actually *flatters* the wider
  arms (survivors get their Day-2 floor raised to `day1_low`, tighter than their
  wide entry stop) and they still lost. The *net* degradation's magnitude is
  empirical (the loser-side recovery rate is where small-n bites), but the
  mechanical compression caps how much a fuller cohort could plausibly move a
  +1.40-vs-+0.14R gap.
- **REGIME-LOCALITY + near-circularity (the real scope limit).** The retained
  window is ONE recent, likely trend-favorable regime — and it is largely the same
  tape the live ORB-low stop just traded, so "recent cohort confirms recent stop"
  is weak *independent* confirmation. Stop geometry is plausibly regime-dependent
  (a wider stop may earn its keep in chop). So the earned claim is **"ORB-low holds
  in the recent regime,"** not "stop tuning is dead forever."
- **1-min IEX-bar sim**, ~47% scan recall, single pass (same as Phase B / study
  #1). Directional, not a pinned live number.

## Decision & follow-ups

- **No live stop change.** ORB-low holds; the kill/scale bands (signed,
  calibrated on the orb_low R-distribution) need **no re-derivation** — the
  winning geometry IS orb_low.
- **RECOMMENDATION (regime-conditioned, not a finding): pause the W2 "tune the
  bracket" thread.** The two W2 entry-mechanics studies (5-min OR #1, stop geometry
  #2) both found the live geometry best *in the recent retained regime* — OR-window
  and stop placement each tested, neither beat the live rule. That makes
  entry-mechanics a low-EV place to keep digging *right now*, so the recommendation
  is to deprioritize it, NOT a proven "the edge isn't here." The evidence is n=44
  over a single ~7-week window that overlaps the tape the live stop already trades
  (regime-locality + near-circularity, see Caveats) — too narrow to retire the
  question. Re-open it on a regime shift (the kill/scale band review, or a chop
  regime where a wider stop could earn its keep).
- *Only if* a stop change is ever seriously contemplated: re-judge the full
  Phase-B window first (paid re-grade — the verdicts were pruned) to lift n. Not
  warranted by this confirmatory result.
- Re-run command (durable): `selection_replay_268.py --simulate --stop-model
  atr_floor --stop-atr-k 1.0` (etc.) → `_w2_stop_geometry_analysis.py --arm …`.
