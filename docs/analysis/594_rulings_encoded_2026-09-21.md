# #594 step 0 — the structure read, scored against his 25 chart rulings

**MEASUREMENT ONLY. Nothing was changed.** No rule, threshold, filter, cutline or trade behaviour
was touched. This encodes labels he has already given and reports what the existing $0 read scores
against them. Any change this implies is his fork (THE LINE).

## Method and population

**Parameter — ONE, pre-declared, unfitted.** `runup_low_pct_20 >= 75.0` ("ANCHOR-75"): his own
signed 75%, chosen by him on other evidence **before the structure study existed**. It is the single
bolded row of `structure_read_v3_2026-08-25.md` §2 — the only result there that owes nothing to a
cutline picked after seeing the labels. **No search over cutlines was run**, and
`tests/test_594_chart_rulings_are_encoded.py` fails the build if one is added to the scorer.

**Populations, all derived from the fixtures rather than listed by hand:**

| population | n | source |
|---|---|---|
| real EPs (the RULE 0 bar) | **30** | `must_not_miss_eps.MUST_NOT_MISS` **minus its 3 `excluded=True` members** |
| his must-NOT-reject dates | **3** | `must_not_trade_charts.MUST_NOT_REJECT_DATES` (GOOD_CHART / OKISH_CHART / OKISH_EARLIER) |
| dates he condemned | **17** | `must_not_trade_charts.MUST_NOT_TRADE` (BAD_CHART) |
| dates he only POINTED AT | 3 | flags, **not** labels — kept apart so inference never wears his name |

Bars: `mi_daily_closes`, pulled once from prod 2026-09-21 for the 52 tickers these populations
name. A date whose bars do not read is counted in its own `unreadable` column and **never** as
having passed.

⚠ **The exclusions are load-bearing and the first run got them wrong.** It read all 33
`MUST_NOT_MISS` rows and reported *"1 of 33 real EPs wrongly rejected — TDIC 2026-05-12"*, which
reads as a RULE 0 violation. TDIC carries `excluded=True`; its own reason calls it **"a data
anomaly, not a real tradeable EP"** — next-day high $750, close $576, then a full round-trip to
$20. `test_577_must_not_miss_eps.py` does not assert on it either. ABNB 2026-08-07 and CHPT
2026-09-03 are the other two. The arithmetic was right and the population was wrong, which is this
repo's recurring defect appearing inside the fix for it.

## The result

| direction | count | the 2026-08-25 study, for comparison |
|---|---|---|
| **real EPs wrongly rejected (RULE 0)** | **0 of 30** | 0 of 26 |
| **his must-NOT-reject dates lost** | **0 of 3** | 0 (population did not exist yet) |
| dates he condemned, rejected | **9 of 17 (53%)** | 8 of 11 (73%) |
| pointed-at dates rejected (a flag, not a miss) | 1 of 3 — MXL 2026-04-24 | MXL 2026-04-24 |

**The honest headline is the third row falling.** RULE 0 stays clean and his approved dates all
survive — but as his label set grew from 11 condemned charts to 17, the run-up rule's coverage of
them fell from **73% (8/11)** to **53% (9/17)**. The six new BAD_CHART labels encode something the
run-up number does not see.

**That is consistent with the criteria he actually applied on 2026-09-06**, none of which is a
run-up measure: (1) did the gap CLEAR overhead supply, measured against **multi-year** structure —
an Oct-2025 double top, a 2022 base; (2) **where it closed in the day's range**; (3) position
versus the 10/20/50/200 MAs; (4) the prior trend. Items (2) and (3) are day-0 computable facts we
do not score at all.

## What this does not answer

- **Whether the read has an edge.** It does not. The 2026-08-25 backtest measured the supply read
  as a NULL winner predictor (0.496 at matched dollar volume, n=2,787) and that is unchanged here.
  This measures agreement with *his labels*, which is a different question.
- **Whether 53% is good.** There is no baseline for "what fraction of his rejects any rule should
  catch", and at n=17 a difference of two charts moves it 12 points.
- **Whether the six new labels are harder or merely different.** Not tested — it would need the
  per-criterion breakdown above, and (2) and (3) are not computed anywhere yet.
- **Anything about a cutline other than 75.** Deliberately: at this n a favourable one is trivial
  to find and worthless, and the fixture says so in its own header.
- **Whether a paid vision eval would beat this.** That is #519's question. This exists so that run
  has a number to be read against; it does not pre-judge it.

## What it unblocks

`scripts/probes/_structure_read_v3.py` now scores against his rulings in **both** directions
(`score_against_operator_rulings`), which is step 0 of the chart-vision chain in **#519** and the
gate in front of roughly **$190** of paid-eval spend. Before today the fixture was mentioned in the
probe's docstring and read by nothing.
