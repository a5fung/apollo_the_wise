# #268 Selection Replay — Phase A (calibration window 2026-05-05 → 2026-06-06)

Run 2026-06-11 on prod (`scripts/selection_replay_268.py`; plan
`~/.claude/plans/selection-replay-268.md`). 23 trading days · **215 reconstructed
candidates** (9.3/day) · 215 graded (grounded point-in-time corpus + the LIVE
`_classify_catalyst_claude` + LIVE `_score_ep` floor) · 215 judged (LIVE
`grade_holistic` on Opus, point-in-time Lane-2 narratives) · 215 ORB-simulated
(backtester engine, 1-min ORB, current stop geometry — the CURRENT entry
mechanics, deliberately).

## Cohort expectancy (the headline table)

| Cohort | n | exp/trade | win | sum |
|---|---|---|---|---|
| **PRE-JUDGE system** (floor-HIGH) | 70 | **−0.04R** | 26% | −2.7R |
| **POST-JUDGE system** (judge-HIGH) | 76 | **+0.03R** | 24% | +2.2R |
| judge-DEMOTED floor-HIGHs (avoided) | 9 | **−0.79R** | 11% | −7.1R |
| judge-PROMOTED moderates (added) | 15 | −0.15R | 7% | −2.2R |

## Reading (agent analysis — Phase A is calibration, not a verdict)

1. **The judge's demote side works.** The 9 floor-HIGHs it demoted averaged
   −0.79R / 11% win — genuinely bad trades, removed. This is the CBRL-class
   behavior showing up in aggregate.
2. **The promote side is the weak half** (n=15, 7% win, −0.15R): judge-promoted
   MODERATEs mostly failed in this window. Small n — but directionally worth
   watching, because live promotes become REAL entries. Track the live promote
   cohort; a promote-bar discussion is an operator decision once N accrues.
3. **Both systems sit at ~zero expectancy on this window — the entry-mechanics
   thesis lands hard.** Selection can only pick among the outcomes the bracket
   geometry produces; with the current 1-min ORB + ORB-low stop, even
   judge-selected candidates net ≈ 0R. This is exactly W2's case (and this
   harness reruns entry variants for free: the candidates + verdicts are
   persisted; only `--simulate` changes).
4. Net judge effect on the window: −0.04R → +0.03R per trade (≈ +0.07R/trade of
   selection alpha, demote-driven). Real but small against the geometry leak.

## Calibration caveats (what these numbers are and aren't)

- **Universe recall ~47%**: 127 live alerts in the window, 60 reproduced by the
  daily-gap reconstruction (the scan sees open-vs-prev-close gaps ≥10 on daily
  bars; live fires on premarket/intraday gaps and applies cooldowns/skip-lists/
  window rules the scan doesn't model). The floor-vs-judge COMPARISON is
  internally valid (same candidate set for both); the ABSOLUTE expectancy
  generalizes to the live universe with this caveat.
- **Floor fidelity 72%** on the overlap (33/46 live-HIGHs also floor-HIGH in
  replay) — missing pm_rvol/projection axes account for most of the gap.
- detected_at pinned to alert-date 09:35 ET for corpus + narrative lookahead
  hygiene; FMP profile/market-cap are current values; analyst_upgrades=0;
  narratives dark before #167 (immaterial for this recent window; matters for
  Phase B's older months).
- 56/215 candidates skipped by ORB validation (stop-width rule) — the same
  shared `validate_orb_entry` as live.

## Phase B decision

GO for the 12-month window in monthly batches (projected ≈ 2,100 candidates,
≈ $100–130 LLM spend — under the $150 gate). Two operational notes:
(1) parallelize the grade stage (sem ~3; Phase A ran sequential at ~21s/row =
12h projected for Phase B — concurrency cuts it to ~4h); (2) schedule batches
OUTSIDE market-morning hours so the shared Anthropic org rate limit can't
pressure the live judge (run overnight ET).

Phase B output feeds: the 6/22 GO/NO-GO evidence pack + the kill/scale criteria
bands (#268 part b) + W2's entry-variant comparisons.
