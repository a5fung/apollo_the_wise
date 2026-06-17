# Deferred grade-quality fixes (#320, #321) — validation plan, ETA, cost-of-delay

**Decision (operator, 2026-06-17):** WAIT — ship after the June 22 go/no-go, not before.
**This doc exists so the deferral does not linger:** it states exactly why we're waiting, what we're
waiting for, what must be answered first, a firm ETA, and the cost of waiting too long.

## Why we're waiting (crystal clear)
**Not because we lack data — we have it.** Both fixes are *grade-affecting*: they change which trades
qualify. In the final days before a real-money go/no-go we don't shift the trade population without a
measured backtest. The gate is the **launch date**, not data accumulation. The moment the 6/22
decision passes, the validation below can run immediately.

## Do we need new data sources?
**No.** Both validations run on data we already collect:
- #321 — the `#149` shadow has been logging, on every missing-YoY downgrade, the deterministic
  yfinance year-over-year we *didn't* act on (`catalyst_q_rev_yoy_shadow_recovered`). The backlog of
  cases is already on disk.
- #320 — the per-decision grade audit already records floor tier, final (judge) tier, score, and the
  confidence boost, so the effect of removing the boost is fully replayable.

---

## Fix #321 — stop penalizing strong earnings for a missing prior-year number (the bigger one)
**What it fixes:** when one data feed omits last year's revenue, the engine (a) can't run its quality
scorecard and (b) downgrades the stock for the *missing data* as if growth were weak (e.g. LZB
6/17 — a genuinely strong quarter, wrongly downgraded; the second source had +3.8%).

**What we validate (already-possible backtest):**
1. **Coverage** — of all missing-YoY downgrades, what % does yfinance actually recover?
2. **Flip rate** — when recovered, how often does it change the decision (downgrade → keep)?
3. **Correctness** — of the flips, are they *right*? (Judged on catalyst-attribution correctness, not
   P&L — per `feedback_catalyst_correctness_is_the_goal`.)

**Gap / unknown we MUST answer first:** **is yfinance reliable enough to be load-bearing?** It can be
stale or rate-limited. Before it can *drive* a grade, spot-check its YoY against the primary source on
a sample to bound its error rate. This is the one genuine unknown — not just "run the backtest."

**ETA:** backtest + reliability spot-check the week of **2026-06-23**; ship-or-hold decision by
**2026-06-25**. (If the recovered-case sample is too small for confidence, accumulate through the next
earnings cycle and re-decide — state the N at that point.)

**Cost of waiting too long:** *every earnings day* we keep wrongly downgrading some genuinely-strong
earnings gappers = **missed good trades (false negatives)** + blank scorecards on those names. The
cost scales with earnings-season density — it is the larger of the two and recurs continuously.

---

## Fix #320 — drop the stale confidence boost
**What it fixes:** when two graders agree we nudge the score up; if the name is later downgraded for a
data issue, the boost isn't removed, leaving the score inflated.

**What we validate (already-possible backtest):**
1. How many names historically carried the stale boost (agree → later downgraded)? (Likely a small
   set.)
2. Of those, how many would the reset drop below the alert threshold?
3. Of *those*, did the final judge promote them — i.e., would removing the boost cost us trades the
   judge wanted? (The subtle **pre-judge gating** risk: the boost can be the only reason a name
   reaches the judge at all.)

**Gap / unknown — and a dependency:** #320 is **coupled to the Perplexity-repositioning decision
(#233)**. If we move Perplexity to display-only and retire the mechanical boost entirely, that
*supersedes* #320. So decide #320 *with* #233, not separately.

**ETA:** same window — backtest week of **2026-06-23**, decision by **2026-06-25**, jointly with #233.

**Cost of waiting too long:** a few downgraded names keep inflated scores and can trip the alert bar
they shouldn't = **occasional false-positive alerts**. Smaller and rarer than #321 (only the
agree-then-downgrade subset is affected).

---

## Anti-linger mechanism
- Both tasks carry a firm ETA of **2026-06-25** in PLAN.md; the plan gate fails if either slips past
  it un-rebumped, so they cannot silently rot.
- They are sequenced as the **first post-launch grade-quality work** (right after the 6/22 close).
- Re-run the relevant probe after shipping to confirm the effect, and add it to the monthly
  backward-check sweep (`feedback_methodology_insights_need_periodic_revalidation`).
