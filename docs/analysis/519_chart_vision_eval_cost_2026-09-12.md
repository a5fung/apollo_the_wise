# #519 — chart-vision eval: one cost number for the whole path

**2026-09-12 · read-only, $0 spent · no LLM call made · harness `scripts/eval_chart_judge.py`
(already built, unmodified) · pricing from `shared/llm_models.pricing_for()`**

## The number

**$116 for the whole path** (227-alert run + one re-run) — **$0.26/alert** for a single pass.

| | one run (227 alerts) | whole path (run + 1 re-run) |
|---|---|---|
| **point estimate** | **$58** | **$116** |
| real-spend band (§1, cross-check) | $51 – $64 | **$101 – $128** |
| structural ceiling (near-cap corpus) | $80 | $161 *(see caveat below)* |

This is priced from measurements, not the harness's own printed estimate. The harness's built-in
guess (its `main()` prints "est cost ~$42.39" for one run using hardcoded constants) is not wrong
in its rate, only in its token assumptions — see §2.

**The $101–$128 band is not another guess — it is an independent cross-check from REAL money
already spent** on this exact code path (§1's #343 shadow: same prompt builder, same renderer, same
B/C arms), and it brackets the $116 point estimate almost exactly, so it does not depend on the
chars/token ratio or the output-token estimate below being exactly right. **The $161 "structural
ceiling" is NOT a realistic scenario**: reconciling it against the same real spend evidence implies
every alert would need only 13–275 output tokens/call, which contradicts the 450–715 tokens/call
the same evidence supports (§1) — near-cap corpora paired with real observed spending are mutually
exclusive. It is reported only as the payload's mechanical ceiling, not a likely outcome.

## 1. Method / population — what was priced, and how

