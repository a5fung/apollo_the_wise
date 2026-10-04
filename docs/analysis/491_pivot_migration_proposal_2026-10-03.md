# #491 — Pivot migration: how a stock whose business changed LEAVES its legacy theme and JOINS the theme that matches its current driver (proposal, 2026-10-03)

**Owner**: `docs/architecture/theme_engine.md`. This is a finding and a PROPOSAL, not an owner and not a
change. **Status: DESIGN + a read-only probe. Nothing was built into the engine, no toggle moved, no table
was written, no theme behaviour changed.** The probe (§3) is written and tested but **PENDING its run on
prod** — every number in this document that is dated tonight is the main session's read of the 2026-10-02
board, not a measurement of mine; everything else is code at `origin/main` `6c6ca247` or a dated prior read.

**The decision it serves — his words, 2026-08-04:** *"really this is a theme change for the stocks, not a
similar theme merge. The crypto miners have undergone strategy change, convert their focus on crypto mining
to AI compute, it's a fundamental shift in this groups business."* The merge route was ruled out and stays
out (the adjudicator returned DISTINCT on the crypto × AI pair and was right — bitcoin price and AI capex
are different drivers). **The themes stay separate; the STOCKS migrate.** `mi_theme_exclusions` is
operator-only permanent bans and is NOT a migration tool.

**Measured cost of the gap (unchanged since 08-04):** 5 of his 9 false-positive theme credits were this one
cohort (HUT ×2, WULF, CLSK, IREN; n = 9, `368_first_90_labels_read_2026-08-04.md`).

⚖ **THE LINE**: theme membership is a detector surface, but a member of an Accelerating/Mainstream theme
carries **+10 on its EP score** (`ep_detector.py:1983-2005`, `SCORE_WEIGHTS["theme_bonus"]`), and a score
can cross the HIGH bar on it and fire an alert that reaches the ORB entry. So the mechanism below is
**money-adjacent**: no money moves directly, but what it lists in a paying theme can lift a score. Every
decision in §4 is his; nothing here flips anything.

---

## 0. Method and population

**What was read (n stated per source):**

| source | window / rows | what it supports |
|---|---|---|
| `agents/market_intelligence/theme_engine.py`, `theme_birth_gate.py`, `ep_theme_belonging.py`, `db.py` at `6c6ca247` | the live code | §1 gate trace — every file:line below is this commit |
| the main session's read of the 2026-10-02 nightly board | 8 names (n = 8): CIFR, HUT, CRWV, IREN, WULF, CORZ, CLSK, APLD | "tonight's state" in §1 — **not re-read by me** |
| `scripts/probes/_lat_themes_full.psv` (local prod capture of `mi_themes`) | rows to **2026-09-18**; the 10 theme names that held any of the 8 between 08-27 and 09-18 (n = 10 names, 44 theme-day rows) | the churn history in §1.4 — dated, ends 09-18 |
| `docs/analysis/655_theme_correctness_test_2026-09-27.md` + `scripts/probes/_655/identity_491_members.tsv` | 60 sessions ending 2026-09-25; 12 cohort names (n = 12) | the tape priors in §1.5 (variant A: taxonomy exemplars, the theme's own members excluded) |
| `docs/analysis/cross_industry_themes_2026-09-13.md`, `assignment_comove_backtest_2026-09-13.md` | 710 proposed pairs over 60 nights (n = 710); the IREN pair table (n = 6 pairs) | the signed membership test and its measured behaviour |
| `docs/analysis/491_theme_migration_design_2026-08-05.md` | the prior design (M2 built; M1, M-CORE not) | what already exists and what this supersedes |

**Population for the probe (§3):** the latest non-Retired `mi_themes` row per name inside 7 days (the
`get_active_themes` idiom), `mi_stock_scores` at the latest COMPLETE score date, `mi_daily_closes` over the
60 sessions strictly before the run date, `mi_theme_candidates_shadow` seeded rows inside the 10-trading-day
Lane-2 window, `mi_validation_cooldowns` / `mi_theme_exclusions`, `mi_audit_log` for 45 days, and the 8
names. **No model calls; read-only transaction; $0.**

**Era:** the engine's membership test has been the market-adjusted co-movement tape since 2026-09-13 (bar
0.35), both strip sites since 2026-09-25, and the assignment pool has been priced for it since 2026-09-28.
Anything measured before 09-13 was under the sector-label test and is cited as history only.

---

## 1. WHY tonight's state is what it is — the gates, in the order the engine runs them

**Tonight (2026-10-02 run, as read by the main session):** CIFR and HUT sit in *Bitcoin Miners Pivoting to
AI/HPC Data Center Hosting* **[Fading]**; CRWV sits in *Emerging AI Compute & Cloud Infrastructure
Platforms* **[Mainstream]**; IREN, WULF, CORZ, CLSK, APLD are in **no live theme**.

