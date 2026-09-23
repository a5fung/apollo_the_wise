# Catalyst labels cross-tab analysis

_N=97 hand-labeled alerts joined to cohort + rubric + classifier outputs._

## §1 — User label × forward outcomes

Does the operator's grading actually predict returns?

| User label | N | Wins | Losses | Pending | Win rate | Avg ret 5d | Median MFE 21d |
|---|---:|---:|---:|---:|---:|---:|---:|
| game_changer | 3 | 2 | 1 | 0 | 66.7% | +6.5% | — |
| game_changer_delayed | 1 | 0 | 0 | 1 | — | — | — |
| strong | 30 | 14 | 6 | 10 | 70.0% | +12.9% | — |
| strong_delayed | 1 | 1 | 0 | 0 | 100.0% | +5.2% | — |
| routine_correct | 1 | 0 | 0 | 1 | — | — | — |
| routine_mislabeled | 56 | 14 | 17 | 25 | 45.2% | +5.4% | — |
| other | 2 | 0 | 1 | 1 | 0.0% | +0.7% | — |
| no_ep | 1 | 0 | 0 | 1 | — | — | — |
| n_a | 2 | 1 | 0 | 1 | 100.0% | +16.0% | -97.2% |

## §2 — User label × current LLM catalyst grade

Where the existing grader is wrong. `routine_mislabeled` × `strong` is the failure-mode count we care about.

| User label | game_changer | routine | strong | total |
|---|---|---|---|---|
| game_changer | 3 | 0 | 0 | 3 |
| game_changer_delayed | 0 | 0 | 1 | 1 |
| strong | 3 | 0 | 27 | 30 |
| strong_delayed | 0 | 0 | 1 | 1 |
| routine_correct | 0 | 1 | 0 | 1 |
| routine_mislabeled | 1 | 0 | 55 | 56 |
| other | 0 | 0 | 2 | 2 |
| no_ep | 0 | 0 | 1 | 1 |
| n_a | 0 | 2 | 0 | 2 |

**Headline**: every row in `routine_mislabeled × strong` = one place the LLM grader incorrectly labeled a routine earnings beat as 'strong' and admitted it to the system.

## §3 — User label × catalyst rubric output (subset with rubric scored)

Only the 50 rubric-sampled tickers (or fewer that overlap the label sheet) appear here. Diagnoses where the rubric diverges from operator grading.

| User label | game_changer | strong | routine_correct | weak | N (with rubric) | Median rubric composite |
|---|---|---|---|---|---|---|
| game_changer | 0 | 0 | 1 | 2 | 3 | 3.2 |
| game_changer_delayed | 0 | 1 | 0 | 0 | 1 | 27.6 |
| strong | 0 | 4 | 6 | 20 | 30 | 9.8 |
| strong_delayed | 0 | 1 | 0 | 0 | 1 | 24.4 |
| routine_correct | 0 | 0 | 0 | 1 | 1 | 6.5 |
| routine_mislabeled | 1 | 2 | 16 | 37 | 56 | 11.4 |
| other | 0 | 0 | 0 | 2 | 2 | 5.6 |
| no_ep | 0 | 1 | 0 | 0 | 1 | 24.4 |
| n_a | 0 | 0 | 0 | 2 | 2 | 0.0 |

## §4 — User label × theme membership (validates meta-rubric architecture)

If theme alignment correlates with `strong` / `game_changer` labels, that confirms theme heat as a separate meta-rubric input.

| User label | In theme | Uncovered | Theme rate | Stage breakdown |
|---|---:|---:|---:|---|
| game_changer | 1 | 2 | 33.3% | Accelerating=1 |
| game_changer_delayed | 1 | 0 | 100.0% | Accelerating=1 |
| strong | 9 | 21 | 30.0% | Mainstream=4, Accelerating=3, Fading=2 |
| strong_delayed | 1 | 0 | 100.0% | Mainstream=1 |
| routine_correct | 0 | 1 | 0.0% | — |
| routine_mislabeled | 4 | 52 | 7.1% | Fading=2, Accelerating=1, Nascent=1 |
| other | 0 | 2 | 0.0% | — |
| no_ep | 0 | 1 | 0.0% | — |
| n_a | 0 | 2 | 0.0% | — |

