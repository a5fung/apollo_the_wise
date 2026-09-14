# Lane-2 narrative grouping — was "no shared story" correct? (review `lane2_narrative_grouping_quality`, #167, run 2026-09-14)

Read-only on prod, $0 (SQL over stored data + local Python; no LLM call of any kind). Nothing live
was changed. Evidence and a recommendation only — the leave / widen / retire ruling is the
operator's (grouping = detection = THE LINE).

Supersedes nothing by fiat: §7 positions this run against the two earlier reads
(`167_lane2_grouping_quality_2026-07-27.md`, `lane2_grouping_quality_2026-09-13.md`) and says
where and why the numbers differ.

---

## 0. Rules and bars — written BEFORE the first query, not moved afterwards

### 0.1 Population

- **Live run-days** = distinct dates with a `mi_audit_log` row `event_type='narrative_theme_discovery_ran'`
  created on/after **2026-06-07**. Captured: **70 rows on 64 distinct days** (2026-06-08 → 09-11).
  Re-runs on the same day (07-28 ×3, 08-04 ×3, 08-18 ×2, 08-19 ×2) — the **last** run is the
  decision of record, because `persist_narrative_theme_candidates` deletes and rewrites that
  day's `narrative_cogap` rows on every run (db.py `DELETE … WHERE run_date=$1 AND source=$2`).
- **Backfill NEVER pooled**: the **94** rows created before 06-07 (06-02 ×2, 06-03 ×1, **06-04 ×67**,
  06-05 ×1, **06-06 ×23**) are hindsight runs and are excluded from every count below. (The
  registry entry says 90; the extra 4 are dev runs on 06-02/03/05 — also excluded.)
- **Failed nights excluded from "declined"**: 08-06, 08-07, 08-11 (`narrative_theme_discovery_failed`,
  code bugs — `ThinkingBlock`, `'str' has no attribute 'get'`). No decision was made, so they are
  neither a decline nor a proposal. 08-10 had one failed invocation and one that succeeded (the
  success is the record).
- **Two eras, split by the `lane2_grouping_v2` flip (mi_safeguard_state `updated_at`
  2026-08-09 14:04 UTC)**:
  - **v1 = 06-08 → 08-05**: same-day alerts only, per-ticker text = `catalyst[:280]`, a `<2`
    qualifying-alert gate that skips the model call.
  - **v2 = 08-10 → 09-11**: per-ticker text = full `grounded_text` (≤10k chars) → `claude_analysis`
    → `catalyst`; a 10-trading-day roster memory (active narratives + one-name seeds); the model
    is called on **any** day with ≥1 qualifying alert (JOIN / NEW / SEED per name).
  - ⚠ So **two of the three "widen" arms the review names (input richness, the <2 gate) already
    shipped on 08-09.** The era split is the natural experiment on them — with the caveat that v2
    changed three things at once (input, memory window, prompt structure), so a v2 improvement
    cannot be attributed to input alone. §0.5 names the within-v1 test that can.

### 0.2 Unit of analysis and "caught"

- **Qualifying alert on day D** replicates prod exactly (`db.get_today_ep_alerts` +
  `theme_engine._lane2_qualifies`): `mi_ep_alerts` with `alert_date = D`, `source='live'`,
  one row per ticker (highest `ep_score`), `ep_score ≥ 50`, and non-empty `catalyst` OR
  `claude_analysis`.
  **Stop condition**: my per-day qualifying count must equal the run-log's own count on every
  evaluated day. Any mismatch = the replication is wrong and nothing below is reported.
- **Unit = same-day unordered pair** (a, b) of qualifying alerts on a run-day with ≥2 qualifying
  alerts. This is the review's own framing ("2+ EPs").
