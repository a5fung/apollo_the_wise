# ADR 0032 — Theme ecosystems (primary → sub-theme hierarchy)

**Date:** 2026-07-14 · **Status:** ACCEPTED (operator-signed the four decisions 2026-07-14) ·
**Supersedes/extends:** ADR 0025 (theme-fragmentation controls) — this is its surfacing/aggregation layer.
**Evidence:** `docs/analysis/theme_ecosystem_litmus_design_2026-07-14.md` (Fable-run, Opus-verified —
every load-bearing claim re-checked against prod on 2026-07-14).

## Context

Borrowed from Marios Stamatoudis (@stamatoudism), the trader whose theme methodology Apollo already
mirrors. His UI is a **two-level hierarchy: ECOSYSTEM (E-\*) → sub-THEMES (T-\*)** — his Cybersecurity
ecosystem ranks #2 overall with a score *inherited/boosted from its 6 sub-themes*. His stated ground
truth: cybersecurity + its sub-themes have dominated his lists for weeks/months and were resilient
through June. We used that as a **litmus test** for Apollo's theme engine over the past month.

**Litmus verdict (verified):**
- **Detection PASS** — the cyber cohort RS ran 75 → 62 (June dip) → 89; Apollo's one cyber theme
  (`Network Security & Zero-Trust Edge`) is its **#1 theme by member RS** (11 of 12 members ≥96).
  Apollo's raw signal saw exactly what Marios saw, dip and recovery included.
- **Surfacing FAIL — three verified mechanisms:** (1) the theme count exploded ~40 → 65, so cyber is
  one unmarked line among ~63; (2) `/themes` renders **Mainstream last** (`agent.py:4411`
  `["Accelerating","Nascent","Mainstream"]`) — below ~15 Nascent 2-member noise themes — while the
  scorecard disagrees (`briefing.py:710`); (3) during the June dip cyber went `Fading` and collapsed
  into a names-only footnote for 4 sessions.
