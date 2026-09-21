# The two numbers #655 needs — what the evidence says

**2026-09-20, measured on his ask: *"I need more info to decide."* ⚖ Both targets are detection
thresholds and stay HIS. Nothing here changes a criterion; it exists so the decision has numbers.**

## Method and population — which rows, what window, derived how

**Step 2 (latency).** Population DERIVED, not listed: all 593 names in `mi_themes` collapsed to **452
lineages** by the identity rules already in use (rename edges + Jaccard), of which the headline uses
the **381 births since 2026-06-01** — the floor is set by data, not preference: `mi_stock_scores` is
WEEKLY before 2026-03-19 and daily after, and a birth needs ≥50 daily score sessions of lookback.
Each birth is classed by ONE uniform rule — **≥2 founders with an open gap ≥9% in the 20 sessions
through birth**, same-day meaning on the birth day or the day before — giving **grind 341 ·
co-gap-in-window 31 · same-day co-gap 9**, in 93% agreement with the independent class from step 1.
Move-start proxy = the founders' equal-weight index crossing above its **50-session** average and
still in force at naming, 3-session tolerance. Founders = the birth row's tickers only; eventual
members are unknowable before birth.

**Step 1 (correctness).** Population = every row in `mi_theme_relevance_cohort` with
`stratum='themed'` — **103 rows**, alerts **2026-03-24 → 2026-09-08**, all 103 labelled (last sitting
2026-09-13). A row entered the cohort when the UNBOUNDED as-of read found a theme
(`theme_axis_shadow.py:384`, verified in code). The **live-path cut is the 72 rows with a non-null
`theme_name_7d`** — the 7-day-bounded read `in_active_theme` actually uses — derived from the column,
not hand-picked. Precision = yes ÷ (yes + no); the single `unsure` (INTC 04-24) is excluded.
Confidence intervals are Wilson 95%; certification sizes are the smallest n at which observing zero
misses rejects "true rate below the bar" at 95% one-sided.

**Board snapshot** = `mi_themes`, latest row per name within 7 days, stage ≠ Retired — the
`get_active_themes` shape: **110 themes on 2026-09-18** (7 Accelerating / 36 Mainstream / 51 Fading /
16 Nascent). Prod was read once per table; nothing was written.


## Step 2 — "do we discover them early enough": ANSWERABLE, and nobody had measured it before

| how late is a theme named? | |
|---|---|
| Median, after the group's move starts | **20 calendar days (14 sessions)** (n=254 grind births with a trend in force) |
| p25 / p75 / p90 | 10 / 57 / 84 days (n=254) |
| **What the group already gained by naming** | **median +14%** (vs SPY +12%), p75 +30%, p90 +52% (n=254) |
| On the engine's OWN strength signal (founder RS ≥70) | median 7 days / 4 sessions (n=197 of 341 grind births that ever reached RS 70) — but that signal itself fires late, so this is a FLOOR on lateness |

**Population: 381 theme births since 2026-06-01** (daily scores only start 03-19), split by one uniform
rule: **grind 341 · co-gap-in-window 31 · same-day co-gap 9**. Move-start proxy = the founders'
equal-weight index crossing above its 50-session average, still in force at naming.

⚠ **Same-day co-gap births read 0 by construction and are EXCLUDED from lateness** — his own
reflexivity point: an EP manufactures relative strength, so a theme named the evening of the first EP
is the normal causal order, not a miss.

**Against his seven labelled EPs:** 4 got a covering theme — **PLTR and MRNA the same evening** (the
theme was made BY the EP), **TEAM +2 sessions, HTFL +4** — and **3 never did** (BFLY, ABNB, CHPT).

⚠ **The median is robust, the tail is not.** With a 20-day trend instead of 50, the median moves
11 sessions but p75 goes 40 → 20. **23% of grind births (77 of 341) were named with no trend in force
at all** — latency is undefined for those and they are reported as a count, never folded into the days.

