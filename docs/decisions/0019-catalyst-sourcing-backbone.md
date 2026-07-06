# ADR 0019 — Catalyst Direct-Sourcing Backbone: completion spec (D-3, #429 · closes #210's design)

**Status:** PROPOSED (2026-07-05, Fable design block D-3) — awaiting operator sign-off (§7).
**Honest framing: this backbone is ~70% BUILT.** D-3's job is the completion delta, not a
greenfield design. Doctrine (operator 6/05, unchanged): catalyst sourcing is a DATA problem —
direct primary sources over LLM discovery; **LLM = judge of grounded text, never discoverer.**

## 1. Inventory — what EXISTS and stays (verified in code 7/5)

| Piece | Where | State |
|---|---|---|
| SEC EDGAR: CIK map, submissions API, filing-doc URL resolution, recent-filings fetch | `collector.py` (`get_sec_recent_filings` + helpers) | LIVE |
| News feeds ingested: Polygon · Alpaca/Benzinga (+ raw JSON retained) | collector + `news_source_quality.py` | LIVE |
| Enriched-corpus assembler (SEC 400d filings + benzinga + dilution + news) feeding LIVE grades | `ep_detector._build_enriched_corpus` (#344/#347, flipped 7/4) | LIVE |
| Source-quality drift telemetry (coverage/density/attribution + weekly drift) | `news_source_quality.py` (#71/#72) | LIVE |
| Unknown-catalyst KPI (`/unknownrate`) + the gap-discovery loop (weekly, Perplexity asks only "WHERE was it published" → source-onboarding queue — never a grade input) | `source_gap_finder.py` (#235 Wave E) | LIVE |

## 2. The completion delta (what D-3 actually adds)

### 2.1 FMP press-release onboarding (T1-adjacent; the key already exists)
FMP's press-release endpoints (`/press-releases/{ticker}`, stable IR-wire text) are unused
despite a paid key in prod. Wire them as a corpus source: fetch at enrichment time alongside
SEC/benzinga (same async gather, same timeout discipline), normalize to the corpus block
format, register the feed alias in `news_source_quality.INGESTED_FEED_ALIASES` (that module
OWNS "what do we ingest" — the gap-finder then stops flagging PR-wire misses as gaps).
Acceptance: a name whose catalyst exists only as an IR press release (the gap-finder's most
common finding class) grades with a grounded corpus instead of `unknown_catalyst`.

### 2.2 Perplexity demotion — the end-state, stated once
Target: Perplexity appears in exactly TWO places — (a) the gap-finder's bounded
"where was it published" question (exists), (b) OPTIONAL verification against an
already-grounded corpus. **Zero discovery in the grade path.** The remaining executors are
already-filed tasks — #233 (its grade becomes a labeled disagreement signal; floor-boost
retired) and #317 (contradictory alert line suppressed, deployed 7/5 pending verify) — this
ADR just pins the end-state so no future change re-introduces discovery. Grade-path changes
ride CHANGE_PROCESS as usual.

### 2.3 Cross-ticker/theme corpus extension — CONDITIONAL on Monday's #367 read
The live fork: #367's 0/50 name-attribution with data present means either matcher-bug or
**corpora are genuinely self-referential** (a company's filings don't name its peers; peers
live in theme narratives). IF Monday's read lands on self-referential: the corpus assembler
gains a THEME-NARRATIVE block — Lane-2 narrative text + the theme's top-3 co-movers' latest
headline lines (sources already ingested; this is assembly, not new fetching). Bounded:
≤500 tokens, clearly labeled `THEME CONTEXT (not subject-specific)` so the judge can't
mistake peer news for subject news (the is_primary_subject_news filter stays upstream).
IF matcher-bug: fix the matcher (#367's own lane); this section stays dormant.

### 2.4 Provenance-lite (audit, not architecture)
No new normalized source store (rejected: a `mi_catalyst_sources` table would duplicate
retained raw JSON + corpus logs for modest gain). Instead: the corpus assembler writes a
**source manifest** — `mi_ep_alerts.corpus_manifest JSONB`:
`[{"src":"sec_8k","ref":"<acc_no>","chars":1840},{"src":"fmp_pr","ref":"<url>","chars":2210},...]`
— one additive column; the judge rationale's citations become checkable ("grade cited an
8-K we can open"), and #367-class diagnostics stop needing corpus re-fetches.

## 3. KPI + done-ness
The backbone is DONE when: `/unknownrate` (HIGH/MODERATE alerts with zero T1/T2-grounded
corpus) holds **< 10% over a 4-week window** AND the gap-finder's weekly actionable queue
is empty for 2 consecutive weeks (every recommended source either onboarded or
operator-rejected with a reason). Weekly-review line already exists via the quality section;
add the unknownrate trend beside it (one line, same section — consolidate).

## 4. Interactions
#416 M&A FP amendment: 8-K/PR primary text enables acquirer-vs-target direction detection —
that amendment should prefer manifest-cited primary text over keyword matching (noted for its
own CHANGE_PROCESS pass). #333 (durability's forward leg) consumes the same structured PR/8-K
text. D-2's precedent store joins on alerts — manifests make precedent corpora reconstructable.

## 5. Build cards
| Card | Scope | Class |
|---|---|---|
| S1 | FMP PR fetch + corpus block + feed-alias registration + **deterministic safe-harbor/boilerplate strip BEFORE corpus append** (Gemini am. 7/5: PR wires carry ~2k-word forward-looking-statements legalese that would dilute the catalyst signal; regex on the standard section headers + a length-capped tail) + tests (mock FMP incl. a boilerplate fixture) | Sonnet card |
| S2 | `corpus_manifest` column + assembler writes it + `/why` renders it | Sonnet card |
| S3 | (CONDITIONAL, opens only on the #367 self-referential verdict) theme-narrative corpus block + label guard + tests | Sonnet card, Fable review |
| S4 | unknownrate trend line in the weekly quality section | rides an existing card |
#233/#317 keep their own task lanes (already filed).

## 6. Test plan
S1: golden PR fixture → corpus contains the block, alias registered, gap-finder treats
fmp-pr answers as covered. S2: manifest matches assembled blocks byte-count-wise on a live
replayed corpus. S3: labeled-block guard — the judge prompt renders THEME CONTEXT distinctly;
a subject-news-only regression pin proves no leakage into is_primary_subject_news.

## 7. Operator sign-off forks (recs first)
- **H1** FMP PR onboarding now (rec — key exists, zero new vendors) vs direct wire vendors
  (BusinessWire et al: real money, revisit only if FMP coverage proves thin via the KPI).
- **H2** The <10% unknownrate done-ness bar (rec) — or tighter.
- **H3** §2.3 conditional pre-approved to execute on the #367 verdict (rec — the read itself
  is the gate) vs a separate sitting after the read.
