# B6 gate-inversion recheck (#448) — third independent look, 2026-09-15

`data_gated_reviews.yaml → b6_gate_inversion_recheck` came ripe today: predicate (live-PASS rows since
2026-07-16, any-reason downgrade excluded) read **46** against threshold **8**. Executing its
`action_when_ready` verbatim: fresh prod pull of the three jsonl inputs into a new `data_dir`,
`scripts/_b6_forward_backtest.py` re-run unchanged, plus the live-verdict crosstab the entry asks for.
Read-only. Nothing changed, flipped, or deployed.

ANALYSIS_CARD_PREAMBLE (`docs/methodology/ANALYSIS_CARD_PREAMBLE.md`) applies verbatim: rank by
recall → expected return → capture → tail, never win rate; tail before median.

---

## THE ANSWER

**Reversed/flat, not confirmed — the review's own fork therefore reads "keep 22, close #448," not "open
fork B."** This is the THIRD time this exact question has been asked (7/16 n=7, 9/07 n=45, today n=46)
and the third time it lands on the same side, now from an independently rebuilt pull.

| | July window (5/19→7/16), rebuilt from raw bars | Growth window (7/17→9/15), this run |
|---|---|---|
| 5-session median, PASS vs DOWNGRADE | −8.8% (n=16) vs +1.1% (n=44) — **inverted** | **+0.4% (n=45) vs +0.9% (n=122) — flat** |
| 5-session win rate, PASS vs DOWNGRADE | 12% vs 52% | **51% vs 57%** |
| 5-session tail ≥20%, PASS vs DOWNGRADE | 0/16 (0%) vs 2/44 (5%) | **4/45 (9%) vs 8/122 (7%) — PASS tail is NOT smaller** |
| 5-session p90, PASS vs DOWNGRADE | +5.1% vs +16.4% | **+16.4% vs +13.0% — PASS p90 is HIGHER** |
| downgrade-precision (5d, loser=ret≤0) | 21/44 = 48% | **52/122 = 43%** |
| operator-labelled EPs the gate dropped | 0 | **0** (PLTR, HTFL both PASSED) |

- **The July inversion did not persist into the window that made this review ripe — but it is not
  perfectly flat either.** At 5 sessions PASS and DOWNGRADE are within a point on median (+0.4% vs
  +0.9%) and win rate (51% vs 57%), and PASS's tail is equal-to-better (9% vs 7% ≥20% movers, p90
  +16.4% vs +13.0%). At 20 sessions a median gap reopens (PASS −9.2%, n=38, vs DOWNGRADE +0.5%,
  n=101) while the tail still favours PASS (11% vs 8% ≥20%, p90 +16.9% vs +17.5% — roughly even).
  Under the operator's 2026-09-05 ruling — a median gap with no tail gap is an entry/exit shape, not
  a selection-gate inversion — this is the same shape the 9/07 recheck found on the same 20-session
  cut and did not read as confirmation.
- **The decision-matrix's "downgrade-precision <60%" leg fires (43%), but so would a coin flip**: see
  §Baseline — 44% of ALL scored rows (PASS+DOWNGRADE pooled) were losers at 5 sessions in this same
  window, so a gate with zero forward signal would also show ~43-44% precision. The number is not
  evidence the gate is wrong; it is also not evidence it is right. It is uninformative either way, and
  is reported as such rather than read as a finding.
- **This reproduces the 2026-09-07 recheck** (`docs/analysis/448_b6_gate_inversion_recheck_2026-09-07.md`,
  n=45 live-PASS then) independently — different session, freshly re-pulled prod data, own raw-bar
  reconstruction rather than reused files — and lands on the same side. Two independent pulls eight
  days apart agreeing is itself the strongest evidence in this document.

---

## Population

