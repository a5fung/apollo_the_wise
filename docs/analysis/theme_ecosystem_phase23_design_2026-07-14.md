# ADR 0032 Phases 2 + 3 — pure-execution design (re-granularization · ecosystem auto-discovery)

**2026-07-14 · DESIGN ONLY — no code changed, no deploy, read-only prod queries.**
Builds ON Phase 1 (deployed + verify-live 2026-07-14: `theme_ecosystems.yaml` 20-bucket taxonomy ·
`agents/market_intelligence/theme_ecosystems.py` loader/score/assignment/render · `mi_theme_ecosystems`
65 rows backfilled **[V]**). Spec sources: ADR 0032 (§B4/§B5/§D1/§Gates), the 7/14 litmus doc, ADR 0025,
`docs/setups/CHANGE_PROCESS.md`. Every load-bearing claim below is **[V]** (verified 2026-07-14 against
the working-tree code at the cited lines and/or prod `apollo-postgres`, read-only) or **[U]**
(unverified / judgment / projection). **All numeric thresholds introduced here are ILLUSTRATIVE PINS —
the §2.4 backtest sets them; none is pre-decided.** THE LINE: themes are a no-money detection surface
(briefs + shadow-judge theme-axis only); nothing here touches trade state — but granularity is a
methodology change, so CHANGE_PROCESS + operator sign-off gate every flip.

---

## §0 Verified ground truth the design stands on (read this first — several findings are NEW)

**G1 — The kill chain, mechanically [V].** Discovery births are validated at birth
(`theme_engine.py:4662`), audited as `theme_discovered` (with tickers, `:4700`), then enter
`_merge_overlapping_themes` (`:4749`) with `protected_names = {every existing theme name}` (`:4739` —
NOT just operator-protected pairs; "protected" in Pass1 means *incumbent*). Pass1 sorts by score desc
(`:3725`); for an overlapping pair (Jaccard ≥0.6 OR subset OR overlap ≥0.6, with |∩| ≥
`MIN_SHARED_FOR_MERGE=3`, `:261,3756`): if the LOWER-sorted theme `j` is protected and `i` is not →
**strip the intersection from `i`** (`:3768-3828`, audit `theme_pass1_protect_strip`). A newborn that
is a subset of one incumbent is stripped to 0 members → dropped by `_enforce_max_themes_per_stock`'s
`PRUNE_MIN_TICKERS=2` floor (`:4017-4035`, audit `theme_cap_drop`) → never reaches `_save_themes`.
That is exactly how both vuln-mgmt births died **[V prod]**:
- 7/07 `Cyber Vulnerability Management & Exposure Platforms` — intersection `[QLYS,RPD,TENB]`,
  `i_protected=False j_size=12 3->0 EMPTY_AFTER_STRIP`.
- 7/13 `Vulnerability Management & Data Security Posture` — intersection `[QLYS,RPD,TENB,VRNS]`,
  `4->0 EMPTY_AFTER_STRIP`.
Parent today: 12 members `{TENB,CRWD,CVLT,QLYS,RPD,PANW,VRNS,FTNT,BB,GRRR,OKTA,RBRK}` **[V]** — both
newborns were **containment 1.0** subsets (Jaccard only 0.25 / 0.33 — containment, not Jaccard, is the
discriminating metric).

**G2 — The trigger's blast radius is tiny [V prod].** 155 `theme_pass1_protect_strip` events across 31
nights since 4/30; **153 are BOTH_PROTECTED** (established-vs-established tiebreaker strips — e.g. the
oncology 7/10 case) and **exactly 2 have `i_protected=False`** — the two vuln-mgmt kills. A routing
keyed on *newborn-vs-incumbent* leaves the 153 established-pair strips byte-identical.

**G3 — The honest backtest population exists [V prod].** Since 6/22 (post-`482dc50` discovery fix):
**71 `theme_discovered` births, 14 never persisted an `mi_themes` row** (killed in the merge passes) —
6/22 Ophthalmic · 6/29 Rare-Metabolic · 7/02 Rare-Orphan · 7/06 Rare-Neuro · 7/07 Cardiometabolic,
**Cyber-Vuln-Mgmt**, Clinical-Autoimmune, Precision-Oncology · 7/08 CRE-Services, Autoimmune-Modulation
· 7/09 Autoimmune-Inflammatory, Oncology-Rotation, CNS-Pharma · 7/13 **Vuln-Mgmt-Data-Security**.
N=14 kills + 57 survivor controls ≥ the CHANGE_PROCESS N≥10 bar, and the mostly-biotech near-dup slices
are a rich **legit-kill** sample.

**G4 — NEW FINDING: the coexistence carve-out is one-directional — a latent child-gutting bug [V code].**
`theme_engine.py:3761-3766` only checks `j_is_subtopic_of_i` (child sorted BELOW parent). When a child
scores HIGHER than its parent (near-certain for an elite-RS sub-cohort: the vuln trio is RS 99.2-99.6),
the child is `i`, the parent is `j` → carve-out never fires → next night both are incumbents →
BOTH_PROTECTED tiebreaker strips the SMALLER (the child) → the child is gutted one night after it was
created. **This also bites the already-built ADR-0025 Arm-B PARENT_CHILD path once `THEME_MERGE_ARM`
flips ON** (Arm B sets `child["parent_theme"]` at `:4205-4219` with members retained in both themes).
It is inert TODAY only because 0 active themes carry `parent_theme` **[V litmus]**. Phase 2 must ship
the symmetric check; see §1.1-D and the sequencing note in §3.

**G5 — Pass1.5 + the per-stock cap already accommodate coexisting children [V code].** Pass1.5 skips
any theme in `sub_theme_parents` (`:3856`); `MAX_THEMES_PER_STOCK=2` is documented as "primary +
sub-theme" (`:260`); Arm-B Stage-A never pairs a parent with its child (`theme_merge_arm.py:158`).
The registration into the `sub_theme_parents` dict must happen AT ROUTING TIME (the same dict object
flows through Pass1.5 and the later diagnostics — mutation is the wiring). Orphan children
(parent dropped) are already remediated: `parent_theme` cleared in place (`:937-965`).

