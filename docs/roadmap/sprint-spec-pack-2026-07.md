# Sprint Spec-Pack — prepared 7/2 evening (the Fable-half, done ahead)

Companion to `long-weekend-sprint-2026-07.md` (§Kickoff pre-sort). **Model split:** Fable 5 =
plan/design/review/careful-path; Sonnet 5 subagents = execution of the SPEC CARDS below (each
self-contained: files → change → DoD → test). Every Sonnet diff gets Fable review before commit.
**Never delegated:** trade-state/money-path edits, methodology semantics (THE LINE), deploys.

---

## A. Deploy-batch runsheet (Fri first hour — one `deploy.sh market-agent` pass)

Already committed, riding this batch — deploy once, then verify each:

| Item | Verify (after DEPLOY OK) |
|---|---|
| #411 sweep cron 18:00 | running scheduler registers `monthly_backward_check_sweep` at 18:00 ET (log line or jobs dump) |
| #401 naked-live alarm | image grep `NAKED LIVE POSITION` = 1 (event rare-by-design; tests carry the logic) |
| #400 toggle + #149 retire | image grep `get_runtime_toggle` ≥1 AND `_yoy_shadow_candidates` = 0; next 7:00 scan clean |
| #384(1) tweet RVOL | image grep `_resolve_ep_rvol` in twitter.py = 1 (posting still OFF — cosmetic until flip) |
| F1 /regime fix | send `/regime` → the why-block appears ONCE |
| F2 HTF-shadow per-break | image grep confirms; next intraday tick writes per-break |
| sweep-floor 2200 | tonight-7/7's `nightly_data_pull` run shows `status=success` (first green since 6/15!) |
| #342 eval CSVs | move cohort CSVs under scripts/ in the SAME commit as the Dockerfile check → container ls |
| #405 catalyst-cache | gated on the advisor-designed "filtered-ticker-never-enters" test — build first (card S6) |
| #406 alpaca label | fix + `maybe_alert_api_failure` register — small (card S5) |

NB: docker/ or shared/ changes would widen scope to `both`; #154 tier-2 guard aborts if the pull
touches out-of-scope files — check its output before assuming market-agent-only.

## B. Operator decision briefs (2 min each, kickoff)

