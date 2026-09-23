# ADR 0024 — Judge-system integration: one brain from five parts (Fable block A, #419/P1-P3)

**2026-07-07 · Status: ACTIVE — operator-signed 2026-07-07 (§9; all 6 forks resolved per the recommendations)**
The five judge-adjacent systems were each designed to execution depth in their own ADRs —
grade judge (0011, LIVE load-bearing) · theme/structure axes (0015/0016, shadow) · management
judge (0017, L0 shadow) · experience stack (0018) · full sight (0021) — but the 7/5 D-series
sprint left the layer BETWEEN them undesigned: how they compose, who wins, one payload, one
promotion ladder. This ADR designs exactly that integration; **it changes NOTHING the six
signed ADRs decided internally** (credit tables, ladder rungs, retrieval rules, detection
mechanics all stand). First turnkey milestone: **the #335/#329 M1 flip, 7/18** (§6).
THE LINE: every authority change here is toggle-gated + CHANGE_PROCESS + operator-signed.

---

## 1. The pipeline (the one picture)

```
ENTRY-TIME (per candidate, pre-9:45)                    POST-ENTRY (per position)
──────────────────────────────────                      ─────────────────────────
deterministic GATES (M&A, revenue-stage,                MECHANICAL FLOOR (stops,
dedup, window, safeguards)  ── veto only                partials, trails, time-stops
        │                                               — the 0023 tune's domain)
floor grade (_classify_catalyst_claude                          │
+ pplx cross-check → baseline_floor_tier)               MGMT JUDGE (0017; L0→L3
        │                                               ladder; bounded enum; can
THE JUDGE (0011; Opus; grades the CATALYST              only ADD risk-reduction)
over grounded corpus) → judge_tier                              │
        │                                               executes via #151-hardened
AXIS COMPOSITION (§3): capped, arithmetic,              functions, mode-isolated
legible credits → final_tier                                    
        │                                               CROSS-CUTTING
AUTHORITY RESOLVE (§2 order) → alert + ORB entry        experience (0018): enriches BOTH
                                                        judges' payloads; labels feed all
                                                        evals; ensemble → sizing lane only
```

## 2. Precedence & arbitration — the bounded contract (who wins, by construction)

Conflict is designed OUT by giving each layer a bounded domain; no layer can express an
opinion outside it:

