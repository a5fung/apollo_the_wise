# Meta-Rubric Axes — Theme · Structure · Gap-Alignment

**Status**: SHADOW ONLY — no axis here has flipped to load-bearing. The live judge continues
to reason about theme/structure/gap-alignment qualitatively (`docs/setups/catalyst_rubric.md`'s
6-axis fundamentals rubric + the holistic judge's rubric clause 4). This file is the SSoT hub
`#329` named as the target once `#330`/`#331` land ("SSoT target ... NEW docs/setups/meta_rubric.md
+ own SSoT per signal").

**Origin**: `PLAN.md #329` (composition), a Path-A decision (ADR 0024 §F1): the judge owns the
catalyst verdict; each axis below owns a CALIBRATED, traceable CONTEXT credit shadowed beside it.
Flip to load-bearing = `#335` (CHANGE_PROCESS + operator sign-off + the ONE batched re-grade —
never a per-axis spend, per the operator's 6/18 cost directive).

**Architecture + dependency graph (decision record, 2026-09-05)**: `docs/decisions/0035-meta-rubric-architecture.md` — what the rubric is in plain words, where it sits, the stage-by-stage path, the three portfolio uses, and the ANTI-BLOCK table (zero-authority work is never gated on a load-bearing flip; every cluster task re-checked, #299 found still chained to #335 after his 08-03 unchain ruling). Its §7 forks are the operator's.

## The 3 sibling axes (#329 child cards)

| # | Axis | ADR | Table | Status |
|---|---|---|---|---|
| #328 | Theme | `docs/decisions/0015-theme-axis-meta-rubric.md` | `mi_theme_axis_shadow` | shadow, accruing |
| #330 | **Structure** | `docs/decisions/0016-structure-axis-meta-rubric.md` | `mi_structure_axis_shadow` | shadow, accruing (this doc) |
| #331 | Gap-alignment | ADR 0033 (designed 2026-07-18) | — | STEP-0 backfill + operator sign of the table pending |

All three share the same mechanics (ADR 0016 inherits ADR 0015's verbatim): a pure
`<axis>_credit(features) -> {credit_steps, marker, reason}` function, **boost-only** (never
returns `credit_steps < 0` — the shared 6/5 evidence that a naive theme-GATE was refuted:
themeless names were 88% of HIGHs, avg +5.73%, held the +137% winner — re-penalizing
post-detection risks the same false-negative class), logged SHADOW-ONLY beside the live label.
Stacking caps across axes are `#329`'s composition call (proposed default: max +1 step TOTAL).

---

## Setup-class classifier (#332, ADR 0028 C1) — companion program, NOT a 4th boost-axis

**Distinct from the 3 axes above**: the axes each contribute a *boost-only credit* to the SAME
uniform rubric; the setup-class classifier instead TAGS each candidate with one of 4 mutually-
exclusive classes so a FUTURE per-class salience profile (ADR 0028 P1/P2/P3 — not yet built)
can eventually re-weight WHICH axes/evidence carry the composite for that class. **P0 (shipped
2026-07-18) is TAG VISIBILITY ONLY — zero grade mutation, no salience weights, no composite/
tier change** (THE LINE; P1 calibration + P2 shadow profiles + P3 authority are each their own
future, operator-gated flip — see ADR 0028 §§3-4).

| Status | ADR | Function | Column |
|---|---|---|---|
| **P0 shipped 2026-07-18** | `docs/decisions/0028-setup-class-conviction-profiles.md` | `agents/market_intelligence/setup_class_classifier.py::classify_setup_class` | `mi_ep_alerts.setup_class` |

### The classifier (operator-signed 2026-07-18, ADR 0028 §2 + §7 F4)

`classify_setup_class(candidate) -> 'pradeep_explosive' | 'mature_leader' | 'episodic_neglect'
| 'unclassified'`, evaluated in this literal order (first-match-wins — the documented v1
tie-break for the one possible overlap, see the module docstring):

| class | rule |
|---|---|
| `pradeep_explosive` | `mcap < $2B AND (RVOL ≥ 3× OR 9M-print same-day OR sugar-baby cohort)` |
| `mature_leader` | `mcap ≥ $10B OR (Stage-2 AND price ≥ 0.75×52w_high AND ADV_20_dollar ≥ $100M/day)` |
| `episodic_neglect` | `$2B ≤ mcap < $10B AND price < 0.70×52w_high AND upgrades_30d == 0` |
| `unclassified` | anything else / any missing field — uniform baseline, **never penalized** |

`ADV_20_dollar ≥ $100M/day` and `upgrades_30d == 0` are the two predicates ADR 0028's §7 F4
fork resolved (operator, 2026-07-18) — a prior build pass found neither had an exact threshold
or a reusable existing primitive; both are now pinned exactly as shown.

### Field provenance (reuse — search-before-build)

| Field | Source | Notes |
|---|---|---|
| `market_cap`, `rvol`, `price` | already on the candidate row `r` (`market_cap`, `rel_volume`, `current_price`) | threaded at detection, no new fetch |
| `week52_high` | FMP profile (`profile.get("52WeekHigh")`), newly threaded onto `r` | a REAL 52-week high — **distinct from `structure_axis_shadow`'s `trailing_high`** (a ~13-month `mi_daily_closes`-retention-depth high). Never conflate the two. |
| `upgrades_30d` | **REPAIRED same-day** — `collector.get_recent_upgrade_events(ticker)` (yfinance `Ticker.upgrades_downgrades`, dated events) + `count_recent_upgrades` (pure, counts `action=="up"` in the 30 calendar days ending `alert_date`) | The ORIGINAL build threaded this from `ep_detector.py`'s `get_fmp_analyst_ratings`-based count (with a cached-tick fix, `CachedGrade.upgrades_30d`/`_resolve_cached_upgrades_30d`). `docs/analysis/332_analyst_bonus_backtest_2026-07-18.md` found THAT feed structurally dead since 2026-03-14 (every candidate read `0`, so this predicate was vacuous) — REPAIRED to the source above; the cache thread-through was removed entirely (`upgrades_30d` no longer rides `r`/the catalyst cache). `_score_ep`'s own analyst bonus was separately REMOVED (not repaired) — see `docs/setups/magna53_ep.md`. |
| `stage2` | **REUSED** — `structure_axis_shadow.compute_structure_features(bars, alert_date)["stage2"]`, over `db.get_daily_bars_asof` (strictly prior to `alert_date`, no lookahead) | never reimplemented |
| `adv_20_dollar` | new `db.get_adv_20_dollar_asof(conn, ticker, alert_date, price)` | ticker-scoped, strictly-prior median-volume query; mirrors `get_adv_from_daily_closes`'s `PERCENTILE_CONT(0.5)` formula but scoped to ONE ticker (that function is a whole-market batch query — calling it per-candidate would re-scan `mi_daily_closes` for a single-ticker answer) |
| `is_9m_same_day` | new `db.get_9m_alert_same_day` — exact `(ticker, alert_date)` match on `mi_9m_ep_alerts` | same-day, not a window |
| `is_sugar_baby_cohort` | new `db.get_sugar_baby_cohort_member_asof` — AS-OF latest `cohort_date <= alert_date` on `mi_sugar_babies_cohort` | mirrors `get_theme_heat_asof`'s as-of pattern |

### Field provenance (lookahead honesty) — ADR 0028 §2

The tag is computed ONCE at detection from the fields above, then persisted on
`mi_ep_alerts.setup_class` — never re-derived from re-fetched current data. A historical row
with `setup_class IS NULL` (pre-C1, or a classify failure) reads as `unclassified` by
definition; a future P1 calibration replay never backfills it.

### Wiring — P0 visibility (THE LINE)

Computed in `ep_detector.py`'s `_judge_shadow`, in its OWN try/except, BEFORE the judge payload
is assembled (so the tag rides the SAME grading pass's `assemble_judge_inputs` payload +
`_emit_grade_decision`'s `ep_grade_decision` audit trace). **Deliberately never rendered into
`_build_judge_prompt`** — stronger than the existing axis-plumbing's "byte-identical when
absent" pattern (`theme_stage`/`tape`): byte-identical to the pre-change prompt REGARDLESS of
the tag's value, so the judge is structurally incapable of being influenced by it in P0.
Persisted via `db.update_ep_alert_setup_class` (mirrors `update_ep_alert_advisory`'s shape). A
classify failure never blocks judge grading or the axis shadows (own isolated try/except).

**Column-writer gate**: `scripts/audit_column_writes.py`'s `ALLOWED_WRITERS` allow-list is
scoped ONLY to `mi_live_trades` (Gate 5 G, the trade-state ownership gate) — `setup_class`
lives on `mi_ep_alerts`, outside that gate's scope, so no registration applies. The tag was
NOT threaded onto `mi_live_trades` in this P0 slice (ADR 0028 scopes it to "the alert row +
judge DecisionContext" only) — flagged for the operator in case per-trade class visibility is
wanted later (would need its own Gate 5 G registration).

### Tests

`tests/test_setup_class_classifier.py` (37) — every class boundary incl. the two operator-
pinned cuts, the pradeep-vs-mature_leader overlap tie-break, unclassified-fail-to-baseline,
missing-fields, a lookahead-honesty/purity pin, the `count_recent_upgrades` pure-counting
tests (window boundary, lookahead, None-vs-empty-list), and the discrimination re-verification
(a coverage-heavy mid-cap must NOT read `upgrades_30d==0`; a genuinely-uncovered one still
can). `tests/test_setup_class_db_helpers.py` (12) — the 3 as-of DB primitives + the tag
writer, SQL-shape asserted (no lookahead). Plus 3 tests in `tests/test_ep_grade_judge.py`
(payload passthrough + prompt byte-identical regardless-of-value). 52 total. (The 3
cached-tick `upgrades_30d` tests that briefly lived in `tests/test_405_catalyst_cache_filters.py`
were removed same-day along with the cache thread-through itself — see that file's `#332` note.)

---

## Theme axis (#328 credit · #329 STEP-0 measurement) — shadow, accruing

Credit table + rollout: ADR 0015 (operator-signed 2026-07-04). Measurement scaffold =
`theme_axis_shadow.py` → `mi_theme_axis_shadow` (as-of heat via `db.get_theme_heat_asof`,
no lookahead; structural ticker/keyword + company-name attribution, matched terms persisted;
co-movement check). Full STEP-0 design + independence argument:
`docs/design/329_step0_structural_attribution_2026-07-26.md`. Operational facts:

- **Attribution is STRUCTURAL, never the LLM catalyst axis** (6/24 decision — LLM-attribute +
  LLM-audit is circular). Known limitation on record (#367, 7/06): the company-name signal is
  dead against the current corpus (subject 8-Ks are self-referential); corpus fix = ADR 0019
  §2.3 (S3), not a matcher change.
- **Independent check = co-movement (tape)** — different mechanism AND different input from
  the text attributor. Its live-path columns were structurally NULL (the intraday writer runs
  before today's `mi_daily_closes` exist); the `theme_axis_co_move_refresh` scheduler job
  (17:58 ET, after the 17:00 nightly pull) recomputes them EOD, re-deriving the cohort
  STRICTLY-prior (`alert_date − 1d`) so a theme born from the day's own move can never grade
  its own co-movement.
- **Label cohort (#368 input)** = `mi_theme_relevance_cohort` — themeless-winner-INCLUSIVE
  strata (`themed` = every themed row; `themeless_winner` = themeless + settled fwd_5d ≥ +5%),
  enrolment rule `theme_axis_shadow.classify_label_stratum`, seeder
  `scripts/seed_theme_relevance_cohort.py` (idempotent; never overwrites an operator label).
  The #335 flip gate is grade-CORRECTNESS over this cohort — disagreement-rate is a health
  gauge only, never a flip gate.
- **ASYMMETRIC by decision**: boost theme-as-driver, never penalize themeless.

---

## Structure axis (#330, ADR 0016)

**Scope boundary vs #331**: #330 grades the structure the stock brought INTO the catalyst day
(long-term trend, base quality, extension state) — #331 (ADR 0033) will grade what the GAP
did to that structure (punched through resistance vs faded into congestion).

**STEP-0 calibration**: `docs/analysis/structure_axis_step0_2026-07-04.md` — backfilled the 3
components onto the #329 theme-axis cohort (N=456) and cross-tabbed vs forward EP outcomes.
Verdict: the boost direction is **NOT contradicted** at the only adequately-powered read (N=386,
relaxed/"whatever history is loaded" trailing-high) — `Stage2+tight` modestly separates on all
three metrics vs `no-Stage2` (avg fwd-5d 11.7% vs 10.0%, win≥+5% 64% vs 56%). The strict
trailing-252-session variant was coverage-starved (14%, a `mi_daily_closes` retention-depth
ceiling that improves automatically over time — no code fix needed). → proceeded to the shadow
build below.

### The 3 components (search-before-build — ALL reuse existing primitives)

| Component | Signal | Reused primitive |
|---|---|---|
| **(a) Stage-2 long-term trend** | `prior_close > 200-session SMA` AND `prior_close >= 75%` of the trailing high | `flag_detector.py`'s #356 HTF Stage-2 gate predicate (`_STAGE2_NEAR_HIGH_MIN=0.75`, `_SMA200_WINDOW=200`) — mirrored EXACTLY, not reimplemented. `parabolic_detector._sma` computes the SMA. |
| **(b) Base tightness** | RMV-15 (base contraction) vs an established "tight" cutline | `flag_detector._compute_rmv` (the SSoT tightness primitive, `lookback=15`) directly; the tight cutline reuses `anticipation.ENTRY_RMV_MAX` (30.0, #327's already-signed rmv_15d "getting tight" gate on this SAME metric) rather than inventing a new threshold. |
| **(c) Extension state** | `prior_close / 10-session SMA` | `parabolic_detector._sma`; the ratio form mirrors the 9M detector's `_MAX_EXTENSION_FROM_MA10` (1.20×) gate shape (STEP-0's own honesty-flag: the ADR's prose cited MAGNA53's extension check, but that live gate is actually a 5-day MIN-close ratio — the SMA-10 ratio specified is the 9M shape; computed as specified, flagged for the record). |

All three are computed **AS-OF strictly PRIOR to alert_date** (no lookahead) via
`db.get_daily_bars_asof(conn, ticker, alert_date, days=380)` — 380 calendar days mirrors
`flag_detector.py`'s own `_HISTORY_DAYS` budget (≈260 trading rows, enough for the 200d SMA).
`high_price`/`low_price` are required (the RMV true-range calc needs both).

### v1 credit decision (`structure_axis_shadow.structure_axis_credit`) — boost-only

Per the ADR's v1 mapping: *"Stage-2 + tight base = +1 tier-step eligibility; partial (Stage-2
only) = near-miss band; absent/unknown = 0, never negative."* Extension state (component c) is
**telemetry only in v1** — recorded on every row for traceability, but does not affect
`credit_steps` (the ADR's own STEP-0 bucket spec cuts the cross-tab on Stage-2 x tightness only).

| stage2 | rmv_tight | `credit_steps` | `marker` |
|---|---|---|---|
| `True` | `True` | **+1** | `stage2_tight` |
| `True` | `False` or `None` | 0 | `stage2_only_near_miss` |
| `False` | any | 0 | `no_stage2` |
| `None` (uncomputable) | any | 0 | `unknown` |

**Documented v1 implementation call (not silently invented)**: the ADR names the "near-miss
band" concept for Stage-2-only but — unlike theme's Nascent near-miss, which DOES carry +1 in
its own signed table — does not specify an exact credited value for structure. `stage2_only_
near_miss` is recorded with 0 credit: the STEP-0 SUPPLEMENTARY read (the only adequately-powered
variant) showed Stage2-only was NOT clearly better than no-Stage2 on win-rate (53% vs 56%) —
only `Stage2+tight` cleanly separated (64%). Flagged here for the record, not silently dropped;
a future data-sized pass at the `#329` composition checkpoint may promote it once evidence
supports it.

**Also documented**: the tight-base cutline reuses `anticipation.ENTRY_RMV_MAX` (30.0) rather
than the STEP-0 cross-tab's own cohort-median RMV cutline (~53.5) — the cohort median is a
data-derived, cohort-relative number unsuitable for a live per-ticker decision (it would drift
with cohort composition day to day); `ENTRY_RMV_MAX` is the nearest EXISTING, already-signed,
deterministic threshold on the same `rmv_15d` metric. Both are PROVISIONAL/calibratable — a
future pass can re-tune specifically for this axis if warranted.

### Shadow table — `mi_structure_axis_shadow`

One row per `(ticker, alert_date)`, upserted latest-scan-wins (the EP scan re-runs every 5 min).
Columns: `grade` (the settled `score_tier`), `prior_close`, `stage2`, `sma_200`, `trailing_high`,
`rmv_15`, `rmv_tight`, `extension_ratio`, `sma_10`, `credit_steps`, `marker`, `reason`. Every
component field is `NULL` when not computable — never a guessed value.

### Wiring

`agents/market_intelligence/structure_axis_shadow.py::log_structure_axis_shadow` is called from
`ep_detector.py`'s `_judge_shadow`, immediately after the sibling `#328` theme-axis shadow call
— same gate (`score_tier in ('HIGH', 'MODERATE')`, i.e. the FINAL settled tier, post-judge-
override), same low blast radius. **There is no separate `scheduler.py` job** for this shadow
(mirrors `theme_axis_shadow.py` exactly — neither axis has a dedicated cron entry); both ride
the existing `ep_scan` job (7:00–10:00 AM ET, every 5 min) through this call site.

**SHADOW INVARIANT** (THE LINE): reads `mi_daily_closes` (read-only) via `get_daily_bars_asof`;
writes ONLY `mi_structure_axis_shadow` + `mi_audit_log` (on failure); never mutates `r`, never
touches `score_tier`/`grade_engine_authority`, never imports anything from the live judge-prompt-
building path (`_build_judge_prompt` / `assemble_judge_inputs` / `grade_holistic`). Never raises
into the caller — every error swallows to a `structure_axis_shadow_failed` audit event.

### Flip gate

Same as `#328`/theme: grade-affecting → `CHANGE_PROCESS` + operator sign-off + N≥10 shadow
divergences with outcomes, folded into the ONE batched `#335` re-grade (`eval_judge_enrich
--regrade`) alongside every other pending axis enrichment. Never on agent authority.

### Tests

`tests/test_structure_axis_shadow.py` — `compute_structure_features` correctness (insufficient
history → all-None, Stage-2 true/false/unknown, tight vs not-tight RMV, the exact
`_compute_rmv` lookback-boundary pin), `structure_axis_credit`'s boost-only sweep, the writer's
upsert-idempotency + never-raises contract, and a `copy.deepcopy` zero-live-mutation pin (the
`r` dict handed in must be byte-identical after the shadow call).