Two kinds of claim below, kept apart: **decided by code** (true of any night — file:line given) and
**decided by tonight's data** (the probe prints the deciding value; nothing is asserted about it here).

### 1.1 Why CIFR and HUT are in the pivot theme and cannot be offered to the AI-compute theme

| step | the gate (decided by code) | what the probe prints (decided by data) |
|---|---|---|
| a | **The pivot theme's first life was a Lane-2 graduate.** `promote_shadow_themes` promotes any `narrative_cogap` cohort with ≥ 3 members seen in the last 3 days (`theme_engine.py:2311-2312`, `:2459-2697`; allowlist `db.py:9508-9512`) as a Nascent `shadow_promoted` row (08-27). Its second life (09-11) is `source=live` — a Lane-1 engine birth or a continuity rename onto the retired name (`:9060-9090` name inheritance; `_canonicalize_theme_names`), a second re-mint path. | tonight's `source`, birth date, and which cohort names it held each night |
| b | **It fades on its first rescore by construction.** `_rescore_existing_theme` counts members with RS ≥ 50 (`THEME_RS_MIN`, `:270`); fewer than 3 (`THEME_COVERAGE_MIN`, `:298`) and no elite pair → the **Fading branch** (`:3812-3850`, `rs_avg=None`, score × 0.8). A pivot cohort has low trailing RS **by construction** (RS is a 1/3/6-month lookback — the B2 finding of 08-05). | each member's RS tonight; how many clear 50 |
| c | **Five weak-Fading nights retire it** (`_count_consecutive_fading` `:1620-1640`; `FADING_RETIRE_AFTER` `:300`; `:3826-3829`), then Lane-2 re-mints the cohort under a new name and (a) repeats. **This is the churn in §1.4.** | the theme's Fading-night count tonight |
| d | **While it lives, its members are COVERED — in every stage including Fading** (`run_theme_engine` `:8760-8768`, deliberate comment: *"Fading tickers shouldn't attract new assignment either"*). A covered name is excluded from the assignment pool (`_build_theme_pools` `:6995-7005`, `_ok`) and from the M2 seeded path (`_seeded_pool_admissions` `:7064-7069`, `tk not in covered_tickers`). **No code path offers a covered member to a different theme.** This is B1, unchanged since 08-05. | `covered=True`, homes |
| e | **The Fading theme keeps attracting the cohort.** The assignment prompt renders every theme including Fading ones (`[Fading]` tag — `:4909-4921`, `_strip_stage_label` exists because Sonnet echoes it), so an uncovered cohort name in the pool can be assigned INTO the pivot theme, not past it — **IREN was proposed into the pivot theme on 09-17** while it was Fading (SSoT change log 2026-09-28; `_comove_universe_for` `:7016-7021`). The other trap on the same two dates: **CIFR was proposed into *Bitcoin Mining Stocks Rotation Reversal* on 09-21 and 09-28** — a Mainstream bitcoin-named theme, i.e. the +10 under the wrong label. | the `assignment_llm_proposed` rows naming the pair |

### 1.2 Why IREN, WULF, CORZ, CLSK and APLD are in no theme

| step | the gate (decided by code) | what the probe prints |
|---|---|---|
| a | **Assignment pool = RS ≥ 70 within the top-600 leaders** (`_build_theme_pools` `:7002-7005`; `ASSIGN_POOL_RS_FLOOR/CEILING` `:295-296`). | RS and rank tonight (rank reported as the universe `rs_rank` — an approximation of the leaders-fetch rank, as the 08-05 correction states) |
| b | **M2 seeded path** (`:8831-8884`; `db.get_seeded_assignment_tickers` `:9435-9462`; sources `db.SEEDED_ASSIGN_SOURCES` `:9432` = `narrative_cogap`, `ecosystem_reactivation` ONLY — fork F-D, operator-ruled): a name is admitted RS-free only if a seeded row inside the last **10 trading days** (`LANE2_WINDOW_TRADING_DAYS` `:495`) names it. Lane-2 writes a row only off a same-day EP alert scoring ≥ 50 with a catalyst (`_lane2_qualifies` `:663-667`). **No alert → no seed → no ticket.** | the seeded rows in the window, and all lane rows in 30 days |
| c | **Discovery is the top-40 leaders + velocity + turners + correlation clusters** (`:6998-7000`, `:8922-8927`); a low-RS name reaches it only through a stored cluster. | clusters naming each name in 30 days |
| d | **Removal arms — how a member LEAVES a theme today:** hard/soft RS prune (`:3687-3762`, RS < 25 one night / < 35 three nights, rising hold), Mon/Wed/Fri thesis-aware validation (`:3767-3776`, writes `ticker_revalidated_out` + a 14d cooldown `:3093-3122`), the nightly carryforward strip (`:5508-5670`: bans, cooldowns, singleton-sector now judged by the tape, deal pins), the birth strip (`:6805`), protect-strip in the merge pass (`:7667-7745`), the 2-themes-per-stock cap (`:7939-8008`), and the whole theme retiring (§1.1c — every member released at once). | the 45-day `mi_audit_log` trail per name, grouped by event type — **this is the "which path removed them" answer and it is not inferable from the code alone** |
| e | **Orphans have no way back** except (a) or (b). A name released by a retiring theme (§1.1c) waits for an EP alert or RS ≥ 70. The 655 doc recorded CORZ and WULF homeless at RS 19 on 09-26. | last theme each name sat in, and how many days ago |