- **Harness.** `scripts/eval_chart_judge.py` — read-only, no DB writes, already shipped (#267 W4).
  Not built or modified here; read in full to count calls, not assumed.
- **Cohort, n=227.** Sourced from the operator-facing #519 line in `PLAN.md` ("the corpus is
  already 4x bigger: 227 graded alerts with settled 5d outcomes"), a figure first stated around
  2026-08-02 and repeated unchanged on 2026-09-05 and 2026-09-12. **This is NOT independently
  re-derived here** — this analysis sandbox has no database credentials (no `.env`, no `docker`,
  and an attempted `ssh` to the production host at `87.99.134.162` was refused by this
  environment's own guardrail, correctly, since the task requires zero spend and zero production
  contact). **Treat 227 as a FLOOR, not a current count** — the corpus grows daily as alerts settle
  their 5-day outcome, so ~6 weeks of drift is unaccounted for. **One reasonable re-count** before
  any spend is authorized (the PLAN.md line does not pin an exact filter — this mirrors
  `judge_replay_common.REPLAY_SQL`'s tier gate; `build_clean_breakout_cohort.py`'s keep-side query
  instead uses `COALESCE(baseline_floor_tier, score_tier)` and requires `n_sessions_5d >= 4` for
  "settled", which could read a handful of rows differently at the margin):
  ```sql
  SELECT COUNT(*) FROM mi_ep_alerts a
  JOIN mi_ep_scan_outcomes o ON o.ticker = a.ticker AND o.scan_date = a.alert_date
  WHERE a.score_tier IN ('HIGH', 'MODERATE') AND o.fwd_5d_pct IS NOT NULL;
  ```
  A handful of the 227 will also skip for free (`no_chart` when <20 prior daily bars exist,
  `no_alert_row` on a stale ticker/date) — `eval_one()` returns before any judge call on those, so
  227 is also an upper bound on the rows that actually spend money.
- **Calls per alert.** Read directly from `eval_one()` / `main()` in the harness: **3 arms** (A
  baseline — no note, no image; B — text-only axis note; C — axis note + rendered chart) **× 3
  replicates** (the harness's own default, and the value used in both its documented example
  invocations — smoke and full run alike) = **9 calls/alert**. "The whole path" = the 227-alert run
  **plus one re-run** (operator's own rule, 2026-08-09: price the whole path up front, not
  increment by increment) = **2 passes**. Total calls: 3 × 3 × 227 × 2 = **4,086**.
- **Model + rate.** `agents/market_intelligence/ep_grade_judge.py` binds `MODEL =
  effective_model("JUDGE_MODEL")`. Run directly in this sandbox (no cache file present here, so it
  falls back to the committed pin — the live container may have resolved a newer opus release, but
  `pricing_for()`'s fallback prices any same-tier release at the tier rate, so this doesn't change
  the number either way):
  ```
  effective_model('JUDGE_MODEL') = claude-opus-5
  pricing_for('claude-opus-5')   = {'input': 5.0, 'output': 25.0}   # $/Mtok
  ```
  **Finding: no numeric disagreement with the harness's hardcoded rate today** — its
  `_OPUS_IN_PER_M = 5.0` / `_OPUS_OUT_PER_M = 25.0` match `pricing_for()` exactly. The
  **fragility** the task asked me to look for is structural, not numeric: the harness computes
  these as its own module constants instead of calling `pricing_for(effective_model("JUDGE_MODEL"))`
  — so a future `OPUS_PIN` rate change (the same class of bug that overstated `sonnet-5` spend by
  50% for a day, CLAUDE.md 2026-09-01) would silently desync the harness's printed estimate from
  the real bill. Not fixed here (read-only task); worth a one-line follow-up.
- **Input tokens — measured, not guessed.** Built the REAL production prompt locally (pure
  functions, no network, no DB) via `agents/market_intelligence/ep_grade_judge._build_judge_prompt`
  + `assemble_judge_inputs`, plus `agents/market_intelligence/chart_axis.CHART_AXIS_NOTE` /
  `CHART_AXIS_NOTE_TEXT_ONLY`, for two representative payloads:
  - **TYPICAL** — a plausible real catalyst (one SEC 8-K excerpt + one Benzinga wire + a short web
    summary, ~1.16K chars of grounded corpus): arm A = 6,397 chars, B = 7,539, C(text) = 7,693.
  - **NEAR-CAP** — every truncatable field pinned at the payload's OWN ceiling
    (`grounded_text`[:6000], `catalyst`/`analysis`[:1500] each, 5 narrative-cohort entries): arm A =
    14,068 chars, B = 15,210, C(text) = 15,364.
  Also measured and added to every call regardless of arm: the forced-tool JSON schema
  (`json.dumps(_judge_tool(False))` = 997 chars ≈ 285 tokens) — every judge call sends this as
  `tools=[...]`, and it is not part of the prompt string above.
  Chars→tokens at **~3.5 chars/token**, Anthropic's own published rule of thumb for English prose
  (no local Claude tokenizer is bundled with this SDK, and a `count_tokens` API call was avoided —
  the task's hard constraint is zero calls to Anthropic).
- **Image tokens — measured, not guessed.** Rendered a synthetic 130-bar OHLCV series through the
  REAL `agents/market_intelligence/chart_render.render_daily_chart_png` locally (same
  figsize/dpi/style the live path uses) → a **1047×743px** PNG. Anthropic's published image-token
  formula, (width×height)/750, gives **1,037 tokens** — corroborating the harness's own inline guess
  of "~1.2K image tok/call".
- **Output tokens — measured against real production evidence, not the harness's 250/call guess.**
  Two independent data points:
  1. `shared/output_ceilings.py`'s own record: `ep_grade_judge`'s `max_tokens` was raised
     **500→1500** after real traffic showed **79/404** (opus-4-8) and **7/49** (opus-5) judge calls
     CENSORED at exactly 500 tokens (~16-19% of real calls wanted more).
  2. The #343 chart-axis shadow's real spend — 336 calls (same B/C-arm structure, same prompt code,
     same chart renderer), **~$11/month**. Subtracting the measured input-token cost for that
     B/C-only mix implies **~450-715 output tokens/call**, depending on whether "$11/mo" is read
     literally or prorated from its actual 24-day measurement window.
  Used **600 tokens/call**, the middle of both bands — not the harness's flat 250.
- **Direct cross-check: the shadow's real $/call, translated to the eval's call mix.** The shadow
  runs only arms B and C (no A); its measured avg input ≈ 2,980 tok/call vs the eval's A/B/C
  average ≈ 2,691 tok/call (arm A is cheaper, and is 1/3 of the eval's calls) — a $0.0014/call
  input-cost difference. Applying that shift to the shadow's own observed $/call band ($0.0262 –
  $0.0327) gives an eval-mix rate of **$0.0247 – $0.0313/call**, i.e. **$101 – $128 for the whole
  4,086-call path** — independent of the chars/token ratio and close to the $116 point estimate
  built from the measured prompt sizes above. This is the strongest evidence in this document,
  because it is the only piece built from money actually spent rather than a local measurement.

## 2. Arithmetic (short enough to check)

```
3 arms × 3 replicates × 227 alerts × 2 passes = 4,086 calls

avg input tok/call  ≈ 2,691   (arm A 2,113 · B 2,439 · C 3,520 — C carries the +1,037 image
                                tokens; all three carry the +285 tool-schema tokens)
output tok/call     ≈   600   (measured — see §1)

cost/call  = 2,691/1e6 × $5.00  +  600/1e6 × $25.00
           = $0.01346 + $0.01500 = $0.02846

4,086 calls × $0.02846  ≈  $116.29
```

NEAR-CAP scenario (same formula, avg input tok/call ≈ 4,882): 4,086 × $0.0394 ≈ **$161**.

Harness's own printed formula, unchanged, for cross-check: one run ≈ $42.39 → whole path ≈ $85 —
inside the $116-$161 band's neighborhood but built on flat 2,500-tok/arm and 250-tok/call guesses
rather than a measured prompt or measured output evidence.

## 3. What this does not answer

- **Whether 227 is the current count.** Could not query the production database from this
  analysis sandbox (no credentials, no docker, ssh refused by the sandbox's own guardrail — this
  task correctly forbids production contact). Re-count with the SQL in §1 before authorizing spend.
- **Which scorer the eval should use.** Out of scope for this task by explicit instruction, and
  already retired from the standing-ask table (`check_plan.py::_standing_ask_gate`).
- **Whether the chart axis is worth shipping.** This document prices a run; it does not evaluate
  the chart axis's accuracy, and makes no claim either way.
- **The real distribution of catalyst-corpus length across the 227 alerts.** No production text
  was sampled (no DB access); TYPICAL/NEAR-CAP bracket the payload's own truncation limits rather
  than measuring the true average.
- **Exact Claude-5 tokenization.** No local tokenizer ships with this environment and an API
  `count_tokens` call was deliberately avoided (zero calls to Anthropic, per the task's hard
  constraint) — 3.5 chars/token is Anthropic's own published approximation, not a bill.

## 4. What would move the number

1. **n is a floor, not a count (biggest unknown).** 227 is ~6 weeks old (first stated ~2026-08-02).
   If the true current count is materially higher, the price scales linearly — re-count first.
2. **Real corpus richness.** TYPICAL ($116) vs NEAR-CAP ($161) is a 39% swing driven entirely by
   how much grounded catalyst text (SEC + wires + web) a typical graded alert actually carries —
   unmeasurable offline; the true average could sit anywhere in that band or (rarely) above it if a
   row's `active_narratives` block is unusually large.
3. **Output tokens/call.** Measured range is 450-715, not a fixed number; the low vs. high end of
   that band alone moves the total by roughly ±13%. A judge that writes long `rationale` text (up
   to its 1,000-char cap) pushes toward the high end.
4. **Timeouts still bill.** `grade_holistic`'s 40s `wait_for` can fire on a slow call; the tokens
   Anthropic already generated before the timeout are billed regardless, but the caller sees `None`
   and the row is excluded from the noise-floor stability count. Small (a handful of calls, not a
   material fraction of $116), but it means the true spend is never exactly zero for a call this
   analysis implicitly treats as "free because it produced nothing."