| Layer | Domain (may express) | May NEVER |
|---|---|---|
| Deterministic gates | binary veto (skip/block) | grade anything |
| Floor | fallback tier + catalyst_quality | override the judge |
| **Judge (0011)** | the CATALYST verdict: real/material/fresh → judge_tier + fire_axes + rationale | move stops, size positions, gate M&A |
| **Axes (0015/0016/#331/neg)** | CAPPED arithmetic credit on the composed tier (§3) | rescue a vetoed name; exceed the cap; penalize absence (boost-axes) |
| Ensemble (0018 §6) | a divergence FLAG → conviction-sizing/abstain lane | touch the tier |
| Precedents/sight enrichers | payload TEXT the judges read | arithmetic effect on any tier |
| **Mgmt judge (0017)** | post-entry verdicts within its ladder rung | entry decisions; lowering the mechanical floor |
| Mechanical exit floor | always-on; the 0023 tune's parameters | be overridden by any judge (judges only ADD risk-reduction) |

**Precedence order (entry-time), highest first:** gates → composite tier (§3) → display.
**Fail-open chain:** axes fail → judge_tier stands · judge fails → floor tier (+ axes still
compose on it — one seam, §3) · everything fails → floor, exactly today's behavior. Every hop
emits its existing audit (`judge_timeout_fallback` etc.) + the composite adds its own (§4).

## 3. The composition model — the ONE open design question, answered (fork F1)

0015 deferred it verbatim: "the #329 composition decides the judge-vs-axis split at flip
time"; the axes were designed against the FLOOR label boundary but the JUDGE now owns tier —
and the judge ALREADY weighs theme/structure qualitatively (0011 rubric clause 4), so axis
credit on top = double-count.

**Decision (rec): split the meta-rubric by DOMAIN — the judge owns the CATALYST axis; the
scored axes own CONTEXT credit; the final tier is their capped arithmetic composition.**
This IS `user_meta_rubric_architecture` realized ("catalyst rubric = ONE input of many;
final grade combines fundamentals + theme heat + technical structure + gap alignment").

- `compose_final_tier(base_tier, credits) -> (final_tier, contributions)` — pure function:
  base_tier = judge_tier when authority=judge, else floor tier (same function on fallback).
  Boost-axes (theme/structure/gap-align) apply per their signed tables; neg axis demote-only;
  **stacking cap: net movement ∈ {−1, 0, +1} tier-step total** (0016's proposed default,
  fork F2). Tier lattice: none < MODERATE < HIGH (credits move along it; nothing composes
  above HIGH or below none).
- **The double-count fix — a rubric amendment (rides the M1 flip commit, CHANGE_PROCESS):**
  the judge still SEES theme/structure/gap context (it needs them to judge catalyst
  attribution — "the theme explains this gap"), but is instructed its tier = the CATALYST
  verdict; context credit is applied OUTSIDE by the calibrated axes. Rubric clause 4 is
  amended from "modulate up or down" to "inform attribution; the scored axes own the credit."
  Judge-rationale keeps citing context freely — legibility unchanged.
- Legibility contract (0015's win, generalized): `/why` renders
  `judge strong (catalyst) + theme Accelerating (+1) − dilution overhang (0) → HIGH` with
  every contribution named. No invisible math.
- **Pre-flip, nothing changes**: axes stay shadow; the judge's qualitative weighing stands.
  The amendment + composition go live TOGETHER at M1 (atomic — never a window where theme is
  neither judge-weighed nor axis-credited, and never both).

## 4. The unified decision object — `DecisionContext` (one payload, one trace)

**Assembly reuse, not new machinery**: `build_judge_payload`
(`agents/market_intelligence/judge_replay_common.py` — already the shared seam between the
live path and every replay/eval harness) becomes the single assembler. It gains typed,
versioned BLOCKS; each enricher ADR plugs its block in where it already planned to:

```
DecisionContext v1 blocks (each independently optional; absence = omitted, never fabricated):
  identity: ticker · alert_date · gap_pct · pm_rvol · vol_percentile · market_cap · sector ·
            revenue_stage · ep_score (context, never floor — 0011)
  corpus:   grounded_text + provenance (has_direct_source) — 0019's manifest
  floor:    baseline_floor_tier · catalyst_quality · pplx cross-check
  axes:     per-axis {raw features, credit_steps, marker, reason} — 0015/0016/#331/neg(0021)
  sight:    intraday_cohort (0021 §1) · neg_flags (0021 §2) · chart_verdict (#343)
  memory:   precedents K=3 (0018 §4) · character profile + ranked pivots (0017 §2, mgmt only)
  verdicts: judge {tier, direction, materiality, fire_axes, rationale, confidence} ·
            ensemble {second_tier, delta} · composite {final_tier, contributions} · authority
  meta:     rubric_version · composite_version · payload_block_versions
```
- **Both judges read the same blocks** — the mgmt judge's payload (0017 §3.2) = identity +
  corpus-lite + axes + sight + memory(+character) + position state; the grade judge's = the
  entry-time subset. One renderer per block, shared (0018's ≤120-token precedent block, 0021's
  cohort line, etc. — each block's format is its ADR's, unchanged).
- **Persistence stays where it is** (alerts columns, per-axis shadow tables, decision rows) —
  DecisionContext is the ASSEMBLY, not a new store. Post-flip the composite emits ONE new
  audit event `ep_composite_decision` {base_tier, per-axis contributions, final_tier,
  composite_version} — extending 0011's full-reconstructability requirement to the composite.
- The #405 cache carries axis/enricher fields with the same completeness as a fresh tick
  (the has_direct_source cache gap is the known instance — #405 Part-1 closes it; a pin test
  asserts cached-path payload parity per block).

## 5. One promotion ladder — the cross-pillar authority vocabulary (fork F4)

The D-series shipped four bespoke promotion mechanics. Unify the VOCABULARY (not the working
toggles — they stay):

| Rung | Meaning | Grade-path gate (per component) | Mgmt-path gate (0017, unchanged) |
|---|---|---|---|
| **L0 shadow** | logs beside live; zero effect | ships on build | live 6/18 |
| **L1 advisory** | rendered on operator surfaces | shadow accruing + verified | ≥30 labels · ≥80% act-agreement |
| **L2 bounded authority** | arithmetic/auto effect w/ caps | N≥10 divergences w/ outcomes + operator labels + batched-regrade delta + CHANGE_PROCESS + sign-off | L1 3wks + 50 labels + clean counterfactuals |
| **L3 authoritative** | owns its domain's verdict | sustained L2 + its own sign-off | L2 4wks clean |

- **Registry**: `mi_authority_registry (component TEXT PK · rung TEXT · toggle_ref TEXT ·
  promoted_at · evidence_ref TEXT · demoted_from TEXT NULL)` — RECORDS state; the existing
  per-component toggles (holistic_judge_enabled, MGMT_JUDGE_AUTHORITY, JUDGE_PRECEDENTS,
  composite_authority) remain the mechanism (don't migrate working kill-switches).
- **Surface**: a "🧠 Authority map" SECTION in the Sunday weekly review (consolidate-surfaces
  rule — no new command): component · rung · days-at-rung · next gate.
- **Auto-demotion generalized** (0017's principle): an operator-labeled harmful authority
  action (wrong tier-flip by an axis, harmful auto-partial) drops THAT component one rung
  pending review — recorded in the registry, Telegramed, CHANGE_PROCESS to re-promote.
- Current rungs at signing: judge L3 (live) · mgmt judge L0 · theme/structure axes L0 ·
  neg axis/radar not-built · precedents not-built (shadow-attach = L0) · ensemble not-built.

## 6. M1 — the 7/18 checkpoint, card-decomposed (the first turnkey integration milestone)

#335's contract: ONE batched regrade (never per-axis spend), operator sign-off, DB toggle,
fail-open. Scope per #335: **flip the CORE first — the theme axis** (fork F3); structure/
gap/neg/chart flip at later checkpoints off the same harness with their own evidence.

| Card | What | Lane |
|---|---|---|
| M1-a | `compose_final_tier` + contributions + cap + tests (golden: NBIS boost case · a cap-clip case · fallback-composes-on-floor · Fading=0) — built DARK behind `composite_authority` (default off) | Sonnet card |
| M1-b | Batched regrade run: `eval_judge_enrich --regrade` over the labeled cohort with pending enrichments toggled (theme credit · has_direct_source-in-cache · structure features as payload text) → per-enrichment verdict-delta table + cost, ONE paid run | Sonnet card (harness exists) |
| M1-c | The rubric amendment text (§3) + the composition weighting sheet — drafted for the sitting | Opus, small |
| M1-d | **The M1 sitting (operator)**: walk deltas + labels → sign composition + cap + amendment → flip `composite_authority` | operator gate |
| M1-e | Post-flip: verify-live on next scan (composite audit rows + `/why` contributions) + a recurring `composite_effectiveness` entry in data_gated_reviews (the harvest_rule pattern: ≥10 post-flip tier-flips or quarterly, re-arms) + registry row L0→L2 | Sonnet card |

Pre-M1 dependency check (all green today): theme shadow live (7/4) + STEP-0 calibrated (N=452
cohort) · labeled cohort exists (0018 X1 backfills it formally, not an M1 blocker — the 7/4
sitting labels suffice for M1-b) · harness proven (#267/#344 runs) · #405 Part-1
(has_direct_source cache) rides M1-b's enrichment list.

## 7. What this ADR explicitly does NOT do

Reopen any signed table/gate/rung inside 0011/0015/0016/0017/0018/0021/0023 · touch entry
mechanics or safeguards (0023/#414's domain) · flip anything (M1-d is the operator's) ·
build embeddings (0018 G1's H2 call stands) · add commands (sections only).

## 8. Fork list (operator) + recommendations

- **F1 — the composition model**: judge-owns-catalyst / axes-own-context-credit, composed
  arithmetically outside the judge (§3). *Rec: YES — it's the meta-rubric memory realized,
  kills the double-count, keeps every contribution legible. Alternative (axes as payload text
  only) loses calibration — rejected in §3.*
- **F2 — stacking cap**: net −1..+1 tier-step total across ALL axes. *Rec: yes (0016's
  default); revisit only with M2 evidence.*
- **F3 — M1 flip scope**: theme axis ONLY (+ the has_direct_source cache fix as payload
  correctness); structure/gap/neg/chart at M2+ off the same harness. *Rec: yes — core-first
  per #335; smallest signed step.*
- **F4 — ladder registry**: light registry table + weekly-review Authority-map section;
  existing toggles stay the mechanism. *Rec: yes.*
- **F5 — ensemble divergence consumer**: conviction-sizing/abstain lane only, never tier
  (0018 §6 as designed). *Rec: affirm.*
- **F6 — mgmt-judge payload adoption**: 0017's C2 builds its payload as DecisionContext
  blocks from day one (shared renderers). *Rec: yes — free coherence, no schedule change.*

## 9. Sign-off
- [x] ADR accepted (integration architecture + fork list): **operator, 2026-07-07 — all 6 forks per the recs (F1 composition split · F2 net ±1 cap · F3 M1 theme-only · F4 registry+section · F5 ensemble→sizing · F6 C2 adopts DecisionContext)**
