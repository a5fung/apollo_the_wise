# ADR 0021 — P2 Full Sight completion: intraday narrative radar + negative axis (D-5, #431)

**Status:** PROPOSED (2026-07-05, Fable design block D-5) — awaiting operator sign-off (§6).
Existing sight (stays): chart vision axis shadow (#343, gate 7/31) · theme/structure axes
(0015/0016, M1 checkpoint) · #238 dilution corpus feed (424B5/8-K equity-sale, point-in-time)
· Lane-2 narrative discovery (`discover_narrative_themes`) — **nightly**. The two deltas:

## 1. Intraday narrative radar (the RCAT-at-10:00 target)

Nightly Lane-2 catches same-day narrative cohorts at 18:05; the radar catches them while the
move is live. **Deterministic detection, LLM only for naming** (cost-bounded):

- **Job**: every 15 min, 9:45–15:45 ET (skip the open chaos window; INTELLIGENCE role).
- **Detection** (pure functions over data already flowing): candidates = names with intraday
  gain ≥3% AND rvol ≥2 (from the snapshot machinery the EP scan already uses). Cluster by
  (a) shared headline tokens over today's ingested news (Polygon/Benzinga raw JSON retained —
  token-overlap Jaccard on cleaned title keywords — **REVIEW 7/5: a NEW headline tokenizer;
  Lane-2 is 100% LLM (one Sonnet call over catalyst summaries), there is NO Lane-2 tokenizer
  to reuse — borrow the regex+Jaccard PATTERN from `_themes_are_related`/`_KEYWORD_RE`** **plus a
  finance-stopword list — Gemini am. 7/5: strip ubiquitous terms (revenue/quarter/guidance/
  announces/results/conference/Fed/shares/...) so clusters form only on SPECIFIC nouns
  (drones, H5N1, Blackwell, NAND); macro-news and ETF-rebalance blasts must not cluster**) and (b)
  pairwise co-movement of 5-min return paths (corr ≥0.6 over the session so far). Cohort =
  ≥3 names satisfying both.
- **Emission**: `mi_narrative_intraday` shadow rows `(cohort_key, detected_at, tickers[],
  shared_tokens[], avg_gain, avg_rvol, named_narrative NULL)`. First detection of a NEW
  cohort ≥5 names or avg gain ≥5%: ONE Haiku call names the narrative (cap 3 namings/day,
  dedup by cohort_key/day) + ONE Telegram line (`📡 Narrative cohort: drones — RCAT AVAV
  ONDS +6.2% avg, rvol 4x`). Smaller cohorts: rows only.
- **Consumers**: the judge's theme axis gets a same-day `intraday_cohort` payload field
  (advisory text, like every axis pre-flip) · Lane-2's nightly pass consumes the day's rows
  as candidate seeds (dedup via the existing pass1.5 absorption) · the #328 shadow gains an
  intraday corroboration column.
- **Explicit boundary**: minutes cadence, never tick-level (the seconds boundary holds);
  detection is deterministic — no LLM discovers cohorts, it only NAMES a detected one
  (judge-not-discoverer, applied to themes).

## 2. Negative-catalyst axis (dilution/overhang as a SCORED axis, ADR 0015/0016 pattern)

The corpus already carries dilution text; the judge reasons about it free-form. Promote to a
first-class axis with the same shadow→checkpoint discipline as theme/structure:

- **Deterministic flag extraction** (from data already fetched — submissions API form types +
  the #238 filing text): `neg_flags JSONB` per candidate:
  `s3_shelf_lt_30d (REVIEW 7/5: needs a NEW forms=('S-3',) fetch call — the parameter is
  generic but no call site passes S-3 today; trivial addition) · atm_agreement_seen_lt_90d
  (REVIEW 7/5: renamed from atm_program_active, which was an OVERPROMISE — true active-status
  needs 10-Q MD&A capacity/usage text we do NOT fetch; the presence-proxy from 8-K item-1.01
  agreements we already see is the honest v1; full ATM-status = a fork, K5) ·
  priced_takedown_lt_10d (424B5) · equity_sale_8k_lt_10d · going_concern_language
  (REVIEW 7/5: requires 10-K/Q fetch that does NOT exist today — rides fork K3 with that cost
  stated) · lockup_expiry_lt_15d (S-1 names, computable when IPO date known)`. Each flag:
  {present, filing ref (url), days_ago} — provenance via the 0019 manifest.
- **Axis score**: `negative_severity ∈ {none, overhang, active_dilution}` — mapped
  deterministically from flags (active = priced takedown/8-K sale <10d; overhang = shelf/ATM
  only). The JUDGE sees flags + severity and reasons (ADR 0011 clause 4).
  **Persistence (REVIEW 7/5 — the original claim was wrong):** the theme axis is NOT an
  mi_ep_alerts column (it lives in its own `mi_theme_axis_shadow` table) and the structure
  axis isn't built yet — so the neg axis follows the ACTUAL house pattern: its own
  **`mi_neg_axis_shadow`** table (#328's shape), never touching the live alert row pre-flip.
- **Shadow accrual** → joins the axis checkpoint cadence (M1-style batched eval): does
  active_dilution correlate with worse forward outcomes on HIGH grades? Boost-only-DOWN
  candidate (an axis that can only demote) — flip decision at a checkpoint with
  CHANGE_PROCESS + sign-off, same as 0015/0016.
- Reuses: `recent_dilution_filing` (exists), submissions form-type fetch (exists), the axis
  shadow-table pattern (#328's).

## 3. Build cards
| Card | Scope | Class |
|---|---|---|
| V1 | Radar job: candidate pull + token/corr clustering + shadow table + tests (golden: a synthetic 3-name cohort; a same-sector-no-news anti-case) | Sonnet card |
| V2 | Naming call (capped) + Telegram line + Lane-2 seed consumption | Sonnet card |
| V3 | neg_flags extractor + severity mapping + axis column + shadow accrual + tests (golden: a 424B5 fixture, a shelf-only fixture) | Sonnet card |
| V4 | Judge payload wiring for both (advisory text fields; grade prompt untouched until checkpoints) | Sonnet card, Fable review (grade-path adjacency) |

## 4. Cost & bounds
Radar: zero LLM in detection; ≤3 Haiku namings/day. V3: zero LLM (deterministic flags). The
15-min job issues its own `get_snapshot_all()` per tick (REVIEW 7/5: NO snapshot cache exists
anywhere — every caller fetches fresh; cheap because Polygon Starter is unlimited-call, not
because of caching) + already-ingested news — no new vendor calls.

## 5. Interactions
0019 §2.3 (theme-narrative corpus block) consumes radar cohorts if the #367 fork opens it ·
0015 theme axis gains intraday corroboration · #322 (untracked-theme gap) is partially
answered by radar cohorts becoming Lane-2 seeds · #309 (P2 umbrella) burns down by this ADR.

## 6. Operator sign-off forks (recs first)
- **K1** Radar Telegram threshold: **≥5 names or ≥5% avg** (rec) — quieter/louder.
- **K2** neg axis polarity: **demote-only** (rec — an axis that can only reduce conviction;
  never penalize the ABSENCE of negatives) vs bidirectional.
- **K3** going-concern grep in v1 (rec: yes, it's a string match on filings we already pull)
  vs defer.
- **K4** Radar cadence 15-min (rec) vs 5-min (3× the compute for marginal earliness).
- **K5** (added 7/5 eve) Full ATM-active status via new 10-Q/10-K fetching (real build) vs
  the presence-proxy only (rec: proxy v1; revisit with the axis checkpoint evidence).
