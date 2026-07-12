# Block 3 T1(b) — mined judge-robustness corpus (Opus pre-build for the Fable session, 2026-07-11)

**What this is:** the **mined (historical) half** of the T1 judge-robustness corpus, pulled read-only
from `mi_audit_log` + `mi_daily_closes`. Data: `docs/analysis/block3_t1_mined_corpus_2026-07-11.json`
(84 cases). Script: `scripts/probes/_block3_t1_corpus_mine.py`. Hands the Fable session real graded
cases + a data-grounded taxonomy so Fable spends its time on **design** — T1(a) taxonomy, T1(b) the
*synthetic* adversarial half, T1(c) the live-path eval, T1(e) the regression gate — not on a data pull.

## The 84 cases (4 classes) + golden distribution

| class | n | source | golden verdict |
|---|---|---|---|
| **A** M&A / acquirer-pop / broad-rotation | 14 | `mna_filter_fired` | **REJECT_MNA** (self-labeled) |
| **B** unconfirmable / weak-revenue downgrade | 14 | `catalyst_earnings_revenue_weak_downgrade` | **DOWNGRADE** (self-labeled) |
| **C** earnings-boost, outcome-labeled | 14 | `catalyst_earnings_boost` × 5d-max | **9 FALSE_BOOST · 4 PASS_CONFIRMED · 1 unverified** |
| **D** live judge verdicts (the eval targets) | 42 | `ep_grade_decision` | outcome-unverified (see gap 1) — but full rationale + context |

39 of 84 carry a real forward outcome (5d-max-high % from the alert-day close, `mi_daily_closes`).

## The emergent misdirection taxonomy (data-grounded — the T1(a) starter)

1. **M&A-as-catalyst** (A): acquirer/target pop or a broad value-rotation dressed as a company
   catalyst. E.g. *CCC* — "moving on a broad value-rotation backdrop rather than a company-specific
   headline." The grader must NOT treat these as HIGH growth catalysts.
2. **Unconfirmable-underlying downgrade** (B): the revenue signal can't be confirmed (sparse corpus,
   no quarterly rev) → correctly downgraded. E.g. reason `news_corpus_sparse_no_q_rev` (EQPT, UCTT).
   The misdirection guarded against = rewarding a beat headline the underlying doesn't support.
3. **Strong-print-no-follow-through** (C, the HARD cases): a real earnings boost that the tape did
   NOT reward — 9 of 14 boosts returned < +10% 5d-max (UCTT +1.5%, SMPL −0.1%, CHTR −0.4%, WDC −1.7%,
   ALNY +3.1%, ENPH +2.6% …). "Excellent print" ≠ "will run." These are the calibration cases.
4. **Mature-brand-not-a-re-rater** (from D rationales): the judge *demotes* a strong print when the
   name is a mature large-cap with no thematic/narrative inflection — e.g. WDFC "mature $3.2B
   consumer/industrial brand, not a growth-stage re-rater … strong earnings surprise rather than a
   thematic game_changer." A named judge pattern worth pinning as golden behavior.
5. **Structural-charter/regulatory upgrade** (from D): the judge *promotes* on a structural catalyst
   (e.g. "OCC approval for a National Digital Currency Bank — a federal charter that structurally
   upgrades a $16.8B stablecoin company"). The positive exemplar — real inflection, correctly HIGH.

*(Fable extends: split A into acquirer-pop vs target-pop vs rotation; add the classes with NO
mined example yet — dilutive-offering-as-growth, stale-news-repackaged, promotional-microcap PR,
sympathy-move-no-own-catalyst, guidance-cut-inside-a-beat, thin "strategic reviews" — as the
SYNTHETIC half.)*

## Known gaps (honest — for Fable to close)

1. **Class D has no ticker in the payload** (`ep_grade_decision` stores grade/direction/rationale/
   context but not the symbol) → the 42 live judge verdicts are outcome-*unverified* here. They still
   carry full rationale + context (direction, grade, `in_active_theme`, market_cap, sector, gap,
   ep_score). T1(c)'s live-path eval re-runs these through grounding→rubric→judge anyway, so it
   recovers the outcome then; or recover the ticker via a fuzzy join on (alert_date, ep_score, gap_pct)
   to `mi_ep_alerts`.
2. **Outcome = 5d-max-high %** (a screening upper bound, no stop/settlement) — good enough to flag
   FALSE_BOOST (a name that never even *traded* +10% clearly didn't follow through), but it is NOT
   realized-R; don't over-read the magnitude.
3. **Mined half only** (~28 self-labeled goldens + the 9 hard FALSE_BOOSTs). The corpus reaches the
   ~50-100 target when Fable adds the crafted synthetic adversarial cases (the classes with no live
   example) — that's the deliberately-hard half a regression gate needs.

## How Fable uses this tomorrow

- **T1(a)** — lift the 5 classes above into the failure-mode taxonomy; add the synthetic-only classes.
- **T1(b)** — the synthetic adversarial half (crafted misdirections), appended to this JSON schema
  (`class, ticker, alert_date, payload, system_action, fwd_max5d_pct, golden, golden_rationale`).
- **T1(c)** — run the live grounding→rubric→judge path over the corpus read-only → failure rate per
  class (this also labels the Class-D outcomes).
- **T1(e)** — freeze the combined corpus as the standing grade-quality regression gate (any prompt
  change / model swap / silent update must pass it), + hand golden cases to #301.

*Read-only prep; no design decisions taken (that's the Fable session). Feeds #457 Block 3 T1 + the
7/18 M1 judge-authority flip.*
