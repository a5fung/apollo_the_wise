# M1 (#335) + HTF (#397) — adversarial readiness review for the 7/18 sitting

> **VERIFICATION (Opus, against prod+code — 2026-07-13). Both decision-threatening findings CONFIRMED:**
> - **M1: judge ALREADY authoritative** — `grade_engine_authority='judge'` on 41/42 alerts since 6/10,
>   `mi_safeguard_state` judge toggle `on`. The pack's "advisory today" premise is false. And the real
>   M1-d flip `compose_final_tier` has NO grade-path call site (only constants.py + meta_rubric_compose.py
>   + tests) → its toggle is a no-op until wired. **VERDICT: M1 is GO-CONDITIONAL, not signable 7/18 as
>   the pack frames it** — prerequisites (wire compose_final_tier · run the M1-b batched regrade · confirm
>   T2c accrual · correct the pack) are buildable this week.
> - **HTF: N unreachable by 7/18** — `mi_htf_breakout_shadow` has 6 rows, **0 settled**, only **1 takeable**
>   (5 are `stop_distance_gt_8pct`); the `htf_breakout_paper_graduation` gate is threshold=10,
>   `earliest_review_date=2026-07-20` (AFTER the sitting). **VERDICT: DEFER (not NO-GO) — re-date ~8/07;**
>   pre-agree the GO bar on the TAKEABLE cohort (the predicate counts the stop>8% rejects).
> Fable's calls (M1 GO-conditional · HTF DEFER) stand as-verified.

**Fable, 2026-07-13 (Mon).** Method: every precondition the M1 sitting pack
(`m1_sitting_pack_2026-07-18.md`) claims was re-verified against code (origin/main, HEAD
`1c99745`) and prod (read-only psql + in-container grep, 7/13 ~12:40 ET). The pack is my own
prior output — this review deliberately stress-tests it rather than re-asserting it. Nothing
here changes code or strategy; every flip below is the operator's (THE LINE).

---

# Decision 1 — #335 / M1: the authority flip

## 1a. Precondition checklist (verified, not asserted)

| # | Precondition | Status | Evidence |
|---|---|---|---|
| 1 | 0030-C3 robustness map | **MET** | `scripts/evals/judge_eval_pass_record.json`: 36/36, overall 1.0, positive_control_rate 1.0, hard_failures [], pass true, corpus_sha1 `04150fdd3a5e`, run 2026-07-12. Per the pre-agreed interpretation contract, nothing blocks from the robustness side. Recorded caveat stands: corpus-v1 misdirections are *legible* (stated tells); v2 hardening lane filed. |
| 2 | [5m/7] regression gate live | **MET** | `scripts/deploy.sh:383` runs `scripts/preflight_judge_eval_gate.py` on every market-agent-scope deploy, hard-fail (operator F3, 7/12 sitting). Gate ast-recomputes the rubric hash from `_RUBRIC` text + checks prompt version, JUDGE_MODEL, corpus sha1 vs the pass record — accidental edits trip it. It survived the 7/13 #416 deploy (deploy green ⇒ gate exercised). |
| 3 | T2c drift band deployed + accruing | **DEPLOYED, NOT YET ACCRUING → QUERY AT SITTING** | Code IS in the prod image (`docker exec apollo-market grep judge_high_rate_daily …system_audit.py` → 2 hits; MetricSpecs at `system_audit.py:470/479`, cold-start ceilings 0.85/0.90 at :73-74). But prod `mi_audit_log` has **ZERO** `metric_sample` rows for either judge metric as of 7/13 12:40 ET — first sample lands at today's 16:15 ET post-EOD audit. By 7/18: n≈4-5 < 7 ⇒ **cold-start ceilings are the only tripwire**; the trimmed band starts n≥14 ≈ 7/29. At the sitting run: `SELECT summary,count(*) FROM mi_audit_log WHERE event_type='metric_sample' AND summary LIKE 'judge%' GROUP BY 1;` — expect ≥4 per metric. |
| 4 | theme_axis_gating review | **SCHEDULED AT SITTING (by design)** | `data_gated_reviews.yaml:4839` — deferred INTO the 7/18 sitting (operator 7/11, deferred_until 2026-07-18). Its evidence inputs: the amendment draft §3 STEP-0 table (N=386 relaxed-history) + the M1-b delta table (**not run — see 1b-F2**) + #368 labeling/weighting (ETA 7/18, gated on #367) + #448 crosstab (ETA 7/16). If #368/#448 slip, the ruling rests on STEP-0 alone — thinner than the pack implies. Rec unchanged: input-only at M1. |
| 5 | Grade-era versioning | **MET** | RUBRIC_VERSION v3 + hash `eef69fa4` stamped per decision (`update_ep_alert_judge_result`, rubric_version arg, `db.py:2657-2660`); the pass record pins the same era. |
| 6 | Fail-open preserved | **MET** | `_resolve_grade_authority` (`ep_detector.py:329-340`): None verdict → floor tier, authority 'fallback', counted. Judge-write failure → reverts to floor in memory + `judge_write_failed` audit (`ep_detector.py:3205-3218`). Toggle read fail-closed to floor (`db.py:2666-2680`). |
| 7 | **M1-b batched regrade** — a NON-NEGOTIABLE gate the pack **omits** | **NOT-MET (not run)** | The amendment draft §5 lists it verbatim as a non-negotiable gate ("the M1-b batched-regrade verdict-delta table (ONE paid run) + operator labels"); ADR 0024 §6 sequences M1-b BEFORE M1-d; PLAN #335: "REMAINING: **M1-b** → M1-d". No output doc exists. It is now RUNNABLE: the 7/4 blocker ("theme axis 0 accrued") is cleared — prod `mi_theme_axis_shadow` = **461 rows** (through 7/10, incl. historical backfill to 3/24); harness `scripts/eval_judge_enrich.py` exists. Operator-gated spend; ~this week. |

