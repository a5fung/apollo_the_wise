# #267 chart-vision judge eval — runbook + design (for the 6/18 operator-labeling session)

**Status (2026-06-17, part 1 built):** renderer + multimodal payload + two-sided eval harness shipped
(commits on `main`). The eval RUN is operator-triggered on 6/18 (API spend). The judge is
load-bearing (ADR 0011) — this measures a CANDIDATE chart axis; promoting it into the live
`_build_judge_prompt` is a separate CHANGE_PROCESS + operator-sign-off step, NOT done here.

## What the eval measures
Re-grade a cohort of historical EP alerts through the holistic judge **twice** per row:
- **no-chart arm** — the existing prompt, text-only (today's behaviour, the baseline).
- **with-chart arm** — existing prompt **+ candidate `CHART_AXIS_NOTE` + the rendered daily chart**.

Surface the rows whose verdict CHANGED → the operator labels each right/wrong. The agent never
self-certifies (ADR 0011: the operator owns the flip gate).

## Disciplines baked in (advisor 2026-06-17)
- **No lookahead** — the chart is rendered through the **prior trading day** (`mi_daily_closes
  WHERE trade_date < alert_date`). The alert-day candle is the breakout-day range the judge is asked
  to predict; it must not appear. Title says "as of … pre-alert".
- **Anchored image** — the bare image is unanchored (the base rubric never mentions charts), so the
  with-chart arm appends `CHART_AXIS_NOTE` (the candidate technical-structure instruction). That
  note text **is the thing being labeled** for value.
- **Two-sided cohort** — `deadcat_cohort.csv` is an adversarial REJECT set (a chart axis that rejects
  everything scores perfectly on it). The KEEP set (clean winners) catches the chart causing FALSE
  rejections. **Pass BOTH `--cohort` flags** or the read is half-blind.
- **Noise floor** — both arms run K replicates; a delta counts only when each arm's modal is STABLE
  across K AND the modals differ (adaptive thinking → non-deterministic).
- **Emit the PNGs** — every chart is saved to `--outdir` keyed by `ticker_date.png` so the operator
  labels seeing the SAME chart the judge saw.

## 6/18 RUNBOOK (in order — none of these steps is optional)
1. **Deploy the renderer dep.** `requirements/base.txt` gained `mplfinance` + `matplotlib`; the
   eval runs in the apollo-market image, so it must be rebuilt:
   `bash scripts/deploy.sh market-agent` (or `both`). Confirm `docker ps` shows apollo-market
   "Up <seconds>".
2. **Generate the KEEP side + CONFIRM non-empty:**
   `docker exec apollo-market python /app/scripts/build_clean_breakout_cohort.py --out /app/clean_breakout_cohort.csv`
   → it prints the count. If it prints the ⚠️ EMPTY warning, the `(ticker, alert_date=scan_date)`
   join did not align — diagnose (or hand-source a keep cohort) BEFORE running the eval; do NOT run
   one-sided.
3. **Smoke (machinery, ~$ negligible):**
   `docker exec apollo-market python /app/scripts/eval_chart_judge.py --cohort /app/deadcat_cohort.csv:reject --limit 4 --replicates 3 --outdir /app/_chart_eval`
   → confirm charts render (render rate), both arms call, 0 deltas is fine (smoke ≠ efficacy).
4. **Full two-sided run (operator-triggered — API spend, ~$ single-digit):**
   `docker exec apollo-market python /app/scripts/eval_chart_judge.py --cohort /app/deadcat_cohort.csv:reject --cohort /app/clean_breakout_cohort.csv:keep --replicates 3 --outdir /app/_chart_eval`
5. **Label.** Pull the `_chart_eval/*.png` + the delta output. Operator labels each delta:
   - REJECT side: a chart-driven downgrade is a **correct catch**.
   - KEEP side: a chart-driven downgrade is a **false rejection** (the failure mode to watch).
6. **Decide (gated).** If the labels support the axis, promoting `CHART_AXIS_NOTE` (or a refinement)
   into the live `_build_judge_prompt` is a CHANGE_PROCESS entry + operator sign-off (load-bearing
   judge). Not before.

## Candidate `CHART_AXIS_NOTE` (what's being measured)
Lives in `scripts/eval_chart_judge.py` (eval-only). Reads, in short: a daily chart (10/20/50 SMA +
volume, through the prior day) is attached; weigh prior trend/leadership, base quality (tight orderly
contraction vs sloppy), volume dry-up, location vs the MA stack, and over-extension — as ONE axis
that nudges the tier, not an override of a strong catalyst.

## Reuse / provenance
Renderer `agents/market_intelligence/chart_render.py` (mplfinance). Payload via the shared
`judge_transport.invoke_forced_tool(image_png=...)` + `grade_holistic(image_png=, chart_note=)`.
Harness mirrors `scripts/eval_tape_judge.py` (#299) discipline. Reject cohort = the #229 dead-cat set
(commit 2576a07). Cohort context wired by `cac2363` (#270 coil-maturity chart-read).