### 1.3 The gates that do NOT decide tonight — stated so they are not re-derived

- **Birth gate** (`theme_birth_gate.py`): prod mode `dedup_only` (SSoT 2026-09-13/09-17 entries; the probe
  prints the row). A Lane-1 newborn whose members overlap ≥ 50% with ANY non-Retired theme — **Fading
  included** (`find_join_target` `:173-199` skips only Retired) — is `join` and suppressed
  (`run_theme_engine` `:9132-9145`); its **novel members are discarded**, never carried into the join
  target (`theme_birth_gate.py:82-83`). So a newborn "AI compute + ex-miners" cohort that overlaps the
  Fading pivot theme dies before it can place IREN/CORZ anywhere. M1 (join-with-member-carry, 08-05 design)
  was never built.
- **Protect-strip / Route A — the site M-CORE was designed around (08-05 §4.2) is largely PRE-EMPTED.**
  M-CORE fired when a newborn shared members with a protected incumbent and Route A said DISTINCT
  (`:7669-7686`). Under `dedup_only` such a newborn is suppressed as `join` before the merge pass ever
  sees it. **The custody verb needs a site that runs nightly on the standing board, not on birth nights.**
- **`lane2_grouping_v2`** — the SSoT (§"Live toggle state", line 626) records it **ON in paper since
  2026-08-09**; the PLAN #491 line's 08-22 revalidation says *"NEITHER has flipped"*. **These disagree.**
  Reported, not resolved here; the probe prints the `mi_safeguard_state` row. If v2 is on, "M-CORE rides
  the v2 flip" has been waiting on an event that already happened.
- **Parent pass #505**: dark (`theme_parent_pass` OFF), and it offers only non-Fading childless themes.
  When armed it could make the pivot theme a CHILD of the AI-compute theme — a structural answer that
  keeps members where they are. It is not migration and he ruled migration.
- **The sector-outlier strip** no longer decides for a judgeable pair (tape since 09-13 at assignment,
  09-25 at both strips, 09-28 pool priced). Where the tape cannot read (fewer than 3 members with history
  — the pivot theme tonight), the label still decides, exactly as before.

### 1.4 The churn, dated (local capture, ends 2026-09-18 — n = 10 theme names, 44 theme-day rows)

**Life 1** — **born 08-27** (`shadow_promoted`, 8 members: APLD CIFR CLSK CORZ HUT MARA RIOT WULF) →
**Fading 08-28 with 4** (APLD, CIFR, CORZ, RIOT left in ONE night — which arm is not recoverable from the
capture; the probe's audit trail is) → five Fading rows (08-28, 08-31, 09-01, 09-02, 09-03) → **Retired
09-04** — consistent with the §1.1 a→b→c cycle (5 weak-Fading nights). **Life 2** — **09-11, `source=live`**
(Nascent, CIFR APLD WULF) → Fading 09-14/15/16 (CIFR, APLD) → **Retired 09-17 after only THREE Fading
rows** — so the 5-night rule did NOT fire; another arm did. The 09-16/09-17 rows show CIFR in three themes
at once (*Cloud Data Storage & Analytics Infrastructure* Mainstream, *AI data-center power buildout*
Nascent, the pivot theme Fading), which is **consistent with the 2-themes-per-stock cap** (`:7939-8008`)
stripping CIFR from its lowest-scored home and leaving APLD alone below `PRUNE_MIN_TICKERS` →
`theme_cap_drop`. Stated as consistent-with; the probe's audit read (`theme_cap_strip` / `theme_cap_drop`
rows, 09-17 is inside its 45-day window) decides. **Life 3** — live again tonight (Fading, CIFR + HUT; source
pending the probe). Three lives in five weeks by at least two different birth paths and two different
death paths.

