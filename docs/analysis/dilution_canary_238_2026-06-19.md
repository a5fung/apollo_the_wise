# #238 dilution corpus-feed — canary validation (2026-06-19)

**What shipped:** `recent_dilution_filing()` + an `assemble_grade_corpus(dilution_filing=)`
dated NEGATIVE-context block, wired into both #344 shadow paths. A recent 424B5 (priced
takedown) or 8-K item 3.02 (actual equity sale) — point-in-time (filed ≤ grade), within a
21-day recency window — is fed to the grader as: *"weigh AGAINST today's move … but do NOT
auto-reject — a genuine EP catalyst can coincide with an opportunistic raise."* The LLM
stays judge (a deterministic skip would violate `feedback-catalyst-sourcing-direct-over-llm`;
BTQ proved the LLM rejects dilution **when it's in the corpus**).

Ships as **shadow** (rides the `ep_grade_enrich_shadow` + `ep_repoll_shadow` events; never
touches the live grade). Premarket-guarded, error-wrapped, `ENRICH_SHADOW_ENABLED`-killable.

## Method

1. **Cheap SEC-only scan** (no Claude $) of the 30-day `ep_catalyst_provenance` cohort
   (57 unique tickers / 60 graded gappers since 2026-05-20): which alerts actually had a
   recent 424B5 / 8-K item 3.02 near the alert? Only those exercise #238. → **6 hits / 4 names.**
2. **Grade replay** (`_344_late_source_replay.py --enrich --ticker X`) on the 4 names, reading
   the **fix-arm ABSOLUTE grade** (advisor 6/19: not the baseline delta — the delta conflates
   dilution with the agreement/revenue enrichment, and there is no isolation arm). Replay
   corpus is SEC+Benzinga, no web.

### Two bugs the advisor caught and fixed *before* the result was trustworthy

- **Replay lookback no-op.** `get_sec_recent_filings` anchors its cutoff on `et_today()`, not
  `alert_date`. The original tight 21-day dilution fetch therefore excluded **every** historical
  alert's offering → `dilution=none` cohort-wide → a silent false pass. Fixed to a separate
  400-day fetch (kept separate from the `today_sec` fetch so a same-day 424B5 can't be
  mislabeled "today's news"); `recent_dilution_filing`'s own 21-day-of-alert window does the
  recency. The **live** path is correct as-is (there `et_today() == grade day`).
- **Corpus truncation.** `assemble_grade_corpus` appends the prior/dilution context AFTER
  today's news, but `_classify_catalyst_claude` sliced `grounded_text[:6000]`. The first canary
  run's corpora were 6270–10860c → the dilution block sat **past** the window → never reached
  the grader. "fix == baseline" was a truncation artifact, and the live #344 shadow was
  silently truncating prior-agreement context for long-today names too. Fixed: today's-news
  capped to `_GRADE_TODAY_MAX_CHARS=6000` (the lean live grader's effective today-window); the
  enriched corpus graded with `_GRADE_ENRICH_MAX_CHARS=12000`; the short high-signal dilution
  block emitted before the lowest-value earnings block. The live non-enriched path is unchanged
  (`max_chars` defaults to 6000). The replay now asserts `"RECENT DILUTIVE FILING" in corpus[:12000]`.

## Result — block confirmed IN the grade window for all 6 alerts

| Ticker | Dilution filing | in window | Today's real catalyst | live | base¹ | **fix** | Read |
|---|---|---|---|---|---|---|---|
| **ELVN** | 424B5 same-day | YES (10379c) | Phase 1 ENABLE CML data + FDA Ph3 align | strong | game_changer | **strong** | fires; concurrent raise tempered gc→strong = **the live grade** ✓ |
| **SHAZ** | 8-K 3.02 same-day | YES (9226c) | 6-yr NVIDIA deal, $4.88B / 40k GB300 @ $1.6B mcap | game_changer | game_changer | **game_changer** | deal magnitude dominates; fires ✓ |
| **TNGX** | 424B5 same-day | YES (10378c) | Phase 1/2 vopimetostat + RAS(ON) data | routine² | strong | **strong** | not suppressed ✓ |
| **WDC** 6/15 | 8-K/A 3.02 (7d) | YES (6270c) | Sandisk share-swap (housekeeping) | routine | routine | **routine** | correctly routine on merits ✓ |
| **WDC** 6/16 | 8-K/A 3.02 (8d) | YES (6978c) | Morgan Stanley PT→$650 upgrade | strong | strong | **strong** | stale large-cap 3.02 **not** suppressive ✓ |
| **WDC** 6/18 | 8-K/A 3.02 (10d) | YES (7022c) | MS PT→$650 + 30% storage demand | strong | strong | **strong** | stale large-cap 3.02 **not** suppressive ✓ |

¹ baseline = no-web **and** no enrichment context. ² TNGX live=routine is the known **no-web
confound** (replay grades on SEC+Benzinga only; live had Perplexity). Not a #238 effect.

## Verdict

- **SAFETY canary PASSES — for real this time** (block confirmed in-window). Across 4 names / 6
  alerts — including the deliberately chosen false-positive risk (WDC, a large-cap whose 8-K/A
  item 3.02 is an immaterial stale housekeeping sale) and two same-day real-raise EPs (ELVN
  biotech, SHAZ $4.88B deal) — **zero real-EP alerts were wrongly suppressed to routine.** Every
  genuine catalyst still fires.
- **The block is read, not a no-op.** The one grade change (ELVN game_changer→strong) is a
  *conservative temper that still fires* — and it moved the no-web baseline **toward** the live
  grade (strong). That is the design working: a real EP that also raises capital fires, but the
  concurrent raise pulls an over-eager grade down a notch, not to routine.
- **Attribution caveat (advisor):** the fix arm bundles prior-context + dilution with no
  isolation arm, so a change isn't attributable to the dilution block *alone*. The absolute
  fix grade is the canary read; the marginal dilution effect is left to the live shadow.
- **SUPPRESSION value is still UNEXERCISED offline** (honest gap). Every dilution hit here had a
  *real* catalyst, so the block was never the decisive factor holding a grade down. There is no
  catalyst-less pump-into-dilution case in the 30-day window (the original BTQ motivating case
  predates it). → carried by the **live shadow** (`has_dilution` on `ep_grade_enrich_shadow`
  rows, Monday+; the verifier now has a #238 suppression-value section) and the **#347 flip**.

**Net:** #238 is **safe to carry as shadow** — proven non-harmful to real EPs with the block
genuinely in the grade window. The live-grade flip stays gated on the live shadow's
net-correctness + CHANGE_PROCESS + operator sign-off (folded into #347).
