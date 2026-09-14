# Theme bonus by BELONGING — the backtest CHANGE_PROCESS requires (2026-09-13, re-run under the TWO-STAGE rule 2026-09-14)

> Operator: *"EP gets boost if it belongs to a theme, regardless if it's already in a theme or
> not at the time of EP alert."* — and on the backtest's role: *"Is a bug, if we don't like the
> impact then is a question if themes should boost at all, or how much, or if themes are right,
> etc. Those are the legit questions, not if we should boost based on belonging to theme or it's
> actually in list, that is the bug."* — and on the correlation-only first cut, shown D / BKKT /
> QBTS / CMPS with their best-matching themes: *"That is clearly wrong themes for those stocks."*

**Status (2026-09-14): stage 1 (correlation, $0) is MEASURED below. Stage 2 (the fit judgement,
paid) is PENDING one command** — the sandbox this was built in could neither export the API key
nor sync code to the host, and both refusals were correct. Everything below the stage-1 table is
filled by that command's `results.md`, which also names every case the operator asked for.

```
bash   scripts/probes/_ep_theme_belonging_pull.sh /tmp/etb              # read-only COPY ... TO STDOUT, six CSVs (DONE 2026-09-14)
python scripts/probes/_ep_theme_belonging_backtest.py /tmp/etb          # stage 1 + the PRICE (DONE: ~US$2)
ANTHROPIC_API_KEY=... python scripts/probes/_ep_theme_belonging_backtest.py /tmp/etb --spend   # stage 2, once; verdicts cached
```

The fix shipped ON by the operator's ruling; this document is a REPORT on it, not a gate. If the
numbers come back alarming they are reported the same day, plainly, and the revert lever
(`ep_theme_belonging` → `off`, no redeploy, no calls) is his.

## Why the rule changed between the two runs

The 2026-09-13 cut paid on correlation alone: listed OR best market-adjusted correlation ≥ 0.35
with any paying-stage basket. Replayed on the same population before it ran live, it would have
paid **197 of 346 (57%)** against 25 listed, and the admissions were wrong on their face:

| alert | best theme by correlation | corr |
|---|---|---|
| D 2026-05-18 (Dominion Energy, a utility) | Hydraulic Fracturing & Well Completion Services | 0.45 |
| BKKT 2026-05-19 (Bakkt, crypto) | Satellite Imagery & Geospatial Intelligence | 0.49 |
| QBTS 2026-05-21 (quantum computing) | Satellite Imagery & Geospatial Intelligence | 0.41 |
| CMPS 2026-05-18 (Compass Pathways, biotech) | Custom AI Silicon & Chip Architecture | 0.38 |

The 0.35 bar was derived for ONE stock against ONE nominated theme. The EP read took the BEST of
every live paying basket — **a mean of 16.9 baskets per alert (min 4, max 51)** — and best-of-many
clears 0.35 by coincidence. Raising the bar does not help: at any level it drops IREN 2026-07-20
before BKKT. So correlation became the FILTER and the nightly assignment pass's own fit judgement
(`theme_engine.judge_theme_fit`, same prompt / tool / rules) the DECIDER.

## Method / population

- **Population**: every `mi_ep_alerts` row with a score, `alert_date >= CURRENT_DATE − 120`
  (**n = 346**, pulled 2026-09-14). HIGH and MODERATE alerts both — the MODERATEs are where a new
  HIGH crossing can come from.
- **Board as-of each alert**: `mi_themes` rows with `theme_date < alert_date AND theme_date >=
  alert_date − 7`, latest row per name, Retired dropped — the mirror of
  `get_active_themes(stale_after_days=7)` at a morning scan (94% of theme rows are written
  17:00–17:59 ET the night before). Reconstruction is checked against the stored
  `in_active_theme` flag row by row.
- **Stage 1**: the SAME functions the live scan runs (`ep_theme_belonging.session_index`,
  `log_returns`, `excess_returns`, `build_baskets`, `score_belonging`) on `mi_daily_closes` over
  the 60 sessions strictly before the alert date, SPY-subtracted. Not a lookalike. Output per
  alert: listed / paying-stage shortlist (≤3, ≥ 0.35) / Nascent shortlist.
- **Stage 2**: `theme_engine.judge_theme_fit` on the shortlist, with the description the live
  path uses (the nightly one-liner from `mi_ticker_overrides` or the static universe; else the
  yfinance profile paragraph capped at 300 chars). Verdicts cached to `fit_verdicts.json` on run
  one and never re-bought.
- **The Nascent question, separately**: alerts NOT belonging under today's stage set get a
  second judgement against their Nascent shortlist. Its own number, never bundled.
