# Operator-shared methodology notes (verbatim capture log)

**Why this file exists:** tweets / screenshots / notes the operator shares in chat live only in
conversation context, which gets compacted — and image content is LOST in summarization. They were
not being captured, so critical methodology shared "yesterday" became unrecoverable (operator
called this out 2026-06-16). **RULE (memory `feedback_capture_operator_shared_notes`): the moment
the operator shares a tweet / image / note with methodology, transcribe it VERBATIM here in the same
turn**, with date + source + how it maps to the build. Append-only; newest at top. This is the
durable home that survives context compaction — grep here before asking the operator to re-explain.

---

## 2026-06-16 — Pradeep Bonde (@PradeepBonde / stockbee), full ANTICIPATION thread (posted 2026-06-15)

The complete playbook for the anticipation setup = our #270. Verbatim, in chronological order (each
is Pradeep's post/reply in a Q&A thread; the quoted question is in parentheses where shown):

1. **3:58 PM** — "See my short list for today. Do you see what I look for in anticipation? **Multiple
   tight days.**" Short list: **$COO, $HYLN, $ALHC, $APPS, $NTAP.** (reply Mat: "$NOK $RXT would be
   tight day anticipatory entry today?")
2. **4:48 PM** — "**3 to 5 day hold if they break else close.**"
3. **5:07 PM** — "**All of my selections have recent catalyst and have a first leg of 15% plus in 10
   days or less and are up or down tiny amount today. Have series of tight days.** Does your
   selection meets that criteria?" (reply WatchlistGuy: "After a strong acceleration, I like to see
   the price moving in a tight range for days. Hyln is doing exactly that.")
