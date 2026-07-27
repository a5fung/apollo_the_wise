# Theme-System Consolidation — design (2026-07-27)

> DESIGN ONLY — no code, prompt, threshold, or flag changed. Every proposal here that touches
> live `mi_themes`, the judge's `active_narratives` input, or any detection criterion is
> CHANGE_PROCESS + operator sign-off before build/flip. #505 (parenting) and #506 (health check)
> are NOT dropped — §5/§7 re-scope them; this design decides what they do first.
>
> Data basis: prod SELECTs run 2026-07-27 (queries in scratchpad `tc_q1..q5.sql`, registry
> simulation `tc_chains.py`). Board-count queries ran on the server's UTC date after the 17:05 ET
> nightly; my "board" snapshot = 83 non-Retired names seen ≤7d (the operator-measured 94 on
> 07-27 includes stages my stricter filter drops — magnitudes agree, Ns stated per claim).

## 0. North star and the one-sentence verdict

Operator (verbatim, 2026-07-27): *"discover subtle RS from themes (early stage) that feeds into
larger themes (more mature stage), and using this edge to help us find stocks to buy before they
are mainstream… keep it simple and focus on the outcome and goal."*

**Verdict: the system has six-plus lanes because it never had ONE gate.** Every lane invents its
own path to a live theme (or a stub nobody can act on), so consolidation is not "pick the best
lanes" — it is: keep the two lanes that answer structurally different questions, route everything
through ONE candidate ledger whose core question is **join-or-new** (the proven #167 registry
pattern), and put ONE birth gate in front of the live board. Parenting (#505) then attaches at
that gate — one place, every path — instead of being retrofitted across six.

```
FEEDS (evidence in)                    ONE LEDGER                      ONE GATE            BOARD
Lane 1: price-action clustering  ─┐
  (+ a/a2 selectors, from shadow) ├─▶  join-or-new registry      ─▶  birth gate:     ─▶  mi_themes
Lane 2: narrative registry        │    (join / child / new /          2-sighting +        (nested under
  (co-gap + RS-slope feed)        │     seed / ignore)                RS floor +          20 ecosystems)
Judge fires → SEEDS (nominate-only)┘                                  driver bar (§6)
                                                                      + parenting (§7)
```

## 1. Measured state (spot-checked today; do not re-derive)

**The candidate table** (`mi_theme_candidates_shadow`, all-time):

| source | rows | names | first→last | auto-promote? |
|---|---|---|---|---|
| shadow_v2 | 116 | 115 | 06-26 → 07-27 | YES |
| narrative_cogap_backfill | 14 | 14 | 05-06 → 06-02 (dead) | no |
| rs_slope_synthesis | 9 | 9 | 06-24 → 07-23 | YES |
| judge_inferred | 3 | 3 | 07-20 → 07-27 | no (surface-only) |
| narrative_cogap | 2 | 2 | 06-25, 07-20 | YES |
| coverage_probe | **0 ever** | — | (13 `mi_coverage_probe` rows since 07-14, 1 families-agree, **0 confirmed**) | no |
| narrative_seed | 0 (dark, flag OFF) | — | — | no |

**Births.** July (07-01→07-27, 18 trading days): **106 births = 61 Lane-1 `live` + 45
`shadow_promoted`** ≈ 5.9/day. All-time: 254 distinct theme names = 193 live-born (median birth
RS **90.2**) + 61 auto-promoted (median birth RS **72.6**).

**Corpses.** 143/254 names (56%) quiet >7d; 73/143 were present ≤7 days, 27 ≤2 days. Corpse birth
split: 118 live-born / 25 promoted — **the churn is systemic, not one lane's junk**. Survival to
today's board: live-born 59/193 (31%), promote-born 24/61 (39%).

**Quality skew is in the promote FUNNEL, not the survivors.** Promote-born survivors now average
RS 81.7 (vs 83.9 live-born) — fine. But the gate lets anything in: tonight's three graduates =
RS **38.7** (Hospital Recovery), **49.1** (Regulated Utilities), 84.2 (Cruise). July births under
RS 70: 22/45 promoted (49%), 18/61 live (30%). `promote_shadow_themes` requires only ≥3 members
seen in 3 days — **no RS floor, no adjudication vs existing themes, no parenting** (theme_engine.py:1999).

**Duplication is SEMANTIC, not member-level — the key instrument finding.** Only 3/106 July
newborns had ≥50% member overlap with any theme alive in the prior 14d, *because Lane 1's
discovery pool structurally excludes covered tickers* (theme_engine.py:4928) — the overlap
instrument can't see re-mints. Where the instrument works, re-minting is heavy:
- shadow_v2: 116 proposals / 115 distinct names — the LLM re-names cohorts nightly. Registry
  simulation (join-or-new at ≥50% intersection-over-smaller, chronological): **116 → 82 NEW +
  34 JOIN (29% were re-sightings); 24 cohorts attracted ≥2 sightings** (top: "HR Outsourcing" ×6,
  "Clinical-Stage Oncology" ×5, "Rare & Orphan Disease" ×4).
- Lane-2 pool replay (measured today, #167): 23 proposals → **4 real narratives** (18/23 were one
  story re-worded), at ~7× lower token cost.
- Cross-lane: rs_slope's "Rare & Orphan Disease Biotech Re-Rating" (06-29) → promoted; shadow_v2's
  "Rare & Orphan Disease Biotech" (07-06) → promoted again at 0.60 overlap. Two lanes, one bet,
  two board rows.

**Ecosystem layer: healthy — and it exposes the categorisation problem.** 18/20 buckets occupied,
catch-all empty. But E-SAAS 11 themes, E-BANKFIN 11 + E-INS 5 + E-REIT 7 = **23 side-by-side
rate-sensitive financial groupings** — sector slices wearing theme names (§6).

**Parenting tonight**: 8 non-NULL `parent_theme` latest rows = **3 containment links (all on
Fading themes) + 5 retirement successor-pointers** — the column is OVERLOADED (containment vs
`theme_auto_retired` successor semantics share one field). Any health metric that counts
`parent_theme IS NOT NULL` without a stage/semantics split lies. No operator surface renders any
of it.

**judge_theme_gap concrete failure, confirmed**: all 3 `judge_inferred` rows are sector-date
stubs — `Judge: Financial Services 2026-07-20` {HUT,IREN} (Lane-2 named the same two "Bitcoin
miners pivoting to AI data centers" the same day), `Judge: Technology 2026-07-27` {QBTS}, and
`Judge: Industrials 2026-07-27` {NNE} whose thesis reads "(no rationale recorded)" — the one
field that was supposed to preserve the story is empty.

## 2. Which lanes survive (the deliverable)

**End state: 2 lanes + 1 seed feed + 1 ledger + 1 gate + 1 digest.** Nothing new is invented —
the ledger IS the #167 registry pattern generalized; the gate reuses machinery that exists.

| # | Lane | Unique question | Verdict | Evidence |
|---|---|---|---|---|
| 1 | **Lane 1 — price-action clustering** (live engine) | which co-moving RS cohorts exist right now | **KEEP** (the workhorse) — add the birth gate; port shadow's a/a2 selectors (accelerators + recovery-slope) into its discovery pool | 193 births, 59/83 of today's board, median birth RS 90.2 |
| 2 | **shadow_v2** | none — same question as Lane 1 with fewer filters | **RETIRE the stream** (fold selectors into Lane 1; remove from `AUTO_PROMOTE_THEME_SOURCES`) | still marked "DRAFT/verify-Monday" in its own docstring (theme_engine.py:1054) yet it feeds an ungated promote; 115 names/116 rows; 29% re-sightings; the RS-38/49 graduates entered here |
| 3 | **narrative_cogap → Lane-2 v2 registry** | what STORY binds names that don't co-move (structurally invisible to Lane 1) | **KEEP — becomes THE narrative lane** (registry already built dark, #167) | 2 live-era proposals in 7 wks, both real (miners→AI 07-20, AI-memory 06-25); replay 23→4; rare-event by design, operator-ruled KEEP 07-27 |
| 4 | narrative_cogap_backfill | none (hindsight population) | **CLOSE** — historical rows only; last write 06-02; already excluded from forward readers | 14 rows, inert |
| 5 | **rs_slope_synthesis** | none separate — "what story binds these coordinated movers" IS Lane-2's question with a different candidate feed | **MERGE into Lane-2**: keep the RS-velocity/turner FEED, route proposals through the same registry join-or-new; drop its independent auto-promote | 9 proposals/7 promoted incl. the 0.60-overlap Rare-&-Orphan near-dup; feed is valuable (slow-burn cohorts Lane 2's EP-alert feed misses), the separate source is not |
| 6 | **judge_inferred** | single-name semantic classification no cohort-floor lane can make (JBL class) | **KEEP the capture, RE-HOME as Lane-2 registry SEEDS** — thesis = judge rationale, provenance-tagged; kill the sector-date stub naming | all 3 rows are sector labels; 1 lost its rationale; the registry's seed slot is EXACTLY this shape (WULF seed → CLSK join → birth, proven today) |
| 7 | **coverage_probe** | deterministic zero-LLM corroboration of a blind-spot cohort | **RETIRE the job; keep P3** (market-adjusted co-movement) as a shared validation primitive for the birth gate | 13 rows, 1 families-agree, **0 confirmed, 0 candidates — lifetime**; its bar (P1 name-hit AND P3 AND persistence) never fires in practice |
| — | narrative_seed | not a lane — Lane-2 v2's internal watch-list state | stays, as part of #3 | 0 rows (dark) |

The judge-seed wall (replaces today's judge_inferred wall, same spirit): **the judge may
NOMINATE, never CORROBORATE** — a judge-sourced seed can convert to a birth only with ≥1
non-judge same-day qualifying anchor, and seeds stay outside `AUTO_PROMOTE_THEME_SOURCES` and
outside `get_narrative_theme_candidates` exactly as they are today. A judge inference alone can
never reach the judge's own `active_narratives` input.

## 3. Should ~6 themes/day be born at all? No.

~6/day against a 7-day absence expiry produced 143 corpses out of 254 names ever — the system
generates faster than it consolidates. The registry pattern applied at the LEDGER level (not per
lane) is the answer, with three components:

1. **Join-or-new against carried state** — every proposal (any feed) resolves against (a) the
   live board AND (b) the last 14 days of ledger entries *including quiet ones* (the biotech
   discover-kill-orphan loop, #476, re-mints against recently-dead names — the live board alone
   can't catch it). Outcomes: JOIN (member union, sighting count +1, no birth) / CHILD (birth
   with parent, §7) / NEW root / SEED (1-name) / IGNORE.
2. **Two-sighting birth bar** — a NEW cohort surfaces to the board only on its 2nd distinct-day
   sighting. Costless delay: discovery is nightly; the earliest tradable signal (a member EP
   alert) is not gated on theme birth.
3. **Derived RS/driver floor** (§6) — the RS-38 hospital cohort never births no matter how often
   it recurs.

**Estimated effect, grounded** (stated as drivers, not false precision):
- The auto-promote stream (45 July births, 2.5/day): under join-or-new + two sightings, the
  shadow_v2 simulation says ≤24 eligible cohorts per ~4.5-week era (~1.1/day) BEFORE the RS
  floor; the floor cuts ~half of what remains (22/45 July promoted births were <RS 70).
- Lane-1 births (61 July, 3.4/day): floor cuts ~30% (18/61 <RS 70); the ≤2-day corpse class
  (27/143 = 19% of all corpses) never surfaces under two sightings; the 14-day quiet-ledger
  check ends the #476-style re-mint loop (unquantifiable from the member-overlap instrument —
  stated as a mechanism, not a number).
- **Net: ~106/month → roughly 40–55/month ≈ 2–3/day**, biased toward high-RS, twice-sighted,
  driver-named cohorts. Operator-visible birth EVENTS fall further under the single digest (§8).
- Lane 2 stays rare by design (2 proposals/7wks) — the registry affects its dedup, not its rate.

This is a detection-criterion change: CHANGE_PROCESS applies, and the backtest population
already exists — the 106 July births replayed through the gate (which ones join, which die at
the floor, which birth late) IS the N≥10 evidence pack for sign-off.

## 4. What is a theme (vs a categorisation) — the testable bar

"Financial Services" (judge stub for two bitcoin miners) vs "Ex-miners pivoting to AI HPC
leases" (Lane-2, same stocks). Tonight's "Regulated Gas & Electric Distribution Utilities"
(RS 49) is the same failure graduating. The bar — a birth must pass ALL three, and each is
checkable, not a vibe:

1. **Driver test** — the thesis names a driver that could CHANGE (a catalyst, policy, demand
   shift — something falsifiable and dateable), not a taxonomy label. Mechanical check: thesis
   non-empty AND theme name not a (fuzzy) match of the sector/industry/ecosystem vocabulary
   (the 20 e_code labels + sector names form the ban-list). "Regulated Utilities" names WHO,
   not WHY-NOW → fails.
2. **Selection test** — members are chosen by the driver, not the partition: the member set must
   differ from "top-RS slice of one industry" — either ≥1 member outside the dominant industry,
   or same-industry peers of comparable RS are excluded and the thesis says why. A theme whose
   members == its industry bucket is the bucket.
3. **Why-now test** — RS evidence consistent with an emerging bet: member-avg RS ≥ derived floor
   OR a rising-RS turner cohort, plus market-adjusted co-movement on ≥2 recent sessions (reuse
   coverage_probe's P3 + SPY-adjust machinery — the one part of that lane worth keeping).

Floor derivation, not selection (repo discipline): the 254-birth history gives the
distribution — live-born median 90.2 vs promoted median 72.6, and survivors vs corpses separate
cleanly enough to derive a floor empirically. Starting cell to backtest: **avg-RS ≥ 70** (would
have blocked 40/106 July births; exact survivor/corpse split per cell comes from the replay).
Operator signs the validated cell, never a picked number.

## 5. Where parenting fits — what #505 becomes

Parenting attaches AT THE GATE, once, for every path — not retrofitted across six lanes (the
sprawl-cementing this design exists to prevent):

- **Every birth is adjudicated** (the existing ADR-0025 adjudicator) against its ecosystem's
  themes: JOIN / CHILD-of / NEW-root. Because auto-promote's successor routes through the same
  gate, the `shadow_promoted` bypass (#505's traced root cause — theme_engine.py:1926-27 writes
  after and outside the adjudication step) is closed structurally, not patched.
- **"Every theme has a parent, even if a catch-all" (operator)** — satisfied by the layer that
  already works: a NEW-root theme's parent is its ECOSYSTEM (94/94 mapped, catch-all empty
  today). No synthetic catch-all themes. Hierarchy = Ecosystem (fixed ~20) → root themes →
  sub-themes; two-level chains proven live tonight (aerospace materials → defence components →
  defence primes).
- **One-time backfill over the current board**: adjudicate within-ecosystem pairs only —
  bounded: E-SAAS 11 and E-BANKFIN 11 are the fat buckets; ~40-60 pair calls total, not 94².
- **Fix the column overload FIRST**: 5 of tonight's 8 non-NULL `parent_theme` values are
  `theme_auto_retired` successor pointers, not containment. Split the semantics (separate
  column or stage-scoped read) or #506's orphan metric is wrong on day one.
- **Render it**: nested indentation on `/themes` under the ecosystem board — the relationship's
  FIRST operator surface (today: four internal files, zero surfaces).

Dependencies it inherits: #471's parent-link persistence fix must be verified-live (first
confirmable run was tonight's nightly) — parenting built on a link that evaporates daily is the
bug we just fixed, not a foundation.

## 6. What the operator sees — and the prompts that die

Rule (operator, today): **never surface a request whose action and payoff aren't immediately
obvious.** Today's flow violates it three ways: 🎓 graduation ping → tells him to run `/themes`
→ a ~100-line board with two extra shadow sections → one of which prompts a *different* command
(`/promotetheme`). And the pings celebrate RS-39 graduates.

**One nightly theme block** (in the existing evening surface), everything in one place:

```
Themes: 83 on board (Δ-2) · 2 births · 3 joins · 1 seed watching
  🆕 Ex-miners pivoting to AI HPC leases — HUT IREN CLSK · RS 87 · 2nd sighting (lane 2)
     driver: miners re-leasing capacity to AI/HPC tenants
  🆕 <name> — <members> · RS <n> · <sighting/lane>
  ↳ 3 proposals joined existing themes (no action)
```

- Every birth line carries name / driver / members / RS / lane — the §4 bar means these fields
  always exist. If a line can't be filled, it didn't birth.
- Operator ACTIONS become rare and self-evident: the only prompt left is a genuine judgment
  call (e.g. a seed the registry wants his read on), phrased with the action AND payoff in the
  message itself — never "run a command to find out what I mean."
- **Dies**: the 🎓 graduation Telegram (folds in), the separate synthesis digest ping (folds
  in), the judge-inferred `/themes` section (becomes registry seeds), below-floor graduations
  (gated out — the RS-49 utilities prompt never happens).
- `/themes` keeps the ecosystem board and gains parent-nesting (§5); the registry roster
  replaces the "nascent narrative" section.

## 7. What #506 becomes — health over the consolidated funnel

The health check watches the CURE, with thresholds DERIVED from distributions measured in this
design (per the derive-don't-pick discipline), one surfaced line nightly:

| metric | today's measured baseline | derived-threshold basis |
|---|---|---|
| births/day (7d avg) | 5.9 | post-Phase-1 median + MAD band (L2 idiom) |
| join:birth ratio | ~0 (no join concept) | shadow-sim 34:82 = the floor; falling toward 0 = re-minting is back |
| corpse rate (births quiet ≤7d later) | 56% lifetime | post-gate cohort, N accrues |
| board count | 83–94 | 30d median 86 already in L2 (`theme_count_active`) |
| orphan rate (non-root themes without live parent) + childless parents | unmeasurable today (column overloaded) | measure AFTER §5's semantics split |
| ecosystem concentration / catch-all growth | E-SAAS 11 · E-BANKFIN 11 · catch-all 0 | operator's red flag: catch-all GROWTH; top-bucket share drift |
| RS-at-birth median | 90.2 live / 72.6 promoted | single funnel → single distribution |

Ship order matters: a **counter-only observability line ships in Phase 1** (no thresholds — so
the consolidation's effect is visible immediately); thresholds derive AFTER the funnel settles,
otherwise they pin the sick state as normal.

## 8. Phased plan

**Phase 1 — the birth gate (stop generating faster than consolidating).**
Unify all live-theme creation through one gate: join-or-new vs board+14d ledger, two-sighting
bar, derived RS/driver floor. Retire the shadow_v2 stream (port a/a2 selectors into Lane-1
discovery; remove `shadow_v2` from `AUTO_PROMOTE_THEME_SOURCES`), retire the coverage_probe job
(keep P3 as a primitive), close the backfill source. Counter-only digest line ships here.
*Gates*: CHANGE_PROCESS — replay the 106 July births through the gate = the backtest; operator
signs the floor cell + lane verdicts. *Proves*: births ~6/day → ~2–3/day; board drifts toward
its 86 median; corpse rate falls. *Unblocks*: parenting lands on a consolidated flow.

**Phase 2 — the narrative side.**
Flip the Lane-2 registry ON (#167 — already built dark; gated on its replay + ADR-0030 judge
eval, both already scoped). Route rs_slope proposals through the registry (its feed survives,
its source retires). Judge fires become registry seeds under the nominate-never-corroborate
wall; `judge_inferred` stub naming retires. *Proves*: narrative stream is join-dominant (replay:
18/23 were joins); judge fires stop minting "Financial Services" stubs. *Unblocks*: one
narrative SoT feeding `active_narratives`.

**Phase 3 — #505: parenting at the gate.**
Adjudicated birth outcomes (JOIN/CHILD/NEW-root), ecosystem-as-default-parent, the
`parent_theme` semantics split, one-time within-ecosystem backfill, nested `/themes` render.
*Gates*: #471 parent-persistence verified-live first; CHANGE_PROCESS (theme structure feeds the
judge). *Proves*: parenting holds on EVERY path incl. auto-promote's successor; E-SAAS/E-BANKFIN
readable as a few bets instead of 11 peers.

**Phase 4 — #506: derived-threshold health check** over §7's metrics + the full digest
consolidation (§6 kill-list completes). *Proves*: this class of regression can't be silent again.

Sequencing rationale: parenting before the gate would nest 6/day of noise (the operator's own
reframe); thresholds before the funnel settles would enshrine the sick baseline.

## 9. Operator decisions (each with the one-line rec)

1. **Retire shadow_v2 as a separate discovery+promote stream** (selectors fold into Lane 1) —
   REC: yes; it is a never-graduated draft feeding an ungated promote, and the main path for
   low-RS board bloat.
2. **Retire the coverage_probe job** (keep P3 co-movement as the birth gate's evidence check) —
   REC: yes; 0 confirmations lifetime; its value can't be demonstrated from data.
3. **RS floor for birth** — REC: derive from the 254-birth replay, starting cell avg-RS ≥ 70;
   sign the validated cell per CHANGE_PROCESS.
4. **Judge-seed wall** (judge nominates, never corroborates; birth needs a non-judge anchor) —
   REC: adopt; kills the sector-stub failure while keeping anti-circularity intact.
5. **Ecosystem as default parent** for root themes (vs synthetic catch-all themes) — REC:
   ecosystem; the layer is complete, healthy, and already the operator's 18-20 simplification.
6. **Sequence**: birth gate (P1) before registry flip (P2) — REC: yes; P1 shrinks what P2's
   judge-eval must cover, and both are independently gated anyway.

Everything above serves one chain: subtle RS → early theme (born once, twice-sighted, driver-
named) → matures inside its parent/ecosystem → members surface before mainstream. Anything the
consolidation removed was answering some other question.