- **Score effect without re-scoring components** (only 10 of 346 alerts carry the full component
  vector): every component is an integer, so `raw = final / multiplier` must be near-integral —
  that checks the multiplier (1.2 if Bull × the row's confidence multiplier); the era bar is the
  row's own `ep_bar` (since #605), else 65 presented on the separation side (≥ 2026-08-22), else
  the regime's raw threshold; the +10's effect is `max(raw + 10, floor) × mult`, presented through
  `apply_output_scale` on the separation side. A conviction floor that BOUND (raw below it) is
  resolved from the stored breakdown where one exists and otherwise reported as *possible*, never
  resolved silently.
- **No lookahead** on any price or board input. The one input that post-dates an alert is a
  company's business description (static text, not price).

## Pre-registered, BEFORE stage 2

| question | the number | what confirms the fix is sane | what says the judgement is not doing its job |
|---|---|---|---|
| newly boosted (unlisted, fit confirmed) | count of 346; correlation alone = 173 | a small minority of the 173, concentrated in names a theme later filed | close to 173 — the judgement confirms whatever it is shown |
| the four wrong cases | D, BKKT, QBTS, CMPS by name | all four REJECTED | any confirmed |
| the case that must work | IREN 2026-07-20 (Bitcoin miners / AI compute) | CONFIRMED | rejected — the shortlist or the judgement lost a real member |
| new HIGH crossings | named, with score before / after at each alert's OWN era bar | a handful, each with a plausible theme | dozens |
| the same with Nascent paying | a separate count — HIS decision | — | — |
| era-bar recheck of "4 HIGHs depended on the +10" | recount at each alert's own bar | — | the earlier read at a flat 70 stands or is corrected here |
| cost | calls, tokens, US$, mean seconds per call | ~US$0.007 and ~5 s per call | — |

## Results — stage 1 (measured 2026-09-14, $0)

| | count | of |
|---|---|---|
| listed on a paying-stage list (reconstructed as-of the alert day) | 25 | 346 |
| listed per the stored `in_active_theme` flag | 22 | 346 |
| reconstruction agrees with the stored flag | 341 | 346 |
| unlisted AND shortlisted against a paying-stage basket at ≥ 0.35 (= what correlation ALONE would have paid) | **173** | 346 |
| unlisted with a Nascent shortlist | 99 | 346 |
| shortlisted but no description anywhere (judgement refused, list membership decides) | 2 | 346 |

Baskets the max ran over, per alert: paying-stage mean 16.9 (min 4, max 51); Nascent mean 7.6
(max 35). The framing's "~119 live themes" is the whole board across stages; the paying-stage
denominator that made best-of-many coincidental is ~17 on a typical alert day.

Price of stage 2, computed before spending: **171 paying + 99 Nascent judgements × ~US$0.0073 ≈
US$2** on `claude-sonnet-4-6` (~1.2k input + ~250 output tokens per call).

## Results — stage 2 (PENDING the `--spend` run; filled from its `results.md`)

*To be filled: list only / belonging-with-fit / newly boosted with denominators; D, BKKT, QBTS,
CMPS each named with verdict and the judgement's own sentence; IREN 2026-07-20 named; every new
HIGH crossing with date, ticker, theme, score before / after, era bar; the "4 HIGHs depend on the
+10" recount at era bars; the Nascent delta; calls, tokens, US$, seconds per call.*

⚠ Already known without stage 2, from the arithmetic: the earlier *"4 HIGHs in 90 days depended
on the +10 (SNOW, HOOD 2026-09-03; BLZE 07-31; AEHR 06-17)"* was read at a flat 70. SNOW and HOOD
at 77.5 on the separation side are raw 50; without the +10, raw 40 presents as 65.0 = the bar, so
neither depends on it. AEHR 06-17 was a MODERATE at 70. The stage-2 run recounts this line at
every alert's own era bar.

## What this does not answer

- **Whether the +10 is the right size, or whether it should differ by stage.** Untested here —
  the operator named these as the legitimate questions that FOLLOW the bug fix.
- **Whether the boosted alerts made money.** Returns on themes are parked by his own sequencing
  (#655: right themes → early themes → only then trading).
- **Causality of the 4-day lag** (EP causing the membership vs the theme forming anyway) — not
  separable from this measurement.
- **The judge.** HIGH here means score ≥ bar; the Holistic Grade Judge overwrites `score_tier` on
  about half of alerts and is not replayed. A crossing counted here is a crossing at the scorer.
- **Intraday drift.** The replay scores each alert once; the live scan re-scores every tick and
  the basket context is fixed for the day. Live, a name first seen at or after 9:30 ET gets no
  judgement that day (the ORB-window guard) and falls to list membership — the replay judges every
  alert as if seen premarket, so it is an UPPER bound on live coverage.
- **Themes that never existed.** A large share of alerts sit in no theme at any stage on the day;
  a belonging test cannot reach a group the engine never formed — that is steps 1–2 of the theme
  programme, not this fix.
- **The judgement's own error rate.** It is the nightly pass's judgement, with the nightly's
  known failure modes; this run measures what it decides on these names, not whether it is right
  in general.
