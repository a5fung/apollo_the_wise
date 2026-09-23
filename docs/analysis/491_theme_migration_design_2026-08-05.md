# #491 — Theme migration: how a stock leaves one theme for another (design, 2026-08-05)

**Status:** DESIGN ONLY — nothing changed, nothing committed, nothing deployed; prod read-only throughout. $0 spent (no LLM calls; all evidence from prod SQL + local code reads, captured once to scratchpad `491/q1..q4`).

**The operator's spine, verbatim (2026-08-04):** *"really this is a theme change for the stocks, not a similar theme merge. The crypto miners have undergone strategy change, convert their focus on crypto mining to AI compute, it's a fundamental shift in this groups business."* The stocks MIGRATE; the themes do NOT merge. The merge route was built 08-04 and withdrawn at its own gate — the adjudicator returned DISTINCT on the crypto×AI pair and was RIGHT to (bitcoin price vs AI capex are different drivers). That work is parked at #529 and stays parked.

**Measured cost of the gap:** 5 of the operator's 9 false-positive theme credits are this one cohort (HUT ×2, WULF, CLSK, IREN — `368_first_90_labels_read_2026-08-04.md`).

---

## 1. The decisions in front of the operator (everything below is evidence for these)

| # | Decision | Recommendation | Gate |
|---|---|---|---|
| D1 | **Approve the migration mechanism: one new verb ("custody") + two reach fixes** — §4. Build order: M2 (seeded-pool exemption, $0, deterministic) → M1 (join-carry, rides the birth-gate flip already scheduled ~08-07) → M-CORE (custody-at-strip, rides the Lane-2 v2 flip, already operator-gated). | Yes. Small, consolidated into three mechanisms that already exist and are already gated for review — no new lane. | Theme membership feeds the judge's theme axis (grade-adjacent, no money). Same class as #534 D2: **operator sign-off + forward junk-watch**, per that precedent. Four forks inside the design (§4.5) each carry a 1-line rec. |
| D2 | **DETECT: build nothing.** The engine detected the pivot on **2026-04-09** — 3.5 months before the gap was filed — and re-detected it in the day-of catalyst of every conversion EP alert. All three candidate detectors named on the task already exist or are unnecessary (§3). | No action. Stated so it is never re-derived. | none |
| D3 | **The neocloud cohort itself: no manual re-homing.** All 8 ex-miners are homeless today while a correct AI theme lives; hand-adding them would be hand-authoring (north-star violation). The paths back and the first checkpoint are in §5. | Accept the wait, or pull M2 forward to this week — M2 is the piece that re-homes them on their next EP alert. | Operator's call on M2 timing only. |
| D4 | **GENERALIZE: this is ONE cohort, not a class** — the 90-day sweep found exactly one genuine business-model pivot (the miners; the sweep independently re-found them by signature). Two other multi-ticker clusters are DIFFERENT, already-tracked defect classes (§6). Optional: file the utilities junk-assign finding as its own small line. | Size the build small (D1 is sized small). One yes/no on filing the utilities finding. | none |

---

## 2. What "migration" means mechanically — the system has every verb except one

The engine's member-level verb inventory, from code (all sites in `theme_engine.py`):

| Verb | Site | Exists? |
|---|---|---|
| leave (weak) | hard/soft RS prune (`_rescore_existing_theme`, F3 rising-hold) | yes |
| leave (wrong) | validation removal → 14d **(ticker, theme)** pair cooldown | yes |
| leave (rule) | carryforward strip: bans / cooldowns / sector-outlier | yes |
| leave (theme dies) | retire / dissolve / age-out → all members released | yes |
| join (strong + uncovered) | assignment pass — **RS ≥ 70 within the top-600 fetch only** | yes |
| join (new theme) | discovery / Lane-2 / promote → birth | yes |
| move (parent↔child) | Route-B split, MOVE semantics (strip from parent same-run) | yes |
| **move (theme A → theme B because the BUSINESS changed)** | — | **NO** |

Three structural blockers make the missing verb unreachable by composition of the others, each verified in code and measured in prod:

