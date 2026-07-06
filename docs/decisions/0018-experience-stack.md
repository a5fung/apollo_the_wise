# ADR 0018 — P1 Experience Stack: precedents, self-review, ensemble (D-2, #428)

**Status:** PROPOSED (2026-07-05, Fable design block D-2) — awaiting operator sign-off (§9).
The P1 step change: "smart at each decision" → "experienced at this craft." Three subsystems,
one dependency spine: **labels → cases → retrieval → (self-review, ensemble)**. Baseline facts:
the judge is load-bearing (ADR 0011, `JUDGE_MODEL = OPUS`); operator labels exist only as
sitting documents (no table); pgvector is installed with 1536-dim columns plumbed in
`core/memory.py` but **no embedding provider exists in the stack** — which settles retrieval v1.

Contract: pure-execution depth; open forks in §9.

---

## 1. The label store — `mi_operator_labels` (new table; the corpus everything rides on)

```
id BIGSERIAL PK · label_date DATE · subject_kind TEXT CHECK IN
('ep_grade','judge_delta','mgmt_verdict','filter_fp','theme_membership') ·
subject_ref JSONB (e.g. {"ticker":"HQ","alert_date":"2026-06-15"} — enough to join back) ·
label TEXT CHECK IN ('correct','incorrect','partial') · note TEXT (operator's words, verbatim) ·
sitting_ref TEXT (the docs/analysis sitting file) · created_at TIMESTAMPTZ
```
- **Backfill card**: transcribe the existing sittings (6/18 $0-eval 11/12, 7/4 M&A 3FP/1TP +
  judge-demotes 5/5, HQ/JBIO/Xe/AEHR/AUGO set) — ~30 rows, done once, provenance kept via
  `sitting_ref`.
- **Capture forward**: #307's weekly ritual writes THIS table at the sitting (the ritual's
  missing persistence layer — labels stop living in chat/doc prose).
- One table for ALL label kinds (mgmt-judge labels from ADR 0017 §6.3 land here too) — the
  0011 principle mechanized: the OPERATOR owns ground truth, the agent never self-certifies.

## 2. The case store — `v_judge_cases` (a VIEW, not a copy)

A precedent case = a judged alert + its outcome + its label, all of which already exist in
tables. Materializing copies would drift; a view can't:
```sql
CREATE VIEW v_judge_cases AS SELECT a.ticker, a.alert_date, a.ep_score, a.catalyst,
a.catalyst_quality, a.judge_tier, a.judge_rationale, a.gap_pct, a.pm_rvol, a.theme_name,
cx.structural_verdict AS structural_chart_verdict, o.fwd_5d_pct, o.fwd_close_pct, l.label, l.note
FROM mi_ep_alerts a LEFT JOIN <outcome source> o USING (ticker, alert_date)
LEFT JOIN <chart-axis shadow table> cx USING (ticker, alert_date)  -- REVIEW 7/5: the chart
-- verdict is NOT an mi_ep_alerts column (it lives in the #343 chart_axis shadow table);
-- the build card binds cx to that table's real name/columns, NULL until #267 matures
LEFT JOIN mi_operator_labels l ON l.subject_kind='ep_grade' AND
l.subject_ref->>'ticker'=a.ticker AND (l.subject_ref->>'alert_date')::date=a.alert_date
WHERE a.judge_tier IS NOT NULL;
```
(Exact outcome-source join = the existing EP-outcomes machinery `get_ep_outcomes` reads; the
build card binds to whichever table that function queries — no new collection.)

## 3. Retrieval v1 — attribute + full-text, NO embeddings (the deliberate call)

