# Runbook — the 2026-08-27 deploy, and exactly what to check on 08-28

RUNBOOK_PIN: TONIGHT'S FIRST DEPLOY IS EXPECTED TO FAIL AT GATE [5m/7] EXIT 17.
RUNBOOK_PIN: That is correct — the rubric moved to v4 (d65ac7f3) and the gate refuses an
RUNBOOK_PIN: ungraded grade surface. Run the robustness eval (~$1.50, ONE run, capture to
RUNBOOK_PIN: a file), regenerate judge_eval_pass_record.json CARRYING ITS envelope SECTION
RUNBOOK_PIN: FORWARD, then redeploy market-agent AND execution. On FAIL: do not hand-edit
RUNBOOK_PIN: the record, do not waiver — revert by redeploying the prior commit.

Written 2026-08-27 PT so tonight and tomorrow are mechanical. Four changes are committed and
pushed but **running nowhere**; one (#559) is already live via a runtime toggle.

| what | ships how | state now |
|---|---|---|
| **#602** judge axis split + per-call reasons | rubric v4 — needs the eval | pushed, dark |
| **#233** boost retired · disagreement → judge · double-count telemetry | same rubric bump | pushed, dark |
| **#603** Perplexity Agent-API migration + fail-to-unavailable | code | pushed, dark |
| **#559** real-time gap decides the 9% floor | runtime toggle | **LIVE since 13:55 ET** |

Commits: `d5b947db` · `2d083d53` · `f084bb98` · `f0be165e` · `fbf30288`.

---

## Part 1 — the deploy (tonight, 21:15–22:15 ET window)

⚠ **Expect the FIRST deploy to FAIL at gate `[5m/7]` with exit 17. That is correct, not a
problem.** The rubric hash changed (v3 → `v4-2026-08-27-axis-split-second-opinion`,
`d65ac7f3`), and the gate refuses to ship an ungraded grade surface. The container comes up on
the new image *before* that gate runs, which is what makes step 2 possible.

```bash
# 1. ships the code; STOPS at [5m/7] exit 17 — expected
ssh apollo@87.99.134.162 'cd /home/apollo/apollo_the_wise && bash scripts/deploy.sh market-agent'

# 2. re-run the robustness eval against v4 — ~36 Opus calls, ~$1.50, ONE run.
#    CAPTURE IT TO A FILE. Do not re-run to re-read (2026-08-03 cost rule).
ssh apollo@87.99.134.162 'docker exec -i apollo-market python -m scripts.evals.run_judge_robustness_eval' \
  > ~/.claude/jobs/*/tmp/judge_eval_v4.txt 2>&1
tail -40 ~/.claude/jobs/*/tmp/judge_eval_v4.txt      # read the GATE line
```

**Read the `GATE:` line.**

- **`✓ PASS`** → regenerate `scripts/evals/judge_eval_pass_record.json` from the
  `RESULTS_JSON` block (`keys` + `summary`, `pass: true`, `run_at`). ⚠ **CARRY THE EXISTING
  `envelope` SECTION FORWARD VERBATIM** — it is hand-seeded, not eval-derived, and dropping it
  silently loses envelope-drift detection. Commit the record, push, then:
  ```bash
  ssh apollo@87.99.134.162 'cd /home/apollo/apollo_the_wise && bash scripts/deploy.sh market-agent'
  ssh apollo@87.99.134.162 'cd /home/apollo/apollo_the_wise && bash scripts/deploy.sh execution'
  ```
  Both are required — `ep_detector.py`, `db.py` and `collector.py` are all in
  `exec_loaded_modules.txt`.

- **`✗ FAIL`** → **do not hand-edit the record and do not waiver.** A v4 failure means the
  reword moved the judge, which is the thing the gate exists to catch. Read the per-class map
  for which cases broke, report to the operator, and leave the box on v3 code with the old
  record — the deployed image is already v4, so **revert by redeploying the prior commit**
  (`fbf30288~1`… whichever precedes the rubric change) rather than by editing anything.

⚠ Weekend deploys are ungated, but Thu 08-27 is a market day — the 21:15–22:15 ET window is
enforced (`deploy.sh` exits 12 outside it). The override is operator-only.

---

## Part 2 — verification (08-28, after the first EP alert)

Nothing below needs a paid call. Run the reads, then close or reopen each task.

### #602 — the judge says its own reason, and its direction stops contradicting itself
Look at the alert itself:
- a `⚖️ Judge:` line ending in a **one-line why** (not the long paragraph), and
- a `✅ Decision:` line ending in its own why.

```sql
SELECT ticker, judge_tier, baseline_floor_tier, judge_direction,
       judge_grade, judge_grade_reason, judge_tier_reason, rubric_version
FROM mi_ep_alerts WHERE alert_date = CURRENT_DATE ORDER BY ticker;
```
✅ `rubric_version` reads `v4-…`; both `*_reason` columns are non-NULL.
✅ **`judge_direction` agrees with the tier movement** — `hold` when
`judge_tier = baseline_floor_tier`. That contradiction is the OKTA bug; if `demote` still
appears under a held tier, v4 did not fix it and #602 stays open.

### #233 — boost gone, disagreement delivered
```sql
SELECT ticker, confidence_multiplier, catalyst_quality, gemini_validation, judge_grade
FROM mi_ep_alerts WHERE alert_date = CURRENT_DATE;
```
✅ `confidence_multiplier` is **1.0 on every row** (1.2 anywhere = the retirement did not ship).
✅ where `gemini_validation <> catalyst_quality`, the alert shows the second-opinion block;
where they agree, it shows nothing extra.
⚠ Expect **fewer HIGH alerts** — measured on today's four, two fall under the bar without the
boost, and the judge promoted one of them back (CRWD) but not the other (DG). A quiet morning
is the predicted outcome, not evidence of a fault.

### #603 — Perplexity still answers, and the cost is the reported one
```sql
SELECT caller, model, input_tokens, output_tokens, cost_usd, stop_reason
FROM api_usage WHERE caller LIKE 'perplexity%' AND created_at::date = CURRENT_DATE;
```
✅ rows exist for `perplexity_news_search` / `perplexity_catalyst_validate`.
✅ `model` records what Perplexity actually routed to (e.g. `openai/gpt-5.6-luna`), **not**
`sonar-pro` — a `sonar-pro` row means the old path is somehow still running.
✅ `cost_usd` looks like a reported figure (~$0.004–0.012), not a rate-table estimate.
✅ `gemini_validation` is populated on alerts that had catalyst text, and **NULL** where there
was none — NULL is the correct new answer, not a failure.

### #559 — the real-time gap is deciding
```sql
SELECT summary, detail FROM mi_audit_log
WHERE event_type = 'ep_rt_floor_flip_up'
  AND (created_at AT TIME ZONE 'America/New_York')::date = CURRENT_DATE;
```
✅ at least one event with `"authoritative": true` in the detail.
✅ ideally an admitted candidate whose delayed gap was below 9% — that is the switch acting.
⚠ Seasonality: admits ran 60/day in late July and 4–11/day this past week. A quiet count
tomorrow says nothing; the real test is the next reporting season (late October).

---

## If something looks wrong

- **#559** reverts alone in ~60s: set `ep_rt_gap_authoritative` to `off` in
  `mi_safeguard_state`. No deploy.
- **#233's boost** does *not* revert by toggle — it is a code change.
- **The rubric** reverts by redeploying the prior commit, never by editing the pass record.
- Attribution is the risk: four changes verify on one morning. Take them in the order above —
  the toggle is independent of the other three.
