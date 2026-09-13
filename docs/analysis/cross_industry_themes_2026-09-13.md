# Can a theme span more than one sector? — the verification he asked for (2026-09-13)

> Operator: *"I lean yes, but we should verify to make sure it doesn't produce garbage and have
> coherent themes"*

**Method**: three independent measurement angles — do the blocked names co-move with their themes ·
what would the board look like · his own four named concepts — each then adversarially verified by a
separate agent instructed to refute it. **3 of 3 survived.** 7 agents. Everything market-adjusted
(SPY subtracted) from `mi_daily_closes`, with matched random-name controls. $0.

**Denominators** — every percentage below resolves against these:

| population | n |
|---|---|
| live themes on the board 2026-09-11 | n = 127 (109 single-sector + 9 empty + 9 multi-sector) |
| accepted name↔theme pairs measured | n = 609 (389 with enough price history) |
| rejected name↔theme pairs measured | n = 109 (83 with enough price history) |
| proposed memberships, 2026-06-01 → 09-11 | n = 824, of which 167 rejected on sector (20%) |
| blocked names scored against a matched control | n = 91 |
| board members carrying a sector the engine can see | 663 of 679 (98%) |

⚠ **Reference scale for every correlation here**: theme members typically sit **0.5–0.8**; a random
board stock sits **≈0.05**. A number without that scale is meaningless.

## The answer

**Confirmed — allowing a theme to span more than one sector does not produce garbage.** On the live board of 2026-09-11, adding back every name the rule had blocked left theme tightness unchanged: 8 of 16 themes got tighter, 8 looser. Substituting a random stock **from a sector the theme already accepts** improved a theme only 2 times in 16 on average, and the best of 300 random draws reached 5. The blocked names behave like members; arbitrary names do not.

- The mechanism, said without any control: the names the gate **admits** move with their themes at 0.65, the names it **rejects** at 0.61 (389 of 609 accepted name-theme pairs, 83 of 109 rejected pairs; 0 = unrelated, 1 = lockstep, a random board stock ≈ 0.05). **The sector test is not separating good from bad.**
- Blocked names are slightly *weaker* than the members that stay (0.50 vs 0.60), but far above any matched random name (0.13) — real members, not star members.

Two framing corrections before you read on: the rule blocks a second **sector** (11 broad buckets), not a second industry — 65 of 127 themes already span two or more industries inside one sector, and the "118 of 127 one-industry" figure is really 109 single-sector themes plus 9 empty ones. And the rule is genuinely active, not idle: 663 of 679 board members (98%) carry a sector the engine can see.

## What the board would look like

Small and specific: **20 of 127 themes change, 26 names return, 18 of the 20 gain exactly one sector and none ends up with more than three.** About one name a day. The gate currently kills 167 of 824 proposed memberships (20%) over 2026-06-01 to 09-11.

*Board reconstruction, 60 trading days to 2026-09-11, market-adjusted. Theme tightness: members ≈ 0.5–0.8, random basket ≈ 0.05.*

| Theme | Name(s) the rule blocks | Members | Effect of adding it back |
|---|---|---|---|
| Emerging Bitcoin Miners Diversifying into AI/HPC Hosting | IREN | 3 → 4 | Your #491 concept, blocked from the theme named after it |
| Corporate Bitcoin Treasury Holding Companies | MSTR | **0** → 1 | Empty theme, refill blocked |
| Bitcoin Treasury & Crypto Proxy Equities | MSTR | 4 → 5 | MSTR ties to the group at 0.65 vs the members' own 0.61 |
| Metallurgical & Thermal Coal Mining Rebound | BTU, CNR | 3 → 5 | Tightness rises 0.52 → 0.59 |
| Global Steel & Metal Producers Recovery | CMC | 4 → 5 | Ties at 0.60 vs members' own 0.50 |
| B2B Payment Rails Modernization | GPN | 4 → 5 | Ties at 0.54 vs members' own 0.49; rejected 16 nights running |
| Skilled Nursing & Senior Housing REITs | PACS | 3 → 4 | The theme name is PACS's business |
| Oil & Product Tanker Shipping / Strait of Hormuz | ECO | 3 → 4 | A Hormuz theme with no tanker in it |
| Diversified Power Generation for AI Electricity Demand | AGX, BE | 4 → 6 | Tightness rises 0.13 → 0.16 (weak theme either way) |

In every one of these the data vendor simply files the same business under a different label — MSTR is "Technology" among "Financial Services" peers, CMC is "Industrials" among "Basic Materials" steel, PACS is "Healthcare" among "Real Estate" nursing REITs, converting miners are split across three different sector labels.

