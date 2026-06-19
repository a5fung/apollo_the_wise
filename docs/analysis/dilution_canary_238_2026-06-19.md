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
   dilution with the agreement/revenue enrichment). Replay corpus is SEC+Benzinga, no web.

> **Replay bug fixed first (advisor 6/19):** `get_sec_recent_filings` anchors its cutoff on
> `et_today()`, not `alert_date`. The replay's original tight 21-day dilution fetch therefore
> excluded **every** historical alert's offering (cutoff = today − 21d) → `dilution=none`
> cohort-wide → a silent false pass. Fixed to a separate 400-day fetch (kept separate from the
> `today_sec` fetch so a same-day 424B5 can't be mislabeled "today's news"); `recent_dilution_filing`'s
> own 21-day-of-alert window does the recency. The **live** path is correct as-is — there
> `et_today() == grade day`.

## Result — every dilution case: fix == baseline (the block changed zero grades)

| Ticker | Dilution filing | Today's real catalyst | live | base | **fix** | Read |
|---|---|---|---|---|---|---|
| **ELVN** | 424B5 same-day | Phase 1 ENABLE CML data (EHA 2026) + FDA Ph3 align | strong | strong | **strong** | inverse-BTQ **FIRES** ✓ |
| **SHAZ** | 8-K 3.02 same-day | 6-yr NVIDIA compute deal, $4.88B / 40k GB300 | game_changer | game_changer | **game_changer** | inverse-BTQ **FIRES** ✓ |
| **TNGX** | 424B5 same-day | Phase 1/2 vopimetostat + RAS(ON) data | routine¹ | strong | **strong** | real catalyst not suppressed ✓ |
| **WDC** 6/15 | 8-K/A 3.02 (7d) | Sandisk share-swap (housekeeping) | routine | routine | **routine** | correctly routine on merits ✓ |
| **WDC** 6/16 | 8-K/A 3.02 (8d) | Morgan Stanley PT→$650 upgrade | strong | strong | **strong** | stale large-cap 3.02 **not** suppressive ✓ |
| **WDC** 6/18 | 8-K/A 3.02 (10d) | MS PT→$650 + 30% storage demand | strong | strong | **strong** | stale large-cap 3.02 **not** suppressive ✓ |

¹ TNGX live=routine is the known **no-web confound** (replay grades on SEC+Benzinga only; live
had Perplexity). Not a #238 effect — and irrelevant to the canary, which reads dilution's
effect as fix-vs-base on the *same* corpus.

## Verdict

- **SAFETY canary PASSES decisively.** Across 4 names / 6 alerts — including the deliberately
  chosen false-positive risk (WDC, a large-cap whose 8-K/A item 3.02 is an immaterial stale
  housekeeping sale) and two same-day real-raise EPs (ELVN biotech, SHAZ $4.88B deal) — the
  dilution block suppressed **nothing**. The LLM-stays-judge design works: it reads the raise
  as background and keeps a genuine catalyst firing.
- **SUPPRESSION value is UNEXERCISED in this cohort** (honest gap). Every dilution hit here had
  a *real* catalyst, so the block was never the decisive factor. There is no catalyst-less
  pump-into-dilution case in the 30-day window (the original BTQ motivating case predates it).
  → The block's *value* (correctly holding such a case at routine) is carried by the **live
  shadow** (`has_dilution` on `ep_grade_enrich_shadow` rows, Monday+) and the **#347 flip**,
  not provable offline. **Say so + watch** — exactly the PLAN's stated fallback branch.

**Net:** #238 is **safe to carry as shadow** — proven non-harmful to real EPs. The live-grade
flip stays gated on the live shadow's net-correctness + CHANGE_PROCESS + operator sign-off
(folded into #347; no separate flip task).
