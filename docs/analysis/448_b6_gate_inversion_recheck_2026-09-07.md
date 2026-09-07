# #448 B6 re-look — does the composite gate's "inversion" hold at bigger N? (2026-09-07)

**The pre-committed re-look** (`data_gated_reviews.yaml → b6_gate_inversion_recheck`, filed 2026-07-16 when the
operator ruled A — OBSERVE on n=7). Gate met: 45 live-PASS rows since 7/16 (yaml predicate, run verbatim on prod
2026-09-07), 41 with a settled 5-session outcome. Read-only. Nothing changed. Threshold 22 untouched.

---

## THE ANSWER

**No — the inversion does not hold, and on the measure the operator has since ruled governs (the tail) the gate
never separated in either direction. Recommendation: keep 22, do not open fork B, close the re-look.**

| the question as pre-committed | July (5/19→7/16) | NEW window (7/17→9/04), standalone |
|---|---|---|
| 5-session median, PASS vs DOWNGRADE | −5.1% (n=7) vs 0.0% (n=40) — "inverted" | **+2.9% (n=41) vs +0.9% (n=113) — flat, slightly the right way** (July's exact method — table outcomes, traded names excluded: +3.8% n=33 vs +0.9% n=113) |
| 5-session win rate, PASS vs DOWNGRADE | 29% vs 50% | **56% vs 59%** |
| big winners ≥20% in 5 sessions, PASS vs DOWNGRADE | 0/16 vs 2/44 (rebuilt from raw bars, see §Contradictions) | **4/41 (10%) vs 8/113 (7%)** |
| big winners ≥20% in 20 sessions, PASS vs DOWNGRADE | 1/16 vs 8/44 | **2/31 (6%) vs 6/83 (7%)** |
| labelled real EPs the composite gate dropped | 0 | **0** (PLTR and HTFL both PASSED; no discarded winner is a labelled EP) |

- **The July 5-day median inversion did not survive.** On the same measure, same return basis, same live-verdict
  method, the new window shows PASS slightly ahead on median and level on win rate.
- **At 20 sessions a median gap reappears** (PASS −10.7% n=31 vs DOWNGRADE +1.3% n=83; survives subtracting QQQ:
  −12.5% vs +0.4%) — **but with no tail difference** (6% vs 7% big winners, p90 +16.7 vs +17.4). Under the
  operator's 2026-09-05 ruling (*"big tail is the key ingredient, median can be somewhat managed with entry and
  exit"*) a median difference with no tail difference is an entry/exit matter, not a reason to change a selection
  gate. It is the same shape the 9/05 session withdrew "inverted" on.
- **Fork B is not supported** — its trigger was written on 7/16 assuming the median was the signal; the operator has
  since ruled it is not. And fork B has a visible cost: the 122 downgraded names (33 alert days) would keep their
  strong-or-better tier, so the cost lands on **alerts and auto-entries** — 82 of them gapped ≥9% at the open, and at
  the PASS arm's own HIGH-alert rate (38 of 45 = 84%) that is an upper bound of **~69 extra HIGH alerts in 33 days,
  about 2 a day on top of today's volume** (§H). The tier is one score input, so treat it as a ceiling, not a forecast.
- **Do not retune 22 either**: the replayed sweep (secondary) is flat on the tail at every cut 16→28 (§K).

---

## ⚠ Contradictions with the brief and with the July document — stated explicitly

1. **This question was already re-cut on 2026-09-05 at N=174 and the operator ruled on it.** PLAN #448 and
   `docs/analysis/448_tail_retraction_2026-09-05.txt`: on the full 5/20→9/04 window, 20 settled sessions, big
   winners were DOWNGRADED 7/127 (6%) vs PASSED 3/47 (6%); "inverted" was **withdrawn**; his verdict: *"our
   rubric is inconclusive but positive is our EPs does get through."* The brief does not mention this. My
   reproduction of the 9/05 cells is exact on the alert-day-close basis (§I), so this run and 9/05 measure the
   same thing; this document is the pre-committed re-look run through the pre-committed script, standalone on the
   post-7/16 window, and it reaches the same answer.
2. **July's PASS n=7 was not "only 7 had settled".** `mi_ep_missed_outcomes` only holds names that were NOT
   traded, so every PASS name that was bought dropped out of July's crosstab. Four July PASS names were traded
   (DY, DELL, NAVN, WDFC) — all four lost. Rebuilt from raw bars July is PASS n=16 median −8.8% / 12% win vs
   DOWNGRADE n=44 median +1.1% / 52% — **July understated its own inversion; it did not flatter it.**
3. **The July note "ret basis = close_d0→close_d5" is wrong.** `missed_outcomes.py:650` has computed
   `(close_d5 − open_d0)/open_d0` since the table first shipped on 2026-05-11. Every number in both documents is
   **from the alert-day OPEN**, no stop. July and today are on the same basis.
4. **Brief says 37 settled; raw bars settle 41 of 45.** The 4 unsettled are the 9/03–9/04 alerts (AGX, SNOW, PL,
   SWBI). The outcome table had 33 of them; the other 8 were traded names it excludes.
5. **The gate's tier authority was already overridden inside this window.** The Holistic Grade Judge (toggle
   `holistic_judge_enabled`; the alert rows carry `grade_engine_authority = judge`) put 4 rubric-downgraded
   names back to HIGH between 8/04 and 8/12: AMRC −18.9%, CAI +16.7%, MTW +20.7%, CRWV −16.4% (5-session). Two
   right, two wrong. n=4, no conclusion.
