# #167 Lane-2 narrative detector — grouping-quality audit (2026-07-27)

**Operator question:** "is the path to gauge common story right — are we discovering the subtle theme for 2+ EPs well?" Not fire-rate: grouping quality.

**Scope:** analysis only, prod read-only. No detector/prompt/threshold changed. Everything in §6 is a PROPOSAL, operator-gated via CHANGE_PROCESS.

## Verdict

**The mechanism is precise but shallow: it groups only when the shared narrative is explicitly
NAMED in both catalyst snippets. It cannot discover a subtle theme, because it never sees the
evidence a subtle theme needs.** On the 13 no-story days old enough to judge: **3 genuine misses,
1 borderline, 9 correct declines** (~23% miss rate). Both accepted proposals were real linkages
(precision 2/2). All 3 misses are the same failure shape — a cross-sector demand-side story
(AI-infrastructure buildout ×2, precious metals ×1) written in company-event language the
280-char input can't surface. The leading "prompt is biased to decline" hypothesis was **tested
and disconfirmed** as the primary driver (§5): a neutrally-framed Sonnet given the same inputs
declines the same groupings. The binding constraints are **input richness** and the **same-day
window**, not prompt wording.

## 1. Population (forward era, 2026-06-08 → 07-24, N=33 runs)

From `mi_audit_log` `narrative_theme_discovery_ran`: 15 runs dropped by the <2 gate (9 days with
exactly 1 qualifying alert, 6 with 0), 18 grouped runs → 16 "no story" + 2 proposals
(06-25 `{MU,SNX}` AI memory/infra; 07-20 `{HUT,IREN}` miners→AI pivot). Candidate texts examined: 54.

## 2. Core test — were the 16 "no story" days correct?

Ground truth used (no LLM-grades-LLM circularity):
- **Later shared-theme membership**: for every day's candidate set, did ≥2 tickers later co-appear in
  any `mi_themes` row or any `mi_theme_candidates_shadow` row (all sources)? **Result: 0 pairs, all 16
  days.** (Weak evidence for cross-sector pairs — Lane 1 structurally fragments those; used as
  corroboration only, never sole grounds.)
- **Co-movement**: SPY-adjusted daily-return pairwise correlation over D+1..D+15
  (`mi_daily_closes`). Null baseline from 1,509 cross-cohort pairs on identical windows:
  mean +0.05, p90 +0.49, **p95 +0.58**. In-cohort corr ≥ ~0.55 = top-5% signal.

| Day | Candidates | Verdict | Evidence |
|---|---|---|---|
| 06-11 | IDCC ELVN NAVN | correct | 3 unrelated stories; corr ≤ +0.03 |
| 06-12 | SHAZ AKTS | correct | AI contract vs Lilly oncology; corr −0.42 (both ripped, independently) |
| **06-15** | HQ MMYT **HYMC XE AUGO IDR** | **MISS (input-caused)** | HYMC-AUGO +0.67, HYMC-IDR +0.66, AUGO-IDR +0.57 — all ≥p90-95. Three precious-metals miners on a silver-thesis day; but 2 of 3 catalyst texts said "no identifiable catalyst" — the story was invisible to the model |
| **06-17** | QURE **AEHR JBL** LZB | **MISS** | AEHR-JBL **+0.71** (>p95). Both texts name AI-infrastructure INSIDE the visible 280 chars (AEHR "semiconductor and AI-related names… alongside INTC/MRVL"; JBL "AI data center infrastructure platform" w/ Adani). Same breadth as the ACCEPTED 06-25 MU+SNX grouping (memory + distribution under one AI-capex story) |
| 06-18 | UUUU SWBI | correct | uranium vs guns; corr −0.11 |
| 06-22 | **MLTX** JBIO DFTX **SYRE** | borderline | MLTX-SYRE +0.43 (~p90); both immunology/inflammation clinical winners, and SYRE was ALREADY in the live "Inflammatory Disease & Immunology Biologics" theme. Spec-compliant decline (prompt bans catalyst-category groupings) — whether the spec matches operator intent ("subtle theme") is the open call |
| 06-24 | ABSI FCEL WEN | correct | ABSI-FCEL +0.56 but genuinely unrelated stories — corr alone ≠ story (the guard against pure-price grouping is right). FCEL's data-center-power story was already Lane-1-tracked ("AI Data Center Power Infrastructure" theme, 06-11→07-13) |
| 06-29 | OUST CHTR QDEL | correct | all pairs negative corr |
| 06-30 | SEDG AVAV | correct | corr −0.42 |
| 07-08 | PENG **KC** | correct outcome, blind decision | corr −0.41 says no real cohort — but KC's text described **wheat futures**; KC is Kingsoft Cloud, an AI-cloud name adjacent to PENG's active AI-cloud theme. The decline was right by luck, not by sight |
| 07-10 | WDFC CRCL | correct | corr −0.42 |
| **07-14** | **CLSK TSEM** | **MISS** | corr **+0.55** (n=8, ~p95). CLSK = a bitcoin miner signing a $6.6B 20-yr AI-data-center lease — **the exact narrative the lane accepted 6 days later** for HUT+IREN; TSEM = govt-backed AI/data-center chip capacity. CLSK was never captured by ANY lane (no theme membership since Mar) — this was the system's only shot and it declined |
| 07-15 | PRG MANE | correct | unrelated (upgrade vs Ph2 data); window too short for corr |
| 07-22/23/24 | ARWR SMCI EFOR · NVCR CLF · WKC THC | likely correct | texts unrelated; ≤2 days of price data — objectively unjudgeable yet |

