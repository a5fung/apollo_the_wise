# #471 — ADR 0032 Phases 2-3: re-granularization + ecosystem auto-discovery (2026-07-18 as-built design record)

**Date:** 2026-07-18 · **Status:** DESIGN RECORD — Phase 2 is BUILT + ARMED (operator-flipped
2026-07-16 17:15 ET, first armed run VERIFIED-LIVE 2026-07-17 17:04 ET); Phase 3 is DESIGNED, NOT
BUILT. **No code changed by this doc.**
**Supersedes where they diverge:** `docs/analysis/theme_ecosystem_phase23_design_2026-07-14.md`
(the pre-probe spec — its Route-A "PARENT_CHILD rescues the vuln-mgmt fixtures" claim was
**falsified by the §1.4 A1 probe** on 7/16; this doc records the as-built mechanism and the
Route-B reframe). Spec parents: ADR 0032 (Part C / D2 / D1), ADR 0025 (Arm-B adjudicator),
`docs/setups/CHANGE_PROCESS.md`.
**THE LINE:** themes are a no-money detection surface (briefs + shadow-judge theme-axis only), but
granularity is operator-signed methodology — every flip here was/is operator-NAMED; thresholds are
design + validation pins, never agent-flipped.

All `file:line` cites verified against the working tree on 2026-07-18.

---

## §0 What changed since the ADR was written (read first)

ADR 0032 Part C (D2) specified: route Pass-1 protect-strip subset-of-parent conflicts to the
ADR-0025 Arm-B **PARENT_CHILD** adjudicator; acceptance fixture = the killed vuln-mgmt births
survive as children of the cyber theme. Three material updates from execution (7/14–7/17):

