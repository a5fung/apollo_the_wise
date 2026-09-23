# ADR 0025 — Theme fragmentation controls (#274: dissolve-on-flagged-pair + thesis-coherence merge)

**Date**: 2026-07-11
**Status**: **BUILT DARK (C1–C3, 2026-07-12) — awaiting the corpus-gated go-live flip.** F1–F3
operator-SIGNED 7/12; the §3 replay (C4) PASSED 7/11. Cards C1–C3 are in the code behind
`THEME_MERGE_ARM` (**default OFF** — the flip is a separate operator decision AFTER the T2b golden
corpus passes on prod; see the change log). No money touches this — themes feed only the shadow
judge theme-axis (#328) and the briefs.
**Authors**: Fable (operator-triggered weekend block, 2026-07-11)
**Relates**: ADR 0007 (discovery sensitivity — the flood's *deliberate* upstream cause; its §3
anti-noise metric governs this ADR), #125 description guard, #126 coherence guard (data-gated),
evidence pack `docs/analysis/theme_fragmentation_evidence_274_2026-07-08.md`.

## 1. Context — the problem is precision, not a regression

Discovery sensitivity was deliberately raised (ADR 0007) to fix the nascent-MISS (drone cohort).
The shipped guards (Pass1 `MIN_SHARED_FOR_MERGE=3` merge `theme_engine.py:252,3620` · Pass1.5
subset absorption `:3776` · #125 description-quality cap `:1872`) all run — but none is *designed*
to reduce coherent, thin, ticker-DISJOINT near-duplicates. Result (7/8 evidence, re-confirmed 7/10
at 79 active / 51 Nascent): **27/63 themes are 2-member (43%)**; **7 sector-families hold 40
themes with ZERO or near-zero shared tickers** — structurally unreachable by any shared-ticker
threshold. The L2 `theme_count_active` anomaly (79 vs 40 median) will fire daily until precision
ships. This ADR is the precision half that ADR 0007 always assumed would follow.

## 2. Decision — two arms shipped, one explicitly re-rejected

### Arm A (L1) — dissolve-on-flagged-pair (evidence-triggered, narrow, pure-signal)

**Rule:** when `_validate_theme_membership` removes a member from a theme whose active member
count is 2 (i.e. the removal leaves 1), the theme **dissolves** — synthetic Retired row via the
existing engine-drop path (`theme_auto_retired` audit, `parent_theme=NULL`), survivor ticker
released to the discovery pools next run. Plus a **retro-sweep** on each nightly run: any active
2-member theme where a member carries a live validation-cooldown *from that same theme*
(`add_validation_cooldown` history, `:1794`) dissolves the same way.

- Fires ONLY on validation *evidence* (an LLM-adjudicated removal), never a bare count — the
  asymmetric-safety rule from the evidence pack. Current surface: 7 themes.
- Interaction guard: the dissolve writes the same 14d (ticker, theme) cooldown rows so the pair
  can't instantly re-form; the *survivor* gets NO cooldown (it did nothing wrong — it re-enters
  discovery and can join a real theme).
- **Not touched:** `PRUNE_MIN_TICKERS=2` stays (pruning ≠ validation; RS-decay pruning of a
  2-member theme already has its own path).

### Arm B (L2b) — thesis-coherence merge arm (the highest-leverage mechanism)

The operator-visible near-dups (8 insurance, 8 REIT, 7 quantum/AI-silicon…) are ticker-disjoint,
so the merge must key on **thesis**, not ticker overlap. Two stages, mirroring the discovery
discipline (deterministic candidate generation → LLM adjudication → mechanical merge):

**Stage A — candidate pairing (deterministic, cheap, nightly after Pass1.5):**
propose (A,B) as a merge-candidate pair iff ALL of:
1. Same dominant sector-family: majority-member sector (via the existing `mi_ticker_overrides` /
   `get_sectors_batch` enrichment) matches, OR name/description share a domain keyword-stem
   (insurance/REIT/quantum/…, a small curated stem list — Stage A only *proposes*; precision
   lives in Stage B).
2. At least one of the pair has **<4 members**, OR the pair's family cluster holds ≥3 active
   themes (the evidence shows the operator-visible dup families — 8 insurance, 8 REIT, 7
   quantum — include 4-8-member themes a bare <4 cap would never pair; a ≥3-theme family is
   itself the fragmentation signal). Two established ≥4-member themes in a 2-theme family are
   still never auto-paired (that's a legitimate parallel pair, not a flood).
3. Neither theme is a sub-theme of the other (existing parent/sub coexistence stays, `:3700`),
   and the pair has no live `merge_distinct` cooldown (below).
Cap: ≤8 pairs adjudicated per night (cost + blast-radius bound).

**Stage B — thesis adjudication (LLM, the same rigor as validation):**
one call per pair (Haiku, `_VALIDATION_SEMAPHORE`, retry-once-on-429 — the validation
plumbing), tool-schema with required first field `analysis_scratchpad` (house discipline).
Input: both names, descriptions, member lists with sectors + 1-line RS context. Output verdict:
- **MERGE** — one thesis, one driver: emit merged name + which description survives. The engine
  then merges mechanically: union members → winner = higher-scoring theme → absorbed theme gets
  the synthetic-Retired row with `parent_theme=successor` (the Pass1 audit shape) → the merged
  theme immediately runs post-assignment validation (birth-validation style, `#266`) so a bad
  union self-corrects the same night.
- **DISTINCT** — genuine sub-industries: write a `(A,B)` **`merge_distinct` cooldown (30d)** so
  the pair isn't re-adjudicated nightly (idempotence + cost). Audit `theme_merge_distinct`.
- **PARENT_CHILD** — one is a sub-theme: wire via the existing sub-theme machinery
  (`MAX_THEMES_PER_STOCK=2` already supports primary+sub), no dissolution.

**Prompt anchors (load-bearing):** the adjudicator prompt MUST carry negative exemplars — “P&C
underwriters vs specialty-catastrophe underwriters = DISTINCT”, “office vs multifamily REITs =
DISTINCT” — and the instruction *merge on shared DRIVER/catalyst, never on sector label*. The
evidence pack's legit-kill table is the exemplar source.

**Churn/blast-radius rails:** ≤3 executed merges per night · every merge Telegrams in the morning
brief info banner + `theme_thesis_merged` audit · a merged theme that validation immediately
guts (post-merge survivor count < 2) auto-dissolves via Arm A — the arms compose.

### Arm C (L3) — birth min-member floor: **REJECTED again, with the re-open gate named**

The flat floor stays rejected (`theme_engine.py:1872` decision: description-guard-not-cap; the
26-theme corpus showed only ~27% noise). **Re-open ONLY if**: ≥14 days after Arms A+B are live,
`validated themes/day` (the ADR 0007 §3 metric — themes FORMED+validated, not candidates) still
runs >1.5× the 40-theme median **and** the 2-member share stays >35%. That condition is wired as
a data-gated review (below), not left to memory.

## 3. Validation — the offline replay IS the backtest (same-day, no live risk)

`scripts/probes/_274_merge_replay.py` (read-only, runs on the cached 7/8 JSONs + live DB
read-only): Stage A pairing over the 63-theme cohort → Stage B adjudication → print the full
proposed action list (merge/distinct/parent-child per pair, with scratchpads). **Acceptance:**
- The 7 insurance/REIT/quantum families collapse toward ~1-2 themes each (expected net ~-25 to
  -33 themes) — the L2 anomaly's arithmetic resolves.
- ZERO merges across the legit-kill anchors (P&C vs specialty-cat; office vs multifamily) — if
  any fires, the prompt iterates before sign-off.
- Arm A list = exactly the 7 evidence-pack themes (deterministic check).
Operator reviews the printed action list = the sign-off artifact (this is the flip gate).

## 4. Rollout + the built-in go-live/measure trigger

1. Cards build behind `THEME_MERGE_ARM` env/runtime toggle, default **on at merge** *after* the
   §3 replay is operator-signed (no dark period — no-money surface, evidence pre-validated).
2. Post-ship measurement (the "did it work" trigger, wired at ship time — not left to memory):
   data-gated review `theme_fragmentation_resolution` — predicate: `theme_count_active` 7d-median
   ≤ 55 AND 2-member share ≤ 30%; earliest 14d post-ship; on ready → close #274, retire the L2
   anomaly watch; on 14d-overdue-unmet → the Arm-C re-open gate (above) fires as the fork.
3. SSoT: this ADR is the theme-engine merge SSoT; CHANGE_PROCESS entry on the flip commit;
   CLAUDE.md theme-engine section gets 2 lines (merge arm + dissolve rule) same commit.

## 5. Card decomposition (Opus/Sonnet-executable)

- **C1 — Arm A dissolve + retro-sweep** (theme_engine validation path + nightly sweep; audits;
  6 tests: dissolve-on-removal-at-2 · survivor-released-no-cooldown · retro-sweep hits the 7 ·
  ≥3-member removal does NOT dissolve · cooldown rows written · composes-with-merge).
- **C2 — Stage A pairing** (pure function over active themes + sector enrichment; pair caps,
  cooldown filter; 5 tests incl. never-pair-two-established + cooldown-respected).
- **C3 — Stage B adjudicator + mechanical merge** (prompt w/ negative exemplars; tool schema
  scratchpad-first; merge mechanics reusing Pass1 audit/retire shapes + post-merge validation;
  7 tests incl. distinct-writes-cooldown + merge-cap + parent-child-routes-to-subtheme).
- **C4 — replay probe + review wiring** (`_274_merge_replay.py`; the `theme_fragmentation_resolution`
  gated review; brief banner line). Runs before C1-C3 flip; its output is the sign-off doc.

**Sequencing:** C4-replay (with C2/C3 logic imported pure) → operator sign-off → C1-C3 live in one
deploy → the gated review measures. Estimated: C1 small, C2 small, C3 medium, C4 small.

## 6. Change log

### 2026-07-12 — C1–C3 BUILT, DARK, behind `THEME_MERGE_ARM` (default OFF)

Built by Fable post-F1–F3 sign-off (7/12 sitting). **Toggle-OFF = byte-identical current
behavior** (every arm entry point checks `merge_arm_enabled()` first; all pre-existing theme
tests pass unchanged; new toggle-off pins in the three test files below). **The flip is the
operator's, gated on the corpus (below) — never flip in code.**

- **Where the code lives:** `agents/market_intelligence/theme_merge_arm.py` (toggle + Stage-A
  pure pairing + Stage-B adjudicator — the replay's pure logic EXTRACTED, not re-implemented;
  the C4 probe now imports from it, one copy) · `theme_engine.py` (Arm A in-run dissolve in
  `_validate_theme_membership`/`_rescore_existing_theme`, `_retro_sweep_flagged_pairs`,
  `_run_thesis_merge_pass`) · `db.py` (`mi_theme_merge_cooldowns` + helpers) · `briefing.py`
  (morning-brief merge banner, the §2 rail).
- **Go-live gate wired:** `scripts/evals/run_theme_merge_corpus_eval.py` runs the REAL
  adjudicator over `theme_merge_corpus_v1.json`; bars = hard pairs 100%, others ≥85%. A green
  run regenerates `scripts/evals/theme_merge_eval_pass_record.json` (pins corpus_sha1 +
  prompt/tool-schema sha1 + model); `tests/test_theme_merge_corpus_gate.py` REDs CI on a
  failing/stale record and skips-loudly while none exists. **Flip forbidden without a passing
  record.** (Candidate for a [5m/7]-style deploy preflight later; the CI pin is the gate now.)
- **§4 deviation (operator-directed at build):** ships **default OFF** (not "on at merge") —
  the flip is a separate operator decision after the corpus passes on prod.
- **Deliberate build choices vs the design text:** (1) Stage-A gate-1's majority-sector
  OR-branch is a FALLBACK for stem-less themes only, and stem families consume the ≤8 pair
  budget first — protects the replay-validated surface from broad FMP sector families;
  (2) Stage-B input carries names/descriptions/member-lists-with-sectors but NO RS-context
  line (the signed replay ran without it; the corpus is the arbiter); (3) Stage-B upgraded
  from the replay's JSON-prompt to the house tool-schema (scratchpad-first, temp=0,
  parse-retry — the C4 determinize caveat), with F1 `merged_name` (+ name-collision guard)
  and a PARENT_CHILD `child` field; (4) a merge gutted by post-merge validation counts
  against the ≤3/night cap (it consumed the night's action).
- **Audits added:** `theme_dissolved_flagged_pair` · `theme_merge_pairs_proposed` ·
  `theme_merge_distinct` · `theme_merge_parent_child` · `theme_thesis_merged` ·
  `theme_merge_cap_deferred` · `theme_merge_dissolved_post_validation` ·
  `theme_merge_adjudication_error` · `theme_merge_arm_error`.
- **Tests:** `tests/test_theme_dissolve_arm.py` (C1) · `tests/test_theme_merge_arm.py` (C2 +
  adjudicator pins) · `tests/test_theme_thesis_merge_pass.py` (C3 executor) ·
  `tests/test_theme_merge_corpus_gate.py` (gate). Full suite green at build.
- **Still owed at the FLIP commit (not before):** the `theme_fragmentation_resolution` gated
  review in `data_gated_reviews.yaml` (§4.2 — its 14d clock starts at flip), the CLAUDE.md
  2-line theme-engine pointer (§4.3), and the CHANGE_PROCESS entry.

## 7. Operator forks — ALL SIGNED as recommended (7/12 sitting; kept for the record)

- **F1 — merged-theme naming:** adjudicator proposes the merged name (rec: keep the
  higher-scoring theme's name unless the adjudicator flags both as sub-optimal and offers a
  family name — rec = adjudicator-proposed, it has both descriptions in hand).
- **F2 — Stage-A pair scope:** rec = as designed (one side <4 members). Alternative (any-size
  pairing) reaches P&C-vs-specialty-scale collapses — explicitly NOT recommended (legit-kill).
- **F3 — ship Arm A independently if B's replay needs prompt iteration?** rec = yes (A is
  evidence-pure and unblocks the 7 worst); B follows when its replay is clean.
