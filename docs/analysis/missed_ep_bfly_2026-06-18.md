# Missed EP — BFLY 2026-06-18 (catalyst-sourcing evidence case for #210)

**One-liner:** BFLY (Butterfly Network) ran +56% on a Midjourney-scanner
partnership PR and we fired **no real-time EP alert** on any track. Root cause is
**catalyst-CACHE STALENESS (timing), NOT missing sourcing.** The live scan already
fetches SEC 8-K/6-K + Benzinga press wires; BFLY graded `routine` at the **7:00 ET**
scan on **web-only** sourcing — *before* its own PR published (~8:05 ET) — and the
per-day catalyst cache pinned that pre-PR `routine` grade for the rest of the day,
so the direct-source PR was never re-fetched. Routine caps the MAGNA53 score below
the alert threshold regardless of the gap.

> **CORRECTION (2026-06-18, later same session):** an earlier draft of this doc
> blamed a "catalyst-sourcing gap (#210) — build the 8-K/PR-wire leg." That was
> **wrong**: `run_ep_scan` already fetches `get_sec_recent_filings(8-K,6-K)` +
> `get_alpaca_news` (Benzinga) and feeds `build_grounded_text`. Scoping the build
> against the code falsified the premise. The real defect is the **cache**, below.

## The move (textbook EP)

| | prev close 6/17 | open 6/18 | high | close | volume |
|---|---|---|---|---|---|
| BFLY | $5.71 | $7.21 (**+26.3% gap**) | $8.94 | **$8.90 (+56%)** | 59.5M (~10× ADV) |

Gapped, held, closed near highs on 10× volume. Exactly the EP shape we want to catch.

## What each track did

**1. MAGNA53 EP scan (the real "EP alert" track) — MISSED.**
Scanned at 7:00 ET (premarket gap then +13.5%, cleared the 12% routine-skip floor),
went through full scoring, but the catalyst graded **`routine`** → score capped < 50
→ no HIGH/MODERATE alert. Audit trail (`mi_audit_log`, 7:00–7:01 ET):
- `ep_catalyst_provenance` — `BFLY routine direct=False` (no direct primary source found)
- `catalyst_earnings_boost` — `routine → strong` (earnings_source=**no_match** — fired
  off the `_claude_text_signals_earnings` TEXT fallback, NOT a real earnings date)
- `catalyst_earnings_revenue_weak_downgrade` — `strong → routine`, reason
  `news_corpus_sparse_no_q_rev`. **Smoking-gun extraction_reasoning:**
  > "No earnings release or financial metrics for BFLY found in corpus; articles
  > discuss only premarket momentum, sector comparisons, valuation commentary, and
  > **unrelated AI imaging themes** without specific quarterly results."