- **B1 — covered-exclusivity.** `covered_tickers` includes ALL stages including Fading (`theme_engine.py:5789-5793`, deliberate comment); a covered name never enters the assignment or discovery pools. While "Bitcoin Mining & Crypto Infrastructure Operators" lived (07-08 → 08-03), HUT and CIFR were invisible to every joining lane for a month.
- **B2 — the joining lanes are RS-floored, and a pivot cohort is a crash-recovery cohort.** Cohort RS today (08-04 scores): RIOT 62 · CLSK 59 · APLD 58 · HUT 52 · CORZ 50 · CIFR 48 · IREN 40 · MARA 31 · WULF 24 · BTDR 17. **All ten are below the (new, widened) RS-70 assignment floor — that is the operative, durable blocker.** ⚠ CORRECTED 2026-08-05 (M2 build): the original text also claimed all ten sit "outside the top-600 leaders fetch entirely (ranks 914–2015)" — those are UNIVERSE `rs_rank` values (~9,700 stocks), not leaders-fetch ranks. Replicating `get_rs_leaders(limit=600)`'s own filters (ADV ≥ 500k, close ≥ $10, EQUITY-only, skip-list, Healthcare < $50 post-filter) on the same 08-04 scores puts the cohort at ranks 605–1423 (RIOT 605 · CLSK 668 · APLD 676 · HUT 793 · CORZ 839 · CIFR 874 · IREN 1016 · MARA 1187 · WULF 1291 · BTDR 1423) — near but outside the 600 boundary, and that boundary drifts with the tape. The FLOOR binds all ten regardless of fetch rank, so M2 was built against the floor and bypasses both (score row fetched explicitly). RS is a 1/3/6-month lookback — it is late on a pivot by construction (same arithmetic as #534 §5). Even fully homeless with a live correct theme on the board, assignment cannot reach one of them.
- **B3 — when a new-frame newborn does capture a covered member, protect-strip takes it back.** Pass-1 protect-strip removes the shared member from the newborn; #471 Route A (ON in prod) adjudicates the pair first, but its DISTINCT branch **fail-closes to today's strip** — and crypto×AI IS correctly DISTINCT. So the only verb at the exact site where migration would happen is "member stays with the incumbent, by rule, regardless of what its current catalysts say." The birth gate's `join` verdict has the same shape: it only suppresses the newborn's INSERT — novel members are discarded, never carried into the join target (`theme_birth_gate.py:69`).

