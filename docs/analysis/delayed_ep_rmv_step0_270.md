# #270 STEP 0 — RMV on the cohort + the stop-placement finding (durable, for re-review)

**Status: DIRECTIONAL (N small, one window, in-sample). Nothing load-bearing — all parameters
remain up for scrutiny (operator 6/16). RMV is RECORDED TELEMETRY; the STOP is now a first-class
tuning candidate.** Reproduce: `python scripts/_270_rmv_cohort_probe.py` (gate-free, read-only;
reuses the anticipation replay's lifecycle + `find_coiled_days` + the REAL `flag_detector._compute_rmv`
via a `{h,l,c}→{high_price,low_price,close}` key-adapter — no reinvention).

## Why this exists
Operator directive (6/16): reuse RMV (our built DeepVue/TraderLion contraction index) as the #270
coil metric, and **"see how it performs"** before wiring it. Telemetry-first per CHANGE_PROCESS:
measure on our cohort, don't assume. This doc is the durable record so the conclusion can be
re-checked as data accumulates (the RMV-miss lesson: don't let a finding go stale unrecorded).

## Cohort
134 huge-gap tickers → 30 ARMED → 11 presented ≥1 coiled day → 19 entered coiled-entries
(stop-and-reenter) / 50 coiled days total. `find_coiled_days` = reclaimed gap_day_low & SMA20 +
range ≤7% + vol ≤1×ADV20 (+ `base_run` maturity). RMV computed at each coiled day.

## Finding 1 — under the coiled-low stop, RMV-low does NOT help; it INVERTS
| coiled-entry outcome | n | med `rmv_5d` | med range% | med \|close%\| |
|---|---|---|---|---|
| win (held into breakout) | 5 | **90** | 6.0% | 2.94% |
| stop (shaken) | 14 | **5** | 4.9% | 1.35% |

Win% by `rmv_5d`: ≤10 → 11% · 10–30 → 33% · >30 → 43%. i.e. the **deepest contraction (RMV floor)
entries get shaken**; the relative-widening (RMV turning up) entries win. Naively this said
"RMV-low is worse for entry." **But that read is confounded by the stop** (Finding 2).

## Finding 2 (operator's hunch 6/16, CONFIRMED) — it's a STOP artifact, not setup quality
A deeply-contracted (RMV≈0) day has a tiny range, so the **coiled-low stop sits ~2% under entry**
→ noise shakes it. Single-shot outcome by **stop × rmv_5d bucket** (all 50 coiled days; R is
**MFE-ceiling**, an upper bound — see caveat):

| stop | med risk% | rmv≤10 | rmv 10–30 | rmv>30 | ALL |
|---|---|---|---|---|---|
| `coiled_low` | 2% | 9/27 −1.0R | 1/3 −1.0R | 6/20 −1.0R | **16/50 −1.0R** |
| `coiled_low − 0.5·ATR` | 6% | 17/27 +1.3R | 2/3 +3.6R | 10/20 +0.8R | **29/50 +1.3R** |
| `gap_day_low` | 6% | 14/27 +0.6R | 2/3 +2.8R | 11/20 +0.6R | **27/50 +0.6R** |
| `fixed −8%` | 8% | 18/27 +1.6R | 2/3 +3.5R | 12/20 +1.1R | **32/50 +1.4R** |

For the low-RMV bucket the win-rate goes **33% → 63–67%** as the stop widens from coiled-low to an
ATR-buffered / structural stop. **The coiled-low stop was cutting winners that recover to the
breakout.** So: the inversion in Finding 1 is a stop-placement artifact; **the STOP is the dominant
lever, and coiled-low is too tight.** This matches the SSoT's structural-reference idea (gap_day_low
is the U&R selling-guide) — the anticipation model's coiled-low stop is the outlier.

## Caveats (keep honest — nothing is 100%)
1. **R is MFE-ceiling** (favorable-excursion / risk), NOT harvested. A wider stop wins MORE OFTEN but
   banks LESS R per win (bigger risk denominator; a +1R target is further away in %), so these R
   numbers **overstate** the wider-stop edge. The clean signal is the **win-rate** (tight stop has a
   high false-shake rate). The **harvested-R** comparison (W3 exit ladder, the +1R/+3R scale-out on
   each stop width) is OWED before trusting magnitude — that's the real arbiter of optimal stop width.
2. **Single-shot ≠ Pradeep's tight-stop + RE-ENTER** model (the coiled-low stop is deliberately tight
   in his "fail fast, re-enter, one pays for ten" tactic). This isolates the stop; it is not the full
   tactic. The two are competing exit philosophies to settle on harvested R.
3. N=50 coiled days / 5 wins / one window / in-sample → DIRECTION only.

## What's recorded vs what stays telemetry
- **RMV (`rmv_5d`/`rmv_15d`)** → RECORDED on the lifecycle row, NOT a gate. Its plausible real role is
  at READINESS level — *RMV turning up off its floor* as a breakout-imminence cue (consistent with #54:
  low-RMV *precedes* a breakout). Test at N≥10; do not gate on RMV-low.
- **Pradeep `|close %change|`** → recorded as `tight_close_pct`. 0.4% fires on only 16% of our coiled
  days (median coiled-day move 1.35%); the our-universe-calibrated tight value is ~1.4%, not 0.4%.
- **STOP placement** → promoted to a first-class **tuning candidate** for the W3 exit/stop layer
  (coiled-low vs ATR-buffered vs structural gap_day_low). Gated on harvested-R confirmation + N≥10 +
  operator sign-off (CHANGE_PROCESS). The deployable records entry+stop+forward bars so realized R can
  be derived per stop width offline.

## Open questions (revisit as data accumulates)
1. Optimal stop width = the harvested-R tradeoff (higher win-rate vs lower R/win) — owed at N≥10.
2. RMV's real role: readiness "turning up" cue vs nothing — test once the shadow logs RMV forward.
3. Tight-stop+reenter (Pradeep) vs wider-structural-stop single-shot — harvested-R head-to-head.
