# #335 theme-axis boost — why we KEEP the dark shadow (2026-07-19 review + operator Q&A)

**One-line:** the theme-axis boost shows "0 would-be upgrades" today, but that is an **instrumentation/coverage/sample ARTIFACT, not evidence the mechanism is useless** — so we keep the (free, dark, zero-risk) shadow running and re-evaluate on DATA, not calendar. This doc captures the reasoning so the next review doesn't re-derive it or wrongly close #335.

## Context
- **#335** = the M1-d decision: flip the meta-rubric **theme axis** into the LIVE (paper) EP grade, or not. The theme boost is **boost-only** — it upgrades a *themed MODERATE* EP toward HIGH (a hot/Accelerating theme adds grade credit). Built DARK (`composite_authority` toggle OFF); shadow rows in `mi_theme_axis_shadow`.
- The operator's methodology priority: **theme/story/catalyst is CENTRAL to EP** (Pradeep/Qullamaggie — the narrative drives the move). Operator ruled **KEEP** (reversed an earlier SHELVE rec).

## The backtest that prompted this (2026-07-19)
Question: do the would-be MODERATE→HIGH theme-boost upgrades beat their MODERATE grade on forward outcomes?
Result on the 466-row `mi_theme_axis_shadow` (2026-03-24 → 2026-07-15):

| | rows | grades |
|---|---|---|
| Themed (themeless_flag=false) | 57 | **100% HIGH** |
| Themeless | 409 | HIGH + MODERATE |
| **Grade split of the WHOLE table** | | **465 HIGH + 1 MODERATE** |

**Hasty first conclusion (WRONG):** "themed EPs are already 100% HIGH → the boost has nothing to upgrade → close #335." The operator pushed back, correctly.

## Operator Q&A — the confounds that overturn the hasty conclusion
1. **Hidden themes (coverage blind spot #467).** "themeless" ≠ "truly no theme." Some MODERATE EPs are almost certainly **themed-but-undetected** — the exact blind spot #467 targets. As coverage improves, themed-MODERATEs appear and the boost gets real targets. **The boost's value is COUPLED to theme coverage** — you can't judge it while coverage is incomplete.
2. **Theme-engine instability + a no-generation period.** Weekly shadow rows: ~17–88/wk (Mar–May) → **6, 6, 8, 1, 5, 5** (Jun–Jul), including a near-dead week. The data is heterogeneous across multiple theme-engine versions and very sparse exactly where new instrumentation exists. Premature to conclude.
3. **Judge ↔ theme-engine cross-pollination (NEW opportunity).** The shadow pairs, per EP, **our engine's theme** with **the judge's grade/narrative**. Where the judge implies a theme our engine missed → feed the engine (#322/#235 direction). Where our engine has a theme the judge ignored → check the judge. A two-way improvement loop; the shadow is already the dataset. (Filed as its own task.)
4. **Sample size — THE decisive confound.** The table is **465 HIGH + 1 MODERATE**. The boost upgrades MODERATE→HIGH, so with ~1 MODERATE row we **cannot evaluate it at all**. Reason: **MODERATE was never instrumented until the coverage-loop S1 fix just landed** — the shadow has been HIGH-only by construction. "0 upgrades" ≠ "no themed-MODERATEs exist"; it = "no MODERATE data to evaluate yet."
5. **Cost/consequence.** `theme_axis_shadow.py` makes **ZERO LLM calls** — deterministic, a DB write per alert. So the shadow is **~free, dark, zero-risk**. Keeping it running costs nothing; killing it discards a free, accruing dataset.

## Conclusions
- The "0 would-be upgrades" is an **artifact** of (a) HIGH-only historical instrumentation (1 MODERATE row), (b) incomplete theme coverage (hidden themes on MODERATEs), and (c) theme-engine instability + sparse recent data — **NOT evidence the boost is useless**.
- **KEEP the shadow running** — free, dark, zero-risk; it accrues a dataset useful even before the boost matters.
- **Do NOT flip live yet** — we literally cannot evaluate the mechanism until MODERATE-instrumented, better-covered data accrues.
- The thing the operator values (theme driving grades) is **already live via the judge** (themed EPs grade HIGH); the deterministic boost is a *potential* refinement for the MODERATE tier we can't yet measure.

## Re-eval criteria (DATA-gated, not calendar) — read this at the next review
Re-open the flip question only when the shadow has accrued enough to actually test it:
- **≥10 MODERATE-tier EP alerts that carry a DETECTED theme** (themeless_flag=false) with settled forward outcomes (fwd_5d and/or realized-R), AND
- a **stable theme-engine window** (no version churn / generation gap over the accrual period), AND
- theme **coverage** (#467) materially improved (fewer blind-spot MODERATEs).
Then: do the would-be upgrades beat their MODERATE grade forward? If yes → flip live (CHANGE_PROCESS + operator sign-off). If the population is still ~0 even with good coverage → *then* it's genuinely redundant with the judge → close.

## Near-term payoff regardless of the boost
Mine the shadow for the **judge↔theme-engine agreement** loop (Q&A #3) — improve the theme engine from the judge's narrative attributions and vice-versa. This pays off even if the boost never goes live.

## Pointers
Shadow table `mi_theme_axis_shadow`; deterministic writer `theme_axis_shadow.log_theme_axis_shadow`; boost math `meta_rubric_compose.compose_final_tier` + `compute_theme_axis_credit`; toggle `composite_authority` (dark). Related: #467 (coverage loop), #322 (judge→radar feed), #235 (gap-discovery), #329 (composite). Prior: `docs/analysis/m1b_regrade_2026-07-13.md`, `docs/analysis/ep_theme_coverage_loop_design_2026-07-13.md`.
