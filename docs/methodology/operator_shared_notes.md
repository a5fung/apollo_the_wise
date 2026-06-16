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

### Build implications (FLAGGED — detection changes need sign-off + CHANGE_PROCESS, not auto-applied)
- **Thrust gate too narrow:** +40% one-day gap vs Pradeep's "first leg +15% in ≤10 days." Broadening
  the WATCHED universe to the 15%/10d leg is the biggest delta (and is essentially task #15's loose
  universe). Evidence + sign-off gated.
- **tight_close_streak** (shipped 6/16) = his "series of tight days." ✓ on the right track.
- **Catalyst-conditional exit leash** = CONFIRMED real; revisit the W3 exit work + reopen the leash
  test once #210/#211 source catalysts properly (the SSoT already filed this; now it has the source).
- **Catalyst-quality bar** (2× 39%+ sales growth + 39%+ projected) = a concrete materiality input for
  #189 / the rubric.
