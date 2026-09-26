# Theme Engine — architecture notes

> SSoT for theme-engine behavior rules. Moved verbatim from CLAUDE.md
> 2026-07-16 (#417 doc-backfill) — update THIS file in the same commit as any
> behavior change. The exclusions rule + recency cap stay inline in CLAUDE.md.
> Ecosystem layer (ADR 0032): docs/decisions/0032-theme-ecosystems.md; Phase 2-3
> design: docs/analysis/theme_ecosystem_phase23_design_2026-07-14.md.

- Bottom-up from price action — themes emerge from RS, not hypotheses
- Lifecycle: Nascent → Accelerating → Mainstream → Fading → Retired (5 fading days)
- **Engine-drop themes skip Fading**: Pass1 cap_drop / Pass1.5 absorption removals get a synthetic Retired row (`theme_auto_retired` audit; `parent_theme=successor` recovered from the pass audit events) — the 5-day Fading→Retired path can't complete under the 7d recency cap. Stub until canonicalization (R3).
- **Validation**: `_validate_theme_membership()` runs Mon/Wed/Fri. `_extract_json_object()` is depth-aware (handles nested JSON Haiku appends). Concurrency capped via `_VALIDATION_SEMAPHORE(2)` + retry-once on 429. **Thesis-aware since #368 (2026-08-04)**: all three callers (rescore, #266 birth validation, Arm-B post-merge) pass the theme's own description; the prompt shows it and instructs judging against the THESIS, not the name alone — a member whose CURRENT driver matches the thesis stays even when its legacy industry label differs (the 7/27 WULF/CORZ eviction class). `_is_garbage` theses are omitted.
- **Member pruning (#368, 2026-08-04 — rising-recovery hold; rising test repaired 2026-08-26)**: hard prune (RS<25, 1 day) and soft prune (RS<35, 3 consecutive days) both SKIP a member whose RS is RISING over the last `PRUNE_HOLD_WINDOW_SESSIONS` (6) sessions. `_rs_rising` requires **at least `PRUNE_HOLD_MIN_POINTS` (4) DATA POINTS of history** — NOT a rise of 4 RS points (RS 1.8 → 3.1 qualifies; the constant's name is ambiguous and was misread once on 2026-08-04) — and now **TWO** conditions: (1) `hist[0] > hist[-1]` (newest above oldest, the original test) **AND** (2) `hist[0] >= min(hist[1:-1])` — today is not below EVERY intermediate reading. **Why (2) exists**: (1) alone compares two ENDPOINTS and is blind to everything between, so a collapse whose oldest reading happens to be a one-day trough scored as rising — BLDR on 2026-08-25 read `[10.0, 13.8, 25.7, 29.4, 29.2, 5.9]`, a 29 → 10 collapse, held/flagged as rising purely because `10.0 > 5.9`. The oldest point is the value being compared AGAINST, so it is excluded from the floor (`hist[1:-1]`, never `hist[1:]`, which would make the clause vacuous). Short history ⇒ no hold, prune as before. Mirrors the birth gate's derived level-OR-rising cell on the retention surface; changelog type `ticker_prune_held_rising`. Backtest: 77% of rising-held names recovered to RS≥50 in 10 sessions vs 31% of the falling control (N=13 scored / 25 held, `docs/analysis/368_crypto_ai_consolidation_2026-08-04.md`).
- **Retire streak counts WEAK-Fading rows only (#368, 2026-08-04)**: `_count_consecutive_fading` counts Fading rows with `rs_avg IS NULL` (the weak branch's); a Fading row WITH rs_avg (score-delta fade / hysteresis-held recovery — the strong floor passed that day) BREAKS the 5-day retire streak. Evidence: the crypto-miner lineage re-qualified healthy 8/03 (elite pair, rs_avg 84.9) yet retired 8/04 off the held row; 14 retirements in Jun–Aug carried a healthy-held row in their terminal streak ('AI Memory & Storage': six of its last eight days).
- **Nightly THEME QUALITY check (#531, 2026-08-04, `health_checks.run_theme_quality_check`, wired into `_post_nightly_audit_job`)**: the regression guard that keeps F2/F3 above working — a theme retiring while its last-known state was healthy (Fading, `rs_avg` populated, then a silent vanish — no explicit `mi_themes` row) or a member pruned while its RS was rising over the F3 hold window. Measured against 97 real trading days before shipping: 6/165 retirement incidents and 25/164 prune-shaped exits, both hand-verified real (79% of rising-held exits recovered to RS≥50 in 10 sessions vs 36% falling control). Deliberately does NOT fire on the ADR-0025 Arm-A 2-member dissolve shape or a Pass1/1.5 engine-drop retirement (different mechanisms, F2 doesn't touch them — the latter is a named, measured gap: 4 occurrences in the window, e.g. 'AI Memory & Storage' 07-13, filed as a future candidate). Fragmentation and churn signatures were ALSO measured (251 firings/122 pairs; 42/301 short-lived names) and DROPPED as too noisy / needing neighbourhood-clustering work not yet built — full measurement + both-ways proof in `docs/analysis/531_theme_quality_measurement_2026-08-04.md`. Dedupe (audit-log-based, permanent per finding, fails open) mirrors `run_inert_sweep_check`'s idiom.
- **⛔ Arm-B Stage-A family `compute_infra` (#368) — BUILT, GATED, NOT SHIPPED (2026-08-04)**: the crypto-mining and AI-datacenter framings of one physical asset base never share a stem family, and the majority-sector fallback cannot form for converting miners (FMP splits them Financial Services / Technology / blank) — so **ZERO crypto pairs have EVER been proposed for adjudication** (verified: 0 of 99 merge events mention crypto or bitcoin, while insurance and fintech pairs ran nightly). The family that fixes that was written and then HELD, because its own pre-deploy gate ran the two frozen historical pairs through the REAL Stage-B judge and neither consolidates: **P1 (07-21) → DISTINCT** (the gate's stated hold condition) and **P2 (08-04) → PARENT_CHILD**, which on this file's own operator-signed terms is not a consolidation — the v2 prompt ruling (7/12, rulings-pack R3) exists precisely because v1 *"answered PARENT_CHILD to pure slices, which keeps both themes and leaves the fragmentation (#274's whole purpose) unfixed"*. There is also no persistence path for a PARENT_CHILD verdict today: `parent_theme` + `sub_theme_parents` are ADR 0032 Phase 2 = **#471, not built**. So the change is correct and premature. Gated on #471 Phase 2, tracked as #529. The adjudicator's real behaviour here is itself the finding: it consolidates only when the theme's THESIS TEXT names the conversion (P2's thesis said *"not bitcoin price"*; P1's read as a crypto theme with one lease headline) — which makes thesis quality, not stem families, the live lever.
- **Nightly ECOSYSTEM REACTIVATION detector (#534 D3(b), 2026-08-05, `health_checks.run_ecosystem_reactivation_check`, wired into `_post_nightly_audit_job` at 17:30 ET — after the 17:00 engine so tonight's board + ecosystem mappings exist)**: deterministic, $0, no LLM. Fires when a DORMANT ecosystem (no live mapped theme, or all-Fading, judged at the alert window's START session against the strictly-prior board, 7d liveness horizon mirroring `get_active_themes`) collects **≥3 distinct HIGH EP tickers within 5 sessions** against a **quiet 15-session trailing baseline (≤1 mapped ticker)**. Ticker→ecosystem mapping = any non-Retired `mi_themes` membership row (INCLUDING tonight's board — the engine's same-night reactive births are how new wake-up names reach the dormant lineage's e_code; the dead themes never held them) whose name is in `mi_theme_ecosystems`, else taxonomy exemplars; a SECTOR fallback was measured and rejected (it admitted two sector-label pseudo-clusters). Thresholds DERIVED from a 66-session prod replay: one incident total (E-DEF 08-04, {AMRC PLTR TSAT VOYG}, baseline 0) and the ARM+LRCX+SIMO semis earnings night correctly suppressed by the quiet-baseline precondition — the §5 "an earnings surge is not a theme" proof; derivation + hand-checks in `health_checks.py`'s #534 header. Output: operator Telegram line (`E-DEF (Defense & space) reactivating: 4 EPs/1d, no live theme`) + a discovery seed in `mi_theme_candidates_shadow` (source=`ecosystem_reactivation`, cohort in `tickers`, dormant lineage named in the thesis). **NEVER an auto-promote**: the source is excluded from `AUTO_PROMOTE_THEME_SOURCES` (#469 allowlist, by construction) and from the judge's `active_narratives` feed — visible only via operator surfaces (`include_probe=True` → /themes, /promotetheme); the birth gate owns whether a reactivation cohort becomes a theme (pinned by `tests/test_ecosystem_reactivation.py`). Dedupe is audit-log-based but RECENCY-bounded (10d — one announcement per incident; an incident self-terminates in ~5 sessions as its own alerts walk into the baseline, and the same ecosystem may legitimately wake again months later), fails open.
- **#491 M2 — SEEDED ASSIGNMENT-POOL EXEMPTION (2026-08-05, operator-approved D1)**: a ticker named in an ACTIVE Lane-2 narrative row (`narrative_cogap`) or an ecosystem-reactivation seed (`ecosystem_reactivation`, #534/#536), ≤ `LANE2_WINDOW_TRADING_DAYS` (10) trading days old and PRIOR sessions only (tonight's lane rows are written after the assignment pass — scheduler 5c), is admitted to the ASSIGNMENT pool regardless of RS floor and fetch rank, its score row fetched explicitly via `get_rs_for_tickers` (no score row ⇒ skip). Why: RS is a 1/3/6-month lookback, so a business-model pivot is under the floor by construction (B2 — every one of the ten ex-miner names under RS 70 on 08-04 while the correct live AI theme sat 3 members wide). **Fork F-D (operator-ruled): the admission scope is ONLY those two seeded sources — NEVER a raw RS band** (`db.SEEDED_ASSIGN_SOURCES`; scope + the RS-free admission signature pinned by `tests/test_seeded_pool_exemption.py`). Never admitted: covered names any stage incl. Fading (covered-exclusivity/B1 stays M-CORE's territory), just-revalidated-out names, names already in the pool. Downstream walls unchanged (assignment LLM decides fit; global bans, pair cooldowns, post-assignment F4 validation, exclusions all apply — admitted names enter the standard pool); DISCOVERY untouched at top-40. Bounded ~15/night by construction (replay over 06-26→08-05: 45 admissions/28 nights, peak 10); >15 logs a loud warning — never a silent cap. Observability: one `seeded_pool_admission` audit row per run with per-ticker trigger pointers; fetch failure fails OPEN (one night without the exemption, never the run). Known accepted gap: seeded admissions can, like any pool name, be offered [Fading]-tagged themes — §4.4's "never migrate INTO Fading" predicate belongs to the custody verb (M-CORE, not built).
- **#530 (2026-08-09) — the shadow-promote re-mint no longer clobbers an unchanged thesis**: `promote_shadow_themes` / `promote_candidate_by_name` used to write `description = tonight's candidate thesis` UNCONDITIONALLY every time a cohort still qualified (`_upsert_promoted_theme`'s `ON CONFLICT ... DO UPDATE SET description = EXCLUDED.description`, no comparison to what was already on the board). shadow_v2's correlation-lane LLM call re-runs fresh every night regardless of whether the cohort changed, and its thesis is frequently a generic price-correlation blurb ("pure-play Bitcoin miners... corr 0.84") — on a night the LIVE lane doesn't independently re-mint that name, this silently replaced a more specific, catalyst-grounded description already on the board. That mattered beyond tidiness: F4 (#368, line above) judges membership against the theme's own THESIS, so an overwritten thesis actively evicts correct members — the root cause of the WULF/CORZ eviction traced in #491. **Fix** (`theme_engine._resolve_promoted_theme_description`, the ONE decision point both promote paths now share): if tonight's ticker SET is EXACTLY unchanged from the last known `mi_themes` row for that name, the EXISTING description is preserved; a ticker-set CHANGE (any add/remove) is real membership evidence, so the fresh thesis is always allowed through. Mirrors the existing `_canonicalize_theme_names` (#59, 2026-05-11) precedent, which solved the identical churn problem for the theme NAME the same way — freeze on exact ticker-set match, no specificity scoring, no numeric threshold. Pinned by `tests/test_promotetheme.py` (`test_530_*`, 3 tests: unchanged cohort preserves the specific thesis, changed cohort refreshes it, no-prior-row is unaffected).
- **#214 RENAME-INSTEAD-OF-STRIP (2026-08-26, `theme_engine._apply_mass_flag_rename`)**: when membership validation flags the **mass-eviction signature** — `_is_mass_eviction(n_flagged, n_members)` = **>=3 flagged AND >=50% of the membership**, byte-identical to `health_checks._is_mass_eviction` — the theme is **RENAMED to describe the cluster it actually holds**; the members are NOT removed and **no validation cooldown is written**. Prior behaviour deleted the members so they would fit the name, which is backwards: the removals are CORRECT given the name, so the NAME is the defect (that is what the `validation_mass_removal_name_suspect` tripwire has been saying since 2026-06-09). Evidence it recurs: the same energy block tripped the signature **three times in ten days under three different names** — Oilfield Equipment 9/16 (08-17), Independent Oil Refiners **42/42** (08-19, swallowed by the min-survivor guard), Oil Refining & Marketing 17/24 (08-26, 17 regulated utilities + midstream deleted, cooldowns to 09-09), after which the theme refilled to 46 upstream names and re-armed (`docs/analysis/theme_mass_eviction_2026-08-26.md`).
  - **Naming REUSES the existing path** — `_THEME_DISCOVERY_TOOL` (`report_themes`), same `THEME_MODEL`, same #214 breadth contract on its `name` field; only the prompt differs (one existing cohort to name, not a pool to cluster). One forced tool call (`tool_choice=any`, thinking DISABLED), no advisor branch, no retry: ~1 bounded Sonnet call per firing (~3 per 10 days observed). Ceiling `theme_rename` (1750, sized by analogy to `theme_split` — same output shape).
  - **Scoped to the RESCORE caller only** (`mass_flag_out` out-param). The other three `_validate_theme_membership` callers keep stripping, deliberately: **birth validation** (#266 — no lineage to preserve, min-survivor guard already covers born-bad themes), **post-assignment** (the strip is rejecting a bad ASSIGNMENT, not judging the theme's name), **Arm-B post-merge** (that name is the merge pass's own product). Passing no out-dict is byte-identical to pre-2026-08-26.
  - **Ordering inside the validator**: AFTER the operator-protection shield (a set that only reaches >=50% by counting operator-shielded names is not a mass eviction) and BEFORE the min-survivor guard (whose "would drop below 2 survivors -> skip removals" escape silently swallowed the 42/42 flag on 08-19 — the loudest possible name-is-wrong signal must reach the rename).
  - **LOOP CAP — a theme minted by one of these renames is not renamed again for `RENAME_LOOP_CAP_DAYS` (14)**, keyed on the NEW name (`theme_renamed_on_mass_flag` audit rows) so it bounds a CHAIN A->B->C, not just a per-name rate. Fails **CLOSED** (DB error => no rename), asymmetric with the #214 inheritance guard's fail-open on purpose: failing open here costs an unbounded rename loop. On cap exhaustion the theme is **NEITHER renamed NOR stripped** — falling back to a strip would reintroduce the defect — and a `theme_rename_cap_reached` row asks the operator to look. 14 days is the window `_canonicalize_theme_names` (#59) already uses for the analogous name-stability call, and the same 14 days as the cooldown a strip would have written.
  - **IDENTITY — a rename preserves the lineage, it does not mint a new theme.** `mi_themes` is keyed `(theme_date, name)`, so continuity is carried explicitly: (a) `days_active` / `consecutive_accelerating` — `_save_themes` also fetches the OLD name and falls back to it via `renamed_from`, because a reset to Nascent would cost every member the R4 +10 in-theme bonus, i.e. it WOULD change EP scores; (b) stage/age/history — `_get_theme_history` + `_count_consecutive_fading` already fall back to ticker-overlap (Jaccard >= 0.4) and a rename leaves the ticker set untouched, so they resolve at 1.0; (c) the OLD name gets an explicit **Retired tombstone with `parent_theme` = the new name** from the engine-drop pass, so `get_active_themes` stops counting it instead of holding the same cohort under two names for the rest of its 7-day window; (d) `sub_theme_parents` is re-keyed across the rename before `_restore_sub_theme_links`, which matches on names and would otherwise clear the link as a genuine orphan (#471's failure mode); (e) it is reported as a rename, never as a retirement. operator rulings filed under the OLD name follow the rename via the persisted lineage (#601 bullet below — the fuzzy exclusion match does NOT cover a broadening rename), and **nothing is ever written to `mi_theme_exclusions` here**; `mi_theme_ecosystems` re-maps on the next save.
  - ⚠ **`_canonicalize_theme_names` is CARVED OUT, and this is the load-bearing part.** That function renames today's theme back to a prior 14d name on an **exact ticker-set match** — and a #214 rename keeps the ticker set unchanged, which is precisely its trigger. Without the carve-out it reverts every rename the same night and logs it as ordinary `theme_renamed_for_continuity` churn: the fix would pass every test and no-op in production. Two guards: the in-memory `renamed_from` flag (protects today) and `_name_recently_mass_evicted(prior_name)` on the donor (protects every later run, since the old name's rows sit inside the 14d window for two more weeks) — the same rule and the same helper the #214 name-INHERITANCE guard already applies. Consequence worth knowing: **the `validation_mass_removal_name_suspect` tripwire emit is now load-bearing, not decorative** — the rename path writes no `ticker_revalidated_out` rows, so the tripwire is the only pattern `_name_recently_mass_evicted` can still match for that theme. It was deliberately kept ALONGSIDE the rename, never replaced by it.
  - **Refusal paths** (all keep the old name and never strip): target name already live (`_name_is_live` — a collision on `(theme_date, name)` would collapse two themes into one row), target name itself recently mass-evicted, model returned the same/unusable name, naming call failed or truncated. A fresh thesis is adopted only if it passes the #125 description-quality check — a failing thesis could cap an Accelerating/Mainstream theme to Nascent and cost every member the +10 bonus.
  - **What this does NOT fix, stated**: the ten-day loop's upstream cause — merge/retire passes killing whichever theme hosts the energy cluster, so its members go uncovered and pour into whatever narrow-named energy theme still exists. That is explicitly undetermined in the 08-26 analysis (§6) and untouched here. FIX 1 stops the eviction, not the churn that keeps re-creating the mismatch.
  - Tests: `tests/test_theme_rename_on_mass_flag.py` (31), each mutation-proven.
- **#601 OPERATOR RULINGS ARE KEYED ON THEME IDENTITY, NOT THE CURRENT NAME (2026-09-02, `db.mi_theme_renames`)**: an operator ruling is filed under a theme's NAME — a bypassed `mi_validation_cooldowns` row = *"this ticker belongs"* (the #213 shield), an `mi_theme_exclusions` row = *"never"*. A #214 rename keeps a NEW name, so the shield's exact `(ticker, theme_name)` match could never fire again, and the exclusion's 0.35-Jaccard word-overlap net fails on exactly the broadening renames #214 performs (`'Oil Refining & Marketing'` ↔ `'Energy Infrastructure'` scores unrelated — verified with the real function). **Fix**: `_save_themes` writes one append-only `(old_name, new_name, mechanism, theme_date)` row the moment the new name's `mi_themes` row lands (same connection, idempotent per day via `ON CONFLICT DO NOTHING`), and BOTH ruling loaders — `get_operator_protected_set` and `get_all_theme_exclusions` — expand every ruling across the connected component of that lineage (`resolve_theme_aliases`: symmetric + transitive, A→B→C means a ruling under A applies to C, no time bound because the rulings themselves never expire). **Why a new table and not the two traces a rename already leaves**: the Retired tombstone's `parent_theme` is overloaded (Pass 1.5 absorption and Pass 1 protect-strip write the same column) and `restore_recently_retired_themes` DELETEs Retired rows; the audit summary needs a string parse a name containing `'` or `%` defeats; a `renamed_from` column on `mi_themes` would be NULLed by the same-night re-run's `ON CONFLICT DO UPDATE` (the #539 nights ran three times). **Fail-open is ISOLATED to the lineage step**: a lineage error returns the raw name-keyed result (pre-#601 behaviour for one run), never an empty set — the shield's own fail-open reads a raise as "remove", so a lineage failure inside the loader would have dropped ALL protection. **Known gap (accepted)**: nodes are NAMES and names get reused — if B retires, an unrelated B is born months later and is renamed to D, A→B and B→D merge and a ruling under A reaches D; only a surrogate theme id closes that, and it was rejected as out of scope (every operator command, `mi_themes`' conflict key and every reader are name-keyed). The asymmetry is benign for protection (keeps a flagged member) and a mild over-application for bans — the same class the 0.35 fuzzy threshold already accepts by design. Deliberately NOT carried: NON-bypassed cooldowns (`get_cooldown_set`) — the rename's premise is that the members were right, so a machine strip under the old name should expire, not follow. **Nothing is ever written to `mi_theme_exclusions`** (read-side expansion only). Tests: `tests/test_theme_rename_lineage_601.py` — the acceptance case is CROSS-RUN: the ruling is recorded under the old name, run 1 persists the rename, run 2 is a fresh process (no in-memory `renamed_from`) validating under the new name, with the no-lineage negative control proving the in-memory flag alone would have lost it.
- **`mi_theme_exclusions`**: user-directed permanent bans ONLY. NOT auto-populated from validation removals (deliberately — a bad-description removal once permanently banned TSEM from semiconductor theme).
- **Fading themes**: tickers from Fading themes ARE in `covered_tickers` — prevents validation-removed stocks appearing as uncovered in the same run.
- **Post-assignment validation**: immediately validates newly assigned stocks (don't wait for Mon/Wed/Fri).
- **Birth validation (#266, 2026-06-17, operator-signed)**: newly DISCOVERED themes run the SAME `_validate_theme_membership` on their founding members before `_save_themes` — discovery previously skipped it, so bad members sat ~6d until the next Mon/Wed/Fri (evidence: `docs/analysis/theme_birth_validation_evidence_2026-06-17.md`). Changes WHEN, not WHAT; min-survivor guard keeps small/born-bad themes intact; emits `theme_birth_validated`.
- **Tool schemas**: all three tools (assignment, discovery, split) have `analysis_scratchpad` as required first field — forces reasoning before JSON output.
- **Membership test = the TAPE, not the sector label (2026-09-13, OPERATOR-SIGNED)**: a proposed (stock, theme) pair is admitted when the stock's market-adjusted (SPY-subtracted) daily returns over the 60 sessions STRICTLY BEFORE the run date correlate at ≥ `ASSIGN_COMOVE_BAR` (0.35 — a PER-PAIR bar; derivation at the constant) with the theme's equal-weight member basket (leave-one-out; ≥3 members with history, ≥30 overlapping sessions — `market_adjusted_correlation`'s maths and guards, imported by both the EP scan and this engine, never re-derived; #660 moved them out of `ep_theme_belonging` 2026-09-18, a pure move). The two strip sites — the birth strip (`_strip_sector_outliers`) and the nightly carryforward strip (`_apply_carryforward_deterministic_filter`) — now RECEIVE the context too (**#657 Shape A, 2026-09-25, OPERATOR-SIGNED "Yes to both"**; from 2026-09-13 to 2026-09-25 they accepted the parameter but their call sites withheld it — operator 2026-09-13: *"swap job 1 and leave job 2"*). This can only re-judge a SINGLETON-sector member (the only member either strip ever touches): kept when it co-moves with the theme at ≥ `ASSIGN_COMOVE_BAR`, stripped when it does not or is unjudgeable — exactly what the label already strips at most, never more; it can never evict a same-sector member (that would be "Shape B", NOT adopted — #657 found it evidence-mixed and it stays undecided). Consequence measured: 16 of 21 cross-sector names the tape admitted since 09-13 were being stripped by the label within 7 days (observed 1-3), a loop; Shape A ends it. Whether the tape should ALSO decide same-sector removals (Shape B / down-weight / leave) is still answered, not pre-decided, in #657: `docs/analysis/657_comove_removals_2026-09-25.md` (§CORRECTED: the evidence does not separate evict, down-weight and leave; the question stays open). Change log 2026-09-25. **Fail direction**: a pair the tape cannot judge (no history / thin basket / closes read failed / toggle off) runs TODAY's sector test — `_sector_identity_gate`, verbatim: the singleton-sector rejection, the sector-keyword fallback with its description rescue, and the Unknown-sector description-overlap check — never a silent admit. **Two passes per run**: a pair thin only for want of members is re-judged after the run's other admits have landed, the label's own yeses first (IREN was proposed before BTDR in the same batch on 2026-09-08 and met a 2-name basket). ONE `mi_daily_closes` read per run (`_load_comove_context`, in `run_theme_engine`, handed to the three sites as `comove_ctx`; and, since 2026-09-25, to a fourth: the Pass-2 sector cap's re-homed members (`_admit_rehomed_members`), which until then were moved by blind union with no test at all — change log 2026-09-25, BUG FIX; `None` = the pre-change engine byte-for-byte). Toggle `theme_assign_comove` (`mi_safeguard_state` / env `THEME_ASSIGN_COMOVE_ENABLED`, DEFAULT ON). Audit: `assignment_comove_admitted_over_sector`, `assignment_skipped_comove_below_bar` (both carry the sector counterfactual), `assignment_comove_summary` (the nightly positive observable), `theme_comove_context_failed`; the strip's aggregate row gains `comove_kept=` / `comove_below_bar=`. Change log 2026-09-13.
- **Description chunking**: `_ensure_descriptions()` sends max 15 tickers per Haiku call.
- **`get_active_themes(stale_after_days=7)`**: recency cap is the de-facto retirement mechanism — themes that stop appearing in daily snapshots age out after a week.
- **Phase 2 re-granularization (ADR 0032, behind `THEME_SUBTHEME_ARM` DB toggle, fail-closed OFF)**: Route A protect-strip→PARENT_CHILD adjudication (inert on DISTINCT verdicts — fail-closed to today's strip) + Route B sole-sub-theme ecosystem-dominant split via `_split_fat_theme` (self-disarms: post-split the ecosystem has 2 themes). Split children persist via `parent_theme` (rebuilt into `sub_theme_parents` each run); covered-ticker exclusion keeps split-offs out of the discovery pool.
- **Phase 3 ecosystem auto-discovery lane (ADR 0032 D1, #471, built 2026-09-12, `ecosystem_discovery.py`)**: `E-UNASSIGNED` is the substrate. Sunday 09:30 ET: active themes mapped E-UNASSIGNED → deterministic pre-cluster (edge = shared ticker OR shared ≥5-char name token; components ≥3 themes) → first sighting = `sighted` row, no alert → a re-sighting ≥7d later with ≥50% of the earlier themes still present AND cluster age ≥14d (earliest `assigned_at`) → ONE Sonnet proposal (`propose_ecosystem`, forced tool, ≤2 clusters/run; validated: `E-[A-Z0-9]{2,8}`, no collision with YAML ∪ dynamic, ≥3 member themes ⊆ cluster, ≥3 stems) → `pending` + the 🆕 veto alert (48h grace; bare `/vetoecosystem` = one-tap). Hourly sweep at :12 (+ boot catch-up) claims `pending AND grace_ends_at <= now` with a status-guarded UPDATE and promotes: `mi_theme_ecosystems_dynamic` row (source `auto`) + member themes remapped E-UNASSIGNED → E-<new> (`method='ecosystem_discovery'`) + loader refresh + Telegram confirm. Veto → `vetoed`, 30d cooldown, a matching re-sighted cluster is SKIPPED (`ecosystem_cooldown_skip`). `/vetoecosystem <live auto code>` → soft-retire + themes back to E-UNASSIGNED + same cooldown (reversibility; rows never deleted). Effective taxonomy = YAML ∪ active dynamic, YAML wins, dynamic entries sit before E-UNASSIGNED; `load_ecosystem_assignments` / `ensure_theme_ecosystems` refresh the dynamic cache (fail-safe: DB error keeps the last cache). Heartbeat `ecosystem_discovery_ran` on EVERY run — the substrate is ~1 theme today (G8), so idle is the expected early reading. Not built (named): `fits_existing` remap, early re-surface of a strengthened vetoed cluster, 28d `sighted → expired`, 🆕 board marker, inline veto button. Tests: `tests/test_471_ecosystem_discovery_lane.py`.
- **#505 PARENT PASS — parent-child holds on EVERY discovery path (built 2026-09-26, DARK behind `theme_parent_pass` in `mi_safeguard_state`, fail-closed OFF; operator 2026-07-27: *"parent child relationship must work regardless on how themes are discovered, if not then it's broken"*)**. Design of record = ruling (5) 2026-07-27 (`docs/design/theme_system_consolidation_2026-07-27.md` §5): **a theme is either a CHILD of a real theme or a ROOT directly under its ecosystem; E-UNASSIGNED is the catch-all** — no synthetic placeholder themes. So "every theme has a parent" is satisfied by the resolver, and the pass only adds CHILD links. Three pieces, one commit:
  - **Resolver (`theme_ecosystems.containment_parent` / `resolve_theme_parent`)** — the ONE reader of the overloaded `parent_theme` column: on a Retired row it is the retirement SUCCESSOR pointer (auto-retire / Arm-B absorption / #214 tombstone), never a link — reading it without the stage guard reported 8 links on 2026-07-27 when 3 were real. Returns `("child", parent) | ("root", E-code) | ("catch_all", E-UNASSIGNED)`. 2026-09-25 board: 117 live themes = 10 child + 104 root + 3 catch-all → 117 of 117 have a parent. #506's orphan metric reads through this function, nothing else.
  - **The pass (`theme_engine._run_parent_pass`, wired in `run_theme_engine` AFTER the auto-retire block and Arm B, BEFORE `_restore_sub_theme_links`)** — runs over the FINAL board so it is path-agnostic by construction: it never asks how a theme was born. Every childless live theme (non-Retired, non-Fading, mapped to a real ecosystem) is offered its ONE best same-ecosystem BROADER candidate to the existing ADR-0025 adjudicator (`adjudicate_merge_pair`, parent = A, child = B). The trigger `propose_parent_candidates` is PURE (no DB/LLM) and shared with the dry-run probe, so the probe prints exactly what an armed night asks. **Why thesis adjudication and not ticker containment**: measured 2026-09-26 before building — ticker containment (Route A's ≥0.8 / ≥3-shared trigger) fires on **1 of ~6,800 board pairs**; the 10 links that exist are ticker-DISJOINT thesis relationships from Arm B. Ticker overlap is therefore a PRIORITY signal (shared tickers → shared ≥5-char name tokens → parent breadth), never the gate. Verdicts: PARENT_CHILD (child = B) → `parent_theme` set + the run's `sub_theme_parents` map (so `_restore_sub_theme_links` re-sets it against the truly final list); PARENT_CHILD naming the BROADER theme the child → no link (inverted), 30d cooldown; DISTINCT → 30d pair cooldown (Arm B's exact semantics, shared table `mi_theme_merge_cooldowns`); **MERGE → audited as a SIGNAL (`theme_parent_pass_merge_signal`), NEVER executed** (merging is Arm B's live behaviour), 7d cooldown so it is not re-asked nightly; ERROR → audited, re-asked next night. Fail-open per pair and for the whole pass (the 2026-07-28 lesson — a crash is not a parity failure). One `theme_parent_pass_ran` heartbeat per armed run with counts. Cap `PARENT_PASS_CAP_PER_NIGHT` = 6 Haiku calls (~$0.01/night). **Arm B gets first right of refusal**: a child whose BEST candidate pair is one Arm B's uncapped Stage-A pairing would propose is DEFERRED, not offered its second-best — the dry run showed the one ticker-contained pair on the board (`Small Satellite & Space Services Rotation` inside `Space Economy: Satellite Communications & Launch Services`, containment 1.00, both `defense_aero` stems) is exactly such a pair, and the fallback candidate shared nothing with the child. Arm B's own verdict then unblocks it (DISTINCT → cooldown → next candidate; MERGE → gone; PARENT_CHILD → parented).
  - **Coverage by path, stated plainly**: Lane-1 discovery, the Route-B split, `/promotetheme` and every incumbent are on `all_themes` tonight → considered tonight. `shadow_promoted` rows are written by scheduler step 5d AFTER `run_theme_engine`, and tonight's NEWBORNS have no ecosystem row until `_map_ecosystems_nonfatal` runs after `_save_themes` → both are considered the NEXT night as incumbents (one night late, never never). The dry run found 6 of the 8 `shadow_promoted` themes on the board in the ask queue.
  - **Render (`format_ecosystem_board`, the /themes board)** — children nest under their containment parent (`↳`, one indent per level, chains render deeper; a child whose parent is Fading/elsewhere keeps an inline `↳ under <parent>` tag; Fading children carry the tag too). `briefing._compute_scored_themes` now carries `parent_theme` into the scored dict — before this the field reached four internal files and zero operator surfaces. Rendering reads whatever links exist; it is not a behaviour flip.
  - **Dry run / backfill = `scripts/probes/_505_parent_pass_dry_run.py`** (read-only, $0; output `_505_parent_pass_dry_run_out_2026-09-26.txt`): resolved parent per theme, tonight's capped asks + the whole queue with why, the 5 biggest families today and as an upper bound, and the backfill priced as ONE number via `pricing_for`. The verdicts need the paid adjudicator — `--adjudicate` runs it on the queue (log_spend=False) and is OPERATOR-authorised only. ⚖ **THE LINE**: theme structure feeds the judge's theme axis and allocation → the flip is CHANGE_PROCESS + operator sign-off on the dry run, and the toggle stays OFF until then. Forks for that sign-off: (a) run the one-shot backfill via `--adjudicate` vs let the nightly cap drain the queue (~7 armed nights); (b) ask zero-signal pairs at all (a childless theme is offered the broadest same-ecosystem theme even with no shared ticker/token — Arm B's own sector-family anchor pairing is the same heuristic and produced real links like `Non-Alcoholic Beverages & Energy Drinks → Defensive Consumer Staples Rotation`; the cost is one DISTINCT cooldown per wrong ask) vs require ≥1 signal. Tests: `tests/test_505_parent_pass.py` (28, all red on the pre-#505 engine).
- **`parent_theme` persistence across daily saves (#471, 2026-07-25 fix)**: `_rescore_existing_theme` rebuilds every theme dict from scratch each night, so a bare `t.get("parent_theme")` on the rebuilt dict is only ever set on birth day — the link went NULL on the very next save even while the parent was still alive (evidence: cyber-vuln child born 2026-07-17, `parent_theme` NULL from 2026-07-20 on; membership stayed stable only because the split used MOVE semantics with zero ticker overlap, masking the break). Fix has two parts: (1) `_rescore_existing_theme`'s two return branches now copy `theme.get("parent_theme")` forward; (2) `_restore_sub_theme_links` — called once, in `run_theme_engine`, immediately before `_save_themes` — is the final authority: for every name that is a key in the run's accumulated `sub_theme_parents` map, it (re)sets `parent_theme` if the parent is present (non-Retired) in today's final snapshot, else clears it. This is the same genuine-orphan semantics `_emit_pipeline_diagnostic`'s mid-pipeline remediation already had (kept as-is, for early audit visibility), just re-checked against the truly final list so it also catches drops from `_run_thesis_merge_pass` (runs after the last diagnostic call). Known gap, not hit by the evidenced case: `_canonicalize_theme_names` (inside `_save_themes`, after this reconciliation) can rename a theme to a 14d-prior canonical name — if that rename lands on a parent or child in the same run, the two names briefly disagree until the next day's `_restore_sub_theme_links` (keyed on the pre-rename name) re-derives them from `existing`; the pre-existing `sub_theme_parents`-based merge-protection carve-outs (Pass 1, ~line 4255) share this same name-stability assumption.

## Two-lane detection architecture + the judge-inference feed (#322)

Theme DETECTION runs on two structurally different lanes, both bottom-up (Pradeep:
themes emerge from price action, never a hypothesis fed in):
- **Lane 1 — price-action clustering** (this file's engine): RS/sector correlation
  against EXISTING clusters (`_assign_uncovered_to_themes`) or new-cluster discovery.
  Needs the ticker to CORRELATE with other names — a single name never clusters alone.
- **Lane 2 — narrative tracking**, two sub-lanes, both feeding
  `get_narrative_theme_candidates` → the judge's `active_narratives` context:
  - `discover_narrative_themes` (#167, `theme_engine.py`, source='narrative_cogap')
    — SAME-DAY co-gap: groups today's EP alerts by shared story via one Sonnet call.
    Drops the whole pass below 2 qualifying alerts (`len(cand) < 2`) and requires
    `len(tks) >= 2` to keep any proposed theme — **structurally needs 2+ co-occurring
    names**, never a single ticker.
    **v2 — INCREMENTAL NARRATIVE REGISTRY (built dark 2026-07-27, flag
    `lane2_grouping_v2` in mi_safeguard_state, operator-signed and flipped on
    2026-08-09 (commit `9b4c5d7`); the DEFAULT is fail-closed off — see "Live
    toggle state" below):** when ON,
    the lane is state-carrying instead of re-derive-nightly.
    State = the lane's own persisted rows: ACTIVE narratives (latest
    `source='narrative_cogap'` row per name, `db.get_lane2_active_narratives`)
    + a single-name WATCH LIST (`source='narrative_seed'`,
    `db.get_lane2_pending_seeds` / `persist_lane2_seeds`), both windowed to
    `LANE2_WINDOW_TRADING_DAYS` (10) trading days since last touch. Each night
    ONE Sonnet call sees only TODAY's qualifying alerts with full budgeted
    `grounded_text`→`claude_analysis`→`catalyst` evidence plus the compact
    roster, and answers per name: JOIN an active narrative (registry name +
    thesis FROZEN, members unioned, FIFO-capped at 12, needs ≥1 same-day
    addition), BIRTH a new theme (2+ tickers from today + watch list, ≥1 from
    today), or SEED the watch list (lone name with a real story — the cross-day
    accretion hook: WULF 07-06 seed + CLSK 07-14 alert = a 2-member birth).
    Dedup is STRUCTURAL (a continuing story is a join, never a new name);
    member overlap between a birth and an active narrative only fires the
    surface-only `lane2_possible_duplicate_narrative` audit tripwire — never an
    auto-merge. ⚠ The seed hygiene ("already a member → consumed, never seeded")
    sees ONLY the lane's own `narrative_cogap` roster — never the live `mi_themes`
    board step 5 wrote minutes earlier — so a name Lane 1 already holds can still
    be parked as a seed (HOOD 09-03, OMER 08-13; change log 2026-09-08). Seeds are outside BOTH walls by construction (not in
    `AUTO_PROMOTE_THEME_SOURCES`, not in `get_narrative_theme_candidates`'s
    source list). OFF is byte-identical to v1 (pinned by
    `tests/test_lane2_grouping_v2.py`). ⚠ GRADE-AFFECTING: this
    lane feeds the judge's `active_narratives` — the flip is operator-gated
    (CHANGE_PROCESS + fresh judge-robustness eval; the ADR-0030
    `preflight_judge_eval_gate` will fire on the grade-surface drift by design).
  - `run_theme_synthesis` (#240, `theme_synthesis.py`, source='rs_slope_synthesis')
    — cross-ticker RS-slope: proposes cohorts from coordinated accelerators/turners,
    `_MIN_MEMBERS = 3` — **structurally needs 3+ coordinated movers**.
- **S2/S3 coverage_probe** (2026-07-13, `coverage_probe.py`, source='coverage_probe';
  ⚠ RETIRED behind the `theme_birth_gate` flag 2026-07-27 — see the Phase-1
  section below; P3 survives as the birth gate's evidence primitive)
  — a THIRD, deterministic (zero-LLM) lane: for every themeless HIGH/MODERATE alert,
  independently re-discovers a peer cohort via P1 named-entity match (a peer
  company's name appearing in the alert's own `grounded_text`) + P3 market-adjusted
  co-movement + cross-session persistence. By design it NEVER reads the judge's
  `fire_axes` as an input (read-only calibration column only) — it must re-derive
  the cohort from independent evidence. **Needs a P1 peer-name hit** — a judge
  inference that names no peer at all (pure world-knowledge company classification)
  scores P1=0 and never confirms.

**#322 finding — why JBL's judge-inferred AI-infra theme was invisible to all three**:
the Holistic Grade Judge (ADR 0011) reads the full grounded catalyst text with
open-ended world knowledge and is explicitly instructed to weigh theme as the #1
Pradeep catalyst axis — it can recognize "this ONE company belongs to a theme" from
the catalyst text alone (e.g. Jabil's AI-datacenter-buildout exposure), with **no
minimum cohort size and no peer name required**. Every detection lane above has a
structural multi-member (Lane 1: correlate with a cluster; Lane 2 either sub-lane:
2-3+ same-day/coordinated names) or peer-naming (coverage_probe P1) floor a single
semantic classification never clears. The judge's `fire_axes` recorded only THAT a
theme/narrative axis lit, never WHICH theme — the name lived only in free-text
`judge_rationale`, parsed by nothing (ADR 0011 addendum 2026-06-17). Detection gap,
not a labeling gap: the signal existed and was simply never captured anywhere durable.

**The feed (shipped #322, `judge_theme_gap.py`)**: `ep_detector.py::_judge_shadow`,
right after the judge's DB write succeeds, calls `feed_judge_theme_gap` — when
`fire_axes` lights theme/narrative AND BOTH `in_active_theme` and
`in_narrative_cohort` are False (the exact booleans the judge itself was fed), it
writes a stub candidate (`db.upsert_judge_theme_gap_candidate`) into
`mi_theme_candidates_shadow` under **`source='judge_inferred'`** — name built
deterministically from sector+alert-date (never parsed from the judge's prose, so a
malformed name can never reach the table), thesis = the judge's rationale verbatim
(where "AI-infra" actually lives). Same-sector fires on the SAME calendar day merge
via ticker-set union (`ON CONFLICT (run_date, name)`, and `name` embeds the alert
date) — **no cross-day accrual**: unlike coverage_probe (whose stub name anchors on
a STABLE persistence-window date, giving it cross-day continuity), a repeat fire on
a LATER day writes a separate 1-member row under a different name, it never unions
into an earlier one. A single fire is therefore a PERMANENT reviewable ONE-member
row — below `theme_engine._PROMOTE_MIN_MEMBERS` (3), the same floor
`promote_shadow_themes` and the operator's own `/promotetheme` enforce
(`too_few` status) — promotable only if 3+ same-sector fires happen to land on the
SAME day; otherwise it's the operator's judgment call (build/rename manually, or
just watch it recur), never automatic.

**Display, not just detection (verify-operator-facing-surface)**: correct rows in
`mi_theme_candidates_shadow` are not the same as an operator-visible surface.
`/themes <ticker-or-name>` (`_handle_theme_lookup`, reactive) already covers any
source via `get_shadow_theme_candidates(include_probe=True)`. The bare `/themes`
board (`_handle_theme_query`, proactive — what the operator actually watches) now
ALSO renders a "🔎 Judge-inferred theme gaps" section reading the same
`get_shadow_theme_candidates(include_probe=True)` call, filtered to
`source == 'judge_inferred'`. This is a DISPLAY-only reader — deliberately NOT
`get_narrative_theme_candidates` (which feeds the judge's own `active_narratives`
input) — so proactive visibility today never touches the anti-circularity wall.

**Anti-circularity (mirrors coverage_probe's walls — the judge must never
corroborate itself)**: `source='judge_inferred'` is (a) NOT in
`db.AUTO_PROMOTE_THEME_SOURCES` (the nightly auto-promote allowlist — pinned by
`tests/test_judge_theme_gap.py`'s promote-wall tests) and (b) NOT matched by
`get_narrative_theme_candidates`'s source filter, so a judge inference can never
re-enter the judge's OWN `active_narratives` input on a later call. Graduation to
a live theme is always the operator's call, gated the same way as every other
non-allowlisted source.

**Known coarse-proxy limitation**: `is_theme_gap` checks the two membership
BOOLEANS (`in_active_theme`, `in_narrative_cohort`), not "does either lane track
the STORY at all" — a judge NEW-JOINER fire (matching an already-active Lane-2
narrative the ticker isn't yet a listed member of, the RCAT 5/28 class in
`ep_grade_judge.assemble_judge_inputs`'s `active_narratives` docstring) also reads
as a gap here even though Lane 2 already has the story. Accepted as an
over-capture cost for a surface-only, never-auto-promoted shadow feed (worst case
is a redundant reviewable row) — documented in `judge_theme_gap.py`, not fixed
(would need re-fetching + fuzzy-matching `active_narratives`, out of this feed's
scope).

**Memory pointer**: `theme_detection_two_lane_architecture` (informal — no
standalone memory file exists; this section + `judge_theme_gap.py`'s module
docstring are the durable SSoT going forward).

### Judge-named theme capture (#651, built 2026-09-12) — the NAME, and how late the engine is

> ⚖ **RULED 2026-09-14 — LEAVE AS IS. Do not re-raise.** He tapped the promote button on
> *Semiconductor Equipment Cycle Recovery* (ACMR+ONTO) and got *"only 2 member(s) — need ≥3. Not
> promoted."* **That is the design, not a defect:** `format_candidate_alert` states the bar in
> words and the button is meant to PERSIST so the original message goes live if the judge names a
> third (`SEED_REFRESH_DAYS = 7`). ⚠ I started removing the button for sub-bar groups and
> `test_651_judge_named_themes.py` caught it — the test encodes the persistence deliberately.
> ⚠ **Known and accepted, stated so nobody files it as a bug:** the seed sits in a 7-day window,
> so a group that never gets a third naming lets its button stop resolving silently. This one's
> tickers were last named 2026-08-07, 38 days before it paged, so it is dormant and will likely
> never promote itself. **`_PROMOTE_MIN_MEMBERS` stays 3** (ruled 2026-09-13 for the auto-promote
> lane). Whether a MANUAL tap should be exempt from an auto-promote floor was surfaced to him on
> 2026-09-14 and he ruled **leave it**. [[never-re-ask-an-answered-question]]


The #322 feed above records THAT the judge fired on an untracked name, as a sector+date
stub, and deliberately never the group the judge named. #651 captures the name itself,
structured, from the prose the judge already wrote (`mi_ep_alerts.judge_rationale`): the
nightly job `judge_named_themes_extract` (18:20 ET, bounded batch) runs one Haiku call per
still-owed alert (`judge_named_themes.extract_pending`) and writes one row per
`(alert, group)` into **`mi_judge_named_themes`** — `group_name`, a model-proposed
`canonical_key`, the judge's own sentence as `evidence`, `judge_says_untracked` — plus a
`(none)` sentinel for an alert that named nothing, so nothing is ever re-billed. **No
change to the judge's prompt or call path** (it cannot move a grade) and **off the alert
hot path by construction** (nightly, never per-scan — `ep_detector.py` does not reference
it, pinned).

**The purpose is a NUMBER, not a list — how late is the engine.** The read
(`judge_named_themes.lead_time_report`, runner `scripts/judge_named_themes_651.py
--report`) groups rows by normalised key and keeps only groups seen on **>= 2 distinct
tickers** — recurrence is the filter (one mention is a story, two names under one story
is a theme), there is no score or threshold — then asks whether `mi_themes` EVER held a
matching name (deterministic token match, rename lineage via `mi_theme_renames`,
near-misses printed beside every verdict) and reports `theme_first_date −
first_named_date` in days, positive = the judge was earlier. Verdicts `judge_earlier` /
`already_existed` / `never_matched`, each with its n. ⚠ The judge is fed our active-theme
context, so a rationale can ECHO our own theme name — the local timeline already holds a
theme literally named "AI data-center power buildout" four days before the SEI 09-08
rationale used those words. Only the dated comparison separates discovery from echo; the
name list alone does not.

**THE LINE / anti-circularity (same walls as #322):** the table is read by NOTHING that
grades, admits, sizes, enters, exits, creates or promotes a theme; the judge's own inputs
(`get_narrative_theme_candidates`, `ep_grade_judge`) never select from it
(`tests/test_651_judge_named_themes.py` group 5). Candidates surface for the operator's
ruling only. Finding: `docs/analysis/651_judge_named_themes_2026-09-12.md`; measured the
same day in prod ($0.24): of 45 groups over 144 alerts, 7 recur across >= 2 tickers — 2
named by the judge 11 and 8 days BEFORE the engine had the theme (7 tickers each), 3 already
existed, 2 never matched anything the engine ever held.

**The surface (2026-09-12, second half — a silent list is the same trap as a fill that
quietly stops; nobody reads it, nothing happens).** After the sweep, the same nightly job runs
`judge_named_themes.surface_new_candidates` over THE SAME `lead_time_report`: a group named
on **>= 2 distinct tickers** (recurrence is the definition of a theme) whose verdict is
`never_matched` (no theme the engine EVER held — a match to a retired name is #534's
reactivation lane, not this) and that has not been paged before is **SEEDED as a shadow
candidate** (`db.persist_judge_named_seed`, source **`judge_named`**, through the same
source-guarded upsert as `persist_reactivation_seed`; name = the judge's most frequent
phrasing, tickers = the ones it was named on, thesis = the judge's own sentences) and
**PAGED ONCE** with the group name, the tickers, the judge's words, the closest names we ever
had, and the **EXISTING one-tap promote button** (`theme_synthesis.build_synthesis_keyboard`
→ `tpromo:` → `/promotetheme_id` → `theme_engine.promote_candidate_by_name`). No creation
path was invented and nothing auto-creates a theme — the tap is the operator's. The engine's
`_PROMOTE_MIN_MEMBERS` bar (3) applies at the tap; the trigger is at 2 tickers, so the alert
states the count and that the button goes live at the third — the seed is re-written nightly
with the CURRENT ticker set while the judge keeps naming the group (`SEED_REFRESH_DAYS`, the
7-day shadow window), and the button resolves the name against the newest row. Dedupe is per
group key, FOREVER (`db.get_judge_named_surfaced_keys` over `judge_named_theme_candidate`
audit rows), written only after a successful send (a lost page retries next night — loud,
never silent). **Walls, by construction and pinned (test group 6):** `judge_named` ∉
`AUTO_PROMOTE_THEME_SOURCES` (never auto-promotes), ∉ `get_narrative_theme_candidates` /
`get_lane2_active_narratives` (never the judge's own evidence), ∉ `SEEDED_ASSIGN_SOURCES`
(the #491 assignment-pool RS-floor exemption is an operator-ruled two-lane scope and was NOT
widened — seeding there would have let a judge inference bypass the RS floor into the
membership that feeds the judge); visible only to operator surfaces via `include_probe=True`.
**Liveness:** every run writes `judge_named_theme_candidates_evaluated` (counts, and per
recurring group which theme suppressed it) — a quiet month and a dead trigger otherwise read
identically; a read failure RAISES so `audit_wrap` records the failure and #501 pages.
Expected ~one page a month. $0 preview: `scripts/judge_named_themes_651.py --surface --dry-run`.

### 2026-09-13 (late evening) — the ASSIGNMENT JUDGEMENT is now on the EP money path (`judge_theme_fit`)

**What changed**: `theme_engine.judge_theme_fit(ticker, description=, sector=, themes=)` asks the
nightly assignment pass's own question — the SAME prompt body, `assign_stocks_to_themes` tool and
rules (*clearly matches the thesis / when in doubt do not / most specific theme / exact name*),
since #661 (2026-09-20, change log) through the shared one-call primitive `_assignment_turn`
rather than through `_propose_assignment_batch` itself — of a caller-supplied theme SHORTLIST,
with the assign tool forced and no Opus advisor loop. It is stage 2 of the EP theme-bonus BELONGING test
(`ep_theme_belonging.py`, SSoT `docs/setups/magna53_ep.md` 2026-09-13): correlation shortlists ≤3
paying-stage themes, this judgement decides, and a confirmed fit pays the +10 on the EP score.
The prompt builders are extracted (`assignment_shared_prefix`, `_assignment_stock_line`,
`_assignment_theme_line`); the nightly render is byte-identical (pinned by literal in
`tests/test_ep_theme_fit.py`).

**⚠ What that means for anyone editing the assignment prompt**: its wording is now a SCORING
input on the money path, not only a nightly membership input. A "nightly-only" edit to the rules
text, the tool schema or the stock/theme line format silently moves EP scores the next morning.
Edit it as a detection-criterion change (CHANGE_PROCESS, magna53_ep.md) — that is the price of
having ONE definition of "fits a theme" instead of two that drift.

**Telemetry is separated on purpose**: the EP-time caller logs to the cost meter as
`ep_theme_fit` and writes `ep_theme_fit_llm_proposed` / `ep_theme_fit_silent_stop` audit rows —
never the nightly's `assignment_llm_proposed` / `assignment_silent_stop`, which
`data_gated_reviews.yaml` and `health_checks` read as the NIGHTLY pass's health (a dead nightly
must not look alive because the morning scan proposed something). Bounds live in
`ep_theme_belonging.py` (≤3 calls/tick, ≤40/day, 15 s timeout, premarket only, cached per day).

### 2026-09-13 — birth gate `observe` → `on` (OPERATOR-SIGNED)

**Trigger**: he asked why the gate was still observe-only and what to expect on flipping. It had
sat in `observe` for **45 days** (since 2026-07-30). Its gating review
(`theme_birth_gate_observe_calibration`) had its evidence bar — 8 clean `theme_date`s since
2026-07-29 — **met on 2026-08-07**; the predicate now reads **32**. It never surfaced as an
operator ask because the entry carries `earliest_review_date: 2026-10-01`. **Un-run, not blocked.**

**Evidence** — the forward review the flip required, run 2026-09-13 on **168 recorded verdicts**
over the 45-day observe window (`mi_theme_birth_candidates`):

| verdict | n | share | avg member RS | sightings |
|---|---|---|---|---|
| `join` | 86 | 51% | 63.0 | 1–14 |
| `await_second_sighting` | 53 | 32% | 68.5 | **1 only** |
| `birth` | 26 | 15% | 70.6 | 2–8 |
| `held_floor` | 3 | 2% | 29.3 | 2–5 |

- **Clause (a)/(c) — the wait arm lost nothing.** All 53 `await_second_sighting` candidates sit at
  exactly **1 sighting and never recurred** — one-day corpses. All 26 `birth` verdicts have 2–8
  sightings and birthed. ⚠ Verified the counter is not broken before believing it: `sightings`
  reaches **14**, with 107 rows above 1 and 107 whose `last_seen > first_seen`.
- **The 2026-08-11 objection does not survive.** It held that the defense theme
  {PLTR, TSAT, VOYG, AMRC} *"would not have been born that night at all"*. The candidate row:
  `U.S. Government/Defense Spending Surge`, verdict **birth**, sightings 2, first_seen 08-04,
  **born_date 08-05**. A **one-day delay**, not a suppression. The note stopped before the
  resolution.
- **Clause (b) — the join arm stops real duplication.** Three of the top ten joins name the SAME
  theme as their join target (*Gold & Precious Metals Miners Rotation*, *Government & Defense IT
  Services Providers*, *Precious Metals Royalty & Streaming*); others are plain synonyms
  (*Major US Passenger Airlines* → *U.S. Domestic Passenger Airlines*).

**Anticipated effect**: fewer, fuller themes. ~Half of new births fold into existing themes rather
than creating new ones, directly addressing *65% of 127 themes hold ≤5 members* and *20 themes sit
at 2, below `_PROMOTE_MIN_MEMBERS = 3`*. Expect theme birth ~1 day later for genuinely recurring
cohorts, and ~53 fewer one-day themes per 45 days. Almost nothing blocked outright (3 of 168).

⚠ **THE JOIN ARM IS NOT THE ONLY THING THAT CHANGED — TWO LANES RETIRED THE SAME INSTANT, and the
first version of this entry omitted both** (caught by an advisor review the same evening; he was
told only "fewer, fuller themes"):

1. **`shadow_v2` is retired** — its nightly pass is skipped (`run_theme_discovery_shadow`, scheduler
   5b) AND it leaves the effective auto-promote allowlist (`db.resolve_auto_promote_sources` returns
   `{narrative_cogap, rs_slope_synthesis}` at `on`). Nothing is lost: its a/a2 selectors were ported
   into Lane-1 discovery FIRST (`theme_engine.py:7428`), so those cohorts now arrive through Lane-1
   — which births at `NEW_THEME_MIN_STOCKS = 2`, not at `_PROMOTE_MIN_MEMBERS = 3`.
2. **The `coverage_probe` job is retired** (P3 survives as evidence annotation only).

🔴 **CONSEQUENCE — the effective auto-promote allowlist shrank from 3 sources to 2, so the night's
theme count will fall for TWO independent reasons** (joins acting, and a lane no longer feeding
promote). A birth-count drop is therefore **NOT** evidence the join arm worked: read the `join`
verdicts in the `/on]` rows, never the total. #655's Monday verify is written against that.

🔴 **"FEWER, FULLER THEMES" ABOVE IS HALF WRONG — the gate makes NO theme fuller, and it was never
built to** (found 2026-09-13 evening; the error is in this entry, not in the gate). A `join` verdict
is **de-duplication, not a merge** — `theme_birth_gate_derivation_2026-07-27.md:36`: *"Joins are
dedup, not kills: a birth suppressed because its cohort already lives on the board under another
name loses nothing… the bet stays on the board."* `join_target` is recorded for the ledger only;
there is no membership write, by design. The gate's whole effect on a non-birth verdict is
`new_themes = _gate_passed` (`:7897`).

⇒ **Read the effect as FEWER themes. Not fuller ones.** 86 of 168 observe verdicts (51%) were
`join`; step 1's defect (*65% of themes hold ≤5 members*) is untouched by this gate, and #655's
claim that the join arm is the lever for it has been corrected.

**Residual gap — the design's PREMISE, not its mechanism.** *"already lives on the board"* is exact
at overlap 1.00 and false below it. Measured on all 86: **64 (74%) are overlap 1.00 — nothing
orphaned, dedup exactly as designed**; the other **22 (26%) orphan ~2.1 members each** (~1 member a
night in no theme, where `observe` gave it one), because `BIRTH_GATE_JOIN_OVERLAP = 0.5` is
intersection-over-smaller — a cohort joins on a MINORITY of its own members; 7 of 86 are cohorts of
≤3 joining on a single shared ticker. `_assign_uncovered_to_themes` cannot catch them: Step 2b
(`:7767`) runs once, BEFORE discovery (`:7790`) and the gate (`:7844`).

**Recommendation (HIS call): keep `on`, floor stays 3, and close the partial-join orphan gap** —
either by re-running assignment on the orphans with the target hinted (NOT a direct `join_target`
write, which would bypass exclusions/cooldowns/bans/protected/F4) or by a small-cohort join-overlap
floor. `BIRTH_GATE_JOIN_OVERLAP = 0.5` was set with no small-cohort analysis.

**Promote floor** (`_PROMOTE_MIN_MEMBERS = 3`): lowering it to 2 was recommended and **WITHDRAWN**
the same evening — 6 of 8 two-member Lane-2 cohorts would draw a `join` (suppressed, identical to
today), so it buys two themes in 120 days. §11 of
`docs/analysis/theme_flow_and_the_0931_seam_2026-08-11.md` measured the same floor 33 days earlier
and its verdict — *"real but small, and for the EP-gap population specifically, unconfirmed"* —
**stands.** No recorded derivation exists for the value 3 (arrived with #226, `36e73843`).
Full evidence: `docs/analysis/lane2_grouping_quality_2026-09-13.md`.

**Reversion-flag**: INSTANT and no redeploy — `set_theme_birth_gate_mode('observe')` (or `'off'`).
The toggle is DB-backed in `mi_safeguard_state`; every reader fails closed to `off`.

⚠ **ONE JOIN IS UNRULED AND WILL NOW ACT.** `Emerging Bitcoin & AI Cloud Compute Miners` would JOIN
`Bitcoin Mining Equities Momentum Basket`, members including **APLD, NBIS, IREN**. That is the #491
case — he ruled on 2026-08-04 that the miners are *"converting into AI infra plays"*, a fundamental
shift and not a merge. **The flip was authorised with this flagged and unresolved**; if that join
lands wrong, it is the first thing to look at, and `/vetoecosystem` and a mode revert are both
one step.

### 2026-09-13 (same day, ~19:22 UTC) — REVERTED `on` → `observe` ON HIS INSTRUCTION ("Revert")

**Why**: the evidence I gave him to authorise the flip was circular. I reported *"all 53
`await_second_sighting` candidates were single sightings that never recurred — one-day corpses"* —
which restates the bucket's own definition, since under `observe` the theme was born anyway and the
candidate never re-presented. Measuring what those 53 cohorts actually did: **5 lived one day, 48
lived 2+ days, 20 lived 14+ days** (longest 31). The claimed *"~53 fewer one-day themes per 45
days"* is really about **5**, and the hold would have delayed 48 real themes by a night each.

**Second, unargued effect**: the same toggle retires `shadow_v2` — 445 of ~547 shadow candidate rows
(81%) — whose promote lane produced **224 of 495 themes born** in 120 days (45%), 120 of them
lasting 5+ days. Its a/a2 selectors were ported into Lane-1 first, but **that port has never run**
(market-days-only engine; last ran Fri 09-11 under `observe`). It was never argued on its own merits.

**What was NOT wrong — the arm worth keeping**: the join/dedup arm. 64 of its 86 observe-era
verdicts (74%) were overlap 1.00, i.e. the cohort genuinely already lived on the board under another
name. That is the piece the split below preserves.

**Verified from three surfaces**: the setter's read-back (`on` → `observe`), `apollo-execution`'s
independent read (`observe`), and the raw row — `theme_birth_gate | paper | observe |
2026-09-13 19:22:38+00`.

⏭ **NEXT, and it is the point of the revert: SPLIT THE TOGGLE** so the duplicate/join check can act
without the two-sighting hold and without the `shadow_v2` retirement. Three behaviours on one
3-state switch is why a good arm and two unargued ones shipped together. ⚖ Detection criterion —
his sign-off. Evidence: `docs/analysis/theme_lifecycle_diagnosis_2026-09-13.md`.

### 2026-09-13 (23:10 UTC) — FLIPPED to `dedup_only` ON HIS INSTRUCTION ("Go with rec")

Third and final mode change of the day, and the one the evidence supports. `observe` → `dedup_only`.

**What acts**: the join/dedup arm ALONE — `BIRTH_GATE_ACTED_OUTCOMES['dedup_only'] = {'join'}`, and
only on a FIRST CROSSING. `await_second_sighting`, `held_floor` and `held_no_rs` are born. Verified
live after the flip: acted verdicts `['join']`, auto-promote lanes
`['narrative_cogap','rs_slope_synthesis','shadow_v2']` — **`shadow_v2` retained**, its nightly pass
still runs, `coverage_probe` still runs, and the a/a2 Lane-1 fold stays OFF.

**Evidence it rests on** (`theme_birth_gate_dedup_only_flip` in `data_gated_reviews.yaml`, bar
declared before the query): of the 6 first-crossing joins to a DIFFERENT theme in the 45-day observe
window, **6 of 6 were correct** — 2 never appeared as a live theme, 4 died within 3 days, 0 survived
4+ days as a distinct lineage. n=6 is thin and was reported as thin; the change is ~3 suppressed
births a month and reverts instantly, so the bar was sized to the risk.

⚠ **Right-sized expectation, measured before the flip**: the gate had a verdict on only **20 of the
92** absorption/merge events in 45 days, so this prevents **at most ~22%** of the re-mint churn. The
other 72 are renamed back or absorbed by other passes before the gate ever sees them. The duplicate
problem is upstream, in naming — this is not its fix.

**Verified from three surfaces**: the setter read-back (`dedup_only`), the raw row
(`theme_birth_gate | dedup_only | 2026-09-13 23:10:57`), and `apollo-execution`'s independent read.

**Reversion-flag**: `set_theme_birth_gate_mode('observe')` — instant, no redeploy.
**Forward tripwire**: any cohort suppressed in `dedup_only` whose members later form a durable
distinct theme is a WRONG suppression — surface it immediately, do not wait for a review.

**Status**: shipped 2026-09-13 on his instruction ("Flip it") after the forward review above, and
**REVERTED the same day on his instruction ("Revert")** — see the entry immediately above.
Awaiting live validation — the forward check is whether consolidated themes mature at the same rate
as separately-born ones, which needs a fresh window at `on`.

### 2026-09-13 (evening) — SPLIT the toggle: new mode `dedup_only`, the join arm alone (SHIPPED DARK)

**Trigger**: the 19:22 UTC revert above. One 3-state switch carried FIVE behaviours that were never
argued separately — (a) the join/dedup arm, (b) the two-sighting hold, (c) the derived RS floor,
(d) the `shadow_v2` retirement (nightly pass skipped + allowlist minus `shadow_v2`), (e) the
`coverage_probe` retirement — so a measured arm and two unargued ones shipped together. Operator:
*"1. Split"*.

**What shipped**: `db.BIRTH_GATE_MODES = ("off", "observe", "dedup_only", "on")`. In `dedup_only`
`evaluate_birth` computes and RECORDS every verdict exactly as in `observe` (ledger row + audit row,
tag `[lane/dedup_only]`) and the callers act on **`join` only**: `await_second_sighting` /
`held_floor` / `held_no_rs` pass through as births; `shadow_v2` keeps its nightly pass AND its
allowlist seat (`db.resolve_auto_promote_sources` returns the full frozen set); `coverage_probe`
runs; the a/a2 fold into Lane-1 stays off — a **SIXTH** bundled behaviour the five-item list omitted
(the fold is the retirement's companion; folding while `shadow_v2` still runs would double-discover
its cohorts). Which verdicts act per mode is ONE table, `theme_birth_gate.BIRTH_GATE_ACTED_OUTCOMES`,
read by BOTH call sites through `gate_acts_on` (`promote_shadow_themes` and `run_theme_engine` Step
3a.5) and pinned against `db.BIRTH_GATE_MODES` so a mode cannot be added to one and not the other;
an unknown mode acts on nothing. Promote lane: acting is restricted to FIRST crossings
(`prior is None`) — the held-cohort fidelity carve-out (now engaging in `dedup_only` as well as
`observe`, via `gate_promotes_held`) re-evaluates a still-`watching` cohort the mode promoted anyway,
and in prod that re-evaluation draws `join` against ITSELF (the board holds last night's promotion
at overlap 1.00); acting on it would cancel a maintenance re-promotion `on` never gated. Scheduler
step 5b was extracted to `_theme_shadow_pass_step` so the per-mode retirement decision is testable
the way `_coverage_probe_job` is; no behaviour change.

**Evidence** (the revert entry's numbers): the hold kills 5 genuine one-day themes but delays 48
real ones (20 lived 14+ days); (d) silently cut the lane that produced 224 of 495 themes born in
120 days; (a) is measured — 64 of its 86 observe-era verdicts were overlap 1.00. ⚠ One caveat on
that 64: the promote lane's carve-out re-evaluates cohorts it promoted itself, and those draw a
self-`join` at 1.00 under the cohort's OWN name — run
`SELECT COUNT(*) FROM mi_theme_birth_candidates WHERE last_outcome='join' AND join_target=name`
before citing 64 as "under another name" (not run tonight — the prod read was unavailable from the
build machine). The self-join also means the carve-out's "hold progression accrues" claim is weaker
than written for the promote lane: on night 2 lever 1 short-circuits levers 2-3.

**Anticipated effect**: **none until flipped** — production stays `observe`; every off/observe
parity pin passed untouched and the diff is dark by construction. At `dedup_only`: roughly half of
would-be births (86 of 168 observe verdicts) are suppressed as duplicates of a theme already on the
board; NO theme is delayed a night; `shadow_v2` keeps feeding promote; the birth count falls for ONE
reason only, so a drop IS evidence the join arm acted (unlike the 09-13 flip). The "previously-held
later PASSED" counter reads as would-have-been-delayed there — the same caveat observe carries.

**Reversion-flag**: NEW (a new mode; `off` / `observe` / `on` behave exactly as before).

**Status**: shipped DARK 2026-09-13; live mode `observe`. Flipping to `dedup_only` is the
OPERATOR's call (THE LINE) — `set_theme_birth_gate_mode('dedup_only')`, instant, no redeploy;
revert with `set_theme_birth_gate_mode('observe')`. Pins: `tests/test_theme_birth_gate.py` (48 —
join acted on and ONLY join at both sites; holds born in `dedup_only` and not in `on`; `shadow_v2`
in the allowlist and its pass running; the self-join carve-out never suppressing; every off/observe
parity pin intact).

## ONE birth gate + lane retirements (consolidation Phase 1, 2026-07-27 — 4-state toggle `theme_birth_gate` since the 2026-09-13 split, fail-closed 'off')

Behind `mi_safeguard_state` toggle `theme_birth_gate`
(`db.get/set_theme_birth_gate_mode`, **4 states — the `broker_order_ingest`
off/dry_run/live idiom plus the 2026-09-13 split**,
`db.BIRTH_GATE_MODES = ("off","observe","dedup_only","on")`,
fail-closed 'off' on any error or unrecognized string, instant no-redeploy
transitions, OPERATOR-gated). **Which verdicts each mode ACTS on is ONE table,
`theme_birth_gate.BIRTH_GATE_ACTED_OUTCOMES`, read by both call sites through
`gate_acts_on` and pinned against `db.BIRTH_GATE_MODES`** — the verdict math is
identical in every non-`off` mode; only the caller's act differs:

- **`off`** (today's production state) ⇒ **byte-identical to the pre-gate
  engine** (pinned by `tests/test_theme_birth_gate.py`).
- **`observe`** (the DEPLOY state) ⇒ **zero behavioural difference from
  `off`** — every theme is born exactly as today, promote untouched, the
  retirements inactive, allowlist unchanged, Telegram parity pinned — while
  the gate COMPUTES and RECORDS its verdict on every would-be birth: per
  candidate the outcome, the DECIDING LEVER (`reason` ∈ pass_rs_level /
  pass_rs_rising / join / await_second_sighting / held_floor / held_no_rs),
  member-avg RS, pre-birth 5-session ΔRS, IoS overlaps vs board/ledger, and
  `mode`, persisted in `mi_theme_birth_candidates` + the `theme_birth_gate`
  audit rows (summary tag `[lane/observe]`). The ledger POPULATES in observe
  so join-or-new — the biggest lever, 50/106 in the July replay — is
  exercised, not starved. Forward evidence therefore accrues BEFORE the gate
  ever touches a live theme (the shadow-first discipline every prior flip
  followed); the observe→on comparison is the run-count-gated review
  `theme_birth_gate_observe_calibration` (data_gated_reviews.yaml — fires at
  20 observe-mode gate rows ≈ 2 trading weeks, NEVER date-gated per the
  2026-07-26 ruling). Observe fidelity notes: on the promote lane a
  still-`watching` ledger cohort keeps being re-evaluated even though observe
  promoted it (so two-sighting/floor progressions accrue real data); on Lane 1
  an observe-born cohort can't re-sight (it's covered next night), so Lane-1
  verdicts read as-at-first-sighting and the review judges the two-sighting
  lever from mi_themes presence (≥2-day themes = delayed-not-lost).
- **`dedup_only`** (the 2026-09-13 SPLIT, operator: *"1. Split"*) ⇒ the gate
  acts on the **`join` verdict ONLY**, at both call sites: a first-crossing
  cohort overlapping ≥ 0.5 (intersection-over-smaller) with a live theme is
  not born — the bet is already on the board under another name. Every other
  verdict (`await_second_sighting` / `held_floor` / `held_no_rs`) is recorded
  exactly as in `observe` and the theme IS born — no theme is delayed a night;
  `shadow_v2` keeps its nightly pass AND its allowlist seat; `coverage_probe`
  runs; no a/a2 fold (the fold is the retirement's companion — folding while
  `shadow_v2` still runs would double-discover its cohorts). Promote-lane
  acting is restricted to FIRST crossings (`prior is None`): the held-cohort
  carve-out engages here as in observe, and a carve-out re-evaluation
  self-joins at overlap 1.00 in prod (the board holds last night's
  promotion) — acting on it would cancel a maintenance re-promotion `on`
  never gated. Audit tag `[lane/dedup_only]`; the
  `theme_birth_gate_observe_calibration` review keys on `%/observe]%` and
  does not count these rows.
- **`on`** ⇒ the gate ACTS on every non-birth verdict:

- **ONE birth gate on every live-theme birth path** (`theme_birth_gate.py`):
  Lane-1 discovery (`run_theme_engine` step 3a.5, after name-inheritance,
  before #266 birth validation) AND `promote_shadow_themes` first-ever
  crossings — the previously-ungated bypass. Order: join-or-new (≥0.5
  intersection-over-smaller vs the live board; member-majority-covered
  refinement proposals are carved out — the merge/Route-A machinery owns
  those) → two-sighting bar (≥2 distinct days vs the 14d
  `mi_theme_birth_candidates` ledger, quiet entries included — the #476
  re-mint memory) → derived floor (member-avg RS ≥ 70 **OR** pre-birth
  5-session cohort ΔRS ≥ 0; derivation:
  `docs/analysis/theme_birth_gate_derivation_2026-07-27.md` — the flat ≥70
  start was derived AGAINST: it kills 19.4% of everything that ever matured;
  the rising arm exists because weak-born maturers are RISING pre-birth
  (+2.5 median) and weak-born corpses are FALLING (−5.3)).
- **Existing live themes untouched, three legs**: re-promotions of any name
  with a prior `mi_themes` row bypass the gate (maintenance); Lane-1
  re-emissions of live names pass ungated (merge owns them); the gate never
  mutates `mi_themes` (a `join` only suppresses an INSERT). Board survivors of
  the retired funnel persist via the daily engine itself (`get_active_themes`
  reads all sources; day-2+ rows are `source='live'` — verified vs prod).
- **shadow_v2 stream RETIRED** (decision 1): the nightly
  `run_theme_discovery_shadow` call is skipped (audited
  `shadow_v2_stream_retired`), and `shadow_v2` leaves the EFFECTIVE
  auto-promote allowlist (`db.resolve_auto_promote_sources`, shared by both
  walls). Its a/a2 selectors (`get_rs_accelerators` + `get_rs_recovery_slope`)
  were PORTED into Lane-1 discovery first — same covered/RS≥THEME_RS_MIN
  filters the shadow applied, discovery-pool only.
- **coverage_probe job RETIRED** (decision 2: 0 confirmed cohorts lifetime):
  `_coverage_probe_job` skips (audited `coverage_probe_retired`). Its P3
  market-adjusted co-movement primitive survives as the gate's EVIDENCE
  ANNOTATION (`theme_birth_gate._p3_annotation` — never a blocking criterion;
  that threshold is underived).
- **Counter-only observability (design §7)**: one `theme_birth_gate` audit row
  per gated run/lane — `[lane/mode] N birth / N join / N awaiting-2nd-sighting /
  N held-floor` (emitted in observe AND on). No thresholds in the health line;
  those derive after the funnel settles.

**Graduation path (honest, shadow-first)**: deploy in `observe` → ~2 trading
weeks alongside the real engine → `theme_birth_gate_observe_calibration`
fires on run count → operator judges forward FN/join/two-sighting evidence
against the 254-replay numbers and signs the cell + FN list (CHANGE_PROCESS
r3 — findings stated, operator rules) → fresh ADR-0030 judge-robustness eval
(the preflight gate fires on grade-surface drift by design — never suppress)
→ `set_theme_birth_gate_mode('on')`.

## ⚠ Live toggle state — `lane2_grouping_v2` is ON in PAPER and was undocumented until 2026-08-29

`lane2_grouping_v2` was operator-signed and flipped on **2026-08-09** (commit `9b4c5d7`, recorded in `docs/roadmap/ep_profitability_program.md`); the `mi_safeguard_state` row carries **`last_transition_at` NULL** (so the
flip date is unrecoverable from the row). The flag selects lane-2's grouping mode in
`theme_engine.discover_narrative_themes` (#167 incremental narrative registry, operator-ruled
2026-07-27; `db.get_lane2_grouping_v2_enabled`, fail-closed OFF). **It is GRADE-AFFECTING when
ON** — the lane feeds the judge's `active_narratives`.

**Why this note exists.** The flip WAS signed and recorded in the profitability program — so nothing about it was unauthorized. What was missing is that no setup or architecture document mentioned the flag at all; the only
prose about it was in an analysis document that describes it as dark. So every doc read as if v1
were running while v2 has been acting in paper. Found 2026-08-29 the first time
`scripts/live_rules.py` was pointed at `docs/analysis/**` — the operator: *"how many times we do
we need to fix this, 100x more times???"*, which is what prompted extending the scan beyond
`docs/setups/`.

⚠ **This records the state, it does not change it.** Whether v2 should be on in paper, and
whether it should reach live, is the operator's call. What was wrong was that nobody could
have known it was running.

## Correlation cluster engine (Lane-1 statistical pre-pass) — parameters and what discovery is shown

`agents/market_intelligence/correlation_engine.py`, run by the nightly job (scheduler step 4.5)
before the theme engine; its output goes to BOTH `run_theme_engine` (17:07 ET, precision
disposition) and `run_theme_discovery_shadow` (~17:15 ET, recall disposition) and is persisted
to `mi_correlation_clusters`. Nothing under `broker/` reads it. Documented here 2026-09-09 (#486)
because nothing recorded these parameters before.

- **Universe** (`db.get_closes_for_correlation`): `mi_daily_closes`, close ≥ $5, security type
  CS/ADRC (`mi_security_types` — this is what keeps single-stock leveraged ETFs out; they sit at
  raw corr 1.00 to their underlying), average daily dollar volume ≥ $20M, full coverage over the
  window. 35 calendar days → ≥ 21 closes → 20 daily returns.
- **Source-level artifact removal (#486, 2026-09-09), BEFORE beta adjustment, on raw returns:**
  1. **Share classes of one issuer → one representative.** Candidate by ticker shape (same pre-dot
     root `BRK.A/BRK.B`; one ticker = the other + one trailing letter `GOOG/GOOGL`, `UA/UAA`; both
     ≥ 5 chars sharing the first four `BELFA/BELFB`, `GOOGM/GOOGN`) AND confirmed by raw-return
     correlation ≥ `_SHARE_CLASS_MIN_RAW_CORR = 0.90`. Survivor = shortest ticker, then
     alphabetical; siblings leave the matrix. **Why both tests:** on real closes the GOOG family's
     raw corr fell to 0.961 in one of 24 windows while DISTINCT issuers reached 0.99 (NSA/PSA, two
     self-storage REITs, 14 windows; RIG/VAL 24 windows) — a pure threshold would collapse real
     groups; a pure root match would merge ALM/ALMS (different companies, corr ≈ 0.3).
  2. **Cash-like series dropped.** A name whose daily-return std with its single largest |return|
     day removed is < `_MIN_EX_SPIKE_DAILY_STD = 0.3%` is a takeover target trading at its deal
     price (BWMN/HZO/VREX: +46-56% on 08-10, then 0.19-0.26%/day). Its beta residual is ∝ the
     market's return, so such names correlate with each other spuriously (five clustered at 0.92
     on 09-08). Measured: the universe's 0.5th percentile of the statistic was 0.20-0.43% across
     three windows; real cluster members sit at 1.3-4.2%/day.
- **Correlation**: beta-adjust each name against SPY (ddof=1 throughout), Pearson on residuals.
- **Clusters**: BFS connected components at pairwise residual corr ≥ 0.85; keep components of
  ≥ 4 members with mean pairwise corr ≥ 0.80 (the chaining filter). Hash = sha256 of the sorted
  members (first 8 hex).
- **Dedup vs themes**: a cluster with ≥ 50% of its members inside ONE non-Fading active theme is
  dropped before the write; a cluster spread across several themes passes (deliberate — a
  cross-theme cluster can be a sub-theme or a merge signal). Consequence, stated: the 33-name
  precious-metals block passed 25 nights while 31 of 33 members sat in five themes.
- **Enrichment**: `avg_rs` and, in memory only, `member_rs` (per-member RS from
  `get_rs_for_tickers`; not persisted — `get_correlation_clusters` readers fall back to the pool
  lookup).
- **What discovery is shown** (`_render_cluster_block`, #486): only clusters with ≥ 1 member not in
  any active theme; ordered strongest-first by avg RS; each member as `TICKER (RS, sector —
  description) [in: <theme>]` for the top `_CLUSTER_DESCRIBED_CAP = 12` members by RS, the rest on
  a `+K more` tail (the header says `N of M already in a theme`). **A Fading parent is named as
  such** — `[in: X (Fading)]`, header `(K of those in a Fading one)` — because the one split that
  did work in the history (tankers, cluster 09-01 → named 09-02) came out of a Fading 41-name
  energy blob, and a bare "already in a theme" on a dying parent would be a stronger skip signal
  than the bare ticker the model used to see. `_partition_discovery_pools`
  counts the described lines toward `_DISCOVERY_LLM_BATCH_STOCKS`. Members outside every pool get
  their description via `_ensure_cluster_member_descriptions` at both call sites (guarded — a
  fetch failure degrades to bare tickers, the pre-09-09 rendering). The three disposition sentences
  (propose on a clear thesis / do NOT force when unclear / real name, never 'Cluster A') are
  verbatim from before and are the criterion.
- **What the recorder writes** (`theme_discovery_shown_declined`, one row per discovery run):
  pools shown/declined, themes proposed, and every cluster as **taken / partial /
  already_named / declined** — `already_named` (2026-09-09) = no member claimed AND ≥ 50% of
  members already in an active theme (Fading included — the set the prompt itself uses), with
  `covered_share` + `covered_by`; plus `scratchpads` = the model's own one-line-per-cluster
  reasoning per batch, so "why did it decline?" is readable from the row.

## What is NOT a theme-engine coverage gap — deal-pinned names (2026-09-17, operator-signed)

The evening brief's 5-session persistent-unanchored line states a diagnosis:
*"theme-engine coverage gap — no theme claimed these names all week"*. **That claim is false for a
stock pinned by an announced acquisition, which is un-themeable by construction — no amount of
theme-engine work will ever claim it.**

Found by the operator on the line itself (`entered: ACVA`): *"but stock is being bought out."*
Our own bars already said so — ACVA gapped **+44.2% on 114.9M shares** on 2026-09-11 (vs a ~3M
norm) and every session since traded a **0.19–0.48%** range at 10.41–10.48. A cash deal price.

**Why it reaches the theme engine at all:** RS is a backward-looking 1M/3M/6M percentile, so one
deal gap moved ACVA **rank 1084 → 7**, still 17 six sessions later on flat bars. Eight such names
sat in the RS ≥ 90 population that day.

🔴 **And a deal had already promoted a theme.** `Management & Business Advisory Consulting Firms` is
**two names, `{HURN, CBZ}`**, and CBZ is deal-pinned. Its `rs_avg` ran **80.3 → 92.9** over
09-10 → 09-16 and it graduated **Nascent → Mainstream on 09-15** — that climb is CBZ's +17.6%
announcement on 24× volume averaged into a two-name theme. **`in_active_theme` counts only
Accelerating or Mainstream** (`ep_detector.py:1568`), so a name in that theme would collect the EP
theme boost on a promotion earned by an acquisition.

**THE RULE — reused, not invented.** `db.get_deal_pinned_tickers` lifts the threshold already signed
in `get_eod_9m_sugar_babies` (*"intraday range >= 2% of close (rejects merger-arb pins like DBRG)"*,
retired 9M path) to a shared helper. Two legs, because low range alone is just a sleepy stock:

| leg | test |
|---|---|
| the pin | last 4 sessions ALL inside 2% of close |
| the announcement | within 180 days, a day up ≥15% on ≥10× its trailing 21-day volume |

Calibrated on prod 2026-09-17: the pin leg alone matches **5,560** tickers (useless alone); both legs
match **54**, which reads like a live M&A book. Of the 8 hand-screened RS ≥ 90 names it catches 7 —
**ITGR is missed** — ⚠ **corrected 2026-09-17, same evening**: not because its announcement falls outside the
lookback (it does not — ITGR announced **2026-07-31**, 48 days back), but because no single day
clears **both** bars. Its announcement day is +20.2% on **6.0×** trailing volume against the 10×
required. So the knob ITGR misses on is `rvol_bar`, not `lookback_days`. That miss **fails open**
(the name stays in the population), which is the safe direction for a filter that removes things.

**APPLIED AT THE SOURCE — `db.get_rs_leaders`**, alongside the classifications already living
there: `SKIP_TICKERS_LIST`, the `mi_tracked_stocks.quote_type` non-equity clause, and
`is_sector_filtered`. A deal pin is the same KIND of fact as "this is an ETF" — a per-ticker
classification every downstream surface inherits without knowing what a deal is. The screen is
scoped to the rows already fetched (~`limit*2`), not the universe. `include_deal_pinned=True` opts
back in, so classification lives in one place and POLICY stays the caller's.

⚠ **A FIRST CUT PATCHED `brief_composer.compute_unanchored` AND WAS REVERTED THE SAME DAY**
(operator: *"Is there a better fix upstream so it's caught at the source"*). Two things were wrong
with it: it would have been the **third** M&A mechanism here — after the retired 9M range rule and
`parabolic_detector._news_check_for_exclusion` — and **the theme engine calls the same
`get_rs_leaders`** (`theme_engine.py:1296`), so the brief would have been clean while discovery and
assignment kept ingesting deal-pinned names.

⚠ **AND "FIXED BY INHERITANCE" WAS ITSELF TOO NARROW — corrected the same evening, by review.**
`get_rs_leaders` is **one of SIX** RS pools — five in the theme engine, and a sixth that never
touches it. The live gather (`theme_engine.py:7886`) takes
**leaders + `get_rs_velocity` + `get_rs_turners`**; a second live gather (`:7919`, behind
`birth_gate_on`) adds **`get_rs_accelerators` + `get_rs_recovery_slope`**, and
`run_theme_discovery_shadow` (`:1296`) takes all five unconditionally. Only the leaders were
filtered. This was not theoretical. **Observed on prod 2026-09-17 under the current UNFILTERED code**
(nothing was deployed yet): **BWMN is in prod's velocity top-30 and at leaders rank 193**, and
ACVA and MKTX are in the uncapped velocity pool one rank move from entering it. So the
leaders-only fix **would have dropped BWMN from the leaders and left it in velocity**. ⚠ Written
as the inference it is: an earlier draft of this section said BWMN was "gone from the leaders
while live in velocity" — a state that existed only in the local tree, never on prod. Same
shape as the #610 retraction earlier the same day.

⚠ **The two selectors found by the guard rather than by inspection are the most deal-prone of
all five**, which is why "no hit measured today" was never the right test:

- **`get_rs_accelerators`** — rank improvement **≥800 places** *or* an RS jump **≥25** inside two
  sessions. That is a definition of an acquisition gap. ACVA went rank **1084 → 7** and **RS
  54 → 99** on its announcement day, clearing *both* arms of the OR by a wide margin.
- **`get_rs_recovery_slope`** — `rs_1m ≥ 90 ∧ rs_6m ≤ 30`. One gap lifts `rs_1m` to the top decile
  while `rs_6m` still measures the pre-deal months — the shape is the deal.

Both are reached in the live path only when the birth gate is `on`; prod reads **`dedup_only`** as
of 2026-09-17, so they are **dark in live today** and reached unconditionally only by the shadow
pass. Filtered anyway — a dark selector is precisely the one nobody re-checks the day it is
switched on.

**Velocity is in fact the WORST leg to leave open.** An announcement gap is a one-week RS jump, so a
pinned name scores *maximum* front-weighted velocity for the four weeks the gap sits inside the
window — ACVA went **RS 54 → 99 in a single session** on its deal. Turners are a weaker fit (they
require RS ≤ 30 four weeks ago) and **none of the eight pinned names were turners**; that leg is a
completeness guard, stated plainly so it is not later read as a measured hit.

**All three inputs now apply the same filter, with the same `include_deal_pinned=True` escape:**

| stage | input | live? | effect |
|---|---|---|---|
| discovery | top-40 **leaders** | live | pinned names no longer seed a theme |
| discovery | **`get_rs_velocity`** (top-30, `min_rs` `THEME_RS_MIN` 50) | live | ← **the leg that was leaking — BWMN was in it on prod** |
| discovery | **`get_rs_turners`** (top-30) | live | completeness — no measured hit; a pinned name is a weak turner by construction (needs RS ≤ 30 four weeks ago) |
| discovery | **`get_rs_accelerators`** (ADR 0007 a) | gate `on` only — **dark today** | the most deal-shaped selector of the five; ACVA clears both arms |
| discovery | **`get_rs_recovery_slope`** (ADR 0007 a2) | gate `on` only — **dark today** | `rs_1m≥90 ∧ rs_6m≤30` is the post-gap shape |
| **evening brief** | **`get_rs_recovery`** — RECOVERY section, top-10 | **live, and he reads it** | `rs_1m≥70 ∧ composite≤45` ranked by the divergence **is** the post-gap signature; outside the theme engine entirely |
| assignment | RS ≥ `ASSIGN_POOL_RS_FLOOR` 70 within top-`ASSIGN_POOL_CEILING` — fed by `get_rs_leaders` | live | pinned names no longer join |
| coverage / staging | `THEME_COVERAGE_MIN` 3 members showing strong RS | live | a theme carried by a deal loses its member and re-stages by existing rules |

🔒 **GATED — `tests/test_deal_pinned_not_a_coverage_gap.py` derives the pool list from `db`'s own
function signatures and asserts every one carries `include_deal_pinned=False`.** POOL vs LOOKUP is
itself derived, never hand-listed: a pool ranks a population and takes `limit`; a lookup answers
about names the caller already holds and takes `tickers`/`conn`. That split sorted nine `get_rs_*`
functions into **6 pools and 3 lookups** with no overlap.

⚠ **THE GATE WAS REPLACED THE SAME EVENING, AND THE REASON MATTERS MORE THAN THE GATE.** Its first
version AST-walked `theme_engine.py`'s `asyncio.gather` calls — and it earned its keep immediately,
going **red on its first run** and surfacing `get_rs_accelerators` and `get_rs_recovery_slope`. But
its own population was wrong **in the same way the fix had been**: it could only see pools passed to
a `gather`, in one file. A repo-wide sweep then found `get_rs_velocity`/`get_rs_turners` called
**bare** in `theme_synthesis.py`, and `get_rs_recovery` feeding the **evening brief** from
`briefing.py` — outside any gather, outside the theme engine. So the derivation moved down a level,
from **call sites to definitions**: every RS pool in `db` carries the flag, wherever it is called
from and whether it is called at all. Strictly stronger, catches a new pool at definition rather
than at wiring, and reads no source text — so the #653 pin baseline went back **down** to 404
instead of up.

📌 **The lesson, the day's recurring one, and it repeated INSIDE its own fix:** "the theme engine
inherits the fix" was an inheritance claim tested against **one** call site. Corrected to five, it
was still wrong — six, and the sixth was the one that reaches the operator directly. Each time the
arithmetic was right and the population was wrong. **A guard is only as good as the population IT
derives**, which is why this one now derives from definitions, the narrowest place the answer can
hide.

✅ **It self-heals — no migration.** Membership is re-derived nightly, not carried: across 639
consecutive-day theme pairs since 09-08, **145 had a ticker LEAVE**. So the two affected themes
(`Management & Business Advisory Consulting Firms` {HURN, CBZ} → 1 member; `Emerging Medical Device
Innovators Breakout` → 2) fall under `THEME_COVERAGE_MIN` on the next run and fade by the rules
already in this file.

⚠ **The exclusion is silent, deliberately and by precedent** — ETFs, non-equities and small-cap
healthcare are already dropped here without announcement. The classification is documented in this
section and in the function's docstring, which is where a reader looks for "why is X not a leader".

### 🔒 The six RS pools read ONE universe (#673, 2026-09-20)

**All six RS pools read ONE universe: known non-equities are excluded by every one of them.**
"Known non-equity" is the two classifications the leaders board has carried since 2026-03-23 —
the `mi_tracked_stocks.quote_type` clause (`NOT EXISTS … quote_type != 'EQUITY'`) and the
hand-kept `SKIP_TICKERS_LIST` (leveraged / inverse / index / sector / commodity ETFs and ETNs).
**Gated:** `tests/test_deal_pinned_not_a_coverage_gap.py` §#673 derives the pool list from `db`'s
signatures (the same POOL-vs-LOOKUP rule as the deal-pin gate), runs each pool against a recording
connection, and classifies the statement it actually sends to `mi_stock_scores` — behaviour, not
source text. A pool that must read a wider universe carries a `UNIVERSE-EXCEPTION: <reason>`
docstring marker; the gate fails on a **silent** divergence and on a **stale** marker alike, so the
readout is always `N/0` or `N/M-with-reasons`, never `3/3-silent`. **Readout 2026-09-20: 6/0.**

**The 3/3 split was ACCIDENTAL, not a design** — how we know, from git rather than argument:

| when | what | who got it |
|---|---|---|
| 2026-03-16 · 03-18 | `get_rs_velocity`, `get_rs_turners` born | no non-equity clause existed yet |
| **2026-03-23 18:03 PT** | `a744d7f6` — *"Filter non-equity tickers from RS leaders via quote_type subquery. Also add SNXX to SKIP_TICKERS as immediate fix."* | **leaders ONLY** — an evening hotfix on the one board that had just shown an ETN; velocity and turners existed and were not touched, and no commit message or doc gives them a wider universe |
| **2026-03-24 07:50 PT** | `bbbfbccc` — the RS engine scores only common stock (`mi_security_types` CS / ADRC) | the **write** side. The read-side clause went dormant the next morning, which is why nobody propagated it: the last non-equity score row is dated 2026-03-23 |
| 2026-05-31 | `get_rs_accelerators`, `get_rs_recovery_slope` (ADR 0007) | cloned from the leaders' liquid branch — carry the clause by copy, not by decision |
| 2026-07-20 | `get_rs_recovery` (#492) | written fresh, without it |
| 2026-09-17 | deal pin on all six | the docstrings and this section assert ONE universe (*"a per-ticker classification every downstream surface inherits"*) — the recorded INTENT, which the split contradicted |

⚠ **"Inherits for free" (09-17, above) was true only of the pools that happened to carry the
clause.** Nothing is inherited: each pool's SQL is its own, and only the gate makes the six agree.
That is the #673 correction to this section's own wording.

**Why keep the read-side clause when the write side already filters?** The write filter FAILS OPEN
— `rs_engine.run_rs_engine` reads `if cs_tickers and ticker not in cs_tickers`, so an empty
`mi_security_types` scores everything — and 1,848 of today's ~2,400 scored rows are UNTRACKED (no
`quote_type` row), so on that failure only `SKIP_TICKERS_LIST` catches SPY / TQQQ. Two
classifications, both needed; the leaders board has carried both since the day they were born.

**This is not "subtle RS wants a wider universe".** `get_rs_recovery`'s docstring argues for a wider
RS *floor* (composite ≤ 45 catches the V-turn that the ≥ 40 velocity floor hides) — that is about RS
thresholds, not asset class. No file in `docs/setups` or `docs/architecture` gives velocity,
turners or recovery the ETFs.

**Two escapes, both written:** `get_rs_leaders(min_adv=0)` is the documented raw-universe branch
(its docstring; used only by the scheduler's sector-enrichment pass) and applies NO classification;
and the `UNIVERSE-EXCEPTION:` marker above.

**Dormant today, by the numbers (prod, 2026-09-19):** 70 ETFs hold 853 `mi_stock_scores` rows, the
last dated 2026-03-23; the current scored set is 533 EQUITY + 1,848 untracked + **0** non-equity.
So this change moves no name off any board today; it is the guard for the day the write filter
fails open.

⚖ **Two FINDINGS, deliberately NOT changed** — read-path population only; either would change what
RISING / ROTATION WATCH / RECOVERY show *today*, and that is the operator's call:
1. **Liquidity and small-cap-healthcare still split 3/3 — but liquidity's OWN mechanism was
   defective, fixed 2026-09-20 (#673(b), see below).** `min_price` $10 and `is_sector_filtered`
   (Healthcare < $50) remain leaders/accelerators/recovery-slope only, POLICY and unsized here.
2. **`get_ma_pullbacks`** (the brief's PULLBACKS section) carries skip / ADV / price / sector but NOT
   the `quote_type` clause — it predates the 03-23 hotfix too — and sits outside the derived pool
   list (optional `tickers`, no `limit`), so the gate does not see it.

### 🔒 The leaders liquidity floor was a SHARE count, not a DOLLAR floor (#673(b), 2026-09-20)

**`get_rs_leaders`, `get_rs_accelerators` and `get_rs_recovery_slope` gated `min_adv` on
`mi_stock_scores.adv_20`, which `db.py:4356` documents as raw SHARES — a ~100x stricter floor in
dollar terms for a $500 stock than a $5 one.** Measured on prod, 2026-09-20: **STRL missed the
500,000-share floor by 2,222 shares while trading $258,187,493/day** (`adv_20` 497,778 x `close`
$518.68) — a >=20R tradeable winner on the must-not-miss fixture
(`tests/fixtures/must_not_miss_eps.py`). Of **488 of 2,354 scored names the share floor blocked,
ZERO traded under $10M/day** — the floor was filtering on PRICE, not liquidity.

**Why NOT spread the bar to velocity/turners/recovery instead (the plan reversed the same day):**
propagating the (broken) share floor there would have dropped STRL from RECOVERY as "illiquid" —
the defect was in the mechanism, not in whether velocity/turners/recovery need a floor at all. They
stay unfiltered, per the operator's standing FINDING above.

**THE FIX:** `(adv_20 * close) >= min_adv` in all three, matching the shape `ep_detector.py:2155`
already uses for EP admission (`adv_dollar = adv_20 * prev_close`) and the existing
`get_top_dollar_volume_universe` helper (`db.py:11045`, `(adv_20 * close) >= $2`). Default raised
`500_000` (shares) -> `10_000_000.0` (dollars/day) — the same #673 measurement found the scored
universe's OWN floor is already $10.0M/day (p05 $12.5M, 2,354 names), so **this excludes ZERO
names today.** It is a guard against a future universe change admitting sub-$10M names, not a live
filter: names enter (the 488 the share floor wrongly blocked), none leave.

**Gated:** `tests/test_deal_pinned_not_a_coverage_gap.py` §#673(b) — behavioural, against a
recording connection (never `inspect.getsource` for the SQL shape): the statement each of the
three pools actually sends must compare `(adv_20 * close)`, never bare `adv_20`; the bound
parameter must be the pool's own live default, not a hardcoded copy; `get_rs_velocity` /
`get_rs_turners` / `get_rs_recovery` must carry no `min_adv` parameter at all. Four mutations run
RED: the SQL reverted to a bare share compare, the default reverted to 500,000, a `min_adv`
parameter added to `get_rs_velocity`, and the default raised past STRL's own dollar volume.

⚖ Read-path board filter only — no entry, exit, sizing or safeguard changed. `min_price` and
`is_sector_filtered` are untouched, per the task that shipped this (explicitly out of scope,
not measured here).


## How a NEWS-PROVIDER failure scores a theme (#679, 2026-09-21 — the guard existed and could not fire)

**The rule, and it is not new: a Perplexity failure must NEVER be scored as a finding about the
theme.** `_news_check` (`theme_engine.py`) returns `(news_score, description, api_err)`, and BOTH
its callers — **derived, not listed: `_rescore_existing_theme` (3825) and `_score_new_theme`
(6824), the only two `_news_check(` call sites in the module** — substitute a **neutral
`news_score = 15`** (half credit) when `api_err` is true, and `_rescore_existing_theme` also KEEPS
the theme's existing description rather than blanking it. The code comment has said so since the
behaviour was written: *"Perplexity is down/rate-limited — don't penalize the theme with score=0."*

🔴 **That guard had never once executed for a provider failure.** `collector.search_news_perplexity`
catches every exception, alerts, and returns `""` — its own comment reads *"Contract is UNCHANGED:
this only alerts, then we still return ''"*. So the outage reached `_news_check` as an empty answer,
took `if not answer: return 0, "", False`, and was recorded as the factual verdict **"no catalysts
found"**. The `except` arm that sets `api_err=True` was unreachable from below.

**What that cost, measured in prod rather than argued.** On **2026-09-04** four themes were capped
**Mainstream → Nascent** between **17 and 27 milliseconds** after their own `api_failure_perplexity`
audit row — Latin American Silver (17:01:28.127 ← .100), IT Consulting (17:01:30.590 ← .573), Life
Sciences (17:02:05.410 ← .388), Office REIT (17:02:42.955 ← .938), all `reason=empty_description`.
`ep_theme_belonging.THEME_BONUS_STAGES = ("Accelerating", "Mainstream")`, so **every member ticker
of those four themes lost the EP theme-belonging bonus because a news API timed out.** Two of the
four were HTTP 400s and two were timeouts — any provider failure does this, not just a 429.

**The fix:** `search_news_perplexity(..., raise_on_failure=True)` — an opt-in the theme engine
passes and the other ~12 callers do not, so their fail-open contract is byte-identical. The failure
now reaches the guard the engine already had.

⚠ **WHAT THIS DOES NOT MEAN, and the distinction matters for any future analysis of history.** A
zero news score is **NOT** a marker of a provider outage. `_is_garbage(answer)` returns the
byte-identical `(0, "", False)` from a **successful** call whose answer said there is no news, and
**2026-07-21 carries a zero-news theme row on a day with no provider failure of any kind**. Outage
and genuine-no-news were indistinguishable in the stored data. This change removes that ambiguity
**going forward only** — no historical theme score, stage or description is restated by it.

⚖ **Classified as a BUG FIX, not a criteria change**: it restores behaviour the code already
documents and intends, under the operator's 2026-08-27 ruling — *"make sure any issue with
perplexity doesn't affect live trades, just render as no-op or unavailable input."* A timeout
demoting a theme and stripping its tickers' EP bonus is the opposite of a no-op.

## Change log

### 2026-09-25 — #657 Shape A: the two REMOVAL sites now get the run's co-movement context (OPERATOR-SIGNED "Yes to both")

**Trigger**: his 2026-09-13 instruction when he split the membership-test change ("swap job 1 and
leave job 2") also filed a task to look into job 2 — *"file task to look into 2nd part and
eval/analysis"*. #657 (`docs/analysis/657_comove_removals_2026-09-25.md`) did that: measured, the
09-13 split created a LOOP — a name the tape admits at assignment is stripped by the sector-label
strips within days, because those two strips never saw the context the admission gate already
uses. Two independent verifiers re-ran the probe the same night and rejected the doc's original
recommendation (evict); the doc's §CORRECTED section is the one that governs. His ruling
2026-09-25: *"Yes to both"* — this entry is the Shape A half; the other half is the sector-cap
re-homing bug fix (the next entry, SR/ATO in a tanker theme).

**Evidence** (`docs/analysis/657_comove_removals_2026-09-25.md`, $0, read-only replay through the
live functions, byte-for-byte reproduced by both verifiers):
- **The loop**: 21 distinct cross-sector (stock, theme) pairs the tape admitted OVER the sector
  label since 2026-09-13; **16 of 21 were stripped again by the label as `sector_outlier` within
  7 days (observed 1-3)**; 9 of 21 were admitted at least twice and 3 (BAH, IRDM, VSAT) re-admitted
  twice or more, each bounce re-spending an assignment proposal and a validation for nothing.
- **Shape A's dry read, today's board (2026-09-24)**: 8 singleton-sector memberships exist (the
  only members either strip ever touches). Passing the run's `comove_ctx` to both strips would
  KEEP 7 of 8 (OKLO 0.90, LEU 0.84, MAS 0.68, PUBM 0.66, TNET 0.61, VSAT 0.49, WLTH 0.40 — all
  ≥ 0.35) and STRIP 1 of 8 (AGRO 0.09 — which the label strips anyway, so nothing is lost there).
  Shape A can never evict a same-sector member — the full-tape eviction rule ("Shape B", 52 of 608
  judgeable memberships below the bar today) is a different, larger, evidence-mixed question the
  doc leaves undecided (the one clean out-of-sample window splits 29 of 58 vs 29 of 58) and is
  **NOT** part of this change.

**What changed** (`agents/market_intelligence/theme_engine.py`):
- The nightly carry-forward strip call (`run_theme_engine`'s call to
  `_apply_carryforward_deterministic_filter`, just below where `comove_ctx` is built each run) now
  passes `comove_ctx=comove_ctx` instead of omitting it.
- The birth strip call (`_discover_new_themes_single`'s call to `_strip_sector_outliers`) now
  passes `comove_ctx=comove_ctx` — the parameter was already in scope (a no-op function argument
  since the 2026-09-13 change) but never forwarded.
- Both strip FUNCTIONS were unchanged — they have honoured `comove_ctx` since 2026-09-13 (see that
  entry); only their two production callers withheld it. `comove_ctx=None` (toggle off, or the
  nightly closes read failed) is the byte-identical pre-2026-09-25 path at both sites — verified by
  test, not just by the default argument.

**What did NOT change**: nothing else on the removal path. Same-sector members are never touched
by either strip (the sector-identity logic that gates which tickers are even candidates for
`_comove_verdict` — singleton sector, ≥3 members total — is untouched). No other removal arm
moved: the ban filter, the cooldown filter, the deal-pin arm (#671), Mon/Wed/Fri validation, the
min-survivor guard, the mass-eviction rename (#214). The ASSIGNMENT gate (2026-09-13) is untouched.
Shape B (evict any judgeable member below the bar, sector ignored) was **NOT** adopted — that
remains his open call, tracked in #657, not decided here. The stale SSoT sentence this entry
corrects: the "Membership test" summary bullet above said the two strips "accept the context but
are NOT passed it" — true from 09-13 to today, now updated to match the code.

**Anticipated effect**: the loop stops for singleton-sector members — the `assignment_comove_admitted_over_sector`
→ next-night `sector_outlier` bounce (measured 16 of 21 pairs since 09-13) should fall toward 0 for
singleton-sector pairs (a same-sector re-admit can still bounce for unrelated reasons — unaffected
by this change). ⚠ The carryforward strip writes an audit row only when it REMOVES something, so a
theme whose only change is keeping a singleton writes no row, and the birth strip writes none at all —
`comove_kept=` rows are NOT a usable verify signal (review 2026-09-25). Verify against #657's
DONE-WHEN instead: no `sector_outlier` strip of a member reading at or above the bar that night. **Exception, by construction, not a bug**:
a singleton in a 3-member theme gives leave-one-out only a 2-name basket — `thin_basket`,
`admit=None` — so it still falls to the label exactly as before (on today's board 24 themes have 3
judgeable members and 12 have 2). The verdict needs at least 3 OTHER members with enough overlapping
history, so the bounce ends only where the rest of the theme can be read.

**Reversion-flag**: REFINEMENT of the 2026-09-13 change (`docs/architecture/theme_engine.md`
2026-09-13 entry) — closes a gap that entry's own design section named as a risk ("Left alone they
would have turned the change into nightly churn") but the 09-13 SPLIT ruling deferred. Not a
reversal: job 1 (assignment) is untouched, and job 2 still uses the sector label for every
same-sector member — only the singleton-sector case moves.

**Status**: built; verify-live = #657's DONE-WHEN in PLAN.md (5 nightly runs with no `sector_outlier`
strip of a member at or above the bar that night, and an above-bar cross-sector member kept 3 nights
running). Tests:
`tests/test_theme_assign_comove.py` (4 new, through the real call sites — `run_theme_engine` and
`_discover_new_themes`/`_discover_new_themes_single`; the two context-present tests go red on the
pre-2026-09-25 wiring, the two no-context tests pin the unchanged path; 17 total in the file).

### 2026-09-25 — BUG FIX: the sector cap moved members into a theme they never passed the membership test for (SR / ATO in a tanker theme)

**Symptom (verified on prod).** 'Regulated Natural Gas Distribution Utilities' (SR, ATO) was retired on
2026-09-24 with `parent='(unknown)'` and both names appeared in 'Crude & Product Tanker Shipping' the
same night, reading 0.105 and 0.2665 against it (`ASSIGN_COMOVE_BAR` 0.35). No LLM judged the pair.

**Mechanism.** `_merge_overlapping_themes` Pass 2 (the keyword sector cap — `_SECTOR_KEYWORD_GROUPS`)
keeps the top N themes whose NAME matches a group and, in the int-cap branch, absorbed every further
match into the group's top theme by blind union: `top_theme["tickers"] = list(existing | extra)`. "gas"
put a utilities theme in `oil_gas`; the Mainstream tanker theme ("crude") held the top slot. No ticker
overlap was required (unlike Pass 1 and Pass 1.5, which fire only on shared members), no verdict, no
validator, and no audit row — which is also why the retire path had no successor pointer. Prod log line
`2026-09-24 21:08:30 … Theme merge (sector cap): 'Regulated Natural Gas Distribution Utilities' → 'Crude
& Product Tanker Shipping' (sector group 'oil_gas', 2 tickers absorbed)`. The prod file logs (eleven
rotations, from 2026-04-15) carry 470 such lines; the 203 absorbs since 04-30 that the replay can
reconstruct moved 1,783 members — 177 of 207 names two or more times (TALO 32×), because a strip or the
validator took most out within a day (834 of 1,559 departed arrivals lasted one day) and the next
night's cap put them back. It fed the #214 mass-flag rename three nights running this month, and on
09-25 fat-split the tanker theme (11 gas E&Ps in, 4 real tankers out to a child). Finding:
`docs/analysis/657_comove_removals_2026-09-25.md` § "Re-homing defect (fixed 2026-09-25)" — every
current membership that arrived this way, derived by `scripts/probes/_rehome_sector_cap.py` (45 on the
09-25 board; the fixed code rejects 29 of them at the branch, admits 16; EMBJ / RTX / AGRO, the
"untraceable" joins in #657's body, are among them).

**Fix (`_admit_rehomed_members`).** A member the cap would move must first pass: operator exclusion and
live validation cooldown for the target, then the tape (`_comove_verdict` against the target's current
members, bar 0.35). **A pair the tape cannot judge (no context / no history / thin basket) is NOT moved —
fail closed**; it returns to the pools and the normal assignment funnel can still admit it later through
the full test. With no context at all, the cap moves nothing. ⚠ Revised the same night after review: the
first cut sent unjudged pairs to `_validate_theme_membership`, which returns its input unchanged on any LLM
error (an outage re-created the blind union), and which judged and cooled down the TARGET's own members
and wrote per-name removal rows under the target's name that the #214 check reads as a mass eviction
(blocking the name for 30 days). `_merge_overlapping_themes` takes the run's `comove_ctx`,
`changelog`, `protected`, `cooldown_set`, `theme_exclusions` (both call sites in `run_theme_engine` pass
them; defaults None keep every other caller's signature). The cap's keep/absorb structure, the per-family
biotech branch, the cap-0 drop and every Pass-1/1.5 guard are unchanged.

**Audit + successor.** One row per absorb: `theme_sector_cap_absorbed` (≥ 1 admitted; summary
`Pass2: 'source' -> 'target': admitted k of n member(s) (sector group 'g')`, detail = every member's
path / reading / verdict as JSON; also written when a member already sits in the target, which is then its
successor) or `theme_sector_cap_not_absorbed` (none admitted and none already there; the source was
absorbed by nothing, so no successor, and its retire note says "dropped by the sector cap — no member
passed the membership test for 'target'"). The engine-drop retire lookup now reads both rows through the
pure `_successor_pointers_from_audit_rows`, so a cap-retired theme points at its successor instead of
`(unknown)`.

**Tests.** `tests/test_theme_sector_cap_rehome.py` reproduces the SR/ATO shape (three oil_gas-named
themes, disjoint rosters so only Pass 2 can move a member): the tape rejects SR/ATO and admits a
co-moving control; no context → nothing moves; an unjudgeable pair is not moved and never reaches the
validator; cooldown and exclusion hold; the audit row carries the successor pointer (also for a source
with a member already in the target); an all-rejected source has none. Observed RED on the pre-fix branch (`SR` in the tanker roster), green after.
`test_sector_cap_int_groups_unchanged` now patches the validator (admit-all) and locks the cap structure
alone.

**Not changed, stated.** Pass 1 (overlap ≥ 0.6 with ≥ 3 shared) and Pass 1.5 (≤ 3 members, ≤ 1 unique,
≥ 1 shared with the target) still union on overlap evidence without a per-member verdict; they are not
the zero-evidence path and were left alone — whether they should carry the same test is a separate
question for him. Deploy: `theme_engine.py` loads in `apollo-execution` too — two steps (`market-agent`
+ `execution`).

### 2026-09-20 — #661: the assignment LLM call has a SEAM — the EP money path no longer runs through the nightly batch driver (REFACTOR ONLY; old-vs-new replay byte-identical)

**Why**: `_propose_assignment_batch` — the nightly pass's multi-turn driver (advisor-consult loop,
truncation handling, batch-numbered telemetry) — had grown four bolt-on kwargs (`allow_advisor`,
`caller`, `audit_prefix`, `sink`) on 2026-09-13 so `judge_theme_fit` could reuse it. That put every
edit made for the NIGHTLY pass on the path that decides whether an EP alert gets its +10 and can
cross into HIGH. Safe as shipped (the forced tool made the advisor branch unreachable — dead code,
not a fork); the risk was the next edit. Found by the 2026-09-14 altitude review.

**What changed** (`theme_engine.py`, no prompt / bar / criterion / tool-schema change):
- The primitive is factored out and BOTH callers use it directly. `_assignment_body(stocks,
  cooldown_note, batch_note)` renders the prompt body ONE way; `_assignment_messages(prefix, body)`
  builds the cache-split opening turn; `_assignment_turn(client, messages, *, tools, tool_choice,
  caller)` makes ONE bounded call (same model, ceiling, `thinking=DISABLED`), meters it, and parses
  the result into `_AssignmentTurn.outcome` ∈ `proposed` / `truncated` / `silent_stop` / `consult`.
  `tools`, `tool_choice` and `caller` are REQUIRED keywords — there is no default a later edit could
  flip one caller onto the other's setting. No audit rows and no log lines live in the primitive.
- `_propose_assignment_batch(client, batch_stocks, shared_prefix, cooldown_note, advisor_state,
  batch_no, n_batches, pool_size)` is now the NIGHTLY wrapper: it appends the advisor paragraph
  (`_ASSIGNMENT_ADVISOR_NOTE`), offers both tools with `tool_choice=any`, loops on `consult`, and
  writes `assignment_llm_proposed` / `assignment_silent_stop` verbatim. **The four kwargs are gone.**
- `judge_theme_fit` calls `_assignment_turn` directly with the assign tool ALONE and FORCED
  (`_ASSIGN_TOOL_FORCED`), writes its own `ep_theme_fit_llm_proposed` / `ep_theme_fit_silent_stop`
  rows (same event names AND the same detail keys as before — batch 1/1, pool 1, advisor_calls 0 —
  so anything written against them since 09-13 keeps reading), and never enters the loop.

**The ONE input on which behaviour differs, stated rather than found**: a `consult_advisor` block
arriving on the EP path. Impossible live (the forced tool cannot produce it); the OLD code would
have entered the advisor loop there (the dead branch), the NEW code returns `FIT_FAILED` "no
verdict (consult)" with no Opus call and no second turn. That is the seam doing its job. The only
other visible difference is a LOG line: a truncated / silent EP call used to log the nightly's
"Theme assignment batch 1/1 TRUNCATED…" text and now logs "ep theme fit: TK — no verdict (…)".
Log lines are not audit rows and nothing reads them.

**Proof it is a pure refactor** — `scripts/probes/_661_assignment_seam_replay.py` (output:
`_661_assignment_seam_replay_out.txt`): the pre-seam `theme_engine.py` is read out of git
(`git show a25b6113:`) and exec'd beside the new one in ONE process; both are driven through the
REAL `_assign_uncovered_to_themes` and the REAL `judge_theme_fit` against identical scripted model
responses that walk every branch (advisor consult → propose with a cross-batch echo → direct
propose with a non-existent theme → truncated batch; silent stop → advisor budget exhausted;
six EP cases). Every `messages.create` kwargs (the prompt bytes incl. batch/cooldown notes and the
advisor paragraph, `tools`, `tool_choice`, model, ceiling, thinking, the advisor-turn follow-ups),
every cost-meter call, every audit row (type, summary, detail), the proposal list as applied
(changelog + remaining), and each EP verdict: **0 differing lines over 51 events**. A one-byte
prompt change shows as 8 differing lines, so the zero is not vacuous. ⚠ It proves the CODE turns
identical model output into identical requests and records; the raw model output of a real night
is not stored anywhere (only the proposals are), so the branches are scripted, not recorded. No
paid call.

**Tests** (`tests/test_ep_theme_fit.py` §4, each run RED against the mutation its docstring
names, then restored): the EP path never enters the batch driver · never reaches the advisor even
if the model asks (one turn, no Opus, no nightly row) · the four kwargs are gone · the primitive
has no defaults · the nightly loop still threads a consult through the primitive. The existing
forced-tool assertion was also driven RED by loosening the EP `tool_choice` to `any`.

### 2026-09-18 — #660: the market-adjusted correlation maths moved to its own module (PURE MOVE, verdicts byte-identical)

- **What**: `session_index`, `log_returns`, `excess_returns`, `usable` (was `_usable`), `_basket_mean`,
  `build_baskets`, `correlate`, `ThemeBasket` and the constants `BELONGING_LOOKBACK_SESSIONS` (60),
  `BELONGING_MIN_OVERLAP_SESSIONS` (30), `BELONGING_MIN_BASKET_MEMBERS` (3), `MARKET_TICKER`,
  `CALENDAR_DAYS_FOR_LOOKBACK` (100, was the private `_CALENDAR_DAYS_FOR_LOOKBACK`) now live in
  `agents/market_intelligence/market_adjusted_correlation.py`. `ep_theme_belonging.py` and this
  engine import it as a PEER; the lazy cross-imports inside `_load_comove_context` /
  `_comove_verdict` are gone, and nothing outside `ep_theme_belonging` reads a `_`-prefixed name of it.
- **Why**: the nightly engine depended on an EP-named module for generic maths, including a private
  constant (2026-09-14 altitude review). `correlation_engine.py` was NOT the home — its adjustment is
  a beta residual, this is SPY subtraction, and the 0.35 bars were measured on the subtraction.
- **What did NOT move**: `fetch_closes` (the `mi_daily_closes` read — I/O; `_load_comove_context`
  still calls `etb.fetch_closes`), both bars, the stage sets (`build_baskets` in the EP module keeps
  its `BELONGING_SHADOW_STAGES` default as a thin wrapper; the peer's `stages` is required).
- **No bar, threshold or criterion changed.** Evidence: the same harness run before and after over 7
  synthetic tapes (holes, thin history, flat closes, 2-member baskets, leave-one-out, no-SPY failure
  path) — 6,082 correlate / verdict / read values plus the context loader's fetch window and excess
  arrays, serialised byte-exactly, identical (commit message carries the checksums). Suite green with
  ONE test line changed (an import path: `etb._basket_mean` → `mac._basket_mean`).
- **Deploy**: `ep_theme_belonging` loads in `apollo-execution`, so the new module does too —
  `scripts/exec_loaded_modules.txt` regenerated; a deploy is `market-agent` + `execution` (#456 class).

### 2026-09-13 — THE MEMBERSHIP TEST ASKS THE TAPE: market-adjusted co-movement at 0.35 replaces the sector-identity test (OPERATOR-SIGNED, shipped ON, one-flag revertible)

> 🔒 **TWO RULES SIGNED 2026-09-14, AFTER the backtest — read these with the entry below; they are
> part of the change, not footnotes to it.**
>
> **RULE 1 — BATCH ORDER MUST NOT DECIDE MEMBERSHIP. The deferred, ordered second pass is
> DELIBERATE (operator 2026-09-14: *"keep it, and write it into the SSoT as a deliberate rule"*).**
> The apply-loop appends each admit to `theme["tickers"]` as it goes, so whether a proposal meets a
> judgeable basket depends on where the LLM's batching happened to put it. **This is not
> hypothetical: IREN on 2026-09-08 was proposed BEFORE BTDR in the same batch, was judged against
> CIFR+CORZ alone, could not be judged for want of members, fell through to the sector test — and
> was rejected. That is the headline case of this entire change, lost to batch order.** So a pair
> the tape cannot judge **ONLY** for `thin_basket` is deferred to a second pass after the run's
> other admits have landed, and that pass is ORDERED so the pairs the sector label would admit go
> first (they land regardless), giving the tape the largest basket the night allows.
> ⚠ **Fail-safe is unchanged:** a pair still thin on the second pass takes the sector test, exactly
> as before. Every other check re-runs on a deferred pair and is idempotent. **Only `thin_basket`
> defers** — a pair the tape judged and REJECTED is not given a second chance to pass, which would
> be shopping for a verdict.
> ⚠ It was originally added by the build agent beyond its instruction. It is signed now because it
> is right, not because it shipped — the reasoning above is the justification, and it belongs in the
> SSoT rather than in a code comment nobody re-reads.
>
> **RULE 2 — THE BAR STAYS SYMMETRIC, AND THE EXPECTATION MOVED INSTEAD (operator 2026-09-14:
> *"keep it as you signed; fix the expectation instead"*).** The swap was signed as a REPLACEMENT of
> the sector-identity test, so the tape decides both directions: it admits cross-sector pairs the
> label rejected **and** rejects same-sector pairs the label would have kept. Narrowing it to
> cross-sector pairs only would have made pre-registration P1 (*member count rises*) safe — and
> that was the wrong fix, because **P1 could not fail either way: a flat member count is produced
> identically by a change that works and one that does nothing.**
> **What changed is the instrument.** `comove_stats` counted `admitted_over_sector` and had **no
> mirror**, so the cost side of a symmetric test was invisible. It now also counts
> **`rejected_over_sector`** — pairs the label would have ADMITTED that the tape threw out — and
> both appear on the summary log line and in the `assignment_comove_summary` audit row.
> **P1 is retired and replaced by P1a/P1b** in `docs/analysis/cross_industry_themes_2026-09-13.md`:
> P1a = `admitted_over_sector` ≥ 1 per trading week (the change does something); P1b =
> `rejected_over_sector` ≤ `admitted_over_sector` over 15 days (it does not cost more than it buys).
> ⚠ **`rejected_over_sector` has NO historical baseline — it was never instrumented.** The first 15
> days ARE the baseline, and that is stated rather than papered over. If P1b fails, narrowing the
> test to cross-sector pairs returns to him as a real decision backed by a number.


**Trigger**: the operator's question 2026-09-13 — *"can a theme span more than one sector? I lean
yes, but we should verify"* — answered in `docs/analysis/cross_industry_themes_2026-09-13.md` (3 of
3 measurement angles survived adversarial refutation), then his sign-off on the bar, the
admit/reject case table and the money-path exposure (*"I thought I already signed it, you asked me
earlier"*). The case that named it: **IREN** excluded from `Emerging Bitcoin Miners Diversifying
into AI/HPC Hosting` — the theme named after his own #491 concept — solely because
`mi_stock_scores` files IREN as Financial Services and CIFR/CORZ/BTDR as Technology, while IREN
co-moves with them at 0.70–0.83 (as tightly as they do with each other).

**What was wrong (REVERSAL — the prior reasoning, and why it was wrong)**: the sector-outlier
post-filter was introduced 2026-03-16 (commit `0dd09144`: *"stricter discovery prompt requires 3+
tickers, genuine industry fit, sector outlier post-filter"*) as a PROXY for "genuine industry
fit", copied to the assignment gate (telemetry added 2026-05-08, `66476697`, #46) and to the
nightly carryforward strip 2026-05-15 (`3f0233ea`). Its premise: *a name whose top-level sector
differs from every other member does not belong to the group.* Measured, the premise is false —
not incomplete, false: the names the label ADMITS co-move with their themes at 0.65 and the names it
REJECTS at 0.61 (analysis, 389/83 pairs), 0.58 vs 0.65 in this replay (504/98 pairs); a random
board stock sits ≈0.05. The label was testing the data vendor's filing cabinet (MSTR "Technology"
among "Financial Services" peers, CMC "Industrials" among "Basic Materials" steel, PACS
"Healthcare" among "Real Estate" nursing REITs, converting miners split three ways), not the
tape. And its real cost was starvation, not coherence: 29 of 46 strip events left a theme under
the 3-member floor.

**What changed** (`theme_engine.py`, section "MEMBERSHIP TEST"):
- **`ASSIGN_COMOVE_BAR = 0.35`** — its own constant (registered in
  `scripts/gate_provenance_registry.py`), with the derivation and the PER-PAIR warning at the
  definition: the same number used to pick the BEST of ~119 themes admits nonsense (Dominion Energy
  matched a fracking theme at 0.45); here the LLM has already nominated one pair and the test
  judges that pair. `ep_theme_belonging.BELONGING_CORR_BAR` carries the same value for that other
  use and the two are free to diverge.
- **The maths is `ep_theme_belonging`'s** — `fetch_closes`, `session_index`, `log_returns`,
  `excess_returns`, `build_baskets`, `correlate` — imported, so the EP scan and the nightly engine
  cannot disagree about what "co-moves" means. *[2026-09-18, #660: the maths now lives in
  `market_adjusted_correlation.py`, a peer both modules import; only `fetch_closes` (the closes
  READ) stays in `ep_theme_belonging`. See the 2026-09-18 entry.]* Its `prepare_basket_context` was NOT reused: it
  builds baskets only for `BELONGING_SHADOW_STAGES` (assignment offers Fading themes too) and its
  module cache is the EP scan's own cost lever. `_load_comove_context` builds the nightly context
  from the same primitives: ONE read of members ∪ RS leaders ∪ velocity ∪ turners ∪ cluster names
  ∪ SPY, strictly before the run date (the fetch asks `< run date` and `session_index` re-applies
  it).
- **Three sites, one rule.** Assignment (`_assign_uncovered_to_themes`): where the tape can judge,
  it decides the pair and supersedes the whole sector block, keyword/description fallbacks
  included (they exist only because the label was blind); where it cannot, `_sector_identity_gate`
  — today's block extracted verbatim — decides. Birth strip and carryforward strip: a
  singleton-sector member is kept when it co-moves ≥ bar with the rest (leave-one-out), stripped
  when it does not, stripped as before when unjudgeable. **The strips had to move with the gate**:
  the analysis called them secondary because relaxing them ALONE changes nothing — true — but once
  assignment admits IREN on night 1, the carryforward strip removes it on night 2 before the LLM
  sees the board. Left alone they would have turned the change into nightly churn.
- **Fail direction, explicit**: no history, fewer than 30 overlapping sessions, a basket with
  fewer than 3 members that have history, a failed closes read, toggle off → TODAY's sector test at
  that site, byte-for-byte (`comove_ctx=None` IS that branch). Never a silent admit. ⚠ The sector-cap
  re-home (2026-09-25) is the one site with no sector fallback: an unjudged pair is simply not moved. Consequence,
  stated: a 3-member theme can be JOINED (basket 3) but a 3-member theme with a singleton cannot
  KEEP it via the strip (leave-one-out basket 2) — today's behaviour by construction; the guards
  are shared with the EP scan and were not forked to change it.
- **Two passes per run** (the one design decision beyond the instruction): the apply-loop appends
  admits to `theme["tickers"]` as it goes, so whether a proposal to a 2-member theme meets a
  3-member basket depended on where the LLM's batches put it. IREN on 2026-09-08 was listed BEFORE
  BTDR in the same batch, met CIFR+CORZ alone, could not be judged, and the label rejected the
  headline case. A pair thin only for want of members is deferred to a second pass after the run's
  other admits land, ordered sector-admit first (they land whether or not the tape can see them);
  a pair still thin then takes the sector test. Every other check re-runs on the deferred pair and
  is idempotent.
- **Toggle `theme_assign_comove`** — reversion only, DEFAULT ON (`db.get_runtime_toggle`:
  `mi_safeguard_state` row > env `THEME_ASSIGN_COMOVE_ENABLED` > default true; fail-open to the
  default on a read error — a grade-quality toggle, not capital). OFF = the pre-change engine at all
  three sites. Revert, no redeploy, ~60s cache lag: `INSERT INTO mi_safeguard_state (safeguard,
  account_mode, state, last_transition_at, updated_at) VALUES ('theme_assign_comove', 'global',
  'off', NOW(), NOW()) ON CONFLICT (safeguard, account_mode) DO UPDATE SET state = EXCLUDED.state,
  updated_at = NOW();` Nothing in the code writes that row.
- **Audit**: `assignment_comove_admitted_over_sector` and `assignment_skipped_comove_below_bar`
  (both carry `corr`, `overlap_sessions`, `basket_n`, `bar` and the SECTOR COUNTERFACTUAL — the
  pre-registration's P4 is readable from prod without a new instrument),
  `assignment_comove_summary` once per run (judged / admitted / admitted-over-sector / rejected /
  unjudgeable — the POSITIVE observable verify-live reads), `theme_comove_context_failed` when the
  read fails; the carryforward aggregate row gains `comove_kept=[…]` / `comove_below_bar=[…]`.
- The assignment PROMPT is unchanged and carries NO sector rule (*"Only assign if the stock's
  business CLEARLY matches the theme's thesis"*) — the gate was the binding constraint, not the
  prompt; U3 (the model has never been told cross-sector is allowed) stays a live-weeks question.

**Evidence** — `docs/analysis/assignment_comove_backtest_2026-09-13.md`, $0, the LIVE
`_comove_verdict` replayed over the last 60 trading days (2026-06-17 → 09-11, 60 nightly runs, 710
proposed pairs), each pair judged on the sessions strictly before its own night against the members
assignment saw (prior row − that night's strip + earlier admits, two passes as built):
- 602 of 710 pairs judgeable; 108 fall to the sector test (88 thin basket, 5 no history, 15 no
  prior row).
- **Admitted now, sector rejected: 88 of 98** judgeable sector-rejections (90%). **Rejected now,
  sector admitted: 95 of 504** judgeable sector-admissions (19%) — 75 of them had survived LLM
  validation and sat on the board that night.
- **IREN → the miners theme, 2026-09-08: ADMITTED at 0.83** over 60 sessions against 3 members
  (via the second pass — BTDR lands first).
- Named checks: MSTR 0.78–0.88 admit, CMC 0.76 admit, GPN 0.63–0.73 admit (15 nights), ECO →
  Hormuz 0.20 reject; ECO → the tanker themes 0.58–0.81 ADMIT (the analysis listed that add-back as
  legitimate — its −0.11 was a ±10-session read on the Hormuz theme); AGX 0.59 admit on 09-10 vs
  0.33 reject on the 09-11 board — sits at the bar. OTTR and SEDG were not sector-rejected inside
  the window.
- Returning names: **14 of 19** candidates clear the bar (4 refused: MAX 0.35, AGX 0.33, FIVE
  0.29, WLTH 0.24; 1 unjudgeable). The analysis's "26" was a rule-OFF count from 06-01 and included
  themes retired since (the miners theme) and an empty theme; 9 of the 11 names in its board table
  reappear here.
- Board 2026-09-11: 119 themes, mean members 6.03 → 6.15, ≤5-member share **70% → 66%** (83 → 79
  of 119) with the add-backs alone; **5.85 and 70% again** once the members the tape would have
  refused at assignment are removed too (a counterfactual — deploying does NOT remove them; the
  strip re-tests singleton-sector members only). **P1 may REFUTE under the symmetric bar**: 95
  refusals vs 88 admits over the window means the member count is more likely to fall than rise
  over weeks; narrowing the tape to cross-sector pairs only would remove that risk — ⚖ his call,
  not pre-decided. Likewise U1 only pre-registered the increase: same-sector refusals mean fewer
  FUTURE +10 carriers.
- Tightness across the 9 changed themes **0.53 → 0.55** (7 tighter, 2 looser); the matched random
  same-sector control lands at **0.48** — the returning names behave like members, random names do
  not. PACS is the one add the control beats (158 of 300 draws).
- Money path (U1): stocks carrying the +10 bonus **178 → 182** (ASC, ECO, BAH, PACS land in
  Accelerating themes) — the pre-registration said ~183.
- Starvation (P2): strips that left a theme under 3 members **27 → 19 of 44**; the tape keeps 27
  of the 58 singleton-sector members stripped in the window.

**Not pre-registered, found by the replay**: the bar is SYMMETRIC and the pre-registration modelled
only add-backs. The larger flow in pair-count is the refusals: 95 sector-admitted pairs the tape
rejects — HOOD → Wealth Management (−0.01, 0.01), ORCL → AI enterprise analytics (0.04), PYPL →
consumer fintech (0.08), MSFT (0.30), BOX (−0.17), ROKU (−0.03) — thematically plausible names that
do not move with their basket over 60 sessions. That is what "the tape decides" means; it is
reported here so the shape is his to keep or narrow (e.g. tape decides cross-sector pairs only),
⚖ not pre-decided.

**Anticipated effect**: ~1.5 cross-sector admits and ~1.5 same-sector refusals per night (88 and
95 over 60 nights); `assignment_skipped_sector_outlier` falls to the unjudgeable residue (~2 a
night); the ≤5-member share drifts under 70% over weeks if P1 holds; boosted-stock count stays under
190 if his EP prediction holds.

**Reversion-flag**: REVERSAL of the 2026-03-16 sector-outlier post-filter (`0dd09144`) and its
2026-05-15 carryforward copy (`3f0233ea`) — why the prior reasoning was wrong: above.

**Status**: shipped, awaiting field validation — measured against the pre-registration rows
P1–P4 / U1–U5 in `docs/analysis/cross_industry_themes_2026-09-13.md` (15+ trading days for the
drift rows). Tests: `tests/test_theme_assign_comove.py` (13, through the real functions).

### 2026-09-12 — #651: the judge's named groups are captured, and the read that turns them into "how late is the engine" is built — NOT yet run

**Themes touch no money; shipped full.** New: `judge_named_themes.py` (Haiku extraction over
`judge_rationale`, nightly `judge_named_themes_extract` 18:20 ET, table `mi_judge_named_themes`,
the recurrence + lead-time read), `scripts/judge_named_themes_651.py`, role
`JUDGE_NAMED_THEMES_MODEL` (haiku tier), ceiling `judge_named_themes`, shadow-writer registration.
No judge prompt/call-path change; not on the alert path. Tests:
`tests/test_651_judge_named_themes.py` (26). Finding:
`docs/analysis/651_judge_named_themes_2026-09-12.md` — the paid pass (~$0.07) could not be run
from the build card (no prod route), so the lateness number is still owed; the doc carries the
command. Section: "Judge-named theme capture (#651)" above.

### 2026-09-09 — #486: the naming lag, read — two cluster artifacts killed at the source, the recorder made truthful, cluster members rendered like every other pool

**Themes touch no money; shipped full (operator working rule). Rule sentences unchanged — the
disposition is the criterion and did not move.** Evidence: the two 09-08 recorder rows
(`/tmp`-captured once), `mi_correlation_clusters` + `mi_themes` for 09-08, and the local frozen
history (`scripts/probes/_step3_clusters.tsv`, `_step1_themes.tsv`, `_step2_closes.tsv`, 06-01 →
09-04). Tests: `tests/test_correlation_engine_artifacts_486.py`,
`tests/test_theme_cluster_rendering_486.py`, `tests/test_theme_discovery_shown_declined.py`.

- **The recall-mode "inversion" (0 of 12 taken vs the nightly's 3) is sequencing, not a
  permissive-mode bug.** The shadow runs ~8 min after `run_theme_engine` has persisted its births
  and reads them back through `get_active_themes()`; it is told not to re-create existing themes,
  so it (correctly) did not; the recorder credited "taken" only against a run's OWN proposals, so
  the three clusters the nightly had just named read as declined — 8 + 3 = the 11 reported.
  Fixed in the instrument (the `already_named` class), not by re-sequencing the shadow.
- **The two "strong but declined" clusters were not misses.** Tankers (RS 92): the nightly named
  them that night — *Crude Oil, Product & LPG Tanker Shipping* → live *Oil & Product Tanker
  Shipping*, score 75. Precious-metals miners (RS 89, 33 names): 31 of 33 already sat in five
  themes (Gold & Precious Metals Miners Rotation, Silver-Focused Primary Miners, Latin American
  Silver & Gold, Royalty & Streaming, Miners Velocity Breakout) — a correct decline, and a
  fragmentation problem, not a naming one. Every other 09-08 decline was RS 18-51 and/or already
  held (healthcare REITs 5/6, shopping REITs 6/7).
- **The real miss class, from the history (06-01 → 09-04, 859 stored cluster-days):** of 145
  RS ≥ 70 clusters only 23% were ≥ 50% inside a theme; 70 cluster-days were strong AND < 25%
  covered; 41 of those were industry-coherent (14 distinct groups) and **only 6 got a theme within
  10 sessions**. Hotel REITs (APLE/DRH/HST/RLJ/SHO, RS 90-94, 6 nights), self-storage
  (CUBE/EXR/NSA/PSA, RS 76-78), shopping REITs, Canadian banks, European banks, security software,
  life-science tools and industrial machinery were **never named**; trucking (RS 89-94) took 18
  sessions, airlines 17, refiners two months. The other 29 were mixed-industry coincidences
  (ABT/ATAI/CDNA/MAN, INCY/IQV/ITRI/KNSA — the momentum factor the SPY residual does not remove),
  which the model declined correctly. **Why the coherent ones were declined is NOT established** —
  homebuilders (RS 22) and CRE brokers were named from bare tickers the same night Canadian banks
  were not; the scratchpad now captured is what answers it. **And naming is not the whole lag:**
  the 09-01 tankers cluster was named 09-02 and auto-retired 09-03 (*"dropped during
  merge/absorption (no successor found)"*), then re-named 09-08; the 08-13 refiners were named
  08-18 and absorbed into a 36-name E&P blob by 08-20. That churn is #555's territory.
- **Shipped (A) at the source** — share-class collapse + cash-like floor in the cluster engine
  (parameters above). GOOG×4 had held a slot 25 consecutive nights and became a live theme once
  (*Alphabet (Google) Platform Re-Rating*, 08-03 → 08-12). The cash-like floor is an ADDITION
  beyond the card's ask, justified by the 09-08 rows (Cluster F, corr 0.92, five takeover
  targets). `member_rs` attached in memory.
- **Shipped (B) the instrument** — `already_named` class with `covered_share`/`covered_by`, and the
  model's per-batch `analysis_scratchpad` stashed on the run-level `advisor_state` and written to
  the row (bounded 2,000 chars × 12). Tomorrow's row can say why.
- **Shipped (C) parity rendering** — cluster members now carry RS / sector / description and an
  `[in: theme]` tag, strongest cluster first, top-12 described + tail; descriptions ensured for
  cluster members at both call sites. Framed as parity, not as the fix for the miss class above.
- **Deliberately NOT changed:** the three disposition sentences and the precision/recall text;
  `THEME_RS_MIN` and the fact that the cluster path has **no RS floor** (homebuilders at RS 22 and
  CRE brokers at RS 32 went live 09-08 while every pool is floored at 50 — changing that is a
  criterion, operator's call); `_dedup_against_themes` (its single-theme-50% rule is why the
  fully-fragmented miners block keeps passing — a merge signal, #555); the merge/retire passes;
  the shadow's run order.
- **Operator forks (each one line, decide after one night of scratchpads):** (1) should a cluster
  need avg RS ≥ 50 like every pool, or is a low-RS coherent cluster a valid rotation seed? (2) do
  sector-rotation groups (REITs / banks / trucking at RS 90+) count as themes under the north
  star, or only catalyst cohorts? Rec: read the 09-09/09-10 scratchpads first.
- **Verify-live (09-10):** `mi_correlation_clusters` for 09-09 holds NO GOOG cluster and no
  BWMN/HZO/VREX cluster; `apollo-market` logs show `collapsed 1 share-class group(s)` and
  `dropped N cash-like series`; the 09-09 `theme_discovery_shown_declined` rows carry
  `already_named=` in the summary and non-empty `scratchpads`; discovery cache_read stays non-zero.

### 2026-09-08 — seed-story vs active-theme matcher: calibrated on 25 labelled seeds, NOT shipped

**No behaviour change.** Recorded so the read is not redone from the same mistaken evidence
(CHANGE_PROCESS rule 7 — the open question lives here, not in a ticket).

- **The rule (operator-approved)**: before parking a lone name as a Lane-2 seed, test its story
  against the ACTIVE themes; on a match, join instead of seeding. Its calibration was the ship
  condition: must fire on seeds that later joined a theme which already existed, must not fire on
  seeds that never joined anything. A rule that cannot separate labelled cases does not go live on
  a detection path.
- **The evidence did not hold** (`scripts/probes/_lane2_seed_story_match_sweep.py`, read-only, $0,
  25 seeds 2026-08-10 → 09-03, joins measured against the live `mi_themes` board because the
  evidence's four "existing themes" are live themes, not Lane-2 narratives). Of the five named
  misses: **BRUN and BLSH** joined themes born AFTER they were parked (08-13, 08-19) — not
  catchable. **HOOD and OMER were already members** of their pre-existing theme on the night they
  were parked (board rows written 21:07 and 21:09 UTC; the lane-2 decision 21:11 and 21:12) — a
  membership fact, not a story-matching one; HOOD had sat in *Wealth Management & Retail
  Brokerage Platforms* since at least 08-21, OMER in *Specialty Pharmaceutical Commercialization*
  since its 08-03 birth. MRNA likewise was on the 08-19 board before its decision. That leaves
  **CBRS (08-17) as the ONE genuine case** (theme born 08-13, CBRS not yet a member, joined
  08-18). "12 later joined, median lag 1 day" is a next-snapshot artefact: 3 were already in, 2
  (NESR, LPTH) were promoted by step 5d (`source='shadow_promoted'`) AFTER the lane-2 decision
  (+2.5 min and +62 ms), 7 truly joined later.
  Against the `active` parameter itself (the Lane-2 roster, 0-7 narratives on those nights) the
  strict must-fire set is EMPTY.
- **The sweep** (IDF-weighted distinctive-token overlap, story vs name+thesis; token floor
  0/1.5/2.5/3.5 × threshold 0.15/0.25/0.35/0.50): the only settings that fire on CBRS and HOOD
  (threshold 0.15) fire on **18 of 25 seeds, including 8 of the 13 that never joined**; every
  stricter setting misses both. No threshold can rescue it: CBRS's real theme ranks **10th of 94**
  on its board (0.20, below a storage-theme hit at 0.29 on `ai/data/infrastructure`), HOOD's ranks
  **9th of 118** (0.10, on `crypto/market`). What fired was catalyst boilerplate — `beat`,
  `guidance`, `raised`, `award`, `contract` — the catalyst-type words `_LANE2_NARRATIVE_RULES`
  forbids as themes. The operator's specific worry did not materialise: the never-joined biotech
  seeds (CGEM, ARGX, SLN, ABCL, AMLX) never paired with an oncology theme on Phase/oncology tokens
  (best 0.19, AMLX on `data/readout`).
- **What WAS found**: the seed hygiene reads only the lane's own roster (architecture bullet
  above). A check against the PRIOR-day live board (race-free — the same-night board can land
  after the decision, as NESR/LPTH show) is exact, needs no threshold, and would have consumed
  exactly HOOD and OMER. It has no write path (Lane 2 cannot add a member to `mi_themes`) — "join"
  can only mean *consume the seed and record it as covered*. Two measured costs: HOOD's
  prediction-market story would be absorbed by a 20-name, yields-driven brokerage cluster (a
  sector, not a theme), and OMER's seed demonstrably fed the 08-14 five-member Lane-2 birth the
  next night — a conversion the check would have prevented. **Operator decision, not taken here.**
- **Reversion-flag**: NEW (nothing changed). **Status**: tested and NOT shipped — a decision, not a
  pending deploy; re-run the probe when the labelled set has grown
  (`lane2_seed_birth_calibration`, data_gated_reviews.yaml).

### 2026-09-07 — discovery now records what it was SHOWN and what it DECLINED (#486)

**Shadow recorder. No behaviour change** — nothing about which themes are born, named, scored or
retired moves. Added because a measured question could not be asked of history at all.

- **What forced it.** `docs/analysis/step3_theme_runway_2026-09-07.md`: the engine names a group a
  median **30 sessions (~6 weeks) after its first signal**, and **140 of 398 themes (35%) had at
  least half their founders sitting in a stored correlation cluster a median 26 sessions before
  birth, unnamed**. `_discover_new_themes` is **already passed `correlation_clusters`** — so those
  groups were in front of the model and it declined them. **Naming is the lag, not detection.**
- **Why nothing could explain it.** The `theme_discovery_llm_call` audit row carries only token
  counts (`stop=tool_use out_tok=… iter=…`), and `mi_theme_candidates_shadow` records what WAS
  proposed — never what was shown or skipped. There was no record of a decline anywhere.
- **What now happens.** `_log_discovery_shown_and_declined` writes ONE `mi_audit_log` row per
  discovery run, event type **`theme_discovery_shown_declined`**: the tickers shown per pool
  (uncovered / velocity / turner / elite), the tickers claimed by proposed themes, the difference,
  and every correlation cluster split into **taken** (all members claimed), **partial**, and
  **declined** (not one member reached a theme — the class step 3 measured), each declined cluster
  carrying its hash, members, mean correlation and average RS.
- **Where.** `theme_engine.py`, called at **both** return paths of `_discover_new_themes` (the
  single-call fast path and the batched path) so a batched run is not silently unrecorded.
- **Safety.** The row is written after the result already exists and cannot alter it; the body is
  wrapped and `log_audit_event` swallows besides, so a failing recorder cannot break discovery.
  Frozen by `tests/test_theme_discovery_shown_declined.py`, including the case where the audit
  write itself raises.
- **Not yet answered:** *why* the model declines. This row is the instrument; the reading comes
  after it has run. Any change to the naming rule is a detection criterion — CHANGE_PROCESS,
  operator sign-off, and this file in the same commit.


### 2026-09-02 — a theme rename no longer discards the operator's rulings (#601)

Found 2026-08-26 reviewing the same night's #214 rename deploy. Themes touch no money, so
this ships full (no shadow arm). Behaviour spec in the **#601** bullet at the top of this file.

- **Defect**: both operator-ruling tables are keyed on the theme's NAME. `get_operator_protected_set`
  matched an EXACT `(ticker, theme_name)` pair — after a rename the ruling could never match again,
  deterministically. `mi_theme_exclusions` used a word-overlap net that survives rewordings but not
  the broadening renames #214 performs. Newly reachable: before #214, canonicalisation reverted almost
  every rename, which incidentally kept names stable; #214 is the first mechanism that KEEPS a new
  name. Losing the shield is worse than it sounds — it runs BEFORE the mass-eviction judgment, so an
  unshielded name goes back into `to_remove` uncounted and is stripped through the ordinary path.
- **Fix**: persisted rename lineage (`mi_theme_renames`, written by `_save_themes`) + both loaders
  expand rulings across it. The in-memory `renamed_from` flag was the only rename record the
  validator could see, and it dies with the run.
- **Reversion-flag**: NEW (first persisted theme-identity record). Revert = stop expanding in the two
  loaders; the table and its writer are inert on their own. No detection criterion, threshold or
  safeguard touched.
- **Direction / risk**: ruling-PRESERVING only. It can keep a member the operator ruled in, or strip
  one he ruled out, under a name the theme acquired later — never the reverse. A ruling now reaches a
  name it could not before; that is the operator's authority being honoured, not new behaviour.
- **Not exposed today** (prod, read-only 2026-08-26): the only protected pair is SIMO + SNDK in
  `AI Memory & Storage`; the two exclusions are CAR and ECOR on unrelated themes. Renames that fired
  between 08-28 and the deploy exist only as audit rows + tombstones and are NOT in the new table —
  backfill, if any are found, is one operator-run INSERT per `theme_renamed_on_mass_flag` row.
- **Verify-live** (first nightly run after deploy): `mi_theme_renames` exists (empty is fine); the
  next `theme_renamed_on_mass_flag` night writes ONE row with `mechanism='mass_flag_rename'`; the
  following Mon/Wed/Fri run logs `#601: operator protection ... (rename lineage)` for any protected
  pair under the old name. Deploy gate `[5h/7]`-adjacent: `preflight_db_updates.py` prepares the
  writer at deploy.

### 2026-08-26 — a too-narrow theme NAME is renamed, not paid for by evicting the members (three fixes)

Operator: *"fix it"* on all three findings in `docs/analysis/theme_mass_eviction_2026-08-26.md`.
Themes touch no money, so these ship full rather than shadow-first. **No EP threshold, score
weight or admission rule was touched** — `ep_rubric.SCORE_WEIGHTS` / `SHORTLIST_WEIGHTS` and
`ep_detector` are byte-unchanged.

**FIX 1 — rename on the mass-eviction signature (`#214`).** Full behaviour spec in the bullet
at the top of this file (naming-path reuse, caller scoping, ordering, loop cap, identity,
refusal paths). The short version: 17 of 24 removals on 08-26 were ONE theme whose name had
gone narrower than its cluster, we deleted the members to fit the name, and the same energy
block had already done this twice in the preceding ten days under two other names.

- **Reversion-flag**: NEW (first mechanism that renames a live theme on a validation signal).
  Revert = stop passing `mass_flag_out` from `_rescore_existing_theme`; the helpers
  (`_apply_mass_flag_rename`, `_rename_theme_to_fit_cluster`, `_recently_renamed_on_mass_flag`,
  `_name_is_live`) go inert and the strip returns exactly as before. The
  `_canonicalize_theme_names` carve-out and the `_save_themes` counter fallback are both
  no-ops when nothing carries `renamed_from`.
- **Cost**: one bounded Sonnet call per firing (~3 per 10 days at the observed rate), against
  a ~$4-6/day stack. It REPLACES no existing call — the validation call still happens.
- **Direction / risk**: strictly member-PRESERVING. It can only keep members that today would
  be evicted, never remove one. Consequence to know: a member kept in an Accelerating or
  Mainstream theme keeps the R4 +10 in-theme bonus it would otherwise have lost, so the fix
  can raise a future EP score relative to today's behaviour. That is the mechanism working as
  designed (membership is the input; the weight is untouched), not a scoring change. Tonight's
  actual case is inert on that axis — `Oil Refining & Marketing` is Nascent, and the bonus set
  only reads Accelerating/Mainstream. The accepted cost is the opposite one: a theme that was
  genuinely holding wrong members now gets a broader name instead of a cleanup, bounded by the
  breadth rule in the naming prompt and by the loop cap.
- **Verify-live** (next Mon/Wed/Fri engine run, 17:00 ET): the mismatch is already re-armed on
  the 46-member cohort for **Fri 2026-08-28**. Expect a `theme_renamed_on_mass_flag` audit row
  instead of a burst of `ticker_revalidated_out` + `validation_cooldown_triggered` rows; ZERO
  new `mi_validation_cooldowns` rows for that theme; an explicit `stage='Retired'` tombstone
  for the old name carrying `parent_theme` = the new name; the new name's `mi_themes` row
  carrying the OLD name's `days_active` (NOT 1); and — the one that proves the carve-out held —
  the new name still present the FOLLOWING run, with no `theme_renamed_for_continuity` row
  moving it back.
  ⚠ **A non-firing on Friday is NOT a failed fix.** The cohort is now 46 members and majority
  UPSTREAM producers, so the signature needs **>=23 of 46** flagged. If validation instead flags
  the 7 remaining refiners (7/46), `_is_mass_eviction` correctly does NOT fire, those 7 strip and
  get cooldowns exactly as before, and nothing renames — the signature working as scoped, not the
  mechanism failing. Read the `validation_mass_removal_name_suspect` row (or its absence) first.

**FIX 2 — `theme_count_active` counted NAMES, not themes.** The metric was
`COUNT(DISTINCT name)` over a 7-day window: it never took the latest row per name, so renamed,
merged-away and retired themes kept counting for 7 more days. It now mirrors
`db.get_active_themes` exactly (latest row per name FIRST, then drop Retired) — the same fix
`get_active_themes` made for itself on 2026-06-09 (#214 RETIRED-GAP) and this metric never got.

- **Measured on prod, read-only, before → after**: **2026-08-26: 166 → 104.** Also 08-25
  163 → 106, 08-24 160 → 104, 08-21 159 → 114, 08-19 141 → 113, 08-17 130 → 94, 08-06 124 → 92.
  The old metric read as CLIMBING through the week (159 → 166) while the real theme count FELL
  114 → 104. It fired L2 on four of the last six nights on that artifact. The corrected metric
  is also anchor-stable: across the 08-27 UTC rollover the old query moved 166 → 152 while the
  corrected one stayed 104 both sides.
- **The `CURRENT_DATE` (UTC) anchor is deliberately NOT changed.** `get_active_themes` uses the
  same bare `CURRENT_DATE`; ET-anchoring only the metric would put it on a different day from
  the reader it reports on. The 08-26 analysis noted the ET/UTC discrepancy — it is real, and it
  belongs to `get_active_themes`, not here.
- **Expect ONE L2 fire on the step down** (166 → 104 is a material level shift). The existing
  machinery covers the persistence: `_persistent_l2_downgrade` + `_recent_window_stable`
  (#352 fix-2) exist for exactly this class and downgrade a settled shift to L3 after the
  transition night, so it does not become a nightly nag while the 30d baseline catches up.
- The **drill query** was fixed the same way — the old one (`GROUP BY name, stage` over every
  row) reproduced the metric's own bug, so an operator drilling into the alarm was handed the
  artifact rather than the set.
- **Reversion-flag**: REFINEMENT of an existing metric definition. Revert = restore the
  `COUNT(DISTINCT name)` query.

**FIX 3 — "rising" now looks at the shape, not just the two endpoints.** `_rs_rising` was
`hist[0] > hist[-1]`. Second clause added: `hist[0] >= min(hist[1:-1])`. Behaviour spec in the
member-pruning bullet above; `health_checks._rs_rising_mirror` moved in lockstep (byte-parity
pinned).

- **Evidence, $0** — read-only prod capture (one pass), `mi_themes` 2026-03-19..2026-08-26
  (5,878 rows / 113 board-days) + `rs_composite` for every themed ticker;
  replay `scripts/probes/_rs_rising_shape_replay_2026-08-26.py`, output
  `_rs_rising_shape_replay_out.txt`. Scored the #368/#531 way: peak RS >= 50 within 10 sessions.
- **BOTH DIRECTIONS, on 645 de-duplicated prune-candidate episodes** (one row per contiguous
  candidate run, so one episode is not counted on every day it persists):
  | | held | held recovery | stops holding | those recover at | newly holds |
  |---|---|---|---|---|---|
  | current (endpoint) | 238 | 52% | — | — | — |
  | **shipped (interior floor)** | **226** | **53%** | **12** | **17%** | **0** |
  The true-hold is intact (52% → 53%) and the names it stops holding are the collapse class
  (17% recovery, vs the 52% base rate). **IREN + APLD 2026-07-22 — the verified ignitions this
  hold was built for — are still held.** BLDR, BRUN (`[12.2, 70.7, 71.6, 66.4, 36.6, 5.3]`) and
  MPWR are correctly rejected.
- ⚠ **FOUR BROADER SHAPE TESTS WERE MEASURED AND REJECTED, and this is the finding worth
  keeping**: OLS slope over the window, slope + above-median, recent-half vs older-half mean,
  and today-vs-median-of-earlier. Every one of them BROKE the true-hold — the names each
  stopped holding recovered at **41-58%**, at or above the held population's own base rate,
  while the extra names they admitted recovered at **29-35%**, well below it. The obvious
  "measure the trajectory properly" fix (OLS slope) is **net-harmful on this data**. Only a
  clause that can *narrow* the hold and nothing else survives — which is why the shipped test is
  a conjunction on top of the old one and provably admits nothing new.
- **Honest scope**: five of the six utilities in the 08-26 analysis (SO, EXC, AEP, ATO, FE) are
  genuinely higher than they were over a 6-session window and **still read rising** after this
  fix. The analysis's own gloss on them — "DOWN over the last 3 sessions" — is a shorter,
  different question. This fix targets the collapse class the analysis proved (BLDR); it does
  not, and should not, reject chop that is really up.
- **EP exposure, counted not estimated**: a stricter hold prunes more, and a pruned member of an
  Accelerating/Mainstream theme loses the +10 bonus. Over 1,191 candidate-day evaluations across
  113 board-days, exactly **2** newly-pruned members sat in an Accelerating or Mainstream theme
  (JOBY 2026-03-20, Accelerating — went on to die; MPWR 2026-08-20, Mainstream, no forward
  window yet). Bounded and tiny; stated so the operator can rule on it rather than discover it.
- **Classification**: BUG FIX inside an already-signed criterion, not a criterion change — the
  SSoT states the intent as "a member whose RS is RISING over the window", and `hist[0] >
  hist[-1]` is a defective implementation of that sentence (the same constant was already
  misread once, on 2026-08-04). The N>=10 both-directions backtest is attached anyway because it
  was free.
- **Reversion-flag**: REFINEMENT of #368's F3 rising-recovery hold. Revert = drop the second
  clause in `_rs_rising` AND in `_rs_rising_mirror` (the parity test forces both).

**Deploy scope: `both`.** `shared/output_ceilings.py` + `shared/llm_thinking.py` gained the
`theme_rename` caller, and `shared/` is owned by both services per the CLAUDE.md ownership map —
a `market-agent`-only deploy would ship the theme_engine call site without its ceiling entry and
`max_tokens_for` raises `KeyError` by design on an unregistered caller.

**Tests**: `tests/test_theme_rename_on_mass_flag.py` (31), `tests/test_rs_rising_shape.py` (9),
`tests/test_theme_count_active_metric.py` (8), plus the BLDR/BRUN/SO samples added to
`tests/test_theme_quality_check.py`'s mirror-parity pin and the `theme_rename` caller added to
`tests/test_llm_thinking.py`'s two classification pins. Each fix mutation-proven separately
(FIX 1 in six places: validator branch, canonicalize carve-out, loop cap, counter carry-forward,
tombstone successor, and the `renamed_from` key on a rescore return branch — the #471 lesson,
since pinning the fallback line does not prove the key REACHES it; verified by trace that the
only rebuilding transform on the rescore->save path, `_strip_sector_outliers`, spreads). Suite: 6394 passed / 7 skipped (baseline 6346).

### 2026-08-18 — discovery batch cap tightened 37→22 (headroom, not a re-raise)

- **Trigger**: the #543 live truncation alarm fired for `theme_discovery` — 1 of 22 calls
  at-cap on 08-18, after 7 clean days on the 08-10 batching fix (max output 5.6K-6.7K,
  well under the 8000 cap on every prior day). Call volume was ~2x the typical 4-11/day.
  Ceiling was NOT raised — `shared/output_ceilings.py` still forbids it for this class.
- **Diagnosis**: the 08-10 derivation sized the batch cap (37) to sit at ~88% of the
  8000 ceiling in the worst case it could measure at the time. The 08-18 truncation is a
  CENSORED sample — true output ≥ 8000, i.e. ≥ 216 tok/stock at N=37 — above every one of
  the 5 clean-day observations (152-182 tok/stock) and above the 190 tok/stock the 08-10
  fix designed for. More calls in a day means more draws from the same per-batch output
  distribution, and 08-18 drew further into its tail than any clean day had reached.
- **Fix**: `_DISCOVERY_LLM_BATCH_STOCKS` 37 → 22 (full arithmetic + the 6-day data table
  at the constant's definition in `theme_engine.py`). Re-derived the same way as 08-10:
  censored floor (8000/37) × the same 1.5x tail-allowance ratio ÷ 0.90 near-ceiling target.
- **Cost**: batches per night rise ~1.7x (37/22) for the same candidate pool — more calls,
  more repeated existing-themes-block input tokens; total OUTPUT tokens stay ≈ flat (set
  mainly by the pool size, not the chunking — mirrors how the 08-10 entry hedged this same
  claim for its own batching change; per-call fixed overhead now amortizes over fewer
  stocks, so the true number is a shade above flat, inside the 1.5x tail-allowance slack).
  Input is priced well below output on sonnet-5, so this is a small dollar cost against the
  truncation it prevents.
- **Residual risk raised by this change**: the 08-10 entry already flagged that a
  CROSS-sector catalyst cohort can straddle a batch boundary and fail to form (sector-sort +
  cluster atoms minimize but do not eliminate it). Smaller batches mean ~1.7x more boundaries
  per run, so that residual risk rises by roughly the same factor. Narrower than a
  truncation (costs one cohort, not the whole call) but worth having stated, not just cost
  and headroom.
- **theme_assignment**: checked against the same question same day. Could not query prod
  `api_usage` this session (no DB access available) — left UNCHANGED for lack of data, not
  because it's known to be fine. Needs a PLAN.md line + fresh data before the next time
  this class of alert fires for it (operator call — not filed here).
- **Tests**: `tests/test_theme_batching.py` — new pure-partition coverage (bound / full
  coverage / order-preservation on `_partition_discovery_pools`) plus the existing
  batch-count and derivation-gate tests updated for cap 22; mutation-proven.

### 2026-08-10 — output-bounded batching: the four theme LLM callers can no longer out-write their ceilings

- **Trigger**: the #543 ceilings (raised 4000→8000 on 08-07) pegged AGAIN — 08-10 live:
  theme_assignment 3/3 at 8000, theme_split 2/2 at 1750, theme_discovery 5/6 at 8000,
  narrative_theme_discovery 1/2 at 1500 — and the nightly digest showed **three consecutive
  engine nights with zero successful assignments** (the 08-07 `tool_choice="any"` fix changed
  the failure's shape from silent-stop to zero-proposals without restoring the component).
  The 08-07 note said it plainly: if at-cap% does not fall at 8000, the cap was never the
  constraint. It was not. No ceiling was raised in this change.
- **Root causes are NOT one shape** (measured per caller, prod `api_usage` × `mi_audit_log`):
  - **theme_assignment**: output is LINEAR in the candidate pool (the scratchpad contract is
    one line per ticker; measured fit on the 16 untruncated sonnet-4-6 calls:
    `output ≈ 274 + 73.4 × pool`). #534 D2 (operator-signed 08-05) widened the pool 75-97 →
    341-373 overnight → demand far beyond ANY ceiling. Every call since 07-18 was censored
    at-cap; there is NO untruncated sonnet-5 assignment sample.
  - **theme_discovery**: same class — output scales with the merged candidate population
    (uncovered + velocity + turners + elite; 63 rendered stocks on 08-10). Only untruncated
    sonnet-5 sample: a forced report at 7375 tokens ≈ 117/stock; its censored siblings prove
    ≥ 127/stock on the same pool.
  - **theme_split**: NOT an unbounded input (one theme, ~2.1K input tokens). The open-ended
    scratchpad let a more verbose model blow the 1750 cap, and the truncated response parsed
    as `propose_split` with `split` missing → logged **"Sonnet found theme already coherent"**
    — an affirmative lie, twice on 08-10.
  - **narrative_theme_discovery** (Lane-2): NOT the alert count. The raw-JSON TEXT transport
    let sonnet-5 spend ~1000 output tokens/call on freeform deliberation around a ~300-token
    JSON payload (sonnet-4-6: ~32 tok/alert, max completed 355 on 11 alerts; sonnet-5:
    completed 1312 of 1500 on a FIVE-alert night, sibling truncated mid-string →
    "Unterminated string" parse failure → 0 narrative themes).
- **Fixes (bound the output by construction — chunk the input, or remove the freeform channel)**:
  - **Assignment batching**: the pool is chunked into batches of ≤ `_ASSIGN_LLM_BATCH_SIZE`
    (= 18; derivation at the constant: worst-case fit + max residual × the 3.5x measured
    freeform model-growth ≤ 0.90 × 8000). Every batch sees the FULL theme list (input-side,
    costs no output) — a stock's best home is never "in another batch". The shared
    intro+theme-list prefix carries a `cache_control` breakpoint so batches 2..N read it at
    the cached rate. Proposals are validated against the batch that carried the stock
    (cross-batch echoes can neither duplicate nor steal an assignment); the validate/apply
    stage runs ONCE over the union, unchanged. The advisor budget (`_MAX_ADVISOR_CALLS`)
    stays RUN-level, shared across batches. An API failure mid-run applies the batches
    already collected instead of dropping them.
  - **Discovery batching**: `_discover_new_themes` is now a driver over
    `_discover_new_themes_single`; ≤ `_DISCOVERY_LLM_BATCH_STOCKS` (= 37; derivation at the
    constant) rendered stocks per call, full existing-themes context in every call, run-level
    advisor budget. Partitioning (`_partition_discovery_pools`, pure): correlation-cluster
    members are atomic (a statistical cluster is never split across calls, and its cluster
    block travels with it); a ticker in two pools keeps both renderings in one batch; atoms
    are sector-sorted so batch boundaries fall between sectors. **Residual risk, stated**: a
    CROSS-sector catalyst cohort (the HBM-maker + equipment-co case) can still straddle a
    batch boundary and fail to form; sector-sort + cluster atoms minimize but do not
    eliminate this. Same-named themes from two batches merge by ticker union. Both callers
    (live engine + `run_theme_discovery_shadow`) route through the driver unchanged.
  - **Split**: terse scratchpad contract (per candidate SUB-GROUP, never per stock — the
    proven 6/25 discovery recipe), `tool_choice="any"` (pre-tool prose can't eat the budget;
    the advisor path survives because `consult_advisor` is a tool), and a truncated response
    now returns no-split WITHOUT the `fat_theme_no_split` "already coherent" audit row.
    No batching — a coherence judgment cannot be chunked, and its input is already bounded.
  - **Lane-2**: converted to a FORCED tool call (`report_narrative_themes` schema; both v1
    and v2reg paths; prompt text byte-unchanged). The deliberation channel no longer exists,
    so demand returns to the measured ~32-48 tok/alert band (even a 28-alert night fits
    0.9 × 1500). The alert list is deliberately NOT chunked — TODAY+TODAY pairing is the
    lane's core signal and the population has never exceeded 11; a truncation now RAISES into
    the shared fail-open (a FAILED night, never "0 themes").
- **Truncation is never silent**: every `stop_reason='max_tokens'` already fires #543's live
  alarm (spend_tracker → `llm_truncation_live` audit row + Telegram) — REUSED, no second
  mechanism. What changed at the callers: a truncated response is a FAILED call — assignment
  skips the batch (stocks stay uncovered; no `assignment_llm_proposed` "proposed 0" row),
  discovery discards the partial and re-forces once (then returns [] loudly), split refuses
  to read the cut as a decline, Lane-2 raises. Note: a night where EVERY assignment batch
  truncates writes no `assignment_llm_proposed` rows at all, so the 3-night barren-streak
  check reads it as not-run — the live truncation alarm (same night, Telegram) is the signal
  for that case.
- **Tests**: `tests/test_theme_batching.py` (16) + 2 in `tests/test_lane2_grouping_v2.py`;
  each mutation-proven (break the load-bearing line → red → revert). Derivation-gate tests
  fail if either batch constant is bumped past what the measurements support.
- **Cost** (sonnet-5 standard $3/$15 per MTok; tonight's populations): assignment goes from
  1 call (~26K in / 8K out, producing NOTHING, $0.20/run) to ~21 batches ≈ $1.9/run at the
  373-stock pool — output-dominated (~117K generated); the cache_control prefix holds the
  input share to ~$0.13 (vs ~$0.55 uncached). Discovery ≈ flat (total output ≈ demand either
  way; themes-block input duplicated per batch ≈ +$0.05/night). Split + Lane-2 FALL (shorter
  outputs, ≈ −$0.04). Net ≈ **+$1.7/night ≈ +$50/month at the widened #534-D2 pool**
  (+$1.15/night during the sonnet-5 intro pricing through 08-31) — the price of the pool the
  operator signed on 08-05 actually being processed; the pre-batching spend bought zero
  assignments for three straight nights.

### 2026-08-09 — #530 shadow_v2 re-mint no longer overwrites an unchanged thesis with fresh generic text

- **Trigger**: PLAN #530, filed alongside #529 — "the shadow_v2 re-mint overwrites a correct
  theme thesis with generic crypto-beta text." #530's own note flagged that birth-gate Phase 1
  (2026-07-27, `theme_birth_gate`) MIGHT already retire this path — checked first, and it does
  NOT: prod's `theme_birth_gate` safeguard row is `state='observe'` today, and even at `mode='on'`
  the gate only retires the shadow_v2 DISCOVERY stream + strips it from the auto-promote
  allowlist for FIRST-time births; re-promotions of an existing live theme are explicit
  "maintenance" that bypasses the gate on all three modes (`promote_shadow_themes`'s own
  docstring). The defect lives one level lower, in the write path itself — and stays there even
  once the gate ships `on`: `narrative_cogap` and `rs_slope_synthesis` remain on the allowlist at
  `on` (only `shadow_v2` leaves it) and both re-promote through the SAME
  `_upsert_promoted_theme` write. So the birth gate was never going to cover this defect at any
  mode — not a timing gap that `on` eventually closes, a structural one this fix is the only
  closure for.
- **Reproduction** (code read + a regression test against the real function — a description
  reading was explicitly disallowed by the task): `theme_engine._upsert_promoted_theme`'s SQL is
  `ON CONFLICT (theme_date, name) DO UPDATE SET ... description = EXCLUDED.description ...` —
  `EXCLUDED.description` is always `thesis or desc_fallback`, i.e. whatever `promote_shadow_themes`
  or the operator's `/promotetheme` passes THIS call, with zero comparison to the description
  already on the board. `tests/test_promotetheme.py::test_530_unchanged_cohort_preserves_
  specific_thesis_on_remint` reproduces this directly: a same-ticker-set shadow_v2 re-proposal
  with generic text overwrote a specific stored thesis before the fix (confirmed RED via
  `git stash` isolating the fix commit, test file kept) — GREEN after.
  ⚠ **What prod does NOT show, stated so nobody re-derives it and reports it as observed**: a
  120-day replay of `mi_themes WHERE source='shadow_promoted'` (read-only, ssh) found ZERO rows
  where the SAME name + SAME ticker set got a DIFFERENT description on a later shadow-promote —
  the mechanism is real and provably fires (per the test above) but has not been CAUGHT firing
  via this exact path in that window; most shadow-promoted cohorts either write byte-identical
  text on repeat (`'AI Data Center Infrastructure Buildout'`, 08-04→08-07, three promotes,
  identical description every time) or get superseded by the LIVE lane the very next day (the
  crypto-miner lineage itself: `source='shadow_promoted'` only once, 07-17, then `source='live'`
  from 07-20 on). The description CHURN actually visible in prod for the crypto lineage — the
  text flipping between correlation-only and catalyst-specific phrasing across `theme_date` rows,
  Jun–Aug — is the LIVE lane's own daily re-synthesis (`_save_themes` / Lane-1 discovery), a
  separate, larger, explicitly out-of-scope mechanism (see Scope below) that `_canonicalize_
  theme_names`'s own docstring already names ("Sonnet's theme discovery generates new descriptive
  names every run"). So this fix hardens a latent path proven by direct test, not one caught
  in the act via `shadow_promoted` rows specifically — Monday's verify-live is written as a
  negative check for exactly this reason (below).
- **Fix**: new pure helper `theme_engine._resolve_promoted_theme_description` — the ONE decision
  point both `promote_shadow_themes` and `promote_candidate_by_name` now call before invoking
  the shared `_upsert_promoted_theme` write. Rule: **ticker-set EXACTLY unchanged from the last
  known TICKER-BEARING `mi_themes` row for that name ⇒ preserve that row's description; any
  ticker addition/removal ⇒ allow the fresh thesis through.** No specificity scoring, no numeric
  threshold — a threshold was proposed, shipped, and reverted earlier the same day this line was
  written; this rule needs no number because it mirrors an EXISTING precedent in this file's own
  code: `_canonicalize_theme_names` (#59, 2026-05-11) already solved the identical churn problem
  for the theme NAME by freezing on exact ticker-set match. This closes the same gap for the
  DESCRIPTION field.
- **Bug found and fixed on review, before ship: the lookup must SKIP auto-retire tombstones.**
  Every explicit Retired-row write in this file (`_synthetic_retired_row`, the engine-drop
  `retire_rows` in `run_theme_engine`) hardcodes `"tickers": []`. A naive "compare against the
  immediately-prior row" lookup would see that tombstone — `set() != set(tonight's cohort)` —
  and refuse to preserve whenever a retire-by-absorption tombstone sits directly ahead of a
  re-promote. **Measured, not estimated** (query in the commit; joins each `shadow_promoted`
  row to the most recent PRIOR row for that name carrying a non-empty ticker set, any
  distance back): **17 of the 93 `shadow_promoted` rows in the 120-day window have such a
  row, all of them within 14 days** (median gap 2 days, range 1–11) — that is the population
  this fix protects. The query returns only the ANCESTOR's date, not what sits between it and
  tonight, so whether a Retired tombstone specifically occupies that gap is NOT separately
  confirmed here (a short gap is also consistent with a quiet weekend with no row at all); what
  IS confirmed is that the immediately-prior row is frequently NOT the cohort row, which is the
  only fact the fix's correctness depends on. Fix: `promote_shadow_themes` /
  `promote_candidate_by_name` now run a SEPARATE query (`AND cardinality(tickers) > 0`, batched
  for the nightly path — not N+1) that
  skips tombstones and returns the most recent row that actually CARRIES the cohort;
  `prior_days_active` keeps reading the unfiltered immediately-prior row (that continuity must
  NOT skip tombstones — a theme's active-day count is real regardless of a same-week
  retire/re-promote blip). Pinned by
  `tests/test_promotetheme.py::test_530_tombstone_between_snapshots_still_preserves` (scenario)
  and `test_530_prior_desc_lookup_sql_filters_empty_tickers` /
  `test_530_operator_path_prior_desc_lookup_sql_filters_empty_tickers` (the SQL text itself,
  so a future edit that drops the `cardinality(tickers) > 0` clause fails a test even though
  the scenario tests hand the resolver pre-filtered rows and can't see the query directly).
- **Two more guards on the preserve branch, added on review, both borrowed from EXISTING code
  rather than new numbers**: a prior (ticker-bearing) row with `stage='Retired'` is NEVER
  preserved — the ticker-bearing filter above already excludes every CURRENT retirement
  mechanism (both hardcode empty tickers), so this guard has no confirmed live case in the
  120-day replay (the one Retired-with-tickers row found, 2026-04-10, predates that convention
  and is also >14 days old — already caught by the age guard below); kept as a categorical,
  zero-cost backstop against any future retirement path that doesn't follow it, stated honestly
  rather than implied as independently evidenced. A prior row OLDER than 14 days is NEVER
  preserved (the exact window `_canonicalize_theme_names` #59 already uses for the analogous
  name-freeze decision — borrowed, not invented). Both apply ONLY to this decision, not to the
  shared `prior_days_active` continuity.
- **Edge cases** (see the function's own docstring for the full statement): no prior row
  (genuine new crossing) → candidate thesis used, unaffected by the fix; prior row's description
  is NULL/empty → nothing worth preserving, candidate thesis used; ticker ORDER differs but the
  SET is identical → still counts as unchanged (set comparison, not list/order comparison);
  operator `/promotetheme` on an unchanged cohort → same protection applies, since the operator
  promotes whatever the shadow lane most recently proposed rather than typing new wording
  themselves, so there is no case of discarding operator-authored text; **a cohort whose
  membership never changes gets a STICKY description** — text written on the first promote
  persists until a ticker moves, even if the real-world story evolves while the ticker set stays
  fixed (a genuine same-membership story change must reach the board via the LIVE lane's own
  daily re-synthesis or an operator hand-edit, not this automated path — a deliberate trade
  against letting shadow_v2's noisy re-generation back in).
- **Why membership-change, not "specificity"**: a text-quality scorer needs either a threshold
  (banned by the task — one was tried and reverted today) or an LLM judgment call on every
  promote (cost + another source of drift); ticker-set equality is mechanical, needs no tuning,
  and is exactly the signal that already justifies a description refresh — the cohort itself
  changed.
- **Scope**: touches ONLY the two shadow-promote write paths (`_upsert_promoted_theme`'s two
  callers). The LIVE lane's own nightly re-synthesis (`_save_themes` / Lane-1 discovery) is a
  separate, much larger design surface (regenerates description for EVERY live theme, not just
  shadow-promoted ones) and is explicitly out of scope — changing it would be a detection-surface
  change needing its own CHANGE_PROCESS evidence, not a #530-shaped fix.
- **Status**: built + tested (9 new tests in `tests/test_promotetheme.py`, 4 pre-existing tests
  in `test_theme_birth_gate.py` / `test_coverage_probe.py` / `test_promote_ecosystem_mapping.py`
  updated for the new `conn.fetch` call shape, full suite 4886+ passed / 7 skipped), NOT
  deployed, NOT committed. No money/trade-state path touched (theme detection surface only).
- **Verify-live (Monday's nightly run) — written as a negative check on purpose**: the
  Reproduction section above already showed the exact "same cohort, different description"
  shape hasn't been CAUGHT via `source='shadow_promoted'` rows in the last 120 days, so
  "wait for an occurrence" is not an honest DoD. Instead: (1) confirm `promote_shadow_themes`
  ran without error and BOTH new prior-row queries (days_active lookup + the tombstone-skipping
  `description, tickers, theme_date, stage` lookup) fetched cleanly — no `KeyError`/SQL error in
  the nightly log; (2) the standing negative check, good indefinitely: for EVERY
  `source='shadow_promoted'` row written, find the MOST RECENT PRIOR row for that name that
  carries a non-empty ticker set (skip Retired tombstones — this is the tombstone-skip fix's own
  predicate, not the naive "immediately-prior row"). If that row's ticker set matches tonight's,
  is not itself Retired, and is ≤14 days old, tonight's `description` MUST equal that row's
  `description` exactly — any row breaking that invariant is the regression this fix exists to
  prevent. (3) If a real same-membership overwrite IS eventually caught by this check on some
  future night, that is the strongest possible confirmation and should be logged back onto this
  line.

### 2026-08-07 (b) — #543: the two theme LLM stages were being TRUNCATED, and it was invisible

- **Trigger**: chasing the 10-day `theme_assignment` outage the same day, we swept every LLM
  caller's `output_tokens` against its ceiling. Over the prior 7 days: `theme_synthesis` **60%
  of calls ended at EXACTLY 4000 tokens**, `theme_discovery` **28.6% at 4000**,
  `theme_assignment` **100% (7 of 7) at 4000**.
- **Why it matters here specifically**: both stages emit a forced/expected TOOL CALL whose JSON
  is the entire product. Truncated JSON yields no parseable `cohorts` / no `tool_use` block, and
  every caller's fail-open turns that into "proposed 0" — which reads as a quiet night. The
  4000-line in `theme_synthesis.py` had a June comment predicting this exact failure and naming
  the fix ("unless we record the stop_reason"); it recurred anyway, because a comment is not a
  column.
- **What shipped**:
  - `theme_synthesis` `max_tokens` 4000 → **8000**.
  - `theme_discovery` `_DISCOVERY_MAX_TOKENS` 4000 → **8000**. Its 6/25 root fix (terse
    scratchpad + no-free-text-before-tool prompt) cut truncation, it did not end it; this loop
    stays `tool_choice=auto` deliberately (the #173 advisor path), so free reasoning text can
    still consume the budget and headroom is the only lever that does not trade against it.
  - `theme_assignment` was fixed separately the same day (`tool_choice="any"` + 8000) — the
    structural fix, since `auto` is what let prose eat the whole budget.
  - **`api_usage.stop_reason`** recorded on every LLM call + a daily 17:52 ET truncation check
    that Telegrams on any truncating caller AND on any caller not reporting `stop_reason` at
    all. Tests: `tests/test_truncation_self_reporting_546.py`.
- **⚠ Watch**: if `theme_synthesis` at-cap% does NOT fall after a real run at 8000, the cap was
  never the constraint — the prompt asks for more output than any envelope and the fix is
  bounding the cohort count, not raising again.
- **Cost**: worst case across all three raises **+$0.11/day** against a ~$4-6/day total.

### 2026-08-05 (c) — #491 M2 seeded assignment-pool exemption (theme membership, $0 LLM)

- **Trigger**: #491 design D1/D3 (operator-approved 2026-08-05) — the ex-miner pivot cohort
  cannot reach the live AI theme because a pivot has low trailing RS by construction (all ten
  names under the RS-70 floor on 08-04); the price-action lanes already carry the names but
  they died in shadow rows the assignment pass never read.
- **What shipped**: `db.SEEDED_ASSIGN_SOURCES` + `db.get_seeded_assignment_tickers` (one
  read-only query over `mi_theme_candidates_shadow`), `theme_engine._seeded_pool_admissions`
  (pure, deliberately RS-free — fork F-D), and the M2 wiring block in `run_theme_engine`
  between pool-build and assignment. Full behavior spec in the bullet at the top of this file.
  Also fixed the assignment prompt's stale header "(RS >= 50, not in any active theme)" —
  wrong since the floor moved to 70, and M2 now admits below it — to "(not in any active
  theme; each line shows its RS)".
- **Evidence** ($0 replay, `scripts/probes/_491_m2_seeded_pool_replay.py` over the frozen
  `_368` exports + prod lane rows): 45 admissions over 28 replay nights (peak 10 on 08-05 —
  inside the ~15/night design bound). IREN admitted from 07-21 (the night after the 07-20
  Lane-2 "Bitcoin miners pivoting to AI data centers" row) at RS 1-36; BTDR admitted 08-05
  (trigger: the 08-04 co-gap row) with the correct live landing zone
  (`AI GPU Compute Infrastructure & Cloud Services`, Nascent) on the board. HUT correctly
  NEVER admitted (covered by the crypto incumbent — B1 is M-CORE's, not M2's). Known
  over-admission class, hand-checked: the ARM/LRCX/SIMO/COHU semis EARNINGS cluster
  (07-30/31 lane rows) — ~4 names × ~3 nights of pool lines; bounded, and the assignment
  LLM + F4 own whether any become members.
- **Reversion-flag**: NEW (first exemption on the assignment pool's floor). Revert = remove
  the M2 block in `run_theme_engine` (the db accessor + helper go inert).
- **Status**: ✅ **LIVE — verified in prod 2026-08-31, not inferred from the commit.**
  `mi_audit_log` holds **20 `seeded_pool_admission` rows, 2026-08-06 → 2026-08-26** — the
  exemption is not merely deployed, it has ACTED. Shipped `588ac305` (2026-08-05). The
  original day-of status (built + tested, 15 new tests, suite 4465 green, NOT deployed) is
  what stood when the entry was written; corrected here because the drift scan reads the
  most recent word on a subject as a CURRENT claim wherever it sits.
- **Verify-live**: after the first nightly run, check the `seeded_pool_admission` audit row
  + whether BTDR reaches the assignment prompt (and, if assigned, survives F4).

### 2026-08-05 (b) — #534 D3(b) ecosystem-reactivation detector (observability + discovery seed, $0)

- **Trigger**: operator, 2026-08-04, on the duplicate defense births: *"multiple defense stocks
  moving and having EP around the same time, this might be indicator that this group is coming
  back alive after a dormant period."* Design: `docs/analysis/534_theme_universe_expansion_2026-08-05.md` §5b.
- **What shipped**: `health_checks.run_ecosystem_reactivation_check` + 6 db.py accessors
  (`get_reactivation_sessions`, `get_high_ep_ticker_days`, `get_ticker_ecosystem_membership`,
  `get_mapped_theme_stages_before`, `get_reactivation_alerted_ecosystems`,
  `persist_reactivation_seed`), wired into `_post_nightly_audit_job`. Full behavior spec in the
  bullet at the top of this file; derivation + both-ways measurement in `health_checks.py`'s
  #534 section header.
- **Thresholds derived, not picked** (66-session replay, 324 HIGH ticker-day alerts): cluster
  K=3 (the size distribution's elbow — pairs are ~10× triples and belong to Lane-2's 2-member
  anchor / the gate's two-sighting arm), baseline B=15/Q≤1 (exactly what separates the defense
  wake-up, baseline 0, from the ARM+LRCX+SIMO same-night earnings cluster, baseline 2), window
  W=5 sessions, dormancy at window START (the five 08-04 reactive births land inside the window
  and must not mask the signal they ARE). Sector fallback measured and REJECTED (admitted
  E-INDL@05-06 and E-COMM@05-14 — sector-label pseudo-clusters, the earnings-surge trap).
- **False-positive rate over the replay**: ONE incident in 66 sessions (E-DEF 2026-08-04 —
  the operator's own worked example), everything else silent, including the entire late-July
  earnings surge.
- **Safety**: never births/retires/renames a theme; seed source excluded from the auto-promote
  allowlist + judge context by construction; birth gate owns promotion. Pinned by
  `tests/test_ecosystem_reactivation.py` (23 tests).

### 2026-08-05 — assignment pool widened: RS floor 90 → 70, ceiling 200 → 600 (#534 D2, operator-signed)

**Change**: `ASSIGN_POOL_RS_FLOOR` 90.0 → 70.0, `ASSIGN_POOL_CEILING` 200 → 600.
**DISCOVERY IS UNTOUCHED at top-40**, so this cannot mint a single new theme — it only lets
existing themes gain members.

**Operator's ask** (2026-08-05): *"we maybe need a larger universe and some sub groupings and show
the highest RS, biggest, strongest etc. but other stocks are still in a theme but not at the top."*
This ships the "still in a theme but not at the top" half.

**Measured before the change** (prod, 2026-08-04/05): 104 themes · 319 distinct tickers · avg 3.3
members, against **1,762 liquid names** (adv₂₀ ≥ 500k, close ≥ $10). Coverage by band: RS 90+ 39%,
**RS 70-89 22%**, under 70 10%. All liquid RS ≥ 70 = **517 names**, so ceiling 600 covers the band
with headroom. Cost ≈ **+$0.20/day** on a $0.50/day theme stack.

**⚠ What this does NOT fix, stated so nobody re-derives it.** The 100 unthemed liquid RS-90+ names
are **not** a reach problem — verified 2026-08-05, replicating `get_rs_leaders`' own filters:

| cause | count |
|---|---|
| removed upstream by `is_sector_filtered` (Healthcare < $50) | **28** |
| inside the pool, seen, never assigned | **72** |
| outside the pool's reach | **0** |

The filter cut includes **CDNA (rank 1, RS 100) and TRAX (rank 2, RS 99.9)** — 5 of the top 20. The
72 fail because assignment can only place a name into a theme that ALREADY EXISTS, and 104 narrow
themes averaging 3.3 members often have no home for a strong name; 12 of those 72 sit inside
discovery's own top-40 seed. **That is theme SUPPLY — discovery breadth — a separate lever, still
top-40, deliberately not changed here.**

**Direction / risk**: strictly additive membership; no theme is born, retired or renamed by this.
The accepted cost is junk assignments — watch the next nightly's assignments for names joining
themes they do not belong to.

**Reversion**: the two constants. Tests `tests/test_theme_assignment_pool.py` are re-based on the
CONSTANTS rather than literals, so a future widening still exercises the floor and the ceiling
instead of passing vacuously.

### 2026-08-04 (b) — #531 nightly THEME QUALITY check (two regression guards, observability-only)

- **Trigger**: operator, verbatim: *"i'm really asking for quality checks regularly to make sure
  our themes are solid without me needing to check it and review manually."*
- **What shipped**: `health_checks.run_theme_quality_check`, wired into `_post_nightly_audit_job`
  (17:30 ET) the same way `run_inert_sweep_check` is. Two signatures, each isolated (one bad query
  can't blind the other): (A) a theme retired while its last-known state was healthy (Fading,
  `rs_avg` populated, then silently vanished — the #368/F2 regression guard); (B) a member pruned
  from a still-alive theme while its RS was rising over F3's hold window (the #368/F3 regression
  guard). Two other candidates (fragmentation, churn) were measured and DROPPED — see below.
- **Evidence** (CHANGE_PROCESS — this is observability, not a strategy/detection-criterion change,
  so no backtest-before-deploy gate applies, but the same measurement discipline was used anyway):
  97 real trading days of prod `mi_themes` + RS history, captured once via read-only ssh. Signature
  A: 6 of 165 distinct retirement incidents fired, every one hand-verified real (129 of the 165 were
  a DIFFERENT legitimate mechanism — ADR-0025 Arm-A 2-member dissolve / engine-drop consolidation —
  and correctly excluded). Signature B: 25 of 164 prune-shaped exits fired; of the scored ones, 79%
  recovered to RS≥50 in 10 sessions vs 36% of the falling control — the spread, not the raw count,
  is what proves these are real defects. Full write-up + both-ways proof + live dry run against
  real prod data (2026-08-04): `docs/analysis/531_theme_quality_measurement_2026-08-04.md`.
- **Dropped**: fragmentation (251 day-level firings / 122 distinct theme-name pairs — the real
  fragmentation signature is F1's territory, "zero pairs ever proposed," not "themes overlap";
  overlap is Arm-B's normal input) and churn (42/301 short-lived names, mostly normal Nascent
  mortality — the operator's "repeatedly, in one neighbourhood" qualifier needs ticker-overlap
  clustering not yet built). Both reasoned through in the measurement doc.
- **No-money / observability-only**: reads `mi_themes` + `mi_audit_log`, writes only audit rows +
  Telegram. Nothing under `broker/`, no detection-criterion or safeguard changed.
- **Dedupe**: `db.get_theme_quality_alerted_targets`, mirrors `run_inert_sweep_check`'s idiom
  exactly (`mi_audit_log` IS the state, `SELECT DISTINCT split_part(summary, ':', 1)`, fails OPEN).
  Each finding is a discrete past event (a specific retirement, a specific prune) — dedupe is
  permanent once announced, no resolve/re-open path (unlike the null/job-liveness sweeps' reconcile).
- **Reversion-flag**: NEW (first check of this class). Revert = remove the `run_theme_quality_check`
  call site in `_post_nightly_audit_job`.
- **Status**: ✅ **LIVE — verified in prod 2026-08-31, not inferred from the commit.**
  `mi_audit_log` holds **16 `theme_quality_clean` rows, 2026-08-06 → 2026-08-28**, plus the
  guards' own firings (`theme_member_pruned_while_rising` ×4 to 08-25,
  `theme_retired_while_healthy` ×1, `theme_assignment_barren` ×1) — the check runs nightly
  AND has caught real cases. Shipped `5ef6781b` (2026-08-04). Day-of status was built +
  tested, 26 new tests, suite 4379 green, NOT deployed.
- **Caveat for verify-live** (RESOLVED — kept for the record): when written, #368's F2/F3
  were committed locally but not yet in prod, so the first live run was expected to alert on
  the 2026-08-04 Bitcoin Mining retirement (a real, correct alert on a defect the fix had not
  reached production for). F2/F3 shipped 2026-08-04 (see the member-pruning and retire-streak
  bullets at the top of this file, repaired 2026-08-26) and the prune guard has fired in
  prod since (`theme_member_pruned_while_rising`, 4 rows through 2026-08-25); the caveat
  no longer applies.
  first live run of this check WILL alert on the 2026-08-04 Bitcoin Mining retirement (a real,
  correct alert on a defect the fix hasn't reached production for yet, not a broken new guard).

### 2026-08-13 — #479 themes state-change message redesign (observability-only)

- **The nightly STATE CHANGES message is now theme-first** (operator-specified
  2026-08-12): keeps NEW themes, upward stage transitions, shadow→live
  graduations (folded in from `promote_shadow_themes` via a `changelog` param —
  no more standalone 🎓 ping seconds before the state message; standalone send
  remains when no changelog is passed), GROUP-level RS deterioration, stage-downs,
  retirements. Per-name RS deterioration, MA breaks, composition adds/prunes and
  nascent churn are COLLAPSED to on-demand mi_audit_log rows (`rs_deterioration`,
  `ma_break`, `theme_composition_churn`) surfaced by the existing audit-log
  command; composition state stays on `/themes`. Detection layer unchanged.
- **Group-deterioration rule is DERIVED, not picked**: ≥3 members down >15 RS in
  ~2wk AND binomial-tail P(X≥x | theme size, day base rate) ≤ 0.02 — measured on
  89 trading days (3,902 theme-days): 1.69 fires/day observed vs 0.16 by chance
  (10.4x lift); a raw count alone is chance-dominated at every k (k≥2 lift 1.0x).
  Constants + full derivation: `state_alerts.py` top-of-file.
- **Advisor output bounded by demand, not cap** (`_call_advisor`): brevity
  contract added to the system prompt (verdict first line, ≤6 sentences) — the
  freeform caller fills ANY cap (p50=600 at the old 600 cap; the only opus-5
  call pegged 1500), so raising `theme_advisor_*` again is banned in the
  registry evidence. `theme_validation` cap 400→1000 (schema-bounded, zero
  truncations, max completed 385/400 — straight raise).
- **Reversion-flag**: restore `send_state_alerts`'s previous flat-section render
  (git) and drop the `changelog` param default to revert exactly.

### 2026-08-04 — #368 crypto→AI-conversion consolidation (four fixes, live-on-deploy)

- **Trigger**: #368 labelling — 5 of the operator's 9 theme-credit false positives are ONE
  systematic mistake (converting miners filed under crypto mining: HUT ×2, WULF, CLSK, IREN).
  Operator asked for "the crypto to AI definition" next. Diagnosis: NOT a missing definition —
  the 7/08 birth thesis already said "miners as power/data-center landlords for the AI compute
  boom"; the phenomenon fragmented across 8+ names because (M1) Arm-B Stage A had no family for
  either framing (zero pairs EVER proposed — audit-verified), (M2) single-print pruning evicted
  the rising recovery cohort on day 2 of its ignition, (M3) name-vs-description validation
  removed WULF/CORZ from the AI theme whose own thesis was the conversion (7/27 dissolve + 14d
  cooldowns), (M4) the retire counter ran through a hysteresis-held recovery row and retired the
  lineage 8/04 — the day after it re-qualified healthy.
- **What changed**: (F1) `compute_infra` family — **WITHDRAWN before ship, see above; the working
  tree carries no change to `theme_merge_arm.py`**; (F2) `_count_consecutive_fading` counts weak (rs_avg-NULL) Fading rows only;
  (F3) rising-recovery hold on hard+soft prune (`PRUNE_HOLD_WINDOW_SESSIONS=6`,
  `PRUNE_HOLD_MIN_POINTS=4`, strict newest>oldest; `ticker_prune_held_rising` changelog); (F4)
  `_validate_theme_membership(thesis=…)` from all three callers, garbage-guarded.
- **Evidence** (CHANGE_PROCESS r1, backtests on frozen prod exports —
  `scripts/probes/_368_crypto_ai_consolidation_replay.py` + `docs/analysis/
  368_crypto_ai_consolidation_2026-08-04.md`): lifecycle replay's current-arm reproduces prod's
  exact death sequence (held-Fading rs_avg 84.9 on 8/03 → retired 8/04); fixed arm holds all six
  cohort names in ONE lineage 7/22–24 and SURVIVES to 8/04 holding APLD CBRS CIFR CRWV HUT vs
  prod's zero surviving themes. F3 backtest N=13 scored (25 held): 77% recovered vs 31% falling
  control; FP cost median 6 sessions (nightly re-check). F2 blast radius: 14 affected
  retirements Jun–Aug, several plainly wrong. Stage-A replay: crypto×AI pairs available from
  6/01; 1–2 budget displacements/night (bounded; cooldowns not modeled).
- **Anticipated effect**: the framings meet the corpus-cleared adjudicator on night 1 both
  exist → one surviving conversion lineage instead of competing shards; igniting recovery
  members stay through their V-bottom; themes stop retiring the day after recovering; ~14/2mo
  fewer wrong retirements; validator keeps thesis-consistent members. The 3 uncovered
  mislabelled alerts (HUT 5/06 · WULF 7/06 · CLSK 7/14) belong to the Lane-2 v2 registry flip
  (operator-gated) — deliberately NOT duplicated here; ditto shadow_v2 re-mint churn (birth-gate
  Phase 1 owns it).
- **Reversion-flag**: F1 NOT SHIPPED (withdrawn at its gate) · F2 REFINEMENT of the FADING_RETIRE_AFTER
  mechanism · F3 NEW (first trajectory term on pruning) · F4 NEW (first thesis input to
  validation). Each independently revertible (family entry / streak predicate / hold branch /
  thesis kwarg).
- **Pre-deploy gate**: run the probe's `--adjudicate` (~4 Haiku calls ≈ $0.02) where the key
  lives — expected MERGE (P1-0721) / MERGE (P2-0804) / DISTINCT (optical negative control). A
  DISTINCT on P1 means the adjudicator won't consolidate the framings — hold F1, the rest stand
  alone. The Stage-B pass record is NOT invalidated (its hash covers the adjudication prompt +
  tool schema only; F1 is Stage-A).
- **Status**: built + tested (40 new tests, suite 4378 green), NOT deployed, NOT committed —
  awaiting the adjudicate check + operator review.

### 2026-07-27 (d) — Phase-1 BIRTH GATE + shadow_v2/coverage_probe retirements (built dark, flag OFF)

- **Trigger**: theme-consolidation design ruled ADOPT on all six decisions
  (operator, 2026-07-27) — ~5.9 births/day vs a 56% lifetime corpse rate; the
  `shadow_promoted` path graduates with NO floor/adjudication (RS-38.7 Hospital
  and RS-49.1 Utilities graduated the same night the design was ruled).
- **Evidence** (CHANGE_PROCESS r1 — threshold change, backtest attached):
  254-birth replay, `docs/analysis/theme_birth_gate_derivation_2026-07-27.md`.
  Key: birth-RS LEVEL does not separate matured (median 90.8) from corpses
  (88.5); flat ≥70 = 19.4% FN at 40% precision; 19% of ALL matured themes were
  born <70 and their PRE-birth 5-session trajectory separates (+2.5 vs −5.3
  median) → derived cell = RS≥70 OR Δ5≥0. July's 106 births replayed through
  the full gate: 50 join + 5 two-sighting kills + 7 floor kills → 44/month
  ≈ 2.4/day (design estimate 40–55 ✓).
- **Anticipated effect** (when flipped ON): births ~5.9/day → ~2.4/day, biased
  to twice-sighted, level-or-rising cohorts; the sub-RS-70-and-falling
  graduate class never births; board drifts toward its 86 median; corpse rate
  falls (watch via the `theme_birth_gate` audit counters + §7 metrics).
- **Reversion-flag**: NEW (first gate on theme birth; no prior criterion on
  this surface). Instant revert = mode 'off' (byte-identical, no redeploy).
- **Status**: built dark, mode 'off' — NOT deployed, NOT flipped. 3-state
  toggle (off/observe/on — coordinator+operator-agreed same day: a dark
  deploy of a 2-state flag teaches nothing; observe accrues forward verdicts
  BEFORE the gate acts, matching how every prior flip validated). Deploy plan:
  ship in 'observe' → the run-count-gated review
  `theme_birth_gate_observe_calibration` (data_gated_reviews.yaml) fires at
  20 observe rows ≈ 2 trading weeks → operator signs the derived cell + the
  FORWARD FN list (CHANGE_PROCESS r3 — findings stated, operator rules; the
  254-replay is the backtest, the observe period the field validation) →
  fresh ADR-0030 judge eval → mode 'on'. Tests:
  `tests/test_theme_birth_gate.py` (30) — off byte-identical, observe
  zero-behavioural-difference (writes/Telegram parity pinned) with verdicts +
  levers + inputs recorded and the ledger populating, every threshold at its
  boundary, weekend two-sighting, existing-live-themes-untouched, a/a2 port
  present in Lane-1 discovery when acting.

### 2026-07-27 (c) — #167 registry: birth-bias correction + decision-record telemetry (still dark, flag OFF)

- **Trigger**: first registry replay (operator-run, ~$0.40). Architecture
  CONFIRMED — 23 near-duplicate pool proposals → 4 distinct narratives + 4
  joins; the miner chain assembled (WULF 07-06 birth → CLSK 07-14 join → HUT
  07-20 join) and power-landlord vs hardware-supply-chain stayed correctly
  SEPARATE. Regression: a bias TOWARD seeding — 06-17 AEHR+JBL (pool-caught)
  filed as two separate seeds instead of a birth; 07-20 IREN seeded while HUT
  joined the same story. Seeding was the costless choice and nothing pushed
  back.
- **What changed**: (1) `_build_lane2_registry_prompt` decision block
  reordered JOIN → NEW → SEED: NEW framed as the EXPECTED outcome when 2+
  visible names share a story ("never file the same story as two separate
  seeds"), a stock fitting an ACTIVE narrative "must be JOINED, never
  seeded", SEED demoted to explicit last resort + a pre-answer seed
  self-check. Deterministic birth guards UNCHANGED (>=2 members, >=1 today
  anchor, duplicate tripwire) — threshold moved, not the floor.
  (2) DECISION RECORD (operator: "if this info is captured, it allows us to
  tune over time"): one `lane2_decision_record` mi_audit_log row per
  evaluated night (JSON detail: offered names, per-name outcome
  join/birth/seed/none, watch list offered, seed→narrative conversions with
  origin date + lag_days, keyed off the PRE-hygiene seed map so a re-alerting
  seed that joins still counts). Never written on backfill runs (forward-pure
  stream). Makes the seed-vs-birth threshold EMPIRICAL: a converting seed was
  a deferred birth; an expiring one was correctly held.
  (3) Run-count-gated review `lane2_seed_birth_calibration` registered in
  `data_gated_reviews.yaml`: fires at 20 decision-record nights (~4 trading
  weeks at the replay-era rate, ~15-20 seed decisions — a directional
  conversion read), date field non-blocking per the 2026-07-26 ruling;
  records only accrue with the flag ON, so it cannot fire pre-flip.
- **Reversion-flag**: REFINEMENT of (b) (prompt-instruction ordering +
  telemetry; no population/guard change; never flipped ON).
- **Status**: built dark, flag OFF (OFF byte-identical re-pinned; 26 tests).
  Next gate: re-run the replay post-deploy — 06-17 and 07-20 must now
  birth/join, correctly-silent days must stay silent, both known-goods
  survive.

### 2026-07-27 (b) — #167 Lane-2 v2 reframed: incremental narrative REGISTRY (supersedes same-day pool draft; still dark, flag OFF)

- **Trigger**: operator, same day, on the pool-draft replay results — "is there
  a smarter way to optimize this given that the overlap and rediscovering the
  same thing there's an efficiency cost here?" The pool replay (2026-06-08 →
  07-24, $1.67) proved recall (23 proposals vs v1's 2; both audited misses
  caught) but 18 of 23 were ONE narrative re-minted under different wordings —
  a 10-day window re-reading the dominant story nightly re-derives and re-names
  it by construction, and each near-duplicate could auto-promote into live
  `mi_themes` (`narrative_cogap` is allowlisted).
- **Evidence**: the pool replay itself (operator-run; per-day results were in
  `/tmp/lane2_replay.json` in apollo-market) — e.g. 06-12/06-16/06-17/06-24/
  06-25/06-30/07-06/07-07/07-08/07-22 are all "AI data-center infrastructure
  buildout/power/leasing" re-namings. Also the double cost: ~25-35k input
  tokens/night re-sending 10 days of full documents.
- **What changed** (design, not population): same flag, same qualifying rule,
  same evidence budgets, same `_LANE2_NARRATIVE_RULES` verbatim. The WINDOW
  mechanism is replaced by carried STATE — see the Lane-2 architecture bullet
  above for the full mechanics (registry roster + watch-list seeds + JOIN /
  BIRTH / SEED contract + drift bounds). Superseded pool code removed:
  `_dedupe_lane2_pool`, `_build_lane2_v2_prompt`, `db.get_ep_alerts_window`.
  New: `db.get_lane2_active_narratives` / `get_lane2_pending_seeds` /
  `persist_lane2_seeds`, `theme_engine._discover_lane2_registry` /
  `_lane2_registry_clean` / `_build_lane2_registry_prompt` /
  `_norm_narrative_name`; constants `LANE2_REGISTRY_MAX_MEMBERS=12`,
  `LANE2_ROSTER_MAX=20`, `LANE2_SEED_STORY_BUDGET=160`.
  `LANE2_WINDOW_TRADING_DAYS=10` is retained as the registry MEMORY horizon
  (absence-based expiry, the `get_active_themes(stale_after_days=…)` idiom —
  but in TRADING days at the operator-measured chain length: the 7-calendar-day
  live-theme idiom would expire the WULF→CLSK seed link (8 calendar days) one
  day short). Drift bounds: name+thesis frozen at birth; a join needs ≥1
  same-day qualifying addition (no self-sustaining touches); FIFO member cap;
  hindsight/backfill runs never write seeds. Auto-promote interaction: a join
  refreshes ONE (run_date, name) row per story, so `DISTINCT ON (name)` gives
  auto-promote a single cohort per narrative; re-promotion happens only while
  the story is genuinely touched, and live rows age out via the themes 7d
  recency cap — bounded, not ever-growing.
- **Anticipated effect** (when flipped ON): near-duplicate proposal stream
  collapses (pool replay's 18-of-23 → joins of one narrative); prompt cost
  drops from ~25-35k to today's-docs + compact roster; cohorts accrete across
  days indefinitely while touched (no 10-day forgetting cliff); audit rows show
  `v2reg … N join + M new + K seed(s)` + the duplicate tripwire.
- **Reversion-flag**: REFINEMENT of 2026-07-27 (a) below (same intent — richer
  input + cross-day accretion — different window mechanism; (a) was never
  flipped ON, so no live behavior reverts).
- **Status**: built dark, flag OFF (OFF byte-identical re-pinned). NOT
  deployed, NOT committed at authoring time. Registry-mode replay over the same
  era is the next gate; then operator sign-off on the surviving-narrative list
  (CHANGE_PROCESS r3), fresh judge-robustness eval (ADR-0030), then
  `set_lane2_grouping_v2_enabled(True)`.

### 2026-07-27 (a) — #167 Lane-2 grouping v2: grounded input + 10-trading-day rolling window (SUPERSEDED same day by (b) — never flipped ON)

- **Trigger**: 167 grouping-quality audit
  (`docs/analysis/167_lane2_grouping_quality_2026-07-27.md`) — verdict "precise
  but shallow": 3 genuine misses + 1 borderline on 13 judgeable no-story days,
  all the same shape (cross-sector demand-side story written as company
  events). Operator ruled exactly two changes (2026-07-27): feed the real
  evidence; 10-TRADING-day rolling window. Proposals 3–5 explicitly out of
  scope.
- **Evidence**: forward-era replay data in the audit — `catalyst` hard-truncated
  at 500 chars in 62/62 qualifying alerts with only 280 fed (~4% of available
  evidence read), `grounded_text` populated 50/62 (81%) at median 7,413 chars
  and unused; the WULF 07-06 → CLSK 07-14 → HUT/IREN 07-20 accretion (pairwise
  corr +0.47..+0.87) structurally invisible same-day; prompt bias tested and
  DISCONFIRMED (§5) — the narrative-definition prompt text is therefore shared
  VERBATIM between v1/v2 (`_LANE2_NARRATIVE_RULES`), never reworded as a recall
  lever. Window size operator-measured on the real cohort: full chain = 10
  trading days; 5 misses WULF, 7 never sees the whole cohort.
- **Anticipated effect** (when flipped ON): the 15-per-33-runs `<2`-gate drops
  shrink (lone same-day alerts group against the pool); input-source mix
  appears in every `narrative_theme_discovery_ran` audit row
  (`input grounded=G analysis=A catalyst=C` — degraded days visible); expected
  recall gain on the 3 audited miss classes, precision guarded by the
  same-day-anchor rule + unchanged narrative-definition prompt + replay before
  flip. More/different proposals reach the judge's `active_narratives` ⇒
  grade surface drifts ⇒ ADR-0030 `preflight_judge_eval_gate` fires on deploy —
  expected, requires a fresh judge-robustness eval, never suppress.
- **Mechanics**: DB flag `lane2_grouping_v2` — currently ON in paper (default fail-closed off)
  (`db.get/set_lane2_grouping_v2_enabled`, mi_safeguard_state, instant no-redeploy revert). Window
  fetch `db.get_ep_alerts_window` (per-(ticker,day) best row, live-source only);
  cross-day dedup in `theme_engine._dedupe_lane2_pool` — highest ep_score wins,
  tie → latest date (same semantics as `get_today_ep_alerts`' same-day
  `DISTINCT ON ... ep_score DESC`, extended across days; the strongest alert
  carries the substantive evidence). Anchor set computed BEFORE dedup. Budgets:
  grounded 10,000 chars (= FULL doc in practice — era max 9,615; a 2.5k
  head-slice was tested on the replay pull and FALSIFIED: SEC boilerplate fills
  the head, the linking evidence sits at char 2.4k–6.6k, and the story-naming
  web synthesis is LAST in `build_grounded_text`'s order) / analysis 1,500 /
  catalyst 500. Realistic cost ≈ 25–35k input tokens ≈ $0.08–0.11/run at
  Sonnet 4.6 rates (worst-case ≈ $0.18). Trading-day math via
  `collector.prev_trading_days` (ET-frame, weekend-skipping).
- **Reversion-flag**: NEW (first change to Lane-2 grouping behavior since the
  lane shipped; no prior threshold on this surface).
- **Status**: SUPERSEDED same day by entry (b) above (registry reframe) after
  the replay exposed structural near-duplication — never flipped ON, no live
  behavior existed to revert. The two operator-ruled levers (rich input +
  cross-day accretion) carry forward into (b); the pool mechanics
  (`_dedupe_lane2_pool`, `_build_lane2_v2_prompt`, `db.get_ep_alerts_window`)
  were removed with the reframe.

### 2026-07-18 — judge → narrative-radar feed for judge-only theme inferences (#322)
- **What**: new `agents/market_intelligence/judge_theme_gap.py` +
  `db.upsert_judge_theme_gap_candidate` — when the judge's `fire_axes` lights
  theme/narrative on a ticker neither Lane 1 nor Lane 2 tracks, write a
  `source='judge_inferred'` candidate into `mi_theme_candidates_shadow`. Wired into
  `ep_detector.py::_judge_shadow` right after the judge's DB-first write succeeds,
  own try/except (SHADOW invariant — never disturbs the judge/alert path).
- **Why**: the judge (JBL 6/17, AI-infra) can make a single-name semantic theme
  classification no existing lane structurally can (see the section above) — that
  signal was previously discarded to free-text `judge_rationale` and lost forever.
- **Anti-circularity**: `judge_inferred` excluded from `AUTO_PROMOTE_THEME_SOURCES`
  and from `get_narrative_theme_candidates`'s source filter (can't feed the judge's
  own future `active_narratives` input) — surface-only, operator-promoted, same
  discipline as coverage_probe's walls.
- **Display**: `agent.py::_handle_theme_query` (the proactive `/themes` board, not
  just the reactive lookup) now renders a "🔎 Judge-inferred theme gaps" section
  from `get_shadow_theme_candidates(include_probe=True)` filtered to
  `source == 'judge_inferred'` — a separate DISPLAY-only read, so today's
  visibility doesn't touch the anti-circularity wall (verify-operator-facing-
  surface: DB rows alone are not a surface).
- **Honesty fix**: a single judge fire is below the 3-member `/promotetheme` floor
  (`theme_engine._PROMOTE_MIN_MEMBERS`) — docs/audit text say so explicitly rather
  than imply a lone row graduates on demand.
- **Tests**: `tests/test_judge_theme_gap.py` (20 cases) — predicate/formatting
  logic, feed wiring, and the two anti-circularity pins (auto-promote reader +
  promote-path re-filter both drop `judge_inferred`; the active-narratives reader
  never matches it).
- **Reversion flag**: remove the `feed_judge_theme_gap` call site in
  `ep_detector.py::_judge_shadow` to fully disable (SHADOW-only; no grade/tier
  impact either way).
- **Verify-live**: watch `mi_theme_candidates_shadow WHERE source='judge_inferred'`
  for real rows after a judge run fires `fire_axes` on an untracked ticker; confirm
  it never appears via `get_narrative_theme_candidates` or a promoted live theme.

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

### 2026-07-17 — assignment pool: fixed top-40 count → RS-level floor (#476)
- **What**: the ASSIGNMENT candidate pool (`_build_theme_pools` → the wider
  `assignment_pool`) now selects names with `RS ≥ ASSIGN_POOL_RS_FLOOR` (90)
  among the top `ASSIGN_POOL_CEILING` (200) leaders, instead of a fixed
  `leaders[:40]`. The `get_rs_leaders` fetch was raised 60→200. DISCOVERY keeps
  `leaders[:40]` (assignment-only widen — discovery has velocity/turners/
  clusters for emerging names and shouldn't force-cluster static singletons).
- **Why the prior rule was wrong**: a fixed COUNT floats the effective quality
  bar with how crowded the RS top is. On a bunched day (50 names ≥ RS 98) the
  40th slot sits at RS 98.4, so genuinely-strong uncovered names (RS 82-96) get
  shut out of assignment to the existing themes they clearly fit — the biotech
  elite-orphan symptom (#476). A name isn't less theme-worthy because 40 others
  spiked to 99 today; the floor gives a consistent bar (with a ceiling as a
  euphoric-tape backstop).
- **Evidence/design**: `docs/analysis/476_pool_threshold_design_2026-07-17.md`
  (measurements: real RS≥90 pool = 83 via the liquidity-filtered fetch;
  advisor-reviewed: floor+ceiling, assignment-only). Fed the theme axis →
  HIGH-tier, so no-money but money-ADJACENT → verify-live discipline.
- **Reversion flag**: revert the `_build_theme_pools` assignment branch to
  `leaders[:40]` (or set `ASSIGN_POOL_RS_FLOOR` = 999) to restore exactly.
- **Verify-live**: the next nightly run's assignments (`ticker_assigned`
  changelog / the /themes board) — the wider pool should assign strong
  sector-coherent names to existing themes (e.g. autoimmune ZBIO/DNTH → the
  immunology theme) and NOT junk-assign marginal names. Revert if junk.
