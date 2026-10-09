# #693 — theme description validator: thinking ON vs thinking cut, replayed on Monday 10-05

**Recommendation (one line):** turn thinking back ON for the validator. With thinking on it removed 5 members instead of 26. All 5 were also removed in the live run. The thinking-cut setting did not repeat its own removals on a second pass. The extra cost is about 7 cents a night.

The operator's ruling of 10-05 ("go with rec") asked for this replay before deciding whether the validator keeps thinking. This page is that read. The decision is his.

## Method and population

- **Live night replayed:** Mon 2026-10-05, 17:02–17:09 ET. There were **151 validator calls** (`api_usage`, caller `theme_validation`), covering **911 member checks**. They removed **26 members**: 19 in the rescore pass, 4 after assignment, 1 when a member joined from another theme, and 2 at the birth of new themes (`ticker_revalidated_out` rows; there were 26 matching cooldown rows). This confirms the PLAN's 26. The "19" quoted earlier in the PLAN line counts the rescore pass only.
- **No 10-05 request was kept on disk.** `logs/llm_samples/` stores the last 3 requests per call site, and those are from 10-06, 10-07 and 10-08. So the 151 requests were **rebuilt** from what was saved:
  - the themes the run loaded (133, the same number the run logged);
  - the prune and exclusion lines in `logs/market-agent.log`;
  - the assignment, re-homing, join, birth and merge lines and audit rows;
  - company descriptions from `mi_ticker_overrides`.
- **How close the rebuild is (checked before spending anything):**
  - The prompt template rebuilds all 3 kept samples byte-for-byte.
  - Of the 133 rescore calls, 125 rebuilt token counts appear in the live set of token counts (a match on the whole set, not call by call). The other 8 differ by 3–18 tokens, mostly because a member's description was rewritten after 10-05.
  - The 18 later calls (re-homing, after-assignment, join, birth, merge) are rebuilt from logs. The 5 birth calls match exactly. The rest are within about 15 tokens; member order and some names are inferred.
  - 17 of the 151 calls contain a description that changed after 10-05. Each such member is flagged in the capture.
- **One paid run, two arms, same rebuilt inputs, interleaved in random order:**
  - **ON:** no `thinking` field. On claude-sonnet-5-5 that means adaptive thinking. `max_tokens` was 2024 (`thinking_headroom(1000)`), which is what the validator ran with 09-29 to 10-02.
  - **CUT (control):** `thinking: {"type": "between_tools"}` with `max_tokens` 1000. This is exactly what the live 10-05 run sent.
- The run used the production client factory (`make_async_anthropic`), with sample capture disabled. It wrote no spend-log rows, no audit rows and no theme changes. The code that applies removals was copied, never called: it covers the mass-eviction skip, the minimum-survivor guard and the two-member dissolve. None of these guards fired in either arm.
- **Checked afterwards that the run was read-only.** In the run window (13:45–14:10 ET on 10-09) there were 0 `api_usage` rows for claude-sonnet-5-5, 0 validation, rewrite or cooldown audit rows, and 0 cooldown rows on 10-09. The validator's sample file still carries its 10-08 21:03 UTC timestamp. A run that wrote anything would have left rows in each of these places (`readonly_check.out`).
- **Price:** the estimate was $0.28–0.31 for ON, using the validator's own thinking-on nights (60–78 output tokens per call). The pessimistic bound was $1.64 at 957 tokens per call. The CUT arm was estimated at about $0.21. That puts the total at about $0.50, or $1.85 in the worst case, under the $2 stop. **Actual spend was $0.282 for ON and $0.209 for CUT, $0.49 in total.** Every call ended normally (`end_turn`), with 0 errors and 0 unreadable answers.

## Results

Each removal below is counted once per theme and member (828 distinct pairs), across all six kinds of validator call.

| | Live 10-05 (thinking cut) | Replay ON | Replay CUT (control) |
|---|---|---|---|
| Members removed | 26 | **5** | 32 |
| Of those, also removed live | — | **5 of 5** | 16 of 32 |
| Output tokens per call (average) | 14 | 59 (max 455) | 11 |
| Calls where the model actually thought | — | 32 of 151 | 0 |
| Cost of the 151 calls | $0.214 | $0.282 | $0.209 |

| Live (thinking cut) vs replay ON | n |
|---|---|
| Removed by both | 5 (ZD, VPG, DOX, ITUB, MHK) |
| Removed only live | 21 |
| Removed only with thinking ON | 0 |
| Kept by both | 802 (of 828 distinct theme–member pairs) |

MHK and ITUB count as removed by both, but the ON arm removed each of them in a different call from the one where the live run removed it.

| Live vs replay CUT (same setting, run again) | n |
|---|---|
| Removed by both | 16 |
| Removed only live | 10 |
| Removed only in the control run | 16 |

**What the control shows:** with thinking cut, two passes over (nearly) the same 151 requests agreed on only 16 removals and disagreed on 26. This is not caused by the rebuild. In the rescore pass, 20 of the 21 disagreements are on calls whose rebuild matches the live token count exactly and whose descriptions have not changed since. Among them, the control flagged 11 banks that the live run kept. The ON arm never removed anything the live run kept. Earlier live nights point the same way. The validator thought on 09-30 and 10-02 and removed 11 and 13 members those nights. With thinking cut it removed 26 on 10-05 and 19 on 10-07 (10-06 and 10-08 had only about 26 calls each, so they are not comparable).

### Disagreements: removed live, kept with thinking ON (21)

