# #519 — scoping the paid chart-vision run (2026-09-24, for iteration with the operator)

**Why this exists.** He asked for the paid run to be re-scoped before any spend: *"I don't want to
spend that much right now, need to know how best to scope it and what exactly we'll get out of it."*
Nothing here is authorised; it is the menu. The free step is re-run first on five years of history
(the weekly purge had deleted the approved backfill — fixed and reloading 2026-09-24 night).

## The question the money would answer

Can a model looking at the chart see what he sees — catch the charts he condemns that our run-up
rule misses (12 of 21 on the 09-23 scoring), **without** rejecting any of the 30 real EPs or his
9 approved dates?

## Method and population

- **Labelled dates:** every (ticker, date) in `tests/fixtures/must_not_trade_charts.py` (his 35
  chart rulings across three sessions, 2026-08-25 → 2026-09-23) plus the 30 assertable members of
  `tests/fixtures/must_not_miss_eps.py` (the 3 `excluded=True` members left out, as the scorer does).
- **Runnable by the harness:** a LEFT JOIN of those dates to prod `mi_ep_alerts` on
  (ticker, alert_date), read 2026-09-24 — a date is runnable only if a stored alert row exists,
  because `eval_chart_judge.py` re-grades the stored alert-time payload.
- **Costs:** per-call rates from `docs/analysis/519_chart_vision_eval_cost_2026-09-12.md` (3 arms ×
  3 replicates = 9 calls ≈ $0.26 per alert per pass); the corpus recounted today with that doc's own
  query: **383** settled HIGH/MODERATE alerts (was 372 on 09-12).

## A constraint that changes the scope (measured today)

The existing harness (`scripts/eval_chart_judge.py`) re-grades STORED alert payloads: it can only
run on dates that became alerts. Of his labelled dates, only **18** have an alert row:

| labelled group | dates | with an alert row (runnable by the harness today) |
|---|---|---|
| real EPs (must-not-miss) | 30 | **5** |
| his approved charts | 9 | **1** |
| his condemned charts | 23 | 12 |
| other rulings (wrong day, wrong stage) | 5 | 0 |

So the harness as built **cannot test the two things that matter most** — that no real EP and no
approved chart is lost — on his labels.

## Options

Rates at Opus-tier pricing (`claude-opus-5-5` has no price entry yet and is priced at opus-5's
$5/$25 per million tokens); image calls ≈ $0.02–0.03 each.

| option | what runs | calls | cost | what we get | what we don't |
|---|---|---|---|---|---|
| **A. Chart reader on his labels** | a model reads ONLY the point-in-time chart (bars to the day before) and answers in his vocabulary (bad / ok / good + the reason), 3 repeats each, on all ~67 labelled dates | ~200 | **under $10** | a direct yes/no on "does it see what he sees": which condemned charts it catches, and whether it rejects any real EP or approved chart | how it would change the live judge's grade (it sees no catalyst text) |
| **B. Existing harness on the 18 runnable labelled alerts** | judge with vs without chart, 3 repeats | ~110 | ~$3 | whether the chart moves the judge on those 18 | RULE 0: covers 5 of 30 real EPs and 1 of 9 approved — cannot answer the question |
| **C. Existing harness, full corpus, trimmed** | 383 alerts, 2 arms (no chart vs chart), 3 repeats, 1 pass | ~2,300 | ~$65 | every alert where the picture changes the verdict — a list for him to label (his time: likely tens of charts) | nothing about non-alerted names; still needs his labels to mean anything |
| **D. The plan as written** | 383 alerts, 3 arms, 3 repeats, run + re-run | ~6,900 | ~$200 | C plus the text-note arm and a repeat | — |

## Recommendation, for him to push back on

**A first.** It is the cheapest, it is the only option that tests the must-not-miss side on his
labels, and it answers his actual question. Only if A shows the model does see what he sees is C
worth its cost — and then as a list for him to label, not as a verdict.

## Option A — outcomes declared BEFORE it runs (operator asked 2026-09-24: *"be clear and specific on expectations so we know prior to running what we'd get"*)

**What it produces.** For each of the 64 scored labelled dates (30 real EPs, 9 approved = 4 good +
5 ok, 21 condemned, 4 other rejected — the free read's populations): the model's read of the
point-in-time chart, in his vocabulary — **bad / ok / good** — with a one-line reason, read 3 times
(~190 calls). The chart = daily bars to the prior close **plus the alert-day open marked**, because his
reasons are about what the gap cleared; `render_prior_day_chart` stops at the prior close, so that
marker is the one $0 addition. A weekly view needs tonight's five-year reload to land first (without
it, "multi-year downtrend" — RARE — cannot be seen). Then one scorecard against his labels:

| line | what is counted | the bar | today's run-up rule on the same line |
|---|---|---|---|
| 1. Real EPs it would reject | of the 30 must-not-miss EPs, how many it reads "bad" | **0** | 0 |
| 2. His approved charts it would reject | of his 9 approved (good or ok), how many it reads "bad" | **0** | 0 |
| 3. Condemned charts it catches | of his 21 condemned, how many it reads "bad" | more than the rule | 8 of 20 evaluable |
| 4. …of the ones the rule misses | of the 12 condemned the run-up rule lets through | **6 or more** | 0 of 12 |
| 5. Stable reads | dates where all 3 reads agree | **2 of 3 dates or more** | n/a |
| 6. Reasons | its reason beside his words, per condemned chart | for him to judge | — |

**Decision rules, fixed now:**
- **PASS** — lines 1 and 2 are zero, line 4 is 6 or more, line 5 holds → it sees something he sees
  that our rules do not. Next: decide on C (~$65), or run it as a shadow read on new alerts.
- **TOO STRICT** — it catches condemned charts but rejects any real EP or approved chart → not usable
  as a filter; at most a warning flag. Stop; no C.
- **FAIL** — fewer than 3 of the 12, or reads unstable on most dates → the model does not see what he
  sees at this task. Stop; no C.
- In between (3-5 of the 12, zero losses) → report it plainly and let him decide; no automatic next step.

**The expected result, stated before it runs:** the free read found no daily-bar measure that tells
the 12 misses from his 9 approved without rejecting real EPs. So the likeliest outcome is **in between
or TOO STRICT**; a PASS would mean the model reads a judgement (which highs matter) that our measures
cannot, and would be the surprise. The 4 other rejected dates are shown, not scored.

**What A cannot tell us:** how it would change the live judge's grade (it sees no catalyst text),
anything about returns, or how it reads names nobody has labelled. With 12 missed charts and 30
real EPs, a pass is a strong hint, not proof. One wrong call on a real EP flips it to TOO STRICT —
deliberately.

## What would change the recommendation

- If A's reads disagree with each other across the 3 repeats on most charts, the model is noise at
  this task and no larger run should follow.
- If he wants the live judge's behaviour tested (not just the chart read), A cannot do that; B/C can,
  but only on alerted names.
- More labelled charts from August 2025 onward (he has offered) raise A's n at almost no cost.

## What this does not answer
- Costs are estimates from the 09-12 per-call measurements; A's prompt does not exist yet (a small
  build, $0) and its exact tokens are unmeasured.
- Opus 5.5 always thinks, which may raise output tokens per call; not yet measured on image calls.
