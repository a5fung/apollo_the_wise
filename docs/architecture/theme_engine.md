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
    `lane2_grouping_v2` in mi_safeguard_state, FAIL-CLOSED OFF — see change log
    below):** when ON, the lane is state-carrying instead of re-derive-nightly.
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
    auto-merge. Seeds are outside BOTH walls by construction (not in
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

## ONE birth gate + lane retirements (consolidation Phase 1, 2026-07-27 — 3-state toggle `theme_birth_gate`, fail-closed 'off')

Behind `mi_safeguard_state` toggle `theme_birth_gate`
(`db.get/set_theme_birth_gate_mode`, **3 states — the `broker_order_ingest`
off/dry_run/live idiom**, `db.BIRTH_GATE_MODES = ("off","observe","on")`,
fail-closed 'off' on any error or unrecognized string, instant no-redeploy
transitions, OPERATOR-gated):

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
- **`on`** ⇒ the gate ACTS:

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

## Change log

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
- **Mechanics**: DB flag `lane2_grouping_v2` (`db.get/set_lane2_grouping_v2_enabled`,
  mi_safeguard_state, FAIL-CLOSED OFF, instant no-redeploy revert). Window
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