**Why**: zero new external providers (no embedding key exists; adding one is a real
dependency decision), deterministic and operator-auditable ("it retrieved these 3 because
same catalyst class + sector + gap bucket"), and the pillar text itself defines v1 as
rule-match. Embeddings are the **H2 upgrade behind the same interface** (§9-G1).

`retrieve_precedents(candidate: dict, k=3) -> list[Case]`:
1. **Hard filters**: `alert_date ≤ today − 5 trading days` (outcome maturity); same
   `catalyst_class` (the rubric's class vocabulary); exclude the candidate's own ticker
   within 30d (no self-retrieval).
2. **Rank**: attribute-overlap score (theme-state match +2 · sector match +1 · gap bucket
   [<10 / 10-20 / >20%] +1 · rvol bucket +1 · labeled +2 [labeled cases beat unlabeled]) then
   `ts_rank(to_tsvector(catalyst), plainto_tsquery(candidate catalyst))` as tiebreak.
   A `tsvector` expression index on `mi_ep_alerts.catalyst` makes this cheap.
3. **Temporal diversity (Gemini am.3, enforced in the query layer from v1)**: greedy-select
   K from the ranked list requiring pairwise `alert_date` separation **≥ 14 days** — three
   cases from one hot sector-week is recency bias, the opposite of experience.
4. Fail-open: any error → empty list → the payload simply omits the block.

## 4. Grade-time integration

- New payload block, ≤ ~120 tokens/case, K=3:
  `PRECEDENT 2026-05-12 CRDO — sales-accel, gap +18%, rvol 9x, same theme-state · judge S ·
  outcome +32%/5d · operator label: correct.`
- Behind runtime toggle `JUDGE_PRECEDENTS` (default off → shadow-attach: rows record
  retrieved ids in a new `mi_ep_alerts.precedent_refs JSONB` even while off, so the A/B
  cohort accrues before the prompt ever changes).
- **Grade-path change ⇒ CHANGE_PROCESS**: the toggle flips only after the §7 eval at a
  batched-regrade checkpoint + operator sign-off (same discipline as every judge input).

## 5. Self-review → rubric distillation (the journaling loop)

- **Weekly job** (Sun 18:45 ET — idle evening slot; NB the weekly review runs Sun 08:00 ET, review 7/5): the judge re-reads its month's graded
  cohort JOINED with outcomes + labels and drafts **bounded amendment proposals**:
  `mi_rubric_amendments (id, axis TEXT, target_ref TEXT [rubric section anchor], current_text
  TEXT, proposed_text TEXT, evidence JSONB [alert refs], rationale TEXT, status CHECK IN
  ('pending','approved','rejected'), created_at, decided_at)`.
- Surfaced as a weekly-digest section (≤3 proposals, ranked; consolidate-surfaces rule — a
  SECTION, not a new command). Operator approves/rejects at the sitting.
- **On approval the agent applies it to `docs/setups/catalyst_rubric.md`** in a commit that
  cites the amendment id + evidence (the rubric stays an operator-signed living document with
  a changelog — approval IS the CHANGE_PROCESS sign-off). NEVER auto-applied; rejected
  proposals persist (the judge sees its rejected history next cycle — negative experience).
- Guard: proposals may only REFINE grading criteria; anything touching entry/exit/sizing
  vocabulary is out of scope by construction (the axis enum whitelists rubric axes).

## 6. Ensemble / uncertainty judging (shadow-first)

- Scope: **HIGH-tier candidates only** (cost-bounded; ~2-6/day). Second grader:
  **`SONNET_5`** (§9-G2) — same wire contract, independent call, no shared context.
- New shadow table `mi_judge_ensemble (ticker, alert_date, primary_tier, second_tier,
  tier_delta, axis_disagreements JSONB, created_at)`. **Zero grade authority** — divergence
  is logged, never acted on, until the calibration eval passes.
- **Calibration eval** (at M1+4wks, one query + a sitting): does `tier_delta ≥ 1` predict
  operator-label disagreement / worse outcomes? If yes → the divergence flag becomes an input
  to the conviction-sizing lane (ADR 0017 §4, size-down/abstain mapping — its own sign-off).
  If no → retire the second call (kill it, don't hoard — the 6/27 rule).

## 7. Eval spine
1. **Precedent A/B**: at the next batched regrade after 4wks of shadow-attach — same labeled
   cohort graded with vs without the precedent block; promote only if grade-correctness
   (attribution, not outcome — the catalyst-correctness principle) improves.
2. **Amendment quality**: operator acceptance rate + post-amendment cohort correctness drift.
3. **Retrieval relevance**: the sitting spot-labels 5 retrievals/week ('relevant/irrelevant')
   → `mi_operator_labels (subject_kind='ep_grade', note='retrieval')` — same table.
4. **Ensemble calibration**: §6.

## 8. Build cards (execution order)
| Card | Scope | Class |
|---|---|---|
| X1 | `mi_operator_labels` + sitting backfill (~30 rows) + #307 ritual writes it | Sonnet card |
| X2 | `v_judge_cases` view + `retrieve_precedents` (filters/rank/diversity) + tsvector index + tests (golden: the HQ 6/15 case must NOT retrieve 3 same-week drone names) | Sonnet card |
| X3 | Shadow-attach (`precedent_refs` column + retrieval call in the grade path, toggle OFF) + payload renderer + tests | Sonnet card, Fable review (grade path adjacency) |
| X4 | Self-review job + `mi_rubric_amendments` + digest section + approve/reject flow | Sonnet card |
| X5 | Ensemble shadow (second call on HIGH + `mi_judge_ensemble`) + spend line | Sonnet card |
| X6 | The A/B eval harness (regrade-with/without over the labeled cohort) — feeds the toggle decision | Sonnet card |
Sequencing: X1 → X2 → {X3, X4, X5 parallel} → 4wks accrual → X6 → toggle/promote decisions.

## 9. Operator sign-off forks (recs first)
- **G1** Retrieval v1: **attribute+FTS now, embeddings as the H2 upgrade** (rec) — vs adding
  an embedding provider (Voyage/OpenAI key) immediately.
- **G2** Ensemble second grader: **Sonnet-5** (rec — capability evidence banked 7/5, intro
  pricing; an all-Anthropic ensemble measures scale-diversity, not family-diversity — noted
  honestly) vs adding an external-family model (new provider decision).
- **G3** K=3 precedents / ≥14d pairwise separation / ≤120 tokens each (rec).
- **G4** Amendment application: **agent applies on operator approval** (rec) vs operator
  applies manually.
- **G5** Label schema: the minimal 3-value label + verbatim note (rec) vs a graded scale.

## 10. Test plan
Unit: retrieval filters (maturity, self-exclusion), diversity greedy (constructed clusters),
rank determinism, amendment-axis whitelist, ensemble parse fail-open. Golden: the hot-week
case (§8-X2). Integration: X3 shadow-attach writes refs with toggle off and changes NOTHING
in the emitted grade (byte-diff a day of shadow grades before/after). Eval: X6 runs on the
frozen labeled cohort and its output format feeds the checkpoint sitting directly.
