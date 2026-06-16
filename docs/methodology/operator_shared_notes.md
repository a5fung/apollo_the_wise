# Operator-shared methodology notes (verbatim capture log)

**Why this file exists:** tweets / screenshots / notes the operator shares in chat live only in
conversation context, which gets compacted — and image content is LOST in summarization. They were
not being captured, so critical methodology shared "yesterday" became unrecoverable (operator
called this out 2026-06-16). **RULE (memory `feedback_capture_operator_shared_notes`): the moment
the operator shares a tweet / image / note with methodology, transcribe it VERBATIM here in the same
turn**, with date + source + how it maps to the build. Append-only; newest at top. This is the
durable home that survives context compaction — grep here before asking the operator to re-explain.

---

## 2026-06-16 — Pradeep Bonde (@PradeepBonde / stockbee), tweet 2026-06-15

**Verbatim (the qualifying criteria for a tight-consolidation continuation candidate):**

> "Price percent change today between -.4 and .4. That is the qualifying criteria. After that, I
> look for a series of tight days in the previous two bars. Plus some additional criteria like
> catalyst, and what is the buzz about the stock amongst the popular traders on Twitter."

Reply (Poor Pay Rich) — clarifying question: *"Are you looking for closing prices +/- .4% or actual
candle of day within .4% range?"* → Pradeep's phrasing is **"price percent change today"** = the
**close-to-close % change**, i.e. **|today close / prior close − 1| ≤ 0.4%**, NOT the intrabar
(high−low) range. (Distinction matters; the reply flags exactly this.)

**The criteria, decomposed:**
1. **Qualifying gate:** today's **close % change between −0.4% and +0.4%** (a doji-tight close).
2. **Then:** a **series of TIGHT DAYS in the previous two bars** (the prior 2 bars also tight) —
   tightness is a *run*, not a single day.
3. **Plus:** catalyst + "buzz among popular traders on Twitter" (the social/theme axis).

**How it maps to our build (#270 anticipation recorder):**
- (1) ⇒ our `tight_close_pct = |close/prev_close − 1|` — ALREADY recorded. Pradeep's threshold is
  **0.4%**; our SSoT calibrated ~1.4% for tiny-caps (#270 STEP 0) — record both; 0.4% is the
  Pradeep-canonical for normal names.
- (2) ⇒ the "series of tight days" = a **tight-close STREAK** + the 2-bar tightness
  `fresh_2bar_tr_pct` (from `_compute_fresh_tightening`). Added as a first-class recorder signal
  (`tight_close_streak`) so we capture the *run* of tight days, not just today's.
- (3) ⇒ catalyst axis (#189/#201 fire panel) + theme/buzz (theme engine) — separate axes, recorded
  for the candidate, not part of the tightness measure.

This is the "bar % range" the operator referred to: **Pradeep's tight-close (≤0.4% close % change)
+ a series of tight days** — the tightness measure that anchors the constructive-pullback signal
([[user_delayed_ep_reentry_template]]: undercut is one SHAPE; tightness is the core).