The prod history is these three blockers acting in sequence: RS pruning sorted one cohort into crypto-named survivors vs AI-named corpses (#368 M2, fixed by F3); validation evicted the converts from the AI framing (M3, fixed by F4); the shards never shared members so no overlap machinery ever saw the pair (M1); and the two strongest names sat covered in the stale theme, unreachable, until it retired 08-04.

---

## 3. DETECT — measured: nothing to build

The task named three candidate detectors. Measured against prod, all three either already exist or add nothing:

| Candidate | Status | Measured catch date for the miners |
|---|---|---|
| Description-refresh cadence re-thesising a carried theme | **Already exists** — `_news_check` (Perplexity) refreshes every healthy theme's description Mon/Wed/Fri or on material score change | **2026-04-09**: "Riot … selling 3,778 BTC for $289.5M **to fund AI data center expansion**" (Bitcoin Mining & Digital Asset Infrastructure); 04-10: "Hut 8 … **pivot to high-performance computing (HPC) and AI data centers**"; 04-14: "HUT … transformative **$7 billion, 15-year AI data center lease**" (Crypto Asset Recovery) |
| Per-ticker catalyst/news | **Already exists** — EP alert catalysts carry it the day it happens | WULF **07-06** (20-yr Anthropic lease, ~401 MW) · CLSK **07-14** (20-yr $6.6B lease) · IREN **07-20** ($2.8B AI Cloud contracts) · CORZ **07-28** (colocation revenue $10.6M→$136.7M y/y) · BTDR **08-04** ($4.7B 16-yr lease). (HUT's 05-06 row is a backfill stub; its analysis text also matches AI terms.) |
| Periodic thesis-revalidation pass | **Unnecessary** — the thesis was already RIGHT; the defect was that nothing READ it. F4 (deployed, verified in the prod image) now makes the validator judge members against the thesis. The one real thesis defect is the re-mint overwrite, already filed as #530. | n/a |

**Verdict: detection was never the gap.** The engine knew on 04-09 — 102 days before the operator filed #491 on 07-20 — and re-knew it on every alert. What is missing is a CONSUMER of the detection: a mechanism that moves the member. That is scope 2, and only scope 2, and it is why D2 recommends building no new detector.

---

## 4. MIGRATION — the design

### 4.1 The pipeline a pivot actually travels, and where each stage stands

1. **Pivot expresses as price action** — EP alerts with conversion catalysts. EXISTS (measured, §3).
2. **A new-frame cohort assembles across days** — Lane-2. v1 (live) needs 2+ same-day co-gaps and 3+ members to auto-promote; the **v2 registry (built dark, flag OFF, operator-gated)** assembles the cross-day chain — its own replay produced exactly this cohort: WULF 07-06 seed → CLSK 07-14 join → HUT/IREN 07-20 join, "Bitcoin miners pivoting to AI data centers." EXISTS, awaiting its already-gated flip.
3. **The cohort's members transfer into the standing new-frame theme (or the newborn keeps them)** — **THE GAP.** B1/B2/B3 all live here.
4. **The old theme fades honestly once its members leave** — EXISTS (F2 fixed the wrongful-retire half; nothing new needed; the theme is never merged, satisfying the DISTINCT verdict).

### 4.2 The mechanism — three pieces, smallest first, all riding existing machinery

**M2 — seeded assignment-pool exemption (deterministic, $0 LLM, ~15 lines).** *[BUILT 2026-08-05, operator-approved D1 — `db.get_seeded_assignment_tickers` / `theme_engine._seeded_pool_admissions`, pinned by `tests/test_seeded_pool_exemption.py`; replay `scripts/probes/_491_m2_seeded_pool_replay.py`; SSoT updated in `docs/architecture/theme_engine.md`.]*
A ticker named in an ACTIVE Lane-2 narrative row (`narrative_cogap`, ≤10 trading days old) or a #536 reactivation seed is admitted to the ASSIGNMENT pool regardless of RS floor and fetch rank (its score row fetched explicitly from `mi_stock_scores`). The existing assignment LLM still decides fit against the live theme list; pair cooldowns and post-assignment F4 validation still apply; discovery stays untouched at top-40.
- *Why:* closes B2 exactly where it bit — the price-action lanes are the ONLY signal with no RS lag, and they already carry the cohort's names; today those names die in shadow rows while the correct live theme sits 3 members wide. Bounded: ~≤15 admitted names/night at current lane volume.
- *This is the piece that re-homes the actual cohort* on its next alert (§5).

**M1 — join-with-member-carry at the birth gate (rides the gate's observe→on flip, ~08-07 calibration).**
When the gate (ON) rules `join` (IoS ≥ 0.5 vs a live theme), offer the newborn's NOVEL members to the join target as assignments instead of discarding them — through the existing walls: pair cooldowns, post-assignment F4 validation, `MAX_THEME_STOCKS`.
- *Why:* a join today records "same cohort, second sighting" and then throws away the very members whose arrival was the signal. Small semantics change on an already-operator-gated flip; fold into that sign-off rather than a separate lane.

**M-CORE — the custody verb at the protect-strip / Route-A site (the genuinely new mechanism).**
Today, when a newborn shares member X with a protected live theme A and Route-A adjudication says DISTINCT, the branch fail-closes to "strip X from the newborn" — the incumbent keeps X by rule. Change: on DISTINCT with shared members, run a per-member **custody check**: one Haiku call judging X's CURRENT evidence (most recent EP catalyst ≤90d if any, plus description) against thesis A vs thesis B — the F4 validator's exact idiom with two theses instead of one. Verdicts:
- `stay` (default, and the fail-closed answer on any error/no-evidence) → strip from newborn, exactly today's behavior;
- `move` → X stays in the newborn (or join target), is stripped from A same-run (Route-B MOVE idiom), and a 14d `(X, A)` validation cooldown is written so the carryforward strip mechanically blocks any bounce-back.
- *Why this site:* it is the one place the system already holds both theses, both member sets, and an adjudicated DISTINCT — the migration question ("which thesis does X's current driver match?") is only askable there, and it is the exact site #471 Route A already instrumented. It composes with stage 2: once the Lane-2 v2 registry promotes the cross-day cohort (WULF+CLSK+HUT+IREN = 4 ≥ 3-member floor), the newborn shares HUT with the live crypto theme → custody moves HUT out — the full migration completes with no merge, no exclusion, no hand-authoring.
- *Cost:* only fires when a newborn actually forms with contested members — a few per week at most; ~$0.01/incident.

### 4.3 What migration is NOT built on — stated per the task
- **`mi_theme_exclusions` is untouched** — operator-only permanent bans, never a migration tool.
- **No theme merge** — the DISTINCT verdict is respected; #529 stays parked on its own correction.
- **No hand-authored theme, no hard-coded sector** — every trigger is price action (an EP alert, an RS-clustered rediscovery); the LLM only reads the alert's own catalyst text. North star intact.
- **No thesis/name surgery on the old theme** — it keeps its identity and fades on its own mechanics when its members leave (F2 made that honest).

### 4.4 Anti-thrash — mostly walls that already exist
- **14d pair cooldown** on `(ticker, old_theme)` at every move — already enforced daily by the carryforward strip; a moved name mechanically cannot re-enter its old home for 14 days.
- **F4 thesis-aware validation at the destination** (Mon/Wed/Fri + post-assignment, deployed) — a wrong move is re-judged within ≤3 sessions; measured FP cost of the analogous F3 hold was days-of-one-weak-member vs cohort destruction the other way.
- **One custody move per ticker per 14d** (new, trivial counter via the cooldown table's `removal_count`).
- **Never migrate INTO a Fading theme** (new, one predicate).
- **Rate bound:** M2 admissions ≤ ~15/night by construction; custody fires only on newborn formation.
- **Operator surface:** every move emits one audit row + one Telegram line ("HUT moved: Bitcoin Mining & Crypto Infra → AI GPU Compute — catalyst: 20-yr AI lease"), so a thrashing name is visible on day one.

### 4.5 Forks inside the mechanism (each needs a ruling; 1-line recs)
- **F-A — MOVE vs COPY when the member is covered elsewhere.** Rec: MOVE — the operator's own framing ("a theme change for the stocks"); dual-homing re-creates the ambiguity this task exists to end.
- **F-B — custody acts on FIRST evidence vs two-sighting.** Rec: first evidence — the walls above catch a wrong move in ≤3 sessions; the measured cost of holding was 3 months of wrong credit (5 of 9 false positives).
- **F-C — custody default with no recent catalyst evidence.** Rec: `stay` (today's behavior) — migration must be earned by evidence, never by absence of it.
- **F-D — M2 admission scope.** Rec: only tickers in active Lane-2 rows / reactivation seeds (never a raw RS band) — keeps the exemption price-action-anchored and bounded.

### 4.6 Evidence plan before build (per CHANGE_PROCESS discipline; membership is grade-adjacent, not a trading criterion)
- **M2 / M1:** $0 replays over the frozen `_368` exports + the birth-gate ledger (populating since 07-29): count admissions and joins the mechanisms would have produced; the D2 precedent (ship on design + forward junk-watch, operator-signed) applies.
- **M-CORE:** replay the Lane-2 v2 registry chain against the July board — the acceptance fixture is: registry promotes the 4-name cohort → protect-strip fires on HUT → custody returns `move` on HUT's 07-20 catalyst vs the two theses. Paid portion ≈ 4–8 Haiku calls ≈ **$0.05 one-off**, run where the key lives, captured once.

---

## 5. The concrete neocloud cohort — where it stands today and what brings it home

Prod, 08-04 board (latest at measurement):
- ⚠ CORRECTED 2026-08-05 (M2 build) — **the cohort is NOT all homeless.** Measured against the live board 08-05: **APLD is IN the live AI theme** (`AI GPU Compute Infrastructure & Cloud Services`, Nascent, 08-04 row); **HUT and CIFR are still COVERED by the Fading crypto lineage** (`Bitcoin Mining & Crypto Infrastructure Operators`, latest non-Retired row 08-03 Fading — inside the 7d recency horizon, and Fading rows keep tickers covered); **BTDR appears only in the Retired 08-04 duplicate newborn** (`AI Data Center Infrastructure Buildout` {BTDR,AMRC,BLZE}) so it IS uncovered. Genuinely homeless: WULF, IREN, CORZ, CLSK, RIOT, MARA. WULF/CORZ cooldowns until 08-10 point at a theme that died 07-27 — pair-scoped, they do NOT block any new home. (Original claim "all 8 homeless / the stale crypto theme retired 08-04" — the crypto theme's 08-04 death was a silent vanish, not a Retired row, so its 08-03 Fading snapshot still covers HUT/CIFR until it ages out.)
- **A correct landing zone is LIVE:** `AI GPU Compute Infrastructure & Cloud Services` (Nascent, 08-04: APLD, CBRS, CRWV) — plus the same-night Lane-2 rediscovery (`AI Data Center Infrastructure Buildout`, BTDR+AMRC+BLZE) died as a duplicate on its first day, again.
- **Nothing currently deployed can connect them** (B2: all ten under the RS-70 floor; the uncovered ones also sit outside the top-600 filtered fetch — see the §2 correction). F2/F3/F4 + D2 + #536 are verified in the running image — they protect the landing zone; they do not carry anyone to it.

Paths back, in order of arrival:
1. **Lane-2 v1 (live, allowlisted):** 3+ cohort names co-gapping the SAME day births/promotes a theme holding them — with F2/F3/F4 deployed it now survives. This is the no-build path; it needs a same-day cluster.
2. **#536 reactivation (deployed):** E-CRYPTO is now dormant; a burst of ≥3 cohort HIGH EPs within 5 sessions fires once July's alerts age out of its quiet-baseline window — it SEEDS discovery, it does not migrate members. Complementary, not the owner.
3. **M2 (once built):** the next single cohort EP alert (CORZ alerted 07-28, BTDR 08-04 — they keep coming) re-homes that name into the live AI theme through normal assignment. This is why D3 offers pulling M2 forward.
- **Not a path: hand-adding the tickers** — hypothesis injection; the north star holds even when it is slower.
- **First checkpoint:** tonight's 08-05 17:00 ET run is the first with F2–F4 + D2 live — watch whether the AI theme holds and whether any cohort name reaches a board surface; then per-alert as above.

---

## 6. GENERALIZE — one cohort, not a class

Sweep: every ticker sitting in themes of ≥2 different ecosystems over the trailing 90 days (`mi_themes` × `mi_theme_ecosystems`). **25 tickers**, hand-classified from the underlying theme rows:

| Cluster (eco signature) | Tickers | Classification |
|---|---|---|
| E-AIINFRA × E-CRYPTO | **CORZ, IREN, WULF** | **The genuine pivot cohort — the sweep independently re-finds #491's subject by signature.** (HUT/CIFR/CLSK/RIOT/MARA don't appear because they never got a second-frame row — the sweep sees DISPUTED identities, not undetected ones.) |
| E-ENER × E-INDL | AVA, BKH, NJR, NWE, POR, SR | **Not a pivot — junk-assignment**: six regulated gas/electric utilities sat inside "U.S. Petroleum Refining & Downstream Processing" (07-23→07-30) while their correct home ("Regulated Gas & Electric Distribution Utilities") lived 3 days and was engine-drop killed 07-30 "no successor found". Routes to the D2 junk-assign watch + the engine-drop gap already named in #531. Optional: file as its own small line (D4). |
| E-CONS × E-HLTH × E-UNASSIGNED | CVSA, LINC, PRDO, STRA, LAUR, UTI | **Not a pivot — re-mint churn + mapping flip-flop**: one for-profit-education cohort under 4 names in 3 weeks, the ecosystem mapper assigning each rename differently. #476-class churn + the #471 mapping-quality note. Already tracked. |
| Remainder (2-ticker / singletons) | AMRC, EFOR, BLZE, BSX, DDOG, BZ, SE, FA, IT, RYZ, +misc | Duplicate-birth night noise (08-04 defense), taxonomy granularity (HLTH/MEDTECH, CYBR/SAAS), adjacent framings of one business. Not pivots. |

**Number for the operator: 1 genuine business-model-pivot cohort in 90 days.** The mechanism is worth building because its cost was measured (5 of 9 false credits) and pivots recur (the market is mid-pivot on power/compute broadly) — but it should be built SMALL, which §4 is. Two caveats, honest: 91 of 256 theme names in the window carry no ecosystem mapping (36%) so the sweep undercounts; and a pivot the engine never expressed under a second frame at all is invisible to it.

---

## 7. What existing work already covers — so nothing here duplicates it

- **#368 F2/F3/F4 (deployed, verified in the prod image):** the landing zone no longer evicts converts on legacy captions (F4), no longer prunes them mid-ignition (F3), no longer retires the day after recovery (F2). The DEATH half of migration is done.
- **Lane-2 v2 registry (dark, operator-gated):** the cross-day cohort assembler — stage 2 of the pipeline. This design adds M-CORE at its output, not a competing lane.
- **#536 reactivation detector (deployed):** the wake-up-while-DEAD case. #491's class is pivot-while-ALIVE; complementary.
- **#530 (filed):** the thesis-overwrite defect — protects the thesis text every mechanism above reads.
- **#471 (in flight):** Route A is the custody site; #505/#506 keep the parent links honest. M-CORE extends Route A's DISTINCT branch rather than adding a pass.
- **#529 (parked, correctly):** the merge family — stays parked; this design is the answer to its operator correction.

## 8. What could NOT be measured, and why

- **Whether M-CORE would have re-homed the cohort on specific July dates** — the full-fidelity replay needs the v2 registry chain + gate ledger, and the ledger only populates from 07-29; the §4.6 fixture is the honest substitute.
- **Custody-call quality / false-move rate** — needs the ~$0.05 paid fixture (§4.6) or a wider ~$0.30 replay over all 73 HIGH alerts; not spent under this task's $0 constraint.
- **Tonight's post-deploy behavior** — F2–F4/D2 first act 08-05 17:00 ET; forward evidence pending.
- **The sweep's blind side** — pivots never expressed under a second frame (RIOT/MARA-shaped) are structurally invisible to any membership-based sweep; only the catalyst lane (M2's trigger) sees those.