**G6 — D3 depth already counts PARENT_CHILD subsets correctly [V code+arithmetic].**
`compute_ecosystem_scores` dedups depth at Jaccard ≥ 0.6 (`theme_ecosystems.py:64,220-225`); a 3-4
member child inside a 12-member parent is Jaccard 0.25/0.33 → counts as a second qualifying sub-theme
(if comp ≥ 85 — the vuln trio's comp would be ~99 **[U arithmetic from V inputs]**). `raw`/`strong`
use the member UNION, so a coexisting subset child changes neither. No Phase-1 formula change needed.

**G7 — Merge arm state [V prod].** `THEME_MERGE_ARM` is UNSET on the prod market container
(`docker exec apollo-market printenv THEME_MERGE_ARM` → empty, exit 1) → arm OFF; 0 `theme_merge_*`
audit events exist. The flip is still the pending operator decision (ADR 0025, corpus 14/14).

**G8 — Phase-3 substrate is nearly EMPTY today [V prod].** `mi_theme_ecosystems`: 65 rows;
`E-UNASSIGNED` holds exactly 1 theme (`Life Science Tools & Analytical Instruments`). The discovery
lane will legitimately idle until unassigned themes accumulate — verify-live for Phase 3 must key on a
heartbeat, not a promotion (§2.6).

**G9 — The YAML is baked into the image [V].** `docker/Dockerfile.market:23`
`COPY theme_ecosystems.yaml theme_ecosystems.yaml` — runtime auto-promotion CANNOT edit the file;
hence the §2.3 DB-union design. Loader is sync + module-cached (`theme_ecosystems.py:94-129`); render
entry points that must see dynamic buckets are async (`agent.py:4427-4428, 4867-4869`,
`ensure_theme_ecosystems`), which is where the async DB refresh fits.

**G10 — `/promotetheme` one-tap idiom [V].** Three-place wiring: handler `agent.py:4896`
`_handle_promotetheme` · dispatch `agent.py:5474` · `BotCommand` + slash-allowlist
`channels/telegram.py:1732-1772`. The decision-alert carries the action as literal command text in the
alert body (`theme_synthesis.py:178` `<code>/promotetheme &lt;name&gt;</code>`, HTML surface).
`channels/telegram.py` is orchestrator-owned → any new command deploys with scope `both`
(the 2026-05-28 `/partialnow` lesson).

---

# PHASE 2 — re-granularization (D2)

Two bounded routes, one correctness fix, all behind a new runtime toggle **`THEME_SUBTHEME_ARM`**
(default OFF; byte-identical off — the ADR-0025 build-dark discipline; the flip is operator-signed
after the §2.4 backtest). No new LLM surface: Route A reuses the corpus-cleared Arm-B adjudicator
verbatim; Route B reuses `_split_fat_theme` verbatim with a widened eligibility gate.

## §1.1 Route A — protect-strip → PARENT_CHILD adjudication

### Trigger (exact, at the strip site)

Insert in `_merge_overlapping_themes` Pass1, inside the `j_protected` branch (`theme_engine.py:3768`),
BEFORE the strip executes. Route the pair to adjudication iff ALL of:

| # | Condition | Rationale / source |
|---|---|---|
| T1 | `THEME_SUBTHEME_ARM` enabled | build-dark discipline |
| T2 | `not i_protected` — `i` is a THIS-RUN newborn, not an incumbent | G2: leaves all 153 established-pair strips untouched. (Split children are already in `protected_names` via `existing_names \| this_run_sub_parents` at `:4812` — they can't re-trigger.) |
| T3 | `i` is not already a child: `themes[i]["name"] not in sub_theme_parents` and `not themes[i].get("parent_theme")` | no chains (mirrors `:4767` "never split a sub-theme further") |
| T4 | **containment** `c = \|tickers_i ∩ tickers_j\| / \|tickers_i\| ≥ C_MIN` — *illustrative pin 0.8; backtest-set* | G1: both fixtures at c=1.0; Jaccard (0.25/0.33) is the wrong metric for child⊂parent |
| T5 | **sole parent**: helper `_sole_parent_of(newborn, themes, protected_names)` — argmax-containment protected incumbent `P` has `c(P) ≥ C_MIN` AND every OTHER protected incumbent has containment `≤ C_MULTI` (*illustrative 0.34*) or intersection `< MIN_SHARED_FOR_MERGE`. Members spread across two parents = not a coherent subset of ONE → fall through to today's strip | the ADR's single-parent condition, made computable; computed once per newborn and cached for the run |
| T6 | `len(tickers_i) ≥ SUBTHEME_MIN_MEMBERS` (*illustrative 3* — matches `_SPLIT_MIN_STOCKS`) | a 2-member child is depth-eligible only as an elite pair; keep the floor backtestable |
| T7 | routed adjudications this run `< ROUTE_CAP` (*illustrative 2/night*) | bounded LLM inside the merge pass; G2 says expected fire rate ≈ 2/31 nights anyway |

`j` in the fired branch must equal `P` from T5 (the pair being processed IS the sole parent);
if `j ≠ P` (newborn overlaps a second incumbent first), fall through to the normal strip for THAT pair —
the routing decision happens only on the (newborn, sole-parent) pair.

### Adjudication + verdict handling

Call the REAL, corpus-cleared adjudicator — `theme_merge_arm.adjudicate_merge_pair(parent, newborn,
client=_get_anthropic_client(), semaphore=_VALIDATION_SEMAPHORE, sectors_by_ticker=…, log_spend=True)`
(prompt v2 `v2-2026-07-12-slice-merge` [V], temp 0, scratchpad-first, 429 backoff). Parent = theme A,
newborn = theme B. Every routed call consumes ROUTE_CAP regardless of verdict.

| Verdict | Action | Why |
|---|---|---|
| `PARENT_CHILD`, `child="B"` (the newborn) | **No strip.** `themes[i]["parent_theme"] = parent_name`; `sub_theme_parents[newborn_name] = parent_name` (mutate the live dict → coexistence + Pass1.5 exemption apply for the rest of this run, G5); audit `theme_subtheme_routed` (containment, members, verdict, scratchpad ≤400 chars); `continue` the pair loop | the D2 mechanism: members coexist in parent+child (`MAX_THEMES_PER_STOCK=2` seat) |
| `PARENT_CHILD`, `child="A"` (adjudicator claims the 12-member incumbent is the child) | strip as today + audit `theme_subtheme_route_inverted` | fail-closed anomaly; an incumbent-as-child ruling on a containment-1.0 pair is a prompt failure, review weekly |
| `MERGE` | strip as today + audit `theme_subtheme_route_merge` (verdict attached) | v2 slice-rule: same driver, no distinct sub-catalyst → the newborn is a redundant slice; the strip IS the merge (members already inside the parent) |
| `DISTINCT` | strip as today + audit `theme_subtheme_route_distinct` for weekly review | fail-closed: high-containment + different-drivers is a contradiction worth human eyes, not an auto-coexist (see fork F-3) |
| `ERROR` / exception | strip as today + audit `theme_subtheme_route_error` | fail-open to current behavior; the arm must never break the run (0025 pattern) |

### Persistence chain (trace, all existing machinery [V])

Routed child → survives Pass1 (carve-out, both directions per §1.1-D) → skipped by Pass1.5 (`:3856`) →
survives sector cap (Pass 2 — child name may match a `_sector_group`; if the group is full the child is
absorbed into the group top theme — acceptable, audit-visible; NOT special-cased) → survives
`_enforce_max_themes_per_stock` (members sit in parent+child = exactly the 2-theme cap; a member also
in a 3rd theme loses its lowest-scored seat — normal) → NOT Arm-B Stage-A paired with its parent
(`theme_merge_arm.py:158`) → `_save_themes` upserts `parent_theme` (`:1358-1375`) → next run
`prior_sub_parents` reloads it from DB (`:4743-4747`) → coexistence protects it permanently.
Fat-split eligibility already excludes children (`:4767`). Orphaning on parent death: existing
remediation (`:937-965`) clears `parent_theme`, child continues standalone.

**Ecosystem inheritance (new, deterministic):** `ensure_theme_ecosystems` gains an optional
`inherit_from: dict[str, str]` (child→parent, from the snapshot's `parent_theme` fields, built at the
`run_theme_engine:4916` call site). Unmapped theme whose parent HAS a mapping → upsert the parent's
`e_code`, `method='inherit_parent'`, no Haiku call. Prevents a Haiku mismatch putting the child in a
different ecosystem than its parent (which would corrupt `depth`).

### §1.1-D — the symmetric coexistence fix (required; also protects Arm B)

`theme_engine.py:3761-3766` becomes: compute both `j_is_subtopic_of_i` AND
`i_is_subtopic_of_j = sub_theme_parents.get(themes[i]["name"]) == themes[j]["name"]`; `continue` on
either. One line of new logic; inert today (0 active parent links **[V]**); without it every coexisting
child that out-scores its parent is gutted the next night by the BOTH_PROTECTED tiebreaker (G4).
**Not toggle-gated** (it is a correctness fix to an existing carve-out, not new behavior — there is
nothing for it to change until a parent link exists), but it is listed as fork F-4 because it touches
merge behavior and because its ABSENCE constrains the merge-arm flip (§3).

## §1.2 Route B — bounded deliberate split for a sole-sub-theme ecosystem-dominant theme

### Eligibility (evaluated at Step 4b, `theme_engine.py:4763-4768`)

Today: `len(tickers) > MAX_THEME_STOCKS(=20) and stage != Fading and not parent_theme`. Add an OR-branch:

```
dominant_eligible(t) = THEME_SUBTHEME_ARM
    AND stage not in ("Fading","Retired") AND not t.parent_theme        # existing conditions
    AND eco := eco_map.get(t.name) not in (None, "E-UNASSIGNED")        # eco_map = await get_all_theme_ecosystems()
    AND t is the ONLY active theme mapped to eco tonight                # sole-sub-theme
    AND len(t.tickers) >= SPLIT_DOM_MIN_MEMBERS                         # illustrative 10 (ADR pin)
    AND |{m in t.tickers : rs_composite(m) >= 80}| >= SPLIT_DOM_MIN_STRONG   # illustrative 8 (ADR pin)
```
`rs_composite` from the run's `stocks_by_ticker` (already in scope at `:4776`); missing RS = not strong.
The 12-name cyber blob (11 members ≥96 **[V]**) qualifies at the illustrative pins; today's >20 trigger
never fires on it.

### Mechanics + bounds

- **Reuse `_split_fat_theme` verbatim** (`:2887`): Sonnet propose-one-split with advisor escalation and
  the built-in decline path (`fat_theme_no_split` — 39 split/no-split events historically **[V]**, so
  the LLM demonstrably declines). One prompt parameterization only: the opening line "has grown too
  broad" becomes reason-aware ("is ecosystem-dominant with no sub-theme structure") — a template arg,
  not a second prompt.
- **Removal semantics kept** (`:4787` removes the sub-group from the parent — disjoint child): smallest
  diff, parent stays coherent, `depth` counts both (disjoint → Jaccard 0). The parent-remains-≥5 rule in
  the prompt bounds a 10-member split to a ≤5-member child. Fork F-5 records coexist-vs-removal.
- **Bounds:** ≤1 split/theme/night (structural: one `_split_fat_theme` call per theme in the loop);
  after a successful split the eco has 2 themes → sole-sub-theme is false → the predicate self-disarms
  for that ecosystem; global `DOM_SPLITS_PER_NIGHT` cap (*illustrative 2*); `_SPLIT_MIN_STOCKS=3` floor
  unchanged; child registered in `this_run_sub_parents` → protected through merge_2/cap_2 (`:4809-4818`).
- Audit: reuse `theme_split` + new `theme_dominant_split_eligible` (fired even when the LLM declines —
  the trigger telemetry the backtest review needs).
- Routes compose: a Route-A child created the same night makes the eco 2-themed only NEXT night
  (eco mapping is assigned post-save), so at worst one night fires both routes once — both caps hold
  independently; acceptable **[U judgment]**.

## §1.3 Sub-theme scoring / lifecycle interaction

- **`compute_ecosystem_scores`: NO change** (G6). Coexisting child ⊂ parent: `raw`/`strong` unchanged
  (union), `depth` +1 (Jaccard 0.25-0.33 < 0.6). Disjoint Route-B child: union unchanged
  (same members, re-homed), `depth` +1. A child that grows to ≥60% Jaccard with its parent is depth-
  deduped back to 1 — correct (it stopped being distinct structure). Document in the module docstring.
- **Divergence → standalone promotion (new, small):** nightly post-save check over active
  parent-linked children: `containment(child, parent) = |child ∩ parent| / |child|` on today's rows.
  If `< DIVERGE_MIN` (*illustrative 0.34*) for `DIVERGE_RUNS` (*illustrative 5*) consecutive snapshots
  (tracked via a counter column or recomputed from history — implementer's choice, recomputed is
  stateless) → clear `parent_theme`, audit `theme_subtheme_promoted_standalone`. Once cleared, the
  normal merge machinery governs again (re-absorption possible if overlap regrows — no special re-absorb
  path; deliberate).
- **Re-absorption / death:** child follows the normal lifecycle (stages, 7d recency cap, validation,
  Arm A dissolve). Parent retires → orphan remediation (existing). No new lifecycle states.
- **Render (small):** `format_ecosystem_board` — inside an ecosystem group, a theme whose
  `parent_theme` is another theme rendered in the same group nests under it (`  └ ` + the existing
  `_theme_line` at deeper indent, keeping its GLOBAL rank). Requires threading `parent_theme` into
  `_compute_scored_themes` output or the raw theme dicts already passed — verify at build; pure
  formatting, fixture-tested.

## §1.4 Backtest methodology (CHANGE_PROCESS N≥10 — sets the thresholds; nothing pre-decided)

**Probe:** `scripts/probes/_0032_regran_replay.py` — read-only DB + offline Haiku (the
`_274_merge_replay.py` pattern; imports the LIVE `adjudicate_merge_pair`, one copy, no drift —
satisfies the rigor-before-paid-eval rule: it exercises the exact production mechanism and prompt).

**Part 1 — Route A (routing + adjudication):**
1. **Sample [V, N=14+57]:** all `theme_discovered` events since 2026-06-22; tickers parsed from event
   detail; kills = names with zero `mi_themes` rows (the G3 fourteen), survivors = control.
2. For each kill: load that night's active `mi_themes` snapshot; compute containment vs every
   incumbent; classify {sole-parent, multi-parent, low-overlap} across a grid
   `C_MIN ∈ {0.6, 0.7, 0.8, 0.9, 1.0}` × `C_MULTI ∈ {0.25, 0.34, 0.5}`.
3. For every sole-parent case (any grid cell): run the REAL adjudicator on
   (incumbent-as-of-that-night, newborn) → verdict + scratchpad. (~≤30 Haiku calls, trivial cost.)
4. **Output = the sign-off table** (date · newborn+members · parent · containment · verdict ·
   1-line scratchpad · forward 5d/10d RS drift of the killed cohort vs the parent's, as ADVISORY
   context only). **The OPERATOR labels each row should-survive vs legit-kill** — CHANGE_PROCESS
   rule 3: the agent must not classify the filter list.
5. Deterministic safety sweeps: (a) all 155 historical strips re-checked — the trigger must fire on 0
   of the 153 BOTH_PROTECTED events (expected by construction, proven by replay); (b) the 57 survivors
   must be untouched (they were never strip victims).

**Pre-registered accept/reject (written before the probe runs):**
- **A1 (fixture):** both vuln-mgmt cases route AND the real adjudicator returns PARENT_CHILD/child=B.
- **A2 (legit-kill check):** ZERO operator-labeled legit-kills get PARENT_CHILD. A violation → iterate
  the adjudicator PROMPT via the ADR-0025 corpus process (add the failure as a negative exemplar,
  re-run `run_theme_merge_corpus_eval.py`, regenerate the pass record) — never fix it by moving C_MIN.
- **A3 (threshold selection):** choose the HIGHEST `C_MIN` (and tightest `C_MULTI`) that admits every
  operator-labeled should-survive. Expected: C_MIN=1.0 admits the fixtures; whether anything below 1.0
  should be admitted is exactly what the table decides.
- **A4 (rate):** projected fires ≤2/night over the historical series at the chosen cell (sets ROUTE_CAP).
- Reject (do not flip) if no grid cell satisfies A1-A3 after one prompt iteration → back to the operator
  with the table.

**Part 2 — Route B trigger grid:**
1. **Sample:** every (snapshot day, active theme) for the last ~25-30 trading days (~65/day → N≫10).
   Inputs: `mi_themes` + `mi_stock_scores` as of each day. **Labeled caveat [U]:** the eco mapping is
   as-of-7/14 applied retroactively (themes are name-keyed; drift is small but nonzero).
2. For each `(S, K) ∈ {8,10,12} × {6,8,10}`: fires/night + the would-split list (theme · day-range ·
   member/strong counts).
3. **Accept:** the cyber blob qualifies across the window its strong-count supports (expected: July);
   total fires ≤2/night; the would-split list contains NO union-mid-pack sole theme the operator flags
   as wrong. The operator signs ONE cell → those become `SPLIT_DOM_MIN_MEMBERS/STRONG`. Downstream
   quality remains double-gated regardless (Sonnet may decline the split; birth validation prunes bad
   children) — the trigger only nominates.

**Evidence archived** with the probe output under `docs/analysis/` (this file's change-log companion);
the signed tables ARE the CHANGE_PROCESS evidence fields.

## §1.5 Acceptance fixture (three levels)

1. **CI (mocked verdict)** — `tests/test_theme_subtheme_routing.py`: replay
   `_merge_overlapping_themes` with the EXACT 7/07 inputs (parent = the verified 12-member set as of
   7/07, protected; newborn = TENB/RPD/QLYS, higher score) + adjudicator mocked to
   PARENT_CHILD/child=B. Assert: no strip; child in output with
   `parent_theme='Network Security & Zero-Trust Edge'`; `sub_theme_parents` updated; Pass1.5 leaves it;
   cap keeps it; a second synthetic run (both incumbents, child scored HIGHER) survives via the
   symmetric carve-out (§1.1-D regression pin). Same for 7/13 (+VRNS). Plus the toggle-off pin:
   arm OFF → byte-identical strip with `EMPTY_AFTER_STRIP` (the 0025 discipline).
2. **Sign-off artifact (real adjudicator)** — the §1.4 probe rows for 7/07 + 7/13 MUST come back
   PARENT_CHILD (accept-criterion A1). Not run in this design session (no paid calls) — it is the flip
   gate, not a design input.
3. **Verify-live (post-flip)** — first production `theme_subtheme_routed` event with a persisted child
   row AND the next `/themes` showing the nested child under E-CYBR. Until then the task stays
   `in_progress` (done = VERIFIED-LIVE).

## §1.6 SSoT + CHANGE_PROCESS + tests + DoD

- **SSoT:** ADR 0032 is the theme-granularity SSoT (the ADR-0025 precedent §4.3) — it gains a
  **Change log** section with CHANGE_PROCESS-shaped entries. CLAUDE.md Theme Engine section: +2 lines
  at the FLIP commit (routing rule + dominant-split trigger). Same-commit rule applies to both.
- **Change-log entry shape** (written at build, Status updated at flip):
  Trigger = the A3 smoking gun (7/07+7/13 protect-strip kills, `mi_audit_log`-verified) ·
  Evidence = §1.4 signed tables (N=14 kill population, 155-event blast-radius sweep, (S,K) grid) ·
  Anticipated effect = "coherent-subset newborns route to adjudication instead of dying; ≤2 routed
  adjudications/night; expect E-CYBR depth 1→2-3 within days of the first routed child; 153/155
  historical strip shapes unchanged" · Reversion-flag: Route A **NEW** · Route B **REFINEMENT** of the
  existing >20 `MAX_THEME_STOCKS` trigger (widened eligibility, mechanics untouched) · §1.1-D
  **NEW** (bug-class fix, no prior decision reversed) · Status per CHANGE_PROCESS.
- **Tests** (beyond §1.5): sole-parent helper (multi-parent → no route; low containment → no route);
  ROUTE_CAP honored; MERGE/DISTINCT/ERROR fail-closed to strip; inverted-child anomaly; e_code
  inheritance (`inherit_parent`); divergence promotion (5-run predicate); render nesting; toggle-off
  pins across all new branches; existing theme tests unchanged.
- **DoD (Phase 2):** built dark, suite green, toggle-off byte-identical (pinned) → §1.4 probe run →
  operator signs {labels table, C_MIN/C_MULTI/ROUTE_CAP, (S,K), forks F-1…F-6} → flip
  `THEME_SUBTHEME_ARM` on prod market container → §1.5-3 verify-live → data-gated review
  `theme_regranularization_effect` (predicate: ≥2 active `parent_theme` children AND depth(E-CYBR) ≥ 2,
  earliest 14d post-flip; overdue-unmet → operator fork: prompt iteration vs threshold revisit vs revert).

---

# PHASE 3 — new-ecosystem auto-discovery lane (D1)

Weekly pass over the E-UNASSIGNED substrate → deterministic pre-cluster → one LLM proposal →
two-sighting sustain rule → **auto-promote with 48h grace + one-tap veto** (operator-signed default-on)
→ DB-backed taxonomy extension (G9). No toggle needed beyond the state machine itself (no-money,
default-to-ship posture per the ADR) — but nothing goes live without the veto surface verified (ADR
Phase-3 gate).

## §2.1 Discovery clustering (recommendation: deterministic pre-cluster + single LLM proposal)

**Weekly job** `_ecosystem_discovery_job` — Sunday 09:30 ET (`CronTrigger(day_of_week="sun", hour=9,
minute=30, tz=ET)`, after the 08:00/08:45 Sunday jobs [V scheduler]; alert lands Sunday morning PT;
48h grace ⇒ Tuesday 09:30 ET promotion — spans the Mon + Tue 9:00 briefs, the ADR's "2 briefs").

1. **Substrate:** `get_active_themes()` ∩ mapping rows with `e_code='E-UNASSIGNED'`
   (+ themes with NO mapping row, defensive). `< 3` themes → audit heartbeat
   `ecosystem_discovery_ran (substrate_n=…)` and exit (G8: this is the common case initially).
2. **Deterministic pre-cluster (pure function, unit-testable):** graph over the substrate — edge iff
   (≥1 shared ticker) OR (shared name-token, len ≥5, not in a small stopword list). Connected
   components of size ≥3 = candidate clusters. Nothing smaller reaches the LLM. (Mirror of the 0025
   Stage-A-proposes / Stage-B-decides split.)
3. **Sustain gate (deterministic):** cluster age = earliest `mi_theme_ecosystems.assigned_at` among
   members ≥ **14d** — the ADR's "sustained ≥2 weeks", plus the §2.2 two-sighting rule.
4. **LLM proposal:** ONE Sonnet call per candidate cluster (≤2 clusters/run cap; `SYNTHESIS_MODEL`
   precedent for cross-sector narrative [V llm_models.py]); forced tool `propose_ecosystem`,
   `analysis_scratchpad` REQUIRED FIRST (house discipline). Input: the cluster's themes
   (name/description/members+sectors/age) + the FULL effective taxonomy (names + descriptions).
   Output fields: `analysis_scratchpad` · `decision ∈ {propose, abstain, fits_existing}` ·
   `e_code` (regex `^E-[A-Z0-9]{2,8}$`, collision-checked vs effective taxonomy) · `name` ·
   `description` · `keyword_stems[]` (≥3) · `exemplars[]` (⊆ union members) · `member_themes[]`
   (⊆ cluster, ≥3) · `evidence` (why ONE narrative). `fits_existing` carries the existing e_code →
   remap those themes there directly (method `discovery_reassign`, audited) — the escape valve for
   themes Haiku under-assigned at birth. `abstain` → heartbeat only.

## §2.2 Grace state machine

**Table `mi_ecosystem_proposals`:** `id SERIAL PK · e_code · name · description · keyword_stems TEXT[]
· exemplars TEXT[] · member_themes TEXT[] · evidence TEXT · status TEXT · first_sighted_at ·
pending_at · grace_ends_at · decided_at · cooldown_until · veto_snapshot JSONB · created_at`.

| From → To | Trigger | Effects |
|---|---|---|
| (none) → `sighted` | weekly pass: qualifying cluster, no matching row | INSERT; audit `ecosystem_cluster_sighted`; NO operator alert |
| `sighted` → `pending` | weekly pass ≥7d later re-proposes a cluster with ≥50% member-theme overlap (and age ≥14d) | `pending_at=now`, `grace_ends_at=now+48h`; **veto alert** (§2.4); audit `ecosystem_proposed_pending` |
| `pending` → `live` | grace sweep: `now ≥ grace_ends_at`, no veto | insert `mi_theme_ecosystems_dynamic` row (source `auto`, `proposal_id`); remap `member_themes` in `mi_theme_ecosystems` → new e_code (`method='ecosystem_discovery'`); `refresh_dynamic_taxonomy()`; Telegram confirm; audit `ecosystem_auto_promoted` |
| `pending` → `vetoed` | `/vetoecosystem` during grace | `cooldown_until=now+30d`; `veto_snapshot={member_theme_count, union_strong_count}`; ack; audit `ecosystem_vetoed` |
| `vetoed` (in cooldown) → skip | weekly pass matches a vetoed cluster (≥50% overlap or same e_code) | audit `ecosystem_cooldown_skip` — UNLESS **materially strengthens**: member themes ≥ snapshot+2 OR union RS80+ ≥ 2× snapshot → straight to `pending` (marked "re-surfaced early"; audit `ecosystem_resurfaced_early`) |
| `sighted` → `expired` | no re-sighting for 28d (weekly hygiene) | audit only |
| `live` → retired | §2.5 retro-retire | dynamic row soft-deleted; themes remapped → E-UNASSIGNED |

**Timing jobs:** grace sweep = hourly (`CronTrigger(minute=12)`, cheap indexed SELECT) + one sweep at
boot (downtime catch-up); idempotent via the status guard (`UPDATE … WHERE status='pending' AND
grace_ends_at <= now()` claims the row before side effects — double-run-safe). Weekly pass as §2.1.

## §2.3 ⚠ The taxonomy-mutation path — DB-backed extension (solves G9 concretely)

**DDL (db.py `CREATE TABLE IF NOT EXISTS`, alongside `mi_theme_ecosystems` at `db.py:1261`):**

```sql
CREATE TABLE IF NOT EXISTS mi_theme_ecosystems_dynamic (
    e_code        TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    description   TEXT,
    keyword_stems TEXT[] NOT NULL DEFAULT '{}',
    exemplars     TEXT[] NOT NULL DEFAULT '{}',
    source        TEXT NOT NULL DEFAULT 'auto',    -- 'auto' | 'operator'
    status        TEXT NOT NULL DEFAULT 'active',  -- 'active' | 'retired'
    proposal_id   INT,                             -- lineage → mi_ecosystem_proposals
    created_at    TIMESTAMPTZ DEFAULT now(),
    retired_at    TIMESTAMPTZ
);
```

**Effective taxonomy = YAML base ∪ active dynamic rows, YAML wins on e_code collision.**

**Loader change (`theme_ecosystems.py`) — the sync/async boundary solved:** the Phase-1 loader is sync
+ module-cached; DB access is async. Add a module-level `_DYNAMIC_CACHE: list[dict] | None` and
`async def refresh_dynamic_taxonomy() -> int` — fetches active dynamic rows, normalizes to taxonomy
entries (`{e_code, name, description, keyword_stems, exemplars, dynamic: True, created_at}`), sets the
cache; on ANY DB error keeps the previous cache (or `[]`), logs, never raises (Phase-1 fail-safe
contract). `get_ecosystems()` stays SYNC and returns
`yaml_entries + [d for d in (_DYNAMIC_CACHE or []) if d["e_code"] not in yaml_codes]`.
**Refresh call sites (all already async [V]):** `ensure_theme_ecosystems` entry (nightly) · the two
`/themes` handlers before `format_ecosystem_board` (`agent.py:4427, 4867`) · the weekly discovery job ·
the grace sweep after a promote · market-agent boot. Staleness bound: one render/run, degrade =
YAML-only — `/themes` never breaks. Note: dynamic entries append AFTER `E-UNASSIGNED` in
`get_ecosystem_codes()` order — harmless: order is only the display TIEBREAK and `E-UNASSIGNED` is
pinned last by the render sort key, not by list order [V `_sort_key`].

**Downstream for free:** the Haiku assignment prompt and `keyword_fallback_ecosystem` both iterate
`get_ecosystems()` [V] → new births map into dynamic buckets with zero further changes.

**Audited + reversible:** every INSERT/retire writes `mi_audit_log`; retire = soft
(`status='retired', retired_at`) + remap that bucket's `mi_theme_ecosystems` rows → `E-UNASSIGNED`
(method `ecosystem_retired`); rows never deleted (lineage). **Graduation path:** a proven auto bucket
can later be added to the YAML at any deploy — YAML-wins dedup means the DB row can then be retired
with no window where the bucket vanishes. Operator manual adds: INSERT with `source='operator'`
(documented in the ADR change log), YAML remains the primary curated path.

## §2.4 The veto surface (mirrors `/promotetheme`, G10 — three places, one commit, scope `both`)

1. **Handler** `agent.py::_handle_vetoecosystem(request)` — arg parsing:
   - `/vetoecosystem E-XXXX` → if a `pending` proposal matches → veto transition; elif a LIVE
     `source='auto'` dynamic bucket matches → **retro-retire** (§2.5) with the same 30d cooldown;
     else error + list of pending/dynamic codes.
   - bare `/vetoecosystem` → exactly ONE `pending` → veto it (**the true one-tap**: Telegram renders a
     bare leading `/command` tappable); zero pending → usage + the live dynamic list; >1 → list codes.
   - YAML-defined buckets are NEVER vetoable (operator edits the YAML) — explicit error.
2. **Dispatch** — `"/vetoecosystem": self._handle_vetoecosystem` in the agent.py command dict (~`:5474`).
3. **Bot registration** — `BotCommand("vetoecosystem", "veto/retire an auto-promoted ecosystem")` in
   `channels/telegram.py::_register_commands` + the slash allowlist (~`:1732`).
   **Deploy scope `both`** (channels/ is orchestrator-owned — the `/partialnow` lesson).

**Alert (HTML, `theme_synthesis.py:168-181` idiom, esc()'d):**
```
🆕 <b>New ecosystem auto-promoting in 48h</b>: E-DRONE — Drones & UAS
Themes: <i>A · B · C</i> (N names, K RS80+; sustained ≥2wk, 2 sightings)
<i>{evidence, 1-2 lines}</i>
▶ Veto: <code>/vetoecosystem E-DRONE</code>  (bare /vetoecosystem works — one pending)
No action → live Tue 09:30 ET. 30d cooldown on veto.
```

## §2.5 Marking · retro-retire · audits · tests · DoD

- **Marking:** `format_ecosystem_board` prefixes `🆕 ` on a dynamic bucket's header while
  `created_at` ≤ 14d (the entry carries `dynamic`/`created_at` from the loader). The 🆕 window IS the
  ADR's "listed for a window" retro-retire affordance; after 14d the bucket renders like any other
  (still retirable via `/vetoecosystem <code>` at any time — dynamic buckets only).
- **Retro-retire:** as §2.3 (soft-delete + remap to E-UNASSIGNED + `refresh_dynamic_taxonomy()` +
  30d cooldown vs re-proposal of the matching cluster + audit `ecosystem_retired` + Telegram ack).
- **Audit events (all new, one vocabulary):** `ecosystem_discovery_ran` (EVERY weekly run — the
  heartbeat; substrate_n + clusters + outcome) · `ecosystem_cluster_sighted` ·
  `ecosystem_proposed_pending` · `ecosystem_auto_promoted` · `ecosystem_vetoed` ·
  `ecosystem_cooldown_skip` · `ecosystem_resurfaced_early` · `ecosystem_retired` ·
  `ecosystem_promotion_error` (fail-loud on sweep/promote exceptions).
- **Tests:** loader union + YAML-wins + DB-down fail-safe + cache refresh; every state transition incl.
  sweep idempotence (double sweep ≠ double promote) and the early-resurface predicate; e_code collision
  guard; remap-on-promote and remap-on-retire; handler branches (pending veto / live retire / bare
  one-tap / YAML refusal); **synthetic e2e acceptance:** seed 3 fake E-UNASSIGNED themes (overlapping
  tickers, `assigned_at` backdated 15d) → weekly pass #1 → `sighted` → pass #2 (+7d) → `pending` +
  alert content pinned → (a) sweep at +48h → `live`, dynamic row exists, mappings remapped, board
  renders `🆕 E-TEST` · (b) veto branch → `vetoed`, cooldown, next pass skips, strengthened cluster
  re-surfaces. All LLM calls mocked in CI.
- **Verify-live (event-gated, per BURNDOWN rule 4):** first prod `ecosystem_discovery_ran` heartbeat
  (next Sunday) + one hourly-sweep audit + `/vetoecosystem` visible in the Telegram menu. A real
  promotion is event-gated on the substrate filling (G8) — the task closes on the heartbeat + CI e2e,
  with a data-gated review `ecosystem_discovery_first_promotion` to verify the full path on the first
  real pending proposal (never seeded synthetically in prod).
- **DoD (Phase 3):** wiring verified-live as above; loader fail-safe proven; ADR 0032 change-log entry
  + CLAUDE.md 2 lines (same commit); the §2.2 defaults (48h / 30d / ≥3 / 2-sighting / caps) recorded as
  operator-tunable constants at the top of the new module (`ecosystem_discovery.py`).

---

# §3 Sequencing + dependencies (explicit)

1. **`THEME_MERGE_ARM` flip (ADR 0025 / ADR 0032 D4) — FIRST.** Already corpus-cleared 14/14; arm OFF
   in prod today (G7). Phase 2's `depth()` is only trustworthy post-flip (the 40% 2-member noise
   inflates nothing structurally, but the nested board and the `theme_fragmentation_resolution` review
   predicate — count ≤55, 2-member ≤30% — are the precondition for reading depth as signal, ADR 0032
   D4). Phase 3 depends on it for substrate cleanliness (unmerged noise otherwise accumulates in
   E-UNASSIGNED and can cluster into fake ecosystems). **⚠ Sequencing catch (from G4): the flip
   enables Arm-B PARENT_CHILD verdicts, whose children the one-directional carve-out can gut the next
   night. Recommendation: land §1.1-D (the symmetric one-liner) WITH or BEFORE the flip commit** —
   it is inert until a parent link exists, so it cannot change the corpus-cleared behavior.
2. **Phase 2:** build dark (one market-agent deploy) → §1.4 probe (same day, read-only + ~30 Haiku) →
   operator sign-off sitting (the labels table + thresholds + forks) → flip `THEME_SUBTHEME_ARM` →
   verify-live → 14d gated review. The flip should trail the merge-arm flip by ≥a few nights so the
   board Phase 2 modifies is the post-merge one.
3. **Phase 3:** technically independent of Phase 2 (it consumes Phase 1's mapping + the merge arm's
   noise reduction; it does not touch parent_theme). Build may proceed in parallel; **ship after the
   Phase-2 flip** and ≥1wk after the merge-arm flip so the substrate reflects the merged board.
   Deploy scope `both` (the veto command).

---

# §4 Operator sign-off asks (consolidated — each: the fork + a 1-line rec)

**Phase 2**
- **F-1 Route-A thresholds** (`C_MIN`, `C_MULTI`, `SUBTHEME_MIN_MEMBERS`, `ROUTE_CAP`): set by the
  §1.4 Part-1 table — **rec: sign the highest-C_MIN cell satisfying A1-A4** (illustrative 0.8/0.34/3/2).
- **F-2 The kill-population labels** (should-survive vs legit-kill, 14 rows): **operator labels the
  printed table** (CHANGE_PROCESS rule 3) — rec: expect the 2 cyber rows survive-as-child, most biotech
  slices legit-kill, but that is the review, not a pre-decision.
- **F-3 DISTINCT-verdict handling at the strip site:** strip-as-today (fail-closed, rec) vs allow
  coexistence without a parent link — **rec: fail-closed + weekly audit review**; revisit only if the
  audit shows real losses.
- **F-4 The symmetric coexistence fix (§1.1-D):** ship un-toggled with/before the merge-arm flip
  (rec — inert today, protects Arm-B children) vs gate under `THEME_SUBTHEME_ARM` — **rec: with the flip**.
- **F-5 Route-B split semantics:** keep removal (child split OUT, disjoint — rec: smallest diff,
  proven mechanics) vs coexist-in-both (Marios-parity unknown, [U]) — **rec: removal**; Route-A
  children coexist by construction (that asymmetry is deliberate and documented).
- **F-6 Route-B thresholds** (`SPLIT_DOM_MIN_MEMBERS`, `SPLIT_DOM_MIN_STRONG`, `DOM_SPLITS_PER_NIGHT`):
  **rec: sign one cell of the §1.4 Part-2 grid** (illustrative 10/8/2 — the ADR pins).
- **F-7 Divergence-promotion constants** (`DIVERGE_MIN=0.34`, `DIVERGE_RUNS=5`): low-stakes lifecycle
  hygiene — **rec: accept illustrative pins, revisit on evidence** (no backtest sample exists yet;
  flagged single-case-tune-class).

**Phase 3**
- **F-8 Clustering algorithm:** deterministic pre-cluster + single Sonnet proposal (rec) vs pure-LLM
  over the whole substrate vs embeddings — **rec: pre-cluster + Sonnet** (bounded cost, testable,
  mirrors the 0025 Stage-A/B split).
- **F-9 The sustain rule:** two-sighting (≥7d apart) AND cluster age ≥14d (rec) vs single-sighting +
  age-only — **rec: two-sighting** (robust to one-off LLM enthusiasm).
- **F-10 The DB-taxonomy design (§2.3):** YAML ∪ dynamic table, YAML-wins, soft-delete, sync-loader +
  async-refresh — **rec: as designed** (the only alternative — rebuilding the image per promotion —
  contradicts auto-promote).
- **F-11 Veto surface shape:** one command `/vetoecosystem` covering grace-veto AND retro-retire, bare
  no-arg one-tap — **rec: as designed** (one command, two phases; YAML buckets never vetoable).
- **F-12 Grace/cooldown defaults:** 48h / 30d (ADR defaults) + hourly sweep + Sunday 09:30 ET —
  **rec: accept** (48h from Sunday spans the Mon+Tue briefs as the ADR intends).

**Sequencing**
- **F-13 `THEME_MERGE_ARM` flip** — already the pending ADR-0025 operator decision; restated because
  Phases 2/3 sequence behind it, and §1.1-D should ride it (F-4).

---

# §5 Unverified / explicitly labeled

- Marios's UI numbers and whether his sub-themes COEXIST with a broad ecosystem theme (informs F-5) —
  operator-provided / unknown **[U]**.
- The should-survive/legit-kill labels for the 14 kills — deliberately NOT pre-decided (F-2).
- The real adjudicator's verdict on the fixture pairs — NOT run in this session (no paid calls);
  it is accept-criterion A1, a flip gate.
- Part-2 replay applies the 7/14 eco mapping retroactively — approximation, labeled in §1.4.
- Projected depth/boost changes (E-CYBR 1→2-3) and fire-rates — arithmetic from verified inputs,
  no code executed **[U]**.
- `theme_discovered` name extraction regex (`^New theme: (.*) \(\d+ stocks\)$`) — validated visually
  against the 14 rows only.
- All Phase-1 code/line citations, prod counts (155/153/2 strips · 71/14 births · 65/1 mapping rows ·
  merge-arm env unset · Dockerfile COPY · `/promotetheme` wiring) — **[V]** 2026-07-14.
