# #476 — Biotech theme-crystallization gap: diagnosis + fix design

**2026-07-17 · DIAGNOSIS + DESIGN ONLY.** Read-only prod queries (SELECTs), no code changed, no
deploy, no strategy/money surface touched (THE LINE untouched — themes feed briefs + the shadow-judge
theme-axis only). The load-bearing change proposed here (the biotech sector-cap) is a **methodology /
detection-criterion change → CHANGE_PROCESS + operator sign-off gate every flip** (`docs/setups/CHANGE_PROCESS.md`).
Nothing here is pre-decided; the operator forks in §6 are the decisions.

Probe SQL archived under `scripts/probes/_476_*.sql` (every query below is reproducible read-only).

---

## §0 TL;DR — the adjudicated root cause (and three ways it contradicts the task framing)

**Root cause = the `biotech → max_themes=0` sector-cap exclusion** (`theme_engine.py:3756-3757`,
shipped **2026-03-20** in commit `0d7293f` "Filter biotech/pharma from RS + themes"). In
`_merge_overlapping_themes` **Pass 2** (`:4389-4419`) any theme whose **name** contains one of
`{biotech, clinical, therapeutics, pharma, drug, mrna, crispr, gene edit, orphan drug}` is **silently
dropped** — the `# else: just drop it (shouldn't happen)` branch (`:4419`) that writes **no audit event
and no successor pointer.** Every run of the engine that carries a biotech-named cohort as an incumbent
re-executes this drop.

Two mechanisms turn that drop into perpetual non-crystallization:

- **M2 — the shadow-promote ping-pong.** `promote_shadow_themes` (17:05 ET, `:1466`) resurrects the
  cohort as `Nascent`/`shadow_promoted` (it bypasses the merge, so the sector-cap never runs on it);
  the next night `run_theme_engine` (17:03 ET) carries that row as an incumbent, Pass-2 sector-cap
  drops it → synthetic `Retired`/`live` row. The `mi_themes.source` column literally alternates
  `shadow_promoted ↔ live` night-over-night (§2). The cohort can never accrue `days_active` → never
  reaches Mainstream → members orphan.
- **M3 (task suspect (a), secondary) — exact-set canonicalization can't converge the cuts.** The
  shadow lane re-cuts the same broad cohort every few days under a **new LLM name AND a ±2-3-different
  member set**. `_canonicalize_theme_names` (`:1175`) only matches an **exact `frozenset`** of tickers
  (`:1201, 1241-1243`), so the near-dups never fold into one canonical name — no theme ever accretes
  history even in the shadow lane (§4).

**Contradiction #1 — it is NOT the "overlap-merge protect-strip."** The task states the cuts "die in
the overlap-merge protect-strip." Prod: `theme_pass1_protect_strip` fired for a biotech theme **once in
30 days** (7/10), and even there **both** themes died at the later sector-cap. Protect-strip is not the
kill path; Pass-2 sector-cap=0 is.

**Contradiction #2 — the ADR-0032 Phase-2 machinery does NOT fix biotech** (task asked to prefer
reusing it). Route A (protect-strip → PARENT_CHILD) requires a stable **sole protected parent** to nest
the newborn under (trigger T5, `:3906`) and fires **inside Pass 1**; biotech has **no stable parent**
(all parents die at the Pass-2 sector-cap) and barely protect-strips. Route B (dominant split) needs an
**ecosystem-dominant theme (≥10 members, ≥8 RS-80+)** to split; the biotech cohort never crystallizes
into anything ≥10 members, so there is nothing to split. See §5.

**Contradiction #3 / state finding — `THEME_SUBTHEME_ARM` was flipped ON today.** `mi_safeguard_state`
shows `theme_subtheme_arm=on` since **2026-07-16 21:15 UTC** (Route A/B live from tonight's run onward;
`THEME_MERGE_ARM` env still OFF). **This flip does NOT address #476** — for the reasons in
Contradiction #2. It must not read as "biotech fixed." (All 30 days of kills diagnosed here were
arm-OFF; provenance of the flip is out of scope.)

---

## §1 The smoking-gun correlation (this is the discriminating evidence)

