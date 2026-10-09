# #505 (nightly theme parent pass) — closeness pick, offline replay 2026-10-09

**Answer:** the pre-set bar is **NOT MET** (new pick ranks the real parent first on 4 of 9 live links; today's pick also 4 of 9; the new pick is never worse). **Not built.** The 9-link test set cannot tell the two rules apart: 5 links are out of the pass's reach on this board whatever the ranking, and 3 of the 4 reachable ones have only one candidate.

## Method and population

- $0, no model calls, no DB writes. One read-only pull reused: `scripts/probes/_505_picker/q8_industry.out` — sector and industry from `mi_ticker_overrides` for all 694 member stocks on the 10-08 board (captured 10-09 by the earlier stopped attempt; SQL beside it).
- Board, ecosystems and cooldowns: the 10-08 snapshot in `scripts/probes/_505/pull_2026-10-09/` (same capture as the 10-09 read).
- Replay: `scripts/probes/_505_picker/replay.py`, output `replay_out.txt`; scorers in `scripts/probes/_505_picker/closeness.py` (rule fixed before any result was run).
- Test set: the 9 themes on the 10-08 board that carry a live parent link. For each, the child is treated as having no parent, its candidate parents are built with the same rules `propose_parent_candidates` applies (same ecosystem, strictly more members, both sides not Fading/Retired, pair not under a cooldown, no cycle), and the real parent's place in that list is read under each ranking.
- Members with no industry: 5 of 694 (AIG, KRP, MCY, TDC, WING — present in `mi_ticker_overrides` with sector and industry both empty); they are ignored in the industry score.

## The rule replayed (exact)

Rank key per candidate parent, lowest first: `(-shared member stocks, -industry overlap, -word similarity, -parent member count, parent name)`. Today's key: `(-shared member stocks, -shared name words, -parent member count, parent name)`.

- **Industry overlap** = of the child's members that have an industry, the share whose industry appears among the candidate parent's members' industries. 0 when no child member has an industry.
- **Word similarity** = Jaccard (shared ÷ combined) of two word sets, each built from the theme's name + description: lower-case; split on anything not a letter or digit; drop words under 3 letters, pure numbers, stop words and common theme words; then stem: `-ies` → `-y` (word > 4 letters), drop `-ing` (word > 5), drop a final `-s` unless `-ss` (word > 3); drop the stem too if it is a stop word or common theme word. 0 if either set is empty.
- Stop words: a an and are as at be been being but by can could did do does for from had has have he her his how i if in into is it its itself may might more most much no nor not of off on once only or other our out over own same she should so some such than that the their them then there these they this those through to too under until up very was we were what when where which while who whom why will with would you your also just about across after again against all any because before below between both down during each few further here many new one two three us via vs per amid around still yet ever even well.
- Common theme words (say nothing about subject; note that some appear in theme NAMES, e.g. driven, rotation, recovery, rebound): stock stocks company companies theme themes group groups sector sectors name names play plays basket baskets catalyst catalysts shared share driven drive driving rally rallies rallying move moves moving trade trading investor investors broad broader broadly market markets demand expectation expectations appear appears seem seems single clear common recent recently strong stronger higher rise rising gain gains boost boosted lift lifted renewed optimism headline headlines news report reports result results quarter quarterly outlook analyst analysts rating ratings target targets price prices tailwind momentum rotation rebound recovery upgrade upgrades sentiment continued continue spending fresh specific.

## Per-link result (the bar: the engine's own rules on the 10-08 board)

| Child | Real parent | Candidates | Today rank | New rank | Why out of reach |
|---|---|---|---|---|---|
| Liquid Biopsy & Molecular Cancer Diagnostics | Genomics & DNA Sequencing Tools | 2 | 1 | 1 | |
| Product Tanker Shipping | Crude & Product Tanker Shipping | 1 | 1 | 1 | |
| Customer Engagement & Marketing/CX SaaS | AI-Powered Enterprise Analytics & Workflow SaaS | 1 | 1 | 1 | |
| Data Backup & Cyber Resiliency Software | Network Security & Zero-Trust Edge | 1 | 1 | 1 | |
| Annuity-Focused Insurers | Life Insurance & Annuity Providers | — | — | — | parent Fading |
| HBM & AI-Driven Memory Chip Makers | AI-Driven Memory & Storage Supply Shortage | — | — | — | child Fading |
| Semi Equipment & Materials Velocity Surge | Semi Test, Yield & Assembly Supply Chain | — | — | — | parent not bigger (6 vs 6 members) |
| Diabetes Management Devices | Medical Device Mean-Reversion & Rotation Recovery | — | — | — | both Fading |
| Orthopedic Surgical Devices | Medical Device Mean-Reversion & Rotation Recovery | — | — | — | both Fading |

- Real parent first: **today 4 of 9, new 4 of 9**; links where the new pick ranks it lower than today: **0**.
- Bar (set before the run): first on at least 5 of 9 AND never lower than today → **NOT MET**. No ranking could reach 5: 5 links are excluded by stage or size, not by ranking.
- Only one link (Liquid Biopsy, 2 candidates) actually tested the ranking; both picks got it.

**Context, not the bar — stage ignored** (Fading treated as live, since these links were made when the themes were not Fading; every other rule kept): real parent first today 8 of 9, new 8 of 9, new never lower. The Semi Equipment link stays out (not bigger). Where it mattered (HBM: 9 candidates; Diabetes and Orthopedic: 4; Annuity: 2) the real parent already wins on today's signals — it shares member stocks with the child (HBM), shares a name word (Annuity), or is the biggest candidate (Diabetes, Orthopedic) — so today's pick finds it too.

**Recorded verdicts:** each of the 4 children the pass ever linked was asked only once (`verdicts.tsv`), all on pairs sharing member stocks — both picks put those first. No discriminating case there either.

## Supplementary — tonight's queue, first pick per childless theme (not the bar)

51 childless themes on the 10-08 board have at least one candidate (Arm B's first-refusal deferral not applied here). The new pick changes the first ask for **23**, keeps it for 28. Examples:

| Child | Today asks | New asks |
|---|---|---|
| Hospital & Behavioral Health Procedure Volume Recovery | IT Consulting & BPO Services | Post-Acute & Home-Based Healthcare Services |
| Fabless Semiconductor IP Licensing | Front-End Fabrication Equipment Makers | Analog, Mixed-Signal & Power Semi Cyclical Recovery |
| Branded Footwear & Hotel Turnaround | Defensive Consumer Rotation & Trade-Down | U.S. Apparel & Fashion Recovery |
| Class I Railroad Freight Carriers | Crude & Product Tanker Shipping | Product Tanker Shipping |
| Gold & Silver Miners Not Yet Classified | Copper Mining & Production | Building Products & Home Improvement Materials |

- Where the ecosystem holds a close theme, the new pick finds it; where it holds none (railroads, gold miners, small nuclear reactors), it still asks something unrelated — the rule has no minimum closeness, so it changes WHICH weak pair is asked, not WHETHER.

## What this does not answer

- Whether the closeness pick finds real parents better than the size pick: this test set cannot show it (5 of 9 out of reach, 3 of 4 with one candidate). A discriminating test needs children with several eligible candidates where the real parent is NOT the biggest — none exist among today's live links.
- Whether the 23 changed first asks would be answered "inside" more often — that is a model verdict (paid) or his judgement; not run.
- Whether the 10-08 snapshot matches tonight's board, and whether the probe's industry pull matches what the engine would read at run time (same table, same day).
- The word score's lists were fixed before the run and not tuned; a different list could change the 23.