Over 08-27 → 09-18 the eight names passed through **10 distinct theme names: 8 bitcoin/crypto/miner-named**
(the pivot theme, *Emerging Bitcoin Miners Diversifying…*, *Bitcoin Mining Equities Momentum Basket*,
*Bitcoin Treasury & Crypto Proxy Equities Correlation Basket* — IREN alone, 09-08 → 09-15 —, *Bitcoin
Mining Stocks Rotation Reversal*, *Crypto Miners Pivoting to Data Center Colocation*, *Second-Tier Bitcoin
Mining & Colocation Operators*, *… (Emerging Names)*) **and 2 AI/cloud-named** (*AI data-center power
buildout* held CIFR; *Cloud Data Storage & Analytics Infrastructure* held CIFR and APLD at Mainstream
09-17). Seven of the eight crypto-named ones held ≥ 2 cohort names (the Treasury basket held IREN alone) —
that 7 is P3's baseline in §2.7. On 09-18 *Bitcoin Mining Stocks Rotation Reversal* was **Mainstream with
WULF and HUT listed** — the +10 under a bitcoin label, the exact 5-of-9 false-credit class.

Lane-2 contributes to the churn by design: its registry refuses to merge *"a miners' halving squeeze vs the
miners' AI pivot"* (`_lane2_registry_clean` `:788-792`, the overlap tripwire), so one cohort can be
re-minted under two stories in the same week (08-27 *Pivoting…* and 08-31 *Diversifying…* split the eight
4 + 4).

### 1.5 What the tape already says about the destination (prior reads, not tonight's)

