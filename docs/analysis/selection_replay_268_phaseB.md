# Selection Replay #268 — Phase B (12-month window)

**Window:** 2025-06-09 → 2026-05-04 · **Run:** 2026-06-11/12 (overnight, prod)
**Pipeline:** `scripts/selection_replay_268.py` — scan (backtester historical_scan) →
grade (LIVE `_classify_catalyst_claude` over point-in-time corpus + LIVE floor) →
judge (LIVE `grade_holistic`, Opus, rubric `v2-2026-06-11-revenue-over-eps`) →
simulate (engine ORB, current 1-min geometry) → report.
**Coverage:** 1,307/1,307 candidates graded AND judged (after credit-refill retry;
see §Run integrity). 953 simulated trades (+354 skipped — no fillable ORB / missing bars).

## Headline cohort table (the 6/22 evidence)

| Cohort | n | exp/trade | win% | sum R |
|---|---|---|---|---|
| **PRE-JUDGE system (floor-HIGH)** | 410 | **+0.90R** | 28% | +368.7R |
| **POST-JUDGE system (judge-HIGH)** | 399 | **+0.95R** | 30% | +378.2R |
| judge-DEMOTED floor-HIGHs (avoided) | 94 | +1.01R | 23% | +95.4R |
| judge-PROMOTED moderates (added) | 83 | **+1.26R** | 33% | +104.9R |

Tier counts: floor_HIGH = 577, judge_HIGH = 514 (the n's above are the simulated
subset of each).

## Read

1. **The strategy itself has positive 12-month expectancy.** +0.90R/trade at
   n=410 on the floor system alone. This is the number Phase A (5/05–6/06,
   ≈0R both systems) could not show — the recent window is chop, the 12-month
   window contains the regimes where EP works. Directly relevant to the 6/22
   GO/NO-GO and the kill/scale bands (#268b).
2. **The judge's promote side is the consistent value-add.** +1.26R/trade,
   33% win, in BOTH phases (Phase A teaser: +2.93R on n=17). Moderates the
   floor scores too low but the holistic read elevates are the best cohort in
   the table.
3. **The demote side is NOT reliably avoiding losers over 12 months.** Phase A:
   demotes avoided −0.79R/trade (judge correctly cut losers). Phase B: demotes
   avoided **+1.01R/trade** — over the full year the judge demoted names that
   would have averaged a profit (low 23% win, lumpy: a few big winners carried
   the cohort). The demote signal flips sign by window. Net effect still
   positive because promotes (+104.9R) outweigh demote opportunity cost
   (+95.4R), but **demote-side caution belongs in the kill/scale criteria** —
   e.g. monitor demoted-cohort forward R as a standing judge-health metric
   rather than assuming demotes are saves.
4. **Net system delta is modest but real**: +0.05R/trade, +2pts win rate,
   +9.5R total on ~same n. The judge is not (yet) a transformation of
   selection economics — it is a quality filter whose main proven win remains
   correctness (CBRL-class catalyst misreads) plus the promote cohort.

## Monthly tier distribution (judge activity is steady, not regime-spiky)

| Month | cands | floor_HIGH | judge_HIGH | demoted | promoted |
|---|---|---|---|---|---|
| 2025-06 | 57 | 14 | 13 | 5 | 4 |
| 2025-07 | 124 | 59 | 41 | 25 | 7 |
| 2025-08 | 180 | 92 | 94 | 19 | 21 |
| 2025-09 | 97 | 39 | 30 | 12 | 3 |
| 2025-10 | 167 | 68 | 61 | 18 | 11 |
| 2025-11 | 136 | 65 | 66 | 13 | 14 |
| 2025-12 | 77 | 45 | 29 | 17 | 1 |
| 2026-01 | 104 | 42 | 34 | 15 | 7 |
| 2026-02 | 139 | 57 | 60 | 11 | 14 |
| 2026-03 | 95 | 46 | 45 | 12 | 11 |
| 2026-04 | 117 | 44 | 38 | 14 | 8 |
| 2026-05 | 14 | 6 | 3 | 3 | 0 |

Demote rate ≈ 16% of floor-HIGHs/month, promote ≈ 8/month — active in every
month, including 2025-12/2025-07 where it leaned strongly demote-heavy.

## Run integrity

- **Rubric uniformity:** all 1,307 rows judged under
  `v2-2026-06-11-revenue-over-eps` (the credit-exhaustion retry re-judged the
  early partial under v2 as well — single-rubric cohort, no era split needed).
- **Credit exhaustion incident:** the first judge pass produced 2,122 silent
  fail-opens (initially misdiagnosed as Opus 429s; actually account credits).
  Post-refill paced retry completed 1,307/1,307 at 05:43 UTC 6/12. Permanent
  fix shipped: `llm_health.py` credit-error detection + Telegram alert (#273),
  deployed.
- **Point-in-time hygiene:** detected_at pinned to alert-date 09:35 ET;
  grounded text resolved from the point-in-time corpus; Lane-2 narratives
  fetched as-of alert date; judge writes BY ID + source-scoped (live rows
  untouchable); LIVE_SOURCE_SQL sweep keeps replay rows invisible to all 13
  live readers (deployed pre-open 6/12).

## Caveats (carry into any kill/scale use)

1. **Recall class:** the historical scan recovers ~47% of what live detection
   alerted on (Phase A measure) — the replay cohort is the scan's view of the
   year, not a perfect twin of live. Floor fidelity vs live tiers ~72%.
2. **Narratives dark for most of the window:** Lane-2 narrative candidates
   exist only from ~2026-06; 12 months of judging ran with empty
   `active_narratives` — the judge's theme axis was handicapped vs live.
3. **Delisted/renamed profile gaps:** ~40+ tickers had no yfinance profile
   (404s — ATXS, EXAS, SNDK, CMA…); judged on price/catalyst context only.
4. **Simulation = current 1-min ORB geometry.** W2 entry-mechanics studies
   rerun the same cohort under variant geometries (ATR wide-open, 5-min OR)
   for free via `--simulate`; expectancy here is conditional on today's entry.
5. **Single pass, no error bars.** n≈400 per system arm; the +0.05R delta is
   well inside noise — the promote-cohort effect (+1.26R, n=83) is the
   statistically interesting one.

## What this unlocks

- **#268(b) — kill/scale criteria bands** from this R-distribution →
  `docs/setups/safeguards.md` draft → operator sign-off (CHANGE_PROCESS).
  Operator decision standing: "#1 we wait (kill/scale until Phase B data)" —
  the data has now arrived.
- **W2 entry studies** on the same cohort (Fri 6/12 runway).
- **P6 replay-regression v0** (Sat 6/20): weekly rerun of `--report` over
  accruing data.

*Companion: `docs/analysis/selection_replay_268_phaseA.md` (215-candidate
recent-window study + methodology detail).*