## §5 — User label × intraday shape (A/B/C/Chop)

| User label | CLASS&nbsp;A | CLASS&nbsp;B | CLASS&nbsp;C | AMBIGUOUS&nbsp;CHOP | AMBIGUOUS&nbsp;DEAD | total |
|---|---|---|---|---|---|---|
| game_changer | 2 | 0 | 0 | 1 | 0 | 3 |
| game_changer_delayed | 0 | 1 | 0 | 0 | 0 | 1 |
| strong | 17 | 1 | 11 | 1 | 0 | 30 |
| strong_delayed | 0 | 0 | 1 | 0 | 0 | 1 |
| routine_correct | 1 | 0 | 0 | 0 | 0 | 1 |
| routine_mislabeled | 27 | 2 | 21 | 6 | 0 | 56 |
| other | 1 | 0 | 1 | 0 | 0 | 2 |
| no_ep | 0 | 0 | 1 | 0 | 0 | 1 |
| n_a | 2 | 0 | 0 | 0 | 0 | 2 |

## §6 — `routine_mislabeled` deep-dive (N=56)

These are alerts the LLM graded 'strong' that operator says are actually routine. They are the prime targets for the magnitude-aware rubric.

### Gap distribution of mislabeled cases

| Gap | N |
|---|---:|
| 8-10% | 1 |
| 10-15% | 14 |
| 15-25% | 34 |
| 25%+ | 7 |

### Outcome of mislabeled cases

- Wins: 14 / 31 (45.2%)
- Losses: 17
- Pending: 25
- Median ret 5d: +4.2%
- Avg ret 5d: +5.4%

- In theme: 4 / 56 (7.1%)

## §7 — Notes thematic aggregation

Keyword-scan of operator notes — which context dimensions appear most. Validates which meta-rubric inputs are load-bearing.

| Dimension | N notes mentioning |
|---|---:|
| theme_aligned | 25 |
| technical | 16 |
| delayed_ep | 11 |
| data_quality_issue | 9 |
| rev_strong | 3 |
| eps_suspect | 2 |

### Dimension co-occurrence by label

| User label | theme_aligned | technical | delayed_ep | guidance_raise | rev_strong | eps_suspect | data_quality_issue |
|---|---|---|---|---|---|---|---|
| game_changer | 1 | 0 | 1 | 0 | 0 | 0 | 1 |
| game_changer_delayed | 0 | 0 | 1 | 0 | 0 | 0 | 0 |
| strong | 15 | 9 | 5 | 0 | 2 | 0 | 2 |
| strong_delayed | 0 | 0 | 1 | 0 | 0 | 0 | 0 |
| routine_correct | 1 | 0 | 0 | 0 | 0 | 0 | 1 |
| routine_mislabeled | 8 | 6 | 3 | 0 | 1 | 2 | 5 |
| no_ep | 0 | 1 | 0 | 0 | 0 | 0 | 0 |

## §8 — Followups surfaced from operator notes

Specific actionable items extracted from operator labels + notes.

- **Leveraged ETFs upstream filter gap** (2 cases): USAX 2026-04-20, USGG 2026-04-20 — shouldn't be admitted as EP candidates at all. Filter at universe selection.

- **M&A buyouts slipped past direction-aware filter** (2 cases): BZH 2026-05-11, KALV 2026-04-29 — investigate why ma_filter.is_likely_ma missed.

- **Catalyst extraction misses** (8 cases): AMBQ 2026-05-12, BAND 2026-04-30, LIVN 2026-05-06, NMAX 2026-04-22, RSI 2026-04-29, SIBN 2026-05-12, STUB 2026-05-14, VG 2026-05-12 — catalyst column doesn't capture the real news. Data extraction issue, not just grading. Affects every downstream consumer.

- **Catalyst date mismatch** (1 cases): CRML 2026-04-27 — system assigned catalyst date doesn't match actual news date. Investigate detector-day-of-news pipeline.

- **Methodological mismatch — not actually EP setup** (1 cases): AIP 2026-05-13 — operator says these are trend-continuation, not EP. Suggests MAGNA53 sometimes admits non-EP shapes.
