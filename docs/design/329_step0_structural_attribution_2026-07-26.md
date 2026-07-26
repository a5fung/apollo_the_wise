# #329 STEP-0 (shadow) — structural theme-attribution + independent check + label-cohort seed (2026-07-26)

Operator-unblocked 2026-07-26 (the advisory/shadow half #329's own text exempts; the live
call-side wire-in stays #335). SHADOW ONLY — nothing here reads into any live grade, alert,
entry or exit.

## 0. Search-first finding: most of STEP-0 already existed — this card completed it

The 7/04–7/06 #367/#369 window had already built and wired parts 1 and 2's *logging*:
`agents/market_intelligence/theme_axis_shadow.py` (attribution + co-movement + writer),
`mi_theme_axis_shadow` (db.py DDL ~line 1142), wired in `ep_detector.py::_judge_shadow`
(~line 4351, final settled tier, HIGH+MODERATE). What was genuinely missing, and what this
card added:

| Piece | State found | This card |
|---|---|---|
| 1. Structural attribution logged | ✅ built + wired (ticker/keyword + company-name variants) | verified, documented — no rebuild |
| 2. Independent check logged beside it | ⚠ built (co-movement) but **structurally dark on the live path** — always NULL (see §3) | EOD refresh job that makes it actually accrue |
| 3. Themeless-winner-inclusive cohort seed | ❌ absent | `mi_theme_relevance_cohort` + enrolment rule + seeder |

## 1. The attributor (structural, deterministic — NOT the LLM catalyst axis)

Per the 6/24 decision (engine = SoT for detection; relevance attributed structurally;
LLM-attribute + LLM-audit = circular). Two sibling deterministic signals, both logged with
their matched terms for auditability:

- **STEP-0 ticker/keyword** (`compute_structural_attribution`): distinct *peer* cohort
  tickers (subject excluded — a corpus about itself must not self-attribute) OR theme
  name/description keywords (4+ letters) found word-bounded in the catalyst
  `grounded_text`. Matches tagged `ticker:XXX` (strong: peer named) vs `kw:word` (weak:
  own-vocabulary is trivially common) so a later data-sizing pass can down-weight
  keyword-only attribution.
- **STEP-1(a) company-name** (`compute_name_attribution`, the #369 fix): normalized peer
  *company names* matched as word-bounded phrases (8-Ks name peers by company name, not
  ticker). **Known #367 verdict (7/06): non-viable against the CURRENT corpus** — the
  subject's own 8-K is self-referential and names no peers (0/457). Kept logged as-built;
  the corpus fix is ADR 0019 §2.3 (theme-narrative block, the S3 card), not a matcher fix.

As-of discipline: theme existence/membership/heat comes from `db.get_theme_heat_asof`
(`mi_themes WHERE theme_date <= alert_date`, `stage != 'Retired'`, hottest-first) — never
`get_theme_membership` (today's membership = lookahead). Same accessor the
`eval_judge_enrich.py` prior art uses.

## 2. The independent check: CO-MOVEMENT (tape), and why it is mechanistically independent

Chosen check (already the #367 "surviving instrument", honored here): **same-day cohort
co-movement** — subject's open→close move vs the median of the *other* cohort members'
moves (`compute_co_movement`; co-moving = same sign AND |cohort median| ≥ 1.0%; `None`
kept distinct from `False`).

**Independence argument.** The attributor is a *lexical/structural* read of the catalyst
TEXT; co-movement is a *market/tape* read of cohort PRICES. They differ in mechanism AND in
input, so their failure modes are uncorrelated in both directions — the #367 fork proved
the text channel can be dead (self-referential corpora) on days the tape channel works, and
a thin-price-data day breaks the tape channel without touching the text one. The
alternative allowed by the decision (the judge's qualitative read) differs in mechanism
(holistic LLM vs lexical) but **shares the input** (the same `grounded_text`), so a corpus
pathology biases both together — weaker independence. The judge's read is still available
for free as a third lens: `mi_ep_alerts.fire_axes` (judge-owned since #249) joins on
`(ticker, alert_date)`; `judge_theme_gap.py` already mines it for detection gaps. Nothing
was built for it — deliberately, to keep the logged check the mechanically independent one.

**The instrumentation artifact this card fixed** (memory: shadow "0 effect" → check
instrumentation): the shadow writer rides the 7:00–10:00 AM EP scan, but `mi_daily_closes`
rows for the alert day are ingested by the **17:00 nightly pull** — so `get_daily_moves`
(alert day) was ALWAYS empty at scan time and every live row logged `co_moving = NULL`,
permanently. The #367 read's "~90% not computable" was substantially this dark instrument.
Fix: `theme_axis_shadow.refresh_co_movement_for_date` + scheduler job
`theme_axis_co_move_refresh` (17:58 ET mon-fri — after the nightly pull, same dependency
the 17:55 coverage probe rides). Writes ONLY the three co-movement columns.

**Refresh as-of rule (lookahead + circularity):** the cohort is re-derived at
`alert_date − 1 day` (strictly prior). This reproduces exactly what the 9:35 AM writer saw
(today's theme snapshot did not exist yet at scan time) and prevents a theme **born from
today's very move** (tonight's engine run may have landed by 17:58) from grading its own
co-movement — that born-today cohort would be trivially co-moving and would corrupt the
check's independence from the engine's same-day output.

## 3. The themeless-winner-INCLUSIVE label cohort (part 3 — seeded here, labeled at #368)

The axis is ASYMMETRIC (boost theme-as-driver, never penalize themeless), so correctness
has two failure sides and the label cohort must cover both:

| Stratum | Rule (`classify_label_stratum`, theme_axis_shadow.py) | Failure side it labels |
|---|---|---|
| `themed` | every themed shadow row, regardless of outcome | false-positive: credited theme wasn't the driver |
| `themeless_winner` | themeless + settled (`n_sessions_5d ≥ 5`) + `fwd_5d_pct ≥ +5%` (the established win bar — ADR 0015 / #331 tables) | false-negative: undiscovered-theme blind spot ("not seeing a theme ≠ no theme exists") |

Themeless non-winners are not auto-enrolled (review-load is the count the operator feels);
a control stratum is an operator add at #368 if wanted. Forward outcomes here *define* the
stratum — they are not a feature of any attribution signal, so no lookahead leaks into the
signals themselves.

Seeder: `scripts/seed_theme_relevance_cohort.py` (dry-run default, `--commit` to write;
idempotent; the upsert is guarded `WHERE operator_label IS NULL` so re-seeding can never
clobber an operator label). Committed runnable, run by the parent session (prod is
read-only for this build).

## 4. What is logged, where (the record downstream portfolio uses join against)

**`mi_theme_axis_shadow`** (existing; one row per `(ticker, alert_date)`, upsert
latest-scan-wins, HIGH+MODERATE): `grade`, as-of `theme_name/stage/score`,
`themeless_flag`, `structural_attribution_score/attributable/matched_terms`,
`name_attribution_score/attributable/matched_names`, and — now actually populated by the
EOD refresh — `cohort_move/ticker_move/co_moving`.

**`mi_theme_relevance_cohort`** (new; db.py boot migration): `ticker`, `alert_date`,
`stratum`, `enrol_fwd_5d_pct`, `enrol_n_sessions_5d`, `seeded_at`, plus operator fields
`operator_label` (unconstrained TEXT — labeling methodology is the operator's call, #368),
`operator_note`, `labeled_at`. Partial index on unlabeled rows for the labeling queue.
Deliberately THIN: signals/judge verdicts JOIN at read time on `(ticker, alert_date)` from
`mi_theme_axis_shadow` / `mi_ep_alerts` — no snapshot copies to go stale.

This is the explicit, traceable, auditable theme-as-driver record the operator's portfolio
uses need (allocation toward hot areas · arbitration between competing EPs · slot
expansion): each is a read over these join keys; none is built here.

## 5. Shadow contract + tests

Everything writes only `mi_theme_axis_shadow` / `mi_theme_relevance_cohort` /
`mi_audit_log`; every writer swallows errors to audit events; nothing mutates `r`, any
grade column, `mi_themes`, or trade state. The live judge call remains byte-identical
(#335 untouched).

Tests (`tests/test_theme_axis_shadow.py`, 40 passing): the strictly-prior as-of pin
(`alert_date − 1d`), refresh writes only co-movement columns, themed-only scoping,
skip-on-nonrederivable-cohort, never-raises, the 17:58 scheduler registration pin, the
stratum rule (both sides + boundaries), and the seeder's label-safety pin
(`operator_label IS NULL` + shared classifier import).

## 6. Prior decisions — implementability check

All 6/24 decisions implementable as stated, with one caveat already on record: the
**named-entity half of the structural attributor is dead against the current corpus**
(#367: subject 8-Ks are self-referential) — honored by logging it as-built beside the
viable signals rather than re-litigating; the corpus fix is the ADR 0019 §2.3 S3 card.
The "judge qualitative read" option for the independent check is implementable but
mechanistically weaker (shared input) — co-movement chosen, judge read available as a
free join (§2).