Two silent drop paths could produce a `theme_auto_retired parent='(unknown)'` row: (a) the Pass-2
sector-cap, or (b) a theme simply not re-emitted into the merge. The **name-keyword correlation**
eliminates (b): survival is perfectly predicted by whether the LLM name hits a sector-cap keyword.

Running the **live `_sector_group()`** over the last 35 days of biotech-family theme names
(`scripts/probes/_476` offline check):

| Group | matched `('biotech', 0)` → dropped | matched `None` → kept |
|---|---|---|
| **Dying** (Retired, ≤4-day lifespans) | **13 / 14** | 1 (died via Pass1.5 absorption instead) |
| **Surviving** (climb Nascent→Mainstream) | 0 | **6 / 6** |

- Dying (all keyword-matched): *Oncology Targeted Therapy **Biotechs*** · *Rare & Orphan Disease
  **Biotech*** · ***Clinical**-Stage Oncology **Drug** Development* · *Autoimmune & Inflammatory Disease
  Bio**pharma**ceuticals* · ***Clinical**-Stage Autoimmune... **Therapeutics*** · *Rare Cardiometabolic
  & Endocrine Specialty **Pharma*** · *Rare Disease Small Molecule Precision **Therapeutics*** · *Rare
  Neurological... **Biotech*** · … (13 of 14).
- Surviving (all keyword-free): *Targeted Protein Degradation Oncology* · *Liquid Biopsy & Multi-Cancer
  Early Detection* · *Inflammatory Disease & Immunology Biologics* · *Genomic Medicine & Synthetic DNA
  Tools* · *Peptide & Hormone Therapies…* · *Antibody-Based Oncology & Autoimmune Biologics*.

The survival determinant is a **name lottery**, not member quality: the broad cohort cuts that carry the
elite RS names get generic names ("…Biotechs", "…Therapeutics", "Clinical-Stage…") that hit the
keyword and die; the tiny 2-3-member niches that dodge the keyword survive — and they do **not** hold
the elite orphans.

**Kill-path audit (30d, `mi_audit_log`):** biotech deaths are `theme_auto_retired ... (0 with successor
pointer)` with detail `'<theme>' -> parent='(unknown)'` — the exact signature of a silent Pass-2 drop
(no `theme_pass1_protect_strip`, no `theme_pass1_5_absorption`, no `theme_cap_drop` naming them). The
only biotech `theme_cap_drop` rows in 30d are the three **cyber** vuln-mgmt kills (7/07, 7/13, 7/15) —
a different mechanism (protect-strip-to-empty), not biotech.

**Why biotech is excluded (the March decision, for CHANGE_PROCESS rule 3).** `0d7293f` did two things:
(1) *"Exclude Healthcare sector stocks < $50 from RS leaders"* and (2) *"Biotech/pharma themes capped at
0 (fully excluded)"* — the rationale being that catalyst/binary-event biotech ("speculative names
crowding the list") is not momentum-continuation material. **The RS half has since been walked back**
(grep of `rs_engine.py`/`collector.py` finds no Healthcare/<$50 filter today; the 12 orphans carry
`sector='Healthcare'` and RS 66-92 in the latest `mi_stock_scores`). The theme half was left in place.
The policy is now **internally inconsistent**: the engine RS-scores biotech, discovers biotech cohorts
nightly, then silently kills the themes — orphaning names it rates elite everywhere else. That
inconsistency is the "why it was wrong (now)" the fix rests on (§6).

---

## §2 The ping-pong, shown in the `source` column (Q7)

Per-date `mi_themes` rows — **dying** cohorts alternate source; **surviving** ones are steady `live`:

```
Oncology Targeted Therapy Biotechs   7/07 Nascent  shadow_promoted   ← promote resurrects
                                     7/08 Retired  live              ← engine sector-cap kills
                                     7/09 Nascent  shadow_promoted   ← promote resurrects
                                     7/10 Retired  live              ← engine sector-cap kills
Rare & Orphan Disease Biotech        7/06 Nascent  shadow_promoted / 7/07 Retired live /
                                     7/08 Nascent  shadow_promoted / 7/09 Retired live
Autoimmune...Biopharmaceuticals      6/30 Nascent  shadow_promoted / 7/01 Retired live /
                                     7/02 Nascent  shadow_promoted / 7/06 Retired live
--- vs survivors (keyword-free names) ---
Targeted Protein Degradation Oncology  7/06..7/16  all source=live   Nascent→Mainstream
Liquid Biopsy & Multi-Cancer Early Det 7/01..7/16  all source=live   Nascent→Mainstream→Accelerating
```