- **CAUGHT**: a `mi_theme_candidates_shadow` row with `source='narrative_cogap'` and `run_date = D`
  contains both a and b (a v2 JOIN row counts — it lists today's name with the prior members).
  **UNCAUGHT** otherwise.
- **No-story day** = evaluated day (≥2 qualifying) with **zero** `narrative_cogap` rows on D.
  (v2 seeds are one-name watch rows, not a story; a seed-only day is a no-story day.)
- **Lone-alert day (v2 only)** = exactly 1 qualifying alert; it was evaluated against the roster.
  Reported separately as the measured yield of the "<2 gate" arm: how many produced a cross-day
  JOIN.

### 0.3 Ground truth A — a later shared theme (PRIMARY)

- Pair (a, b) **later shared a theme** if any `mi_themes` row (either `source`, any stage) with
  `theme_date` in **(D, min(D+60, 2026-09-11)]** contains both.
- **Already on the board** if any `mi_themes` row with `theme_date` in **[D−7, D]** contains both
  (7 days = the board's own staleness window). Split: **PRIOR** (theme_date ≤ D−1 — the board
  had it before Lane 2 ran) vs **SAME-NIGHT** (theme_date = D only — Lane 1 grouped them in the
  same nightly run; zero days lost).
- Classification of an UNCAUGHT pair:
  - **MISS** — later shared a theme AND not already on the board. `lag` = first co-appearance
    theme_date − D (calendar days). **Sub-bucket by who caught it later**: (i) **Lane 2 itself**
    — a `narrative_cogap` row containing both exists on/before the first theme co-appearance
    (a seed→conversion or a JOIN: the registry's own cross-day arm doing its job, a 1-day lag by
    design, NOT a detection failure); (ii) **another lane** — first co-appearance is a
    `source='live'` theme row, or a `shadow_promoted` row with no Lane-2 row behind it.
  - **REDUNDANT** — already on the board (PRIOR or SAME-NIGHT). A story existed and Lane 2 did
    not see it independently (in v2 the prompt carries only Lane 2's own roster, never the live
    board), but no earliness was lost.
  - **CORRECT** — never co-members through the horizon.
- **Two rates, both reported, both denominators stated**:
  - *"Was there a story?"* = (MISS + REDUNDANT) / uncaught pairs — answers the review's literal
    question.
  - *"Earliness lost"* = MISS / uncaught pairs, and MISS-days / no-story days — drives the ruling.
- **Horizon honesty**: the era-agnostic miss list uses the long horizon above. The **era
  comparison (§0.5) uses ONE fixed 20-calendar-day horizon for both eras**, because v1 days have
  up to 60+ days of look-ahead and v2 days at most 32 — otherwise "v2 has fewer misses" could
  just mean "v2 has not had time". Days with <20 days of horizon (D > 2026-08-22) are excluded
  from the fixed-horizon rates and listed as *not yet judgeable*.

### 0.4 Ground truth B — market-adjusted co-movement (SECONDARY)

- Residual daily return r_t = ln(P_t/P_{t−1}) − ln(SPY_t/SPY_{t−1}) from `mi_daily_closes`;
  Pearson correlation over the **15 trading days after D** (D+1…D+15; ≥10 valid observations
  required, else *unjudgeable*).
- **Null** = cross-day pairs: each tested ticker a (on D) paired with every qualifying alert c
  from a **different** run-day within ±20 trading days, correlation computed over the **same**
  D+1…D+15 window. **Bar = null p95.** A pair "co-moved" if corr ≥ p95. Expected false positives
  under the null = 5% × pairs tested — stated next to every count.
- **Power check first**: the same-day base rate (all same-day pairs above p95) is measured before
  the check is used. If it is ≈5%, same-day EP pairs do not co-move more than random pairs and
  the check has no power to separate a working from a useless Lane 2 — it is then reported as
  such and not used for the ruling.
- **Structural bias, stated up front**: Lane 2 exists for stories that bind NON-co-moving names.
  Co-movement therefore under-detects Lane-2-type misses. It is corroboration, never the sole
  ground for a miss.

### 0.5 The input-richness hypothesis — two tests, declared

1. **Era comparison** (fixed 20-day horizon, MISS pairs / uncaught pairs): **CONFIRMED** if the
   v2 rate is < ½ the v1 rate with both denominators ≥ 10 pairs; **REFUTED** if v2 ≥ v1;
   **INDETERMINATE** otherwise or if a denominator is < 10 — a legal outcome; v2 has only
   **5 no-story days** (08-10, 08-13, 08-17, 08-20, 08-27) and I will not force a verdict on
   five days.
2. **Within-v1 keyword test** (isolates input from the other two v2 changes): for every v1 MISS
   pair, was the later theme's driver **named inside both `catalyst[:280]` snippets**? Mechanical
   keyword presence (the theme name's content words plus obvious synonyms listed per pair in the
   table), no judgement call. If the driver was visible in both snippets on most v1 misses, richer
   input cannot be the binding constraint, whatever v2 shows.

### 0.6 Precision (needed only for the RETIRE option)

- For every live-era `narrative_cogap` proposal pair: later co-members in a **`source='live'`**
  `mi_themes` row (Lane 1 independently agreed), or already on the board at proposal time.
  **`shadow_promoted` co-membership is reported separately and labelled "Lane 2's own promoted
  row"** — `narrative_cogap` is on the auto-promote allowlist, so counting it would be Lane 2
  grading itself.
- Also: proposals that preceded the board (first live co-appearance > proposal date) and by how
  many days.

### 0.7 What a WORKING and a USELESS Lane 2 would each produce on every check

| check | working Lane 2 | useless Lane 2 (declines everything) | discriminates? |
|---|---|---|---|
| A. uncaught pairs that later share a NEW theme | ≈0 (every real group was named on the day) | every later-grouped pair — the base rate at which same-day alert pairs later share a theme | **yes**, but its floor is the rest of the engine's recall: a story no lane ever finds reads as CORRECT under both — stated as a limitation, not hidden |
| A′. REDUNDANT pairs | can be >0 (the board already had it; the birth gate would dedup the proposal anyway) | same | **no** — reported for the literal question only, never for the ruling |
| B. co-movement of uncaught pairs vs null | ≈5% above p95 (chance) | the same-day base rate | only if the base rate is materially above 5% — measured first |
| C. precision of proposals vs `live` themes | high | n/a (no proposals) — a useless-but-proposing Lane 2 reads ≈ the base rate | **yes** |
| D. lone-alert-day JOIN yield (v2) | >0 | 0 | yes, small n |

### 0.8 Bars for the ruling — declared

- **"No shared story" was CORRECT as a rule** if MISS-days ≤ 15% of judgeable no-story days
  (≤ about 1 in 7); **WRONG as a rule** if > 30%; in between = mixed, decided on earliness.
- **Earliness prize** = MISS pairs caught by another lane with lag ≥ 5 days. ≥ 2 such misses in
  an era = widening has a concrete, named prize; < 2 = the misses cost a day, not a theme.
- **RETIRE is defensible only if** precision vs `live` themes < 25% AND Lane 2 never preceded
  the board. Otherwise retire is off the table whatever the miss rate says.
- **WIDEN (a specific arm)** only if the misses concentrate on one mechanism the arm targets
  (input / window / gate) — a miss the arm would not have prevented is not evidence for it.

---

## 1. Replication check — the stop condition passed

| check | result |
|---|---|
| my per-day qualifying count vs the run log's own count | **64 of 64 days match** (incl. 06-15 = 6, 08-04 = 11, 08-12 = 10) |
| my per-day qualifying set vs the v2 `lane2_decision_record` `offered` list | **14 of 14 records match** |

So the **input** Lane 2 saw each day is fully reconstructible from `mi_ep_alerts` — for **every** live day,
both eras. (The 09-13 read said *"what Lane-2 considered each day is unrecorded"*: the run row's `detail`
column is indeed empty on all 70 rows and the model's per-candidate reasoning is not stored anywhere —
but the review's objective method does not need it. The summary line carries the count, the decision
records carry per-ticker outcomes from 08-10, and the qualifying set replicates exactly; §7.)

## 2. Population, by era

| era | run-days | model not called | evaluated, ≥2 alerts | of which **no-story** | of which proposed | lone-alert days evaluated |
|---|---|---|---|---|---|---|
| v1 (06-08 → 08-05) | 41 | 16 (the `<2` gate: 10 days with 1 alert, 6 with 0) | 25 | **20** | 5 | — (gated) |
| v2 (08-10 → 09-11) | 23 | 9 (0 qualifying alerts) | 10 | **5** | 5 | 4 |
| **total** | **64** | 25 | 35 | **25** | 10 | 4 |

Plus 3 failed nights (08-06, 08-07, 08-11) — no decision, excluded. Backfill: 94 rows, excluded.
Same-day pairs across the 35 evaluated days: **313** (v1 184, v2 129); Lane 2 CAUGHT 34, leaving
**279 uncaught** pairs to judge.

Every v2 evaluated day ran with `grounded=N analysis=0 catalyst=0` — the input-richness arm is 100 %
deployed in v2; every name the model saw came with its full SEC-grounded body.

## 3. Ground truth A — did the declined pairs later share a theme?

### 3.1 Pair level (long horizon, ≤60 days, data to 09-11)

| era | uncaught pairs | MISS (later shared a NEW theme) | of which caught next day by **Lane 2 itself** (seed→conversion) | of which caught by **another lane** | REDUNDANT (board already had it) | CORRECT (never) |
|---|---|---|---|---|---|---|
| v1 | 164 | 1 | 0 | 1 | 0 | 163 |
| v2 | 115 | 6 | 3 | 3 | 1 | 108 |
| **all** | **279** | **7 (3 %)** | 3 | **4 (1.4 %)** | 1 | **271 (97 %)** |

- *"Was there a story?"* — (MISS + REDUNDANT) / uncaught = **8 of 279 = 3 %**.
- *"Earliness lost to another lane"* — **4 of 279 = 1.4 %**.

**Every MISS pair, with what caught it:**

| day | era | day type | pair | lag | caught later by | the theme | that theme's size / nature |
|---|---|---|---|---|---|---|---|
| 06-15 | v1 | no-story | AUGO–HYMC | **51 d** | live lane | Precious Metals Miners Rotation | 19 members, RS rotation, **lived 2 days** (08-05/06) |
| 08-12 | v2 | proposal day | BRUN–CRWV | 6 d | live lane | Emerging Cloud GPU Rental & AI Infra Hardware | 5 members, sector ("what the company is") |
| 08-12 | v2 | proposal day | BRUN–EROC | 8 d | live lane | same | same |
| 08-13 | v2 | no-story | CGEM–KURA | **27 d** | live lane | Oncology Therapeutics RS Turnaround | 15 members, RS turnaround; CGEM added on day 6 of the theme |
| 08-13 | v2 | no-story | CRMD–KURA | 1 d | **Lane 2 itself** | Rare disease/specialty pharma earnings beats | seeded 08-13, converted 08-14 — the registry's cross-day arm by design |
| 08-13 | v2 | no-story | CRMD–OMER | 1 d | Lane 2 itself | same | same |
| 08-13 | v2 | no-story | KURA–OMER | 1 d | Lane 2 itself | same (an independent live theme, *Clinical-Stage Oncology & Hematology Biotech Breakout*, also held the pair 7 d later) | same |

REDUNDANT: 08-27 CRWD–OKTA — both already sat in *Network Security & Zero-Trust Edge* (a live theme since
03-20). Lane 2 declined; the board had it; zero days lost.

Handoff, not analysed here: 08-13 (three rare-disease names seeded, birthed as one narrative the next
day) is exactly the seed-vs-birth signal the `lane2_seed_birth_calibration` review exists to tune on.

### 3.2 Day level — the review's literal question

| | no-story days | judgeable (≥20 d horizon) | days where a story existed by ANY reading | **days where earliness was lost** (MISS, any lane) | … excluding Lane 2's own next-day conversion |
|---|---|---|---|---|---|
| v1 | 20 | 20 | 1 (06-15) | **1 of 20 = 5 %** | 1 |
| v2 | 5 | 4 (08-27 too recent for the 20-d test, but its pair was already on the board) | 2 (08-13, 08-27) | **1 of 4 = 25 %** (08-13) | 1 |
| **all** | **25** | **24** | **3 of 25 = 12 %** | **2 of 24 = 8 %** | 2 |

Against the declared bar (§0.8: ≤15 % = correct as a rule): **8 % — "no shared story" was CORRECT as a
rule.** v2 alone reads 25 % on four days — declared INDETERMINATE territory, and it is one day (08-13).

### 3.3 Recall against what the engine found on its own (the check's floor, made explicit)

Ground truth A can only see stories some lane eventually found. Restricting to themes the engine named
**independently** (a `live` row whose name is not one of Lane 2's own — a promoted Lane-2 row is carried
forward as `live` the next day, so name-matching is the only clean independence test). ⚠ This
name-based independence rule was **refined after §0.6 was declared**, once the first pass showed
`source='live'` alone let Lane 2's own promoted rows count as confirmation; it only **tightens** the
test (fewer confirmations, fewer engine-found pairs), never loosens it:

| horizon | same-day pairs an independent live theme held afterwards (not before) | Lane 2 caught on the day | recall |
|---|---|---|---|
| 20 d | 7 | 4 | 4 of 7 (v1 2 of 2 · v2 2 of 5) |
| 60 d | 11 | 6 | **6 of 11** (v1 3 of 4 · v2 3 of 7) |

Only **11 of 285** same-day pairs (4 %) were ever grouped by the engine on its own within 60 days — that is
the floor. The 5 Lane 2 did not catch are the four other-lane rows in §3.1 plus KURA–OMER; **all five are
sector / RS groupings** (19-member miners rotation, 15-member oncology RS turnaround, 5-member GPU-cloud
sector, 8-member oncology biotech), not a shared catalyst narrative.

## 4. Ground truth B — market-adjusted co-movement

- Null: **10,691** cross-day pairs on identical windows; mean +0.08, p90 +0.51, **p95 +0.62**.
- **Power check (declared first): all 295 same-day pairs with price data → 16 above p95 = 5.4 %, vs 5 %
  by chance.** Same-day EP pairs do not co-move more than random pairs; **the check cannot separate a
  working Lane 2 from a useless one at the pair level and is not used for the ruling.**
- What it does say, at the population level:

| bucket | pairs with 15-d data | above p95 | rate | expected by chance |
|---|---|---|---|---|
| CAUGHT by Lane 2 | 32 | 5 | 16 % | 1.6 |
| MISS | 7 | 2 | — | 0.4 |
| CORRECT (declined, never a theme) | **255** | **8** | **3.1 %** | **12.8** |

The declined pool holds **fewer** co-moving pairs than chance would put there (8 vs ~13). A useless Lane 2
would leave every co-mover in that pool. The 8: HYMC–IDR, AEHR–JBL, CLSK–TSEM, NNE–QBTS, AEIS–CAT,
ECG–KMT, PRGO–ROCK, ATRO–EROC — **none shared any theme within 60 days.** The 07-27 audit's AEHR–JBL and
CLSK–TSEM "misses" rest on this co-movement alone.
- `mi_correlation_clusters` was not used: it stores uncovered clusters only (dedup'd against live themes
  before the write), so absence from it says nothing, and presence duplicates ground truth A.

## 5. Input richness — REFUTED as the binding constraint

**Test 1, era comparison, fixed 20-day horizon (§0.5 rule):**

| era | judgeable uncaught pairs | MISS ≤ 20 d | … excluding Lane 2's own next-day conversion |
|---|---|---|---|
| v1 (`catalyst[:280]`) | 164 over 24 days | **0 (0 %)** | 0 |
| v2 (full grounded text) | 89 over 7 days | 5 (6 %) | **2 (2 %)** |

v2 ≥ v1 → **REFUTED** by the declared rule. The v1 declines, made on one truncated line each, almost never
turned out to hide a story (0 of 164 within 20 days; 1 of 164 within 60). There was nothing for richer
input to recover. Caveat as declared: v2 is 7 days / 5 no-story days; but the direction is not close.

**Test 2, within v1 — was the driver visible in the 280 chars?** Only one v1 miss exists (AUGO–HYMC,
06-15). Mechanical keyword hits for *Precious Metals Miners Rotation* {gold, silver, metal, miner,
mining, precious}: **HYMC yes** ("silver/mining sympathy … bullish silver thesis"), **AUGO no** ("no
clearly identifiable … catalyst … technical/flow-driven … or sympathy"). So on this one pair the
truncated line hid the driver on one side. The fuller text Lane 2 would see today: AUGO's
`claude_analysis` says *"sympathy buying in the gold/copper sector"*, HYMC's says *"broad
silver/precious-metals sector momentum"* — the sector was nameable from the richer text. **But the v2
era shows what Lane 2 does with full text on exactly this shape**: CGEM–KURA (two oncology names,
different drugs, full 8-K bodies) and BRUN–CRWV/EROC (a GPU-cloud name whose day's filing was an
earnings-call date) were both declined — because the prompt asks for a **shared catalyst narrative** and
bans sector/category groupings. A silver-sympathy day with no company catalyst on either side is that
same shape. Richer input makes the sector visible; the spec still (correctly, by its own rules)
declines it.

**Conclusion:** the binding constraint on the ≥5-day misses is the lane's **definition** (catalyst story,
not sector membership), not the input. Every ≥5-day miss is a sector/RS grouping — the thing Lane 1 is
built for and did in fact do.

## 6. Precision, and the two "widen" arms that already shipped

### 6.1 Precision of the 16 live-era proposals (independence = a live theme the engine named itself)

| verdict | proposals | which |
|---|---|---|
| **independently confirmed, Lane 2 FIRST** | **5** | EME–PWR 07-30 (→ *Electrical Grid & Power Infrastructure Construction*, +29 d) · COHU–MPWR 07-31 (→ *AI Chip & Interconnect Supply Chain Enablement*, **+14 d**) · AI-DC buildout 08-12 (→ *Power Generation Buildout for AI DC Electricity*, +27 d) · Power & Grid 08-12 (same, +27 d) · AGX–ALAB–SNOW 09-04 (→ *Cloud Data Storage & Analytics Infra*, +4 d) |
| independently confirmed, same night | 1 | AMRC–BLZE–BTDR 08-04 |
| independently confirmed, board already had it | 1 | Rare disease 08-14 (*Specialty Pharmaceutical Commercialization & Rare Disease Drugs*, 3 d earlier) |
| already on the board via another shadow lane | 1 | HUT–IREN 07-20 (*Bitcoin & Crypto Mining Infrastructure*) — a thesis re-name, not a new group |
| own auto-promotion only, no independent agreement | 4 | ARM–LRCX–SIMO 07-30 · BLZE–FLNC–MPWR 07-31 · Defense 08-04 · AGX–SNOW 09-03 |
| never (any lane, 60 d) | 4 | MU–SNX 06-25 · AEIS–ZBRA 08-04 · TEM–TWST 08-19 (23 d old) · PHVS–ROIV 09-08 (3 d old, unjudgeable) |

**7 of 16 (44 %) independently confirmed; 5 of 16 were early, by 4–29 days.** Against the RETIRE bar
(§0.8: <25 % AND never ahead of the board): **retire is not defensible.**

### 6.2 The `<2` gate arm — measured, not argued

v2 removed the gate. **4 lone-alert days ran: 1 produced a cross-day JOIN** (09-04 ALAB → *AI data-center
power buildout* with AGX/SNOW; an independent live theme held the trio 4 days later), 3 were seeded
(AMLX, UUUU, SOLS) and never converted. Yield **1 of 4**.

### 6.3 The window / memory arm — the strongest single result here

Cross-day pairs (today's alert × a qualifying alert in the prior 10 trading days) that an engine theme later
held within 20 days:

| era | real cross-day pairs | Lane 2 caught (JOIN / conversion) | at story level |
|---|---|---|---|
| v1 (no memory) | 8 | **0** | 0 of 3 stories (semis test TER→LRCX→COHU/MPWR · INSP–NVCR · KTOS–VOYG) |
| v2 (10-day roster) | 37 | **30** | **3 of 7** stories caught (08-12 Power & Grid +EROC/BE · 08-12 AI-DC +5 names · 08-14 rare-disease conversion); missed LPTH×defense 08-14, CBRS×GPU-cloud 08-17, TEM×HTFL 08-19, BULL×BLSH 08-20 |

The WULF→CLSK→HUT/IREN accretion the 07-27 audit could only watch through a same-day pinhole is now the
lane's normal mode.

## 7. Position against the 07-27 and 09-13 reads

**07-27** (13 judgeable v1 days; "3 misses + 1 borderline", ground truth = co-movement). This run finds
**1** of its 3 misses on the theme test (06-15 precious metals, 51 d); AEHR–JBL and CLSK–TSEM never shared
a theme in 60 days and rest on a co-movement bar that §4 shows has no power here. Its leading hypothesis
(input richness) is refuted in §5 — including on its own 06-15 case, where the richer text names the
sector for both names but the lane's spec would still decline a no-catalyst sympathy pair. Its window
proposal is vindicated (§6.3).

**09-13** (64 days; "8 genuine misses, 81 days of earliness available"). Method difference: its miss rule
was *"≥2 of that day's EP alerts later landed in the same theme"* and **never checked whether Lane 2 had
proposed that very group on that day.** Re-reading its table against `mi_theme_candidates_shadow`:

| 09-13 "miss" | what actually happened |
|---|---|
| 07-30 EME/PWR 13 d · 07-31 BLZE/FLNC/MPWR 12 d · 08-04 BTDR/AMRC/BLZE 1 d · 08-12 CRWV/WYFI/BE/EROC 1 d · 09-03 AGX/SNOW 1 d | **Lane 2's own proposals, that day, those exact members** (rows 187, 191, 230, 298, 574). The "lag" is Lane 2's LEAD over the board — 5 wins scored as misses. |
| 08-27 OKTA/CRWD 1 d | already on the board 5 months (§3.1) — redundant, not a miss |
| 06-15 HYMC/AUGO 51 d · 08-13 CRMD/KURA/OMER 1 d | **stand** — the two real ones; 08-13 was Lane 2's own next-day conversion |

So of the "81 days of earliness available": **29 were Lane 2's own lead time (13+12+1+1+1) plus a
board dedup (1)**; the 52 that stand are 51 days on a 19-member precious-metals RS rotation that lived
two days on the board, and 1 day on Lane 2's own next-day conversion. Its
**final** verdict (LEAVE; the 3-member promote floor is the downstream defect) is **agreed** — with the
evidence under it corrected, and its "instrument then decide" detour shown unnecessary (§1: the inputs
were always reconstructible).

## 8. Answer, options, recommendation

**Answer: yes — on 22 of the 25 no-story days no story existed by any lane's later reading **to date**
(the v2 days have at most 32 days of look-ahead), and on 2 of the 24 judgeable days (8 %) the decline
cost earliness; both of those were sector/RS groupings (a 19-member
precious-metals rotation, a 15-member oncology RS turnaround) that Lane 1 exists to make and did make.
The one cross-day story in the declined set (rare-disease pharma, 08-13) Lane 2 converted itself the next
day. At pair level: 279 declined pairs, 4 (1.4 %) later grouped by another lane, 271 (97 %) never.**

| option | verdict | why (one line) |
|---|---|---|
| **Leave as-is** | **RECOMMENDED** | miss rate 8 % of days / 1.4 % of pairs, under the 15 % bar; precision 7 of 16 with 5 early by 4–29 d; both arms the review names already shipped and measured (input: no effect on misses; window: 0→30 cross-day catches) |
| Widen — input richness | done (08-09), **no further arm** | v2 runs on full grounded text every day; misses did not fall (§5) — there was nothing to recover |
| Widen — the `<2` gate | done (08-09) | yield 1 JOIN in 4 lone-alert days; keep, nothing more to widen |
| Widen — prompt breadth (allow sector / "what the company is" groupings) | **not supported** | it targets exactly the 4 other-lane misses, all sector groupings Lane 1 already makes; it would spend the precision (7 of 16 independent, 4 never) that keeps the auto-promote allowlist honest, and re-create Lane 1 inside Lane 2 |
| Retire | **off the table** | fails both retire conditions: precision 44 % vs the <25 % bar, and 5 proposals beat the board by 4–29 days |

**⚠ My own §0.8 earliness bar FIRED for v2, and the recommendation is LEAVE anyway — said plainly so it
does not read as a bar moved after the data.** The bar: ≥2 other-lane misses with lag ≥5 days in an era
= widening has a concrete, named prize. v2 has three such pairs across two stories (CGEM–KURA 27 d;
BRUN–CRWV 6 d, BRUN–EROC 8 d); v1 has one (AUGO–HYMC 51 d). **The only arm that captures that prize is
grouping on sector membership without a shared catalyst** — that is a change to the lane's definition
(§5), not a knob, and it is the operator's fork, not mine. Recommendation stays **leave** because: the
prize is 51 days on a 19-member rotation theme that lived two days, 27 days on a 15-member RS-turnaround
theme, and 6–8 days on a 5-member sector theme — all of which Lane 1 made on its own — and taking it
means Lane 2 doing Lane 1's job at the cost of the precision that keeps its auto-promote seat honest.

## What this does not answer

For the record — (a) the engine's own recall is the floor of ground truth A —
a cross-sector story no lane ever finds reads as CORRECT here, and 11 of 285 pairs is a thin base;
(b) v2 is 23 run-days / 5 no-story days — the v2-only rate (1 of 4) is not a rate; (c) the 4 own-promoted
proposals (§6.1) were on the board 1–2 days and nobody has judged them — that is the promote-floor /
lifecycle question the 09-13 read already routed downstream, not a grouping-quality question; (d) trade
outcomes, by standing ruling, untouched.

**Action for the operator:** rule leave / widen / retire on #167's PLAN line. Recommendation: **leave**;
the next Lane-2 read should re-run this exact script when v2 reaches ~20 no-story days (roughly
mid-November at the current 5-per-5-weeks rate), not on a calendar.

---
*Method: prod read-only (`mi_audit_log`, `mi_theme_candidates_shadow`, `mi_ep_alerts`, `mi_themes`,
`mi_daily_closes`, `mi_safeguard_state`); prod filter replicated and cross-checked 64/64 + 14/14; all
dumps captured once to files and post-processed locally (`lane2_review.py` + 3 addenda in the session
scratch dir; results.json). $0 spent. No LLM opinion used anywhere in the classification.*