## 1b. Adversarial findings (what the pack takes on faith)

**F1 — The pack names the WRONG toggle and misstates the current state.** The pack's decision
paragraph says "Flip `get_holistic_judge_enabled()` … Today the judge writes advisory columns
only; the conviction floor decides." **False on prod**: `mi_safeguard_state` shows
`holistic_judge_enabled | paper | on` since **2026-06-10 14:43 UTC** (operator-signed —
CHANGELOG "JUDGE LOAD-BEARING day", first real call CBRL), and **41 of 42** alerts since 6/10
carry `grade_engine_authority='judge'`. The judge has been authoritative for a month. The
actual M1-d flip per ADR 0024 §6 and the amendment draft is **`composite_authority`** (the
theme-axis composition on top of the judge's verdict). Consequence: the pack's verify-live
step ("`ep_grade_decision` rows show `authority='judge'`") would pass TODAY with no action
taken — it verifies the 6/10 flip, not M1. Correct verify-live = composition evidence
(theme-credit contributions in the trace / a composed final tier ≠ judge tier on an
Accelerating-theme alert / the `/why` render).

**F2 — Flipping `composite_authority` today is a NO-OP: the wire-in does not exist.**
`compose_final_tier` / `composite_authority_enabled()` have **zero call sites outside
`meta_rubric_compose.py` and its tests** (repo-wide grep). The credit function
(`catalyst_rubric_runtime.theme_axis_credit`, :540) is shadow-only. ADR 0024 §6 has no
wire-in card (M1-a built only the pure function, deliberately dark). So the sitting cannot
"end in an action" unless a small wire-in ships first: grade path → judge verdict →
`theme_axis_credit` → `compose_final_tier` → composed tier through the same atomic
`update_ep_alert_judge_result`, gated behind the default-off flag (dark until flipped).
Estimated small (~40-60 lines + tests, mirrors the M1-a golden cases) — buildable pre-7/18,
but it is an unbuilt, unnamed dependency today.

**F3 — Rollback is not what the pack says.** Pack: "Rollback = the same runtime toggle, off
(no deploy)." Reality: `COMPOSITE_AUTHORITY` is an **env var** (`meta_rubric_compose.py:34-39`)
— flip/rollback = compose-file env edit + container recreate, i.e. a mid-day service bounce,
not an instant runtime revert. The amendment itself requires the flip to ride a COMMIT (the
rubric amendment must go live atomically with the composition — §2 atomicity). The code
comment already anticipates the fix: replace the env read with a DB-backed toggle at M1-d.
Rec: the wire-in card (F2) should include the DB toggle (mirror `holistic_judge_enabled`'s
`mi_safeguard_state` pattern + a `set_composite_authority.py` twin) so rollback is genuinely
instant and deploy-free — only then does the pack's rollback claim become true.

**F4 — The flip commit trips [5m/7] by design — sequence it explicitly.** The amendment edits
`_RUBRIC` → hash changes → the gate FAILS the deploy until the 0030 eval re-runs green on the
amended rubric (~$5, 36 calls, on prod) and the pass record is regenerated. The pack knows
this ("the gate's first real exercise") but the mechanics section doesn't sequence it. Correct
order: (1) wire-in + DB toggle + amendment in one commit → (2) re-run
`run_judge_robustness_eval.py` on prod → green → new pass record → (3) `deploy.sh
market-agent` (gate passes) → (4) operator flips the toggle off-hours → (5) verify-live per F1.

**F5 (minor) — eval/live config parity on `axis_reads`.** The 36/36 eval ran
`include_axis_reads=ON`; the live `grade_holistic` call (`ep_detector.py:3169`) runs the
default OFF, and [5m/7] does not key on this flag. If the axis wire-ins flip WITH authority
(pack's rec), live matches the eval'd config — good. If they do NOT, the passing eval
permanently certifies a config live doesn't run. Note also: theme narratives ALREADY flow into
the judge prompt (`active_narratives=_narrative_cohorts`, `ep_detector.py:3167` — live), so
"theme heat into the prompt" is partially pre-existing; what M1 adds is the *scored, arithmetic*
credit outside the judge.

**F6 (minor) — T2c will be noisy exactly when it matters.** Grade-decision flow is 1-2/day
(prod, last 14d) and the metrics have deliberately no N-floor — a single-HIGH day reads 1.0 >
the 0.85 ceiling ⇒ expect cold-window L2 pings. And the amendment itself shifts judge-tier
behavior (theme stops moving the tier) precisely while n≈5 — the band's baseline is born
mid-shift. Handled by the pack's pre-declared-shift idiom + generous ceilings; state it at the
sitting so the first pings aren't read as drift.

## 1c. The fork + rec

**Fork:** (A) close the three gaps this week — wire-in + DB toggle built dark, M1-b regrade
run with the delta table on the sitting table, pack's decision paragraph corrected — then 7/18
signs AND flips as planned; vs (B) 7/18 signs the package (credit table, ±1 cap, amendment
wording) but the flip executes only when M1-b + the wire-in land.

**Rec (1 line): GO-conditional — 7/18 is honestly signable ONLY IF the F2 wire-in (with DB
toggle) is deployed dark and M1-b's delta table is at the sitting; if either misses, sign the
package and DEFER the flip days-not-weeks (fork B), never flip a no-op toggle for the optics.**

## 1d. If GO — exact flip mechanics + rollback (corrected from the pack)

1. Pre-sitting (this week): wire-in commit = grade-path consumption of
   `theme_axis_credit`+`compose_final_tier` behind the flag + DB-backed toggle
   (`mi_safeguard_state` pattern) + amendment text in `ep_grade_judge.py` clause 5 and ADR 0011
   clause 4 (both mirrors, same commit). Run M1-b (`eval_judge_enrich --regrade`, ONE paid run)
   → delta table.
2. Re-run the 0030 eval on the amended rubric on prod → green → regenerate
   `judge_eval_pass_record.json`.
3. `bash scripts/deploy.sh market-agent` — [5m/7] passes against the new record; flag still OFF
   ⇒ behavior byte-identical.
4. At the sitting: walk M1-b deltas + labels → sign credit table (§3), ±1 cap, amendment,
   Mainstream open question → operator flips the DB toggle ON (off-hours; instant, no deploy).
5. Verify-live (next scan day): a composed tier visibly ≠ judge tier on an Accelerating-theme
   alert (or an explicit composition trace row) + `/why` renders the contribution + T2c samples
   ticking (checklist row 3 query). Pre-declare the T2c level shift in the flip's audit note.
6. Rollback = DB toggle OFF (instant; composition stops, judge-authority behavior of the last
   month resumes). The amendment text rollback, if ever needed, is a revert commit → re-eval →
   redeploy (CHANGE_PROCESS).

---

# Decision 2 — #397: the HTF money gate (shadow→paper)

## 2a. Precondition checklist

| # | Precondition | Status | Evidence |
|---|---|---|---|
| 1 | Shadow settlements ≥ 10 (the signed gate) | **NOT-MET — 0 settled** | Prod 7/13: `mi_htf_breakout_shadow` = **6 rows, ALL outcome NULL** (XMTR 6/29 · OKTA+CRWD 7/1 · RBRK+OKTA 7/6 · SNOW 7/7). Gate: `data_gated_reviews.yaml::htf_breakout_paper_graduation` — threshold **10 settled**, and its own `earliest_review_date` is **2026-07-20, after the sitting**. |
| 2 | Settlement math by 7/18 | **≤3 settled possible → QUERY AT SITTING** | `_HTF_SETTLE_WINDOW=12` trading bars (`flag_detector.py:75`): XMTR (6/29) settleable ~7/16-17; OKTA/CRWD (7/1) ~7/17+; the 7/6-7/7 trio settles 7/22-23. Best case at the sitting: N≈1-3 settled vs 10. |
| 3 | Takeable cohort | **N=1 takeable of 6** | **5 of 6** rows carry `would_reject_reason='stop_distance_gt_8pct'` (`_HTF_MAX_LOSS_PCT=0.08`, `flag_detector.py:109,137`) — the entry pipeline would have taken only XMTR. |
| 4 | Machinery alive | **MET** | `consolidation_readiness` (17:35 ET) + `htf_management_shadow` (17:36) green daily on prod (7/8-7/10 all success); HTF settle is folded + error-wrapped (`scheduler.py:3250-3252`); digest self-verifies settled counts. #396 mgmt shadow accruing (1 row). |
| 5 | Early edge signal | **Leans negative, N=1 (not evidence)** | The ONE takeable break (XMTR) already reads `closed_hard_stop` in `mi_htf_management_shadow` — the first settled datum will likely be a stop-out. Nothing accrued supports a GO; nothing at N=1 supports a kill either. |

## 2b. Adversarial findings

**G1 — 7/18 is a date, not a gate, and the gate is unreachable by it.** 0 settled today, ≤3 by
the sitting, threshold 10, and the review's own earliest date (7/20) post-dates the sitting.
Flow math: breaks arrive ~3/wk but only ~0.5/wk takeable ⇒ N=10 ANY-settled ≈ early-to-mid
August; N=10 TAKEABLE-settled ≈ late Q3. Consistent with #146-T3's independent datum (~4
triggers/3mo replay). PLAN #356's "[blocked: … #397 GO/NO-GO gate 7/18]" should be read as a
checkpoint, not a decision that can be made.

**G2 — Gate precision: the graduation predicate counts would-reject rows.** `SELECT COUNT(*)
… WHERE outcome IS NOT NULL` includes the `stop_distance_gt_8pct` rows — at the current 5:1
mix the review could "arm" at N=10 with only ~2 rows the pipeline would actually have taken.
A paper GO judged on the blended cohort grades an entry the system wouldn't take. Pre-agree
NOW: the GO cohort = `would_reject_reason IS NULL` settled rows; the would-reject cohort is
kept separately as counterfactual evidence.

**G3 — The 8% stop-cap is silently the binding constraint on the whole lane.** 5/6 rejects
come from one parameter. Before ANY paper promotion the operator faces a hidden prior
question: is `stop_distance_gt_8pct` the setup's definition (sourced 5-8% — likely yes) or a
tunable eating the cohort? If it stands (primary-definition discipline says it should), a
paper lane at ~0.5 takeable breaks/wk needs a quarter to produce its own N — set that
expectation at promotion time, not after. (The separate `htf_adr_threshold_tune` review is the
ADR-floor tune, N≥10 settled winners — even further out.)

## 2c. The fork + rec

**Fork:** DEFER-with-date (re-key #397 to the evidence gate) vs NO-GO (kill the lane).

**Rec (1 line): DEFER, explicitly not NO-GO — at the sitting re-date #397 to ~8/07 keyed to
`htf_breakout_paper_graduation` auto-arming (N≥10 settled), and pre-agree the GO bar now:
takeable-cohort only (G2), expectancy ≥ 0R at N≥10 with win%/MFE noted, would-reject cohort
reviewed alongside as the 8%-cap counterfactual (G3).**

## 2d. Flip mechanics

Not applicable at 7/18 (DEFER). What the sitting CAN productively sign: the GO-bar
pre-agreement above, so the ~8/07 review is a ruling, not a debate.

---

# Verdict

**#335 is signable on 7/18 only conditionally; #397 is not decidable on 7/18 and should be
deferred by evidence, not rejected.** For M1, five of the pack's six preconditions verify
clean (robustness 36/36 with the recorded legibility caveat; [5m/7] live and exercised; grade-era
versioning; fail-open; the gating review scheduled) — but the pack misdescribes the decision
itself: judge authority has been live since 6/10 (prod-verified), the real flip is
`composite_authority`, and that flag currently controls **nothing** (no wire-in), is env-read
(no instant rollback), and its non-negotiable evidence gate (the M1-b batched regrade, named
in the amendment the operator will sign) has not run — though its input (461 theme-axis shadow
rows) is now sufficient and the harness exists. **MUST close before 7/18: the wire-in built
dark with a DB-backed toggle, M1-b's delta table produced, T2c sample accrual confirmed
(first sample expected 7/13 16:15 ET), and the pack's decision paragraph + verify-live step
corrected** — with those closed, GO; with either of the first two open, sign the package and
defer only the flip. For HTF, the machinery is verified alive and the honest state is 6
breaks / 0 settled / 1 takeable / first takeable already at hard-stop in the management
shadow: the signed N≥10 gate cannot be met by 7/18 (its own earliest review date is 7/20), so
the only sign-off that respects the evidence discipline is **DEFER to ~8/07 with the GO bar
(takeable-cohort segmentation + ≥0R expectancy) pre-agreed at the sitting.**
