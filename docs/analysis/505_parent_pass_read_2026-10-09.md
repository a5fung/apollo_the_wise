# #505 (nightly theme parent pass) — the 10-09 read

**Answer:** the queue cannot drain as the blocker is worded, and the pass links almost nothing because it is asking about the wrong pairs, not because the model misses containment. The catch-all half of the blocker is already met by design.

## Method and population

Read-only, $0. Five SELECT pulls on 2026-10-09 (market open, light queries), captured once under `scripts/probes/_505/pull_2026-10-09/`:

| Pull | Rows |
|---|---|
| `q1_audit.out` — every `theme_parent_pass_%` audit row, last 45 days | 64 (9 nightly heartbeats, 43 no-containment, 4 linked, 1 inverted, 6 error, 1 switch-on) |
| `q2_cooldowns.out` — all of `mi_theme_merge_cooldowns` | 426 (183 still live; 43 written by the parent pass, all live) |
| `q3_board.out` — the latest saved board, `mi_themes` 2026-10-08 | 136 rows: 122 not retired, of which 37 Fading |
| `q4_eco.out` — theme → ecosystem map | all rows |
| `q5_sect.out` — sectors, latest `mi_stock_scores` | top ~300 tickers |
| `q7_linkhist.out` — the 4 linked children, day by day | 23 rows |

The queue was reproduced offline by running the real pure function `theme_engine.propose_parent_candidates` (and `propose_merge_pairs` for the Arm-B exclusions) over the captured 10-08 board — `scripts/probes/_505/offline_queue_2026-10-09.py`, output `offline_queue_2026-10-09.txt`. Every verdict was parsed from the audit rows into `pull_2026-10-09/verdicts.tsv` (54 asks, 48 real verdicts on 47 distinct pairs).

Population surprise (n = 122 live themes): 37 of them (30%) are Fading, which the pass skips on both sides — a large slice of the board is out of scope every night.

## 1. Has the queue drained? No, and as worded it never will

- Runs on record: 9 nights (09-28 to 10-08), 6 asks each = 54; 09-29's 6 all failed (model refusal).
- Tonight's queue (one best candidate per childless theme): **42** themes — more than the 37 it started with on 09-26.
- But that is only the head of the queue. The selector walks each theme down its list of broader same-ecosystem themes one per night; each "no containment" answer cools that pair for 30 days and moves the theme to its next candidate. The full space of pairs not yet asked is **206** (one theme has 17 left) ≈ **35 nights at the cap of 6** (16 of the 206 wait on the merge pass, Arm B, which the parent pass never asks).
- It does not stop there: new themes keep arriving (the ~6 a day is a July figure, not re-measured here), and the first 30-day cooldowns expire **10-28**, after which those pairs are asked again. "No un-adjudicated pair" is structurally unreachable.

## 2. Why it links nothing

Verdicts on record (48 real, 47 distinct pairs):

| Verdict | Count | Shared ≥1 ticker | Shared 0 tickers |
|---|---|---|---|
| CHILD_OF (linked) | 4 | 4 | 0 |
| INVERTED | 1 | 1 | 0 |
| PEERS | 31 | 6 | 25 |
| UNRELATED | 12 | 3 | 9 |
| ERROR (09-29 refusals) | 6 | — | — |