The validator returns no reasons. The live reason is always "the description does not match the theme". The model's thinking came back with no text, so the ON side has no reason either. "Control" says whether the CUT re-run removed the member again.

**In 5 cases the stored description names the theme's own business**, so the description does not support the removal:

| Ticker | Theme | Stored description | Control |
|---|---|---|---|
| P | Data Storage & Data Management Software/Hardware Leaders | Data storage, management software & hardware | kept |
| JAN | Skilled Nursing & Senior Housing Healthcare REITs | Senior housing real estate investment trust | removed |
| TDS | Legacy Telecom & Pay-TV/Broadcasting Distribution Rebound | Residential & commercial telecom services | removed |
| SEI | On-Site Power Generation & Distribution Equipment for Data Centers | Modular power generation, oilfield equipment | removed |
| EFOR | Defense Intelligence & Cybersecurity IT Contractors | IT services & solutions for government, commercial | removed |

**16 judgement calls for the operator.** In these the business is next to the theme's rather than plainly the same or plainly different:

| Ticker | Theme | Stored description | Control |
|---|---|---|---|
| SMTC | AI-Driven Memory & Storage Supply Shortage | IoT semiconductors, cloud connectivity | kept |
| TILE | Commercial, Office & Home Furniture | Modular carpet, commercial flooring | kept |
| CMBT | Crude & Product Tanker Shipping | Marine transportation, hydrogen infrastructure & vessels | removed |
| ICFI | Defense Intelligence & Cybersecurity IT Contractors | Management consulting, government & commercial services | removed |
| DEC | Energy Supply Disruption: Middle East Geopolitical Risk | Natural gas & oil production, Appalachia | kept |
| PS | Financial Data & Advisory/Capital Markets Platforms | Alternative asset management, hedge fund | removed |
| SSNC | Fintech & Digital Finance Re-rating | Financial & healthcare software & services | kept |
| MD | Hospital & Behavioral Health Facility Procedure Volume Recovery | Newborn, maternal-fetal, pediatric medical services | kept |
| RDVT | Identity & Access Management Security Software | Identity intelligence, analytics software | kept |
| ACA | Industrial Construction Execution & On-Site Supply Chain | Infrastructure products & engineered structures | kept |
| FTRE | Life Science Tools & Analytical Instruments | Contract research organization | removed |
| TTAN | Marketing & Customer Data SaaS Rotation | Field service management software | removed |
| STWD | Mortgage REITs (Agency & Residential MBS) | Commercial & residential mortgage lending (description changed since 10-05) | removed |
| SAIL | Network Security & Zero-Trust Edge | Identity & access management software, enterprise security | removed |
| IMO | Oil & Gas E&P Crude-Weighted Producers | Oil & gas exploration, production & refining, Canada | kept |
| SIG | Specialty Retail Short-Squeeze Momentum Basket | Diamond & jewelry retail (the theme's stored thesis describes "SIG" as a gold explorer, so the thesis itself is wrong) | removed |

### Removed only by the CUT control run (16; not live, not ON)

- **11 large or foreign banks** were flagged out of the 45-member "Bank Stocks: Rising-Rate NIM Expansion": JPM, C, WFC, MUFG, SMFG, MFG, SAN, BBVA, ING, DB and NWG. The theme's thesis is about *regional* banks, so this is a judgement call. It also shows how far one cut-thinking pass can swing.
- **The other 5:** AVPT, PH, RAL, FET and WKC.

## What this does not answer

- **One night, one run per arm.** Run-to-run variation was measured only for the CUT arm: a second pass moved 26 of 42 removals. Within this run, the 68 theme–member pairs that were judged in two calls were nearly stable in both arms. ON changed its verdict on 2 (MHK, ITUB) and CUT on 1 (ITUB). How much ON varies from one run to the next is still unmeasured. A random-failure difference needs several runs on several nights before it is settled ([[a-one-shot-pass-is-not-a-verify-for-random-failures]]).
- **Fewer removals is not automatically better.** Thinking ON may keep real mismatches. Several of the 16 judgement calls (for example SMTC, FTRE and TTAN) could be correct removals. This replay measures how much the two settings agree, not which one is right.
- **The inputs are rebuilt, not captured.** 8 rescore calls and most later calls differ from live by a few tokens. In 17 calls a description changed after 10-05.
- **Other changes on 10-05 are not separated out.** The control arm takes the rebuild out of the comparison, but nothing here re-examines the other changes that shipped the same night.

## Cost per night

- **Thinking ON:** about 59 output tokens per call, about $0.28 per Mon/Wed/Fri night (151 calls).
- **Thinking cut:** about 11–14 output tokens per call, about $0.21 per night.
- **Difference:** about $0.07 per night. On the two quiet weekday nights (about 26 calls) it is about a cent.

## Files

All in `scripts/probes/_693_replay/`:

- **Probes:** `pop.py` and `pop2.py` (population probes), `usage_rows.py` and `usage_1005.json` (live per-call tokens).
- **Rebuild:** `recon.py` (rebuild) and `count.py` (free token-count check); the output of both is `693_recon.json`.
- **The paid run:** `replay.py`, with every raw response and verdict in `693_replay.jsonl` and totals in `693_replay_totals.json`.
- **Comparison:** `compare.py`, with results in `compare_out.json` and `compare_sets.json`.
- **Live-night context:** `nightly_removals.out` and `log_1005_run.txt`.
- **Read-only proof:** `readonly_check.py` and `readonly_check.out`.