The `WHERE source='shadow_promoted'` guard on the promote upsert (`_upsert_promoted_theme:1442-1446`)
is why the ping-pong is a clean day-level alternation: on a "Retired/live" day the guard blocks
re-promotion; the next date it fires fresh. Net: a biotech-keyword cohort is **structurally pinned at
Nascent forever** — the only thing keeping it alive (shadow-promote) cannot advance its lifecycle, and
the engine deletes it every time it becomes an incumbent.

Current state (Q9): **67 active themes** (still above the ADR-0025 ≤55 target), of which **6 are
biotech-family** — all the keyword-free niche survivors above. **All 12 named elite orphans are in zero
active themes** (Q5): AGIO 92 · ZBIO 91 · XENE 88 · TGTX 87 · NRIX 85 · ELVN 84 · ACAD 80 · RARE 79 ·
ANNX 73 · KURA 71 · ALMS 68 · DNTH 66 (latest `mi_stock_scores`; all `sector='Healthcare'` except NRIX
which additionally has no sector enrichment — a separate coverage gap).

---

## §3 The cohort churn — why even the shadow lane can't build one theme (Q8)

`mi_theme_candidates_shadow` rows touching any of the 12 elites, 25d — the "biotech cohort" is really
**3-4 independent sub-clusters, each re-cut under a new name + new member set every few days**:

```
ONCOLOGY   6/24  Next-Gen Oncology Platform Re-Rating         IDYA,GLUE,NRIX,CGON,NTRA
           6/30  Clinical-Stage Oncology Therapeutics         ELVN,CGON,SNDX
           7/01  Clinical-Stage Oncology Drug Developers      CGON,NRIX
           7/07  Oncology Targeted Therapy Biotechs           TGTX,RVMD,ELVN,SNDX,IMNM
           7/09  Clinical-Stage Oncology Drug Development      RVMD,KURA,IMNM,CRVS,SNDX,IMMX
AUTOIMMUNE 6/26  Clinical-Stage Autoimmune...Biologics        VERA,VOR,ZBIO,ANAB,KNSA,AVTX
           6/30  Autoimmune...Biopharmaceuticals              VERA,VOR,ALMS,ABVX,CLDX,TRAX
           7/01  Clinical-Stage Autoimmune...Therapeutics     VOR,VERA,ALMS,CLDX,ABVX
           7/09  Clinical-Stage Autoimmune...Therapeutics     DNTH,ZBIO,ALMS,VERA,ANNX
RARE/NEURO 6/29  Rare & Orphan Disease Biotech Re-Rating      RARE,MIRM,RGNX,AGIO,AMLX
           7/06  Rare & Orphan Disease Biotech                RARE,RGNX,RYTM,MIRM,SRRK
           7/09  Rare Neurological...Genetic Disease Biotech  CRNX,XENE,BBIO,SRRK,AMLX,ACAD
```

No ticker set repeats. Each cut is a fresh `frozenset` → `_canonicalize_theme_names` never matches →
each is a brand-new 2-4-day-lived theme. And **every one of these names hits a sector-cap keyword**, so
each one that gets promoted dies at the next engine run. The two failure modes compound: churn prevents
convergence; the sector-cap kills whatever converges.

---

## §4 Day-by-day trace of one elite orphan (deliverable #2)

### ELVN — the ping-pong made concrete (gains a home nightly, loses it nightly, never crystallizes)

Every ELVN `mi_themes` row is `Nascent`/`shadow_promoted` — it never once reaches a `live` snapshot or
advances past Nascent, and it is homed under **two different names** as the shadow lane re-cuts it:

| ET date | Event | ELVN's home | source/stage |
|---|---|---|---|
| 6/30 | promote fires | *Clinical-Stage Oncology Therapeutics* {ELVN,CGON,SNDX} | Nascent / shadow_promoted — **gains home** |
| 7/01 | engine sector-cap | — (theme → `Retired parent=(unknown)`) | **loses home** |
| 7/02 | promote re-fires | *Clinical-Stage Oncology Therapeutics* | Nascent / shadow_promoted — **regains** |
| 7/06 | engine sector-cap | — (`theme_auto_retired`) | **loses** |
| 7/07 | promote (re-cut, **new name**) | *Oncology Targeted Therapy Biotechs* {TGTX,RVMD,ELVN,SNDX,IMNM} | Nascent / shadow_promoted — **regains, new name** |
| 7/08 | engine sector-cap | — (`theme_auto_retired`) | **loses** |
| 7/09 | promote re-fires | *Oncology Targeted Therapy Biotechs* | Nascent / shadow_promoted — **regains** |
| 7/10 | engine sector-cap | — (`theme_auto_retired`) | **loses** |
| 7/11 → 7/16 | cohort stops being re-cut | — | **orphaned** (0 active themes) |

Each "gains home" is the 17:05 shadow-promote; each "loses home" is the 17:03 next-day engine
sector-cap (all four Retired events are the `parent='(unknown)'` rows in Q4b). ELVN is homed for a
single night at a time, under a name that changes mid-stream, and never accrues a second consecutive
`days_active`. (ALMS shows the same pattern alternating between *two* names on adjacent days:
6/30 "…Biopharmaceuticals" → 7/01 "Clinical-Stage…Therapeutics" → 7/02 "…Biopharmaceuticals".)

### NRIX — the extreme case: never homed once

NRIX has **zero `mi_themes` rows, ever** (Q6, Q9 — no date limit). It lived only in the shadow lane, in
two differently-named, differently-membered oncology cuts (6/24 `{IDYA,GLUE,NRIX,CGON,NTRA}`, 7/01
`{CGON,NRIX}`), and is orphaned at RS 85. Why it never even ping-ponged: (i) its 6/24 keyword-*free*
cut predates the auto-promote job — `shadow_themes_promoted` first fired **2026-06-28** (Q10), so
nothing promoted it; (ii) by the time promote existed, its cohort had re-cut, and its 7/01 cut had only
**2 members** — below `_PROMOTE_MIN_MEMBERS=3`. NRIX is the headline stat (**RS-elite, never homed a
single day**); ELVN is the richer gain→loss trace.

---

## §5 Why the task's suggested reuse (ADR-0032 Route-B / canonicalization) is insufficient

The task asked to prefer reusing ADR-0032 Route-B split machinery or canonicalization. Adjudicated
against the mechanism:

- **Route A (protect-strip → PARENT_CHILD adjudication), now live:** structurally cannot fire for
  biotech. Trigger T2 needs the pair to reach the Pass-1 `j_protected` strip branch; T5 needs a
  **single stable protected parent** with containment ≥ C_MIN. Biotech has **no stable parent** (§1-3:
  every candidate parent dies at the Pass-2 sector-cap) and rarely protect-strips at all (§1). Route A
  lives in Pass 1; the biotech kill is in Pass 2 — Route A never sees it. *(This is exactly why the
  7/14 Phase-2/3 design targeted the cyber vuln-mgmt case, which HAS a 12-member parent, and its fork
  F-2 pre-labeled "most biotech slices legit-kill." #476 says the opposite: they are elite and should
  home. The Phase-2 design does not cover this case.)*
- **Route B (dominant split):** needs an ecosystem-dominant theme ≥10 members / ≥8 RS-80+ to split into
  sub-themes. The biotech cohort never reaches ≥10 stable members — nothing to split.
- **Canonicalization:** reusing `_subtheme_set_match` containment (below) is the correct low-surface
  reuse for the **churn** (M3) — but it is **necessary, not sufficient**: a cohort that converges to
  one canonical *keyword-named* theme **still dies at the sector-cap** the next engine run. It must be
  **paired** with the sector-cap decision, not shipped as a standalone fix.

**Conclusion:** the load-bearing fix is the **sector-cap=0 methodology decision** — not the Phase-2
arm. Do not let the 7/16 arm flip stand in for #476.

---

## §6 Fix design (CHANGE_PROCESS-ready) — forked, nothing pre-decided