## Step 1 — "do we have the right themes": NOT ANSWERABLE YET, and the reason is the finding

**The ground truth on hand answers a DIFFERENT QUESTION.** The labelling sheet's own README defines a
NO on a themed row as *"idiosyncratic — a company-specific catalyst; the theme was incidental"*. **That
says the theme was not the DRIVER of that alert. It does not say the theme is wrong.**

| | |
|---|---|
| Themed rows he has labelled | **103** — 70 yes / 32 no / 1 unsure = **70 of 102 decided (69%, CI 59-77)** |
| On the LIVE credit path only (the read `in_active_theme` uses) | **55 of 71 = 77%** (CI 66-86; n=72 rows, 1 unsure excluded) |
| NOs carrying a written reason | **10 of 32** |
| Active themes today with ANY label | **9 of 110** |

**Three things make a bar unsettable today:**
1. **22 of 32 NOs have no reason recorded**, and every one carries a company-specific catalyst — the
   sheet's own definition of "idiosyncratic". Whether they are wrong themes or right themes on an
   idiosyncratic alert **cannot be determined from data on hand.** Not estimated.
2. **Four themes carry BOTH a yes and a no on different alerts** (Inflammatory Disease, Semi Wafer
   Foundry, Specialty Pharma, Satellite) — direct proof that some NOs judge the ALERT, not the theme.
3. **31 of the 103 rows asked him to judge a theme the live path never named** — the sheet used an
   unbounded as-of read that walks back to the newest snapshot ever containing the ticker (KODK was
   shown "Agricultural Commodities", last alive 06-11, for an 08-05 alert). Those 16 NOs measure the
   instrument, not an engine decision.

**What each bar would cost to CERTIFY** (95% confidence, zero misses): **90% needs 29 labelled rows ·
95% needs 59 · 99% needs 299.** At the ~15 themed alerts a month the cohort has been adding, **99% is
not certifiable this year.** Today's live-path rate of 16 misses in 71 fails 90/95/99 outright; fixing
every NOTED error reaches 61 of 71 = 86%.

⚠ **The 84.5% → 47.7% gap between his two sittings is NOT a degradation finding** — it is confounded
three ways at once (alert period, whether catalyst text was shown, and the share of stale-bucket rows).

## Recommendation

**Step 2: set it against the GAIN, not the days.** Days move with the trend definition; the +14%
median already-gained is what actually costs him, and it is stable. A target of the shape *"named
before the group has gained X%"* is measurable tomorrow and does not need a new instrument.

**Step 1: no bar can be signed yet, and forcing one would certify the wrong thing.** The smallest
unblocking step is **reason-coding the 22 unnoted NOs** — for each, was the theme wrong, or was the
theme right and the alert idiosyncratic? That is a short sitting with the existing sheet and it
converts an unusable 69% into a real number.

⚠ **Until step 1 has a bar, step 3 stays parked** — that is this task's whole point, and step 3 is
where most of the open theme work sits (#368's boost magnitude, the Nascent exclusion that gave PLTR
and MRNA no boost, the #335 flip). None of it is wrong; all of it is premature.

## What this does not answer

- **Whether any theme is RIGHT in the abstract.** Every number here rests on his labels, which judge
  credited alerts, and on 7 labelled EPs. No theme is judged on returns — that is deliberate.
- **The false-negative rate.** Recall labels cover 8 trading days in the May regime (22 of 31 themeless
  winners had a theme he could name); 136 themeless winners since are unlabelled by design.
- **Theme-level verdicts.** Labels are per credited ALERT: 58 distinct themes, 36 with a single row.
  "How many of today's themes would fail a bar" is uncomputable for **101 of 110**.
- **Whether a sector is masquerading as a theme.** No label identifies one. From the recall side, all
  22 missed-theme names he wrote are broad buckets ("AI Semi", "Biotech related", "Software").
