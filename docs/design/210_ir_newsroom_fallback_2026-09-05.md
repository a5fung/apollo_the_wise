# IR newsroom fallback — fetch the issuer's own press-release feed when our news finds no catalyst (#210)

**Date:** 2026-09-05 (PT) · **Status: DESIGN + SCOPE — nothing built, nothing flipped, no live
behaviour changed.** · **Standard:** `docs/methodology/analysis_standard.md` (§6 sections present;
§1 questions answered in §0). · **Worked case it answers:**
`docs/methodology/ep_reference_bfly_2026-06-18.md`. · **Parent task:** `#210` (an accurate read of
the news).

> **First line, so he can stop here:** a plain-HTTP fetch of the issuer's press-release feed
> **works cleanly on 7 of the 21 trigger names (33%), is reachable-but-unparseable on 7, and is
> bot-blocked or dead on 7.** Where it reaches, it works: it would have found **BFLY's 06-18
> Midjourney release** and **JBIO's 06-01 Phase 1 results** — both names we called "no catalyst" —
> and it correctly returns nothing for CHRN 06-18. **Recommendation: build it as a bounded,
> premarket-only, fail-open SHADOW recorder (Phase 1 below), $0 for the fetch and under $0.10 a
> month for the shadow re-grade, and let the shadow rows decide whether it ever acts.**

---

## §0 · The decision this serves

**Operator, 2026-08-28:** *"i don't think it's one or the other, we can have multiple sources and
verify each, the goal is accuracy and it doesn't matter where it came from as long as we have
accurate read on the news."*

**Operator, 2026-09-05, the provenance correction:** the BFLY release he quoted was read on
**Butterfly's own IR newsroom** (`ir.butterflynetwork.com/News/press-releases/news-details/2026/...`).
The vendor copy may or may not exist; the issuer's copy always does.

1. **What decision does this serve?** Whether to add one more catalyst source — the issuer's own
   press-release feed — and if so, in what shape. It is a last-resort fetch on a bounded set
   (names that gapped hard where every feed we hold came back empty-handed), not a new firehose.
2. **What would change the decision?** Two numbers. (a) **Reachability**: if the issuer feed
   could not be fetched and parsed on most trigger names, the capability is not worth building
   — the task set the bar at "fails on 3 of 5". Measured below: it fails on roughly 2 of 3 under
   an honest User-Agent, but succeeds on the one case we can fully verify (BFLY) and on a second
   (JBIO). (b) **Would-be effect**: whether the added item would have changed the catalyst grade
   on a name that then went on to be a real EP. That is what the shadow phase measures; it
   cannot be known from here.
3. **What population answers it?** The 21 alerts since 2026-05-01 whose stored analysis declares
   no concrete catalyst (`docs/analysis/210_no_catalyst_sizing_2026-09-05.txt`): 3 of 63 in the
   20%+ gap band, 18 of 260 in the 10–20% band. Reachability was probed on **all 21**.
4. **What would make this wrong?** If the 21 are mostly correct "no catalyst" calls (two of the
   three 20%+ names — CHTR 06-29, SOUN 08-06 — fell over the next 20 sessions), the fetch adds a
   source that mostly confirms the status quo. That is fine for a shadow and is exactly why it
   must not act on its own. And if the structural trigger (§2.1) fires far more often than the
   prose count of 21 suggests, the "bounded" claim weakens — that number must be measured on
   prod before Phase 1 ships (§4).

---

## §1 · The premise, checked — does the issuer feed actually exist and parse?

