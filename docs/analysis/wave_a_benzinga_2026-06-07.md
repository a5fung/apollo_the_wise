# #210 Wave A — Benzinga wire into the EP catalyst corpus: validation (2026-06-07)

**Status: engineering validated + deployed (additive, error-wrapped, activates Mon 6/8
scan). "Net-positive / graduate Wave A" is an operator judgment (hard-gate rule) —
this doc reports evidence, not a verdict.**

## What shipped (commit `cbb7619`, deployed both 6/7)
- `collector.get_alpaca_news` now returns `symbols`; new `is_primary_subject_news()`
  rejects the #88/#90 multi-tag bleed + basket roundups before any item enters the
  grounded corpus. 9/9 unit tests (incl. the GRRR probe trio).
- `ep_detector`: `get_alpaca_news` added to the catalyst gather; primary-subject-
  filtered items → `grounded_parts` via new shared `build_grounded_text()`. Capped
  top-3. **Grounded-corpus only** — NOT fed to the M&A keyword scan (no `is_likely_ma`
  regression). 40/40 catalyst tests green; datetime-hygiene gate OK.

## GRRR 2026-06-02 — what it does and does NOT show

**Re-anchor:** GRRR is **not** a winner-rescue exemplar. The headline #210 thesis
("a real EP winner suppressed by a missed source") is **falsified** for GRRR on two
counts:
1. **Not suppressed** — the production EP grade stored `score=100.8, HIGH, strong`.
   It alerted. (The `no_real_catalyst` came from the separate #212 dialogic prototype,
   not the production grade.)
2. **Not a winner** — GRRR did not fill on the EP day and dropped the next day on a
   debt-issuance announcement (operator, 6/7). A real, large, correctly-attributed
   catalyst still produced a bad trade.

So GRRR validates the **narrower, real** claim: **attribution correctness**.

### The isolated A/B (the rigorous comparison)
Same Perplexity-now, same (absent) SEC — **only the Benzinga block differs**:

| arm | grade | attribution |
|---|---|---|
| as-of WITHOUT bz | `strong` | generic "AI infrastructure contract wins" |
| as-of WITH bz | **`game_changer`** | **"$2B deal … >4× GRRR's $474M market cap"** |

→ Benzinga = **+1 tier + correctly-sized attribution**. The WITHOUT-bz control is
**hindsight-contaminated** (Perplexity-now has since indexed the deal), so **+1 tier
is a LOWER BOUND** on Benzinga's same-day live value.

### Two supporting facts
- **Stored 6/2 production grade confabulated:** its catalyst text reads *"…rather than
  on a single major fundamental surprise like an acquisition or large contract"* — it
  reached `strong` while **explicitly denying** the $2B contract that was that day's
  actual catalyst. (Right score, wrong reason.)
- **6-K lagged the PR by 3 days:** SEC 6-K filed **2026-06-05** vs the Benzinga wire
  **2026-06-02 13:08 UTC**. On the gap day the 6-K **did not exist** — the press wire
  was the *only* same-day primary source. This is the structural argument for the wire
  on foreign issuers, proven.

## What is still UNPROVEN
- **The winner-rescue thesis** (Benzinga rescues *suppressed* catalysts the grade
  misses). GRRR can't prove it (not suppressed). Needs a **known-suppressed name or a
  small cohort** — the right vehicle is the #211 unknown-rate-by-source-class KPI +
  #202 attribution on the live forward cohort, not another GRRR run.
- Caveat noted, not claimed: the WITHOUT-bz-now arm cited a "Yotta Data Services
  contract" — possibly GRRR's *earlier* Yotta deal, not the 6/2 SMCI one. So we do NOT
  claim the *now* arm confabulated; only the *stored 6/2* grade demonstrably did. The
  tier-upgrade isolation holds regardless.

## Honest close for #231
Engineering validated · attribution-correctness demonstrated (isolated, lower-bound
+1 tier) · press-wire-timeliness proven (6-K lags 3d) · **winner-rescue thesis pending
a suppressed-case / cohort run**. Code stays deployed (additive, safe; Monday
activation). Operator judges whether this clears Wave A. Backbone (#210) thesis should
re-anchor its headline exemplar on **RUM (#187, $270M deal both LLMs actually missed)**;
GRRR is the attribution-correctness + 6-K-timing exemplar.