- The rule's real cost today is shrinkage, not coherence: **29 of 46 actual strip events left the theme with fewer than 3 members**, and about 5 theme-nights across 3 themes were cut to a single name, which the engine treats as dead.
- It emptied **zero** themes outright — the one case that looked like it was caused by the banned-ticker list, not this rule.

## Where it WOULD produce garbage

Roughly **1 readmitted name in 7 would be junk** — 13 of 91 blocked names move with their theme *worse* than a random stock from the sector the theme already accepts. **But the names the gate already lets through fail at the same rate (12%)**, so the sector test is not what is protecting the board from junk today. That is the case for replacing it rather than deleting it.

*Individual cases, ±10 sessions around the event, market-adjusted.*

| Name | Theme | Its tie | A random same-sector name |
|---|---|---|---|
| OTTR | Oilfield Services & Drilling Rigs | −0.14 | 0.52 |
| SEDG | Enterprise Server & AI Infra Hardware | 0.16 | 0.61 |
| ECO | Energy Supply Disruption: Hormuz | −0.11 | 0.45 |
| DCH | five unrelated themes in one week | −0.63 to −0.42 | themes ran +0.87 |

- **The honest failure cohort is AI power/grid** — AGX ties its power theme at 0.29 against 0.50 for a random utility, and FLNC is below its theme's members. Of your four named concepts, only the miners cohort has broad support (6 tickers); chip supply chain rests on AEIS alone and payments on GPN.
- **What replaces the proxy:** a direct co-movement test. It separates cleanly where sector does not — real members ≈ 0.6, junk ≈ 0.05 — and would catch OTTR, SEDG and DCH while admitting CIFR, MSTR, AEIS and IREN.

## Recommendation

**Replace the sector-identity test with a co-movement or industry-level test — do not simply delete it.** That is a detection-criteria change: **yours** under CHANGE_PROCESS, with a backtest and your sign-off. I have not changed anything.

| Gate | What it does | Binds? |
|---|---|---|
| **Assignment gate** | Rejects any name whose sector is not already in the theme | **Yes — this is the one to change.** It is why the board is single-sector |
| Birth strip | Drops a lone-sector name in a new ≥3-member theme | Secondary |
| Nightly carryforward strip | Re-applies the birth rule each night | Secondary |

- Relaxing only the strips leaves the assignment gate in place and nothing changes; a merge can still add a sector, so the sector set is not literally frozen forever.
- **Necessary but possibly not sufficient:** discovery batches are sorted by sector upstream, so a converting-miners cohort can straddle two batches and never reach any gate — your miners theme may still fail to *form*.

## Still unknown

- **The one measurement left:** a multi-week run with the rule relaxed, to see what accumulates. Everything above models one night of add-backs on today's board; the drift a rule-off regime produces over weeks is untested, and the assignment LLM has never been told cross-industry is permitted, so it may propose more.
- Birth-time drops leave no record at all, so every count here **understates** what the rule removes; and none of this touches trade returns — step 3 stays parked.

---

## Verified by hand afterwards — his own case, independently of the workflow

The single most load-bearing claim is that blocked names move with their themes about as well as
admitted ones. Checked directly on the theme named after his own #491 ruling:

**`Emerging Bitcoin Miners Diversifying into AI/HPC Hosting`** (2026-09-08) — members CIFR, CORZ,
BTDR. **IREN is not in it.**

| pair | market-adjusted correlation, 60 sessions |
|---|---|
| IREN ~ CORZ | **0.83** |
| IREN ~ CIFR | **0.75** |
| IREN ~ BTDR | **0.70** |
| CIFR ~ CORZ (a member pair) | 0.84 |
| CIFR ~ BTDR (a member pair) | 0.71 |
| CORZ ~ BTDR (a member pair) | 0.71 |

**IREN moves with this theme exactly as tightly as its members move with each other.** The sole
reason it is excluded: `mi_stock_scores.sector` files IREN as **Financial Services** while CIFR,
CORZ and BTDR are **Technology**. A data-vendor label, not a judgement about the group.

That is the whole finding in one case: the rule is testing the vendor's filing cabinet, not the tape.

## What this does NOT answer

- **What a rule-off regime accumulates over weeks.** Everything here models add-backs onto one
  night's board. The assignment LLM has never been told cross-sector is permitted and may propose
  more once it is.
- **Whether the miners theme would even FORM.** Discovery batches are sorted by sector upstream, so
  a converting-miners cohort can straddle two batches and never reach any gate. Relaxing the gate is
  necessary but possibly not sufficient.
- **How much the rule removes at BIRTH.** Birth-time drops write no record, so every count here
  understates the true cost.
- **Anything about trade returns.** Step 3 stays parked by his own sequencing (#655).
