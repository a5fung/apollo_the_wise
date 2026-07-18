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
