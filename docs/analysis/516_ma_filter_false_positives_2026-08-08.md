# #516 — M&A filter: which PATH is wrong, measured

**EVIDENCE ONLY. No criterion changed.** A detection-criterion change needs CHANGE_PROCESS +
operator sign-off; this is the measurement that makes the decision possible.

## Two corrections to the task's own premise — both good news

**1. The "70% of fires carry `match_path='unknown'`" line is wrong, and the diagnostic data was
there all along.** `detail.match_path` is set on only 2 of the ~6 paths, so reading that field
made 73% of fires look unattributable. **The path is in the `summary`** as `"TICKER via <source>
(detector)"`, and it is populated on **every single row**:

| source | fires (60d) |
|---|---|
| claude_classifier | 27 |
| polygon_news | 21 |
| keyword_in_text_1 | 11 |
| keyword_in_text_0 | 8 |
| deal_pin_fresh | 4 |
| deal_pin_signature | 2 |

Nothing needs instrumenting first. That was assumed to be a blocker and is not.

**2. The paths are NOT equally wrong — one is clean.**

## The measurement

A genuine M&A target **pins near the deal price**; a false positive **keeps moving**. So: for
every suppression in the last 60 days, what did the name do over the following 10 sessions?

| path | suppressed | measurable | ran ≥10% after | worst case |
|---|---|---|---|---|
| **claude_classifier** | 27 | 26 | **0** | best was +9.8% |
| **polygon_news** | 21 | 18 | **5** | **+154.6%** |
| keyword_in_text_1 | 11 | 11 | 2 | +10.7% |
| keyword_in_text_0 | 8 | 8 | 2 | +16.3% |

**The LLM classifier is 0-for-26. The keyword and news paths account for every single one.**

⚠ **The proxy has a known false signal, and it is in this data.** CLRO (+154.6%) is on the list,
and the operator ruled CLRO a **CORRECT** suppression — a real deal that ran on a bidding
situation. So "ran ≥10%" cannot be used as proof on its own; it is a screen that produces
candidates for his judgment, which is exactly how #514 was run.

## The 9 candidates, named

| ticker | path | date | keyword | ran |
|---|---|---|---|---|
| CLRO | polygon_news | 07-02 | merger | +154.6% | ← **ruled CORRECT** (real deal) |
| WEN | polygon_news | 06-26 | takeover | +21.2% | ← ruled NO M&A |
| FRMI | polygon_news | 06-17 | merger | +17.0% | **unruled** |
| UMAC | keyword_in_text_0 | 06-30 | definitive agreement | +16.3% | ← ruled NO M&A |
| SOUN | keyword_in_text_0 | 08-06 | merger | +14.8% | **unruled** |
| WEN | polygon_news | 06-29 | takeover | +14.5% | ← ruled NO M&A |
| WEN | polygon_news | 06-29 | takeover | +14.5% | ← **the same day, twice** |
| LII | keyword_in_text_1 | 06-15 | takeover | +10.7% | **unruled** |
| SCZM | keyword_in_text_1 | 06-15 | merger | +10.0% | **unruled** |

**WEN appears three more times here**, on two dates, all via `polygon_news`/"takeover" — the
recurring misfire the task flagged, still recurring, and the #89 dedup did not stop it.

## The clearest single case: SOUN, 2026-08-06

Suppressed via `keyword_in_text_0`, `matched_keyword: "merger"`. Its own stored news summary
says the move was:

> *"driven primarily by a blowout Q2 earnings print and upgraded forward guidance that
> materially beat Street expectations"*

The filter's own record classified the catalyst as `"routine"` (not `"mna"`) — and suppressed it
anyway, because the word "merger" appeared somewhere in the text. **This is not a judgment call
that went the wrong way; it is a keyword match on text that explicitly attributes the move to
something else.**

## What the evidence supports — for the operator, not for me to ship

The keyword paths match a word **anywhere in the text**, without asking whether that word is what
is **driving the move**. The classifier path reasons about the driver, and is 0-for-26.

Candidate directions, in order of how much evidence backs them:

1. **Require the classifier to concur before a keyword/news match can suppress.** Directly
   targets the measured split; costs nothing on the 27 fires the classifier already catches.
2. **Reject a keyword match when the catalyst is classified as something else** (SOUN was
   `routine`). Narrower, and it would have caught SOUN and probably UMAC.
3. Nothing for `deal_pin_*` (6 fires, 0 runners) — leave it alone.

⚖ **A detection-criterion change requires CHANGE_PROCESS: N≥10 backtest, SSoT in the same
commit, and his sign-off.** The N≥10 bar is met by this 63-name measurable cohort.

## Still owed by this task

- Operator ruling on the four unruled names: **FRMI, SOUN, LII, SCZM**.
- WEN's repeat: the dedup key is per (ticker, detector) with a time window; two fires on 06-29
  suggests the window does not cover same-day repeats from the same path. Worth a look
  independent of the criterion change.
