# Missed EP — BFLY 2026-06-18 (catalyst-sourcing evidence case for #210)

**One-liner:** BFLY (Butterfly Network) ran +56% on a Midjourney AI-imaging
partnership announcement and we fired **no real-time EP alert** on any track.
Root cause = **catalyst-sourcing gap** (#210): the actual deal never reached the
grader's news corpus, so the catalyst graded `routine`, which mathematically caps
the MAGNA53 score below the alert threshold regardless of the gap.

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

## Root cause = #210 (catalyst sourcing), not a grading bug

The grader behaved correctly given a corpus that lacked the real catalyst. The
catalyst was a **partnership / commercial-deal announcement** — the kind of event
that lives in an **8-K Item 1.01 (material agreement) or a PR-wire press release**,
NOT in earnings data and NOT reliably discoverable by LLM web-scrape (which returned
only "AI imaging theme" ambient chatter). This is precisely the failure mode #210
(direct primary sources over LLM-discovery) exists to fix; see memory
`feedback_catalyst_sourcing_direct_over_llm` ("LLMs confabulate when discovering;
reliable only when judging grounded text").

The specific leg BFLY stresses: **the partnership / commercial-deal 8-K + PR-wire
sourcing path.** #238 already covers the EDGAR *negative*-catalyst leg (dilution
S-3/424B5/8-K-3.02); BFLY shows the symmetric *positive* leg (8-K 1.01 partnership)
is equally unsourced today.

## Secondary smell (not the cause; self-corrected here)

The `_claude_text_signals_earnings` text fallback fired a **false earnings signal**
on a non-earnings day (`earnings_source=no_match`), routing a partnership catalyst
through the earnings Q-rev rubric, which then downgraded it on missing quarterly
data. It self-corrected back to `routine` (same end state), so no net harm THIS time
— but it means a partnership catalyst gets forced through the wrong rubric. Worth a
glance when #210/#211 land a partnership path: the earnings text-fallback shouldn't
claim a non-earnings deal day.

## Implication

- File as a named evidence case under **#210** (partnership/8-K-1.01 + PR-wire leg).
- This is a clean "lost-alpha" case (+56% EP, zero real-time alert) — the operator-
  facing kind of miss that justifies the direct-sourcing backbone investment.
- No tonight fix: the remedy is the #210/#211 build (direct deal sourcing), not a
  threshold tweak. A threshold/gap-override band-aid would re-admit the routine-
  catalyst noise the 50-floor is designed to filter.