**Method / population.** For each of the 21 trigger names I took the company website from
yfinance (`get_fmp_profile` is yfinance, the #624 lesson), derived candidate IR hosts and paths
(`ir.` / `investors.` / `investor.` subdomains; `/investors`, `/news`, `/press-releases`,
`/newsroom` and the Q4 feed path `/rss/pressrelease.aspx`; plus any RSS `<link>` the page
declares), fetched each with a **10-second timeout** and recorded status, latency, whether the
page carried dated headlines, and whether an RSS/Atom feed with dated items existed. Working
feeds were **re-fetched with the honest User-Agent the SEC fetcher already uses**
(`_SEC_UA`: "Apollo Research <email>") — the design must not depend on pretending to be a browser.
Scripts and raw captures: session scratchpad `ir_probe.py` / `second_pass.py` / `third_pass.py`
(to be filed under `scripts/probes/_210_ir_probe.py` in Phase 0). Probed 2026-09-05, one pass,
n = 21. ⚠ yfinance's own `irWebsite` field was present for only 4 of 21 and all 4 were stale
legacy URLs (`phoenix.zhtml`, `index.cfm`, a pre-merger domain) — it cannot be the discovery path.

### The tally (n = 21)

| outcome under plain HTTP + honest UA | n | names | what it means for the design |
|---|---|---|---|
| **Clean: a dated press-release feed parses** | **7** | CHRN, EWTX, NN, NUAI, BFLY, JBIO (RSS) · ALNY (HTML list with dates) | These are the names the fetch serves today. 4 of the 6 RSS feeds are the Q4 platform's `/rss/pressrelease.aspx`; CHRN's is its own platform's `/press-releases/rss`; JBIO is a WordPress `/feed`. |
| Reachable, but the list is JS-rendered or undated | 7 | LWLG, CHTR, WYFI, BRUN, GRRR, COHR, SOUN | A 200 with no parseable headline/date pairs. Not usable without per-site work. |
| Bot-blocked (403) or dead end | 7 | FN, ENPH, ACLS (Notified/Q4 `investor.*` hosts, 403 in ~120 ms with a browser UA and a 10 s tar-pit with the honest one) · NEXA, CECO (403 on every host) · AUGO (Portuguese-language site, no IR feed) · NVTS (single-page app answering 200 to every path — a soft-404) | Unreachable **by policy** — we do not evade bot management. Record as `blocked` and stop. |

**So 7 of 21 (33%) clean — the task's own "fails on 3 of 5" bar is roughly met.** The doc proceeds
anyway for three reasons stated plainly: where it reaches it is decisive (below); the clean third
is the Q4-hosted small/mid-cap population that dominates EP alerts; and the design's first slice
is a shadow that costs nothing when it cannot reach.

### Where it reaches, it works — three verified cases

| name · alert date | what the issuer's own feed shows | our stored call | verdict |
|---|---|---|---|
| **BFLY · 2026-06-18** | The release *"Butterfly Network Provides Commentary on Midjourney Medical's Full Body Ultrasound Scanner Announcement"* is live at the Q4 URL pattern (`/news/press-releases/news-details/2026/<slug>/default.aspx`, 200, 0.7 s, body server-rendered, "Midjourney" in the text). The feed answers the honest UA in 0.34 s with 10 items, each `title + pubDate (ET offset) + link`, **no body**. | "no concrete, verifiable company-specific catalyst" | **Confirmed retrieval miss** — the reference case. |
| **JBIO · 2026-06-01** | `jadebiosciences.com/feed` (WordPress, honest UA, 0.2 s): *"Jade Biosciences Announces Positive Interim Phase 1 Results for JADE101 …"* with `pubDate` **Mon 01 Jun 2026 11:00:24 UTC = 07:00 ET**, the exact alert date, and a May 29 pre-announcement of the 8:00 ET call. | in the 21 "no catalyst" names | **A second same-day issuer catalyst on a name we called catalyst-less.** ⚠ Whether our corpus (5,733 chars) contained it is not checkable from this machine; the release was public at 07:00 ET, before the first scan tick's grade. |
| **CHRN · 2026-06-18** | `ir.chronoscale.com/press-releases` lists Jun 4, Aug 18, Aug 27 2026 — **nothing on Jun 18**. | in the 21 | **Fetch would correctly return "no same-day item"** — the "no catalyst" call stands. This is the negative the shadow needs. |

**Not verifiable from here:** ALNY 07-09 (its HTML list ignores `?page=`, only the 10 newest show);
the four other Q4 names (the feed holds the 10 newest items, and the listing page is JS-rendered).
**A Q4 feed is a 10-item window** — a same-day release is item 1 on the day, but historical backfill
through the feed is impossible for anything older than ~10 releases. Backfill of the 21 is a hand
check on the 7 reachable sites, not a script.

### Latency and shape facts the design rests on (measured, honest UA)

- Q4 RSS: 0.26–0.54 s. WordPress feed: 0.20 s. Detail page (body): 0.14–0.69 s. Worst host seen:
  GRRR's investor site at **8.6 s** (would time out under the 5 s budget — fine, fail open).
- Q4 and WordPress feeds carry `title`, `pubDate`, `link`; **Q4 carries no description** — the body
  is one more GET of `link`, which is server-rendered HTML (~72 k chars raw → strip to text).
- Q4 listing HTML pages are **2.9 k chars with zero dates** — the list loads by script. HTML
  scraping of Q4 sites is a dead end; the feed is the only plain-HTTP path.
- Bot management fingerprint: `investor.<company>.com` hosts returned 403 in ~100–190 ms to a
  browser UA and **timed out at 10 s** to the honest UA (FN, ENPH, ACLS). Treat any 403 or
  timeout on discovery as `blocked`, negative-cache it, never retry with a different identity.

---

## §2 · The design

### 2.1 Trigger — the exact predicate and where it sits

**Predicate (structural, not prose):** after the catalyst grade is in hand,

```
llm_catalyst_quality == "routine"
AND has_direct_source is False        # corpus_provenance(): no same-day SEC body, no primary-subject Benzinga wire
AND gap_pct >= MIN_GAP_PCT            # the acting floor, 9.0 (ep_detector.py:113) — read at run time, never hardcoded here
AND _is_premarket(now_et)             # strictly before 09:30 ET — the same guard both #344 shadows use
AND not already checked today         # once per ticker per day
```

This is BFLY's exact shape: routine, no SEC filing, no wire, big gap, premarket. It deliberately
does NOT read the analysis prose ("no concrete catalyst…") — the four `NEGATIVE_CATALYST_MARKERS_BASE`
phrases would not even match BFLY's sentence, and a prose gate drifts with prompt wording.
`has_direct_source` is already computed on the uncached grade tick and rides the cache
(`CachedGrade.has_direct_source`), so the predicate costs no I/O.

**Two hook points, both required — the second is the BFLY mechanism:**

1. **Uncached grade tick** (`run_ep_scan`, right after the `ep_catalyst_provenance` audit emit,
   ~`ep_detector.py:4340`): the first time a name is graded routine with no direct source.
2. **Cached-routine tick** (the #344 re-poll precheck, ~`ep_detector.py:4160`): BFLY's release went
   out at 08:05 ET and the routine grade was at 07:00. A first-grade-only hook misses the
   motivating case. Add an `ir_checked` flag to `_repoll_shadow_state[ticker]` beside the Benzinga
   `count`; on each premarket tick where the cached grade is still routine and `ir_checked` is
   False, run the fetch once. (`should_repoll_shadow` stays as it is — this is a sibling check,
   not a replacement for the Benzinga count.)

**Bounds:** at most **3 IR fetches per scan tick** (a sector-flood morning could otherwise queue
20), the rest deferred to the next tick; the `_repoll_shadow_state` flag makes it once per ticker
per day across both hooks.

⚠ **The prose count (21 since 05-01, ~5 a month) is NOT the count of this predicate.** The
structural predicate is a different population and was not measurable from this machine (prod
access denied in this session). It is Phase 0's first query: count `ep_catalyst_provenance`
audit rows with `catalyst_quality='routine' AND has_direct_source=false` joined to `mi_ep_alerts`
gap bands since 05-01. If it is many times larger than ~5/month, tighten with the gap band
(20%+ first) before shipping Phase 1.

### 2.2 URL discovery — per-issuer, unstandardised, so cache it

**Cache, not live discovery, on every trigger.** `mi_ticker_overrides` is the precedent (per-ticker
persistent cache: description, sector, industry, company_name). Add:

| column | meaning |
|---|---|
| `ir_feed_url TEXT` | the feed (or dated HTML list) that parsed |
| `ir_feed_kind TEXT` | `rss` · `html` · `none` |
| `ir_probe_status TEXT` | `found` · `blocked` (403/timeout on the IR hosts) · `none` (reachable, nothing parseable) |
| `ir_probed_at TIMESTAMPTZ` | negative cache: a `blocked`/`none` is not re-probed for **30 days** |
| `ir_feed_source TEXT` | `probe` · `operator` · `gap_finder` — who set it |

**Three ways the cache gets filled, in order of cost:**

1. **Bounded probe on first trigger** (≤ 8 GETs, then stop): from the yfinance `website`, take the
   **registrable domain** (`charter.com`, not `corporate.charter.com` — CHTR's IR lives on
   `ir.charter.com` and the probe missed it by deriving from the subdomain). Try, in this order:
   `ir.<d>/rss/pressrelease.aspx`, `investors.<d>/rss/pressrelease.aspx`,
   `investor.<d>/rss/pressrelease.aspx` (the Q4 feed — 4 of the 6 RSS hits), then
   `<ir-host>/press-releases/rss` (CHRN's platform), then the IR root
   pages for a declared `<link rel="alternate" type="application/rss+xml">`, then
   `<website>/feed` (WordPress), then `<website>/press-releases` as a dated-HTML fallback.
   **Acceptance test for a feed:** ≥ 1 item with a parseable date AND at least one title passing
   `is_primary_subject_news` against the company name (so a corporate blog or a site-wide feed —
   ALNY's `rss.xml` opened with a "Corporate Responsibility Report", AUGO's with "Olá, mundo!" —
   does not get cached as the press feed). A soft-404 (NVTS: 200 for every path, same title)
   fails this test by construction.
2. **Operator-supplied** (`/irfeed TICKER URL`, Phase 2): he reads these sites. One line, cached
   as `operator`, never overwritten by a probe.
3. **The weekly source-gap finder** (`source_gap_finder.py`, Sunday 08:45 ET, already ≤ 8
   Perplexity calls a week) already answers `SOURCE_CLASS: ir_page` for unknown movers. Extend its
   prompt by one field, `IR_URL:`, and seed the cache with it as `gap_finder`. No new spend — the
   calls already run.

**When we can't find it:** write `ir_probe_status` (`blocked` / `none`), emit the shadow row with
`ir_status` set to the same value, and stop. That row IS the coverage metric — the Sunday review
should be able to say "of N triggers this month, k had no reachable issuer feed". Nothing else
happens; "no catalyst found" remains the status quo.

### 2.3 Parsing — minimum viable, fail-safe

- **RSS/Atom with the standard library** (`xml.etree.ElementTree`) — no new dependency. Extract per
  item: `title`, `pubDate`/`published`, `link`. Normalise the date to an **ET calendar date** with
  `ZoneInfo("America/New_York")` (Q4 stamps `-0400`, WordPress stamps UTC; a 20:05 UTC WordPress
  release is a 16:05 ET same-day item). The datetime-hygiene gate `[5h/7]` applies; no `pytz`.
- **Same-day rule:** keep an item if its ET date == the alert date, **or** it is dated the prior
  trading day at or after 16:00 ET (an after-close release is next morning's gap).
- **Body:** at most **2** same-day items; for each, one GET of `link`, `_strip_html` (the SEC
  fetcher's helper, `collector.py`), keep the **first 3,000 characters after the first occurrence of
  the title** (the substance follows the headline; the 70 k-char page is mostly chrome). If the
  body GET fails or is empty, keep the headline + date alone — a dated same-day issuer headline is
  already more than the corpus held for BFLY.
- **HTML-list fallback** (`ir_feed_kind = html`, ALNY-class only): a dated-headline extractor —
  scan for `Mon DD, YYYY` / `MM/DD/YYYY` tokens and take the nearest anchor text. Deliberately
  crude; it exists so ALNY-shaped sites are not a special case in the caller.
- **Unrecognised layout / any exception** → `ir_status = parse_failed`, no raise, no Telegram
  (an audit row only — the no-silent-failures gate `[5k/7]` wants it logged, not swallowed).

### 2.4 Where the result goes — shadow first, then the same shape every other source uses

**SHADOW (Phase 1) — a record every trigger can reach.** ⚠ `mi_ep_catalyst_metrics`'s `raw_*`
columns cannot be the shadow home: `persist_catalyst_metrics` runs only inside the
earnings-revenue-gate branch (`strong`/`game_changer`), so a routine-with-no-source name — the
entire trigger population — never gets a row there. (BFLY has one only because the negation-regex
bug routed it through the earnings path.) The shadow record therefore goes to:

- a new table `mi_ir_newsroom_shadow` in `db.py` (single source of truth for schema), one row per
  `(ticker, alert_date)`: `trigger_tick_et`, `hook` (`first_grade` / `cached_repoll`),
  `ir_status` (`same_day_item` · `no_same_day_item` · `blocked` · `none` · `parse_failed` ·
  `timeout`), `feed_url`, `same_day_items JSONB` (title, date, link, body_chars),
  `latency_ms`, `live_quality`, `shadow_quality`, `shadow_analysis`, `created_at`;
- plus one audit event `ep_ir_newsroom_shadow` per row (the `ep_repoll_shadow` pattern) so the
  Sunday weekly review and `/audit` see it without a new surface.

`mi_catalyst_tier_shadow` (UNIQUE `scan_date, ticker`, already carrying `grounded_head` /
`claude_analysis`) was considered and rejected as the home: it is the lattice's record of what the
grader SAW; mixing in what it WOULD have seen muddies the #593 evidence.

**ACT (Phase 3, operator-gated) — follow the existing source shape exactly:**

- **Corpus:** a stamped part in `build_grounded_text`, `[IR newsroom <YYYY-MM-DD>] <title>. <body>`,
  placed **after the SEC body and before the Benzinga wires** — issuer-authored is a direct source.
  `assemble_grade_corpus` inherits it (it calls `build_grounded_text` for today's news) and the
  `DATE CONTEXT` anchor already handles freshness.
- **Provenance:** `corpus_provenance` adds `sources["ir_newsroom"] = n` and counts it as direct
  (`has_direct = … or k == "ir_newsroom"`) — so the `#211` unknown-rate KPI and the alert's
  "catalyst discovery" display line both see it.
- **Raw persistence:** `raw_ir_newsroom_json JSONB` on `mi_ep_catalyst_metrics` beside
  `raw_alpaca_news_json`, written by `persist_catalyst_metrics` from a `_raw_ir_newsroom` key —
  the same pop-and-bind pattern. **Known limitation carried forward:** that table is populated on
  the earnings path only, so the source-quality coverage number for this source will be partial by
  construction; the complete record stays in `mi_ir_newsroom_shadow`.
- **Source quality:** add `("raw_ir_newsroom_json", "IR newsroom", "array")` to
  `news_source_quality.SOURCES` and `"investor relations"` / `"ir page"` to
  `INGESTED_FEED_ALIASES` — one place, or the gap finder keeps recommending a source we now read.

### 2.5 🛑 THE LINE — why shadow-first is structural here, and what would justify acting

This feeds the catalyst grade → `ep_score` (routine 0 → strong +15 → game_changer +25 points
against a 65–80 bar) → admission → real orders. **So it does not touch the live grade, the cache,
or `grounded_text` in Phase 1 or 2.**

**What the shadow records instead:** on `same_day_item`, it builds the corpus WITH the IR part
(`build_grounded_text(sec, benzinga, perplexity)` + the IR part) and calls
`_classify_catalyst_claude` on it **once** → `shadow_quality`, `shadow_analysis`, stored beside
`live_quality`. Nothing reads them on the live path. This is the same telemetry-only shape
`ep_grade_enrich_shadow` used before #347 flipped.

**Evidence that would justify acting (the operator's call, not mine):**

| the question | the number, from the shadow rows | the bar |
|---|---|---|
| Does it ever change the grade? | rows with `shadow_quality != live_quality` | n ≥ 10 such rows (at ~5 triggers/month with ~1/3 reachable, that is a few months; sooner if Phase 0 shows the structural trigger is larger) |
| When it upgrades, was it right? | forward 5- and 20-session move of the upgraded names — **tail first** (count ≥ 20% moves, p90), then median, per `analysis_standard.md` | upgraded names must not sit in the losing bucket; operator-labelled EPs (BFLY, JBIO if he labels it) must land on the upgrade side |
| Does it ever wrongly upgrade a pump? | upgraded rows where the same-day item is a financing / conference / inducement grant | any such row is a rule for the same-day filter, before any flip |

**The CHANGE_PROCESS step for the flip:** a dated change-log entry in `docs/setups/magna53_ep.md`
(Trigger: BFLY 06-18, JBIO 06-01 · Evidence: the shadow table, n stated · Anticipated effect: "≤ N
routine→strong upgrades a month" · Reversion-flag: **NEW** · Status: shipped, awaiting field
validation), **operator sign-off on the list of names the shadow would have upgraded** (rule 3 — a
source that can lift a grade over the bar is a gate on entries), the same-commit SSoT update, and
the judge-eval regression gate `[5m/7]`. **Acting mechanism when flipped:** the existing re-poll
"cache-only apply, next tick" path — the IR-driven grade rewrites `_catalyst_cache` with
`filters_cleared=False`, so the NEXT tick re-runs the post-grade filters and proceeds exactly as
any fresh survivor. No new live path is created; the flip is a runtime toggle `ir_newsroom_live`
(the #400 pattern: `mi_safeguard_state` row overrides env, ≤ 60 s, no redeploy), default OFF.

### 2.6 Timing and safety — this sits on the order-submission path

- **Premarket-only**, via the existing `_is_premarket` guard (strictly before 09:30 ET). The scan
  runs every 5 min 07:00–09:55 ET; ORB submission is 09:31–09:44. Both #344 shadows already
  confine their SEC GETs and Sonnet call to premarket for exactly this reason; this fetch inherits
  the same fence. **Zero added latency inside the ORB window, by construction.**
- **Timeout:** one `asyncio.wait_for(…, 5.0)` around discovery + feed + body per ticker (measured
  path: 0.3–1.5 s typical; GRRR's 8.6 s host times out and fails open). Per-request `httpx` timeout
  3 s, `follow_redirects=True`, `_SEC_UA`-style honest headers.
- **Concurrency:** the grade loop is sequential (`for c in candidates[:SHORTLIST_SIZE]`,
  `run_ep_scan`, `ep_detector.py:3732`);
  ≤ 3 fetches per tick → worst case **+15 s on a premarket tick**, never on a 09:30+ tick. The
  shadow re-grade goes through the existing `_ANTHROPIC_SEMAPHORE` (5).
- **Politeness:** honour `robots.txt` (fetched once per host, cached with the URL); ≤ 1 request/s
  per host; 30-day negative cache on `blocked`/`none`; the discovery probe is once per ticker, not
  once per trigger. **No browser User-Agent, ever** — a 403 is "unreachable", not a challenge.
- **Failure mode: fail OPEN, loudly in the audit log, silently to the operator.** Every branch
  returns "no IR item", which is the status quo; the reason lands in `ir_status` and one
  `ep_ir_newsroom_shadow` row. No Telegram (transient/self-healing → audit only).
- **Live path vs post-hoc backfill:** a nightly post-hoc fetch (17:30 ET audit job) would be safer
  still but **could never change an entry**, so it cannot produce the one number that matters
  (would the grade have moved in time to act). The premarket shadow is already fail-open and
  fenced off the ORB window; that is the recommended slice. If Phase 1's `latency_ms` telemetry
  shows premarket ticks running long, the fallback is to move the fetch to a background task
  whose result the next tick reads — the same "next tick" semantic the re-poll uses.

### 2.7 Cost — one number

- **Fetch: $0.** Plain HTTP to public feeds; no API, no key, no vendor.
- **Shadow re-grade: ≈ $0.014 per call** on the grade model (`claude-sonnet-4-6`,
  `pricing_for` → $3 in / $15 out per million tokens; ~3 k input tokens for a 6,000-char corpus +
  ~300 output). It runs **only** on `same_day_item` rows — at ~5 triggers a month and a third
  reachable, that is **under $0.10 a month**, and under $1 for the whole shadow period.
- **Perplexity: no new calls** — the gap-finder seeding rides the existing ≤ 8/week budget.
- **The whole path priced up front:** Phase 0 $0 · Phase 1 < $0.10/month · Phase 2 $0 · Phase 3
  no new spend (the IR part joins a call that already happens).

### 2.8 Phasing — each phase one card

| phase | what ships | who | evidence it produces | gate to next |
|---|---|---|---|---|
| **0 — size and file** ($0, no deploy) | Prod SQL: count the structural trigger (§2.1) since 05-01 by gap band. File the probe as `scripts/probes/_210_ir_probe.py`. Hand-check the remaining reachable names' newsrooms on their alert dates (EWTX 06-01, NN 06-03, NUAI 06-22, ALNY 07-09 — 4 sites, minutes). | Sonnet card | the trigger's true monthly rate; the same-day hit rate on reachable names (n ≤ 7) | trigger rate is bounded (or a gap band that bounds it is named) |
| **1 — shadow recorder** | `collector.get_ir_newsroom_items(ticker, alert_date, company_name)` (discovery + cache + parse + body, fail-open); `mi_ticker_overrides` columns; `mi_ir_newsroom_shadow` table; the two hooks in `run_ep_scan`; `ep_ir_newsroom_shadow` audit event; toggle `ir_newsroom_shadow` default ON; tests on fixture feeds (a Q4 RSS, a WordPress RSS, ALNY-shaped HTML, a soft-404, a 403). Deploy `market-agent` in a window. | Sonnet card (mechanical, well-specified); Opus verifies live: first shadow row + first `blocked` row | the shadow table filling; `latency_ms`; per-status counts | ≥ 10 `shadow_quality != live_quality` rows, or the operator's call sooner |
| **2 — fill the cache** | `/irfeed TICKER URL` (handler + dispatch + `BotCommand` in `channels/telegram.py` — orchestrator scope, so deploy `both`); `IR_URL:` field in `source_gap_finder` feeding the cache; a Sunday-review line: triggers / reachable / same-day items this week. | Sonnet card | reachable share rising from 33% as he feeds URLs | none — telemetry |
| **3 — act** (🛑 operator-gated) | §2.4 ACT wiring behind `ir_newsroom_live` default OFF; `magna53_ep.md` change-log entry; sign-off on the would-have-upgraded list; judge-eval gate. | Fable (grade-path change, adversarial review) → operator flip | the flip's field validation ("shipped + validated against N live sessions") | — |

---

## §3 · The numbers

| measure | value | n |
|---|---|---|
| trigger names since 2026-05-01 (prose predicate) | 21 (3 of 63 at 20%+ gap = 5%; 18 of 260 at 10–20% = 7%) | 323 alerts |
| issuer feed parses cleanly under an honest UA | 7 of 21 = 33% | 21 |
| reachable but unparseable (JS-rendered / undated) | 7 of 21 | 21 |
| bot-blocked or dead | 7 of 21 | 21 |
| Q4-platform feeds among the clean RSS hits | 4 of 6 | 6 |
| clean names verifiable on their alert date | 3 of 7 (BFLY: catalyst present · JBIO: catalyst present · CHRN: nothing) | 7 |
| yfinance `irWebsite` usable for discovery | 0 of 4 present were current | 21 |
| feed latency, honest UA | 0.20–0.54 s | 6 feeds |
| body page latency | 0.14–0.69 s | 3 pages |
| worst host seen | 8.6 s (GRRR) | 1 |
| shadow re-grade cost | ≈ $0.014 per call; < $0.10/month | — |

---

## §4 · What this does not answer

- **The structural trigger's real rate.** The 21 is a prose count; the predicate in §2.1 is
  structural and was not measurable here (prod access denied this session). Phase 0, first query.
- **Retrieval vs reasoning on JBIO.** The issuer released Phase 1 results at 07:00 ET on the alert
  date; whether our 5,733-char corpus contained them is unknown from this machine. If it did, JBIO
  is a grader miss, not a source miss — and this design does not fix that.
- **The 14 non-clean names.** Whether FN, ENPH, ACLS, CECO, NEXA (blocked) or the 7 JS-rendered
  sites had a same-day release is unknown; they are outside what plain HTTP can reach. The
  reachable share improves only through the operator's `/irfeed` and the gap-finder seeding.
- **Q4's JSON API.** Q4 sites serve their listing through `feed/PressRelease.svc` behind a
  per-site key embedded in page script. Not pursued: it is undocumented, per-site, and the RSS
  already answers the same-day question.
- **Wire-side per-company pages** as an alternative discovery route: Business Wire's newsroom
  search returned 403 to both UAs; GlobeNewswire's keyword search answered the honest UA (0.3 s,
  dated) but timed out for the browser UA — unstable, not designed on.
- **Name-scoped aggregator RSS (untried alternative, not the ask).** Google News RSS
  (`news.google.com/rss/search?q="<company name>"`) answered in 0.4–0.6 s with **100 items** and
  short descriptions for both BFLY and FN, and — because it is keyed on the company NAME, not the
  ticker — it is the only path probed that could surface a third-party announcement (Midjourney's)
  **before the issuer comments**. Caveats that keep it out of this design: it is another
  aggregator, an unofficial endpoint with no terms for automated use, and it carries no body
  (links are redirectors). Worth a side-by-side column in the Phase 1 shadow if the operator wants
  the third-party class covered earlier than the issuer's own comment; his provenance correction
  points at the issuer's site, and that is what this document designs.
- **Whether acting improves expectancy.** That is the shadow's output, not this document's.

---

## §5 · ⚖ THE LINE

This capability feeds the catalyst grade, which moves `ep_score`, admission, and real orders.
**Nothing here changes a live grade, a threshold, a safeguard, sizing, or an entry.** Phases 0–2
are a read, a recorder and a cache. Phase 3 — letting the issuer's item into the live corpus — is
the operator's decision, taken on the shadow table's numbers through `CHANGE_PROCESS`, with his
sign-off on the names it would have upgraded, and behind a toggle he can turn off in a minute.
Nothing was flipped in producing this document.