### The load-bearing fork — is biotech a legitimate momentum-theme surface now?

This is the operator's momentum-philosophy call (Qullamaggie/Pradeep may deliberately avoid
catalyst-driven biotech). The internal inconsistency (§1: RS-half walked back, theme-half not) is the
trigger, not an auto-answer. Two coherent resolutions — present both; **do not pick a winner in code**:

- **Fork A — re-include biotech as a themed sector.** Raise the biotech `_SECTOR_KEYWORD_GROUPS` cap
  `0 → N` (e.g. 2, matching `oil_gas`), so biotech themes are *capped like every other sector* rather
  than *excluded*. Pair with the containment-canonicalization fix so the oncology / autoimmune /
  rare-disease clusters converge to ≤1-2 stable themes each and crystallize. They then map into the
  already-existing **E-BIO** ecosystem bucket (`theme_ecosystems.yaml`) and surface on `/themes`.
  *Rec (weak, no-money default-to-ship + the inconsistency): lean A* — biotech is already fully in RS +
  discovery + the taxonomy; excluding it only at the theme sector-cap is the inconsistent half-measure
  that produces the orphan churn. **This is a methodology expansion — operator sign-off required.**
- **Fork B — keep biotech excluded, but stop the waste.** Suppress biotech **at discovery** (the shadow
  lanes stop cutting biotech cohorts) so it no longer ping-pongs and orphans visibly; the orphans are
  then "working as designed" (biotech is not a momentum surface). Coherent with the original March
  intent; forfeits the RS-elite signal the operator otherwise trusts. Lower surface than A, but
  discards information.

The fork is **A vs B**; both are legitimate. §6 backtest informs A's thresholds; B needs no backtest
(it is a scope reduction) but is a deliberate decision to leave elite names unthemed.

### Companion fix (reuse, low surface) — containment canonicalization (applies under A; reduces churn under B)

Extend `_canonicalize_theme_names` (`:1175`) to match on **ticker-set containment** — reuse the
existing `_subtheme_set_match(a, b)` helper (`:3851`, containment of the smaller set ≥ `SUBTHEME_C_MIN`
with ≥ `MIN_SHARED_FOR_MERGE` shared members) as a **fallback** when the exact-`frozenset` match misses.
On match, adopt the earliest canonical name (unchanged rule). Effect: the ±2-3-member re-cuts (§3) fold
into one stable name that accretes `days_active`. **Over-merge guard is mandatory** — oncology ≠
autoimmune ≠ rare-disease are distinct drivers; canonicalization must only converge *within* a cluster,
never merge two clusters (they share few/no tickers, so containment stays low — but the backtest must
prove zero cross-cluster merges). This is a change to a de-facto detection criterion → CHANGE_PROCESS +
backtest.

### Independent fix (ship-now, no methodology change) — make the silent drop observable

The Pass-2 `else: just drop it (shouldn't happen)` branch (`:4419`) drops a theme with **no audit
event and no successor pointer** — this is a latent **observability** bug affecting *every* sector-cap
group, not just biotech. Emit a `theme_sector_cap_drop` audit row there (theme, group, members). Pure
telemetry, no criteria change, no operator gate — recommend shipping regardless of the A/B decision so
future sector-cap kills are traceable (they are invisible today).

### Backtest (CHANGE_PROCESS N≥10 — sets thresholds; nothing pre-decided)

Read-only replay probe `scripts/probes/_476_biotech_regran_replay.py` (the `_274_merge_replay` /
`_0032_regran_replay` pattern; read-only `mi_theme_candidates_shadow` + `mi_themes` history — **$0**,
exercises the live `_sector_group`, `_canonicalize_theme_names`, `_subtheme_set_match`):

- **Population (N):** all biotech-family shadow cuts + persisted rows since **2026-06-22** (post-`482dc50`
  discovery fix) — ≥13 distinct cohort cuts across 3 clusters, ~36 distinct elite members (≥ the N≥10
  bar). Kill set = the 13 sector-cap deaths; control = the 6 keyword-free survivors.