- **Cohort**: every row of `mi_ep_catalyst_metrics` with `alert_date >= 2026-05-19` (340 rows, 318
  tickers, through 2026-09-15 — today's single alert, FPS, has no raw bar yet and is excluded from
  return stats). Full re-pull today via read-only SELECTs on `mi_ep_catalyst_metrics`,
  `mi_ep_missed_outcomes`, `mi_audit_log`, `mi_daily_closes`, into a fresh `data_dir`
  (`b6_data_2026-09-15/`, session scratchpad, not committed).
- **Live verdict** (matches the yaml predicate exactly — verified: my PASS count for the post-7/16
  slice is 46, identical to the predicate's live COUNT(*)):
  - **PASS** (n=62 total cohort-wide): `mi_ep_catalyst_metrics.q_revenue_yoy_pct` not null AND no
    `catalyst_earnings_revenue_weak_downgrade` audit event of ANY reason for that (ticker, alert_date).
  - **DOWNGRADE** (n=174): an audit event whose `reason` matches `rubric_composite_*_below_*` — the
    composite gate specifically, not the safety-net q-rev-yoy downgrades.
  - **UNSCORED** (n=104): rubric could not score (no revenue extracted); not gated by composite=22;
    reference only.
  - Checked for the confound the 7/16 predicate fix exists to prevent: **0 revenue-bearing rows carry
    a non-composite downgrade reason**, cohort-wide. The predicate's PASS definition and this doc's
    composite-specific DOWNGRADE definition are exhaustive and non-overlapping on this data.
- **Outcome**: computed from raw bars (`mi_daily_closes`), NOT `mi_ep_missed_outcomes`, for the reason
  the 9/07 doc established — that table excludes tickers that were traded, understating PASS n by
  ~12 rows here (script's own outcomes-only crosstab: live PASS n=49; raw-bar reconstruction: n=61
  settled). Formula: `(close at alert-day-open + N trading sessions later − alert-day open) / alert-day
  open`, matching `mi_ep_missed_outcomes`'s own formula. **Validated**: 311 rows overlap both sources
  with a 5-session return; 0 mismatches beyond 0.5 percentage points. `max_hi` = best high from the
  alert-day open through the window, i.e. maximum favourable excursion (MFE) — reported for reference,
  not as a return (see §What this does not answer).
- **Settlement**: last close on disk 2026-09-14. 5-session outcomes settle for alerts through
  roughly 2026-09-05; 20-session outcomes settle through roughly 2026-08-14. n on every figure below
  reflects only settled rows.
- **Era**: the window spans the 2026-08-19 gap-floor change, the 2026-08-22
  lattice/separation-score/shortlist change, and the 2026-08-27 real-time gap authority change — all
  ADMISSION changes, not rubric changes. `git log` on `catalyst_rubric.py` /
  `catalyst_rubric_runtime.py` since 7/16 shows only the 7/16 hardening commit itself (predicate fix +
  replay-fidelity fixes, explicitly logged as producing an IDENTICAL crosstab); `scripts/live_rules.py
  --drift-only` (run today, 0 findings) confirms no doc/code drift. `CATALYST_RUBRIC_MIN_COMPOSITE`
  is still 22 in `constants.py`. So every number below is the SAME gate under CHANGING admission; the
  §Era-split table shows what that does to the population.

## Method

Ran `scripts/_b6_forward_backtest.py` unmodified on the fresh pull (its own report:
`b6_report_2026-09-15.md`, session scratchpad) — this is the literal `action_when_ready` step, and it
also serves as a cross-check: its outcomes-only PRIMARY crosstab (live DOWNGRADE n=166, precision 44%)
matches this doc's raw-bar numbers almost exactly, differing only on PASS n because of the
traded-name exclusion above. All tail/era/baseline analysis below is a second, independent pass
(session-scratch script, same live-verdict definitions) built directly from the fresh pull, because
the shipped script does not report tail counts or era splits and the operator's own rule is tail
first. Composite-fidelity (rederived vs live anchors): 111/174 = 64% within ±2 points — the same
known drift as prior runs (yfinance history-depth gap) — which is why the LIVE-verdict crosstab
(audit-log anchored, zero replay error) is primary throughout, not the script's REPLAYED-verdict
crosstab. **p90 uses nearest-rank** (`sorted[round(0.9*(n-1))]`); the 9/07 doc's July PASS p90
(+0.8%, n=16) does not match this doc's July PASS p90 (+5.1%, n=16) on what is otherwise the same 16
rows — an interpolation-method difference, not a data difference (median, win rate, and ≥20%/≥40%
counts on that same cell agree exactly across both documents). Flagged rather than reconciled; p90
should not be compared across the two documents without accounting for it.

**Positive check on the PASS label**: PASS is defined by an ABSENCE (no downgrade audit event), so a
silently-failed audit writer would also read as PASS. Cross-checked all 46 growth-window PASS rows
against `mi_ep_alerts`: 40 have a matching alert row (39 HIGH-tier, 1 MODERATE, 1 `none`-tier/CBRS).
**6 have NO `mi_ep_alerts` row at all** — FEIM 09-11, FUTU 08-20, GKOS 07-30, PL 09-04, SWBI 09-04,
YOU 08-05 — meaning `mi_ep_catalyst_metrics` extracted a rubric-scorable row for them with no
corresponding live alert ever firing; not resolved here (see §What this does not answer). The other
40 are corroborated by an independent live-alert record, which is what this check was run to confirm.
**Their inclusion is conservative, not a hidden bias toward "flat":** the 5 of 6 with a settled 5d
return are GKOS −5.1%, YOU −28.7%, FUTU +5.9%, PL −17.5%, SWBI −6.5% (4 of 5 losers, including the
two worst rows in the whole PASS arm) — excluding all 6 moves the growth-window PASS 5d arm from
n=45/mean +1.0%/median +0.4%/win 51%/≥20% 9% to n=40/mean +2.5%/median +2.0%/win 55%/≥20% 10%. Every
measure moves TOWARD "not inverted," none away — so leaving the unmatched 6 in the crosstab, as this
document does throughout, is the harder test of the "reversed/flat" verdict, not a softer one.

## The numbers

### A. PRIMARY — live-verdict crosstab, tail first, by era

| era | arm | n (5d) | ≥20% | p90 | median | mean | win% | n (20d) | ≥20% (20d) | median (20d) |
|---|---|---|---|---|---|---|---|---|---|---|
| **Full cohort 5/19→9/15** (pooled, spans eras — see caveat) | PASS | 61 | 4 (7%) | +15.5% | −3.6% | −1.7% | 41% | 54 | 5 (9%) | −8.1% |
| | DOWNGRADE | 166 | 10 (6%) | +14.5% | +0.9% | +1.2% | 56% | 145 | 16 (11%) | +0.1% |
| **July 5/19→7/16 only** | PASS | 16 | 0 (0%) | +5.1% | −8.8% | −9.3% | 12% | 16 | 1 (6%) | −6.8% |
| | DOWNGRADE | 44 | 2 (5%) | +16.4% | +1.1% | +0.2% | 52% | 44 | 8 (18%) | −1.9% |
| **Growth window 7/17→9/15** (what made this review ripe) | PASS | 45 | 4 (9%) | +16.4% | +0.4% | +1.0% | 51% | 38 | 4 (11%) | −9.2% |
| | DOWNGRADE | 122 | 8 (7%) | +13.0% | +0.9% | +1.6% | 57% | 101 | 8 (8%) | +0.5% |
| &nbsp;&nbsp;· pre-8/22 admission | PASS | 41 | 4 (10%) | +16.4% | +2.9% | +2.1% | 56% | 38 | 4 (11%) | −9.2% |
| &nbsp;&nbsp;· pre-8/22 admission | DOWNGRADE | 106 | 8 (8%) | +15.6% | +1.1% | +2.5% | 60% | 101 | 8 (8%) | +0.5% |
| &nbsp;&nbsp;· post-8/22 admission (current) | PASS | 4 | 0 (0%) | −3.2% | −9.7% | −10.0% | 0% | 0 | — | — |
| &nbsp;&nbsp;· post-8/22 admission (current) | DOWNGRADE | 16 | 0 (0%) | +9.6% | −4.8% | −4.6% | 38% | 0 | — | — |

- **Growth window is the operative comparison** (it is what the ripeness gate is measuring): median
  and win rate are within a point either way; **tail favours PASS, not DOWNGRADE** (9% vs 7% ≥20%
  movers, p90 +16.4 vs +13.0) — the opposite of what "confirmed inversion" would require.
- **post-8/22 (current admission) is new since the 9/07 doc** — 4 settled PASS rows, all losers,
  median −9.7%. n=4 is not a conclusion (analysis standard: state and draw none under ~10), but it is
  the first settled evidence under the CURRENT admission system, and it is directionally worse for
  PASS. Flagged, not treated as a finding.
- max-high (MFE) reference, growth window: PASS 5d median +10.8% (win 98% — MFE is positive on
  nearly every row by construction, see caveats); DOWNGRADE 5d median +8.5% (win 98%). Not a return.

### B. Baseline — what a no-signal gate would produce (the "ask what broken looks like" check)

| population | n scored (PASS+DOWNGRADE) | losers at 5d | base loser rate |
|---|---|---|---|
| Full cohort | 227 | 109 | 48% |
| July window | 60 | 35 | 58% |
| Growth window | 167 | 74 | 44% |

**Downgrade-precision in the growth window is 43% (52/122) against a 44% base rate for the same
population.** A gate that downgraded a RANDOM 122 of these 167 rows would land at essentially the same
number. **This is the check the brief asked for, and it reads the same whichever way the gate performs
— so it is reported as uninformative, not as a pass or a fail.** The full-cohort precision (44%
against a 48% base) is likewise indistinguishable from noise; only the July-only window's 48%-vs-58%
gap moves in the "gate is doing something" direction, and that is the window whose inversion did not
recur.

### C. Decision-matrix legs (from `b6_forward_backtest_first_eval`, #448's original decision rule)

| leg | full cohort | growth window (7/17→9/15) |
|---|---|---|
| downgrade-precision >80% AND PASS-edge ≥ DOWNGRADE-edge by ≥1R → keep 22 | NO (44% precision) | NO (43% precision) |
| downgrade-precision <60% → lower threshold | **FIRES** (44%) | **FIRES** (43%) |
| PASS-edge ≤ DOWNGRADE-edge → raise threshold | **FIRES** (mean −1.7 vs +1.2, full; +1.0 vs +1.6, growth) | **FIRES** (small: −0.6pp) |

Both "wrong direction" legs fire simultaneously in both windows, as they did on 7/16 and again on
9/07 — the matrix contradicts itself, which is the same conclusion both prior runs reached:
**threshold retuning is not a valid lever here**, independent of which way the number is nudged.

### D. Operator-labelled EPs (`docs/methodology/operator_labelled_eps.md`) — where they land, n=2 judged

| ticker | date | gate verdict | 5-session outcome |
|---|---|---|---|
| PLTR | 2026-08-04 | **PASSED** | +20.5% |
| HTFL | 2026-08-14 | **PASSED** | +27.4% |
| BFLY | 2026-06-18 | UNSCORED — downgraded for `news_corpus_sparse_no_q_rev` (the safety-net gate, not composite) | +23.3% (per 9/07's prior lookup; not re-derived today) |
| ABNB / TEAM / MRNA / CHPT | 2026-08-07 / 08-07 / 08-19 / 09-03 | never reached `mi_ep_catalyst_metrics` (shortlist / extraction-outage / no-earnings / market-cap floor) | not evaluable by this gate |

**The composite gate has dropped zero of the two labelled EPs it has ever judged.** n=2 — decisive
only by inspection at this size, not a cohort statistic (analysis standard §label-check corollary).

### E. Names — growth-window downgraded winners and passed losers (settled)

Downgraded, then ≥15% in 5 sessions (n=12 of 122 settled DOWNGRADE, 10%): COHR +37.4%, RNG +37.3%,
MRVI +32.5%, EFOR +30.7%, AVAH +28.5%, NIQ +26.3%, MTW +20.7%, IBTA +20.1%, WIX +18.2%, CAI +16.7%,
ITRI +15.8%, GRMN +15.6%.

Passed, then ≤−10% in 5 sessions (n=7 of 45 settled PASS, 16%): YOU −28.7%, KMT −24.0%, BW −22.9%,
PL −17.5%, CBRS −17.2%, NVCR −15.4%, SNOW −12.8%.

Both lists exist under either verdict — the gate is not cleanly separating either direction on the
named names, which is the same picture the tail numbers in §A give.

## ⚖ THE LINE

`CATALYST_RUBRIC_MIN_COMPOSITE` (currently 22) and the composite's tier-downgrade authority are a
detection criterion — changing either is the operator's sole call, via `CHANGE_PROCESS` + sign-off,
never mine. **Nothing was changed, flipped, or deployed by this review.** What this document adds is
evidence: the review's own pre-declared fork ("if CONFIRMED → fork B; if reversed/flat → keep 22,
close #448") reads **reversed/flat** on today's independently-rebuilt pull, same as the 9/07 recheck.
Whether to formally close #448 / this yaml entry on that basis is the operator's decision, not mine —
this document does not touch `data_gated_reviews.yaml`, `PLAN.md`, or make any commit.

## What this does not answer

- **The current admission system is barely represented.** Only 4 settled PASS rows and 16 settled
  DOWNGRADE rows exist under the post-8/22 lattice/shortlist/separation-score rules that are actually
  live today; the rest of this document's evidence — including all of the 9/07 recheck's evidence — is
  about the gate operating under admission rules that no longer run. A future re-look needs the
  post-8/22 cohort to grow, not just more calendar time.
- **Not our realized return.** Every figure is alert-day-open to close N sessions later, no stop, no
  R — a day-0-open buyer's view. `max_hi` is maximum favourable excursion and is positive on nearly
  every row by construction; its ~98-100% "win rate" is not evidence of anything and should not be
  read as a return statistic. The entry/exit layer (#545) owns the median gap between MFE and what a
  stop-and-target strategy would actually capture; this document does not touch it.
- **Regime (QQQ) adjustment, the gapped-≥9%-at-open tradeable subset, and the Pradeep 39% bar were not
  independently re-derived today** — this document relies on the 9/07 recheck's finding that none of
  them change the conclusion, rather than re-running them fresh. If that finding were wrong, this
  document would not catch it.
- **Fork B's downstream cost (over-admission into alerts/auto-entry) is not estimated here** — the
  9/07 recheck's bounded estimate (~2 extra HIGH alerts/day) is the only figure available and was not
  refreshed.
- **Composite replay fidelity is 64% within ±2 points of the live anchor** — the REPLAYED-verdict
  crosstab (script's own threshold-sweep table) inherits that noise and is not used as evidence here;
  only the LIVE-verdict (audit-log-anchored, zero replay error) crosstab is.
- **6 of 46 growth-window PASS rows have no corresponding `mi_ep_alerts` row** (§Method) — why
  `mi_ep_catalyst_metrics` extracted them without a live alert firing (a different extraction path,
  a backfill, or an alert-pipeline gap) is not investigated here; their outcomes are included in the
  PASS crosstab as pulled, unflagged individually beyond this note.
- **n=2 on the labelled-EP check.** Readable by eye at this size; not a base-rate claim about the
  rubric's true drop rate on real EPs generally.
- **Whether the composite axes measure the right thing at all** (surprise vs magnitude, the 9/05
  rulings) is untouched — this document only asks whether the 22-point cutoff separates outcomes, and
  finds that on this evidence it still does not, in either direction.