- **The smoking gun (verified in `mi_audit_log`):** the engine's own discovery advisor **twice
  proposed Marios's exact vuln-mgmt sub-theme** — 7/07 (`Cyber Vulnerability Management & Exposure
  Platforms`, TENB/RPD/QLYS — literally his global-#3 trio) and 7/13 (adds VRNS) — and **both were
  killed by Pass1 protect-strip** (members stripped to protect the 12-name incumbent blob → theme
  died empty). The engine *wants* the granularity Marios has and is actively suppressing it.
- **Also verified:** NET (RS 97) and S (RS 96) — two elite cyber names — were in **zero themes all
  month** (member-coverage leak); the "15-theme June baseline" was a broken-discovery artifact
  (0 `theme_discovered` events 5/11–6/21, fixed by `482dc50`); ~40% of active themes are 2-member noise.

Net: Apollo detects dominance perfectly and surfaces it as one buried line in a fragmented flat list —
no ecosystem aggregation, no sub-theme structure, and machinery that kills the sub-themes it discovers.
Themes are a **no-money detection surface** (they feed briefs + the shadow-judge theme-axis only), but
the **ecosystem taxonomy and the score formula are operator-signed methodology** — hence this ADR.

## Decision

Add a **two-level surface mirroring Marios: ECOSYSTEM (E-\*) over sub-THEMES (T-\*).** Themes stay the
unit of discovery/validation/lifecycle; **ecosystems are a read-model + score aggregate**, not a new
lifecycle object. Four operator-signed decisions:

**D1 — Curated taxonomy + automated discovery of new ecosystems.**
- A **curated ~18-bucket taxonomy** (repo/DB-owned) is the stable ranking axis (emergent nightly
  re-clustering would re-introduce at E-level the churn ADR 0025 fights at T-level). Proposed buckets:
  E-CYBR, E-AISEMI, E-AIINFRA, E-SAAS, E-BIO, E-MEDTECH, E-INS, E-BANKFIN, E-REIT, E-ENER, E-METAL,
  E-DEF, E-TRANS, E-CONS, E-INDL, E-CRYPTO, E-COMM, E-HLTH + reserved **E-UNASSIGNED**.
- **Curated ≠ frozen.** `E-UNASSIGNED` is the **discovery substrate**: themes that map to no bucket
  accumulate there. A **weekly ecosystem-discovery pass** clusters them; when a coherent cluster forms
  (**≥3 themes, shared thesis + ticker overlap, sustained ≥2 weeks**), an LLM proposes a *new primary
  ecosystem* (code/name/description/keyword-stems) with evidence. Bottom-up preserved — a new primary
  theme rises from price action, never from a hypothesis.
- **Promotion = auto with a grace-period opt-out** (operator's refinement, 2026-07-14; fits the
  no-money default-to-ship posture): a qualifying proposal **auto-promotes into a `pending` grace
  state**, notifies the operator with a **one-tap veto** (carries the action, `/promotetheme` idiom):
  *"🆕 New ecosystem auto-promoting in 48h: E-DRONE … [🚫 Veto]"*. No veto → live at grace-end (themes
  remap `E-UNASSIGNED → E-<new>`). Veto → rejected, themes stay unassigned, **30-day cooldown**
  (re-surfaces early only if the cluster materially strengthens). Auto-promoted ecosystems are
  **marked 🆕/auto** and listed for a window so the operator can retire one retroactively. Defaults:
  **grace 48h** (spans 2 briefs), **cooldown 30d** (tunable). Taxonomy mutations are audited + reversible.

**D2 — Scope: group AND re-granularize deep ecosystems (re-granularization REQUIRED, not optional).**
Grouping alone clears the *headline* litmus, but only because cyber's blob is itself elite — with
depth=1 the boost/nested-view/resilience signal (the actual Marios borrow) are vacuous. And the engine
already proposes the correct splits (the smoking gun). So we **stop killing them**: route Pass1
protect-strip conflicts where a newborn is a coherent subset of one protected parent to the
**already-built ADR-0025 Arm-B PARENT_CHILD adjudicator** → on PARENT_CHILD, persist the child with
`parent_theme=<parent>` + register in `sub_theme_parents` (the coexistence carve-out then protects it).
Plus a bounded deliberate-split trigger for a sole-sub-theme *ecosystem-dominant* theme (≥10 members,
≥8 RS-80+). Acceptance fixture: the two killed vuln-mgmt births (7/07, 7/13) must survive as `T-`
children of the cyber theme when replayed.

**D3 — Ecosystem score: member-union breadth-weighted (anti-fragmentation).**
```
members(E) = dedup union of tickers across E's active non-Fading sub-themes
raw(E)     = trimmed_mean(rs_composite of members(E))            # 0-100, uses rs_composite directly
strong(E)  = |{m ∈ members(E) : rs_composite ≥ 80}|
depth(E)   = |{T ∈ E : T has ≥3 members (or elite pair) AND theme comp ≥ 85}|
boost(E)   = 0                          if strong(E) < 5          # thin-ecosystem floor
           = min(0.30, 0.04·depth(E) + 0.015·strong(E))          otherwise
