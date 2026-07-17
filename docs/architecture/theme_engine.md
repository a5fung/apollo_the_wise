# Theme Engine — architecture notes

> SSoT for theme-engine behavior rules. Moved verbatim from CLAUDE.md
> 2026-07-16 (#417 doc-backfill) — update THIS file in the same commit as any
> behavior change. The exclusions rule + recency cap stay inline in CLAUDE.md.
> Ecosystem layer (ADR 0032): docs/decisions/0032-theme-ecosystems.md; Phase 2-3
> design: docs/analysis/theme_ecosystem_phase23_design_2026-07-14.md.

- Bottom-up from price action — themes emerge from RS, not hypotheses
- Lifecycle: Nascent → Accelerating → Mainstream → Fading → Retired (5 fading days)
- **Engine-drop themes skip Fading**: Pass1 cap_drop / Pass1.5 absorption removals get a synthetic Retired row (`theme_auto_retired` audit; `parent_theme=successor` recovered from the pass audit events) — the 5-day Fading→Retired path can't complete under the 7d recency cap. Stub until canonicalization (R3).
- **Validation**: `_validate_theme_membership()` runs Mon/Wed/Fri. `_extract_json_object()` is depth-aware (handles nested JSON Haiku appends). Concurrency capped via `_VALIDATION_SEMAPHORE(2)` + retry-once on 429.
- **`mi_theme_exclusions`**: user-directed permanent bans ONLY. NOT auto-populated from validation removals (deliberately — a bad-description removal once permanently banned TSEM from semiconductor theme).
- **Fading themes**: tickers from Fading themes ARE in `covered_tickers` — prevents validation-removed stocks appearing as uncovered in the same run.
- **Post-assignment validation**: immediately validates newly assigned stocks (don't wait for Mon/Wed/Fri).
- **Birth validation (#266, 2026-06-17, operator-signed)**: newly DISCOVERED themes run the SAME `_validate_theme_membership` on their founding members before `_save_themes` — discovery previously skipped it, so bad members sat ~6d until the next Mon/Wed/Fri (evidence: `docs/analysis/theme_birth_validation_evidence_2026-06-17.md`). Changes WHEN, not WHAT; min-survivor guard keeps small/born-bad themes intact; emits `theme_birth_validated`.
- **Tool schemas**: all three tools (assignment, discovery, split) have `analysis_scratchpad` as required first field — forces reasoning before JSON output.
- **Unknown sector fallback**: when sector is "Unknown", checks description keyword overlap (4+ letter words) before allowing assignment.
- **Description chunking**: `_ensure_descriptions()` sends max 15 tickers per Haiku call.
- **`get_active_themes(stale_after_days=7)`**: recency cap is the de-facto retirement mechanism — themes that stop appearing in daily snapshots age out after a week.
- **Phase 2 re-granularization (ADR 0032, behind `THEME_SUBTHEME_ARM` DB toggle, fail-closed OFF)**: Route A protect-strip→PARENT_CHILD adjudication (inert on DISTINCT verdicts — fail-closed to today's strip) + Route B sole-sub-theme ecosystem-dominant split via `_split_fat_theme` (self-disarms: post-split the ecosystem has 2 themes). Split children persist via `parent_theme` (rebuilt into `sub_theme_parents` each run); covered-ticker exclusion keeps split-offs out of the discovery pool.

## Change log

### 2026-07-17 — biotech sector-cap 0 → PER-FAMILY (#476, operator-signed)
- **What**: `_SECTOR_KEYWORD_GROUPS` biotech entry `max_themes 0 → PER_FAMILY_CAP`
  (one keyword-theme slot per Stage-A stem family via `theme_merge_arm.family_of`;
  unstemmed names share one slot; ≤6 effective). Family-keyed slots make
  cross-family blind absorption structurally impossible.
- **Why the prior rule was wrong (not just incomplete)**: cap-0 ("exclude
  entirely", 2026-03-20) silently deleted every biotech-named theme in Pass 2
  (the bare-else drop, no audit for 4 months) while `promote_shadow_themes`
  resurrected the same cohort nightly — an infinite churn loop that orphaned an
  RS-elite cohort (12 names RS 85-98 homeless). The RS side had already walked
  back ITS biotech filter because the cohort is elite; the theme side never did
  — the rule was internally inconsistent with the system's own beliefs.
- **Evidence**: diagnosis `docs/analysis/476_biotech_crystallization_diagnosis_2026-07-17.md`;
  $0 replay backtest `docs/analysis/476_optionA_backtest_2026-07-16.md` (48
  killed cuts / 35d, 24-cell grid): convergence via Pass-1 (≥0.6 containment
  subsumes the replay's 0.8 rule — no new canonicalization code needed), mush
  guard clean everywhere, cap-2-global rejected (5-6 real lineages; per-family
  calibrated). Operator ruled Option A 7/16, signed the calibrated per-family
  cell 7/17.
- **Reversion flag**: single-line revert (`PER_FAMILY_CAP → 0`) restores the
  old exclusion exactly.
- **Forward verify**: ≥10/12 of the elite cohort covered within 5 nightly runs
  (the assignment pass homes the rest once stable biotech themes exist);
  `theme_sector_cap_dropped` / the board's E-BIO section are the watch surfaces.