**Score: 3 misses + 1 borderline out of 13 judgeable days.** All misses share one failure shape:
demand-side cross-sector cycles expressed as company events.

The dropped-run side compounds it: the miner→AI cohort accreted ACROSS days — **WULF 07-06 (lone,
ep 96, 20-yr Anthropic lease → killed by the <2 gate) → CLSK 07-14 (declined) → HUT+IREN 07-20
(accepted)**. July pairwise corr of WULF/CLSK/HUT/IREN: +0.47 to +0.87. The lane watched a 4-name
narrative through a same-day pinhole and caught the last 2 members, 2 weeks late.

Precision side: both proposals check out (MU-SNX +0.53 top-decile; HUT-IREN +0.83; on 06-25 it
correctly grouped MU+SNX while excluding the unrelated third alert KYMR). Note MU/SNX fwd-10d
returns were −22%/−12% market-adjusted — grouping quality ≠ trade quality.

## 3. Input quality — the leading hypothesis, confirmed

What the model gets per ticker: `ticker (gap X%, ep Y): catalyst[:280]`.

- **`catalyst` is hard-truncated at 500 chars in 62/62 forward-era qualifying alerts** (100% cut
  mid-sentence), and the prompt keeps only the first **280** — mostly Perplexity preamble ("X
  gapped up because…").
- Meanwhile the same alert rows carry **`grounded_text`** (SEC-8-K-grounded body): populated for
  **50/62 (81%)**, median **7,413 chars**. Lane-2 sees ~4% of the grounded evidence that already
  exists on the row. `claude_analysis` (median 722 chars, grounded when a direct source exists —
  the #360 QURE lesson) is also unused unless `catalyst` is empty.
- **~20% of candidate texts (11/54) are "no identifiable catalyst" boilerplate or worse**, incl.
  outright ticker misidentification: KC graded as wheat futures (it's Kingsoft Cloud), SG as the
  Singapore exchange (Sweetgreen), HQ unresolved. The 06-15 miss is directly input-caused: 2 of
  the 3 co-moving miners had "no catalyst" text.
- The revealed acceptance rule follows: **both accepted proposals had the shared driver literally
  named in both snippets** ("AI infrastructure/AI server demand" 06-25; "AI cloud/data center
  contracts" 07-20). When it must be inferred (CLSK's text never says "AI" — "global technology
  company… data center campus"), the lane declines.

## 4. The <2 gate (15/33 runs killed)

6 zero-alert days are unfixable (nothing qualified). The 9 lone-alert days are not: they included
**WULF 07-06 (ep 96)** and **DOCN 07-07 (ep 115** — record AI-driven acceleration, right after its
Lane-1 cloud theme faded**)**. A lone alert is only ungroupable against a SAME-DAY set — against a
rolling recent-alert pool or the active-theme/narrative roster it is groupable (the "new joiner"
idea, `docs/architecture/theme_engine.md` ~L106; the judge already does a read-only version for
grading, but nothing grows a cohort). Concretely: a 10-day rolling pool on 07-14 contains
{WULF, DOCN, PENG, KC, WDFC, CRCL, CLSK, TSEM} — WULF+CLSK is exactly the miner-pivot pair, six
days before live caught it.

## 5. Prompt bias — tested, and NOT the primary driver

The prompt carries 8 restrictive clauses vs 2 permissive, states the empty-set escape twice, and
requires "truly share". Suspicious on its face — so it was tested: a fresh Sonnet
(production tier), **neutral editorial framing** (organize each day's stocks into wrap paragraphs;
no "truly", no empty-list steer, grouping presented as normal), **identical 280-char inputs**,
3 test days + 2 controls, blind. **Result: it declined every grouping production declined**,
including AEHR/JBL and CLSK/TSEM (kept every stock standalone; controls also standalone —
supplement, n=1/day, reported separately from the objective evidence per audit design).
Given the same inputs, the neutral frame reproduces the declines → rewording "truly"/"themes=[]"
is unlikely to buy recall. What both prompts share is the real bias: each stock is presented as an
independent company event to be explained, and nothing invites demand-side/customer-side linking
("who is buying" — the axis all 3 misses sit on).

## 6. Proposals (operator decision; CHANGE_PROCESS + replay before any change — the lane is shadow/advisory, but these alter detection behavior)

Ordered by evidence strength:

1. **Feed richer input** — replace `catalyst[:280]` with `claude_analysis` or the first ~1-2k chars
   of `grounded_text` (fallback to catalyst). Evidence: §3 — 100% truncation, 20% junk, 06-15 miss
   input-caused, both accepts required the story to be pre-named in-snippet. Cheapest, most
   causally supported change. Cost: more input tokens on ~2-6 alerts/day — trivial.
2. **Rolling multi-day window** — group today's alerts against the last 5-10 trading days'
   qualifying alerts (today's must anchor; propose only cohorts containing ≥1 same-day name).
   Evidence: §2/§4 — the WULF→CLSK→HUT/IREN accretion (corr +0.47..+0.87) was structurally
   invisible same-day; also converts the 9 lone-alert drops into groupable runs.
3. **Active-cohort context** — pass current live-theme names + active Lane-2 narratives into the
   call so a lone/paired alert can be proposed as a JOINER (FCEL 06-24 and DOCN 07-07 both fit
   then-active themes). Complements #2; the anti-circularity wall (#322: judge_inferred excluded)
   must carry over unchanged.
4. **Prompt: add a demand-side instruction** ("consider whether names share a customer/demand cycle
   — e.g. data-center capex — even when the filings describe different products"). Deprioritized vs
   1-2 per §5; do NOT merely soften "truly"/empty-list — no evidence that buys recall, and it risks
   the precision that is currently 2/2.
5. **Input integrity upstream** (separate ticket, not Lane-2): ~6% ticker misidentification in
   catalyst discovery (KC/SG/HQ class) poisons every downstream consumer, not just Lane-2.

**Guard:** any recall-loosening change must replay against the forward-era alert stream and hold
precision (the `evaluate_narrative_themes` harness + backfill segregation already support this).

## 7. Sample-size honesty

13 judgeable grouped days is thin for a rate estimate; 3-of-13 vs a true 10% miss rate is not
separable at this N (needs ~40-50 grouped days ≈ 4-5 more months at current base rates). What the
N=13 DOES establish beyond rate arithmetic: every observed miss has the same mechanism, that
mechanism is causally traceable to the input (§3) and window (§4), and one miss (CLSK) is
system-terminal — no other lane ever caught it. The proposals stand on the mechanism evidence, not
on the rate.

---
*Method: prod read-only (`mi_audit_log`, `mi_ep_alerts`, `mi_themes`, `mi_theme_candidates_shadow`,
`mi_daily_closes`); production filter replicated exactly (ep≥50, catalyst-or-claude_analysis,
DISTINCT ON ticker, source='live'); correlations SPY-adjusted, null from 1,509 same-window
cross-cohort pairs. Code: `theme_engine.py::discover_narrative_themes` (L387-479),
`db.py::get_today_ep_alerts`, `ep_detector.py::_pick_catalyst_text` (#360). Analysis scripts in
session scratchpad (not committed).*