**#305 close-criterion.** Fact: arm-mechanic VERIFIED-LIVE (AVAV 6/30 armed clean/cancelled clean);
zero fills in 3 days of thin tape. Option A: close #305 as "launch executed, entry-path verified" +
spin a standalone first-fill watch task (burndown-friendly, honest — the launch DID execute).
Option B: hold open until a fill (the full lifecycle incl. stop-attach-on-fill + exits has never
run on real money). **Rec: A** — the un-verified remainder is better tracked as its own watch item
(the fill verifies trade_stream/finalize paths, which #184/#151 harnesses already cover on paper);
#305 open past launch reads as launch-not-done, which is false. Your call — real money.

**#364 dead buttons.** Fact (review F17): the staged-proposal Confirm flow is STRUCTURALLY broken
under the HTTP split (callback lands on the creds-less intelligence container; flips status
'confirmed' BEFORE submit → wedge). Dormant (no strategy stages proposals). Option A: REMOVE the
buttons + the `/broker/callback` registration on intelligence (F17 dies with it). Option B: fix the
routing (design work for a path nothing uses). **Rec: A** — if staged mode ever returns, it needs a
real design pass anyway (the wedge ordering too). Removal = burndown + kills a HIGH finding.

## C. Sonnet 5 spec cards (execution tier — dispatch with `model:"sonnet"`, worktree, test-gated)

- **S1 (F4+#261, DO FIRST, one unit):** re-home `build_judge_payload`/`fetch_profile`/
  `resolve_grounded_text` from `scripts/_judge_replay_common.py` → new
  `agents/market_intelligence/judge_replay_common.py`; scripts file becomes a thin re-export;
  update the scheduler import (scheduler.py:3212) + any eval-script imports. THEN the #261 reorg
  remainder can proceed safely. DoD: grep = no prod import from scripts/; suite green.
- **S2 (F9):** add `log_anthropic_call_safe(...)` wrapper (one WARNING on failure) in
  spend_tracker.py; replace the ~16 pasted `try/except: pass` blocks. DoD: grep shows 0 pasted
  blocks; a test that a raising tracker logs WARNING and doesn't propagate.
- **S3 (F13):** extract `_post_market_task(task, user_id, timeout)` in channels/telegram.py
  (Markdown→plain fallback included); route /themes-arg, /ideas, /ideas-drill through it. DoD:
  the 3 sites use it; a test pins the /themes plain-fallback on Markdown 400. ⚠ orchestrator-owned
  → needs `deploy.sh orchestrator` (or both) — batch note.
- **S4 (F5+F6):** ep_detector #344 blocks — extract `_build_enriched_corpus(...)` shared by the
  enrichment + re-poll shadows; count-precheck uses `include_content=False`, bodies fetched only
  on trigger. DoD: one pipeline, light precheck; existing #344 tests green.
- **S5 (#406):** register alpaca in the #370 provider registry + fix the wrong-domain consequence
  on `maybe_alert_api_failure("alpaca", ...)`. Small; follow the task line.
- **S6 (#405 test-first):** build the advisor-designed "filtered-ticker-never-enters" test, then
  the catalyst-cache re-grade refactor per the task line. Fable reviews the refactor diff extra
  care (grade path — but shipped logic, not methodology).
- **S7 (F12):** module-level `_coerce_date(v)` in db.py; replace the 4 `_dd` copies + the
  live_tracker inline. DoD: one definition, suite green.
- **S8 (F15+F11):** move `_FLAG_DEPTH_MIN` to the constants block; generalize
  `anticipation.entry_bet_outcome` (entry-price override + include-entry-bar flag) and make
  `_htf_settle_from_bars` call it. DoD: settle semantics single-sourced; HTF+anticipation tests green.
- **S9 (#279):** the W2 /simplify deferrals per task line (derive `_EXEC_HANDLERS`; bidirectional
  partition guard; dedup feed resolver). DoD per item; suite green.
- **S10 (#409):** rename "Consolidation plays" → "Anticipation plays" across user-facing surfaces
  (boards/digests; grep for the label). DoD: no user-facing "Consolidation plays" remains.
- **S11 (#387+#410 shared core):** wire the `mna_filter` exclusion into the anticipation universe
  + the coil-finder buyout-pin guard (sub-1% stop distance + gap-to-flat shape = pin candidate →
  exclude + audit row). Family-A shadow only (no money). DoD: NUVL-shaped fixture excluded; tests.
- **S12 (F21):** kill/scale band-transition dedup — advisory-lock or upsert-guard the
  read→write. DoD: concurrent double-eval test emits once.

## D. Fable-only designs (careful path — trade-state; paper-exercise per #151 before relying)

- **F22 fix (FIRST):** make the 4:45 write monotonic — `SET breakeven_active =
  mi_live_trades.breakeven_active OR $3` (the flag never legitimately goes TRUE→FALSE intra-trade;
  finalize_partial_exit is the only TRUE-writer). Add a regression test: job-start read FALSE,
  finalize lands TRUE mid-job → post-job flag still TRUE. Paper-exercise: force the interleave with
  the #151 harness. Alternative considered+rejected: dropping the column from the UPDATE (loses the
  legitimate day-N passthrough when no partial exists — the OR form is strictly safer and smaller).
- **F16 fix:** exceptions-out read for the coverage loop only — `get_open_orders(...,
  raise_on_error=True)` param (default False keeps every other caller's [] contract) → the existing
  `except → defer` branch becomes live. Test: raising client → no stop placed, defer logged.
- **F18 fix:** `_exec_call` catches Exception → 500-with-body `{error_type, error_message}`;
  `_http_call` re-raises `ExecutionCallFailed(error_type, msg)` (new, distinct from
  ExecutionUnreachable) on a 500-with-body vs Unreachable on transport errors. Callers: audit which
  catch ExecutionUnreachable and decide per-site (most: same handling, better label). Staging
  exercise before deploy.
- **#184/#225:** advance per their task lines; the F22 exercise shares the same harness session.

## E. Suggested sprint flow (model-tagged)

- **Fri AM:** [You] briefs B · [Fable] deploy batch A + verifies · [Sonnet ×3 parallel] S1, S2, S7.
- **Fri PM:** [Fable] F22 design→implement→paper-exercise (D) · [Sonnet] S4, S5, S6, S12.
- **Sat:** [Fable] #328 theme-axis design + shadow build (Track 2, deep-focus) · [Sonnet] S3, S8,
  S9, S10, S11 · [Together] Track-6 reviews (the 3 investigations + cutover gates).
- **Sun:** [Fable] F16/F18 + hardening lane · [Sonnet] burndown remainder · [Together] triage-the-38
  cleanup · CLOSE with honest re-dates.
- Every Sonnet diff: Fable review → commit; deploys batch to windows; verify-lists per §A.