- Pairs sharing a ticker: the model said containment on 5 of 14. Pairs sharing none: **0 of 34** — but every one of those 34 was a FALLBACK pick (the biggest same-ecosystem theme), so this measures how poor the fallback picks are, not how often ticker-disjoint pairs are containment; it is also the model's verdict, not an independent check.
- The 4 links (09-28: memory chips, liquid biopsy, identity security; 10-01: low-cost airlines) came on nights 1 and 4, before the ticker-sharing pairs ran out. Of the 4, **only liquid biopsy → genomics tools survives** on the 10-08 board (the memory-chip link carried over through a rename and that theme is now Fading); identity security and low-cost airlines retired 7 days after linking.
- Of the 206 pairs still to ask, **205 share no ticker and 147 share neither a ticker nor a name word**. With no signal, the selector's tie-break picks "the biggest theme in the same ecosystem", e.g. Class I Railroads → Crude Tanker Shipping, Building Products → Copper Mining, Insurance Brokerage → Fed-easing fintech.
- Reading the 43 no-containment reasons against names and members, the model is right on almost all: most pairs are same-level neighbours (two semiconductor baskets, two SaaS categories). Borderline, not plain misses: Cloud Contact Center (TWLO, RNG, FIVN, NICE) vs Customer Engagement/CX SaaS; Marketing & Digital Presence SaaS vs the same parent.
- One answer flipped: Genomics & DNA Sequencing → Life Science Tools was CHILD_OF in the 09-26 preview and PEERS live on 10-01. The prompt was reworded and the model moved to Sonnet 5.5 in between (06e3aa5d, 09-29), and the genomics basket's members changed; its reason (the basket mixes diagnostics and gene editing) is defensible.
- One real relationship the pass can never write: 09-28 said on-site power equipment sits **inside** "AI data-center power buildout" (INVERTED), but the pass only nests the theme with fewer members under the one with more, so the true parent (7 members) cannot parent the true child (11). Re-asked 10-07, it answered PEERS.
- Ecosystem mapping errors feed nonsense pairs: Electronics Manufacturing Services (BHE, PLXS, SANM, CLS) and IT Consulting (ACN, CTSH, EPAM) both sit in the **healthcare** ecosystem; Enterprise Unstructured Data Storage (DBX, BOX) in **industrials** paired with electric utilities; Alternative Asset Managers in **SaaS**. Three of the 12 UNRELATED answers are the model correctly rejecting these.

**Root cause:** candidate selection. Ticker overlap was deliberately made a priority signal, not a gate (theme_engine.py:356), so once the few overlapping pairs were spent, every ask is "is X inside the biggest neighbour Y?" with nothing pointing to containment. Secondary: wrong ecosystem assignments, and member count used as the measure of which theme is broader.

## 3. The 2 unassigned themes

- **For-Profit Postsecondary & Vocational Education** (Mainstream; CVSA, LOPE, LAUR, STRA, PRDO).
- **Global Agriculture Value Chain Recovery** (Fading; CNH, AGCO, DE).
- Both are mapped to the catch-all bucket, and `resolve_theme_parent` returns the catch-all as their parent — under the 07-27 ruling ("ecosystem is the default parent, even if it's the catch-all") that half of the blocker is **already met**. If the intent is "move them into a real ecosystem", that is a different ask: education has no bucket today; agriculture could go to industrials.

## 4. Smallest fix

- ⚠ **CORRECTED BY THE VERIFIER (same day):** the builder's first proposal — only ask a pair sharing ≥1 ticker or ≥2 name words — would refuse the very kind of pair that makes most real links: **7 of the 9 live parent links on the 10-08 board share no ticker with their parent** (Product Tanker, Customer Engagement/CX SaaS, Data Backup, Annuity-Focused Insurers, Semi Equipment Velocity Surge, Diabetes devices, Orthopedic devices), and 6 of 8 share one name word or none. It would also reverse the recorded design (theme_engine.py ~349-356: shared tickers set PRIORITY, never a filter, because real links are ticker-disjoint thesis relationships) without showing that reasoning was wrong. Withdrawn.
- **The root cause stands — the FALLBACK, not the filter:** with no signal, the selector asks the biggest theme in the same ecosystem (Class I Railroads → tanker shipping). **Rule change (his call):** pick the candidate parent by closeness of MEANING (name + description) instead of size, so the ask is a plausible containment pair; keep shared tickers as the first priority. Needs a design + an offline replay on the 9 live links (does the new pick find their real parent first?) before any switch.
- **Data fix (no rule change):** correct the ecosystem mapping of EMS, IT consulting, unstructured data storage and alternative asset managers.
- **Plan wording (his call):** the blocker's "no un-adjudicated pair" can never be met; restate it as "every signal-bearing pair has been asked".

## What this does not answer

- Whether tonight's real board matches the 10-08 snapshot: the replay uses yesterday's saved board and a narrower sector map (Arm-B exclusions can differ by a few pairs).
- Whether the PEERS/UNRELATED answers are right beyond the reading above — no paid re-ask was run.
- Whether a meaning-based pick finds the real parents: not built or replayed here. The 9 live links (7 ticker-disjoint) are the test set for it.
- Whether linking small themes is worth it at all, given 3 of 4 linked children retired within a week.
