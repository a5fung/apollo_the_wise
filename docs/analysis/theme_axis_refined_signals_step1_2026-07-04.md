# #367 STEP-1 — refined theme-relevance signals (inherits the #369 finding)

## Background

STEP-0 (#329, `agents/market_intelligence/theme_axis_shadow.py`) logged a **structural
attribution** score for every scored EP HIGH: does the catalyst `grounded_text` mention another
theme-cohort **ticker**, or a theme keyword? The #369 STEP-0.5 backfill (452 historical rows)
surfaced a correction (commit `2838d90`, 6/24): `grounded_text` is the **raw SEC 8-K**, not
analysis prose — filings name other companies by **company name**, not ticker symbol. So
ticker-intersection structurally can almost never match a real peer reference, regardless of
whether the theme is actually the driver of the move. That STEP-0 signal is kept (for
continuity/comparison — see the health-read script below), but it is not the instrument to
size the theme-axis weighting decision (#368) on its own.

STEP-1 builds the two signals the #369 correction and the 6/24 direction decided on, **as
CO-EQUAL candidates** (neither assumed to dominate a priori):

- **(a) company-NAME matching** — the direct fix: match cohort companies' NAMES against the
  catalyst text.
- **(b) co-movement** — is the ticker moving WITH its theme cohort that day? An independent,
  price-based signal that doesn't depend on catalyst-text quality at all.

Both are shadow/telemetry only (THE LINE untouched) and log side by side onto
`mi_theme_axis_shadow` (6 new nullable columns, same schema-evolution pattern as the STEP-0
columns). Neither is a flip-gate — the #368 STEP-2 weighting decision is the operator's call
over a labeled cohort; the disagreement rate here is a **health gauge only** (#329, 6/24).

## (a) Company-name matching — the normalization rule

Implemented in `theme_axis_shadow.py`: `_normalize_company_name()` + `compute_name_attribution()`.
Name source: `collector.get_fmp_profile()` (yfinance `longName` — the same call
`theme_engine._ensure_descriptions()` already makes to build its Haiku description prompt),
cached persistently in a new `mi_ticker_overrides.company_name` column via
`db.get_company_names_batch()` / `db.upsert_company_names_batch()` (mirrors the existing
sector/description cache columns exactly) so repeat lookups for the same ticker are a DB read,
not a re-fetch.

**Normalization rule** (documented as a starting rule for a health gauge — not tuned, not a
flip-gate):

1. Lowercase; strip punctuation (periods, commas, apostrophes).
2. Drop a leading "the" (`"The Boeing Company"` → `"boeing company"`).
3. Strip TRAILING corporate-suffix tokens, repeatedly (handles multi-suffix names like
   `"Foo Holdings Inc"`): `inc, incorporated, corp, corporation, co, company, ltd, limited,
   llc, plc, holdings, holding, group, sa, nv, ag, se, pte, gmbh, spa, srl, kk`.
4. The remainder is **usable** for matching iff it has **≥2 tokens**, OR **exactly 1 token**
   that is **≥6 characters** AND not in a small generic-word denylist (`group, holdings,
   systems, solutions, technologies, industries, international, global, capital, partners,
   resources, enterprises, ventures, brands, energy, financial, health, media, labs, networks,
   digital, national, united, american, world, star, sun`, …). Unusable remainders (too short,
   too generic, or empty after suffix-stripping) are **excluded from matching entirely** —
   deliberately conservative (under-count rather than false-match), mirroring the STEP-0
   ticker signal's own subject-exclusion asymmetry.
5. The match test is a **word-bounded, case-insensitive, contiguous-phrase** search of the
   normalized name against the (identically normalized) `grounded_text` — not bag-of-words.

Examples: `"Acme Robotics Inc."` → `"acme robotics"`; `"Friendco Holdings Inc"` → `"friendco"`
(8 chars, passes the single-token floor); `"Solutions Inc"` → `None` (generic single word,
excluded); `"AMD"` (as a raw name, not a ticker) → `None` (3 chars, below the floor).

The subject ticker's own name is excluded from the cohort before matching (same rationale as
STEP-0: the corpus is *about* the subject, so it would trivially "self-match").

## (b) Co-movement

Implemented as `compute_co_movement()` + `db.get_daily_moves()`. Uses `mi_daily_closes`
**open→close** same-day pct move (not prev_close→close) for both the subject ticker and the
cohort — a deliberate simplification: it needs only a single day's row (no weekend/holiday-
aware prior-trading-day lookup) and puts the subject and cohort on an identical basis, which is
all a same-day co-movement compare needs.

`cohort_move` = median of the OTHER cohort members' move (subject excluded). `co_moving` = the
subject's move and `cohort_move` share a sign, AND `|cohort_move|` clears
`CO_MOVEMENT_FLOOR_PCT = 1.0` (a named, documented **starting value — not tuned**; a cohort
that barely moved makes same-sign agreement uninformative either way). `co_moving` is a
tri-state (`True` / `False` / `NULL`) — `NULL` means "not computable" (no cohort price data, or
no subject price data), kept distinct from a computed `False` so the health read never conflates
"unknown" with "measured, not co-moving."

## The health read

`scripts/probes/_367_theme_axis_health_read.py` — read-only (`SELECT` from
`mi_theme_axis_shadow` only). Reports, over the configurable window (`--since-days`, default
120d):

- N themed vs themeless.
- Attribution distribution: STEP-0 (ticker) vs STEP-1(a) (name) attributable rates.
- STEP-1(b) co-movement distribution (co-moving / not co-moving / not computable).
- **Disagreement rate** between signal (a) `name_attributable` and signal (b) `co_moving`,
  over rows where both are computable — the STEP-1 DoD read.
- Secondary: STEP-0 vs STEP-1(a) disagreement — the #369 finding made quantitative (expected to
  be large, since ticker-intersection under-detects vs name-matching on 8-K-sourced text).
- A small-N caveat banner when the both-computable count is under 25 (#329 6/24: "don't read
  low early counts as green").

**This script was NOT run against prod by the agent that built it.** It requires a live DB pool
(and, for any newly-encountered cohort tickers, network access to yfinance for the company-name
cache) that this offline build environment does not have — verified: running it here fails
closed with the intended message (`Could not reach the live DB pool from this environment ...
This script is ready to run as-is inside apollo-market ...`) rather than a stack trace or
fabricated numbers. **The parent session runs it** (after deploying the schema changes and
running `scripts/backfill_theme_axis_refined_signals.py --commit` to populate the two new
signals onto the existing 452+ historical rows) to produce the actual STEP-1 DoD numbers.

## Reminder — health gauge, never a flip-gate

Per the #329 6/24 operator decision (reaffirmed here for STEP-1): the disagreement rate this
read produces is a **review-load regulator + health gauge only**. It measures which signal
separates "theme is the driver" from "uses theme vocabulary" — it does **not** decide the
#368 STEP-2 weighting. That decision is the operator's, gated on a themeless-winner-inclusive
LABELED cohort (STEP-2, #368), not on this script's output.
