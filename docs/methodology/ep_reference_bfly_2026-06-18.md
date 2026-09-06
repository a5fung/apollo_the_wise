# BFLY 2026-06-18 — the EP we called "no catalyst", and why the news never reached us

**Operator-labelled a real EP twice** (2026-06-19 hard label: *"BFLY 6/18 **IS** an Episodic Pivot —
`routine` is the WRONG grade"*; again 2026-09-05). It is in
`docs/methodology/operator_labelled_eps.md` and `tests/fixtures/must_not_miss_eps.py`.

**Captured 2026-09-05, the same turn he pasted the release** — [[capture-operator-shared-notes]].

## What our system said, verbatim from `mi_ep_catalyst_metrics`

> "There is no concrete, verifiable company-specific catalyst driving BFLY's gap-up. The move
> appears entirely sentiment- and narrative-driven… No new earnings release, FDA decision, major
> contract, or 8-K filing has been identified as the trigger; absent a real hard catalyst, this is
> a narrative/momentum gap with no repricing of underlying fundamentals."

Perplexity, in the same corpus, called it *"an AI/MedTech narrative catalyst and being highlighted
as a top premarket mover, rather than… a single company-specific press release."*

**Both statements are TRUE OF THE CORPUS WE HELD.** The corpus was 5,219 characters and the string
`midjourney` appears nowhere in it. The grader did not misread the news — it correctly described a
news set that did not contain the story. **This is a retrieval failure, not a reasoning failure.**

## What actually happened (the operator supplied the release, 2026-09-05)

⚠ **PROVENANCE, corrected by the operator 2026-09-05: he read it on the COMPANY'S OWN IR NEWSROOM** — `ir.butterflynetwork.com/News/press-releases/news-details/2026/...`. The body carries a `(BUSINESS WIRE)` dateline so it went out on the wire too, **but the copy that is always reachable is the issuer's own site.** That distinction is the fix: a vendor may or may not carry a given release; an issuer's newsroom always has it, is free, and is deterministic.

**Butterfly Network press release, 06/18/2026** — *"Butterfly Network Provides
Commentary on Midjourney Medical's Full Body Ultrasound Scanner Announcement"*:



- Midjourney publicly announced **Midjourney Medical** and **The Midjourney Scanner**, a full-body
  tomographic imaging machine.
- **The prototype incorporates 40 Butterfly Ultrasound-on-Chip™ modules per system**, under a
  co-development agreement; future generations expected to use "substantially more".
- CEO Joseph DeVivo: the roadmap *"represents a potentially meaningful commercial opportunity for
  Butterfly."* Management discussed it at a 12:00 EDT TD Cowen webinar the same day.
- ⚠ **"Butterfly previously filed the terms of its agreement with Midjourney in a Form 8-K on
  November 17, 2025, which disclosed up to $74 million in expected payments to Butterfly over a
  five-year term."**

## The two findings, and they are different problems

**1. THE SEC PATH WAS NEVER GOING TO CATCH THIS. The 8-K is from 2025-11-17 — seven months before
the gap.** The 06-18 catalyst is a **same-day company press release over Business Wire**, not a
filing. Any fix framed as "fuse 8-K bodies" cannot address this class; the $74M number that makes
the story concrete lives in a filing that is old news by itself. **The freshness is in the partner's
announcement, not in any Butterfly disclosure.**

**2. THE STRUCTURAL CLASS: THE CATALYST ORIGINATED AT A THIRD PARTY.** What moved BFLY was
*Midjourney's* announcement. A ticker-scoped news search cannot see an announcement made by a
private company that does not carry our ticker — it becomes visible only once the company itself
comments, which Butterfly did the same morning, over the wire. **So the recoverable failure is
narrow and checkable: a same-day Business Wire release naming BFLY did not reach Polygon, Alpaca,
FMP or Perplexity in our capture.** Whether that is source coverage, timing (we graded before it
crossed), or a filter is the next question — and it has a yes/no answer.

**2b. CHECKED 2026-09-05 — NO VENDOR CARRIED IT.** Alpaca returned `[]`. Polygon returned one
headline, an unrelated congenital-heart AI editorial. Perplexity returned 500 characters of
premarket-mover commentary. FMP returned five, four of them generic screener filler — and one that
is the most instructive row in the whole case: *"Butterfly Network TD Cowen Call Puts Volatile
Growth Story In Focus"*, **the same 12:00 EDT TD Cowen webinar the press release announces.** A
vendor saw the event's shadow and still never carried the release that explains it. **So this is
not recoverable by tuning aggregators.**

**3. THE CANDIDATE FIX HIS CORRECTION POINTS AT: POLL THE ISSUER'S OWN IR NEWSROOM.** We depend entirely on aggregators (Polygon, Alpaca, FMP) plus a web synthesis (Perplexity). Every one is a bet that a vendor picked the release up AND tagged it with our ticker. **The issuer's newsroom is the primary source, is free, and cannot fail to carry the company's own announcement** — for BFLY it had the story while all four of ours did not. **The trigger is already defined by the 2026-09-05 measurement: a name gapping hard where we found no catalyst — 21 names, 5-7% of alerts. A bounded last-resort fetch, not a new firehose.** ⚠ Not built, not scoped: IR sites are per-issuer and unstandardised, so URL discovery, parsing and rate limits are a real design, not a config change.

⚠ **Do not generalise this into "our news is bad".** 21 of ~323 alerts since 05-01 were called
catalyst-less (5-7%), and the two other 20%+ names in that set (CHTR, SOUN) both fell over the
next 20 sessions, so the call may have been right on them. **BFLY is the one case where we
independently know the driver.**

## Why it graded `routine`

Separately from retrieval: the name entered the EARNINGS rubric path because
`_claude_text_signals_earnings` matched the words "earnings release" inside our own sentence *"No
new earnings release… has been identified"* — the regex had no notion of negation. It was then
downgraded `strong`→`routine` on `news_corpus_sparse_no_q_rev`, i.e. for lacking quarterly revenue
that a partnership catalyst could never have. **That regex bug was fixed and deployed 2026-09-05**
(`tests/test_448_earnings_signal_negation.py`, pinned against this exact text).