- **Part 1 — containment canonicalization grid** `SUBTHEME_C_MIN ∈ {0.6, 0.7, 0.8}`: for each cluster,
  how many cuts collapse to a single canonical name. **Accept:** each of oncology / autoimmune /
  rare-disease converges to ≤2 stable names; **legit-kill guard (hard):** ZERO cross-cluster merges
  (oncology must not merge autoimmune). Choose the **highest C_MIN** that converges within-cluster
  with zero cross-cluster merges.
- **Part 2 — sector-cap `0 → N` grid** `N ∈ {1, 2, 3}` (Fork A only): replay the last 25-30 days with
  biotech capped at N + Part-1 canonicalization applied. **Accept:** (i) the 12 elite orphans obtain a
  **durable home** — ≥5 consecutive `days_active` in one active theme; (ii) total active-theme count
  stays ≤ the ADR-0025 target (≤55) — capping at N, not uncapping, bounds the add; (iii) no non-biotech
  theme regresses. Operator signs one N cell.
- **Output = the sign-off table** (cluster · cuts · canonical name at chosen C_MIN · would-persist
  days · elite members homed), operator-labeled — the agent does not classify (CHANGE_PROCESS rule 4).

### Operator forks (each: the fork + a 1-line rec)

- **F-1 (load-bearing) — biotech as a theme surface: Fork A (re-include, cap 0→N) vs Fork B (suppress
  at discovery).** *Rec: A* (weak) — resolves the RS/theme inconsistency; but this is the operator's
  momentum-philosophy call. **Sign-off required either way.**
- **F-2 — sector-cap N (if A):** 0→2 to match `oil_gas`. *Rec: sign the §6 Part-2 cell.*
- **F-3 — containment `SUBTHEME_C_MIN`:** *Rec: highest cell passing the within-cluster-converge /
  zero-cross-cluster-merge test (illustrative 0.7-0.8).*
- **F-4 — silent-drop audit event:** ship now, independent of A/B. *Rec: yes* (pure observability).
- **F-5 — the 7/16 `THEME_SUBTHEME_ARM` flip vs #476:** confirm it is understood that Phase-2 Route A/B
  does **not** address biotech (§5); #476 stays open on its own track. *Rec: keep #476 separate.*

### SSoT + sequencing

- SSoT: this fix touches the theme engine's granularity/exclusion policy → the change-log lives in
  **ADR 0032** (the theme-granularity SSoT) with a CHANGE_PROCESS-shaped entry; CLAUDE.md Theme-Engine
  section +2 lines at the flip commit; `0d7293f`'s biotech-cap rationale cited + why-now-wrong stated.
- Sequence: (1) ship F-4 audit now (observability, no gate) → (2) operator decides F-1 → (3) if A: build
  dark behind a toggle, run the §6 backtest ($0), operator signs F-2/F-3 + the labeled table → flip →
  verify-live (the 12 orphans appear in an active E-BIO theme on `/themes`, ≥5 consecutive days) → 14d
  data-gated review.

---

## §7 Verified / unverified

**[V] 2026-07-16 (read-only prod):** sector-cap biotech=0 (`:3756`) + silent `else` drop (`:4419`);
13/14 dying vs 6/6 surviving keyword correlation (live `_sector_group`); source ping-pong (Q7); biotech
deaths = `theme_auto_retired parent='(unknown)'`, 1 protect-strip / 0 biotech cap_drop in 30d (Q4/Q4b/Q4c);
cohort churn table (Q8); ELVN/NRIX traces (Q6/Q7/Q10); 12 orphans in 0 active themes, RS 66-92 (Q5);
67 active / 6 biotech-family (Q9); `theme_subtheme_arm=on` 7/16 21:15 UTC; `THEME_MERGE_ARM` env unset;
RS-side Healthcare/<$50 filter absent from `rs_engine.py`/`collector.py`; `shadow_themes_promoted` first
fired 6/28; `0d7293f` commit body.

**[U] / judgment:** the A-vs-B recommendation (operator methodology call); backtest projections (no code
run); that containment canonicalization stays within-cluster (must be proven by the §6 legit-kill guard,
not assumed); whether Route A's now-live adjudicator would ever mis-fire on a biotech pair (it lacks a
parent to fire on, so expected inert — not exhaustively replayed).