6. **Downgrade-precision is 41%, not 50%** — i.e. 59% of the names the gate downgraded went UP over 5 sessions.
   The July decision matrix would read that as "lower the threshold"; the sweep says lowering changes nothing
   on the tail. The matrix's premise (the gate is at least directionally right) is still not met.

---

## 1. The decision this serves, and what would change it

- **Decision:** keep `CATALYST_RUBRIC_MIN_COMPOSITE = 22` and close #448's re-look, or open fork B (neutralise
  the composite's tier-downgrade authority via CHANGE_PROCESS + operator sign-off).
- **Pre-declared cuts (written before measuring):** (A) live-verdict crosstab, 5 and 20 sessions, from raw bars,
  tail first; (B) the gapped-at-the-open subset; (C) minus-QQQ and up/down-tape split; (D) pre/post-8/22 era
  split; (E) names both ways; (F) operator-labelled EPs; (G) judge overrides; (H) fork-B admission cost;
  (I) bridge to 9/05; (J) July re-stated, then pooled; (K) the script's replayed threshold sweep, plus a tail
  version of it at each cut.
- **What would have supported fork B:** DOWNGRADE showing materially more ≥20%/≥40% winners than PASS on the
  tradeable subset, surviving the QQQ adjustment, with a labelled real EP among the discarded names.