4. **5:08 PM** — "Today in anticipation" (reply NavsariGuju: "Did you buy any of these today or on
   the break tomorrow?")
5. **5:21 PM** — "**Unless they have catalyst which my analysis shows has long term potential no.
   Exit by end of third 4th or 5 the day or 20% whichever is earlier**" (reply chris: "Do you hold
   anything after 3-5 days or exit fully? And how do you choose the # of days?")
6. **5:42 PM** — "**I use time stop. If the stock does not move, I close.**" (reply ursachi: "How do
   you manage names that hold near day-one highs for the next 3+ days? No movement whatsoever but
   staying close to entry and increasing gap risk day over day")
7. **5:59 PM** — "**I just move my stops aggressively to protect profit if it gaps or breakouts in
   first few minutes so it starts fading you out with profit. Genuine breakouts don't fade so you
   hold for 3 to 5 days.**" (reply EternalCipher: "how are you deciding which one to do a morning
   sell and which ones to hold for 3-5 days?")
8. **7:04 PM** — "**Price percent change today between -.4 and .4. That is the qualifying criteria.
   After that, I look for a series of tight days in the previous two bars. Plus some additional
   criteria like catalyst, and what is the buzz about the stock amongst the popular traders on
   Twitter.**" (reply Poor Pay Rich: "closing prices +/- .4% or actual candle of day within .4%
   range?" → it's the **close-to-close % change**, not the intrabar range.)
9. **7:25 PM** — "**2 quarters in a row of 39% plus sales growth and also projected growth for next
   4 quarters are 39% plus**" (reply Steadfast, re catalysts with long-term potential).

### The setup, decomposed (the canonical #270 spec — from the source)

**SELECTION / readiness (a name qualifies when ALL hold):**
- **Recent catalyst** (ideally long-term — see catalyst quality below).
- **A first leg of +15% or more in ≤10 days** (the prior acceleration/thrust). ⚠ NOTE: BROADER than
  our current WATCHED gate (+40% gap). Pradeep's thrust is a *15%/10d leg*, not a one-day +40% gap →
  our universe is likely too narrow (ties to the generalization + task #15).
- **Up or down only a TINY amount today**: |close % change today| ≤ 0.4% (the qualifying tight bar).
- **A SERIES of tight days** (multiple tight days; "price moving in a tight range for days" after the
  acceleration). Tightness is a RUN, not one day.
- **Buzz among popular traders on Twitter** (social/theme axis).

**CATALYST QUALITY (the long-term-potential bar):** 2 quarters in a row of **39%+ sales growth** AND
projected **39%+ for the next 4 quarters** — strong, sustained, accelerating REVENUE/SALES growth
(reinforces [[user_pradeep_revenue_over_eps]]: revenue is the signal).

**ENTRY:** anticipate — buy on the tight day (the day before), or on the break the next day.

**EXIT / management (derisk fast; catalyst-conditional leash):**
- **3–5 day hold IF it breaks; else close** (no break → close).
- **Time stop:** if the stock does not move, close it (don't let a dead name sit and accumulate gap
  risk day over day).
- **Aggressive stop-trail on a fast move:** if it gaps / breaks out in the first few minutes, move
  stops aggressively to protect profit so it "fades you out WITH profit." Genuine breakouts don't
  fade → you hold those 3–5 days. (This IS the day-0 giveback-trail / two-phase exit we backtested.)
- **Hard cap:** exit by end of day 3 / 4 / 5 OR +20%, whichever is earlier — **UNLESS** it has a
  catalyst with long-term potential, then hold longer. ⚠ This **CONFIRMS the catalyst-conditional
  leash is real Pradeep methodology** — our SSoT had it as "inconclusive / confounded by unsourced
  catalysts." It's not inconclusive in principle; it was just untestable on the backfill cohort.

### ARCHITECTURE — "CONSOLIDATION PLAYS POST A RUNUP" (the family; operator 2026-06-16)
**Umbrella name (operator): "consolidation plays post a runup."** anticipation, flags/continuation, and
U&R-on-the-consolidation are the SAME family (FAMILY A): a runup → a consolidation (tight base/coil) →
entry. Share ONE universe + ONE coil detection (undercut allowed). Differ on ONE axis — **ENTRY MODE
(when you enter):** Anticipate (in the coil, before the break) · Confirm/flag (on the confirmed break) ·
U&R (on undercut of the base/consolidation low → reclaim; tightest stop). EP NOT required for Family A
("anticipation can be from an EP but not necessary").

**U&R is a GENERIC MECHANIC, not a family member** (operator nuance 6/16): "price falls below SOME
reference point → reclaims it." Reference = a consolidation/base low (Family A), an EP low, an MA,
congestion, etc. Reusable across families (`fishhook_detector` + `anticipation.detect_gdl_reclaim` are
reclaim-mechanic implementations). Do NOT treat U&R as owned by one family.

**Fishhook / delayed-EP are FAMILY B (the EP family), NOT Family A** (operator correction 6/16): a
delayed-EP REQUIRES an EP first (fishhook's gap-up IS the EP), then re-enters — often via a U&R on the
EP low. The EP is not an "optional gate on consolidation"; delayed-EP is its own EP-family play. **FAMILY
B = the EP family (MAGNA53 / 9M / delayed-EP / fishhook) = the NEXT rework, SEPARATE** from the current
Family-A build. ⇒ current scope tightens to Family A only; fishhook stays put.

Anticipation is NOT a from-scratch detector — it's a sibling in FAMILY A sharing the substrate. Three
unification decisions:
1. **One shared, well-tuned UNIVERSE for ALL tactics** — a post-runup tightening universe (loose runup
   + liquidity), tuned ONCE, feeding flags + anticipation + others. NOT per-tactic universes.
   "We want a good universe for all tactics." (Folds in #15 + reconciles the flag universe.)
2. **Undercut is OK for BOTH** — the flag detector's "INVALIDATE on undercut" is wrong for flags too,
   not just anticipation. An undercut (U&R) is a valid shape for both. → fix in `flag_detector`
   (detection-criterion change → CHANGE_PROCESS + sign-off).
3. **The difference = ENTRY TIMING on the same coiled candidate — THREE modes** (operator added U&R):
   - **Anticipate** — enter BEFORE the move, in the tightness. Stop = tight-range low. (anticipation entry)
   - **Confirm / flag** — WAIT for the confirmed breakout (base_high + vol). Stop = base/breakout low. (#94)
   - **U&R (undercut & rally)** — undercut the low → RECLAIM it. Stop = the undercut/washout low (TIGHTEST,
     biggest cushion — the U&R paradox). Mechanic ALREADY EXISTS: `fishhook_detector` (gap-up undercut &
     reclaim state machine) + `anticipation.detect_gdl_reclaim`. REUSE it — but on the shared post-runup
     TIGHT universe (higher conviction), NOT fishhook's broad gap-up/low-R harvester universe.
⇒ Build = ONE shared universe → ONE coil detection (undercut allowed) → THREE entry modes. All three
mechanics already exist (anticipation / flag-break / fishhook-reclaim) — the unification is pointing them
at the shared coiled universe. Formalize as an ADR (reshapes flags + anticipation + fishhook). Reconcile:
does fishhook-the-broad-harvester stay separate, or fold its reclaim mechanic into the U&R mode?

### LAYERING — anticipation (a TACTIC) ≠ Stocks in Play (operator 2026-06-16, recurring correction)
**Anticipation is ONE tactic** (runup → tight spot → entry); it produces a ranked candidate feed.
**Stocks in Play is the CONSOLIDATED list across ALL tactics** — anticipation + MAGNA53 EP + 9M-derived
+ flag + … merged (ADR-0004 `mi_stocks_in_play`). The anticipation shortlist is ONE INPUT that feeds
SiP, not SiP itself. Do not call a single tactic's output "Stocks in Play." (I've conflated these
multiple times — stop.)

### VERIFICATION RESULTS — 6 known-good names, as-of 2026-06-15 (read-only probe, 6/16)
Validation set: COO/HYLN/ALHC/APPS/NTAP (Pradeep 6/15) + MNTS. Measured, no thresholds applied.
- **+15% in ≤10d leg: holds 6/6** (COO 15% exactly · NTAP 52 · ALHC 55 · APPS 130 · HYLN 159 · MNTS 265).
  The sourced universe gate WORKS.
- **Universe sources (as-of-6/15, date-filtered — not "ever"):** flag_candidates has all 6 but only as
  **WATCH (APPS/HYLN/MNTS/NTAP) / unqualified (COO/ALHC)** — its TIGHTENING/COILED classification fired
  for NONE. 9M alerts = **2/6** (APPS 6/9, MNTS 6/11). EP alerts = **0/6** in window. multiple-9M cohort
  = **0/6**. ⇒ **9M/multiple-9M are TOO SPARSE to be the universe** (refuted). The flag WATCH list is the
  closest existing post-runup radar (all 6), but its tightening gate MISSES genuinely-tight names.
- **Tightness must be VOLATILITY-RELATIVE (stock character), not absolute:** COO/ALHC/NTAP tight by
  RMV+range (rmv5 0-19, range 2-4%). HYLN/MNTS are "tight" only RELATIVE to their own 159%/265% legs
  (range 12%/28% absolute). Absolute range fails; the ≤0.4% close-streak is far too strict (all 0-1);
  RMV closer but imperfect (HYLN rmv5=37, MNTS=33). ⇒ confirms COMBINE + normalize to the stock's own
  ATR/character ([[user_pivot_generalization]]). The ATR-normalized fresh_tightening primitive is the
  right shape.
- **Catalyst:** EP data covers the EP-subset only (APPS/NTAP/MNTS) — one input, not universal.
- **DIRECTION the data supports:** anticipation = the post-runup WATCH universe (flag radar; NOT 9M) →
  rank by OUR volatility-relative tightness (RMV + ATR-relative range; recalibrate the close-streak) +
  catalyst → top-N. Verify next; nothing gated yet.

### Design inputs to VERIFY — NOT facts (operator 2026-06-16)
The operator's framing: these connect anticipation to what we already have, but they are **ideas to
verify against data, not criteria to hardcode** (the whole phantom-criterion lesson). Reuse + measure:
- **Catalyst** can share from our **EP/MAGNA53 detector** as a possible input (reuse its catalyst data).
- **Tightness** can include **RMV** — and **compare or COMBINE** it with the tight-close series / range
  (don't pick one blindly; measure which separates the real picks).
- **Universe** can include **9M / multiple-9M cohort** (sugar-baby list) as the initial list to monitor,
  or to AUGMENT the +15%/≤10d leg universe.
VERIFY each against the known-good set (Pradeep 6/15: COO/HYLN/ALHC/APPS/NTAP + MNTS) before any gate:
does 9M/multi-9M capture them? does +15%/≤10d? do RMV/tight-close agree on which are "tight"? do they
have EP catalyst? Report what the data says; gate only on what holds. No invented thresholds.

### Build implications (FLAGGED — detection changes need sign-off + CHANGE_PROCESS, not auto-applied)
- **Thrust gate too narrow:** +40% one-day gap vs Pradeep's "first leg +15% in ≤10 days." Broadening
  the WATCHED universe to the 15%/10d leg is the biggest delta (and is essentially task #15's loose
  universe). Evidence + sign-off gated.
- **tight_close_streak** (shipped 6/16) = his "series of tight days." ✓ on the right track.
- **Catalyst-conditional exit leash** = CONFIRMED real; revisit the W3 exit work + reopen the leash
  test once #210/#211 source catalysts properly (the SSoT already filed this; now it has the source).
- **Catalyst-quality bar** (2× 39%+ sales growth + 39%+ projected) = a concrete materiality input for
  #189 / the rubric.