60 sessions to 2026-09-25, variant A (taxonomy exemplars, the theme's own members excluded; n = 12 names):

| name | tie to E-CRYPTO exemplars | tie to E-AIINFRA exemplars |
|---|---|---|
| HUT | 0.23 | 0.57 |
| CIFR | 0.24 | 0.60 |
| IREN | 0.28 | 0.63 |
| CORZ | 0.14 | 0.63 |
| WULF | 0.21 | 0.68 |
| APLD | 0.27 | 0.68 |
| CLSK | 0.41 | 0.53 |

And the cohort moves with ITSELF at 0.70–0.83 (IREN~CORZ 0.83, IREN~CIFR 0.75, CIFR~CORZ 0.84; 09-13 doc,
n = 6 pairs). Two consequences for any mechanism: (i) the tape puts six of seven with AI infrastructure,
not bitcoin — the destination he named is the one the tape names; (ii) a cohesive cohort inside a
well-populated home will NOT read as "misfiled" against its own basket — the leave trigger must handle a
home the tape cannot read (tonight: 2 members → leave-one-out basket of 1 → `thin_basket`).

### 1.6 The EP money path is already two-legged — what nightly membership still changes

Since 2026-09-13 the +10 is paid when the alerting stock is **LISTED** in an Accelerating/Mainstream theme
**OR** its market-adjusted returns shortlist a paying basket at ≥ 0.35 and `judge_theme_fit` **confirms the
fit** (`ep_theme_belonging.py:1-70`, `resolve_theme_bonus_input` `:346-362`; `theme_engine.judge_theme_fit`
`:4548`). So an unlisted IREN that co-moves with *Emerging AI Compute…* [Mainstream] can already earn the
+10 at alert time **if the judgement confirms it**. What the nightly roster still decides: (a) the LISTED
leg, which is the fallback when the fit call cannot run (budget, timeout, no description); (b) the **wrong
label** case — a pivoted name LISTED in a Mainstream bitcoin-named theme is paid +10 under the wrong story
(09-18, WULF/HUT), and the judge's `in_active_theme` input reads the same list; (c) every operator surface
(§2.5).

---

## 2. THE MIGRATION MECHANISM

### 2.1 The test every option has to pass first

**It must reach BOTH halves.** CIFR/HUT are covered (B1) and need a **LEAVE** verb; IREN/WULF/CORZ/CLSK/APLD
are uncovered under the RS floor with no fresh seed (B2) and need a **JOIN** path. An option that only
re-homes covered members leaves five of eight where they are; one that only admits homeless names leaves
CIFR/HUT in the Fading theme. Then: does it reuse the signed primitives (the tape as the membership test,
the assignment judgement as the fit decider, cooldowns as the anti-bounce wall), is it price-action-anchored
(north star: themes emerge from the tape, never from a hypothesis), and what does it cost per night.

### 2.2 Options

| option | mechanism | reaches LEAVE? | reaches JOIN? | trade-offs |
|---|---|---|---|---|
| **A — a per-ticker "current business driver" read** refreshed from catalysts/filings (one LLM read per name per N days), consulted by the assignment pass | a stored driver tag per ticker; assignment offers a covered member whose tag disagrees with its theme's ecosystem | yes, via the tag | only if the tag also admits a name past the RS floor — a NEW admission rule | **Detection was never the gap** (08-05 §3: the engine knew on 04-09 and on every conversion alert; D2 "build nothing" stands). A per-ticker text tag is a hypothesis surface that goes stale, costs a call per name, and re-opens F-D (an RS-free admission by text, not price action). It also cannot say WHICH theme — only that the label is wrong (the 655 identity read found the same: *"knows bitcoin is wrong, not what is right"*). |
| **B — a thesis-match re-assignment pass over members of Fading themes whose thesis names a pivot** | for a Fading theme whose name/description carries a pivot word, re-offer its members to the live themes | yes, but only from Fading, pivot-WORDED homes | **no** — a homeless name has no theme to be read from | Text-keyed trigger (brittle: *Bitcoin Mining Stocks Rotation Reversal* carried WULF/HUT at Mainstream with no pivot word); misses every orphan; still needs the tape to pick the destination. Narrow by construction. |
| **C — custody by the tape through the existing assignment funnel** (recommended) | a nightly RE-HOMING pass: candidates from three price-action-anchored sources enter the SAME assignment call; the tape (≥ 0.35 to the proposed theme) is the FILTER and the assignment judgement is the DECIDER (the two-stage shape `ep_theme_belonging` adopted after one-stage correlation admitted Dominion → fracking at 0.45); a confirmed fit MOVES the member | yes — source (i) | yes — sources (ii) and (iii) | Every primitive is signed and live: `_comove_verdict`, `_assign_uncovered_to_themes`, `mi_validation_cooldowns`, F4 post-assignment validation. Cost is extra 18-stock batches on the nightly call (priced in §2.6). Source (ii) widens F-D's admission scope and is **his call** (D2). |

### 2.3 The recommendation — "custody by the tape"

**One verb, three feeders.** Built as Step 2a.5 of `run_theme_engine`, after the carryforward strip
(`:9007-9011`) and before assignment (`:9022-9030`), on the board the strip has just cleaned; it feeds the
SAME `_assign_uncovered_to_themes` call with extra candidates tagged `_rehome_from`.

**The candidate sources (each its own toggle arm; the verb is one):**

| source | who | the ticket | today's rule it extends |
|---|---|---|---|
| **(i) covered, misfiled on the tape** | a member of a live theme whose tie to a DIFFERENT live non-Fading theme fires the leave trigger | **#655 G2's signed shape**: own tie < 0.35 AND other ≥ 0.35 AND other ≥ own + 0.20 (baseline 3.4%, 20 of 589 memberships on the 09-25 board) — **plus the unjudgeable-home arm (D3)**: own theme cannot be read (`thin_basket` / `no_history`) AND other ≥ 0.35 | none — covered names are never offered anywhere today (B1) |
| **(ii) orphans** | a name in NO live theme whose last `mi_themes` membership row is ≤ 14 days old | admitted RS-free like M2 (score row fetched explicitly) — a membership-history anchor, the same 14 days the cooldown and `_canonicalize_theme_names` already use | **widens fork F-D** (two seeded sources → three price-action-anchored sources). **D2, his call.** |
| **(iii) join-suppressed newborns** | the NOVEL members of a Lane-1 newborn the birth gate ruled `join` (`dedup_only`) | offered to the join TARGET through the funnel instead of being discarded (the 08-05 M1, unchanged) | today `join` discards them (`theme_birth_gate.py:82-83`) |

**The decider — unchanged and shared.** Each candidate is one more line in the assignment batch; the prompt
line carries its current home (so the model can answer "stays"). The tape re-checks the PROPOSED pair at
≥ 0.35 (`:4958-4981`); an unjudgeable pair falls to today's sector test (`:5001-5006`), never a silent
admit; exclusions, pair cooldowns and the two-pass deferral apply as written. Post-assignment F4 validation
runs on the target as it does for every assignment (`:5063-5076`).

**The verb — MOVE (fork F-A's rec, his framing: "a theme change for the stocks"):** on a confirmed fit for a
source-(i) candidate the member is appended to the target (the funnel already does this) AND stripped from
its source in the same run, with a 14-day `(ticker, source)` cooldown written so the carryforward strip's
arm 2 blocks a bounce-back mechanically (`:5588-5590`). One `theme_member_rehomed` audit row per move
(ticker, source, target, both ties, the judgement's rationale) and one `ticker_rehomed` changelog entry so
the nightly themes state message carries the line in plain words (*"HUT moved: Bitcoin Miners Pivoting →
Emerging AI Compute — moves with it at 0.6, not with bitcoin"*), the way `theme_graduated` already rides it
(`state_alerts.py:525`).

**Walls (mostly existing):**
- **Never INTO a Fading theme** (design §4.4) — the re-homing pass filters its targets; the general pass is
  untouched (D4).
- **Operator rulings outrank the tape**: a `/bypass`-protected `(ticker, source)` pair is never moved; an
  exclusion on the target blocks it (both read through the #601 rename lineage as today).
- **One move per ticker per 14 days**, by the cooldown's `removal_count` — no ping-pong.
- **The re-home cooldown must not count toward the global ban.** `get_globally_banned_tickers`
  (`db.py:15995-16016`; `_GLOBAL_BAN_THRESHOLD` 3 / `_GLOBAL_BAN_LOOKBACK_DAYS` 30, `theme_engine.py:98-99`)
  counts non-bypassed `mi_validation_cooldowns` rows across ≥ 3 distinct themes in 30 days; a cohort
  that churned through seven names would be BANNED from its destination by its own moves. The row carries a
  distinct `removal_reason` prefix (`rehome:`) and the ban query excludes it — one clause.
- **Per-target cap: ≤ 3 re-homes into one theme per night.** Seven ex-miners landing in a 5-member AI theme
  in one night would make it a miners theme by count and invite the #214 mass-flag rename. The cap is a
  bound, not a verdict; the rest wait a night. (Inside D1 — a number he may change.)
- **A source theme that empties retires by the existing engine-drop path** (`:9380-9430`, a Retired tombstone
  with a successor pointer) — *"the old theme fades honestly once its members leave"* (08-05 §4.1 step 4).
  No name surgery, no merge, nothing written to `mi_theme_exclusions`.
- **Toggle**: `theme_rehome_pass` in `mi_safeguard_state`, fail-closed OFF, with per-source arms; OFF is the
  byte-identical engine. `comove_ctx=None` (toggle off / closes read failed) disables the pass for the
  night — the tape is the only trigger, so no tape means no move.

### 2.4 Why this and not the 08-05 M-CORE

M-CORE put custody at the protect-strip site. That site fires on birth nights only, and under `dedup_only`
the colliding newborn is suppressed before it gets there (§1.3). The standing board, not the newborn, is
where the pivot cohort sits every night — so the verb moves to a nightly pass over the board. M2 (shipped
08-05) stays as source (ii)'s sibling; M1 becomes source (iii). The design's §4.3 "what migration is NOT
built on" holds verbatim: no exclusions, no merge, no hand-authored theme, no thesis surgery.

### 2.5 Live surfaces this changes — named

| surface | how it changes |
|---|---|
| **EP score, +10 theme bonus** (`ep_detector.py:1983-2005`, `:2099-2101`; `ep_theme_belonging.listed_paying_set`) | a member moved INTO an Accelerating/Mainstream theme becomes LISTED → +10 on its next EP; moved OUT of a paying theme it loses the LISTED leg (the fit leg still applies). **Money-adjacent — stated plainly: a +10 can lift a score across the HIGH bar.** Pre-registered in §2.7 as U1. |
| the judge's `in_active_theme` input (`mi_ep_alerts`) | reads the same list; follows the move |
| `/themes` board and `/themes TICKER` lookup (`channels/telegram.py:992`, `theme_ecosystems.format_ecosystem_board`) | the name appears under its new theme; the source theme shrinks or retires |
| evening briefing theme section + the nightly themes state-change message (`briefing.py`, `state_alerts.py:525-532`) | one plain-words line per move |
| dashboard `dashboard/theme_rank_evolution.py` (reads `mi_themes`) | member counts move |
| #655 nightly correctness (G1/G2) and #506 hierarchy health | measurement surfaces: G2 "misfiled" should FALL (that is the point); member counts shift |
| `mi_validation_cooldowns` | new rows with `removal_reason='rehome:…'`; the global-ban query excludes them |
| `mi_theme_ecosystems`, `parent_theme`, `mi_theme_exclusions` | **unchanged** |

### 2.6 Cost — one number, from the probe

The pass adds `ceil(candidates / 18)` batches to the nightly assignment call (`_ASSIGN_LLM_BATCH_SIZE`
`:4049`; output ≈ 274 + 73.4 × N tokens per batch on the measured fit `:4027-4043`, × 3.5 on Sonnet 5.x).
The probe prices it at run time from the model the `THEME_MODEL` role resolves to in prod
(`mi_model_resolution`, else `effective_model`) and tonight's candidate count — the laptop pin
(`claude-sonnet-4-6`, $3/$15) is NOT prod's model and is not quoted here. Bound: G2 baseline 20 of 589
memberships + a handful of orphans → ~1–2 extra batches a night. The one-off paid preview (§3, D6) is
8 `judge_theme_fit`-shaped calls at ~1.2k in / ~250 out each — the probe prints its $.

### 2.7 Pre-registration for the build (written now, before any data — the task's `EXPECT:` / `DONE-WHEN:`)

| # | expectation | today's baseline | confirms | refutes |
|---|---|---|---|---|
| P1 | the verb acts | no verb; 0 moves ever | ≥ 1 `theme_member_rehomed` row within 5 nightly runs | 0 rows in 5 runs with ≥ 1 OFFER in the probe → the funnel is rejecting every candidate; read why |
| P2 | the 8 names resolve | 2 covered in a Fading theme, 5 homeless, 1 in the destination | each OFFER from the probe lands in the AI-compute theme or is rejected by the judgement with a stated reason — n of 8 reported both ways | a name still in no theme after 10 runs with no stated rejection |
| P3 | the re-mint churn stops | 7 bitcoin/miner-named themes holding ≥ 2 cohort names in 3 weeks (08-27 → 09-18) | 0 new such births over 15 trading days | ≥ 2 |
| P4 | misfiled share falls | #655 G2 = 3.4% (20 of 589, 09-25 board) | below 2% on ≥ 10 of 15 nights | unchanged |
| U1 | 🔴 +10 exposure (money-adjacent) | 0 | count of EP alerts whose HIGH depended on the +10 AND whose ticker was re-homed in the prior 14 days — **reported to him the same day, any count** | — |
| U2 | bounce-back | — | a `ticker_assigned` to the SOURCE inside the 14-day cooldown = **WOULD-FAIL-IF**; expect 0 | ≥ 1 |
| U3 | volume | M2's ~15/night bound | candidates/night ≤ 15 | > 15 → investigate before anything else |
| U4 | thrash | — | the same name re-homed twice in 14 days = WOULD-FAIL-IF; expect 0 | ≥ 1 |

**DONE-WHEN:** 15 trading days of audit rows; P1–P4 and U1–U4 read in ONE table against this one; the eight
names' homes written down against tonight's. **EXPECT** is this table.

---

## 3. The probe — `scripts/probes/_491/pivot_probe.py` (read-only, $0, no model calls; PENDING its run)

```
docker exec -i apollo-market python - < scripts/probes/_491/pivot_probe.py \
    > scripts/probes/_491/pivot_probe_out.jsonl 2> scripts/probes/_491/pivot_probe_summary.txt
python3 scripts/probes/_491/pivot_probe.py --selftest        # pure parts, no DB
```

What it prints (stdout JSONL by `kind`; stderr the plain-words summary):
- `toggles` — `theme_birth_gate`, `theme_assign_comove`, `theme_parent_pass`, `lane2_grouping_v2`,
  `ep_theme_belonging`, `theme_subtheme_arm` as stored (§1.3's two open questions read from the row).
- `name` × 8 — homes, RS / rank / sector at the latest complete score date, pool verdict, last theme and
  orphan age, seeded rows in the Lane-2 window and all lane rows in 30 days, clusters in 30 days,
  cooldowns / protections / exclusions, EP alerts in 90 days.
- `tie` × 8 — the engine's own `_comove_verdict` against the AI-compute theme's members, the pivot theme's
  members (**expected `thin_basket` tonight and reported as-is**), the name's own home(s), the best other
  non-Fading theme and the top 3; then labelled SUPPLEMENTARY references that are NOT the engine's test
  (8-name cohort leave-one-out, E-CRYPTO exemplars, E-AIINFRA exemplars, min_members = 1).
- `audit` × 8 — 45 days of `mi_audit_log` rows naming the ticker as a whole word, by event type with the
  newest three summaries: **the "which path removed them" read**.
- `verdict` × 8 — `today_path` (what tonight's engine does) next to the recommendation's verdict
  (`OFFER` / `FALLBACK_SECTOR` / `REJECT`) with the DECIDING GATE named — `rehome_verdict` is pure and
  tested (`tests/test_pivot_probe.py`, 38 tests).
- `churn` — every theme name that held a cohort member in 120 days, first/last night, stage counts.
- `sweep` — GENERALIZE: every live theme (and retired ≤ 30 days) whose name or thesis carries a declared
  pivot stem — `pivot`, `transition`, `repurpos`, `convert`, `conversion`, `diversif` — the live non-Fading
  theme its members tie to best, and the members at or above 0.35 to it. A candidate list, not a ruling.
- `pricing` — the model the THEME_MODEL role resolves to in prod, tonight's candidate count → extra batches
  → $/night; the one-off fit preview $.

The probe cross-checks its constants against the running `theme_engine` / `ep_theme_belonging` and stops
loudly on drift. Its pure parts (the gate order, the leave trigger with its unjudgeable arm, the pool
boundary, the board idiom, the stem list, the whole-word regex, the pricing arithmetic) are the tests.

⚠ **Approximation, stated (the #505 probe's lesson):** "covered" and every tie are read off the LAST SAVED
board (the `get_active_themes` read), not off tonight's post-rescore `updated_themes` — a name the next
run's prune or validation releases would still read covered here; and `rs_rank` is the universe rank, not
the leaders-fetch rank behind the 600 ceiling. Close enough to judge the design; not an exact replay of an
engine night.

---

## 4. The operator's decisions

| # | decision | today's behaviour | recommendation |
|---|---|---|---|
| **D1** | Adopt **custody by the tape** as the migration verb: a nightly re-homing pass through the existing assignment funnel; tape ≥ 0.35 filters, the assignment judgement decides; **MOVE** (append to target, strip from source same run, 14-day `(name, source)` cooldown that the global ban ignores, ≤ 3 moves into one theme a night, audit row + a line in the nightly themes message); toggle `theme_rehome_pass`, fail-closed OFF | **no verb exists** — a member leaves a theme only by RS prune, validation removal, a strip, the 2-theme cap, or its theme dying; a covered name is never offered elsewhere | **Yes — build it.** Detector change; +10 money-adjacent through the LISTED leg; CHANGE_PROCESS entry + §2.7 before the flip |
| **D2** | **Orphan reach**: a name in no live theme whose last membership row is ≤ 14 days old enters the assignment pool RS-free (a third price-action-anchored source beside M2's two) | orphans wait for an EP alert (Lane-2 seed, 10 trading days) or RS ≥ 70 inside the top-600; CORZ and WULF sat at RS 19 for weeks | **Yes**, bounded by the 14-day window — but it **widens fork F-D (your 08-05 ruling)** and is yours to widen |
| **D3** | The leave trigger's **unjudgeable-home arm**: own theme too thin to read AND tape ≥ 0.35 to a non-Fading theme → offer | no trigger exists; the engine's own test returns `thin_basket` on tonight's 2-member pivot theme | **Yes** — without it the headline case cannot move (the IREN/BTDR 09-08 shape, lost to a thin basket) |
| **D4** | Fading themes as **destinations** for the general assignment pass | offered (`[Fading]` rendered); IREN was proposed INTO the Fading pivot theme on 09-17 — the covered-exclusivity trap refills itself | **Keep** for the general pass (a Fading theme recovers by gaining strong members); the re-homing pass itself never targets Fading |
| **D5** | Trigger acts on the **first reading** vs two consecutive nights | — | **First reading** (F-B's rec stands): a 60-session correlation is already a long read; the 14-day source cooldown and F4 at the destination are the anti-thrash walls |
| **D6** | **Price and run the checks**: the probe ($0, read-only, tonight's numbers) and then ONE paid preview — the 8 names through `judge_theme_fit` against the probe's OFFER targets (≈ 8 calls; the probe prints the $ from prod's resolved model) | nothing run | **Run the probe first**; the fit preview only if the OFFER set is non-empty |

---

## 5. What this does not answer

- **Tonight's numbers.** The probe is written and tested but has not run; every tonight-dated fact above is
  the main session's read of the 10-02 board. RS, rank, seeds, cooldowns, which removal arm fired on the
  five, and the eight ties are all **PENDING**.
- **Whether the assignment judgement will CONFIRM the eight fits.** The tape filters; Sonnet decides; the
  probe stops at `OFFER`. D6's paid preview is the only way to know before the build.
- **Which arm removed APLD, CIFR, CORZ and RIOT on 08-28** (8 → 4 members in one night) — the capture shows
  the loss, not the cause; the probe's 45-day audit read reaches 08-28 by 9 days.
- **Whether the AI-compute theme is the RIGHT destination, or whether the cohort is its own theme under a
  parent.** The cohort moves with itself at 0.7–0.8 and with AI infrastructure at ~0.6; the tape picks the
  best LIVE basket, and the 655 read's destination call was *"a separate question"*. The sweep prints the
  best target per pivot-worded theme; #505's containment adjudicator (dark) is where "child of the AI
  theme" would be asked. Not pre-decided.
- **Generalization beyond the miners.** The 08-05 90-day sweep found exactly one genuine pivot cohort. The
  stem sweep finds NAMES that say pivot, not pivots; a cohort that pivoted under a stable wrong name
  (*Rotation Reversal*) is invisible to it and visible only to the tape-vs-label read, which the 655 doc
  found too noisy for a board-wide bar.
- **The `lane2_grouping_v2` discrepancy** (SSoT ON since 08-09 vs PLAN "neither has flipped") — reported;
  the probe prints the row; resolving the PLAN line is the main session's CLOSE.
- **Whether a re-homed name should keep a second home** (MAX_THEMES_PER_STOCK = 2 allows primary +
  sub-theme). F-A's rec is MOVE; a COPY variant is not designed here.
- **The destination's identity once it holds more ex-miners than incumbents** — the ≤ 3/night cap bounds the
  rate, not the end state; the thesis-aware F4 validation and the #214 rename are the existing responses and
  are not modelled.

⚖ **THE LINE, restated**: nothing here is built into the engine, no toggle moved, no row written. D1–D6 are
his; the build follows CHANGE_PROCESS with §2.7 as its pre-registration.