- **What would make this wrong:** the population (below); an era mix inside the window (§D); the return basis
  (from the open, no stop — a day-0 open buyer's view, not our R).

## 2. Method and population

- **Population:** every row of `mi_ep_catalyst_metrics` with `alert_date > 2026-07-16` (228 rows, 7/17→9/04).
  These are the names that reached the earnings-catalyst extraction, not only alerts. Live verdict per the yaml
  predicate verbatim: **PASS** = `q_revenue_yoy_pct` not null and NO `catalyst_earnings_revenue_weak_downgrade`
  event of any reason (45); **DOWNGRADE** = a `rubric_composite_*_below_22` event (122); **UNSCORED** = rubric
  could not score (61; not gated by 22; reference only). No scorable row carried a non-composite downgrade
  reason, so the yaml definition and the script's definition agree exactly (0 differences, both windows).
- **Outcome:** computed from `mi_daily_closes` (raw bars) with the table's own formula — return from the
  alert-day OPEN to the close 5 / 20 sessions later; best high within the window likewise from the open. Checked
  against `mi_ep_missed_outcomes` on all 296 overlapping rows: 0 mismatches >0.5pp. Raw bars are used because the
  table excludes traded names (§Contradictions 2). Last close on disk 2026-09-04: 5-session settles alerts
  ≤8/28, 20-session settles alerts ≤~8/06. No stop, no R — percent from the open, as July.
- **Era:** the window spans the 8/19 gap floor 10→9, the 8/22 lattice / separation score / liquidity shortlist,
  and the 8/27 real-time gap authority. 198 of 228 rows are pre-8/22; post-8/22 has 4 PASS and 16 DOWNGRADE, none
  with a settled 20-session outcome. **The 20-session arm is entirely the pre-8/22 system.** The rubric scoring
  code (`catalyst_rubric.py`, `catalyst_rubric_runtime.py`) has no commits after 2026-07-16 (git log).
- **Tools:** `scripts/_b6_forward_backtest.py` run UNCHANGED (three runs: full cohort, new window, new window
  with the table's outcomes); `scripts/live_rules.py --drift-only` run first (4 stale-status drift notes — two in
  `catalyst_rubric.md` about the #321 YoY-recovery deploy status, two elsewhere; none about the composite gate); `python scripts/operator_now.py` = 2026-09-07 06:45 PDT. Inputs pulled read-only with
  SELECTs on `mi_ep_catalyst_metrics`, `mi_ep_missed_outcomes`, `mi_audit_log`, `mi_ep_alerts`, `mi_live_trades`,
  `mi_daily_closes`. Working files in the session scratchpad `b6_2026-09-07/` (ephemeral; the SQL is one SELECT per
  table, alert_date ≥ 2026-05-19).

## 3. The numbers

### A. PRIMARY — live-verdict crosstab, NEW window standalone (7/17→9/04). Zero replay error.

Tail first, then the middle. Return from the alert-day open, no stop.

| arm | n | ≥20% | ≥40% | p90 | best | median | mean | % up | p10 |
|---|---|---|---|---|---|---|---|---|---|
| **5 sessions** PASS | 41 | 4 (10%) | 0 | +16.4% | +27.4% | +2.9% | +2.1% | 56% | −15.4% |
| **5 sessions** DOWNGRADE | 113 | 8 (7%) | 0 | +15.0% | +37.4% | +0.9% | +2.1% | 59% | −11.2% |
| 5 sessions UNSCORED (ref) | 59 | 4 (7%) | 0 | +15.1% | +26.2% | +0.3% | +0.8% | 51% | −13.9% |
| **20 sessions** PASS | 31 | 2 (6%) | 0 | +16.7% | +28.1% | −10.7% | −7.2% | 29% | −23.4% |
| **20 sessions** DOWNGRADE | 83 | 6 (7%) | 2 | +17.4% | +65.5% | +1.3% | +3.3% | 59% | −14.3% |
| 20 sessions UNSCORED (ref) | 29 | 2 (7%) | 0 | +17.9% | +31.2% | +0.4% | −0.8% | 55% | −26.8% |
| best high in 5 PASS | 41 | 5 (12%) | 0 | +23.7% | +29.2% | +11.4% | +11.8% | — | — |
| best high in 5 DOWNGRADE | 113 | 13 (12%) | 3 | +20.8% | +45.6% | +8.8% | +10.2% | — | — |
| best high in 20 PASS | 31 | 5 (16%) | 1 | +28.3% | +49.9% | +12.6% | +14.1% | — | — |
| best high in 20 DOWNGRADE | 83 | 16 (19%) | 4 | +26.1% | +71.5% | +10.9% | +13.9% | — | — |

- Downgrade-precision (downgraded name went ≤0 over 5 sessions): **46/113 = 41%**; over 20 sessions 34/83 = 41%.
- The two ≥40% at 20 sessions (RNG +65%, WIX +57%) are both on the DOWNGRADE side and **neither gapped at the
  open** (RNG +4.9%, WIX −0.7%) — not setups by the operator's "must have been theoretically tradeable" rule.
  On the gapped subset (B) there is no ≥40% on either side.

### B. Tradeable subset — gapped ≥9% at the open by raw bars (160 of 228)

| arm | n | ≥20% | ≥40% | p90 | median | % up |
|---|---|---|---|---|---|---|
| 5 sessions PASS | 29 | 3 (10%) | 0 | +16.9% | +0.4% | 52% |
| 5 sessions DOWNGRADE | 75 | 6 (8%) | 0 | +12.7% | +0.1% | 51% |
| 20 sessions PASS | 23 | 2 (9%) | 0 | +4.3% | −10.7% | 22% |
| 20 sessions DOWNGRADE | 54 | 3 (6%) | 0 | +13.9% | −0.3% | 48% |

Same at a 10% floor (PASS 29 / DOWNGRADE 71; identical PASS cells). 68 rows did not gap ≥9% at the open
(14 PASS, 40 DOWNGRADE) — pre-market prints that faded, or late alerts.

### C. Regime — same sessions on QQQ, and the stock minus QQQ

| cut | n PASS / DOWN | PASS ≥20% | DOWN ≥20% | PASS p90 | DOWN p90 | PASS median | DOWN median |
|---|---|---|---|---|---|---|---|
| 5 sessions minus QQQ | 41 / 113 | 3 (7%) | 6 (5%) | +18.4% | +12.4% | −0.3% | −0.6% |
| 20 sessions minus QQQ | 31 / 83 | 2 (6%) | 6 (7%) | +15.8% | +14.5% | −12.5% | +0.4% |
| QQQ UP over the 5 sessions, raw | 25 / 62 | 3 (12%) | 4 (6%) | +18.9% | +15.8% | +5.8% | +3.6% |
| QQQ DOWN over the 5 sessions, raw | 16 / 51 | 1 (6%) | 4 (8%) | +14.8% | +12.1% | −1.7% | −1.3% |

QQQ's 5-session move over the 213 settled alert dates: median +1.0%, range −6.0% to +7.0%. **Regime does not
explain anything here because at 5 sessions there is nothing to explain**, and the 20-session median gap
survives the adjustment. By alert week the 5-session medians flip sign week to week (wk31 PASS −2.4 vs DOWN
+3.6; wk32 +3.8 vs +0.3; wk33 +11.8 vs −7.3; wk34 −3.7 vs +12.1, n=3/5) — small weekly cells, no consistent
direction, so the July "rising tape made PASS worse" reading does not recur.

### D. Era split inside the window

| era | n | PASS n / DOWN n (5 sessions) | PASS ≥20% | DOWN ≥20% | PASS median | DOWN median |
|---|---|---|---|---|---|---|
| pre-8/22 | 198 | 41 / 106 | 4 (10%) | 8 (8%) | +2.9% | +1.1% |
| post-8/22 | 30 | 0 / 7 settled | — | 0 | — | −3.8% |

**Every settled PASS row is pre-8/22.** This document says nothing about the gate under the current shortlist,
score and gap authority; that cohort is 30 rows and mostly unsettled.

### E. Names — what 22 threw away and what it let through (NEW window)

**Downgraded, then went on to win** (≥+10% in 5 sessions or ≥+20% in 20), composite / open gap / 5s / 20s:

| name | date | composite | gap at open | 5 sessions | 20 sessions | note |
|---|---|---|---|---|---|---|
| RNG | 07-24 | 15.0 | +4.9% | +37.3% | +65.5% | did not gap — not a setup |
| WIX | 08-04 | 17.0 | −0.7% | +18.2% | +56.5% | did not gap — not a setup |
| COHR | 07-31 | 15.0 | +10.8% | +37.4% | +1.2% | gave it all back |
| CAI | 08-06 | 17.5 | +15.5% | +16.7% | +33.3% | judge restored HIGH; unfilled |
| MRVI | 08-19 | 18.0 | +17.0% | +32.5% | n/a | |
| EFOR | 07-30 | 12.0 | +3.2% | +30.7% | +31.0% | did not gap |
| AVAH | 08-13 | 19.0 | +11.5% | +28.5% | n/a | |
| NIQ | 08-11 | 18.0 | +17.4% | +26.3% | n/a | |
| MTW | 08-07 | 17.0 | +20.6% | +20.7% | +24.9% | judge restored HIGH; unfilled |
| IBTA | 08-04 | 16.1 | +24.5% | +20.1% | +21.8% | |
| HURN / CSTL / ITRI / GRMN / FORM / MRVI 08-20 / SWIM / EL / ROAD / LFUS | — | 9–21 | — | +10% to +16% | mixed | 10 more in the +10–16% band |

Total downgraded rows 122; 20 of the 113 settled went ≥+10% in 5 sessions (18%). **None is an operator-labelled EP.**

**Passed, then lost** (≤−10% in 5 sessions): YOU 08-05 −28.7% (gapped +16%), KMT 08-05 −24.0% (HIGH, unfilled),
BW 08-11 −22.9% (HIGH, filled, −$50), CBRS 08-17 −17.2%, NVCR 07-23 −15.4% (HIGH, filled, −$24). 5 of 41.

**Passed, then won** (≥+10% in 5 or ≥+20% in 20): LIFE 08-04 +22.4%/+28.1%, **HTFL 08-14 +27.4%**, U 08-06 +27.2%,
**PLTR 08-04 +20.5%/+24.0%** (filled, +$119), ZBRA +16.0%, TH +16.4%, ETON +15.5% (filled, +$19), HAS +14.0%,
NESR +11.8%, LFST +11.2%, ONTO +10.6%. 11 of 41.

### F. Operator-labelled real EPs (`docs/methodology/operator_labelled_eps.md`) — where they fall

| name | date | composite gate | outcome from the open |
|---|---|---|---|
| PLTR | 08-04 | **PASSED** — one of the two labelled EPs the gate ever judged | +20.5% / +24.0% |
| HTFL | 08-14 | **PASSED** — the other | +27.4% / n/a |
| TEAM | 08-07 | never reached it (extraction failed, grade kept) | — |
| MRNA | 08-19 | never reached it (no earnings extraction) | — |
| CHPT | 09-03 | never reached it (market-cap floor) | — |
| ABNB | 08-07 | never reached it (shortlist) | — |
| BFLY | 06-18 | UNSCORED — safety-net gate, not the composite | +23.3% / −7.2% |

**The composite gate has dropped zero labelled real EPs (2 judged, 2 passed).** The recall failures on this list
are all upstream of it — shortlist, market-cap floor, extraction, news retrieval.

### G. The judge overrode the gate in-window — n=4, no conclusion

AMRC 08-04 (composite 14.0) −18.9% / −29.2% · CAI 08-06 (17.5) +16.7% / +33.3% · MTW 08-07 (17.0) +20.7% / +24.9% ·
CRWV 08-12 (18.8) −16.4% / n/a. All four alerted HIGH on judge authority; none filled.

### H. Fork-B cost — what neutralising the gate would push downstream (NEW window)

- The 122 downgraded rows were already graded — neutralising the gate does not add grading work, it keeps them at
  strong-or-better tier, so the cost lands on alerts and auto-entries. **82 gapped ≥9% at the open**; only 6
  alerted anyway (4 HIGH via the judge). Upper bound: at the PASS arm's HIGH-alert rate (38/45 = 84%) that is
  **~69 extra HIGH alerts over 33 alert days ≈ 2.1 per day**, against 38 PASS HIGH alerts in the same span — a
  near-tripling of the earnings-path alert flow. It is a ceiling: the tier is one score input and the exact
  number cannot be replayed from here. **The over-admission cost is real and bounded above; the under-admission
  cost (a dropped labelled EP) is zero.** P14: only one of those is visible.
- The PASS arm in live trading, for the record (entry/exit layer, not selection): 45 passed, 38 alerted HIGH,
  37 got a live trade row, **7 filled**, net **−$3** (PLTR +119, ETON +19, FTNT −7, NVCR −24, WKC −24, BLZE −37,
  BW −50).

### I. Bridge to the 9/05 cut — the same 174 rows, three return bases (full window, 20 settled sessions)

| basis | DOWNGRADE ≥20% | DOWNGRADE ≥40% | DOWNGRADE p90 | DOWNGRADE median | PASS ≥20% | PASS ≥40% | PASS p90 | PASS median |
|---|---|---|---|---|---|---|---|---|
| alert-day close → close+20 (9/05's) | 7/127 (6%) | 0 | +14.0 | −0.2% | 3/47 (6%) | 1 | +12.7 | −6.8% |
| alert-day open → close+20 (this doc, July's table) | 14/127 (11%) | 2 | +20.6 | +0.5% | 3/47 (6%) | 0 | +13.4 | −10.1% |
| prior close → close+20 (includes the gap) | 42/127 | 8 | +32.7 | +13.9% | 8/47 | 3 | +25.4 | +2.8% |

The close basis reproduces 9/05 to the row. The open basis adds the alert day's open-to-close run; that is the
whole 7 → 14 difference on the DOWNGRADE side — OKTA, MLKN, PRGS, ANGO, MAN, EFOR, IBTA, MTW cross 20% only when
day 0 is counted (PRCH drops out), and 4 of those 8 did not gap ≥9% at the open. On the PASS side PLTR crosses
the same way (LFST drops out). On 9/05's basis the two arms are identical; on the open basis the pooled
20-session gap is 11% vs 6%, and in the new window standalone it is 7% vs 6% (§A). Same rows, same answer.

### J. July re-stated from raw bars, then pooled — pooled ONLY here

| window | arm | n (5s) | ≥20% 5s | p90 5s | median 5s | % up 5s | n (20s) | ≥20% 20s | ≥40% 20s | median 20s |
|---|---|---|---|---|---|---|---|---|---|---|
| July 5/19→7/16 | PASS | 16 | 0 | +0.8% | −8.8% | 12% | 16 | 1 (6%) | 0 | −6.8% |
| July 5/19→7/16 | DOWNGRADE | 44 | 2 (5%) | +15.9% | +1.1% | 52% | 44 | 8 (18%) | 0 | −1.9% |
| NEW 7/17→9/04 | PASS | 41 | 4 (10%) | +16.4% | +2.9% | 56% | 31 | 2 (6%) | 0 | −10.7% |
| NEW 7/17→9/04 | DOWNGRADE | 113 | 8 (7%) | +15.0% | +0.9% | 59% | 83 | 6 (7%) | 2 | +1.3% |
| POOLED 5/19→9/04 | PASS | 57 | 4 (7%) | +15.7% | −3.0% | 44% | 47 | 3 (6%) | 0 | −10.1% |
| POOLED 5/19→9/04 | DOWNGRADE | 157 | 10 (6%) | +15.7% | +0.9% | 57% | 127 | 14 (11%) | 2 | +0.5% |

Pooling adds nothing the two windows do not already say: July's median inversion was real and did not recur;
the tail is flat in both; the pooled 20-session 11% vs 6% is the RNG/WIX/EFOR non-gapper effect (§I).
**Are the two cohorts comparable?** Same live-verdict method, same return basis, same rubric code. They differ in
tape and season: the new window is peak earnings season (weeks 30–33, 7/20→8/14, hold 185 of 228 rows = 81%)
under pre-8/22 admission rules; July was a quiet tape under the 10% floor. The July PASS arm (n=16) faded almost
uniformly (2 of 16 up over 5 sessions) on a flat tape (QQQ median −1.2% over those windows, 7 of 16 up); the new
PASS arm (n=41) did not fade (23 of 41 up). That is a cohort/season difference, not evidence the gate learned
anything — the tail never moved in either window.

### K. SECONDARY — the script's replayed composite, NEW window (known fidelity gap)

- Fidelity vs live downgrade anchors: **86/122 within ±2 points (70%; July was 28/44 = 64%)**; misses split
  18 high / 18 low. Live-vs-replay verdict agreement 143/167 = 86% (15 live-PASS replay below 22; 9 live-DOWNGRADE
  replay above). Same history-depth limitation as July.
- Replayed at 22, 5 sessions: PASS n=36 median −0.1% / 50% up vs DOWNGRADE n=118 median +2.0% / 61% up;
  20 sessions PASS n=25 median −10.7% vs DOWNGRADE n=89 +1.3%.
- **Tail at each cut (the version that matters):**

| cut | PASS n 5s | PASS ≥20% 5s | PASS p90 5s | DOWN n 5s | DOWN ≥20% 5s | DOWN p90 5s | PASS n 20s | PASS ≥20% 20s | DOWN n 20s | DOWN ≥20% 20s |
|---|---|---|---|---|---|---|---|---|---|---|
| 16 | 101 | 8 (8%) | +16.0 | 53 | 4 (8%) | +15.2 | 74 | 5 (7%) | 40 | 3 (8%) |
| 18 | 78 | 5 (6%) | +15.7 | 76 | 7 (9%) | +17.0 | 54 | 3 (6%) | 60 | 5 (8%) |
| 20 | 53 | 3 (6%) | +15.9 | 101 | 9 (9%) | +15.8 | 39 | 3 (8%) | 75 | 5 (7%) |
| **22** | 36 | 3 (8%) | +16.0 | 118 | 9 (8%) | +15.9 | 25 | 2 (8%) | 89 | 6 (7%) |
| 24 | 28 | 3 (11%) | +17.6 | 126 | 9 (7%) | +15.7 | 21 | 2 (10%) | 93 | 6 (6%) |
| 26 | 9 | 1 | +16.9 | 145 | 11 (8%) | +16.0 | 6 | 1 | 108 | 7 (6%) |
| 28 | 6 | 1 | +19.0 | 148 | 11 (7%) | +15.9 | 3 | 1 | 111 | 7 (6%) |

No cut from 16 to 28 moves the big-winner share or p90 on either side. Threshold retuning is not the lever, in
either direction — the same conclusion July reached from the median, now on the tail.

## 4. What this does not answer

- **Nothing about the current system.** Every settled PASS row is pre-8/22; the post-8/22 cohort (4 PASS,
  16 DOWNGRADE) has no settled 20-session outcome. Re-check at the next natural point is a data-gated question,
  not a date.
- **Not our R.** Return from the alert-day open with no stop. A −29% row (YOU) would have been about −1R live.
  The entry/exit layer (#545) owns the median; this doc does not touch it.
- **Whether fork B would over-admit.** 3.7 names/day back into grading is the input; how many clear the 65 bar,
  fill, and what they cost cannot be replayed from here.
- **Whether the rubric measures the right thing.** The 9/05 rulings (edge is surprise, not magnitude; earnings is
  one EP type) stand untouched; this doc only asks whether the 22 gate separates on the tail. It does not.
- **The Pradeep 39% bar** — still not evaluable (script add-on: q0∧q1≥39% n=1, DELL, no settled outcome).
- **The UNSCORED arm** (61 rows, 28 HIGH, 28 traded) is now the larger live population and is where the BFLY
  class lives; it is reference only here and was not studied.
- **n on the labelled-EP check is 2** (PLTR, HTFL). It is decisive at that size only because both are readable
  by eye; it is not a cohort statistic.

## ⚖ THE LINE

`composite_min` and the composite's tier-downgrade authority are detection criteria. This document is evidence
and one recommendation (keep 22, close the re-look, do not open fork B). Nothing was changed, flipped, deployed
or proposed for deployment. The call is the operator's, via CHANGE_PROCESS if he rules otherwise.

*Feeds #448. Runs: `scripts/_b6_forward_backtest.py` (unchanged) ×3 in the session scratchpad; per-row dumps
`b6_rows.json`; measurement script `b6_analysis.py` (scratchpad, pre-declared cuts A–K). Prod: SELECTs only.*