The corpus had vague "AI imaging theme" chatter but **not the actual Butterfly ×
Midjourney deal**, so Claude correctly refused to grade theme-chatter as a catalyst
→ `routine`. (Per the rubric: "if none of the news items clearly explain WHY the
stock gapped, classify as routine" — the grader did the right thing on the wrong input.)

**2. 9M intraday per-tick digest — no real-time ping.**
9M detector flagged BFLY at 10:00 ET but as an **anticipation** (today_vol 6.6M,
projected 86.3M, gap 26.3%). Anticipations were moved off the per-tick Telegram
digest (#133, `ninem_detector.py:365` — only `is_9m_actual` crossings ping live).

**3. 9M EOD pace digest (16:20 ET) — surfaced, but only as a watchlist line.**
`_9m_pace_digest_job` ran (success) and ranked BFLY **#2** (behind EOSE 89.6M, ahead
of UUUU 75M): `• BFLY ~86.3M proj $7.61 +26.3%` under the header
"_Projection-based anticipations · watchlist, not entries._" — an EOD rollup, not a
real-time actionable EP alert.

**Net:** the only operator-facing mention of BFLY all day was a #2 line in an EOD
"watchlist, not entries" digest. The actionable EP track missed it entirely.

## Root cause = catalyst-CACHE staleness (timing), not missing sourcing

**The fetchers exist and ran.** `run_ep_scan` (ep_detector.py:1382) already fetches
`get_sec_recent_filings(ticker, forms=("8-K","6-K"))` + `get_alpaca_news` (Benzinga
press wires, #210 Wave A) and assembles them via `build_grounded_text` →
SEC → Benzinga PR → web. `corpus_provenance` records what the grade consumed.
**For BFLY that record was `{"web_perplexity": 1}, has_direct_source=false`** — i.e.
no SEC filing and no Benzinga PR were present at grade time; the grade ran on
Perplexity's web synthesis alone.

**Why no direct source — the timeline (all ET):**
- **7:00** — EP scan grades BFLY `routine` on web-only sourcing (gap then +13.5%).
- **~8:05** — BFLY issues its PR on BusinessWire ("Provides Commentary on
  Midjourney Medical's Full Body Ultrasound Scanner") — the primary source Benzinga
  carries. *This is after the 7:00 grade.*
- The underlying $74M agreement 8-K was filed **2025-11-17** — 7 months old, so
  `get_sec_recent_filings` correctly finds no *recent* 8-K. The 6/18 catalyst was
  the PR + a third party's (Midjourney) product unveiling, not a fresh filing.
- **rest of day** — every 5-min scan reuses the **cached** 7:00 `routine` grade and
  re-fetches nothing.

**The mechanism (ep_detector.py:1359–1379):** the per-day catalyst cache is "one
evaluation per ticker per day" — `if cached: <reuse grade, skip ALL fetches>`. So a
grade made on incomplete (web-only, `has_direct_source=false`) sourcing at 7:00 is
**pinned for the whole day**; the direct-source PR that lands at 8:05 is never seen.
This is a timing + cache-invalidation defect, not a sourcing-coverage gap and not a
grading bug (the grader graded thin pre-PR chatter correctly).

## The fix (surgical, cost-aware)

Don't cache a `has_direct_source=false` grade as terminal. On a cached tick where
the grade lacked a direct source, **cheaply re-poll the free/error-wrapped direct
sources** (SEC + Benzinga) — and only if a direct source *now* exists that didn't
before, **invalidate the cache and re-grade** (bounded: until a direct source
appears or the ORB window closes). This bounds the expensive LLM re-grade to "a new
primary source actually arrived," preserving the cache's cost purpose while closing
the premarket-PR-after-first-scan hole. Distinct from the #210 sourcing backbone
(which is about *adding* sources); this is about *re-reading the sources we already
fetch* when they update intraday.

## Secondary smell (not the cause; self-corrected here)

The `_claude_text_signals_earnings` text fallback fired a **false earnings signal**
on a non-earnings day (`earnings_source=no_match`), routing a partnership catalyst
through the earnings Q-rev rubric, which then downgraded it on missing quarterly
data. It self-corrected back to `routine` (same end state), so no net harm THIS time
— but it means a partnership catalyst gets forced through the wrong rubric. Worth a
glance when #210/#211 land a partnership path: the earnings text-fallback shouldn't
claim a non-earnings deal day.

## Implication

- The fix is a **surgical cache-invalidation** (PLAN **#344**), not a sourcing
  build — meaningfully smaller than the original framing implied.
- **Operator made it a HARD 6/22 GO/NO-GO gate** (2026-06-18). Because the fix is
  small and validates offline via replay, the gate is plausibly satisfiable without
  slipping 6/22 — but that's conditional on the replay showing the re-grade actually
  recovers catalysts at acceptable precision (re-grading too eagerly could over-fire).
- **Shadow-validation design (the gate evidence):** replay recent gappers where the
  first grade was `has_direct_source=false` but a direct source (Benzinga PR / 8-K)
  became available later the same day; measure how many would re-grade
  strong/game_changer and fire, and at what precision. **BFLY is case #1.** The
  load-bearing flip into the live grade stays CHANGE_PROCESS + sign-off.
- **Open localization owed before building:** confirm the 8:05 ET BFLY PR is in
  `get_alpaca_news` (Benzinga) — i.e. that a re-poll would actually have found it
  (timing) vs. a Benzinga coverage/`is_primary_subject_news` filter miss. If the PR
  is NOT in Benzinga even now, the cache fix alone won't catch BFLY and a coverage
  source is also needed (then #210 re-enters). Verify before committing the fix.
- No threshold/gap-override band-aid (would re-admit the routine-catalyst noise the
  50-floor is designed to filter).