1. **The fixture set is 3, not 2.** A third cyber vuln-mgmt birth was killed 7/15 ("Cyber
   Vulnerability & Exposure Management") — same protect-strip pattern. Blast radius re-verified:
   **156 historical `theme_pass1_protect_strip` events, 3 newborn-kills** (all cyber vuln-mgmt),
   153 BOTH_PROTECTED established-pair strips that any routing must leave byte-identical.
2. **The A1 probe FAILED for Route A — and that redefined the mechanism.** The real corpus-cleared
   adjudicator returns **DISTINCT** (order-independent) on all 3 cyber fixtures: vuln-mgmt is a
   *sibling* of "Network Security & Zero-Trust Edge" (both sub-domains under E-CYBR — matching
   Marios), not its child. No broad "Cybersecurity" parent theme exists for Route A to nest under.
   A coexist-on-DISTINCT reframe was considered and **scratched** (advisor: coexist *duplicates*,
   it doesn't *decompose*). **Route B (deliberate split) is the actual rescue mechanism**: the
   mis-named 11-member blob is really all-of-cyber, and the split decomposes it into its real
   sub-themes. Route A stays built and armed — inert-but-harmless on the cyber case (fail-closed
   DISTINCT → strip + audit) and correct for a genuine future broad-parent × narrow-child pair.
3. **The flip already happened.** `THEME_SUBTHEME_ARM` flipped ON by the operator 7/16 17:15 ET
   (DB toggle, read once per run). First armed run 7/17 17:04 ET verified-live: Route-B split
   landed — parent 12→9 members, new child "Cyber Exposure Management & Vulnerability Assessment"
   (≈QLYS/TENB/RPD) born with `parent_theme` set, `theme_dominant_split_eligible` fired
   (eco=E-CYBR, members=12, rs80=11). **Day-2 stability observation = the 2026-07-18 nightly run**
   (open checkpoint, see §3.3).

---

## §1 Phase 2 as built — the re-granularization mechanism (file:line-anchored)

### §1.1 Arming + constants

- **Toggle:** `mi_safeguard_state` row `("theme_subtheme_arm", "paper")` —
  `db.py:2866-2901` (`get_theme_subtheme_arm_enabled` / `set_theme_subtheme_arm_enabled`).
  **Fail-closed**: any read error or missing row → OFF → the engine is byte-identical to
  pre-Phase-2 (pinned in CI). Resolved **once per run** at `theme_engine.py:5320-5334`
  (`run_theme_engine` builds the per-run `subtheme_ctx` via `make_subtheme_route_ctx`, `:3892`) —
  flip timing vs a running engine pass is race-free.
- **Pins (operator-signed at the 7/16 flip):** `theme_engine.py:278-290` —
  `SUBTHEME_C_MIN=0.8` (T4 containment) · `SUBTHEME_C_MULTI=0.34` (T5 sole-parent) ·
  `SUBTHEME_MIN_MEMBERS=3` (T6) · `SUBTHEME_ROUTE_CAP=2`/run (T7) ·
  `SPLIT_DOM_MIN_MEMBERS=10` · `SPLIT_DOM_MIN_STRONG=8` · `DOM_SPLITS_PER_NIGHT=2` (Route B).
  Any CHANGE to these = CHANGE_PROCESS N≥10 backtest + operator sign-off (§2.3).

### §1.2 Route A — Pass-1 protect-strip → Arm-B PARENT_CHILD adjudication

**The 2-3-line mechanism:** inside `_merge_overlapping_themes` Pass 1, at the `j_protected`
branch (`theme_engine.py:4271-4290`) — i.e. exactly where a this-run newborn overlapping a
protected incumbent would be stripped — the hook calls `_route_a_subtheme(i, j, …)` (`:4003`)
BEFORE the strip. If every trigger gate passes, the pair goes to the REAL ADR-0025 Arm-B
adjudicator (`adjudicate_merge_pair`, prompt v2, parent=A newborn=B, `:4083-4093`); on
`PARENT_CHILD/child=B` the strip is **averted**: `themes[i]["parent_theme"] = parent` and
`sub_theme_parents[newborn] = parent` are set on the live objects (`:4111-4113`) and the caller
`continue`s the pair loop (`:4287-4288`). Every other outcome falls through to today's strip.

**Trigger gates (in `_route_a_subtheme`):**

| Gate | Code | Meaning |
|---|---|---|
| T2 | `:4034-4037` | `i` must be a THIS-RUN newborn (`name_i not in protected_names`) — the 153 BOTH_PROTECTED historical strips are structurally unreachable |
| T3 | `:4040-4041` | no chains — a child (in `sub_theme_parents` or with `parent_theme`) is never re-routed |
| T6 | `:4043-4044` | newborn ≥ `SUBTHEME_MIN_MEMBERS` (3) |
| F-2 canonicalization | `:4046-4064` | **deterministic, no LLM, no cap**: a newborn whose ticker set matches an EXISTING child (`_subtheme_set_match` `:3915` — containment of the smaller set ≥ `SUBTHEME_C_MIN` with ≥ `MIN_SHARED_FOR_MERGE` shared) is FOLDED into it (`_canonicalize_newborn_into_child` `:3930`, ticker union, audit `theme_subtheme_canonicalized`). The child's identity is its **TICKER SET, not its name** — the LLM name churns daily (operator F-2 ruling 7/16) |
| T4 | `:4066-4069` | containment `|i∩j|/|i| ≥ SUBTHEME_C_MIN` — containment, NOT Jaccard (fixtures were c=1.0 at Jaccard 0.25-0.33) |
| T5 | `:4073-4075` | `_sole_parent_of` (`:3962-4000`): the argmax-containment protected incumbent must BE `j`, with every other protected incumbent ≤ `SUBTHEME_C_MULTI` or < `MIN_SHARED_FOR_MERGE` shared; existing children excluded from the disqualifier scan |
| T7 | `:4077-4080` | run-level budget: `routed < SUBTHEME_ROUTE_CAP` — a SINGLE counter shared across both merge calls (ctx built once, `:5325`, passed to merge_1 `:5341` and merge_2 `:5427`); every routed call consumes it regardless of verdict |

**Verdict handling (fail-closed everywhere — `:4100-4156`):**

| Verdict | Action | Audit |
|---|---|---|
| `PARENT_CHILD`, child=B | coexist — no strip; `parent_theme` + `sub_theme_parents` + `ctx["routed_children"]` set (`:4108-4123`) | `theme_subtheme_routed` |
| `PARENT_CHILD`, child=A (inverted) | strip as today (`:4124-4132`) | `theme_subtheme_route_inverted` (weekly review) |
| `MERGE` | strip as today — the strip IS the merge, members already inside the parent (`:4133-4141`) | `theme_subtheme_route_merge` |
| `DISTINCT` | strip as today (**F-3 fail-closed**, operator-signed; this is the branch the cyber case actually hits — Route B owns that rescue) (`:4142-4150`) | `theme_subtheme_route_distinct` (weekly review) |
| ERROR / any exception | strip as today; the arm never breaks the run (`:4151-4169`) | `theme_subtheme_route_error` |

**Child persistence chain (all existing machinery):**
mutation of the live `sub_theme_parents` dict → the Pass-1 coexistence carve-out protects the pair
for the rest of the run — **now symmetric** (§1.1-D / F-4, ALWAYS-ON, not toggle-gated:
`:4253-4269` checks `j_is_subtopic_of_i` AND `i_is_subtopic_of_j`; without the reverse check a
child that out-scores its parent is gutted the next night by the BOTH_PROTECTED tiebreaker) →
Pass-1.5 never absorbs a sub-theme (`:4377-4378`) → merge_2's protected set includes
`routed_children` (`:5418-5425`: `existing_names | this_run_sub_parents | routed_children`) →
`_save_themes` upserts `parent_theme` into `mi_themes` (`:1386-1397`) → next run reseeds
`prior_sub_parents` from the persisted rows (`:5312-5318`) → permanent coexistence.
Orphan remediation on parent death: `_emit_pipeline_diagnostic` clears the dangling
`parent_theme` in place (`:894-995` block) — child survives standalone.

### §1.3 Route B — the bounded deliberate split (the mechanism that actually fired)

`_nominate_dominant_split_themes` (`theme_engine.py:3104-3175`), called at Step 4b
(`:5357-5368`) to widen the fat-theme list. Arm OFF → `[]` with **no DB access**. Predicate
(per nominee, all conditions):

```
stage not in (Fading, Retired)  AND  no parent_theme            (:3135, :3144-3145)
AND eco := get_all_theme_ecosystems()[name] not in (None, E-UNASSIGNED)   (:3146-3148)
AND the ONLY active theme mapped to eco tonight                 (:3149-3150)  ← self-disarm
AND len(tickers) >= SPLIT_DOM_MIN_MEMBERS (10)                  (:3151-3153)
AND len(tickers) <= MAX_THEME_STOCKS (20)                       (:3154-3155)  ← >20 = existing fat trigger's job
AND |{m : rs_composite(m) >= 80}| >= SPLIT_DOM_MIN_STRONG (8)   (:3156-3161)  missing RS = not strong
≤ DOM_SPLITS_PER_NIGHT (2) nominees                             (:3142-3143)
```

`theme_dominant_split_eligible` audits **before** the LLM runs (`:3163-3171`) — trigger telemetry
fires even when Sonnet declines. The nominee then flows through the UNCHANGED `_split_fat_theme`
(`:2953`, Sonnet propose-one-split + decline path + `_SPLIT_MIN_STOCKS=3` floor `:5389`) with one
template arg: `reason_line="is ecosystem-dominant with no sub-theme structure (N stocks)"`
(`:5379-5383`; default `None` = byte-identical fat prompt, pinned).

**Split semantics = MOVE (F-5, operator-signed):** members are REMOVED from the parent (`:5393`),
child gets `parent_theme` (`:5401`) + `this_run_sub_parents` (`:5403`) → protected through
merge_2/cap_2 (`:5418-5432`). Day-2 child↔parent overlap is ZERO, so the merge pass has nothing
to re-adjudicate; the symmetric carve-out + `prior_sub_parents` reseed are belt-and-suspenders.

**Why the split STICKS (the load-bearing stability trace, Opus 7/16 + Fable-corrected):**
(1) carryforward is strip-only (`_apply_carryforward_deterministic_filter` `:3178` — never
re-adds removed members); (2) the LIVE discovery path excludes covered tickers (`covered_tickers`
built `:5026-5034`; `uncovered`/velocity/turner pools exclude them — shadow path has the identical
guard at `:642`) — once the child is its own covered theme, QLYS/TENB/RPD never re-enter the
discovery pool, so the daily re-propose→protect-strip→kill oscillation ENDS; (3) Route B
self-disarms structurally: post-split the ecosystem has 2 themes (sole-theme fails `:3149`), the
child is skipped via `parent_theme` (`:3144`), and the ≤9-member residue would still need to
re-qualify. Blast radius vs the live universe: **exactly 1 theme** trips (S,K)=(10,8) — the cyber
blob, zero over-fire; no ≥10-member dominant biotech theme exists (the orphaned-biotech gap is
**#476**, a separate stability/canonicalization problem, NOT Phase 2).

---

## §2 The deliberate-split trigger — N-gate + CHANGE_PROCESS status

- **The pins (S,K)=(10,8), cap 2/night, child floor 3** were validated pre-flip by: the §1.4
  probe redefined on Route-B criteria (1 fire, correct target, A2 no-biotech-over-fire holds),
  the 156-strip / 71-birth historical sweeps, the F-2 operator labeling of the ~15-row kill
  population (3 cyber = survive-as-child · 12 biotech = legit-kill for this mechanism), and the
  Route-B probe (real `_split_fat_theme` cleanly split QLYS/TENB/RPD off the 11-member blob,
  1 LLM call). The operator signed the cell by NAMING the flip ("flip it", 7/16).
- **Standing rule going forward:** these constants are methodology. Any change (loosening (S,K),
  raising caps, changing `SUBTHEME_C_MIN`) requires the CHANGE_PROCESS N≥10 backtest — re-run
  `scripts/probes/_0032_regran_replay.py` over the grid, operator signs the new cell, SSoT
  change-log entry in the same commit. Single-case tuning ("theme X didn't split") is flagged
  as such per CHANGE_PROCESS.
- **Reversion:** the arm is a reversible DB toggle (`set_theme_subtheme_arm_enabled(False)` →
  next run is byte-identical pre-Phase-2). Reverting is operator-named, like the flip.

---

## §3 The acceptance fixture — what it is now, and how it is asserted

**Original (ADR Part C):** "the two killed vuln-mgmt births (7/07, 7/13) survive as T- children of
the cyber theme." **As executed:** the set is THREE births (7/07, 7/13, 7/15), and they survive as
ONE canonicalized child via **Route B** (split-out sibling-content child under the cyber theme,
`parent_theme` set), not via a Route-A PARENT_CHILD verdict — the adjudicator correctly rules the
pair DISTINCT and the flip-gate caught that before shipping the wrong mechanism. Assertion is
three-level:

1. **CI (deterministic, no paid calls)** — `tests/test_theme_subtheme_routing.py` (19 tests, in
   the suite): arm-off byte-identical protect-strip + BOTH_PROTECTED pins · arm-on leaves
   BOTH_PROTECTED untouched · Route-A coexist on a mocked PARENT_CHILD ·
   **`test_route_a_three_rediscoveries_collapse_to_one_child`** — the 3-fixture ticker-set
   canonicalization (F-2) pin: re-discoveries fold into ONE child, never a second ·
   fail-closed matrix (MERGE/DISTINCT/inverted/ERROR → strip + the right audit) · cap/T4/T5/T6
   negative pins · G4 symmetric-carve-out regression (child out-scores parent, survives) ·
   Route-B eligibility matrix + nightly cap + no-DB-when-off + reason-line byte-identity.
2. **Probe / sign-off artifact** — `scripts/probes/_0032_regran_replay.py` (imports the LIVE
   adjudicator + trigger logic; read-only DB). Redefined accept criteria: **A1** = the cyber blob
   nominates under (S,K)=(10,8) and the real split yields the vuln-mgmt child (RAN 7/16, PASSED);
   **A2** = zero operator-labeled legit-kills rescued (the 12 biotech rows correctly skip — no
   protected parent, no dominant theme) (HOLDS); Route-A A1 (PARENT_CHILD on the fixtures) is
   RETIRED — DISTINCT is the *expected* verdict, pinned as such in CI.
3. **Verify-live (production)** — the armed-run checkpoints:
   - ✅ 7/17: `theme_dominant_split_eligible` (eco=E-CYBR members=12 rs80=11) · split applied —
     parent 12→9, child "Cyber Exposure Management & Vulnerability Assessment" (3) with
     `parent_theme` set.
   - **OPEN — day-2 stability (the 2026-07-18 ~17:00 ET run):** assert the child carries forward
     (row for today with same `parent_theme`, not re-absorbed/re-killed), the parent residue
     persists, Route B did NOT re-fire on E-CYBR (self-disarm — no new
     `theme_dominant_split_eligible` for the parent), and no
     `theme_pass1_protect_strip` re-kill of the child's ticker set. SQL: `mi_themes` rows for
     both names on today's `theme_date`; `mi_audit_log` since the run for the three event types.
   - **14-day gated review (TO FILE — not yet in `data_gated_reviews.yaml`, see §6):**
     `theme_regranularization_effect` — predicate: ≥1 active `parent_theme` child sustained AND
     depth(E-CYBR) ≥ 2 on the board; overdue-unmet → operator fork (prompt iteration vs threshold
     revisit vs revert).

---

## §4 Phase 3 — new-ecosystem auto-discovery lane (DESIGNED, NOT BUILT)

No Phase-3 code exists (verified: zero hits for `ecosystem_discovery` / `mi_ecosystem_proposals` /
`vetoecosystem` / `mi_theme_ecosystems_dynamic` in the tree). Design forks **F-8…F-12 are already
operator-APPROVED (7/16)** — what follows is the bounded build spec, updated to current anchors.
Full detail lives in the 7/14 doc §2.1-2.5; deltas and anchors here.

### §4.1 Substrate + anchors (current code)

- Mapping table `mi_theme_ecosystems` DDL `db.py:1300-1306`; accessors `db.py:9204,9215`.
- Taxonomy YAML at **repo root** `theme_ecosystems.yaml` (root-copy is canonical since the #474
  class-kill; baked into the image → runtime promotion MUST be DB-backed, never file-writes).
- Loader `theme_ecosystems.py`: sync module cache `_TAXONOMY_CACHE :102`, `get_ecosystems() :139`,
  `get_ecosystem_codes() :149`, `keyword_fallback_ecosystem :359`, `E_UNASSIGNED :52`,
  `_MAX_HAIKU_PER_RUN=25 :95`; assignment `assign_theme_to_ecosystem :402` +
  `ensure_theme_ecosystems :450` (sticky — never re-assigns); board render
  `format_ecosystem_board :621`; score `compute_ecosystem_scores :164`.
- Engine hook: `_map_ecosystems_nonfatal` `theme_engine.py:1464-1477` (ONE swallow-policy helper;
  call sites `:1580, :1657` promote paths + `:5529` nightly) — Phase-3's remap-on-promote uses the
  same accessor layer, NOT a new hook.

### §4.2 The lane (F-8…F-12 as approved)

Weekly job (Sunday 09:30 ET) over the E-UNASSIGNED substrate:
1. **Deterministic pre-cluster** (pure function): graph over unassigned themes — edge iff ≥1
   shared ticker OR a shared name-token (len ≥5, stoplisted); connected components ≥3 themes =
   candidate clusters. Nothing smaller reaches an LLM.
2. **Sustain gate:** cluster age ≥14d (earliest `assigned_at`) AND **two sightings ≥7d apart**
   with ≥50% member overlap (F-9).
3. **One Sonnet proposal per cluster, ≤2/run:** forced tool, `analysis_scratchpad` first;
   `decision ∈ {propose, abstain, fits_existing}`; `fits_existing` remaps to the existing e_code
   (the escape valve for Haiku under-assignment); e_code regex + collision guard vs the effective
   taxonomy.
4. **Grace state machine** (`mi_ecosystem_proposals`): sighted → pending (48h grace + one-tap
   veto alert) → live (hourly sweep, idempotent claim-then-act) | vetoed (30d cooldown;
   early re-surface only on material strengthening: members ≥ snapshot+2 OR RS80+ ≥ 2×) ;
   sighted → expired at 28d.
5. **DB-backed taxonomy extension** (F-10): `mi_theme_ecosystems_dynamic` table; **effective
   taxonomy = YAML ∪ active dynamic rows, YAML-wins on collision**; sync loader + async
   `refresh_dynamic_taxonomy()` cache (DB-down → previous cache/YAML-only, never raises);
   soft-delete retire + remap that bucket → E-UNASSIGNED; graduation = add to YAML at any deploy.
6. **Veto surface** (F-11): `/vetoecosystem` — 3-place wiring (handler + dispatch in `agent.py`,
   `BotCommand` in `channels/telegram.py::_register_commands`), **deploy scope `both`** (the
   `/partialnow` lesson); bare command = one-tap when exactly one pending; covers grace-veto AND
   retro-retire of a live auto bucket; YAML buckets never vetoable.
7. **Marking:** 🆕 prefix on dynamic buckets ≤14d old; every transition audited
   (`ecosystem_discovery_ran` heartbeat EVERY run · sighted · pending · promoted · vetoed ·
   cooldown_skip · resurfaced_early · retired · promotion_error).

### §4.3 The confirmation-bias bound (why this lane can't self-license)

ADR 0032 flagged the loop risk: an LLM that both proposes and confirms ecosystems would breed
buckets that then attract mappings that then justify the bucket. Bounds, in order of mechanism:
**bottom-up substrate only** (clusters form from price-action-born themes that ALREADY failed to
map — the LLM never sees a hypothesis first, it adjudicates a deterministic cluster); **abstain +
fits_existing are first-class outputs** (the escape valve prevents inventing a bucket for
mis-assignment noise); **two-sighting + 14d sustain** (one-off LLM enthusiasm can't promote);
**caps** (≤2 proposals/run, weekly cadence); **operator veto + 30d cooldown + retroactive
retire** (human oversight without human bottleneck — no-veto default-ship per the operator's
posture); **YAML-wins** (auto can never shadow or mutate the curated taxonomy); **audit +
soft-delete** (every mutation reversible, lineage kept). Mapping-quality follow-ups from 7/14
(subject-over-modifier prompt tightening, operator reassignment path beyond `/vetoecosystem`,
periodic mapping re-validation) belong to this phase's build card.

### §4.4 Phase-3 validation (shadow-then-ship — no flip toggle needed)

No-money read-model → default-to-ship posture, but nothing goes live unverified:
1. **Build dark-equivalent:** the weekly job ships with the state machine live but the substrate
   naturally near-empty (E-UNASSIGNED held ~1 theme at last count) — the lane idles by
   construction; the **heartbeat audit is the verify-live**, not a promotion.
2. **CI e2e synthetic:** seed 3 fake E-UNASSIGNED themes (backdated 15d) → pass 1 sighted →
   pass 2 pending + alert content pinned → sweep promotes (dynamic row, remap, 🆕 render) AND
   the veto branch (cooldown, skip, strengthened re-surface). All LLM calls mocked.
3. **Verify-live:** first Sunday `ecosystem_discovery_ran` heartbeat + one sweep audit +
   `/vetoecosystem` visible in the Telegram menu. The first REAL promotion is event-gated —
   file a data-gated review `ecosystem_discovery_first_promotion` (never seed prod).
4. **Sequencing:** ship AFTER the `THEME_MERGE_ARM` flip (F-13) + ≥1wk, so the substrate reflects
   the merged board (unmerged 2-member noise otherwise accumulates in E-UNASSIGNED and can
   cluster into fake ecosystems — the D4 dependency). Build may proceed in parallel.
5. **Defaults (48h grace / 30d cooldown / ≥3 cluster / 2-sighting / ≤2 proposals)** are approved
   design pins (F-12), recorded as operator-tunable constants at the top of the new module;
   tuning them later on evidence is a normal operator call, not CHANGE_PROCESS (no detection
   criterion changes — the lane only creates *display buckets*).

---

## §5 Shadow-then-flip validation plan (consolidated, current state)

| Item | State | Gate / next check |
|---|---|---|
| `THEME_SUBTHEME_ARM` (Phase 2) | **ON** (operator 7/16) | Day-2 stability = 7/18 run (§3.3) → 14d `theme_regranularization_effect` review (§6) |
| Route-A weekly audit review | standing | `theme_subtheme_route_distinct` / `_inverted` / `_error` events — human eyes weekly; DISTINCT-heavy weeks are EXPECTED (cyber-class cases belong to Route B) |
| `THEME_MERGE_ARM` (F-13, ADR 0025) | **OFF** — approved, not executed | Stage AFTER ≥1 clean armed subtheme run for diff attribution; the 7/17 run was clean → **stageable once day-2 passes**. Operator-named flip; §1.1-D symmetric fix is already live (rides nothing — shipped un-toggled) |
| Route-B / Route-A threshold changes | pinned | CHANGE_PROCESS N≥10 re-run of `_0032_regran_replay.py` + operator cell sign-off (§2) |
| Phase 3 | not built | Build → CI e2e → deploy scope `both` → heartbeat verify-live → event-gated first-promotion review (§4.4) |

---

## §6 Remaining build items (small, honest gap list — designed 7/14, NOT in the tree)

1. **F-7 divergence promotion** — approved pins `DIVERGE_MIN=0.34` / `DIVERGE_RUNS=5` (child
   containment in parent < min for 5 consecutive snapshots → clear `parent_theme`, audit) —
   **not built** (zero `DIVERGE` hits). Note: F-5 MOVE semantics makes Route-B children disjoint
   (containment 0 from birth), so the predicate as designed would instantly fire on them — the
   build must scope divergence-promotion to COEXISTING (Route-A) children only, or key on a
   different signal for split children. Flag for the build card.
2. **Ecosystem inheritance for children** — `ensure_theme_ecosystems` has no `inherit_from` /
   `method='inherit_parent'` path; the 7/17 child was mapped by the generic Haiku hook. Risk: a
   Haiku mismatch puts a child in a different ecosystem than its parent → corrupts `depth()`.
   Small deterministic add at the `:5529` call site.
3. **Board nesting** — `format_ecosystem_board` (`theme_ecosystems.py:621`) does not yet nest a
   child under its parent within an ecosystem group (`:28` comment defers it to Phase 2). Pure
   formatting; fixture-tested.
4. **`theme_regranularization_effect` gated review** — not in `data_gated_reviews.yaml` (owed per
   the 7/14 DoD; the 14d clock should run from the 7/16 flip).
5. **ADR 0032 change-log entry** — the ADR has no Change log section; the flip + the Route-B
   reframe (this doc) should be recorded there in the next code commit touching the area
   (SSoT-same-commit rule; this design session is doc-only + no-commit by card).

---

## §7 Operator sign-off asks (each: fork + 1-line rec)

- **O-1 — F-13 `THEME_MERGE_ARM` flip timing:** flip after today's day-2 stability check passes
  (1 clean armed run condition met) vs wait longer — **rec: flip on day-2 green** (corpus 14/14,
  symmetric fix already live, diff attribution satisfied).
- **O-2 — Phase-3 build authorization:** forks F-8…F-12 are signed; the remaining ask is naming
  the build + ship (deploy scope `both`) after O-1 + ≥1wk substrate settling — **rec: authorize
  build now, ship on the sequencing gate**.
- **O-3 — the §6 gap list:** file items 1-4 as PLAN.md tasks with ETAs (burndown gate may require
  an operator carryover if no offsetting closes exist) — **rec: file; items 2+4 first** (depth()
  integrity + the review clock already running).
- **O-4 — standing:** any (S,K)/C_MIN/cap change routes through CHANGE_PROCESS N≥10 + operator
  cell sign-off (§2.3) — no ask, restated as the rule of record.

## References

- ADR 0032 `docs/decisions/0032-theme-ecosystems.md` (Part C = D2/D1) · ADR 0025
  `docs/decisions/0025-theme-fragmentation-controls.md` (Arm-B adjudicator, corpus gate)
- Pre-probe spec: `docs/analysis/theme_ecosystem_phase23_design_2026-07-14.md` (superseded where
  it claims Route-A rescues the cyber fixtures; still the detailed Phase-3 build spec)
- Probe: `scripts/probes/_0032_regran_replay.py` · CI: `tests/test_theme_subtheme_routing.py`
- Operator labels: `scratchpad/F2_table.md` · PLAN.md `#471` line (full execution chronology)
