# #394 — Coil-finder tuning methodology (Fable block 1 Tier-2, 2026-07-11)

**Status: METHODOLOGY DESIGN — the tune itself waits for forward-shadow N (the market's clock).**
This defines WHAT gets measured, the decision rules, and the N-gates so the tune is a mechanical
Opus/Sonnet execution the day the data is sufficient — no design fork left. Amends ADR 0013's
coil-finder (changelog entry on tune day, CHANGE_PROCESS; operator sign-off on the tables).

## 1. What's being tuned (and what is NOT)

Three knobs, tuned against SETTLED forward-shadow evidence (`mi_consolidation_entry_shadow` +
the daily 🪙 board history), never against the n=5 build cohort (operator's anti-overfit rule):
1. **The ~50% hold cap** (share-of-base-days-holding-tight admission gate).
2. **The board rank ordering** (which metric sorts the 🪙 board).
3. **The orderliness metric + demotion** (new — defined below; ships as *ranking demotion*
   first, never a hard gate on day one).
NOT in scope: the runup gate (15%/10d — signed), RMV floors/ceilings (recalibrated 6/27), the
entry mechanics (ADR 0013/0026 own those).

## 2. N-gates (the "when")

- **Primary gate:** ≥20 SETTLED shadow rows (entry-fired candidates with realized R on corrected
  bases) — wired as data-gated review `coil_tuning_ready` (predicate on the settled count;
  earliest +14d from wiring). Board-only candidates (never fired) count toward ordering/
  orderliness analysis but not the hold-cap sweep.
- **Per-knob honesty:** any knob whose decisive cell has N<10 stays UNCHANGED that round; the
  review re-arms +3 weeks. Partial tunes are fine (ordering may resolve before the cap does).

## 3. Decision rules (mechanical on tune day)

### 3a. Hold cap
Sweep {40%, 50%, 60%} over the settled cohort: for each value, the admitted subset's median R +
win rate + admitted-count. **Rule:** move to the plateau value maximizing median-R without
cutting admitted-count >30% (recall guard — the cap exists to drop junk, not to starve the
board); knife-edge results (adjacent cells disagree in sign) = no change + re-arm.

### 3b. Rank ordering
Candidate orderings, computed per candidate at detection (all already derivable from stored
fields — no new capture): (i) current composite, (ii) RMV-tightness-led, (iii) tight-close-count
-led, (iv) orderliness-penalized composite (3c). **Rule:** Spearman rank-correlation of each
ordering vs settled R at N≥20; adopt the winner only if its correlation beats the incumbent by
≥0.15 (a real gap, not noise churn); report the top-5-board composition delta so the operator
sees what visibly changes.

### 3c. Orderliness (the gappy-coil metric)
**Definition (per the operator's correction — overnight character, not intraday ADR):**
per base day `d`: `overnight_gap_pct(d) = |open(d) − close(d−1)| / close(d−1)`. The candidate's
**orderliness score = P95(overnight_gap_pct over the base window) ÷ ATR14%** — a coil whose
overnight prints rival its daily volatility is held together by luck, not supply absorption.
- **Phase 1 (ships with the tune):** record + display the score on the 🪙 board (visibility).
- **Phase 2 (demotion, only IF evidence):** if the settled cohort at N≥10-per-side shows
  orderliness-top-quartile candidates underperform the rest by ≥0.5R median → orderliness joins
  the ranking as a demotion term (ordering (iv)). NEVER a hard admission gate in this cycle —
  a gate needs its own later review with a named false-kill check.

## 4. Cards (executable on `coil_tuning_ready` firing)

- **C1 — the tune probe** `scripts/probes/_394_coil_tune.py` (read-only: the 3a sweep table +
  3b correlation table + 3c quartile table; verdict line per knob per the rules above).
- **C2 — apply the verdicts** (constants + board ordering + orderliness display; ADR 0013
  changelog + this doc's status flip, same commit; instant-revert env for the ordering).
- **C3 — re-arm** (`coil_tuning_ready` recurs +6 weeks — thresholds re-checked once per regime
  change, the quarterly-rule-review discipline).
DoD (#394): C2 landed with operator-signed tables = "cap tuned + orderliness decided."

## 5. Optional (unchanged from the task): long-base peak-detection accuracy — stays LOW-pri,
not part of this methodology (aged>20 already bounds the harm; PTGX confirmed absent).