boosted(E) = raw(E) × (1 + boost(E))    # display raw → boosted (Δ), Marios-style
```
Deduped **member-union** is the base so fragmentation adds no members — splitting a cohort into 8
near-dups cannot raise `raw`/`strong` (the anti-gaming property max/sum/theme-count formulas lack; on
today's data a naive count-boost ranks Insurance's 8 fragments above cyber's 1 blob — the failure mode
this avoids). `depth` reproduces the "inherited from Themes" pop once sub-themes exist; the `strong<5`
floor blocks a 2-member RS-99 micro-theme masquerading as an ecosystem. **Constants
(0.30/0.04/0.015/5/85) are illustrative pins — they get the CHANGE_PROCESS N≥10 backtest before any
live flip.** Uses member `rs_composite` directly, NOT the stored `score` column (which mixes an
80-cap native scale with a 0-100 `rs_avg` scale on promoted rows — a verified landmine).

**D4 — Companion flip: `THEME_MERGE_ARM` ON (ADR 0025, corpus-cleared 14/14).**
The ecosystem design depends on it for a trustworthy `depth()` and a sane nested list; without it the
E-layer would hide the 40% 2-member noise rather than resolve it. Its `theme_fragmentation_resolution`
gated review (count ≤55, 2-member share ≤30%) is the precondition for trusting `depth`.

## Mechanics — reuse vs new

**Reuse (verified in code):** `parent_theme` column + `sub_theme_parents` + merge coexistence carve-out
(`theme_engine.py:3762`) + `MAX_THEMES_PER_STOCK=2`; `_split_fat_theme` (its *trigger* >20 is the only
wrong part); ADR-0025 Arm-B PARENT_CHILD verdict; `_compute_scored_themes` (`briefing.py:632`) for the
aggregate. Caveat: `parent_theme` is overloaded (successor pointer on synthetic Retired rows) — document
the active-row semantic or split the column at build time.

**New:** `mi_theme_ecosystems(theme_name, e_code, method, assigned_at)` mapping (Haiku-assigned at birth
+ backfill, `analysis_scratchpad`-first, fallback `E-UNASSIGNED`); the curated taxonomy store (YAML/DB);
the weekly discovery + auto-promote/veto lane; `/themes` v2 (ecosystems ranked by boosted score →
sub-themes nested with global theme rank, Fading shown struck-through *inside* its ecosystem, stage as a
per-line tag — drops the Mainstream-last grouping that buries the strongest mature theme).

## Gates & phasing

- **Phase 1 (ships full — no money):** taxonomy + `mi_theme_ecosystems` mapping + backfill; ecosystem
  score (D3) as a read-model; `/themes` v2 + the `agent.py:4411` stage-order fix. Read-only aggregation.
- **Phase 2 (N≥10-gated):** re-granularization (D2) — the PARENT_CHILD routing + the bounded split
  trigger thresholds get the CHANGE_PROCESS N≥10 backtest before flip; acceptance fixture = the two
  killed vuln-mgmt births survive as children.
- **Phase 3:** the discovery + auto-promote/veto lane (D1) — auto-promote is default-on, so it ships
  once the veto surface + cooldown + audit are verified live.
- **Companion:** flip `THEME_MERGE_ARM` (D4) — operator-gated, corpus-cleared, sequenced with Phase 1.
- **Smaller calls surfaced (operator-scoped):** promotion-lane floor (44 shadow-promoted births/4wk,
  some rs_avg ≤26); CYBR missing from the RS universe; NET/S unthemed (assignment probe); the
  `parent_theme` double-semantic doc/column split.

## Consequences

**Positive:** the dominant cohort surfaces as a ranked ecosystem (cyber #1–2 of ~15–18) instead of a
buried line; the sub-theme readout Marios has becomes possible; the engine stops killing its own
discoveries; the flat 65-line board collapses to ~15–18 ranked ecosystems; new primary narratives
still rise bottom-up (auto-discovery) under operator oversight (veto). **Risks/mitigations:** taxonomy
drift → curated + high discovery bar + veto + audit/reversibility; formula overfit → N≥10 gate on
constants; auto-promote noise → grace + cooldown + retroactive retire; re-granularization regressions →
0025 adjudicator is corpus-cleared + the acceptance fixture. **THE LINE:** untouched — no money path,
no strategy/sizing/safeguard; the theme-axis into the shadow judge stays shadow.

## References
- `docs/analysis/theme_ecosystem_litmus_design_2026-07-14.md` (full diagnostic + verified evidence)
- ADR 0025 (theme-fragmentation controls — `THEME_MERGE_ARM`, PARENT_CHILD adjudicator)
- `docs/setups/CHANGE_PROCESS.md` (N≥10 backtest, SSoT-in-same-commit, sign-off on drop/merge)
